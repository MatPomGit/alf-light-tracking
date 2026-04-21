"""Main entrypoint for robot mission control desktop app."""

from __future__ import annotations

import importlib
import importlib.util
import sys
from datetime import timedelta
from pathlib import Path
from typing import Optional

from PySide6.QtWidgets import QApplication

from robot_mission_control.core import (
    STATE_KEY_BAG_INTEGRITY_STATUS,
    STATE_KEY_DATA_SOURCE_MODE,
    STATE_KEY_DEPENDENCY_STATUS,
    STATE_KEY_PLAYBACK_STATUS,
    STATE_KEY_RECORDING_STATUS,
    STATE_KEY_SELECTED_BAG,
    HealthMonitor,
    StateStore,
    Supervisor,
    WorkerModule,
    utc_now,
)
from robot_mission_control.ros.dependency_audit_client import DependencyStatusClient
from robot_mission_control.ui.main_window import MainWindow
from robot_mission_control.rosbag.integrity_checker import IntegrityChecker
from robot_mission_control.rosbag.playback_controller import PlaybackController
from robot_mission_control.rosbag.record_controller import RecordController
from robot_mission_control.versioning import resolve_version_metadata

# [AI-CHANGE | 2026-04-20 22:05 UTC | v0.158]
# CO ZMIENIONO: Rozszerzono RosBridgeService o publikowanie wszystkich globalnych pól rosbag/source
#               (`data_source_mode`, `recording_status`, `playback_status`, `selected_bag`, `bag_integrity_status`)
#               wyłącznie do StateStore oraz utrzymano publikację `dependency_status`.
# DLACZEGO: UI ma czytać stan tylko ze store; warstwa ROS nie może wykonywać bezpośrednich aktualizacji widgetów.
# JAK TO DZIAŁA: RosBridgeService utrzymuje kontrolery playback/recording, wylicza bezpieczny snapshot
#                i zapisuje go przez `set_with_inference`; gdy integralność lub dane są niepewne, publikuje `None`.
# TODO: Dodać cykliczny polling runtime ROS, aby odświeżać statusy rosbag także po zdarzeniach asynchronicznych.


class RosBridgeService:
    """Minimal ROS2 bridge abstraction used by the desktop app."""

    def __init__(self, supervisor: Supervisor) -> None:
        self._supervisor = supervisor
        self._rclpy = None
        self._initialized = False
        self._state_store = StateStore()
        self._channel_name = "ros_bridge_channel"
        config_path = Path(__file__).resolve().parent / "config" / "dependency_catalog.yaml"
        self._dependency_client = DependencyStatusClient(
            request_fn=self._request_dependency_status,
            dependencies_config_path=config_path,
        )
        self._integrity_checker = IntegrityChecker()
        self._playback_controller = PlaybackController(integrity_checker=self._integrity_checker)
        self._record_controller = RecordController()

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
            return

        rclpy_module = importlib.import_module("rclpy")
        self._rclpy = rclpy_module
        self._initialized = True

    def start(self) -> None:
        """Start ROS worker and publish safe source status."""
        if not self._initialized:
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

        self._publish_rosbag_snapshot(reason_code="waiting_for_topics")
        self._supervisor.heartbeat_channel(self._channel_name, utc_now())
        self._publish_dependency_report()

    def stop(self) -> None:
        """Safely shutdown ROS2 if it was initialized."""
        if self._initialized and self._rclpy is not None:
            shutdown_fn = getattr(self._rclpy, "shutdown", None)
            if callable(shutdown_fn):
                shutdown_fn()

        self._state_store.set_with_inference(
            key=STATE_KEY_DATA_SOURCE_MODE,
            value=None,
            source="ros_bridge",
            timestamp=utc_now(),
            reason_code="app_shutdown",
        )
        self._publish_rosbag_snapshot(reason_code="app_shutdown")

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
    # [AI-CHANGE | 2026-04-20 23:02 UTC | v0.159]
    # CO ZMIENIONO: Globalny excepthook deleguje obsługę do `handle_global_exception`
    #               oraz oznacza panel globalny jako niedostępny.
    # DLACZEGO: Zapewniamy spójne mapowanie wyjątków na kody błędu i izolację skutków awarii.
    # JAK TO DZIAŁA: Wyjątek trafia do jednej granicy błędów; incydent jest logowany, a aplikacja może działać dalej.
    # TODO: Dodać raportowanie traceback do diagnostyki serwisowej (np. plik rotowany).

    def _hook(exc_type, exc, tb):  # noqa: ANN001
        _ = exc_type, tb
        now = utc_now()
        supervisor.handle_global_exception(exc=exc, now=now)
        supervisor.mark_panel_unavailable(panel_name="global_ui", exc=exc, now=now)

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

    exit_code = qt_app.exec()
    supervisor.stop_worker("ros_bridge", utc_now())
    return int(exit_code)


if __name__ == "__main__":
    raise SystemExit(main())
