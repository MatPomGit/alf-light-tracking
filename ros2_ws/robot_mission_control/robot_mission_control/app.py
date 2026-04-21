"""Main entrypoint for robot mission control desktop app."""

from __future__ import annotations

import importlib
import importlib.util
import sys
from datetime import timedelta
from pathlib import Path
from typing import Optional

# [AI-CHANGE | 2026-04-21 14:43 UTC | v0.175]
# CO ZMIENIONO: Rozszerzono bootstrap ścieżek importu i przeniesiono go przed importy zewnętrzne (PySide6),
#               aby zawsze przygotować poprawne `sys.path` jeszcze przed ładowaniem modułów aplikacji.
# DLACZEGO: W części środowisk uruchomieniowych (np. uruchomienie pliku po absolutnej ścieżce przez IDE)
#           pojedyncze dodanie `parent.parent` nie wystarczało i nadal pojawiał się `ModuleNotFoundError`
#           dla pakietu `robot_mission_control`.
# JAK TO DZIAŁA: Dla trybu skryptowego (`__package__` puste) kod sprawdza kilka katalogów nadrzędnych
#                i dodaje do `sys.path` pierwszy, który realnie zawiera pakiet `robot_mission_control`.
#                Jeżeli żaden kandydat nie pasuje, nic nie dopina (bezpieczny fallback bez fałszywych założeń).
# TODO: Dodać test uruchomieniowy CLI, który waliduje start zarówno przez `python app.py`, jak i `python -m`.
if __package__ in (None, ""):
    app_file = Path(__file__).resolve()
    path_candidates = (app_file.parent.parent, app_file.parent.parent.parent)
    for candidate in path_candidates:
        package_init_file = candidate / "robot_mission_control" / "__init__.py"
        if package_init_file.exists():
            candidate_str = str(candidate)
            if candidate_str not in sys.path:
                sys.path.insert(0, candidate_str)
            break

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from robot_mission_control.core import (
    STATE_KEY_BAG_INTEGRITY_STATUS,
    STATE_KEY_DATA_SOURCE_MODE,
    STATE_KEY_DEPENDENCY_STATUS,
    STATE_KEY_PLAYBACK_STATUS,
    STATE_KEY_RECORDING_STATUS,
    STATE_KEY_ROS_CONNECTION_STATUS,
    STATE_KEY_SELECTED_BAG,
    HealthMonitor,
    StateStore,
    Supervisor,
    WorkerModule,
    utc_now,
)
from robot_mission_control.ros.dependency_audit_client import DependencyStatusClient
from robot_mission_control.ros.node_manager import ReconnectPolicy, RosNodeManager
from robot_mission_control.ui.main_window import MainWindow
from robot_mission_control.rosbag.integrity_checker import IntegrityChecker
from robot_mission_control.rosbag.playback_controller import PlaybackController
from robot_mission_control.rosbag.record_controller import RecordController
from robot_mission_control.versioning import resolve_version_metadata

# [AI-CHANGE | 2026-04-21 03:58 UTC | v0.160]
# CO ZMIENIONO: RosBridgeService zintegrowano z RosNodeManager (init/shutdown/reconnect/heartbeat)
#               i publikacją statusu połączenia `ros_connection_status` do StateStore.
# DLACZEGO: DoD wymaga, by utrata i odzyskanie połączenia były widoczne w UI na podstawie danych ze store.
# JAK TO DZIAŁA: Serwis deleguje zarządzanie cyklem życia ROS do node managera i wykonuje polling, który
#                publikuje heartbeat, wykrywa stale heartbeat oraz uruchamia reconnect z bezpiecznym fallbackiem.
# TODO: Podmienić polling timer na sygnały z warstwy ROS (event-driven), gdy pojawi się stabilny adapter.


class _RclpyRuntime:
    """Adapter runtime rclpy zgodny z kontraktem RosRuntime."""

    def __init__(self, module: object) -> None:
        self._module = module

    def init(self) -> None:
        init_fn = getattr(self._module, "init", None)
        if not callable(init_fn):
            raise RuntimeError("rclpy_init_missing")
        init_fn()

    def shutdown(self) -> None:
        shutdown_fn = getattr(self._module, "shutdown", None)
        if not callable(shutdown_fn):
            raise RuntimeError("rclpy_shutdown_missing")
        shutdown_fn()


class RosBridgeService:
    """Minimal ROS2 bridge abstraction used by the desktop app."""

    def __init__(self, supervisor: Supervisor) -> None:
        self._supervisor = supervisor
        self._rclpy = None
        self._initialized = False
        self._state_store = StateStore()
        self._channel_name = "ros_bridge_channel"
        config_path = self._resolve_dependency_catalog_path()
        self._dependency_client = DependencyStatusClient(
            request_fn=self._request_dependency_status,
            dependencies_config_path=config_path,
        )
        self._integrity_checker = IntegrityChecker()
        self._playback_controller = PlaybackController(integrity_checker=self._integrity_checker)
        self._record_controller = RecordController()
        self._session_id = f"ros-bridge-{utc_now().strftime('%Y%m%d%H%M%S')}"
        self._node_manager: RosNodeManager | None = None

    def _resolve_dependency_catalog_path(self) -> Path:
        """Rozwiązuje położenie katalogu config dla obu ścieżek uruchamiania (moduł/pakiet)."""
        local_path = Path(__file__).resolve().parent / "config" / "dependency_catalog.yaml"
        if local_path.exists():
            return local_path
        return Path(__file__).resolve().parent.parent / "config" / "dependency_catalog.yaml"

    def init(self) -> None:
        """Prepare ROS bindings without crashing GUI boot."""
        if importlib.util.find_spec("rclpy") is None:
            self._initialized = False
            self._state_store.set_with_inference(
                key=STATE_KEY_DATA_SOURCE_MODE,
                value=None,
                source="ros_bridge",
                timestamp=utc_now(),
                reason_code="ros_unavailable",
            )
            self._state_store.set_with_inference(
                key=STATE_KEY_ROS_CONNECTION_STATUS,
                value=None,
                source="node_manager",
                timestamp=utc_now(),
                reason_code="ros_unavailable",
            )
            return

        rclpy_module = importlib.import_module("rclpy")
        self._rclpy = rclpy_module
        self._node_manager = RosNodeManager(
            runtime=_RclpyRuntime(rclpy_module),
            session_id=self._session_id,
            reconnect_policy=ReconnectPolicy(max_attempts=3, base_delay_seconds=0.5, max_delay_seconds=2.0),
            state_store=self._state_store,
        )
        self._initialized = self._node_manager.init_node(correlation_id="bridge_init")

    def start(self) -> None:
        """Start ROS worker and publish safe source status."""
        if not self._initialized or self._node_manager is None:
            self._state_store.set_with_inference(
                key=STATE_KEY_DATA_SOURCE_MODE,
                value=None,
                source="ros_bridge",
                timestamp=utc_now(),
                reason_code="ros_unavailable",
            )
            self._publish_rosbag_snapshot(reason_code="ros_unavailable")
            self._publish_dependency_report()
            return

        self._poll_connection()
        self._publish_rosbag_snapshot(reason_code="waiting_for_topics")
        self._publish_dependency_report()

    def stop(self) -> None:
        """Safely shutdown ROS2 if it was initialized."""
        if self._node_manager is not None:
            self._node_manager.shutdown_node(correlation_id="bridge_stop")

        self._state_store.set_with_inference(
            key=STATE_KEY_DATA_SOURCE_MODE,
            value=None,
            source="ros_bridge",
            timestamp=utc_now(),
            reason_code="app_shutdown",
        )
        self._publish_rosbag_snapshot(reason_code="app_shutdown")

    def _poll_connection(self) -> None:
        """Aktualizuje heartbeat i reconnect, publikując bezpieczny status połączenia."""
        if self._node_manager is None:
            self._state_store.set_with_inference(
                key=STATE_KEY_ROS_CONNECTION_STATUS,
                value=None,
                source="node_manager",
                timestamp=utc_now(),
                reason_code="node_manager_unavailable",
            )
            return

        now = utc_now()
        is_connected = self._node_manager.ensure_connected(correlation_id="bridge_poll_connect")
        if not is_connected:
            self._initialized = False
            self._state_store.set_with_inference(
                key=STATE_KEY_DATA_SOURCE_MODE,
                value=None,
                source="ros_bridge",
                timestamp=now,
                reason_code="reconnect_failed",
            )
            return

        self._initialized = True
        heartbeat = self._node_manager.heartbeat(correlation_id="bridge_poll_heartbeat")
        if heartbeat is None:
            self._initialized = False
            return

        if self._node_manager.is_heartbeat_stale(now=now, max_age=timedelta(seconds=5)):
            self._initialized = False
            return

        self._supervisor.heartbeat_channel(self._channel_name, heartbeat)

    def _request_dependency_status(self, payload: dict[str, object]) -> dict[str, object] | None:
        """Placeholder contract call returning conservative UNKNOWN when transport is unavailable."""
        dependencies = payload.get("dependencies")
        if not isinstance(dependencies, list):
            return None

        now_iso = utc_now().isoformat()
        return {
            "source": "system/dependency_status",
            "generated_at_utc": now_iso,
            "dependencies": [
                {
                    "name": str(item.get("name")),
                    "status": "UNKNOWN",
                    "detected_version": None,
                    "timestamp_utc": now_iso,
                    "source": "system/dependency_status",
                }
                for item in dependencies
                if isinstance(item, dict)
            ],
        }

    def _publish_rosbag_snapshot(self, *, reason_code: str | None = None) -> None:
        now = utc_now()
        playback_state = self._playback_controller.state
        selected_bag = playback_state.bag_path if playback_state.bag_path else None

        playback_status = "PLAYING" if playback_state.is_playing else "STOPPED"
        if playback_state.is_paused:
            playback_status = "PAUSED"

        bag_integrity = None
        if selected_bag:
            bag_integrity = self._integrity_checker.check(selected_bag).status

        self._state_store.set_with_inference(
            key=STATE_KEY_DATA_SOURCE_MODE,
            value=self._playback_controller.source_mode.value if self._initialized else None,
            source="ros_bridge",
            timestamp=now,
            reason_code=reason_code,
        )
        self._state_store.set_with_inference(
            key=STATE_KEY_RECORDING_STATUS,
            value=self._record_controller.status.value if self._initialized else None,
            source="ros_bridge",
            timestamp=now,
            reason_code=reason_code,
        )
        self._state_store.set_with_inference(
            key=STATE_KEY_PLAYBACK_STATUS,
            value=playback_status if self._initialized else None,
            source="ros_bridge",
            timestamp=now,
            reason_code=reason_code,
        )
        self._state_store.set_with_inference(
            key=STATE_KEY_SELECTED_BAG,
            value=selected_bag if self._initialized else None,
            source="ros_bridge",
            timestamp=now,
            reason_code=reason_code,
        )
        # Zasada bezpieczeństwa: przy niepewnej integralności publikujemy None zamiast ryzyka fałszywego "OK".
        self._state_store.set_with_inference(
            key=STATE_KEY_BAG_INTEGRITY_STATUS,
            value=bag_integrity if self._initialized else None,
            source="ros_bridge",
            timestamp=now,
            reason_code=reason_code if bag_integrity is None else None,
        )

    def _publish_dependency_report(self) -> None:
        report = self._dependency_client.fetch_report()
        # Zasada bezpieczeństwa: bez pełnego raportu wolimy brak danych niż potencjalnie fałszywe OK.
        self._state_store.set_with_inference(
            key=STATE_KEY_DEPENDENCY_STATUS,
            value=report if report.items else None,
            source=report.source,
            timestamp=report.generated_at_utc,
            reason_code="dependency_report_empty" if not report.items else None,
        )

    @property
    def state_store(self) -> StateStore:
        """Expose central state store for UI."""
        return self._state_store


def _install_global_excepthook(supervisor: Supervisor) -> None:
    """Install global boundary for unhandled UI/runtime exceptions."""

    def _hook(exc_type, exc, tb):  # noqa: ANN001
        _ = exc_type, tb
        supervisor.mark_panel_unavailable(panel_name="global_ui", exc=exc, now=utc_now())

    sys.excepthook = _hook


def main(argv: Optional[list[str]] = None) -> int:
    """Application entrypoint."""
    monitor = HealthMonitor(
        heartbeat_timeout=timedelta(seconds=10),
        base_backoff=timedelta(seconds=1),
        max_backoff=timedelta(seconds=20),
        breaker_threshold=3,
        breaker_cooldown=timedelta(seconds=30),
    )
    supervisor = Supervisor(health_monitor=monitor)
    _install_global_excepthook(supervisor)

    bridge = RosBridgeService(supervisor=supervisor)
    supervisor.register_channel("ros_bridge_channel")
    supervisor.register_worker(
        WorkerModule(
            name="ros_bridge",
            init_fn=bridge.init,
            start_fn=bridge.start,
            stop_fn=bridge.stop,
        )
    )

    now = utc_now()
    supervisor.init_worker("ros_bridge", now)
    supervisor.start_worker("ros_bridge", now)

    qt_app = QApplication(argv or sys.argv)
    window = MainWindow(
        state_store=bridge.state_store,
        supervisor=supervisor,
        version_metadata=resolve_version_metadata(),
    )
    window.show()
    # [AI-CHANGE | 2026-04-21 03:58 UTC | v0.160]
    # CO ZMIENIONO: Dodano cykliczny polling połączenia ROS w pętli UI (QTimer co 1 s).
    # DLACZEGO: Utrata i odzyskanie połączenia mają być widoczne w runtime, nie tylko przy starcie aplikacji.
    # JAK TO DZIAŁA: Timer uruchamia `_poll_connection` i odświeża snapshot rosbag; przy utracie połączenia
    #                store dostaje wartości bezpieczne (`None`), a po reconnect wraca status `CONNECTED`.
    # TODO: Dodać adaptacyjny interwał timera zależny od stanu (krótszy podczas reconnect, dłuższy gdy stabilnie).
    poll_timer = QTimer()
    poll_timer.setInterval(1000)

    def _tick() -> None:
        bridge._poll_connection()
        reason = None if bridge._initialized else "ros_unavailable"
        bridge._publish_rosbag_snapshot(reason_code=reason)

    poll_timer.timeout.connect(_tick)
    poll_timer.start()

    exit_code = qt_app.exec()
    supervisor.stop_worker("ros_bridge", utc_now())
    return int(exit_code)


if __name__ == "__main__":
    raise SystemExit(main())
