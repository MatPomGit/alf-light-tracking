"""Overview tab with runtime mission summary."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QFrame, QGridLayout, QLabel, QVBoxLayout, QWidget

from robot_mission_control.core import (
    STATE_KEY_ACTION_PROGRESS,
    STATE_KEY_ACTION_RESULT,
    STATE_KEY_ACTION_STATUS,
    STATE_KEY_ROS_CONNECTION_STATUS,
    DataQuality,
    StateStore,
    StateValue,
)


# [AI-CHANGE | 2026-04-23 12:55 UTC | v0.180]
# CO ZMIENIONO: Zastąpiono placeholder dziedziczący po UnavailableTab pełnym QWidget z sekcjami:
#               stan łączności ROS, status akcji, jakość danych oraz czerwony baner alarmowy.
# DLACZEGO: Operator potrzebuje bieżącego i bezpiecznego podglądu najważniejszych sygnałów stanu,
#           a zakładka nie może już pozostać nieaktywna.
# JAK TO DZIAŁA: Zakładka odczytuje wartości ze StateStore co 700 ms przez QTimer, renderuje je
#                helperem zgodnym semantycznie z MainWindow._render_value i stosuje fallbacki:
#                `BRAK DANYCH` dla brakujących/niepewnych danych oraz `ROZŁĄCZONY` dla łączności.
#                Baner alarmowy jest pokazywany, gdy brak pewnego połączenia ROS albo jakość danych
#                nie jest `VALID`, zgodnie z zasadą bezpieczeństwa (lepiej brak wyniku niż błędny wynik).
# TODO: Rozszerzyć baner o kody reason_code i mapowanie priorytetów alarmów (INFO/WARN/CRITICAL).


class OverviewTab(QWidget):
    """Runtime overview panel with conservative status rendering."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._state_store = self._resolve_state_store(parent)

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(8)

        self._alarm_banner = QLabel("ALARM: BRAK PEWNEGO POŁĄCZENIA LUB JAKOŚCI DANYCH", self)
        self._alarm_banner.setStyleSheet(
            "background-color: #b00020; color: white; font-weight: 700; padding: 8px; border-radius: 4px;"
        )
        root.addWidget(self._alarm_banner)

        card = QFrame(self)
        layout = QGridLayout(card)
        layout.setVerticalSpacing(10)
        layout.setHorizontalSpacing(14)

        self._connection_value = QLabel("ROZŁĄCZONY", card)
        self._action_status_value = QLabel("BRAK DANYCH", card)
        self._action_progress_value = QLabel("BRAK DANYCH", card)
        self._action_result_value = QLabel("BRAK DANYCH", card)
        self._quality_value = QLabel(DataQuality.UNAVAILABLE.value, card)

        row = 0
        layout.addWidget(QLabel("Stan łączności ROS:", card), row, 0)
        layout.addWidget(self._connection_value, row, 1)
        row += 1

        layout.addWidget(QLabel("Status akcji:", card), row, 0)
        layout.addWidget(self._action_status_value, row, 1)
        row += 1

        layout.addWidget(QLabel("Postęp akcji:", card), row, 0)
        layout.addWidget(self._action_progress_value, row, 1)
        row += 1

        layout.addWidget(QLabel("Wynik akcji:", card), row, 0)
        layout.addWidget(self._action_result_value, row, 1)
        row += 1

        layout.addWidget(QLabel("Jakość danych:", card), row, 0)
        layout.addWidget(self._quality_value, row, 1)

        root.addWidget(card)
        root.addStretch(1)

        self._refresh_timer = QTimer(self)
        self._refresh_timer.setInterval(700)
        self._refresh_timer.timeout.connect(self._refresh_view)
        self._refresh_timer.start()
        self._refresh_view()

    def _resolve_state_store(self, parent: QWidget | None) -> StateStore | None:
        window = parent.window() if parent is not None else None
        return getattr(window, "state_store", None)

    def _resolve_render_helper(self) -> Callable[[StateValue | None], str]:
        window = self.window()
        render_fn = getattr(window, "_render_value", None)
        if callable(render_fn):
            return render_fn

        def _fallback_render(item: StateValue | None, *, fallback: str = "BRAK DANYCH") -> str:
            if item is None:
                return fallback
            if item.quality is not DataQuality.VALID:
                if item.quality is DataQuality.ERROR:
                    return "BŁĄD DANYCH"
                if item.quality is DataQuality.STALE:
                    return "DANE PRZETERMINOWANE"
                return fallback
            return str(item.value)

        return _fallback_render

    def _refresh_view(self) -> None:
        if self._state_store is None:
            self._connection_value.setText("ROZŁĄCZONY")
            self._action_status_value.setText("BRAK DANYCH")
            self._action_progress_value.setText("BRAK DANYCH")
            self._action_result_value.setText("BRAK DANYCH")
            self._quality_value.setText(DataQuality.UNAVAILABLE.value)
            self._alarm_banner.setVisible(True)
            return

        render_value = self._resolve_render_helper()

        connection_item = self._state_store.get(STATE_KEY_ROS_CONNECTION_STATUS)
        action_status_item = self._state_store.get(STATE_KEY_ACTION_STATUS)
        action_progress_item = self._state_store.get(STATE_KEY_ACTION_PROGRESS)
        action_result_item = self._state_store.get(STATE_KEY_ACTION_RESULT)

        self._connection_value.setText(render_value(connection_item, fallback="ROZŁĄCZONY"))
        self._action_status_value.setText(render_value(action_status_item, fallback="BRAK DANYCH"))
        self._action_progress_value.setText(render_value(action_progress_item, fallback="BRAK DANYCH"))
        self._action_result_value.setText(render_value(action_result_item, fallback="BRAK DANYCH"))

        observed_items = [connection_item, action_status_item, action_progress_item, action_result_item]
        worst_quality = next((item.quality for item in observed_items if item is not None and item.quality is not DataQuality.VALID), None)
        self._quality_value.setText(worst_quality.value if worst_quality is not None else DataQuality.VALID.value)

        connection_uncertain = connection_item is None or connection_item.quality is not DataQuality.VALID
        data_quality_invalid = worst_quality is not None
        self._alarm_banner.setVisible(connection_uncertain or data_quality_invalid)
