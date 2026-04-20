"""Application package for Robot Mission Control."""

# [AI-CHANGE | 2026-04-20 21:55 UTC | v0.157]
# CO ZMIENIONO: Pakiet `app` eksportuje funkcję `main` z modułu bootstrap.
# DLACZEGO: Po utworzeniu katalogu `app/` import `robot_mission_control.app` wskazuje pakiet, więc wymagany jest jawny eksport.
# JAK TO DZIAŁA: `from robot_mission_control.app import main` działa poprawnie i uruchamia aplikację desktopową.
# TODO: Rozdzielić bootstrap na warstwy (DI, konfiguracja, start UI) dla łatwiejszych testów jednostkowych.

from robot_mission_control.app.bootstrap import main

__all__ = ["main"]
