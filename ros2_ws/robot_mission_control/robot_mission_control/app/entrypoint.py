"""Primary entrypoint module for Robot Mission Control."""

from __future__ import annotations

# [AI-CHANGE | 2026-04-20 21:55 UTC | v0.157]
# CO ZMIENIONO: Dodano nowy entrypoint w strukturze `app/`, delegujący uruchomienie do istniejącego bootstrapu.
# DLACZEGO: Ujednolicamy ścieżkę uruchamiania zgodnie z wymaganiem struktury projektu i minimalizujemy ryzyko regresji.
# JAK TO DZIAŁA: Funkcja `main` przekazuje argumenty do `robot_mission_control.app.main`, dzięki czemu GUI działa jak wcześniej.
# TODO: Przenieść pełny bootstrap z `robot_mission_control/app.py` do tego modułu i zostawić zgodny alias wsteczny.

from robot_mission_control.app import main as _legacy_main


def main(argv: list[str] | None = None) -> int:
    """Run desktop application with backward-compatible startup path."""
    return _legacy_main(argv)


if __name__ == "__main__":
    raise SystemExit(main())
