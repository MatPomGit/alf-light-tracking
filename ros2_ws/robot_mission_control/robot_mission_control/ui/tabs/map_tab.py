from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace
from datetime import datetime, timedelta, timezone

from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from robot_mission_control.core import (
    STATE_KEY_MAP_DATA_QUALITY,
    STATE_KEY_MAP_FRAME_ID,
    STATE_KEY_MAP_REASON_CODE,
    STATE_KEY_MAP_TF_STATUS,
    STATE_KEY_MAP_TIMESTAMP,
    STATE_KEY_MAP_TRAJECTORY,
    STATE_KEY_MAP_POSITION,
    DataQuality,
    StateValue,
)
from .operator_guidance import resolve_operator_guidance
from .state_rendering import quality_color_hex, render_quality_with_icon


@dataclass(frozen=True)
class MapSample:
    """Próbka danych mapowych wykorzystywana do walidacji UI."""

    timestamp: datetime
    frame_id: str
    x: float | None
    y: float | None
    yaw: float | None
    position_text: str | None
    trajectory_text: str | None
    source: str


# [AI-CHANGE | 2026-04-30 12:10 UTC | v0.201]
# CO ZMIENIONO: Rozszerzono `MapTab` o walidację próbek mapy (świeżość czasu, spójność frame,
#               jakość wejściową i dostępność ROS), jawny wskaźnik źródła/jakości oraz bezpieczne
#               czyszczenie bieżącej pozycji/trajektorii przy degradacji jakości.
# DLACZEGO: Operator nie może zobaczyć historycznej lub niespójnej pozycji jako aktualnej; zgodnie
#           z polityką bezpieczeństwa dla danych niepewnych lepszy jest brak wyniku niż fałszywa lokalizacja.
# JAK TO DZIAŁA: `validate_map_sample` zwraca końcowe `DataQuality` + reason_code, a `set_map_sample`
#                renderuje pozycję/trajektorię wyłącznie dla `VALID`. Dla innych jakości pokazuje
#                `BRAK DANYCH` i wskazówki operatorskie, a wskaźnik jakości korzysta ze spójnego
#                mapowania koloru/ikony z `state_rendering.py`.
# TODO: Dodać walidację geometryczną trajektorii (np. skok pozycji > limit prędkości) opartą o historię TF.
class MapTab(QWidget):
    """Map panel with conservative fail-safe rendering."""

    _ALLOWED_QUALITIES: tuple[DataQuality, ...] = (
        DataQuality.VALID,
        DataQuality.STALE,
        DataQuality.UNAVAILABLE,
        DataQuality.ERROR,
    )
    _DEFAULT_MAX_SAMPLE_AGE_SECONDS = 2.5
    _DEFAULT_MAX_LINEAR_SPEED_MPS = 3.5
    _MAX_ANGULAR_SPEED_RADPS = 2.5

    def __init__(self, parent: QWidget | None = None, map_config: dict[str, float | list[str]] | None = None) -> None:
        super().__init__(parent)
        # [AI-CHANGE | 2026-04-30 23:20 UTC | v0.201]
        # CO ZMIENIONO: Dodano bezpieczne wczytanie parametrów mapy z `map_config` z fallbackiem do wartości domyślnych.
        # DLACZEGO: Niepewna lub uszkodzona konfiguracja nie może powodować awarii ani niebezpiecznego poluzowania walidacji.
        # JAK TO DZIAŁA: `_resolve_map_runtime_limits` waliduje pola i przy błędzie używa konserwatywnych defaultów.
        # TODO: Dodać jawny kanał diagnostyczny sygnalizujący, które pola map_config uruchomiły fallback.
        resolved_map_config = self._resolve_map_runtime_limits(raw_config=map_config or {})
        self._max_sample_age_seconds = resolved_map_config["max_sample_age_s"]
        self._max_linear_speed_mps = resolved_map_config["max_speed_mps"]
        self._allowed_frames = tuple(resolved_map_config["allowed_frames"])
        self._expected_frame_id: str | None = None
        self._last_valid_position_text: str | None = None
        self._last_valid_trajectory_text: str | None = None
        self._last_valid_timestamp: datetime | None = None
        self._previous_sample_for_kinematics: MapSample | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        self._title_label = QLabel("Mapa robota", self)
        self._title_label.setStyleSheet("font-size: 16px; font-weight: 600;")
        layout.addWidget(self._title_label)

        self._position_label = QLabel("Pozycja: BRAK DANYCH", self)
        layout.addWidget(self._position_label)

        self._trajectory_label = QLabel("Trajektoria: BRAK DANYCH", self)
        layout.addWidget(self._trajectory_label)

        self._quality_label = QLabel("Jakość danych mapy: ⚠ UNAVAILABLE", self)
        layout.addWidget(self._quality_label)

        self._source_label = QLabel("Źródło danych: BRAK DANYCH", self)
        layout.addWidget(self._source_label)


        # [AI-CHANGE | 2026-04-30 20:40 UTC | v0.201]
        # CO ZMIENIONO: Dodano etykietę na ostatnią poprawną próbkę wyświetlaną jako dane historyczne.
        # DLACZEGO: Operator potrzebuje kontekstu diagnostycznego bez mieszania historii z pozycją bieżącą.
        # JAK TO DZIAŁA: Etykieta jest aktualizowana wyłącznie przy degradacji jakości i zawiera timestamp UTC.
        # TODO: Rozważyć oddzielną sekcję UI z listą kilku ostatnich poprawnych próbek historycznych.
        self._historical_label = QLabel("Ostatnia poprawna próbka (historyczne): BRAK DANYCH", self)
        self._historical_label.setStyleSheet("color: #6b7280;")
        layout.addWidget(self._historical_label)

        self._operator_hint_label = QLabel("Wskazówki: Sprawdź połączenie ROS i topic TF.", self)
        self._operator_hint_label.setStyleSheet("color: #b7791f;")
        layout.addWidget(self._operator_hint_label)

        self._availability_label = QLabel("Status panelu: OCZEKIWANIE NA DANE", self)
        self._availability_label.setStyleSheet("color: #aa8800;")
        layout.addWidget(self._availability_label)

        layout.addStretch(1)

    def validate_map_sample(
        self,
        *,
        sample: MapSample | None,
        quality: DataQuality,
        ros_connected: bool,
        tf_available: bool,
        now_utc: datetime | None = None,
    ) -> tuple[DataQuality, str]:
        """Waliduje próbkę mapy i zwraca bezpieczny wynik jakości + reason_code."""
        # [AI-CHANGE | 2026-04-30 18:05 UTC | v0.201]
        # CO ZMIENIONO: Ujednolicono docelowy kod dla utraty łączności ROS na `ros_unavailable`
        #               zamiast lokalnego wariantu `ros_disconnected`.
        # DLACZEGO: Wspólny standard kodów upraszcza mapowanie guidance w wielu kartach UI i
        #           eliminuje ryzyko niespójnych komunikatów operatorskich po tym samym incydencie.
        # JAK TO DZIAŁA: Gdy `ros_connected` jest `False`, walidacja zwraca teraz dokładnie
        #                `(DataQuality.UNAVAILABLE, "ros_unavailable")`, który ma dedykowany opis
        #                i akcję w `CODE_GUIDANCE_MAP`.
        # TODO: Wydzielić reason_code mapy do współdzielonych stałych, aby uniknąć literówek w UI/ROS bridge.
        if quality not in self._ALLOWED_QUALITIES:
            return (DataQuality.ERROR, "invalid_quality")
        if not ros_connected:
            return (DataQuality.UNAVAILABLE, "ros_unavailable")
        if not tf_available:
            return (DataQuality.UNAVAILABLE, "MAP_TF_MISSING")
        if sample is None:
            return (DataQuality.UNAVAILABLE, "missing_sample")
        if quality is not DataQuality.VALID:
            return (quality, f"degraded_input_quality:{quality.value}")

        reference_time = now_utc if now_utc is not None else datetime.now(timezone.utc)
        if reference_time - sample.timestamp > timedelta(seconds=self._max_sample_age_seconds):
            return (DataQuality.STALE, "MAP_POSE_STALE")
        if sample.frame_id not in self._allowed_frames:
            return (DataQuality.ERROR, "MAP_FRAME_NOT_ALLOWED")
        if self._expected_frame_id is None:
            self._expected_frame_id = sample.frame_id
        elif sample.frame_id != self._expected_frame_id:
            return (DataQuality.ERROR, "MAP_FRAME_MISMATCH")

        if sample.position_text is None:
            return (DataQuality.UNAVAILABLE, "missing_position")

        # [AI-CHANGE | 2026-04-30 22:10 UTC | v0.201]
        # CO ZMIENIONO: Dodano walidację kinematyczną porównującą bieżącą próbkę z poprzednią
        #               oraz limity bezpieczeństwa dla prędkości liniowej/kątowej.
        # DLACZEGO: Skoki pozycji/yaw pomiędzy próbkami często oznaczają błąd danych mapy;
        #           zgodnie z polityką bezpieczeństwa wolimy odrzucić próbkę niż pokazać fałszywą lokalizację.
        # JAK TO DZIAŁA: `_validate_kinematics_against_previous_sample` zwraca reason_code dla outliera
        #                (UNAVAILABLE przy pojedynczym braku danych wejściowych albo ERROR przy przekroczeniu limitów),
        #                a dla poprawnej próbki zwraca `ok`.
        # TODO: Zastąpić limity stałe wartościami dynamicznymi zależnymi od trybu robota i klasy platformy.
        kinematic_quality, kinematic_reason = self._validate_kinematics_against_previous_sample(
            current_sample=sample
        )
        if kinematic_quality is not DataQuality.VALID:
            return (kinematic_quality, kinematic_reason)

        return (DataQuality.VALID, "ok")

    # [AI-CHANGE | 2026-04-30 23:20 UTC | v0.201]
    # CO ZMIENIONO: Dodano lokalny resolver limitów mapy z walidacją i bezpiecznym fallbackiem.
    # DLACZEGO: `MapTab` musi działać stabilnie nawet przy uszkodzonej konfiguracji wejściowej.
    # JAK TO DZIAŁA: Metoda akceptuje tylko dodatnie liczby i niepustą listę `allowed_frames`; w przeciwnym razie
    #                zwraca twarde defaulty zgodne z polityką bezpieczeństwa danych.
    # TODO: Rozszerzyć fallback o strategię „strict mode”, która całkowicie blokuje render mapy przy błędnym configu.
    def _resolve_map_runtime_limits(self, *, raw_config: dict[str, float | list[str]]) -> dict[str, float | list[str]]:
        max_sample_age_s = raw_config.get("max_sample_age_s")
        if not isinstance(max_sample_age_s, (int, float)) or float(max_sample_age_s) <= 0.0:
            max_sample_age_s = self._DEFAULT_MAX_SAMPLE_AGE_SECONDS
        max_speed_mps = raw_config.get("max_speed_mps")
        if not isinstance(max_speed_mps, (int, float)) or float(max_speed_mps) <= 0.0:
            max_speed_mps = self._DEFAULT_MAX_LINEAR_SPEED_MPS
        raw_allowed_frames = raw_config.get("allowed_frames")
        allowed_frames = [item.strip() for item in raw_allowed_frames if isinstance(item, str) and item.strip()] if isinstance(raw_allowed_frames, list) else []
        if not allowed_frames:
            allowed_frames = ["map"]
        return {
            "max_sample_age_s": float(max_sample_age_s),
            "max_speed_mps": float(max_speed_mps),
            "allowed_frames": allowed_frames,
        }

    def set_map_sample(
        self,
        *,
        sample: MapSample | None,
        quality: DataQuality,
        ros_connected: bool,
        tf_available: bool,
        now_utc: datetime | None = None,
    ) -> None:
        """Aktualizuje mapę po walidacji i czyści prezentację przy degradacji jakości."""
        resolved_quality, reason_code = self.validate_map_sample(
            sample=sample,
            quality=quality,
            ros_connected=ros_connected,
            tf_available=tf_available,
            now_utc=now_utc,
        )
        quality_item = SimpleNamespace(quality=resolved_quality)
        rendered_quality = render_quality_with_icon(quality_item)
        indicator_color = quality_color_hex(quality_item)
        self._quality_label.setText(f"Jakość danych mapy: {rendered_quality} | reason_code={reason_code}")
        self._quality_label.setStyleSheet(f"color: {indicator_color};")
        # [AI-CHANGE | 2026-04-30 21:00 UTC | v0.201]
        # CO ZMIENIONO: Powiązano status panelu mapy z wynikiem walidacji (`resolved_quality`)
        #               oraz `reason_code` przez dedykowane mapowanie stanów operacyjnych.
        # DLACZEGO: Statyczny napis „NIEDOSTĘPNE W TEJ WERSJI” nie odzwierciedlał realnej
        #           gotowości danych i utrudniał szybką diagnostykę błędów wejścia mapy.
        # JAK TO DZIAŁA: `_resolve_panel_status_text` zwraca jeden ze stanów: GOTOWY,
        #                OCZEKIWANIE NA DANE, BRAK TF, ROZŁĄCZONY ROS. Wynik jest wyświetlany
        #                zawsze po walidacji, zanim zostanie wyrenderowana reszta etykiet UI.
        # TODO: Dodać dedykowane kolory statusu panelu zależnie od ryzyka operacyjnego stanu.
        panel_status_text = self._resolve_panel_status_text(
            resolved_quality=resolved_quality,
            reason_code=reason_code,
        )
        self._availability_label.setText(f"Status panelu: {panel_status_text}")

        if resolved_quality is DataQuality.VALID and sample is not None:
            self._previous_sample_for_kinematics = sample
            self._last_valid_position_text = sample.position_text
            self._last_valid_trajectory_text = sample.trajectory_text
            self._last_valid_timestamp = sample.timestamp
            self._position_label.setText(f"Pozycja: {sample.position_text}")
            trajectory = sample.trajectory_text or "BRAK DANYCH"
            self._trajectory_label.setText(f"Trajektoria: {trajectory}")
            self._source_label.setText(f"Źródło danych: {sample.source}")
            self._historical_label.setText("Ostatnia poprawna próbka (historyczne): BRAK DANYCH")
            self._operator_hint_label.setText("Wskazówki: Dane poprawne, monitoruj ciągłość TF.")
            self._operator_hint_label.setStyleSheet("color: #0b6e4f;")
            return

        # [AI-CHANGE | 2026-04-30 20:40 UTC | v0.201]
        # CO ZMIENIONO: Dla jakości innej niż VALID dodano bezpieczny podział na dane bieżące i
        #               sekcję historyczną oraz utrzymano guidance operatorski po `reason_code`.
        # DLACZEGO: Zgodnie z zasadą bezpieczeństwa nie wolno pokazywać danych historycznych jako
        #           aktualnej pozycji/trajektorii, ale warto zachować ostatnią poprawną próbkę
        #           do diagnostyki incydentu jakości.
        # JAK TO DZIAŁA: Główne etykiety pozycji/trajektorii są zawsze czyszczone do `BRAK DANYCH`,
        #                a ostatnia poprawna próbka trafia wyłącznie do etykiety „historyczne”
        #                z timestampem UTC; guidance pozostaje mapowane przez `resolve_operator_guidance`.
        # TODO: Dodać telemetrykę UI dla najczęstszych reason_code mapy i ich czasu trwania.
        self._position_label.setText("Pozycja: BRAK DANYCH")
        self._trajectory_label.setText("Trajektoria: BRAK DANYCH")
        self._source_label.setText("Źródło danych: BRAK DANYCH")
        if self._last_valid_position_text and self._last_valid_timestamp is not None:
            timestamp_text = self._last_valid_timestamp.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
            historical_trajectory = self._last_valid_trajectory_text or "BRAK DANYCH"
            self._historical_label.setText(
                "Ostatnia poprawna próbka (historyczne): "
                f"czas={timestamp_text} | pozycja={self._last_valid_position_text} | trajektoria={historical_trajectory}"
            )
        else:
            self._historical_label.setText("Ostatnia poprawna próbka (historyczne): BRAK DANYCH")
        operator_guidance = resolve_operator_guidance(reason_code=reason_code, status=None)
        self._operator_hint_label.setText(
            f"Wskazówki: Co się stało: {operator_guidance.meaning} Co zrobić: {operator_guidance.action}"
        )
        self._operator_hint_label.setStyleSheet("color: #b7791f;")

    # [AI-CHANGE | 2026-04-30 22:10 UTC | v0.201]
    # CO ZMIENIONO: Dodano metodę do walidacji kinematyki względem poprzedniej próbki mapy.
    # DLACZEGO: Wczesne wykrycie niefizycznych skoków pozycji/kąta chroni operatora przed fałszywym obrazem sytuacji.
    # JAK TO DZIAŁA: Jeśli brakuje którejkolwiek danej liczbowej lub czasu, metoda zwraca bezpieczny stan
    #                `UNAVAILABLE`; jeśli limity są przekroczone, zwraca `ERROR` z `MAP_KINEMATIC_OUTLIER`.
    # TODO: Rozważyć licznik kolejnych outlierów i eskalację do osobnego kodu alarmowego dla dłuższych serii.
    def _validate_kinematics_against_previous_sample(
        self, *, current_sample: MapSample
    ) -> tuple[DataQuality, str]:
        previous_sample = self._previous_sample_for_kinematics
        if previous_sample is None:
            return (DataQuality.VALID, "ok")

        if (
            current_sample.x is None
            or current_sample.y is None
            or current_sample.yaw is None
            or previous_sample.x is None
            or previous_sample.y is None
            or previous_sample.yaw is None
        ):
            return (DataQuality.UNAVAILABLE, "MAP_KINEMATIC_INPUT_MISSING")

        dt_seconds = (current_sample.timestamp - previous_sample.timestamp).total_seconds()
        if dt_seconds <= 0.0:
            return (DataQuality.UNAVAILABLE, "MAP_KINEMATIC_NON_MONOTONIC_TIME")

        dx = current_sample.x - previous_sample.x
        dy = current_sample.y - previous_sample.y
        dyaw = abs(current_sample.yaw - previous_sample.yaw)
        linear_speed = (dx * dx + dy * dy) ** 0.5 / dt_seconds
        angular_speed = dyaw / dt_seconds

        if linear_speed > self._max_linear_speed_mps or angular_speed > self._MAX_ANGULAR_SPEED_RADPS:
            return (DataQuality.ERROR, "MAP_KINEMATIC_OUTLIER")

        return (DataQuality.VALID, "ok")

    # [AI-CHANGE | 2026-04-30 16:20 UTC | v0.201]
    # CO ZMIENIONO: Dodano adapter mapujący rekord snapshotu store na `MapSample`.
    # DLACZEGO: UI wymaga jednego miejsca konwersji kontraktu mapy i twardego odrzucenia danych niekompletnych.
    # JAK TO DZIAŁA: Metoda czyta osobne klucze mapy (dane + quality + reason_code); gdy którekolwiek
    #                pole krytyczne jest niepoprawne, przekazuje do `set_map_sample` wartość `sample=None`.
    # TODO: Rozszerzyć adapter o walidację monotoniczności timestamp dla wykrywania cofnięć czasu.
    def update_from_store_snapshot(self, snapshot: dict[str, StateValue]) -> None:
        position_item = snapshot.get(STATE_KEY_MAP_POSITION)
        frame_item = snapshot.get(STATE_KEY_MAP_FRAME_ID)
        timestamp_item = snapshot.get(STATE_KEY_MAP_TIMESTAMP)
        trajectory_item = snapshot.get(STATE_KEY_MAP_TRAJECTORY)
        tf_status_item = snapshot.get(STATE_KEY_MAP_TF_STATUS)
        quality_item = snapshot.get(STATE_KEY_MAP_DATA_QUALITY)
        reason_item = snapshot.get(STATE_KEY_MAP_REASON_CODE)

        sample: MapSample | None = None
        if all(item is not None for item in (position_item, frame_item, timestamp_item, tf_status_item)):
            pos_val = position_item.value if position_item else None
            frame_val = frame_item.value if frame_item else None
            ts_val = timestamp_item.value if timestamp_item else None
            tf_val = tf_status_item.value if tf_status_item else None
            if (
                isinstance(pos_val, tuple)
                and len(pos_val) == 2
                and isinstance(frame_val, str)
                and isinstance(ts_val, datetime)
                and isinstance(tf_val, str)
            ):
                trajectory_text = None
                if trajectory_item is not None and isinstance(trajectory_item.value, tuple):
                    trajectory_text = f"points={len(trajectory_item.value)}"
                sample = MapSample(
                    timestamp=ts_val,
                    frame_id=frame_val,
                    x=float(pos_val[0]),
                    y=float(pos_val[1]),
                    yaw=0.0,
                    position_text=f"x={pos_val[0]:.2f}, y={pos_val[1]:.2f}",
                    trajectory_text=trajectory_text,
                    source=position_item.source,
                )

        quality = DataQuality.UNAVAILABLE
        if quality_item is not None and quality_item.quality is DataQuality.VALID and isinstance(quality_item.value, str):
            quality = DataQuality[quality_item.value] if quality_item.value in DataQuality.__members__ else DataQuality.ERROR

        ros_connected = True
        tf_available = bool(tf_status_item and tf_status_item.quality is DataQuality.VALID and tf_status_item.value == "OK")
        self.set_map_sample(sample=sample, quality=quality, ros_connected=ros_connected, tf_available=tf_available)

    def set_map_status(self, quality: DataQuality, *, position_text: str | None = None) -> None:
        """Kompatybilny wrapper dla istniejących wywołań testowych."""
        sample = None
        if position_text is not None:
            sample = MapSample(
                timestamp=datetime.now(timezone.utc),
                frame_id="map",
                x=None,
                y=None,
                yaw=None,
                position_text=position_text,
                trajectory_text=None,
                source="legacy",
            )
        self.set_map_sample(sample=sample, quality=quality, ros_connected=True, tf_available=True)

    def _resolve_panel_status_text(self, *, resolved_quality: DataQuality, reason_code: str) -> str:
        """Mapuje wynik walidacji mapy na zwięzły status gotowości panelu."""
        if reason_code == "ros_unavailable":
            return "ROZŁĄCZONY ROS"
        if reason_code == "MAP_TF_MISSING":
            return "BRAK TF"
        if resolved_quality is DataQuality.VALID and reason_code == "ok":
            return "GOTOWY"
        return "OCZEKIWANIE NA DANE"
