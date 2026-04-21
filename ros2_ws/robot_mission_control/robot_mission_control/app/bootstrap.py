"""Main entrypoint for robot mission control desktop app."""

from __future__ import annotations

import importlib
import json
import importlib.util
import sys

import yaml
from datetime import timedelta
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from robot_mission_control.core import (
    STATE_KEY_ACTION_GOAL_ID,
    STATE_KEY_ACTION_PROGRESS,
    STATE_KEY_ACTION_RESULT,
    STATE_KEY_ACTION_STATUS,
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
from robot_mission_control.ros.action_backend import ActionBackendConfig, Ros2MissionActionBackend
from robot_mission_control.ros.action_clients import ActionClientBindings, MissionActionClient
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


# [AI-CHANGE | 2026-04-21 10:35 UTC | v0.169]
# CO ZMIENIONO: Zastąpiono lokalny transport unavailable pełnym backendem ROS2 Action
#               z dynamicznym ładowaniem typu akcji i bezpiecznym fallbackiem.
# DLACZEGO: Moduł operatorski ma korzystać z realnego backendu Action, a nie z warstwy bez transportu.
# JAK TO DZIAŁA: `Ros2MissionActionBackend` obsługuje send/progress/result/cancel przez rclpy ActionClient;
#                gdy kontrakt lub serwer są niedostępne, metody zwracają None/False (UNAVAILABLE).
# TODO: Dodać walidację payloadu goal względem jawnego schematu kontraktu Action.


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
        self._action_backend: Ros2MissionActionBackend | None = None
        self._action_client = MissionActionClient(
            session_id=self._session_id,
            bindings=ActionClientBindings(
                send_goal=self._send_action_goal,
                cancel_goal=self._cancel_action_goal_transport,
                fetch_result=self._fetch_action_result,
                fetch_progress=self._fetch_action_progress,
            ),
        )
        self._active_goal_id: str | None = None

    def _resolve_dependency_catalog_path(self) -> Path:
        """Rozwiązuje położenie katalogu config dla obu ścieżek uruchamiania (moduł/pakiet)."""
        local_path = Path(__file__).resolve().parent / "config" / "dependency_catalog.yaml"
        if local_path.exists():
            return local_path
        return Path(__file__).resolve().parent.parent / "config" / "dependency_catalog.yaml"

    # [AI-CHANGE | 2026-04-21 10:35 UTC | v0.169]
    # CO ZMIENIONO: Dodano odczyt jawnej konfiguracji backendu Action z pliku YAML.
    # DLACZEGO: Typ i endpoint akcji nie mogą być ukryte w kodzie; muszą być konfigurowalne pod środowisko robota.
    # JAK TO DZIAŁA: Bridge rozwiązuje ścieżkę pliku, waliduje wymagane pola i tworzy `ActionBackendConfig`.
    # TODO: Dodać formalną walidację typów/liczb dodatnich przez dedykowany schemat (np. pydantic/cerberus).
    def _resolve_action_backend_config_path(self) -> Path:
        """Rozwiązuje położenie pliku konfiguracyjnego backendu Action."""
        local_path = Path(__file__).resolve().parent / "config" / "action_backend.yaml"
        if local_path.exists():
            return local_path
        return Path(__file__).resolve().parent.parent / "config" / "action_backend.yaml"

    def _load_action_backend_config(self) -> ActionBackendConfig | None:
        """Wczytuje konfigurację Action; przy błędzie zwraca None (bezpieczny fallback)."""
        config_path = self._resolve_action_backend_config_path()
        if not config_path.exists():
            return None

        try:
            raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            return None

        if not isinstance(raw, dict):
            return None

        required = [
            "action_name",
            "action_type_module",
            "action_type_name",
            "node_name",
            "server_wait_timeout_sec",
            "future_wait_timeout_sec",
        ]
        if any(key not in raw for key in required):
            return None

        try:
            return ActionBackendConfig(
                action_name=str(raw["action_name"]),
                action_type_module=str(raw["action_type_module"]),
                action_type_name=str(raw["action_type_name"]),
                node_name=str(raw["node_name"]),
                server_wait_timeout_sec=float(raw["server_wait_timeout_sec"]),
                future_wait_timeout_sec=float(raw["future_wait_timeout_sec"]),
            )
        except Exception:  # noqa: BLE001
            return None

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
        if not self._initialized:
            return

        action_config = self._load_action_backend_config()
        if action_config is None:
            self._action_backend = None
            return

        self._action_backend = Ros2MissionActionBackend(
            rclpy_module=rclpy_module,
            config=action_config,
        )
        if not self._action_backend.start():
            self._action_backend = None

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
        if self._action_backend is not None:
            self._action_backend.shutdown()
            self._action_backend = None

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

    def _send_action_goal(self, goal_payload: dict[str, object]) -> str | None:
        """Deleguje wysyłkę goal do backendu Action; brak backendu => None."""
        if self._action_backend is None:
            return None
        return self._action_backend.send_goal(goal_payload)

    def _cancel_action_goal_transport(self, goal_id: str) -> bool:
        """Deleguje cancel goal do backendu Action; brak backendu => False."""
        if self._action_backend is None:
            return False
        return self._action_backend.cancel_goal(goal_id)

    def _fetch_action_result(self, goal_id: str) -> dict[str, object] | None:
        """Deleguje pobranie result do backendu Action; brak backendu => None."""
        if self._action_backend is None:
            return None
        return self._action_backend.fetch_result(goal_id)

    def _fetch_action_progress(self, goal_id: str) -> float | None:
        """Deleguje pobranie feedback progress do backendu Action; brak backendu => None."""
        if self._action_backend is None:
            return None
        return self._action_backend.fetch_progress(goal_id)

    def submit_action_goal(self) -> None:
        """Wysyła goal akcji i publikuje stan początkowy do store."""
        now = utc_now()
        if self._active_goal_id is not None:
            return

        goal_id = self._action_client.send_goal(
            goal_payload={"goal": "operator_mission_step"},
            correlation_id=f"action_send_{now.strftime('%H%M%S')}"
        )
        if goal_id is None:
            self._state_store.set_with_inference(
                key=STATE_KEY_ACTION_STATUS,
                value=None,
                source="action_client",
                timestamp=now,
                reason_code="action_backend_unavailable",
            )
            return

        self._active_goal_id = goal_id
        self._state_store.set_with_inference(key=STATE_KEY_ACTION_GOAL_ID, value=goal_id, source="action_client", timestamp=now)
        self._state_store.set_with_inference(key=STATE_KEY_ACTION_STATUS, value="RUNNING", source="action_client", timestamp=now)
        self._state_store.set_with_inference(key=STATE_KEY_ACTION_PROGRESS, value="0%", source="action_client", timestamp=now)
        self._state_store.set_with_inference(
            key=STATE_KEY_ACTION_RESULT,
            value="OCZEKIWANIE NA WYNIK",
            source="action_client",
            timestamp=now,
        )

    def cancel_action_goal(self) -> None:
        """Anuluje aktywny goal i publikuje status anulowania."""
        now = utc_now()
        if self._active_goal_id is None:
            self._state_store.set_with_inference(
                key=STATE_KEY_ACTION_STATUS,
                value=None,
                source="action_client",
                timestamp=now,
                reason_code="no_active_goal",
            )
            return

        is_cancelled = self._action_client.cancel_goal(
            goal_id=self._active_goal_id,
            correlation_id=f"action_cancel_{now.strftime('%H%M%S')}",
        )
        self._state_store.set_with_inference(
            key=STATE_KEY_ACTION_STATUS,
            value="CANCEL_REQUESTED" if is_cancelled else None,
            source="action_client",
            timestamp=now,
            reason_code=None if is_cancelled else "cancel_failed",
        )

    def poll_action_status(self) -> None:
        """Polluje progress i wynik aktywnego goala, stosując bezpieczne fallbacki."""
        now = utc_now()
        if self._active_goal_id is None:
            return

        goal_id = self._active_goal_id
        progress = self._action_client.get_progress(
            goal_id=goal_id,
            correlation_id=f"action_progress_{now.strftime('%H%M%S')}",
        )
        if progress is not None:
            progress_label = f"{int(progress * 100)}%"
            self._state_store.set_with_inference(
                key=STATE_KEY_ACTION_PROGRESS,
                value=progress_label,
                source="action_client",
                timestamp=now,
            )

        result = self._action_client.get_result(
            goal_id=goal_id,
            correlation_id=f"action_result_{now.strftime('%H%M%S')}",
        )
        if result is None:
            return

        status = str(result.get("status", "UNKNOWN"))
        self._state_store.set_with_inference(key=STATE_KEY_ACTION_STATUS, value=status, source="action_client", timestamp=now)
        self._state_store.set_with_inference(
            key=STATE_KEY_ACTION_RESULT,
            value=json.dumps(result, ensure_ascii=False),
            source="action_client",
            timestamp=now,
        )
        self._state_store.set_with_inference(
            key=STATE_KEY_ACTION_GOAL_ID,
            value=None,
            source="action_client",
            timestamp=now,
            reason_code="goal_finished",
        )
        self._active_goal_id = None

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
        submit_action_goal=bridge.submit_action_goal,
        cancel_action_goal=bridge.cancel_action_goal,
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
        bridge.poll_action_status()

    poll_timer.timeout.connect(_tick)
    poll_timer.start()

    exit_code = qt_app.exec()
    supervisor.stop_worker("ros_bridge", utc_now())
    return int(exit_code)


if __name__ == "__main__":
    raise SystemExit(main())
