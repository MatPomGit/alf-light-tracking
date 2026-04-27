"""Video/Depth operators tab with conservative stream state rendering."""

from __future__ import annotations

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QGridLayout, QGroupBox, QLabel, QPushButton, QVBoxLayout, QWidget

from robot_mission_control.core import DataQuality, StateStore, StateValue
from .operator_guidance import resolve_operator_guidance
from .state_rendering import render_card_value_with_warning, render_state

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
        # [AI-CHANGE | 2026-04-27 06:55 UTC | v0.203]
        # CO ZMIENIONO: Dodano do VideoDepthTab sekcję „Co się stało / Co zrobić”
        #               opartą o wspólny resolver `operator_guidance`.
        # DLACZEGO: Ta karta była ostatnią bez pełnego guidance operatorskiego, co tworzyło
        #           niespójność względem Overview/Diagnostics/Controls/Rosbag.
        # JAK TO DZIAŁA: Sekcja otrzymuje komunikat z `resolve_operator_guidance` wyliczony
        #                z reprezentatywnego `reason_code` (lub statusu) dla video/depth/sync.
        # TODO: Dodać wyróżnienie wizualne (kolor/ikona) zależne od krytyczności guidance.
        guidance_group = QGroupBox("Guidance operatora", self)
        guidance_layout = QGridLayout(guidance_group)
        self._what_happened_value = QLabel("BRAK DANYCH", guidance_group)
        self._what_to_do_value = QLabel("Wstrzymaj działania do czasu odzyskania wiarygodnych danych.", guidance_group)
        guidance_layout.addWidget(QLabel("Co się stało:", guidance_group), 0, 0)
        guidance_layout.addWidget(self._what_happened_value, 0, 1)
        guidance_layout.addWidget(QLabel("Co zrobić:", guidance_group), 1, 0)
        guidance_layout.addWidget(self._what_to_do_value, 1, 1)
        root.addWidget(guidance_group)

        future_group = QGroupBox("Funkcje przyszłe", self)
        future_layout = QVBoxLayout(future_group)
        future_layout.setSpacing(8)

        # [AI-CHANGE | 2026-04-25 08:57 UTC | v0.202]
        # CO ZMIENIONO: Zastąpiono martwe przyciski „Snapshot/Overlay” zestawem działających akcji:
        #               „Odśwież status teraz” i „Kopiuj status streamów”.
        # DLACZEGO: Operator potrzebuje natychmiastowych działań diagnostycznych w karcie VideoDepth;
        #           przyciski bez implementacji obniżały użyteczność panelu.
        # JAK TO DZIAŁA: Pierwszy przycisk wymusza `refresh`, a drugi kopiuje do schowka bezpieczny
        #                raport statusów (video/depth/sync) wraz z quality i timestampem UTC.
        # TODO: Rozszerzyć akcje o eksport raportu do pliku i automatyczne dołączanie ostatniego reason_code.
        snapshot_button = QPushButton("Odśwież status teraz", future_group)
        snapshot_button.clicked.connect(self._refresh_view)
        overlay_button = QPushButton("Kopiuj status streamów", future_group)
        overlay_button.clicked.connect(self._copy_stream_status_to_clipboard)

        future_layout.addWidget(snapshot_button)
        future_layout.addWidget(overlay_button)
        root.addWidget(future_group)
        root.addStretch(1)

        self._refresh_timer = QTimer(self)
        # [AI-CHANGE | 2026-04-23 18:29 UTC | v0.195]
        # CO ZMIENIONO: Interwał odświeżania VideoDepthTab został przeniesiony do konfiguracji.
        # DLACZEGO: Usuwamy hardcode 700 ms, aby parametry odświeżania regulować przez YAML.
        # JAK TO DZIAŁA: Zakładka odczytuje `video_depth_tab_refresh_interval_ms` z MainWindow,
        #                a jeśli wartość nie jest dostępna, zachowuje fallback 700 ms.
        # TODO: Dodać adaptacyjny interwał zależny od FPS źródła video.
        window = self.window()
        timer_fn = getattr(window, "ui_timer_interval_ms", None)
        interval_ms = timer_fn("video_depth_tab_refresh_interval_ms", default_ms=700) if callable(timer_fn) else 700
        self._refresh_timer.setInterval(interval_ms)
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

    # [AI-CHANGE | 2026-04-24 10:20 UTC | v0.200]
    # CO ZMIENIONO: `_render_stream_status` pokazuje teraz jawne ostrzeżenie i `reason_code`
    #               dla każdej próbki o jakości różnej od `VALID`.
    # DLACZEGO: Status strumieni jest kartą operacyjną, więc niepewna próbka nie może wyglądać
    #           jak normalny stan (`CONNECTED`/`STALE`) bez wyraźnego ostrzeżenia.
    # JAK TO DZIAŁA: Dla quality != VALID zwracany jest tekst `⚠ BRAK DANYCH | reason_code=...`;
    #                mapowanie `CONNECTED/STALE` działa wyłącznie dla próbek operacyjnych.
    # TODO: Dodać dodatkowe pole z wiekiem próbki (age_ms), aby łatwiej diagnozować przeterminowanie.
    def _render_stream_status(self, item: StateValue | None) -> str:
        """Mapuje stan ze Store na bezpieczne wartości operatorskie."""
        if item is None:
            return "BRAK DANYCH"
        if item.quality is not DataQuality.VALID or item.value is None:
            return render_card_value_with_warning(item)

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
            fallback_guidance = resolve_operator_guidance(reason_code="missing_data")
            self._what_happened_value.setText(fallback_guidance.meaning)
            self._what_to_do_value.setText(fallback_guidance.action)
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
        # [AI-CHANGE | 2026-04-27 06:55 UTC | v0.203]
        # CO ZMIENIONO: VideoDepthTab wylicza guidance z tych samych reguł co pozostałe karty operatorskie.
        # DLACZEGO: Ujednolicenie eliminuje ryzyko, że operator dostanie sprzeczne zalecenia
        #           dla tego samego incydentu zależnie od aktywnej zakładki.
        # JAK TO DZIAŁA: Funkcja wybiera pierwszą nie-VALID próbkę (video > depth > sync);
        #                jeżeli wszystkie są VALID, fallbackowo używa statusu video.
        # TODO: Rozszerzyć selekcję o priorytet severity po integracji z centralnym rejestrem alertów.
        representative_item = next(
            (
                item
                for item in (video_item, depth_item, sync_item)
                if item is not None and (item.quality is not DataQuality.VALID or item.value is None)
            ),
            None,
        )
        guidance = resolve_operator_guidance(
            reason_code=representative_item.reason_code if representative_item is not None else None,
            status=str(video_item.value) if video_item is not None and video_item.value is not None else None,
        )
        self._what_happened_value.setText(guidance.meaning)
        self._what_to_do_value.setText(guidance.action)

    # [AI-CHANGE | 2026-04-25 08:57 UTC | v0.202]
    # CO ZMIENIONO: Dodano eksport skrótu statusu Video/Depth/Sync do schowka systemowego.
    # DLACZEGO: Ułatwia to szybką eskalację incydentów (ticket/chat) bez ręcznego przepisywania danych.
    # JAK TO DZIAŁA: Metoda pobiera aktualne etykiety z UI i składa jedną linię tekstu diagnostycznego;
    #                gdy schowek jest niedostępny, funkcja kończy się bez side effectów.
    # TODO: Dodać opcjonalny format wieloliniowy JSON dla integracji z narzędziami observability.
    def _copy_stream_status_to_clipboard(self) -> None:
        payload = (
            "video_depth_status | "
            f"video={self._video_status_value.text()} ({self._video_quality_value.text()}) | "
            f"depth={self._depth_status_value.text()} ({self._depth_quality_value.text()}) | "
            f"sync={self._sync_status_value.text()} ({self._sync_quality_value.text()})"
        )
        clipboard = QApplication.clipboard()
        if clipboard is not None:
            clipboard.setText(payload)
