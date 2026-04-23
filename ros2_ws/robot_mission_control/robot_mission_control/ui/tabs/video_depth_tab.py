"""Video/Depth operators tab with conservative stream state rendering."""

from __future__ import annotations

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QGridLayout, QGroupBox, QLabel, QPushButton, QVBoxLayout, QWidget

from robot_mission_control.core import DataQuality, StateStore, StateValue
from .state_rendering import render_state

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

        self._video_status_value, self._video_quality_value = self._build_status_block(root, "Video stream status")
        self._depth_status_value, self._depth_quality_value = self._build_status_block(root, "Depth stream status")
        self._sync_status_value, self._sync_quality_value = self._build_status_block(root, "Synchronizacja czasowa")

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

    # [AI-CHANGE | 2026-04-23 17:10 UTC | v0.192]
    # CO ZMIENIONO: Rozszerzono blok statusu VideoDepth o dodatkową etykietę „Quality”.
    # DLACZEGO: Wymagane jest podpięcie kart do wspólnego renderowania stanów
    #           `VALID/STALE/UNAVAILABLE/ERROR` i jawna widoczność jakości próbki.
    # JAK TO DZIAŁA: Każdy blok zwraca teraz dwie etykiety: stan logiczny + stan quality.
    # TODO: Dodać ikony statusu quality i spójny theme kolorów dla operatora.
    def _build_status_block(self, parent_layout: QVBoxLayout, title: str) -> tuple[QLabel, QLabel]:
        """Buduje blok statusu i zwraca etykiety: stan logiczny oraz quality."""
        group = QGroupBox(title, self)
        layout = QGridLayout(group)
        layout.addWidget(QLabel("Stan logiczny:", group), 0, 0)

        value_label = QLabel("BRAK DANYCH", group)
        layout.addWidget(value_label, 0, 1)
        layout.addWidget(QLabel("Quality:", group), 1, 0)
        quality_label = QLabel("UNAVAILABLE", group)
        layout.addWidget(quality_label, 1, 1)

        parent_layout.addWidget(group)
        return value_label, quality_label

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
            self._video_quality_value.setText("UNAVAILABLE")
            self._depth_quality_value.setText("UNAVAILABLE")
            self._sync_quality_value.setText("UNAVAILABLE")
            return
        # [AI-CHANGE | 2026-04-23 17:10 UTC | v0.192]
        # CO ZMIENIONO: Podpięto VideoDepthTab do wspólnego helpera `render_state`
        #               dla wszystkich trzech kart statusu strumieni.
        # DLACZEGO: Karta ma raportować te same stany jakości co reszta UI i nie używać
        #           lokalnych, niespójnych etykiet jakości.
        # JAK TO DZIAŁA: Dla każdego klucza pobierana jest próbka, renderowany jest
        #                bezpieczny stan logiczny oraz wspólny stan quality.
        # TODO: Zastąpić ręczne przypisania pętlą po mapie klucz -> etykiety.
        video_item = self._state_store.get(STATE_KEY_VIDEO_STREAM_STATUS)
        depth_item = self._state_store.get(STATE_KEY_DEPTH_STREAM_STATUS)
        sync_item = self._state_store.get(STATE_KEY_TIME_SYNC_STATUS)

        self._video_status_value.setText(self._render_stream_status(video_item))
        self._depth_status_value.setText(self._render_stream_status(depth_item))
        self._sync_status_value.setText(self._render_stream_status(sync_item))
        self._video_quality_value.setText(render_state(video_item))
        self._depth_quality_value.setText(render_state(depth_item))
        self._sync_quality_value.setText(render_state(sync_item))
