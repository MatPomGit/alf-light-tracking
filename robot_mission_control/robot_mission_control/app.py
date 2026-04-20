"""Main entrypoint for robot mission control desktop app."""

from __future__ import annotations

import sys
from typing import Optional

from PySide6.QtWidgets import QApplication

from robot_mission_control.core import (
    STATE_KEY_DATA_SOURCE_MODE,
    StateStore,
    utc_now,
)
from robot_mission_control.ui.main_window import MainWindow

# [AI-CHANGE | 2026-04-20 18:27 UTC | v0.143]
# CO ZMIENIONO: Zastąpiono prosty RuntimeState centralnym StateStore i podłączono go do bridge ROS.
# DLACZEGO: Wymuszamy zasadę, że UI czyta stan wyłącznie ze store, bez bezpośredniego podawania surowych
#           wartości z ROS do widżetów.
# JAK TO DZIAŁA: RosBridgeService inicjalizuje StateStore i publikuje w nim status źródła danych.
#                Przy braku pewności ustawiana jest jakość UNAVAILABLE/ERROR zamiast domyślnych liczb.
# TODO: Dodać mapowanie realnych topiców ROS na klucze store z walidacją timestamp/source per wiadomość.


class RosBridgeService:
    """Minimal ROS2 bridge abstraction used by the desktop app."""

    def __init__(self) -> None:
        self._rclpy = None
        self._initialized = False
        self._state_store = StateStore()

    def start(self) -> StateStore:
        """Try to initialize ROS2, but never fail the GUI startup."""
        try:
            import rclpy  # type: ignore

            self._rclpy = rclpy
            # W tej wersji nie łączymy się z robotem aktywnie; publikujemy bezpieczny status źródła.
            self._initialized = True
            self._state_store.set_with_inference(
                key=STATE_KEY_DATA_SOURCE_MODE,
                value="ROS_DISCONNECTED",
                source="ros_bridge",
                timestamp=utc_now(),
                reason_code="waiting_for_topics",
            )
        except Exception:
            # Zgodnie z zasadą jakości: lepiej brak danych niż potencjalnie błędna interpretacja stanu.
            self._initialized = False
            self._state_store.set_with_inference(
                key=STATE_KEY_DATA_SOURCE_MODE,
                value=None,
                source="ros_bridge",
                timestamp=utc_now(),
                reason_code="ros_unavailable",
            )

        return self._state_store

    def stop(self) -> None:
        """Safely shutdown ROS2 if it was initialized."""
        if self._initialized and self._rclpy is not None:
            try:
                self._rclpy.shutdown()
            except Exception:
                # Wygaszanie nie może wywołać awarii zamykania aplikacji.
                pass

        self._state_store.set_with_inference(
            key=STATE_KEY_DATA_SOURCE_MODE,
            value=None,
            source="ros_bridge",
            timestamp=utc_now(),
            reason_code="app_shutdown",
        )


def main(argv: Optional[list[str]] = None) -> int:
    """Application entrypoint."""
    bridge = RosBridgeService()
    state_store = bridge.start()

    qt_app = QApplication(argv or sys.argv)
    window = MainWindow(state_store=state_store)
    window.show()

    exit_code = qt_app.exec()
    bridge.stop()
    return int(exit_code)


if __name__ == "__main__":
    raise SystemExit(main())
