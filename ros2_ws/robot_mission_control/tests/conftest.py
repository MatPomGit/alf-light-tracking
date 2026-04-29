"""Konfiguracja pytest dla pakietu robot_mission_control."""

from __future__ import annotations

import sys
import shutil
import uuid
from pathlib import Path

import pytest

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


# [AI-CHANGE | 2026-04-29 13:15 UTC | v0.332]
# CO ZMIENIONO: Dodano lokalny fixture `tmp_path`, który nie korzysta z globalnego katalogu tymczasowego Pytest.
# DLACZEGO: Na Windows katalog `pytest-of-<user>` może mieć uszkodzone lub zablokowane ACL, co powoduje błąd
#           `PermissionError` zanim test zdąży wykonać właściwą asercję.
# JAK TO DZIAŁA: Fixture tworzy unikalny katalog pod `robot_mission_control/.pytest_tmp`, przekazuje go testowi,
#                a po teście usuwa katalog; gdy cleanup się nie powiedzie, `.gitignore` nadal ukrywa artefakt.
# TODO: Po ustabilizowaniu środowiska CI rozważyć powrót do wbudowanego `tmp_path_factory` z jawnie ustawionym `--basetemp`.
@pytest.fixture
def tmp_path(request: pytest.FixtureRequest) -> Path:
    safe_name = "".join(char if char.isalnum() or char in {"_", "-"} else "_" for char in request.node.name)
    temp_root = Path(__file__).resolve().parents[1] / ".pytest_tmp"
    temp_path = temp_root / f"{safe_name}-{uuid.uuid4().hex}"
    temp_path.mkdir(parents=True, exist_ok=False)
    try:
        yield temp_path
    finally:
        shutil.rmtree(temp_path, ignore_errors=True)
