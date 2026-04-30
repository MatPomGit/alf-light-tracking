from __future__ import annotations

import pytest

qt_widgets = pytest.importorskip("PySide6.QtWidgets", reason="Brak bibliotek systemowych Qt (np. libGL) w środowisku testowym.")
QApplication = qt_widgets.QApplication

from robot_mission_control.core import DataQuality
from robot_mission_control.ui.tabs.map_tab import MapTab


# [AI-CHANGE | 2026-04-30 10:28 UTC | v0.201]
# CO ZMIENIONO: Dodano minimalne testy importu i inicjalizacji nowej zakładki `MapTab`.
# DLACZEGO: Potrzebna jest szybka regresja potwierdzająca bezpieczny stan startowy (`BRAK DANYCH`)
#           i jawne statusy jakości bez domyślnego wyświetlania pozycji.
# JAK TO DZIAŁA: Testy uruchamiają kartę w headless Qt i asertywnie sprawdzają etykiety startowe
#                oraz zachowanie metody `set_map_status` dla jakości VALID/STALE.
# TODO: Dodać testy integracyjne z MainWindow, które potwierdzą aktualizację mapy ze StateStore.
def _ensure_qapplication() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_map_tab_initializes_with_safe_defaults() -> None:
    _ensure_qapplication()

    tab = MapTab()

    assert tab._position_label.text() == "Pozycja: BRAK DANYCH"
    assert tab._quality_label.text() == "Jakość danych mapy: UNAVAILABLE"


def test_map_tab_set_map_status_respects_quality_gate() -> None:
    _ensure_qapplication()

    tab = MapTab()
    tab.set_map_status(DataQuality.VALID, position_text="X=1.0 Y=2.0")
    assert tab._position_label.text() == "Pozycja: X=1.0 Y=2.0"

    tab.set_map_status(DataQuality.STALE, position_text="X=9.9 Y=9.9")
    assert tab._position_label.text() == "Pozycja: BRAK DANYCH"
    assert tab._quality_label.text() == "Jakość danych mapy: STALE"
