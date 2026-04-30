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
        x=1.0,
        y=2.0,
        yaw=0.1,
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


# [AI-CHANGE | 2026-04-30 23:20 UTC | v0.201]
# CO ZMIENIONO: Dodano testy inicjalizacji `MapTab` z poprawnym presetem oraz uszkodzonym presetem konfiguracji.
# DLACZEGO: Musimy potwierdzić, że parametry mapy są konfigurowalne i jednocześnie bezpiecznie fallbackują przy błędzie.
# JAK TO DZIAŁA: Pierwszy test sprawdza przyjęcie limitów z `map_config`, drugi weryfikuje fallback do defaultów.
# TODO: Rozszerzyć testy o przypadek częściowo poprawnego presetu (np. tylko `allowed_frames`).
def test_map_tab_initializes_with_custom_map_preset() -> None:
    _ensure_qapplication()
    tab = MapTab(
        map_config={
            "max_sample_age_s": 1.25,
            "max_speed_mps": 1.75,
            "allowed_frames": ["map", "odom"],
        }
    )
    assert tab._max_sample_age_seconds == 1.25
    assert tab._max_linear_speed_mps == 1.75
    assert tab._allowed_frames == ("map", "odom")


def test_map_tab_initializes_with_safe_fallback_for_broken_preset() -> None:
    _ensure_qapplication()
    tab = MapTab(
        map_config={
            "max_sample_age_s": -5.0,
            "max_speed_mps": 0.0,
            "allowed_frames": [""],
        }
    )
    assert tab._max_sample_age_seconds == tab._DEFAULT_MAX_SAMPLE_AGE_SECONDS
    assert tab._max_linear_speed_mps == tab._DEFAULT_MAX_LINEAR_SPEED_MPS
    assert tab._allowed_frames == ("map",)


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


# [AI-CHANGE | 2026-04-30 22:10 UTC | v0.201]
# CO ZMIENIONO: Dodano testy graniczne walidacji kinematyki: ruch poprawny, pojedynczy outlier
#               oraz seria kolejnych outlierów utrzymująca blokadę renderowania.
# DLACZEGO: To zabezpiecza wymaganie bezpieczeństwa „lepiej brak danych niż błędna pozycja/trajektoria”.
# JAK TO DZIAŁA: Testy porównują próbki z kontrolowanym krokiem czasu i sprawdzają reason_code,
#                jakość oraz etykiety pozycji/trajektorii po wykryciu przekroczeń limitów.
# TODO: Dodać osobny test dla skoku kąta (`yaw`) bez istotnego ruchu liniowego.
def test_map_tab_accepts_kinematically_valid_motion() -> None:
    _ensure_qapplication()
    now = datetime.now(timezone.utc)
    tab = MapTab()

    first = MapSample(timestamp=now, frame_id="map", x=0.0, y=0.0, yaw=0.0, position_text="x=0.00,y=0.00", trajectory_text=None, source="odom")
    second = MapSample(timestamp=now + timedelta(seconds=1), frame_id="map", x=0.5, y=0.0, yaw=0.2, position_text="x=0.50,y=0.00", trajectory_text=None, source="odom")

    tab.set_map_sample(sample=first, quality=DataQuality.VALID, ros_connected=True, tf_available=True, now_utc=first.timestamp)
    tab.set_map_sample(sample=second, quality=DataQuality.VALID, ros_connected=True, tf_available=True, now_utc=second.timestamp)

    assert "reason_code=ok" in tab._quality_label.text()
    assert tab._position_label.text() == "Pozycja: x=0.50,y=0.00"


def test_map_tab_rejects_single_kinematic_outlier() -> None:
    _ensure_qapplication()
    now = datetime.now(timezone.utc)
    tab = MapTab()

    base = MapSample(timestamp=now, frame_id="map", x=0.0, y=0.0, yaw=0.0, position_text="x=0.00,y=0.00", trajectory_text=None, source="odom")
    outlier = MapSample(timestamp=now + timedelta(seconds=1), frame_id="map", x=25.0, y=0.0, yaw=4.0, position_text="x=25.00,y=0.00", trajectory_text=None, source="odom")

    tab.set_map_sample(sample=base, quality=DataQuality.VALID, ros_connected=True, tf_available=True, now_utc=base.timestamp)
    tab.set_map_sample(sample=outlier, quality=DataQuality.VALID, ros_connected=True, tf_available=True, now_utc=outlier.timestamp)

    assert "MAP_KINEMATIC_OUTLIER" in tab._quality_label.text()
    assert tab._position_label.text() == "Pozycja: BRAK DANYCH"
    assert tab._trajectory_label.text() == "Trajektoria: BRAK DANYCH"


def test_map_tab_rejects_series_of_kinematic_outliers() -> None:
    _ensure_qapplication()
    now = datetime.now(timezone.utc)
    tab = MapTab()

    valid_seed = MapSample(timestamp=now, frame_id="map", x=0.0, y=0.0, yaw=0.0, position_text="x=0.00,y=0.00", trajectory_text=None, source="odom")
    tab.set_map_sample(sample=valid_seed, quality=DataQuality.VALID, ros_connected=True, tf_available=True, now_utc=valid_seed.timestamp)

    for i in range(1, 4):
        outlier = MapSample(
            timestamp=now + timedelta(seconds=i),
            frame_id="map",
            x=20.0 * i,
            y=0.0,
            yaw=3.5 * i,
            position_text=f"x={20.0 * i:.2f},y=0.00",
            trajectory_text=None,
            source="odom",
        )
        tab.set_map_sample(sample=outlier, quality=DataQuality.VALID, ros_connected=True, tf_available=True, now_utc=outlier.timestamp)
        assert "MAP_KINEMATIC_OUTLIER" in tab._quality_label.text()
        assert tab._position_label.text() == "Pozycja: BRAK DANYCH"


# [AI-CHANGE | 2026-04-30 23:40 UTC | v0.199]
# CO ZMIENIONO: Dodano negatywne testy schematu wejściowego `validate_map_sample` dla błędnych typów/formatów:
#               naive datetime, pusty frame/source, puste `position_text` oraz runtime exception.
# DLACZEGO: Walidator musi zawsze zwracać bezpieczny wynik (`ERROR` + reason_code), a nie generować wyjątek w UI.
# JAK TO DZIAŁA: Każdy test tworzy uszkodzoną próbkę i sprawdza finalne etykiety po `set_map_sample` oraz
#                bezpośredni wynik `validate_map_sample`, oczekując `MAP_SAMPLE_INVALID_SCHEMA`.
# TODO: Rozszerzyć przypadki o błędy serializacji z realnego transportu ROS (np. `timestamp=None` po deserializacji).
@pytest.mark.parametrize(
    "sample",
    [
        MapSample(
            timestamp=datetime(2026, 4, 30, 12, 0, 0),
            frame_id="map",
            x=1.0,
            y=2.0,
            yaw=0.0,
            position_text="X=1.0 Y=2.0",
            trajectory_text="traj",
            source="odom",
        ),
        MapSample(
            timestamp=datetime(2026, 4, 30, 12, 0, 0, tzinfo=timezone.utc),
            frame_id="   ",
            x=1.0,
            y=2.0,
            yaw=0.0,
            position_text="X=1.0 Y=2.0",
            trajectory_text="traj",
            source="odom",
        ),
        MapSample(
            timestamp=datetime(2026, 4, 30, 12, 0, 0, tzinfo=timezone.utc),
            frame_id="map",
            x=1.0,
            y=2.0,
            yaw=0.0,
            position_text="X=1.0 Y=2.0",
            trajectory_text="traj",
            source="  ",
        ),
        MapSample(
            timestamp=datetime(2026, 4, 30, 12, 0, 0, tzinfo=timezone.utc),
            frame_id="map",
            x=1.0,
            y=2.0,
            yaw=0.0,
            position_text="",
            trajectory_text="traj",
            source="odom",
        ),
    ],
)
def test_map_tab_returns_safe_error_for_invalid_schema_variants(sample: MapSample) -> None:
    _ensure_qapplication()
    tab = MapTab()
    now_utc = datetime(2026, 4, 30, 12, 0, 1, tzinfo=timezone.utc)

    quality, reason_code = tab.validate_map_sample(
        sample=sample,
        quality=DataQuality.VALID,
        ros_connected=True,
        tf_available=True,
        now_utc=now_utc,
    )
    assert quality is DataQuality.ERROR
    assert reason_code == "MAP_SAMPLE_INVALID_SCHEMA"

    tab.set_map_sample(sample=sample, quality=DataQuality.VALID, ros_connected=True, tf_available=True, now_utc=now_utc)
    assert "reason_code=MAP_SAMPLE_INVALID_SCHEMA" in tab._quality_label.text()
    assert tab._position_label.text() == "Pozycja: BRAK DANYCH"


def test_map_tab_validate_map_sample_catches_runtime_exception() -> None:
    _ensure_qapplication()
    tab = MapTab()
    now = datetime.now(timezone.utc)

    broken_sample = MapSample(
        timestamp=now,
        frame_id="map",
        x=1.0,
        y=2.0,
        yaw=0.0,
        position_text="X=1.0 Y=2.0",
        trajectory_text="traj",
        source="odom",
    )
    object.__setattr__(broken_sample, "timestamp", "2026-04-30T12:00:00Z")

    quality, reason_code = tab.validate_map_sample(
        sample=broken_sample,
        quality=DataQuality.VALID,
        ros_connected=True,
        tf_available=True,
        now_utc=now,
    )
    assert quality is DataQuality.ERROR
    assert reason_code == "MAP_SAMPLE_INVALID_SCHEMA"
