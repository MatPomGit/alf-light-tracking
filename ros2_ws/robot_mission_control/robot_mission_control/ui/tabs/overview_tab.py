"""Overview tab with runtime mission summary."""

from __future__ import annotations

from datetime import timezone

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QFrame, QGridLayout, QLabel, QVBoxLayout, QWidget

from robot_mission_control.core import (
    STATE_KEY_ACTION_PROGRESS,
    STATE_KEY_ACTION_RESULT,
    STATE_KEY_ACTION_STATUS,
    STATE_KEY_ROS_CONNECTION_STATUS,
    DataQuality,
    StateStore,
)
from robot_mission_control.ui.operator_alerts import OperatorAlerts
from .state_rendering import render_quality, render_value


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

    # [AI-CHANGE | 2026-04-23 16:30 UTC | v0.188]
    # CO ZMIENIONO: Dodano podłączenie `OverviewTab` do centralnego rejestru `OperatorAlerts`.
    # DLACZEGO: Baner zakładki ma prezentować ostatni alert krytyczny z tego samego źródła,
    #           z którego korzysta DiagnosticsTab, aby uniknąć rozbieżności.
    # JAK TO DZIAŁA: Zakładka pobiera referencję `operator_alerts` z okna nadrzędnego i używa jej
    #                podczas odświeżania do renderowania komunikatu krytycznego.
    # TODO: Dodać lokalny cache komunikatu, aby ograniczyć migotanie banera przy szybkim odświeżaniu.
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._state_store = self._resolve_state_store(parent)
        self._operator_alerts = self._resolve_operator_alerts(parent)

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

    def _resolve_operator_alerts(self, parent: QWidget | None) -> OperatorAlerts | None:
        window = parent.window() if parent is not None else None
        return getattr(window, "operator_alerts", None)

    # [AI-CHANGE | 2026-04-23 14:15 UTC | v0.187]
    # CO ZMIENIONO: Usunięto lokalny helper fallbacków i podpięto wspólne funkcje
    #               `render_value` / `render_quality` z modułu `state_rendering`.
    # DLACZEGO: Jedno źródło prawdy eliminuje duplikację i wymusza jednolite bramkowanie jakości
    #           we wszystkich zakładkach operacyjnych.
    # JAK TO DZIAŁA: Widok renderuje wartości przez wspólny helper, który zwraca fallback dla każdego
    #                stanu nie-VALID, więc operator nie zobaczy wartości operacyjnej z niepewnej próbki.
    # TODO: Ujednolicić ranking „worst_quality” przez centralny helper z priorytetami jakości.
    def _refresh_view(self) -> None:
        if self._state_store is None:
            self._connection_value.setText("ROZŁĄCZONY")
            self._action_status_value.setText("BRAK DANYCH")
            self._action_progress_value.setText("BRAK DANYCH")
            self._action_result_value.setText("BRAK DANYCH")
            self._quality_value.setText(DataQuality.UNAVAILABLE.value)
            self._alarm_banner.setText("ALERT KRYTYCZNY: BRAK POŁĄCZENIA ZE STATESTORE")
            self._alarm_banner.setVisible(True)
            return

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
        representative_item = next((item for item in observed_items if item is not None and item.quality is worst_quality), None)
        self._quality_value.setText(DataQuality.VALID.value if worst_quality is None else render_quality(representative_item))

        # [AI-CHANGE | 2026-04-23 16:30 UTC | v0.188]
        # CO ZMIENIONO: Baner OverviewTab został podłączony do „ostatniego krytycznego alertu”
        #               z centralnego rejestru `OperatorAlerts`.
        # DLACZEGO: Operator ma widzieć konkretny, najnowszy komunikat CRITICAL, a nie ogólny tekst alarmu.
        # JAK TO DZIAŁA: Widok odczytuje `last_critical_alert()` i renderuje kod + komunikat + timestamp;
        #                gdy brak alertu krytycznego, baner jest ukrywany.
        # TODO: Dodać akcję „Przejdź do Diagnostics” po kliknięciu banera krytycznego.
        critical_alert = self._operator_alerts.last_critical_alert() if self._operator_alerts is not None else None
        if critical_alert is None:
            self._alarm_banner.setVisible(False)
            return
        timestamp = critical_alert.updated_at.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        self._alarm_banner.setText(
            f"ALERT KRYTYCZNY [{critical_alert.code}] {critical_alert.message} | {timestamp}"
        )
        self._alarm_banner.setVisible(True)
