"""TelemetryTab placeholder."""

from __future__ import annotations

from robot_mission_control.ui.tabs._placeholder import UnavailableTab

# [AI-CHANGE | 2026-04-20 14:12 UTC | v0.141]
# CO ZMIENIONO: Dodano szkielet zakładki TelemetryTab jako jawnie niedostępny komponent UI.
# DLACZEGO: Wymagany jest komplet zakładek, ale funkcjonalność jest poza zakresem tej iteracji.
# JAK TO DZIAŁA: Zakładka dziedziczy po wspólnym placeholderze i renderuje stan BRAK DANYCH + komunikat niedostępności.
# TODO: Zaimplementować logikę danych i akcje operatora dla zakładki TelemetryTab.


class TelemetryTab(UnavailableTab):
    """Temporary tab with explicit unavailable status."""

    def __init__(self, parent=None) -> None:
        super().__init__(tab_name="TelemetryTab", parent=parent)
