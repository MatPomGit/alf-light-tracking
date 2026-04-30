from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

qt_widgets = pytest.importorskip("PySide6.QtWidgets", reason="Brak bibliotek systemowych Qt (np. libGL) w środowisku testowym.")
QApplication = qt_widgets.QApplication

from robot_mission_control.core import DataQuality
from robot_mission_control.ui.tabs.map_tab import MapSample, MapTab


# [AI-CHANGE | 2026-04-30 12:10 UTC | v0.201]
# CO ZMIENIONO: Rozbudowano testy `MapTab` o przypadki brzegowe walidacji próbek mapy:
#               brak TF, przeterminowany timestamp, niespójny frame_id, brak połączenia ROS
#               oraz kontrolę, że przy degradacji nie utrzymujemy historycznej pozycji jako bieżącej.
# DLACZEGO: Te scenariusze są krytyczne dla bezpieczeństwa operatorskiego i muszą gwarantować,
#           że UI preferuje `BRAK DANYCH` zamiast ryzykownej prezentacji pozycji.
# JAK TO DZIAŁA: Testy budują próbki `MapSample`, uruchamiają `set_map_sample` i sprawdzają etykiety
#                jakości/pozycji/trajektorii oraz reason_code wynikający z walidacji.
# TODO: Dodać test integracyjny z rzeczywistym feedem `tf2` i symulacją utraty pojedynczych ramek.
def _ensure_qapplication() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def _sample(*, ts: datetime, frame: str = "map", source: str = "odom") -> MapSample:
    return MapSample(
        timestamp=ts,
        frame_id=frame,
        position_text="X=1.0 Y=2.0",
        trajectory_text="(0,0)->(1,2)",
        source=source,
    )


def test_map_tab_initializes_with_safe_defaults() -> None:
    _ensure_qapplication()

    tab = MapTab()

    assert tab._position_label.text() == "Pozycja: BRAK DANYCH"
    assert tab._trajectory_label.text() == "Trajektoria: BRAK DANYCH"
    assert "historyczne" in tab._historical_label.text()
    assert "UNAVAILABLE" in tab._quality_label.text()
    assert tab._availability_label.text() == "Status panelu: OCZEKIWANIE NA DANE"


def test_map_tab_renders_position_only_for_valid_quality() -> None:
    _ensure_qapplication()
    now = datetime.now(timezone.utc)
    tab = MapTab()

    tab.set_map_sample(sample=_sample(ts=now), quality=DataQuality.VALID, ros_connected=True, tf_available=True, now_utc=now)
    assert tab._position_label.text() == "Pozycja: X=1.0 Y=2.0"
    assert tab._trajectory_label.text() == "Trajektoria: (0,0)->(1,2)"

    tab.set_map_sample(sample=_sample(ts=now), quality=DataQuality.STALE, ros_connected=True, tf_available=True, now_utc=now)
    assert tab._position_label.text() == "Pozycja: BRAK DANYCH"
    assert tab._trajectory_label.text() == "Trajektoria: BRAK DANYCH"
    assert "degraded_input_quality:STALE" in tab._quality_label.text()


def test_map_tab_handles_missing_tf() -> None:
    _ensure_qapplication()
    now = datetime.now(timezone.utc)
    tab = MapTab()

    tab.set_map_sample(sample=_sample(ts=now), quality=DataQuality.VALID, ros_connected=True, tf_available=False, now_utc=now)

    assert "MAP_TF_MISSING" in tab._quality_label.text()
    assert tab._position_label.text().endswith("BRAK DANYCH")
    assert "Co się stało:" in tab._operator_hint_label.text()
    assert tab._availability_label.text() == "Status panelu: BRAK TF"


def test_map_tab_handles_stale_timestamp() -> None:
    _ensure_qapplication()
    now = datetime.now(timezone.utc)
    tab = MapTab()

    tab.set_map_sample(
        sample=_sample(ts=now - timedelta(seconds=30)),
        quality=DataQuality.VALID,
        ros_connected=True,
        tf_available=True,
        now_utc=now,
    )

    assert "MAP_POSE_STALE" in tab._quality_label.text()
    assert "STALE" in tab._quality_label.text()


def test_map_tab_handles_inconsistent_frame_id() -> None:
    _ensure_qapplication()
    now = datetime.now(timezone.utc)
    tab = MapTab()

    tab.set_map_sample(sample=_sample(ts=now, frame="map"), quality=DataQuality.VALID, ros_connected=True, tf_available=True, now_utc=now)
    tab.set_map_sample(sample=_sample(ts=now, frame="odom"), quality=DataQuality.VALID, ros_connected=True, tf_available=True, now_utc=now)

    assert "MAP_FRAME_MISMATCH" in tab._quality_label.text()
    assert tab._position_label.text() == "Pozycja: BRAK DANYCH"


def test_map_tab_handles_ros_disconnection() -> None:
    _ensure_qapplication()
    now = datetime.now(timezone.utc)
    tab = MapTab()

    tab.set_map_sample(sample=_sample(ts=now), quality=DataQuality.VALID, ros_connected=False, tf_available=True, now_utc=now)

    # [AI-CHANGE | 2026-04-30 18:05 UTC | v0.201]
    # CO ZMIENIONO: Zaktualizowano asercję do wspólnego kodu `ros_unavailable` i dodano
    #               weryfikację, że wskazówka operatorska jest specyficzna (bez fallbacku).
    # DLACZEGO: Test regresyjny ma gwarantować spójny standard kodów i czytelny komunikat
    #           naprawczy dla operatora po rozłączeniu ROS.
    # JAK TO DZIAŁA: Test sprawdza obecność `ros_unavailable` w quality label oraz treść
    #                podpowiedzi „Warstwa ROS jest niedostępna...” pochodzącą z mapy guidance.
    # TODO: Dodać asercję identycznej treści guidance dla rozłączenia ROS w pozostałych kartach UI.
    assert "ros_unavailable" in tab._quality_label.text()
    assert "Warstwa ROS jest niedostępna" in tab._operator_hint_label.text()
    assert tab._source_label.text() == "Źródło danych: BRAK DANYCH"
    assert tab._availability_label.text() == "Status panelu: ROZŁĄCZONY ROS"


def test_map_tab_does_not_show_historical_data_as_current_after_degradation() -> None:
    _ensure_qapplication()
    now = datetime.now(timezone.utc)
    tab = MapTab()

    tab.set_map_sample(sample=_sample(ts=now), quality=DataQuality.VALID, ros_connected=True, tf_available=True, now_utc=now)
    assert tab._position_label.text() == "Pozycja: X=1.0 Y=2.0"

    tab.set_map_sample(
        sample=_sample(ts=now - timedelta(seconds=60), source="tf"),
        quality=DataQuality.VALID,
        ros_connected=True,
        tf_available=True,
        now_utc=now,
    )

    assert tab._position_label.text() == "Pozycja: BRAK DANYCH"
    assert tab._trajectory_label.text() == "Trajektoria: BRAK DANYCH"
    assert "historyczne" in tab._historical_label.text()
    assert "czas=" in tab._historical_label.text()
    assert "X=1.0 Y=2.0" in tab._historical_label.text()
    assert "X=1.0 Y=2.0" not in tab._position_label.text()
    assert "(0,0)->(1,2)" not in tab._trajectory_label.text()


# [AI-CHANGE | 2026-04-30 20:40 UTC | v0.201]
# CO ZMIENIONO: Dodano test regresyjny, że po degradacji dane historyczne nie są renderowane
#               jako aktualna pozycja ani trajektoria, nawet jeśli istnieją w cache ostatniej próbki.
# DLACZEGO: To bezpośrednio zabezpiecza politykę „lepiej brak wyniku niż błędny wynik” na poziomie UI.
# JAK TO DZIAŁA: Test najpierw zapisuje poprawną próbkę `VALID`, potem wymusza degradację przez `STALE`
#                i asercjami pilnuje, że bieżące etykiety pozostają `BRAK DANYCH`, a historia jest osobna.
# TODO: Dodać analogiczny test dla degradacji przez `MAP_FRAME_MISMATCH`.
def test_map_tab_keeps_historical_sample_out_of_current_labels_for_stale_quality() -> None:
    _ensure_qapplication()
    now = datetime.now(timezone.utc)
    tab = MapTab()

    tab.set_map_sample(sample=_sample(ts=now), quality=DataQuality.VALID, ros_connected=True, tf_available=True, now_utc=now)
    tab.set_map_sample(sample=_sample(ts=now), quality=DataQuality.STALE, ros_connected=True, tf_available=True, now_utc=now)

    assert tab._position_label.text() == "Pozycja: BRAK DANYCH"
    assert tab._trajectory_label.text() == "Trajektoria: BRAK DANYCH"
    assert "historyczne" in tab._historical_label.text()
    assert "X=1.0 Y=2.0" in tab._historical_label.text()


# [AI-CHANGE | 2026-04-30 21:00 UTC | v0.201]
# CO ZMIENIONO: Dodano test mapowania statusu panelu na podstawie walidacji próbki i reason_code.
# DLACZEGO: Wymagane jest potwierdzenie, że etykieta statusu odzwierciedla realną gotowość danych mapy.
# JAK TO DZIAŁA: Test przechodzi przez sekwencję stanów: GOTOWY -> OCZEKIWANIE NA DANE
#                (degradacja jakości wejścia) i sprawdza końcowe etykiety UI.
# TODO: Rozszerzyć test o weryfikację spójności kolorów statusu po wdrożeniu dedykowanego kodowania barw.
def test_map_tab_maps_panel_status_for_ready_and_waiting_states() -> None:
    _ensure_qapplication()
    now = datetime.now(timezone.utc)
    tab = MapTab()

    tab.set_map_sample(sample=_sample(ts=now), quality=DataQuality.VALID, ros_connected=True, tf_available=True, now_utc=now)
    assert tab._availability_label.text() == "Status panelu: GOTOWY"

    tab.set_map_sample(sample=_sample(ts=now), quality=DataQuality.STALE, ros_connected=True, tf_available=True, now_utc=now)
    assert tab._availability_label.text() == "Status panelu: OCZEKIWANIE NA DANE"
