"""Module launcher for `python -m robot_mission_control`."""

from __future__ import annotations

# [AI-CHANGE | 2026-04-20 21:55 UTC | v0.157]
# CO ZMIENIONO: Dodano uruchamianie modułowe `python -m robot_mission_control`.
# DLACZEGO: Ułatwia lokalny smoke-test aplikacji bez instalowania entrypointu w systemie.
# JAK TO DZIAŁA: Moduł deleguje wykonanie do `app.entrypoint.main` i zwraca kod zakończenia procesu.
# TODO: Dodać parametry CLI `--offline` i `--headless` do testów automatycznych.

from robot_mission_control.app.entrypoint import main


if __name__ == "__main__":
    raise SystemExit(main())
