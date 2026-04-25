"""Controls tab with mission action lifecycle controls."""

from __future__ import annotations

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QGroupBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from robot_mission_control.core import (
    ActionStatusLabel,
    STATE_KEY_ACTION_GOAL_ID,
    STATE_KEY_ACTION_PROGRESS,
    STATE_KEY_ACTION_RESULT,
    STATE_KEY_ACTION_STATUS,
    StateStore,
)
from .operator_guidance import resolve_operator_guidance
from .state_rendering import is_actionable, render_card_value_with_warning, render_value


# [AI-CHANGE | 2026-04-21 05:21 UTC | v0.163]
# CO ZMIENIONO: Zastąpiono placeholder zakładki ControlsTab pełnym panelem operatora dla akcji
#               (start goal, cancel, podgląd progress oraz wynik końcowy).
# DLACZEGO: DoD wymaga, aby operator widział pełny status wykonania akcji bez przełączania do logów.
# JAK TO DZIAŁA: Zakładka pobiera dane ze StateStore, wywołuje callbacki z MainWindow i odświeża widok co 500 ms;
#                przy jakości != VALID pokazuje bezpieczny fallback `BRAK DANYCH`.
# TODO: Dodać wizualny timeline etapów akcji z dokładnymi timestampami i kodami błędów.


class ControlsTab(QWidget):
    """Operator panel for action lifecycle operations."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._state_store = self._resolve_state_store(parent)

        root = QVBoxLayout(self)
        card = QFrame(self)
        root.addWidget(card)

        layout = QVBoxLayout(card)
        title = QLabel("Sterowanie akcją", card)
        title.setStyleSheet("font-size: 16px; font-weight: 600;")

        buttons = QHBoxLayout()
        self._send_button = QPushButton("Wyślij goal", card)
        self._cancel_button = QPushButton("Anuluj goal", card)
        self._cancel_button.setEnabled(False)

        self._send_button.clicked.connect(self._on_send_goal)
        self._cancel_button.clicked.connect(self._on_cancel_goal)

        buttons.addWidget(self._send_button)
        buttons.addWidget(self._cancel_button)

        # [AI-CHANGE | 2026-04-21 15:52 UTC | v0.176]
        # CO ZMIENIONO: Dodano panel szybkich akcji operatorskich z predefiniowanymi funkcjami misji
        #               (patrol, powrót do bazy, pauza i wznowienie).
        # DLACZEGO: Operatorzy najczęściej wykonują powtarzalne polecenia i potrzebują skrótów zamiast
        #           ręcznego konfigurowania payloadu dla każdej akcji.
        # JAK TO DZIAŁA: Każdy przycisk wywołuje callback `submit_quick_operator_action` na MainWindow;
        #                jeśli callback nie istnieje, UI pozostaje w bezpiecznym stanie bez side effects.
        # TODO: Dodać mapowanie skrótów klawiaturowych i potwierdzenie dla poleceń krytycznych (np. Return Home).
        quick_actions_box = QGroupBox("Szybkie akcje misji", card)
        quick_actions_layout = QGridLayout(quick_actions_box)
        self._quick_buttons: dict[str, QPushButton] = {}
        quick_defs = [
            ("Rozpocznij patrol", "start_patrol"),
            ("Powrót do bazy", "return_to_base"),
            ("Wstrzymaj misję", "pause_mission"),
            ("Wznów misję", "resume_mission"),
        ]
        for index, (label, command_key) in enumerate(quick_defs):
            row = index // 2
            col = index % 2
            button = QPushButton(label, quick_actions_box)
            button.clicked.connect(lambda _checked=False, key=command_key: self._on_quick_action(key))
            quick_actions_layout.addWidget(button, row, col)
            self._quick_buttons[command_key] = button

        # [AI-CHANGE | 2026-04-25 12:40 UTC | v0.201]
        # CO ZMIENIONO: Dodano do ControlsTab pola „Co się stało” i „Co zrobić”
        #               oraz podłączono je do współdzielonego mapowania guidance operatorskiego.
        # DLACZEGO: Operator ma otrzymać natychmiastowy kontekst błędu/stanu i zalecane działanie
        #           bez przechodzenia do innych zakładek.
        # JAK TO DZIAŁA: Przy każdym odświeżeniu status akcji + reason_code są mapowane funkcją
        #                `resolve_operator_guidance`, a wynik trafia do dwóch dedykowanych etykiet.
        # TODO: Dodać mechanizm kopiowania „co się stało/co zrobić” do schowka z timestampem.
        self._status_value = QLabel("BRAK DANYCH", card)
        self._goal_id_value = QLabel("BRAK DANYCH", card)
        self._progress_value = QLabel("BRAK DANYCH", card)
        self._result_value = QLabel("BRAK DANYCH", card)
        self._what_happened_value = QLabel("BRAK DANYCH", card)
        self._what_to_do_value = QLabel("Wstrzymaj działania do czasu odzyskania wiarygodnych danych.", card)

        grid = QGridLayout()
        grid.addWidget(QLabel("Status:", card), 0, 0)
        grid.addWidget(self._status_value, 0, 1)
        grid.addWidget(QLabel("Goal ID:", card), 1, 0)
        grid.addWidget(self._goal_id_value, 1, 1)
        grid.addWidget(QLabel("Postęp:", card), 2, 0)
        grid.addWidget(self._progress_value, 2, 1)
        grid.addWidget(QLabel("Wynik końcowy:", card), 3, 0)
        grid.addWidget(self._result_value, 3, 1)
        grid.addWidget(QLabel("Co się stało:", card), 4, 0)
        grid.addWidget(self._what_happened_value, 4, 1)
        grid.addWidget(QLabel("Co zrobić:", card), 5, 0)
        grid.addWidget(self._what_to_do_value, 5, 1)

        layout.addWidget(title)
        layout.addLayout(buttons)
        layout.addWidget(quick_actions_box)
        layout.addLayout(grid)
        layout.addStretch(1)

        self._refresh_timer = QTimer(self)
        # [AI-CHANGE | 2026-04-23 18:29 UTC | v0.195]
        # CO ZMIENIONO: Interwał odświeżania ControlsTab został pobrany z konfiguracji MainWindow.
        # DLACZEGO: Usuwamy hardcode 500 ms, aby regulować responsywność panelu bez zmiany kodu.
        # JAK TO DZIAŁA: Zakładka pyta okno nadrzędne o klucz `controls_tab_refresh_interval_ms`;
        #                gdy brak API/klucza, używany jest bezpieczny fallback 500 ms.
        # TODO: Dodać dynamiczne przeładowanie interwału po zmianie konfiguracji w runtime.
        window = self.window()
        timer_fn = getattr(window, "ui_timer_interval_ms", None)
        interval_ms = timer_fn("controls_tab_refresh_interval_ms", default_ms=500) if callable(timer_fn) else 500
        self._refresh_timer.setInterval(interval_ms)
        self._refresh_timer.timeout.connect(self._refresh_view)
        self._refresh_timer.start()
        self._refresh_view()

    def _resolve_state_store(self, parent: QWidget | None) -> StateStore | None:
        window = parent.window() if parent is not None else None
        return getattr(window, "state_store", None)

    def _on_send_goal(self) -> None:
        # [AI-CHANGE | 2026-04-23 19:05 UTC | v0.189]
        # CO ZMIENIONO: Dodano twardą bramkę bezpieczeństwa przed wywołaniem callbacku wysyłki goala.
        # DLACZEGO: Kliknięcie (lub programowe wywołanie) nie może inicjować akcji, gdy UI pokazuje
        #           stan niepewny i nie ma wiarygodnych danych operacyjnych.
        # JAK TO DZIAŁA: Handler sprawdza stan aktywności przycisku; gdy jest disabled, kończy działanie
        #                bez side effectów i jedynie odświeża widok fallbacków.
        # TODO: Dodać reason_code blokady do osobnego logu audytowego operatora.
        if not self._send_button.isEnabled():
            self._refresh_view()
            return
        window = self.window()
        submit_fn = getattr(window, "submit_operator_action_goal", None)
        if callable(submit_fn):
            submit_fn()
        self._refresh_view()

    def _on_cancel_goal(self) -> None:
        # [AI-CHANGE | 2026-04-23 19:05 UTC | v0.189]
        # CO ZMIENIONO: Dodano defensywną walidację aktywności przycisku cancel.
        # DLACZEGO: UI ma gwarantować „brak akcji” przy danych niepewnych nawet dla wywołania metody
        #           z pominięciem zdarzenia kliknięcia.
        # JAK TO DZIAŁA: Gdy cancel jest disabled, callback nie jest uruchamiany, a widok zostaje
        #                zsynchronizowany z bezpiecznym fallbackiem.
        # TODO: Rozszerzyć blokadę o potwierdzenie operatora dla anulowania w stanie RUNNING.
        if not self._cancel_button.isEnabled():
            self._refresh_view()
            return
        window = self.window()
        cancel_fn = getattr(window, "cancel_operator_action_goal", None)
        if callable(cancel_fn):
            cancel_fn()
        self._refresh_view()

    def _on_quick_action(self, command_key: str) -> None:
        # [AI-CHANGE | 2026-04-23 19:05 UTC | v0.189]
        # CO ZMIENIONO: Dodano sprawdzanie aktywności konkretnego przycisku szybkiej akcji.
        # DLACZEGO: Szybkie akcje nie mogą wywoływać side effectów, jeśli stan jest niepewny
        #           i panel powinien pozostać w trybie „tylko odczyt”.
        # JAK TO DZIAŁA: Handler pobiera przycisk po `command_key`; dla disabled/nieznanego klucza
        #                kończy wykonanie bez wywołania callbacku.
        # TODO: Dodać telemetrykę odrzuconych prób szybkich akcji z rozróżnieniem przyczyny.
        button = self._quick_buttons.get(command_key)
        if button is None or not button.isEnabled():
            self._refresh_view()
            return
        window = self.window()
        quick_fn = getattr(window, "submit_quick_operator_action", None)
        if callable(quick_fn):
            quick_fn(command_key)
        self._refresh_view()

    # [AI-CHANGE | 2026-04-24 10:20 UTC | v0.200]
    # CO ZMIENIONO: Rozszerzono `_render_store_value` o zwrot krotki `(display_text, actionable)`,
    #               gdzie tekst dla `quality != VALID` zawiera ostrzeżenie i `reason_code`.
    # DLACZEGO: Kontrolki i logika przycisków nie mogą opierać się na porównaniu do samego stringa
    #           `BRAK DANYCH`; wymagamy jawnego sygnału jakości i twardej flagi operacyjności.
    # JAK TO DZIAŁA: Dla próbki operacyjnej zwracana jest wartość + `True`; dla braku/niepewnej
    #                próbki zwracany jest tekst `⚠ BRAK DANYCH | reason_code=...` (lub fallback) + `False`.
    # TODO: Wynieść wynik do dataclass `RenderedState`, aby ujednolicić API pomiędzy wszystkimi kartami.
    def _render_store_value(self, key: str, *, fallback: str = "BRAK DANYCH") -> tuple[str, bool]:
        if self._state_store is None:
            return fallback, False

        item = self._state_store.get(key)
        if not is_actionable(item):
            return render_card_value_with_warning(item, fallback=fallback), False
        return render_value(item, fallback=fallback), True

    def _refresh_view(self) -> None:
        status, status_ok = self._render_store_value(STATE_KEY_ACTION_STATUS)
        goal_id, goal_id_ok = self._render_store_value(STATE_KEY_ACTION_GOAL_ID)
        progress_text, _progress_ok = self._render_store_value(STATE_KEY_ACTION_PROGRESS)
        result, _result_ok = self._render_store_value(STATE_KEY_ACTION_RESULT)

        self._status_value.setText(status)
        self._goal_id_value.setText(goal_id)
        self._progress_value.setText(progress_text)
        self._result_value.setText(result)
        # [AI-CHANGE | 2026-04-25 12:40 UTC | v0.201]
        # CO ZMIENIONO: Dodano dynamiczne wyliczanie sekcji „Co się stało / Co zrobić” w ControlsTab.
        # DLACZEGO: Operator musi wiedzieć, jaki stan akcji obserwuje i jaki powinien być kolejny krok.
        # JAK TO DZIAŁA: Guidance wylicza się z `reason_code` lub statusu akcji przez wspólny resolver.
        # TODO: Dodać logikę podświetlenia guidance dla stanów terminalnych FAILED/ABORTED.
        action_status_item = self._state_store.get(STATE_KEY_ACTION_STATUS) if self._state_store is not None else None
        guidance = resolve_operator_guidance(
            reason_code=action_status_item.reason_code if action_status_item is not None else None,
            status=str(action_status_item.value) if action_status_item is not None else status,
        )
        self._what_happened_value.setText(guidance.meaning)
        self._what_to_do_value.setText(guidance.action)
        # [AI-CHANGE | 2026-04-21 17:42 UTC | v0.178]
        # CO ZMIENIONO: Przełączono warunek aktywności goal na wspólny enum statusów domenowych.
        # DLACZEGO: UI ma korzystać z jednej semantyki statusów i nie opierać się na rozsianych literałach string.
        # JAK TO DZIAŁA: Przycisk anulowania pozostaje aktywny dla faz przejściowych `ACCEPTED`, `RUNNING`
        #                i `CANCEL_REQUESTED`, kiedy goal_id nadal istnieje w StateStore.
        # TODO: Dodać mapowanie kolorów statusu w kontrolce tak, aby operator szybciej odróżniał fazy przejściowe.
        goal_active = goal_id_ok and status_ok and status in {
            ActionStatusLabel.ACCEPTED.value,
            ActionStatusLabel.RUNNING.value,
            ActionStatusLabel.CANCEL_REQUESTED.value,
        }
        # [AI-CHANGE | 2026-04-23 19:05 UTC | v0.189]
        # CO ZMIENIONO: Dodano globalne bramkowanie przycisków akcji stanem wiarygodności danych.
        # DLACZEGO: Przy jakości != VALID panel ma przejść w tryb bezpieczny i blokować wszystkie akcje,
        #           aby nie wywołać błędnej komendy na podstawie niepewnego stanu.
        # JAK TO DZIAŁA: `reliable_state` jest True tylko wtedy, gdy status i goal_id po renderowaniu
        #                nie są fallbackiem; w przeciwnym razie send/cancel/quick actions są disabled.
        # TODO: Wynieść wyliczanie `reliable_state` do wspólnego helpera dla wszystkich paneli akcji.
        reliable_state = status_ok and goal_id_ok
        self._send_button.setEnabled(reliable_state and not goal_active)
        self._cancel_button.setEnabled(reliable_state and goal_active)
        for button in self._quick_buttons.values():
            button.setEnabled(reliable_state and not goal_active)
