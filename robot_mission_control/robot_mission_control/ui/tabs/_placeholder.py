"""Shared placeholder widget for unfinished tabs."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

# [AI-CHANGE | 2026-04-20 14:12 UTC | v0.141]
# CO ZMIENIONO: Dodano wspólny widget placeholdera dla niegotowych zakładek.
# DLACZEGO: Redukujemy duplikację kodu i wymuszamy spójne oznaczenie „NIEDOSTĘPNE W TEJ WERSJI”.
# JAK TO DZIAŁA: Widget renderuje tytuł zakładki, status BRAK DANYCH oraz komunikat niedostępności.
# TODO: Rozszerzyć placeholder o checklistę warunków aktywacji funkcji i link do dokumentacji.


class UnavailableTab(QWidget):
    """Simple disabled-like content used until implementation is ready."""

    def __init__(self, tab_name: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setEnabled(False)

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        title = QLabel(tab_name, self)
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("font-size: 16px; font-weight: 600;")

        data_state = QLabel("BRAK DANYCH", self)
        data_state.setAlignment(Qt.AlignmentFlag.AlignCenter)

        unavailable = QLabel("NIEDOSTĘPNE W TEJ WERSJI", self)
        unavailable.setAlignment(Qt.AlignmentFlag.AlignCenter)
        unavailable.setStyleSheet("font-weight: 700; color: #a94442;")

        layout.addWidget(title)
        layout.addWidget(data_state)
        layout.addWidget(unavailable)
