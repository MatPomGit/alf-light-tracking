"""Konfiguracja pytest dla pakietu robot_mission_control."""

from __future__ import annotations

import sys
from pathlib import Path

# [AI-CHANGE | 2026-04-29 00:00 UTC | v0.207]
# CO ZMIENIONO: Dodano bezpieczne dołączanie katalogu źródeł pakietu do `sys.path` na etapie kolekcji testów.
# DLACZEGO: W środowisku CI testy były kolekcjonowane bez instalacji editable pakietu, co kończyło się błędem
#           `ModuleNotFoundError: No module named 'robot_mission_control'` i zatrzymaniem całego etapu testowego.
# JAK TO DZIAŁA: Pytest importuje `conftest.py` przed kolekcją modułów testowych; funkcja poniżej dodaje do
#                `sys.path` katalog zawierający pakiet tylko wtedy, gdy nie jest już widoczny, dzięki czemu importy
#                w testach działają deterministycznie również bez aktywnego `install/setup.bash`.
# TODO: Rozważyć zastąpienie modyfikacji `sys.path` pełnym uruchamianiem testów przez `colcon test` w izolowanym venv.
def _ensure_package_import_path() -> None:
    package_root = Path(__file__).resolve().parents[1]
    if str(package_root) not in sys.path:
        sys.path.insert(0, str(package_root))


_ensure_package_import_path()
