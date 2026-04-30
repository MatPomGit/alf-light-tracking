from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace
from datetime import datetime, timedelta, timezone

from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from robot_mission_control.core import DataQuality
from .state_rendering import quality_color_hex, render_quality_with_icon


@dataclass(frozen=True)
class MapSample:
    """Próbka danych mapowych wykorzystywana do walidacji UI."""

    timestamp: datetime
    frame_id: str
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
    _MAX_SAMPLE_AGE_SECONDS = 2.5

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._expected_frame_id: str | None = None
        self._last_valid_position_text: str | None = None
        self._last_valid_trajectory_text: str | None = None

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

        self._operator_hint_label = QLabel("Wskazówki: Sprawdź połączenie ROS i topic TF.", self)
        self._operator_hint_label.setStyleSheet("color: #b7791f;")
        layout.addWidget(self._operator_hint_label)

        self._availability_label = QLabel("Status panelu: NIEDOSTĘPNE W TEJ WERSJI", self)
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
        if quality not in self._ALLOWED_QUALITIES:
            return (DataQuality.ERROR, "invalid_quality")
        if not ros_connected:
            return (DataQuality.UNAVAILABLE, "ros_disconnected")
        if not tf_available:
            return (DataQuality.UNAVAILABLE, "missing_tf")
        if sample is None:
            return (DataQuality.UNAVAILABLE, "missing_sample")
        if quality is not DataQuality.VALID:
            return (quality, f"degraded_input_quality:{quality.value}")

        reference_time = now_utc if now_utc is not None else datetime.now(timezone.utc)
        if reference_time - sample.timestamp > timedelta(seconds=self._MAX_SAMPLE_AGE_SECONDS):
            return (DataQuality.STALE, "stale_timestamp")

        if self._expected_frame_id is None:
            self._expected_frame_id = sample.frame_id
        elif sample.frame_id != self._expected_frame_id:
            return (DataQuality.ERROR, "frame_mismatch")

        if sample.position_text is None:
            return (DataQuality.UNAVAILABLE, "missing_position")

        return (DataQuality.VALID, "ok")

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

        if resolved_quality is DataQuality.VALID and sample is not None:
            self._last_valid_position_text = sample.position_text
            self._last_valid_trajectory_text = sample.trajectory_text
            self._position_label.setText(f"Pozycja: {sample.position_text}")
            trajectory = sample.trajectory_text or "BRAK DANYCH"
            self._trajectory_label.setText(f"Trajektoria: {trajectory}")
            self._source_label.setText(f"Źródło danych: {sample.source}")
            self._operator_hint_label.setText("Wskazówki: Dane poprawne, monitoruj ciągłość TF.")
            self._operator_hint_label.setStyleSheet("color: #0b6e4f;")
            return

        self._position_label.setText("Pozycja: BRAK DANYCH")
        self._trajectory_label.setText("Trajektoria: BRAK DANYCH")
        self._source_label.setText("Źródło danych: BRAK DANYCH")
        self._operator_hint_label.setText(
            "Wskazówki: Zweryfikuj ROS/TF, spójność frame_id i świeżość timestamp.")
        self._operator_hint_label.setStyleSheet("color: #b7791f;")

    def set_map_status(self, quality: DataQuality, *, position_text: str | None = None) -> None:
        """Kompatybilny wrapper dla istniejących wywołań testowych."""
        sample = None
        if position_text is not None:
            sample = MapSample(
                timestamp=datetime.now(timezone.utc),
                frame_id="map",
                position_text=position_text,
                trajectory_text=None,
                source="legacy",
            )
        self.set_map_sample(sample=sample, quality=quality, ros_connected=True, tf_available=True)
