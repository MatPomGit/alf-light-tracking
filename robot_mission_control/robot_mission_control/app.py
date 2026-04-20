"""Main entrypoint for robot mission control desktop app."""

from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import Optional

from PySide6.QtWidgets import QApplication

from robot_mission_control.ui.main_window import MainWindow

# [AI-CHANGE | 2026-04-20 14:12 UTC | v0.141]
# CO ZMIENIONO: Dodano lekki most aplikacji do ROS2 z bezpiecznym fallbackiem, gdy rclpy jest niedostępne.
# DLACZEGO: Aplikacja ma uruchamiać się bez robota i bez wymuszania aktywnego środowiska ROS2.
# JAK TO DZIAŁA: Klasa RosBridgeService próbuje opcjonalnie zainicjalizować rclpy; przy błędzie utrzymuje stan
#                BRAK DOSTĘPU/BRAK DANYCH i nie blokuje startu GUI.
# TODO: Dodać asynchroniczne subskrypcje ROS2 i mapowanie topiców na modele danych UI.


@dataclass(slots=True)
class RuntimeState:
    """Runtime status visible in UI from the first frame."""

    connection_status: str = "BRAK DOSTĘPU"
    data_status: str = "BRAK DANYCH"


class RosBridgeService:
    """Minimal ROS2 bridge abstraction used by the desktop app."""

    def __init__(self) -> None:
        self._rclpy = None
        self._initialized = False

    def start(self) -> RuntimeState:
        """Try to initialize ROS2, but never fail the GUI startup."""
        try:
            import rclpy  # type: ignore

            self._rclpy = rclpy
            # W tej wersji nie łączymy się z robotem aktywnie, zostawiamy bezpieczny stan początkowy.
            self._initialized = True
        except Exception:
            # Zgodnie z zasadą jakości: lepiej brak danych niż potencjalnie błędna interpretacja stanu.
            self._initialized = False

        return RuntimeState()

    def stop(self) -> None:
        """Safely shutdown ROS2 if it was initialized."""
        if self._initialized and self._rclpy is not None:
            try:
                self._rclpy.shutdown()
            except Exception:
                # Wygaszanie nie może wywołać awarii zamykania aplikacji.
                pass


def main(argv: Optional[list[str]] = None) -> int:
    """Application entrypoint."""
    bridge = RosBridgeService()
    runtime_state = bridge.start()

    qt_app = QApplication(argv or sys.argv)
    window = MainWindow(runtime_state=runtime_state)
    window.show()

    exit_code = qt_app.exec()
    bridge.stop()
    return int(exit_code)


if __name__ == "__main__":
    raise SystemExit(main())
