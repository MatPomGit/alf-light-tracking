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
    StateValue,
)
from robot_mission_control.ui.operator_alerts import OperatorAlerts
from .operator_guidance import map_action_status_to_mission_state, resolve_operator_guidance
from .state_rendering import is_actionable, render_card_value_with_warning, render_quality


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

        # [AI-CHANGE | 2026-04-23 20:11 UTC | v0.193]
        # CO ZMIENIONO: Dodano kartę szybkiej decyzji operatora z polami:
        #               „Ocena bezpieczeństwa”, „Stan misji” i „Aktywne alarmy krytyczne”.
        # DLACZEGO: Kryterium ukończenia wymaga, aby operator jednym spojrzeniem ocenił,
        #           czy może bezpiecznie kontynuować misję.
        # JAK TO DZIAŁA: Karta renderuje jawny werdykt (`MOŻNA KONTYNUOWAĆ` / `WSTRZYMAJ MISJĘ`)
        #                oparty o jakość danych, łączność ROS i aktywne alarmy krytyczne.
        # TODO: Dodać sygnał dźwiękowy przy przejściu z trybu bezpiecznego do krytycznego.
        safety_card = QFrame(self)
        safety_layout = QGridLayout(safety_card)
        safety_layout.setVerticalSpacing(8)
        safety_layout.setHorizontalSpacing(14)
        # [AI-CHANGE | 2026-04-25 12:40 UTC | v0.201]
        # CO ZMIENIONO: Dodano w OverviewTab pola „Co się stało” i „Co zrobić”
        #               obok panelu decyzji bezpieczeństwa.
        # DLACZEGO: Operator ma otrzymać jednocześnie werdykt oraz kontekst/incydent + instrukcję działania.
        # JAK TO DZIAŁA: Etykiety są odświeżane z tego samego źródła mapowania co Diagnostics/Controls/Rosbag.
        # TODO: Dodać skrócony tooltip z ostatnim kodem reason_code i kluczem stanu.
        self._safety_value = QLabel("WSTRZYMAJ MISJĘ", safety_card)
        self._safety_value.setStyleSheet("font-size: 18px; font-weight: 800; color: #b00020;")
        self._mission_state_value = QLabel("BRAK DANYCH", safety_card)
        self._what_happened_value = QLabel("BRAK DANYCH", safety_card)
        self._what_to_do_value = QLabel("Wstrzymaj działania do czasu odzyskania wiarygodnych danych.", safety_card)
        self._critical_alarm_count_value = QLabel("0", safety_card)

        safety_layout.addWidget(QLabel("Ocena bezpieczeństwa:", safety_card), 0, 0)
        safety_layout.addWidget(self._safety_value, 0, 1)
        safety_layout.addWidget(QLabel("Stan misji:", safety_card), 1, 0)
        safety_layout.addWidget(self._mission_state_value, 1, 1)
        safety_layout.addWidget(QLabel("Co się stało:", safety_card), 2, 0)
        safety_layout.addWidget(self._what_happened_value, 2, 1)
        safety_layout.addWidget(QLabel("Co zrobić:", safety_card), 3, 0)
        safety_layout.addWidget(self._what_to_do_value, 3, 1)
        safety_layout.addWidget(QLabel("Aktywne alarmy krytyczne:", safety_card), 4, 0)
        safety_layout.addWidget(self._critical_alarm_count_value, 4, 1)
        root.addWidget(safety_card)

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
        # [AI-CHANGE | 2026-04-23 18:29 UTC | v0.195]
        # CO ZMIENIONO: OverviewTab pobiera interwał odświeżania z konfiguracji MainWindow.
        # DLACZEGO: Usuwamy hardcode 700 ms i umożliwiamy dostrojenie panelu decyzyjnego przez YAML.
        # JAK TO DZIAŁA: Zakładka odczytuje `overview_tab_refresh_interval_ms`; gdy brak wartości,
        #                stosowany jest fallback 700 ms bez wpływu na bezpieczeństwo renderowania.
        # TODO: Uzależnić interwał od liczby aktywnych alertów krytycznych.
        window = self.window()
        timer_fn = getattr(window, "ui_timer_interval_ms", None)
        interval_ms = timer_fn("overview_tab_refresh_interval_ms", default_ms=700) if callable(timer_fn) else 700
        self._refresh_timer.setInterval(interval_ms)
        self._refresh_timer.timeout.connect(self._refresh_view)
        self._refresh_timer.start()
        self._refresh_view()

    def _resolve_state_store(self, parent: QWidget | None) -> StateStore | None:
        window = parent.window() if parent is not None else None
        return getattr(window, "state_store", None)

    def _resolve_operator_alerts(self, parent: QWidget | None) -> OperatorAlerts | None:
        window = parent.window() if parent is not None else None
        return getattr(window, "operator_alerts", None)

    # [AI-CHANGE | 2026-04-24 10:20 UTC | v0.200]
    # CO ZMIENIONO: Wprowadzono renderowanie pól kart Overview z jawnym ostrzeżeniem i reason_code
    #               dla wszystkich próbek, których `quality != VALID`.
    # DLACZEGO: DoD wymaga braku ścieżki, w której niepewne dane wyglądają jak operacyjne.
    # JAK TO DZIAŁA: Dla niepewnych próbek helper zwraca `⚠ BRAK DANYCH | reason_code=...`,
    #                a dla jakości VALID renderuje rzeczywistą wartość bez dodatkowych adnotacji.
    # TODO: Dodać ikonę ostrzegawczą obok etykiety jakości i tooltip z pełnym kontekstem diagnostycznym.
    def _refresh_view(self) -> None:
        if self._state_store is None:
            self._connection_value.setText("ROZŁĄCZONY")
            self._action_status_value.setText("BRAK DANYCH")
            self._action_progress_value.setText("BRAK DANYCH")
            self._action_result_value.setText("BRAK DANYCH")
            self._quality_value.setText(DataQuality.UNAVAILABLE.value)
            self._mission_state_value.setText("BRAK DANYCH")
            fallback_guidance = resolve_operator_guidance(reason_code="missing_data")
            self._what_happened_value.setText(fallback_guidance.meaning)
            self._what_to_do_value.setText(fallback_guidance.action)
            self._critical_alarm_count_value.setText("0")
            self._set_safety_decision(can_continue=False)
            self._alarm_banner.setText("ALERT KRYTYCZNY: BRAK POŁĄCZENIA ZE STATESTORE")
            self._alarm_banner.setVisible(True)
            return

        connection_item = self._state_store.get(STATE_KEY_ROS_CONNECTION_STATUS)
        action_status_item = self._state_store.get(STATE_KEY_ACTION_STATUS)
        action_progress_item = self._state_store.get(STATE_KEY_ACTION_PROGRESS)
        action_result_item = self._state_store.get(STATE_KEY_ACTION_RESULT)

        self._connection_value.setText(render_card_value_with_warning(connection_item, fallback="BRAK DANYCH"))
        self._action_status_value.setText(render_card_value_with_warning(action_status_item, fallback="BRAK DANYCH"))
        self._action_progress_value.setText(render_card_value_with_warning(action_progress_item, fallback="BRAK DANYCH"))
        self._action_result_value.setText(render_card_value_with_warning(action_result_item, fallback="BRAK DANYCH"))

        observed_items = [connection_item, action_status_item, action_progress_item, action_result_item]
        worst_quality = next((item.quality for item in observed_items if item is not None and item.quality is not DataQuality.VALID), None)
        representative_item = next((item for item in observed_items if item is not None and item.quality is worst_quality), None)
        self._quality_value.setText(DataQuality.VALID.value if worst_quality is None else render_quality(representative_item))
        # [AI-CHANGE | 2026-04-25 12:40 UTC | v0.201]
        # CO ZMIENIONO: Dodano wyliczanie guidance operatorskiego przy każdym odświeżeniu OverviewTab.
        # DLACZEGO: Zakładka overview ma zawsze pokazywać „co się stało” + „co zrobić” bez zgadywania.
        # JAK TO DZIAŁA: Priorytet ma `reason_code` próbki nie-VALID, a gdy brak błędu używany jest
        #                status akcji; finalny tekst pochodzi z `resolve_operator_guidance`.
        # TODO: Rozszerzyć priorytet wyboru guidance o kody alertów krytycznych z OperatorAlerts.
        self._mission_state_value.setText(self._render_mission_state(action_status_item))
        action_status_text = str(action_status_item.value) if action_status_item is not None else None
        guidance_reason = action_status_item.reason_code if action_status_item is not None else None
        if representative_item is not None and representative_item.reason_code:
            guidance_reason = representative_item.reason_code
        guidance = resolve_operator_guidance(reason_code=guidance_reason, status=action_status_text)
        self._what_happened_value.setText(guidance.meaning)
        self._what_to_do_value.setText(guidance.action)

        # [AI-CHANGE | 2026-04-23 16:30 UTC | v0.188]
        # CO ZMIENIONO: Baner OverviewTab został podłączony do „ostatniego krytycznego alertu”
        #               z centralnego rejestru `OperatorAlerts`.
        # DLACZEGO: Operator ma widzieć konkretny, najnowszy komunikat CRITICAL, a nie ogólny tekst alarmu.
        # JAK TO DZIAŁA: Widok odczytuje `last_critical_alert()` i renderuje kod + komunikat + timestamp;
        #                gdy brak alertu krytycznego, baner jest ukrywany.
        # TODO: Dodać akcję „Przejdź do Diagnostics” po kliknięciu banera krytycznego.
        critical_alert = self._operator_alerts.last_critical_alert() if self._operator_alerts is not None else None
        critical_alert_count = self._count_active_critical_alerts()
        self._critical_alarm_count_value.setText(str(critical_alert_count))
        # [AI-CHANGE | 2026-04-29 13:35 UTC | v0.333]
        # CO ZMIENIONO: Rozbito decyzję kontynuacji na jawnie typowany warunek połączenia.
        # DLACZEGO: `is_actionable` chroni runtime przed niepewną próbką, ale statycznie nie zawęża `StateValue | None`;
        #           dostęp do `.value` musi być poprzedzony bezpośrednim sprawdzeniem `None`.
        # JAK TO DZIAŁA: `connection_is_connected` jest prawdziwe tylko dla pewnej próbki `CONNECTED`; brak próbki
        #                albo jakość inna niż VALID blokują kontynuację misji.
        # TODO: Przenieść tę decyzję do wspólnego helpera bezpieczeństwa, żeby Controls/Overview używały identycznej bramki.
        connection_is_connected = (
            connection_item is not None
            and is_actionable(connection_item)
            and str(connection_item.value).upper() == "CONNECTED"
        )
        can_continue = connection_is_connected and worst_quality is None and critical_alert_count == 0
        self._set_safety_decision(can_continue=can_continue)
        if critical_alert is None:
            self._alarm_banner.setVisible(False)
            return
        timestamp = critical_alert.updated_at.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        self._alarm_banner.setText(
            f"ALERT KRYTYCZNY [{critical_alert.code}] {critical_alert.message} | {timestamp}"
        )
        self._alarm_banner.setVisible(True)

    # [AI-CHANGE | 2026-04-23 20:11 UTC | v0.193]
    # CO ZMIENIONO: Dodano metody pomocnicze `_set_safety_decision`, `_render_mission_state`
    #               oraz `_count_active_critical_alerts` dla panelu decyzji operatorskiej.
    # DLACZEGO: Logika decyzji bezpieczeństwa musi być jawna, testowalna i odseparowana od renderowania pól.
    # JAK TO DZIAŁA: `_set_safety_decision` nadaje etykietę i kolor, `_render_mission_state` mapuje status
    #                akcji na stan misji, a `_count_active_critical_alerts` liczy aktywne alerty CRITICAL.
    # [AI-CHANGE | 2026-04-25 12:40 UTC | v0.201]
    # CO ZMIENIONO: `OverviewTab` korzysta z współdzielonego mapowania stanu misji i guidance operatorskiego.
    # DLACZEGO: Operator ma widzieć ten sam opis „co się stało/co zrobić” i ten sam status misji
    #           niezależnie od tego, czy patrzy na Overview czy Diagnostics/Controls/Rosbag.
    # JAK TO DZIAŁA: `_render_mission_state` deleguje mapowanie do `map_action_status_to_mission_state`,
    #                a guidance jest wyliczane przez `resolve_operator_guidance` z `reason_code`/statusu.
    # TODO: Ujednolicić styl (kolory/ikony) sekcji „co się stało/co zrobić” we wszystkich kartach UI.
    def _set_safety_decision(self, *, can_continue: bool) -> None:
        if can_continue:
            self._safety_value.setText("MOŻNA KONTYNUOWAĆ")
            self._safety_value.setStyleSheet("font-size: 18px; font-weight: 800; color: #0b6e4f;")
            return
        self._safety_value.setText("WSTRZYMAJ MISJĘ")
        self._safety_value.setStyleSheet("font-size: 18px; font-weight: 800; color: #b00020;")

    def _render_mission_state(self, action_status_item: StateValue | None) -> str:
        if not is_actionable(action_status_item):
            return render_card_value_with_warning(action_status_item, fallback="BRAK DANYCH")
        # [AI-CHANGE | 2026-04-29 13:35 UTC | v0.333]
        # CO ZMIENIONO: Dodano asercję zawężającą status akcji po walidacji jakości.
        # DLACZEGO: Bezpośredni dostęp do `.value` jest bezpieczny tylko po potwierdzeniu, że próbka istnieje i ma jakość VALID.
        # JAK TO DZIAŁA: Brak lub niepewny status wcześniej zwraca ostrzeżenie `BRAK DANYCH`; asercja zabezpiecza kontrakt
        #                przed przypadkowym ominięciem tej bramki.
        # TODO: Zastąpić asercję typowanym `TypeGuard` dla wspólnej funkcji `is_actionable`.
        assert action_status_item is not None
        status = str(action_status_item.value)
        return map_action_status_to_mission_state(status)

    def _count_active_critical_alerts(self) -> int:
        if self._operator_alerts is None:
            return 0
        return sum(1 for alert in self._operator_alerts.active_alerts() if alert.severity == "CRITICAL")
