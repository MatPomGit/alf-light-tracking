"""Telemetry tab with quality-aware state table."""

from __future__ import annotations

from datetime import datetime, timezone

from PySide6.QtCore import QTimer
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QCheckBox, QHeaderView, QLabel, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget

from robot_mission_control.core import (
    GLOBAL_STATE_KEYS,
    STATE_KEY_DATA_SOURCE_MODE,
    STATE_KEY_DEPENDENCY_STATUS,
    STATE_KEY_ROS_CONNECTION_STATUS,
    DataQuality,
    StateStore,
    StateValue,
)
from .state_rendering import quality_color_hex, render_quality_with_icon, render_value


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

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(8)

        self._title = QLabel("Telemetry danych runtime", self)
        self._title.setStyleSheet("font-size: 16px; font-weight: 600;")
        root.addWidget(self._title)

        self._problems_only_checkbox = QCheckBox("Tylko problemy", self)
        self._problems_only_checkbox.toggled.connect(self._refresh_table)
        root.addWidget(self._problems_only_checkbox)

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
        snapshot = self._state_store.snapshot() if self._state_store is not None else {}

        rows: list[tuple[str, StateValue | None]] = []
        for key in self._telemetry_keys:
            item = snapshot.get(key)
            if problems_only and item is not None and item.quality is DataQuality.VALID:
                continue
            rows.append((key, item))

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
