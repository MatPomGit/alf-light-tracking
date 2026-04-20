"""Main entrypoint for robot mission control desktop app."""

from __future__ import annotations

import importlib
import importlib.util
import sys
from datetime import timedelta
from typing import Optional

from PySide6.QtWidgets import QApplication

from robot_mission_control.core import (
    STATE_KEY_DATA_SOURCE_MODE,
    HealthMonitor,
    StateStore,
    Supervisor,
    WorkerModule,
    utc_now,
)
from robot_mission_control.ui.main_window import MainWindow

# [AI-CHANGE | 2026-04-20 19:12 UTC | v0.145]
# CO ZMIENIONO: Dodano integrację Supervisor+HealthMonitor z globalnym error boundary i lifecycle workera ROS.
# DLACZEGO: Aplikacja musi izolować awarie modułów, prowadzić heartbeat/incydenty oraz mapować wyjątki UI.
# JAK TO DZIAŁA: RosBridgeService ma jawne kroki init/start/stop; Supervisor wywołuje je przez WorkerModule,
#                a globalny excepthook rejestruje incydent zamiast zatrzymywać całą aplikację.
# TODO: Rozszerzyć obsługę `sys.excepthook` o raportowanie stacktrace do pliku diagnostycznego per sesja.


class RosBridgeService:
    """Minimal ROS2 bridge abstraction used by the desktop app."""

    def __init__(self, supervisor: Supervisor) -> None:
        self._supervisor = supervisor
        self._rclpy = None
        self._initialized = False
        self._state_store = StateStore()
        self._channel_name = "ros_bridge_channel"

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
            return

        self._state_store.set_with_inference(
            key=STATE_KEY_DATA_SOURCE_MODE,
            value="ROS_DISCONNECTED",
            source="ros_bridge",
            timestamp=utc_now(),
            reason_code="waiting_for_topics",
        )
        self._supervisor.heartbeat_channel(self._channel_name, utc_now())

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
    window = MainWindow(state_store=bridge.state_store, supervisor=supervisor)
    window.show()

    exit_code = qt_app.exec()
    supervisor.stop_worker("ros_bridge", utc_now())
    return int(exit_code)


if __name__ == "__main__":
    raise SystemExit(main())
