"""Map tab with explicit safe startup state and data quality visibility."""

from __future__ import annotations

from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from robot_mission_control.core import DataQuality


# [AI-CHANGE | 2026-04-30 10:28 UTC | v0.201]
# CO ZMIENIONO: Dodano nową zakładkę `MapTab` z bezpiecznym stanem startowym oraz jawną prezentacją
#               statusów jakości danych (VALID/STALE/UNAVAILABLE/ERROR).
# DLACZEGO: W obszarze mapy nie wolno domyślnie prezentować pozycji bez pewności danych;
#           zgodnie z zasadą bezpieczeństwa lepszy jest brak wyniku niż wynik błędny.
# JAK TO DZIAŁA: Po inicjalizacji zakładka renderuje `BRAK DANYCH` i status `UNAVAILABLE`.
#                Metoda `set_map_status` przyjmuje tylko jawnie dopuszczalne quality i aktualizuje
#                ekran; dla nieznanego statusu wymusza bezpieczny fallback `ERROR` + `BRAK DANYCH`.
# TODO: Podpiąć źródło danych pozycji robota z walidacją świeżości timestamp i filtrem outlierów.
class MapTab(QWidget):
    """Map panel with conservative fail-safe rendering."""

    _ALLOWED_QUALITIES: tuple[DataQuality, ...] = (
        DataQuality.VALID,
        DataQuality.STALE,
        DataQuality.UNAVAILABLE,
        DataQuality.ERROR,
    )

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        self._title_label = QLabel("Mapa robota", self)
        self._title_label.setStyleSheet("font-size: 16px; font-weight: 600;")
        layout.addWidget(self._title_label)

        self._position_label = QLabel("Pozycja: BRAK DANYCH", self)
        layout.addWidget(self._position_label)

        self._quality_label = QLabel("Jakość danych mapy: UNAVAILABLE", self)
        layout.addWidget(self._quality_label)

        self._availability_label = QLabel("Status panelu: NIEDOSTĘPNE W TEJ WERSJI", self)
        self._availability_label.setStyleSheet("color: #aa8800;")
        layout.addWidget(self._availability_label)

        layout.addStretch(1)

    def set_map_status(self, quality: DataQuality, *, position_text: str | None = None) -> None:
        """Aktualizuje stan mapy z jawnym fallbackiem bezpieczeństwa."""
        if quality not in self._ALLOWED_QUALITIES:
            self._quality_label.setText("Jakość danych mapy: ERROR")
            self._position_label.setText("Pozycja: BRAK DANYCH")
            return

        self._quality_label.setText(f"Jakość danych mapy: {quality.value}")
        if quality is DataQuality.VALID and position_text:
            self._position_label.setText(f"Pozycja: {position_text}")
            return

        self._position_label.setText("Pozycja: BRAK DANYCH")
