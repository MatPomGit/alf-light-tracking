"""Telemetry tab with quality-aware state table."""

from __future__ import annotations

from datetime import datetime, timezone

from PySide6.QtCore import QTimer
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from robot_mission_control.core import (
    GLOBAL_STATE_KEYS,
    STATE_KEY_DATA_SOURCE_MODE,
    STATE_KEY_DEPENDENCY_STATUS,
    STATE_KEY_ROS_CONNECTION_STATUS,
    DataQuality,
    StateStore,
    StateValue,
)
from .state_rendering import quality_color_hex, render_quality_with_icon, render_value, severity_rank_from_quality


# [AI-CHANGE | 2026-04-23 16:20 UTC | v0.181]
# CO ZMIENIONO: Zastąpiono placeholder TelemetryTab pełnym widokiem tabelarycznym QTableWidget,
#               który prezentuje klucze telemetryczne ze StateStore (tryb źródła, dependency,
#               połączenie ROS i wszystkie klucze akcji `action_*`) razem z kolumnami: value,
#               quality, reason_code, timestamp oraz ostrzeżenie jakości.
# DLACZEGO: Operator potrzebuje jednego miejsca do diagnostyki telemetrii wykonania; dodatkowo
#           wymagane jest bezpieczne zachowanie: gdy jakość nie jest pewna, UI ma pokazywać brak
#           bieżącej wartości zamiast potencjalnie błędnej ostatniej próbki.
# JAK TO DZIAŁA: Zakładka cyklicznie odczytuje snapshot ze StateStore, mapuje każdy klucz na wiersz
#                tabeli, a dla jakości UNAVAILABLE/STALE/ERROR wymusza tekst `BRAK DANYCH` w kolumnie
#                wartości oraz etykietę ostrzegawczą. Checkbox "Tylko problemy" ukrywa rekordy VALID.
# TODO: Dodać sortowanie po czasie i opcjonalne grupowanie kluczy (source/dependency/ros/action).
class TelemetryTab(QWidget):
    """Telemetry panel with conservative data rendering."""

    _BASE_KEYS: tuple[str, ...] = (
        STATE_KEY_DATA_SOURCE_MODE,
        STATE_KEY_DEPENDENCY_STATUS,
        STATE_KEY_ROS_CONNECTION_STATUS,
    )

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._state_store = self._resolve_state_store(parent)
        self._telemetry_keys = self._build_telemetry_keys()
        self._severity_filters: tuple[str, ...] = ("ALL", "CRITICAL", "HIGH", "MEDIUM", "INFO")

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(8)

        self._title = QLabel("Telemetry danych runtime", self)
        self._title.setStyleSheet("font-size: 16px; font-weight: 600;")
        root.addWidget(self._title)

        # [AI-CHANGE | 2026-04-27 08:25 UTC | v0.203]
        # CO ZMIENIONO: Dodano pasek filtrów telemetryki: checkbox „Tylko problemy”, filtr severity
        #               oraz filtr tekstowy po nazwie klucza.
        # DLACZEGO: Operator musi szybciej zawężać widok do krytycznych rekordów przy dużej liczbie kluczy.
        # JAK TO DZIAŁA: Każda zmiana filtra uruchamia `_refresh_table`; rekord przechodzi dalej tylko gdy
        #                spełnia wszystkie warunki (problem/severity/nazwa klucza).
        # TODO: Dodać preset filtrów per rola operatora (L1/L2/serwis).
        filters_layout = QHBoxLayout()
        self._problems_only_checkbox = QCheckBox("Tylko problemy", self)
        self._problems_only_checkbox.toggled.connect(self._refresh_table)
        filters_layout.addWidget(self._problems_only_checkbox)

        self._severity_filter = QComboBox(self)
        self._severity_filter.addItems(self._severity_filters)
        self._severity_filter.currentIndexChanged.connect(self._refresh_table)
        filters_layout.addWidget(QLabel("Severity ≥", self))
        filters_layout.addWidget(self._severity_filter)

        self._key_filter_edit = QLineEdit(self)
        self._key_filter_edit.setPlaceholderText("Filtr klucza (np. action_)")
        self._key_filter_edit.textChanged.connect(self._refresh_table)
        filters_layout.addWidget(self._key_filter_edit, stretch=1)
        root.addLayout(filters_layout)

        self._table = QTableWidget(self)
        self._table.setColumnCount(6)
        self._table.setHorizontalHeaderLabels(["Klucz", "Wartość", "Quality", "Reason code", "Timestamp", "Ostrzeżenie"])
        self._table.verticalHeader().setVisible(False)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self._table.setAlternatingRowColors(True)
        header = self._table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        root.addWidget(self._table)
        # [AI-CHANGE | 2026-04-27 08:25 UTC | v0.203]
        # CO ZMIENIONO: Dodano legendę kolorów quality bezpośrednio pod tabelą telemetryczną.
        # DLACZEGO: Kolory quality są skuteczne tylko wtedy, gdy operator zna ich znaczenie bez zgadywania.
        # JAK TO DZIAŁA: Etykieta legendy odwzorowuje mapę `VALID/STALE/UNAVAILABLE/ERROR` używaną
        #                przez helpery renderowania i działa jako stały kontekst dla odczytu tabeli.
        # TODO: Dodać wariant legendy z wysokim kontrastem (tryb nocny i projektor).
        self._quality_legend = QLabel(
            "Legenda quality: ✅ VALID (zielony) | ⚠ STALE/UNAVAILABLE (amber) | ⛔ ERROR (czerwony)",
            self,
        )
        root.addWidget(self._quality_legend)

        self._refresh_timer = QTimer(self)
        # [AI-CHANGE | 2026-04-23 18:29 UTC | v0.195]
        # CO ZMIENIONO: TelemetryTab korzysta teraz z interwału timera podanego w konfiguracji.
        # DLACZEGO: Hardcode 700 ms utrudniał strojenie obciążenia UI i częstotliwości telemetrii.
        # JAK TO DZIAŁA: Zakładka pobiera `telemetry_tab_refresh_interval_ms` z MainWindow,
        #                a gdy konfiguracja nie jest dostępna, stosuje fallback 700 ms.
        # TODO: Dodać metrykę czasu renderowania, by automatycznie dobierać interwał.
        window = self.window()
        timer_fn = getattr(window, "ui_timer_interval_ms", None)
        interval_ms = timer_fn("telemetry_tab_refresh_interval_ms", default_ms=700) if callable(timer_fn) else 700
        self._refresh_timer.setInterval(interval_ms)
        self._refresh_timer.timeout.connect(self._refresh_table)
        self._refresh_timer.start()
        self._refresh_table()

    def _resolve_state_store(self, parent: QWidget | None) -> StateStore | None:
        window = parent.window() if parent is not None else None
        return getattr(window, "state_store", None)

    def _build_telemetry_keys(self) -> tuple[str, ...]:
        action_keys = tuple(key for key in GLOBAL_STATE_KEYS if key.startswith("action_"))
        ordered_keys: list[str] = []
        for key in (*self._BASE_KEYS, *action_keys):
            if key not in ordered_keys:
                ordered_keys.append(key)
        return tuple(ordered_keys)

    def _refresh_table(self) -> None:
        problems_only = self._problems_only_checkbox.isChecked()
        key_filter = self._key_filter_edit.text().strip().lower()
        min_severity = self._severity_filter.currentText()
        snapshot = self._state_store.snapshot() if self._state_store is not None else {}

        rows: list[tuple[str, StateValue | None]] = []
        min_rank = self._severity_filters.index(min_severity) - 1 if min_severity in self._severity_filters else -1
        for key in self._telemetry_keys:
            item = snapshot.get(key)
            if problems_only and item is not None and item.quality is DataQuality.VALID:
                continue
            if key_filter and key_filter not in key.lower():
                continue
            if min_rank >= 0:
                row_rank = severity_rank_from_quality(item)
                if row_rank > min_rank:
                    continue
            rows.append((key, item))
        rows.sort(
            key=lambda row: (
                severity_rank_from_quality(row[1]),
                0 if row[1] is None else -int(row[1].timestamp.timestamp()),
                row[0],
            )
        )

        # [AI-CHANGE | 2026-04-25 16:20 UTC | v0.201]
        # CO ZMIENIONO: Kolumna Quality używa teraz mapowania quality -> ikona/kolor.
        # DLACZEGO: Operator szybciej rozpoznaje stan danych przy wysokim obciążeniu poznawczym.
        # JAK TO DZIAŁA: `render_quality_with_icon` buduje etykietę z ikoną, a `quality_color_hex`
        #                koloruje tekst komórki jakości zgodnie z poziomem ryzyka.
        # TODO: Dodać legendę kolorów Quality bezpośrednio pod tabelą telemetryczną.
        self._table.setRowCount(len(rows))
        for row_index, (key, item) in enumerate(rows):
            self._table.setItem(row_index, 0, QTableWidgetItem(key))
            self._table.setItem(row_index, 1, QTableWidgetItem(render_value(item)))
            quality_item = QTableWidgetItem(render_quality_with_icon(item))
            quality_item.setForeground(QColor(quality_color_hex(item)))
            self._table.setItem(row_index, 2, quality_item)
            self._table.setItem(row_index, 3, QTableWidgetItem(self._render_reason_code(item)))
            self._table.setItem(row_index, 4, QTableWidgetItem(self._render_timestamp(item)))
            self._table.setItem(row_index, 5, QTableWidgetItem(self._render_warning_label(item)))

    def _render_reason_code(self, item: StateValue | None) -> str:
        if item is None:
            return "missing_state"
        return item.reason_code or "-"

    def _render_timestamp(self, item: StateValue | None) -> str:
        if item is None:
            return "-"
        timestamp = item.timestamp
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)
        return self._format_timestamp(timestamp)

    def _format_timestamp(self, timestamp: datetime) -> str:
        return timestamp.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    def _render_warning_label(self, item: StateValue | None) -> str:
        if item is None:
            return "⚠ UNAVAILABLE"
        if item.quality in (DataQuality.UNAVAILABLE, DataQuality.STALE, DataQuality.ERROR):
            return f"⚠ {item.quality.value}"
        return "-"
