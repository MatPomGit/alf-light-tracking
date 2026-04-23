"""Video/Depth operators tab with conservative stream state rendering."""

from __future__ import annotations

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QGridLayout, QGroupBox, QLabel, QPushButton, QVBoxLayout, QWidget

from robot_mission_control.core import DataQuality, StateStore, StateValue

STATE_KEY_VIDEO_STREAM_STATUS = "video_stream_status"
STATE_KEY_DEPTH_STREAM_STATUS = "depth_stream_status"
STATE_KEY_TIME_SYNC_STATUS = "time_sync_status"


# [AI-CHANGE | 2026-04-23 13:10 UTC | v0.183]
# CO ZMIENIONO: Zbudowano panel operatorski z 3 blokami statusu: „Video stream status”,
#               „Depth stream status” oraz „Synchronizacja czasowa”. Dodano też disabled
#               kontrolki funkcji przyszłych opisane jako „NIEDOSTĘPNE W TEJ WERSJI”.
# DLACZEGO: Na etapie bez pełnego playera operator ma widzieć bezpieczny stan logiczny
#           strumieni pobierany z warstwy StateStore/bridge, bez ryzyka domyślnego „OK”.
# JAK TO DZIAŁA: Widok odświeża się cyklicznie (700 ms), pobiera stan z `StateStore`
#                i mapuje go wyłącznie na `CONNECTED`, `STALE` albo `BRAK DANYCH`.
#                Niepewne, puste lub nieznane wartości są celowo degradowane do
#                `BRAK DANYCH` (fail-safe).
# TODO: Dodać integrację z rzeczywistym feedem video/depth i logikę jakościową opartą
#       o wiek ostatniej ramki oraz telemetrię opóźnień transportu.
class VideoDepthTab(QWidget):
    """Panel operatorski dla statusu strumieni video/depth i synchronizacji czasowej."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._state_store = self._resolve_state_store(parent)

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        self._video_status_value = self._build_status_block(root, "Video stream status")
        self._depth_status_value = self._build_status_block(root, "Depth stream status")
        self._sync_status_value = self._build_status_block(root, "Synchronizacja czasowa")

        future_group = QGroupBox("Funkcje przyszłe", self)
        future_layout = QVBoxLayout(future_group)
        future_layout.setSpacing(8)

        snapshot_button = QPushButton("Snapshot — NIEDOSTĘPNE W TEJ WERSJI", future_group)
        snapshot_button.setEnabled(False)
        overlay_button = QPushButton("Overlay — NIEDOSTĘPNE W TEJ WERSJI", future_group)
        overlay_button.setEnabled(False)

        future_layout.addWidget(snapshot_button)
        future_layout.addWidget(overlay_button)
        root.addWidget(future_group)
        root.addStretch(1)

        self._refresh_timer = QTimer(self)
        self._refresh_timer.setInterval(700)
        self._refresh_timer.timeout.connect(self._refresh_view)
        self._refresh_timer.start()

        self._refresh_view()

    def _build_status_block(self, parent_layout: QVBoxLayout, title: str) -> QLabel:
        """Buduje blok statusu i zwraca etykietę przechowującą bieżący stan logiczny."""
        group = QGroupBox(title, self)
        layout = QGridLayout(group)
        layout.addWidget(QLabel("Stan logiczny:", group), 0, 0)

        value_label = QLabel("BRAK DANYCH", group)
        layout.addWidget(value_label, 0, 1)

        parent_layout.addWidget(group)
        return value_label

    def _resolve_state_store(self, parent: QWidget | None) -> StateStore | None:
        """Pobiera StateStore bezpośrednio z okna lub pośrednio przez bridge."""
        window = parent.window() if parent is not None else None
        direct_store = getattr(window, "state_store", None)
        if isinstance(direct_store, StateStore):
            return direct_store

        bridge = getattr(window, "bridge", None)
        bridged_store = getattr(bridge, "state_store", None)
        if isinstance(bridged_store, StateStore):
            return bridged_store
        return None

    def _render_stream_status(self, item: StateValue | None) -> str:
        """Mapuje stan ze Store na bezpieczne wartości operatorskie."""
        if item is None:
            return "BRAK DANYCH"
        if item.quality is DataQuality.STALE:
            return "STALE"
        if item.quality is not DataQuality.VALID or item.value is None:
            return "BRAK DANYCH"

        normalized = str(item.value).strip().upper()
        if normalized == "CONNECTED":
            return "CONNECTED"
        if normalized == "STALE":
            return "STALE"
        return "BRAK DANYCH"

    def _refresh_view(self) -> None:
        """Odświeża statusy panelu na podstawie bieżących wartości StateStore."""
        if self._state_store is None:
            self._video_status_value.setText("BRAK DANYCH")
            self._depth_status_value.setText("BRAK DANYCH")
            self._sync_status_value.setText("BRAK DANYCH")
            return

        self._video_status_value.setText(
            self._render_stream_status(self._state_store.get(STATE_KEY_VIDEO_STREAM_STATUS))
        )
        self._depth_status_value.setText(
            self._render_stream_status(self._state_store.get(STATE_KEY_DEPTH_STREAM_STATUS))
        )
        self._sync_status_value.setText(
            self._render_stream_status(self._state_store.get(STATE_KEY_TIME_SYNC_STATUS))
        )
