"""Wrapper uruchamiający narzędzie kalibracji percepcji z lokalizacji repozytorium."""

from __future__ import annotations

import runpy
from pathlib import Path


# [AI-CHANGE | 2026-04-17 13:32 UTC | v0.109]
# CO ZMIENIONO: Dodano cienki adapter `main()` mapujący entry point pakietu na istniejący skrypt
# kalibracyjny umieszczony w katalogu `ros2_ws/g1_light_tracking/tools`.
# DLACZEGO: `setup.py` eksportuje narzędzia przez ścieżki modułów pakietu `g1_light_tracking.*`;
# bez adaptera nowy wpis console_scripts wskazywałby nieistniejący moduł.
# JAK TO DZIAŁA: Funkcja `main()` lokalizuje oryginalny plik skryptu, wykonuje go przez `runpy.run_path`
# i wywołuje jego funkcję `main`, dzięki czemu zachowane jest dotychczasowe zachowanie CLI.
# TODO: Przenieść pełną implementację kalibratora do `g1_light_tracking/tools/` i utrzymać
# kompatybilność przez alias w starej lokalizacji.
def main() -> int:
    script_path = Path(__file__).resolve().parents[2] / 'tools' / 'calibrate_perception.py'
    namespace = runpy.run_path(str(script_path), run_name='g1_light_tracking.tools.calibrate_perception_script')
    return int(namespace['main']())
