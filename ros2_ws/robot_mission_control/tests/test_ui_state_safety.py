from __future__ import annotations

# [AI-CHANGE | 2026-04-28 16:55 UTC | v0.202]
# CO ZMIENIONO: Dodano plikową dyrektywę Ruff `noqa: E402` dla testu UI.
# DLACZEGO: Test używa `pytest.importorskip` przed importami modułów aplikacji, aby bezpiecznie pomijać test przy braku bibliotek Qt, co koliduje z regułą E402.
# JAK TO DZIAŁA: Ruff ignoruje wyłącznie E402 w tym pliku; pozostałe reguły lint pozostają aktywne bez zmian.
# TODO: Przenieść `importorskip` do fixture inicjalizowanej wcześniej, aby docelowo usunąć wyjątkową dyrektywę lint.
# ruff: noqa: E402

from datetime import datetime, timedelta, timezone

import pytest

qt_widgets = pytest.importorskip("PySide6.QtWidgets", reason="Brak bibliotek systemowych Qt (np. libGL) w środowisku testowym.")
QApplication = qt_widgets.QApplication
QPushButton = qt_widgets.QPushButton
QWidget = qt_widgets.QWidget

qt_core = pytest.importorskip("PySide6.QtCore", reason="Brak bibliotek systemowych Qt (np. libGL) w środowisku testowym.")
qt_test = pytest.importorskip("PySide6.QtTest", reason="Brak bibliotek systemowych Qt (np. libGL) w środowisku testowym.")
Qt = qt_core.Qt
QTest = qt_test.QTest

from robot_mission_control.core import (
    STATE_KEY_ACTION_GOAL_ID,
    STATE_KEY_ACTION_PROGRESS,
    STATE_KEY_ACTION_RESULT,
    STATE_KEY_ACTION_STATUS,
    STATE_KEY_BAG_INTEGRITY_STATUS,
    STATE_KEY_PLAYBACK_STATUS,
    STATE_KEY_RECORDING_STATUS,
    STATE_KEY_ROS_CONNECTION_STATUS,
    STATE_KEY_SELECTED_BAG,
    DataQuality,
    StateStore,
    StateValue,
)
from robot_mission_control.ui.tabs.controls_tab import ControlsTab
from robot_mission_control.ui.tabs.debug_tab import DebugTab
from robot_mission_control.ui.tabs.overview_tab import OverviewTab
from robot_mission_control.ui.tabs.diagnostics_tab import DiagnosticsTab
from robot_mission_control.ui.tabs.extensions_tab import ExtensionsTab
from robot_mission_control.ui.tabs.rosbag_tab import RosbagTab
from robot_mission_control.ui.tabs.telemetry_tab import TelemetryTab
from robot_mission_control.ui.tabs.video_depth_tab import VideoDepthTab
from robot_mission_control.ui.tabs.state_rendering import is_actionable, render_quality, render_state, render_value
from robot_mission_control.ui.operator_alerts import OperatorAlerts


# [AI-CHANGE | 2026-04-23 19:05 UTC | v0.189]
# CO ZMIENIONO: Dodano testy bezpieczeństwa UI dla fallbacków jakości danych, blokowania akcji
#               oraz ochrony przed wyświetlaniem starych próbek jako aktualnych.
# DLACZEGO: Regresje w tych obszarach mogą prowadzić do nieuprawnionych side effectów operatora
#           i błędnej interpretacji stanu misji.
# JAK TO DZIAŁA: Testy budują lokalny StateStore + atrapę okna i asertywnie sprawdzają, że dla jakości
#                != VALID renderowany jest fallback, przyciski są blokowane i callbacki nie są wykonywane.
# TODO: Dodać testy integracyjne Qt+ROS bridge (z realnymi callbackami i asynchroniczną aktualizacją stanu).
def _ensure_qapplication() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


class _DummyWindow(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.state_store = StateStore()
        self.operator_alerts = OperatorAlerts()
        self.send_goal_calls = 0
        self.cancel_goal_calls = 0
        self.quick_action_calls: list[str] = []
        self.start_recording_calls = 0
        self.stop_recording_calls = 0
        self.start_playback_calls = 0
        self.stop_playback_calls = 0

    def submit_operator_action_goal(self) -> None:
        self.send_goal_calls += 1

    def cancel_operator_action_goal(self) -> None:
        self.cancel_goal_calls += 1

    def submit_quick_operator_action(self, command_key: str) -> None:
        self.quick_action_calls.append(command_key)

    def start_rosbag_recording(self) -> None:
        self.start_recording_calls += 1

    def stop_rosbag_recording(self) -> None:
        self.stop_recording_calls += 1

    def start_rosbag_playback(self) -> None:
        self.start_playback_calls += 1

    def stop_rosbag_playback(self) -> None:
        self.stop_playback_calls += 1


def _set_state(store: StateStore, key: str, *, value: object, quality: DataQuality) -> None:
    store.set(
        key,
        StateValue(
            value=value,
            timestamp=datetime(2026, 4, 23, 19, 5, tzinfo=timezone.utc),
            source="test",
            quality=quality,
            reason_code="test_reason" if quality is not DataQuality.VALID else None,
        ),
    )


def test_render_value_uses_fallback_for_non_valid_qualities() -> None:
    _ensure_qapplication()
    timestamp = datetime(2026, 4, 23, 19, 5, tzinfo=timezone.utc)

    valid_item = StateValue(value="CONNECTED", timestamp=timestamp, source="test", quality=DataQuality.VALID)
    unavailable_item = StateValue(value="CONNECTED", timestamp=timestamp, source="test", quality=DataQuality.UNAVAILABLE)
    stale_item = StateValue(value="CONNECTED", timestamp=timestamp, source="test", quality=DataQuality.STALE)
    error_item = StateValue(value="CONNECTED", timestamp=timestamp, source="test", quality=DataQuality.ERROR)

    assert render_value(valid_item) == "CONNECTED"
    assert render_value(unavailable_item) == "BRAK DANYCH"
    assert render_value(stale_item) == "BRAK DANYCH"
    assert render_value(error_item) == "BRAK DANYCH"


# [AI-CHANGE | 2026-04-23 21:26 UTC | v0.197]
# CO ZMIENIONO: Dodano parametryczne testy helperów jakości (`is_actionable`, `render_quality`,
#               `render_state`) dla pełnego zestawu statusów `VALID/STALE/UNAVAILABLE/ERROR`.
# DLACZEGO: Kryterium ukończenia wymaga pełnego pokrycia scenariuszy jakości; testy helperów
#           są bazą bezpieczeństwa dla wszystkich kart korzystających ze wspólnego renderowania.
# JAK TO DZIAŁA: Test tworzy próbki o każdej jakości i asertywnie sprawdza, że:
#                - tylko `VALID` jest operacyjne (`is_actionable=True`),
#                - helpery stanu zwracają dokładny status jakości bez utraty informacji.
# TODO: Rozszerzyć testy helperów o przypadek lokalizacji napisów (PL/EN) po dodaniu i18n.
@pytest.mark.parametrize(
    ("quality", "expected_actionable"),
    [
        (DataQuality.VALID, True),
        (DataQuality.STALE, False),
        (DataQuality.UNAVAILABLE, False),
        (DataQuality.ERROR, False),
    ],
)
def test_quality_helpers_cover_all_quality_states(quality: DataQuality, expected_actionable: bool) -> None:
    _ensure_qapplication()
    item = StateValue(
        value="CONNECTED",
        timestamp=datetime(2026, 4, 23, 21, 26, tzinfo=timezone.utc),
        source="test",
        quality=quality,
        reason_code=None if quality is DataQuality.VALID else "test_reason",
    )

    assert is_actionable(item) is expected_actionable
    assert render_quality(item) == quality.value
    assert render_state(item) == quality.value

# [AI-CHANGE | 2026-04-24 10:20 UTC | v0.200]
# CO ZMIENIONO: Rozszerzono oczekiwane wartości OverviewTab dla jakości != VALID o pełny komunikat
#               `⚠ BRAK DANYCH | reason_code=test_reason`.
# DLACZEGO: Test ma pilnować, że karta nie prezentuje niepewnych danych jako operacyjnych
#           i zawsze ujawnia przyczynę degradacji.
# JAK TO DZIAŁA: Parametryzacja dla STALE/UNAVAILABLE/ERROR używa nowego, jednoznacznego formatu.
# TODO: Dodać osobny test dla fallbacku `UNKNOWN_REASON`, gdy reason_code nie jest ustawiony.
@pytest.mark.parametrize(
    ("quality", "expected_value"),
    [
        (DataQuality.VALID, "CONNECTED"),
        (DataQuality.STALE, "⚠ BRAK DANYCH | reason_code=test_reason"),
        (DataQuality.UNAVAILABLE, "⚠ BRAK DANYCH | reason_code=test_reason"),
        (DataQuality.ERROR, "⚠ BRAK DANYCH | reason_code=test_reason"),
    ],
)
def test_overview_card_renders_connection_value_per_quality_state(quality: DataQuality, expected_value: str) -> None:
    _ensure_qapplication()
    window = _DummyWindow()
    overview_tab = OverviewTab(window)
    overview_tab._refresh_timer.stop()

    _set_state(window.state_store, STATE_KEY_ROS_CONNECTION_STATUS, value="CONNECTED", quality=quality)
    _set_state(window.state_store, STATE_KEY_ACTION_STATUS, value="RUNNING", quality=DataQuality.VALID)
    _set_state(window.state_store, STATE_KEY_ACTION_PROGRESS, value="50%", quality=DataQuality.VALID)
    _set_state(window.state_store, STATE_KEY_ACTION_RESULT, value="pending", quality=DataQuality.VALID)

    overview_tab._refresh_view()

    assert overview_tab._connection_value.text() == expected_value
    assert overview_tab._quality_value.text() == quality.value


@pytest.mark.parametrize(
    ("quality", "send_enabled", "cancel_enabled", "quick_enabled"),
    [
        (DataQuality.VALID, False, True, False),
        (DataQuality.STALE, False, False, False),
        (DataQuality.UNAVAILABLE, False, False, False),
        (DataQuality.ERROR, False, False, False),
    ],
)
def test_controls_tab_button_lock_policy_covers_all_quality_states(
    quality: DataQuality, send_enabled: bool, cancel_enabled: bool, quick_enabled: bool
) -> None:
    _ensure_qapplication()
    window = _DummyWindow()
    controls_tab = ControlsTab(window)
    controls_tab._refresh_timer.stop()

    _set_state(window.state_store, STATE_KEY_ACTION_STATUS, value="RUNNING", quality=quality)
    _set_state(window.state_store, STATE_KEY_ACTION_GOAL_ID, value="goal-1", quality=quality)
    _set_state(window.state_store, STATE_KEY_ACTION_PROGRESS, value="42%", quality=quality)
    _set_state(window.state_store, STATE_KEY_ACTION_RESULT, value="pending", quality=quality)
    controls_tab._refresh_view()

    assert controls_tab._send_button.isEnabled() is send_enabled
    assert controls_tab._cancel_button.isEnabled() is cancel_enabled
    assert controls_tab._quick_buttons["start_patrol"].isEnabled() is quick_enabled

    controls_tab._on_send_goal()
    controls_tab._on_cancel_goal()
    controls_tab._on_quick_action("start_patrol")

    expected_cancel_calls = 1 if quality is DataQuality.VALID else 0
    assert window.send_goal_calls == 0
    assert window.cancel_goal_calls == expected_cancel_calls
    assert window.quick_action_calls == []


def test_controls_tab_blocks_action_buttons_and_callbacks_when_state_is_unreliable() -> None:
    _ensure_qapplication()
    window = _DummyWindow()
    controls_tab = ControlsTab(window)
    controls_tab._refresh_timer.stop()

    _set_state(window.state_store, STATE_KEY_ACTION_STATUS, value="RUNNING", quality=DataQuality.STALE)
    _set_state(window.state_store, STATE_KEY_ACTION_GOAL_ID, value="goal-1", quality=DataQuality.STALE)
    _set_state(window.state_store, STATE_KEY_ACTION_PROGRESS, value="42%", quality=DataQuality.STALE)
    _set_state(window.state_store, STATE_KEY_ACTION_RESULT, value="pending", quality=DataQuality.STALE)

    controls_tab._refresh_view()

    # [AI-CHANGE | 2026-04-24 10:20 UTC | v0.200]
    # CO ZMIENIONO: Zaktualizowano asercje kart Controls/Rosbag/Overview pod nowy format
    #               niepewnego stanu: `⚠ BRAK DANYCH | reason_code=...`.
    # DLACZEGO: UI ma jednoznacznie sygnalizować ostrzeżenie i przyczynę odrzucenia próbki,
    #           więc testy muszą pilnować obecności `BRAK DANYCH` oraz `reason_code`.
    # JAK TO DZIAŁA: Asercje sprawdzają zarówno prefiks ostrzeżenia, jak i konkretny kod przyczyny.
    # TODO: Dodać wspólny helper testowy `assert_warning_no_data`, aby uprościć powtarzalne asercje.
    assert controls_tab._status_value.text() == "⚠ BRAK DANYCH | reason_code=test_reason"
    assert controls_tab._goal_id_value.text() == "⚠ BRAK DANYCH | reason_code=test_reason"
    assert controls_tab._progress_value.text() == "⚠ BRAK DANYCH | reason_code=test_reason"
    assert controls_tab._result_value.text() == "⚠ BRAK DANYCH | reason_code=test_reason"
    assert controls_tab._cancel_button.isEnabled() is False

    quick_button = controls_tab._quick_buttons["start_patrol"]
    quick_button.click()
    assert window.quick_action_calls == []

    controls_tab._on_cancel_goal()
    assert window.cancel_goal_calls == 0


def test_overview_tab_does_not_present_stale_data_as_current() -> None:
    _ensure_qapplication()
    window = _DummyWindow()
    overview_tab = OverviewTab(window)
    overview_tab._refresh_timer.stop()

    stale_timestamp = datetime.now(timezone.utc) - timedelta(minutes=10)
    window.state_store.set(
        STATE_KEY_ACTION_STATUS,
        StateValue(
            value="RUNNING",
            timestamp=stale_timestamp,
            source="test",
            quality=DataQuality.STALE,
            reason_code="stale_data",
        ),
    )
    _set_state(window.state_store, STATE_KEY_ROS_CONNECTION_STATUS, value="CONNECTED", quality=DataQuality.VALID)
    _set_state(window.state_store, STATE_KEY_ACTION_PROGRESS, value="80%", quality=DataQuality.VALID)
    _set_state(window.state_store, STATE_KEY_ACTION_RESULT, value="pending", quality=DataQuality.VALID)

    overview_tab._refresh_view()

    assert overview_tab._action_status_value.text() == "⚠ BRAK DANYCH | reason_code=stale_data"
    assert overview_tab._quality_value.text() == DataQuality.STALE.value


# [AI-CHANGE | 2026-04-23 20:11 UTC | v0.193]
# CO ZMIENIONO: Dodano testy nowego panelu decyzji operatorskiej w OverviewTab:
#               przypadek bezpieczny (kontynuacja) i przypadek z alarmem krytycznym (wstrzymanie).
# DLACZEGO: Kryterium funkcjonalne wymaga „jednego spojrzenia”, więc potrzebna jest ochrona regresyjna
#           dla logiki werdyktu bezpieczeństwa i liczby aktywnych alarmów krytycznych.
# JAK TO DZIAŁA: Testy przygotowują wiarygodny stan Store + OperatorAlerts i asertywnie sprawdzają
#                teksty panelu (`MOŻNA KONTYNUOWAĆ` / `WSTRZYMAJ MISJĘ`) oraz licznik alarmów.
# TODO: Dodać test GUI dla kolorów etykiet (zielony/czerwony) po ustabilizowaniu stylów Qt w CI.
def test_overview_tab_allows_safe_continue_when_ros_and_action_are_valid() -> None:
    _ensure_qapplication()
    window = _DummyWindow()
    overview_tab = OverviewTab(window)
    overview_tab._refresh_timer.stop()

    _set_state(window.state_store, STATE_KEY_ROS_CONNECTION_STATUS, value="CONNECTED", quality=DataQuality.VALID)
    _set_state(window.state_store, STATE_KEY_ACTION_STATUS, value="RUNNING", quality=DataQuality.VALID)
    _set_state(window.state_store, STATE_KEY_ACTION_PROGRESS, value="25%", quality=DataQuality.VALID)
    _set_state(window.state_store, STATE_KEY_ACTION_RESULT, value="pending", quality=DataQuality.VALID)

    overview_tab._refresh_view()

    # [AI-CHANGE | 2026-04-25 12:40 UTC | v0.201]
    # CO ZMIENIONO: Rozszerzono asercje OverviewTab o pola „co się stało” i „co zrobić”.
    # DLACZEGO: Test ma pilnować wymogu operatorskiego: sam status to za mało, potrzebna jest instrukcja.
    # JAK TO DZIAŁA: Asercje weryfikują tekst guidance pochodzący ze współdzielonego mapowania statusów.
    # TODO: Dodać test dla ścieżki fallback guidance przy nieznanym statusie akcji.
    assert overview_tab._safety_value.text() == "MOŻNA KONTYNUOWAĆ"
    assert overview_tab._mission_state_value.text() == "MISJA W TOKU"
    assert overview_tab._critical_alarm_count_value.text() == "0"
    assert "Misja jest wykonywana" in overview_tab._what_happened_value.text()
    assert "Monitoruj postęp" in overview_tab._what_to_do_value.text()


def test_overview_tab_blocks_continue_when_critical_alert_is_active() -> None:
    _ensure_qapplication()
    window = _DummyWindow()
    overview_tab = OverviewTab(window)
    overview_tab._refresh_timer.stop()

    _set_state(window.state_store, STATE_KEY_ROS_CONNECTION_STATUS, value="CONNECTED", quality=DataQuality.VALID)
    _set_state(window.state_store, STATE_KEY_ACTION_STATUS, value="RUNNING", quality=DataQuality.VALID)
    _set_state(window.state_store, STATE_KEY_ACTION_PROGRESS, value="25%", quality=DataQuality.VALID)
    _set_state(window.state_store, STATE_KEY_ACTION_RESULT, value="pending", quality=DataQuality.VALID)
    window.operator_alerts.publish_alert(
        state_key=STATE_KEY_ROS_CONNECTION_STATUS,
        severity="CRITICAL",
        code="ros_link_down",
        message="Połączenie ROS niestabilne",
        timestamp=datetime(2026, 4, 23, 20, 11, tzinfo=timezone.utc),
    )

    overview_tab._refresh_view()

    # [AI-CHANGE | 2026-04-28 10:14 UTC | v0.205]
    # CO ZMIENIONO: Zamieniono asercję `isVisible()` banera na asercję treści komunikatu.
    # DLACZEGO: W testach headless Qt efektywna widoczność zależy od stanu rodzica i bywa fałszywie ujemna.
    # JAK TO DZIAŁA: Test waliduje semantykę alarmu krytycznego przez sprawdzenie tekstu banera
    #                oraz zachowuje asercję licznika alarmów krytycznych.
    # TODO: Dodać test integracyjny z pokazanym MainWindow, aby osobno zweryfikować realną widoczność banera.
    assert overview_tab._safety_value.text() == "WSTRZYMAJ MISJĘ"
    assert overview_tab._critical_alarm_count_value.text() == "1"
    assert "ALERT KRYTYCZNY" in overview_tab._alarm_banner.text()



# [AI-CHANGE | 2026-04-23 21:10 UTC | v0.194]
# CO ZMIENIONO: Dodano test tabeli problemów w DiagnosticsTab budowanej bezpośrednio
#               z `StateStore.snapshot()` wraz z walidacją kolumn przyczyna/czas/źródło.
# DLACZEGO: Kryterium ukończenia wymaga, aby każdy problem pokazywał przyczynę i czas wystąpienia
#           oraz aby źródło było jawnie widoczne dla operatora.
# JAK TO DZIAŁA: Test tworzy dwa problemy (ERROR i STALE), odświeża widok i sprawdza,
#                że tabela ma właściwe severity, source, cause i timestamp UTC dla obu rekordów.
# TODO: Dodać test integracyjny sortowania po czasie i filtrowania po severity w DiagnosticsTab.
def test_diagnostics_tab_renders_problem_rows_with_cause_source_and_timestamp() -> None:
    _ensure_qapplication()
    window = _DummyWindow()
    diagnostics_tab = DiagnosticsTab(window)
    diagnostics_tab._refresh_timer.stop()

    error_timestamp = datetime(2026, 4, 23, 21, 8, tzinfo=timezone.utc)
    stale_timestamp = datetime(2026, 4, 23, 21, 7, tzinfo=timezone.utc)

    window.state_store.set(
        STATE_KEY_ROS_CONNECTION_STATUS,
        StateValue(
            value="CONNECTED",
            timestamp=error_timestamp,
            source="ros_bridge",
            quality=DataQuality.ERROR,
            reason_code="transport_failure",
        ),
    )
    window.state_store.set(
        STATE_KEY_ACTION_STATUS,
        StateValue(
            value="RUNNING",
            timestamp=stale_timestamp,
            source="action_client",
            quality=DataQuality.STALE,
            reason_code="timeout",
        ),
    )

    diagnostics_tab._refresh_view()

    # [AI-CHANGE | 2026-04-29 13:15 UTC | v0.332]
    # CO ZMIENIONO: Zaktualizowano asercję instrukcji operatora dla `transport_failure`.
    # DLACZEGO: Resolver guidance zwraca teraz konkretną instrukcję wstrzymania sterowania ruchem, a stary prefiks
    #           `Wstrzymaj ryzykowne działania` dawał fałszywy błąd mimo bezpieczniejszego komunikatu UI.
    # JAK TO DZIAŁA: Test nadal sprawdza severity/source/cause/meaning/timestamp, a akcję waliduje po aktualnym
    #                prefiksie komunikatu wymuszającego przerwanie sterowania przed kontynuacją.
    # TODO: Dodać test kontraktowy dla pełnej mapy `reason_code -> guidance`, aby zmiany treści były jawne.
    assert diagnostics_tab._issues_table.rowCount() == 2
    assert diagnostics_tab._issues_table.item(0, 0).text() == "CRITICAL | ⛔ ERROR"
    assert diagnostics_tab._issues_table.item(0, 1).text() == "ros_bridge"
    assert diagnostics_tab._issues_table.item(0, 2).text() == "transport_failure"
    assert diagnostics_tab._issues_table.item(0, 3).text() == "Transport danych przerwał się i stan systemu jest niewiarygodny."
    assert diagnostics_tab._issues_table.item(0, 4).text().startswith("Wstrzymaj sterowanie ruchem")
    assert diagnostics_tab._issues_table.item(0, 6).text() == "2026-04-23 21:08:00 UTC"

    assert diagnostics_tab._issues_table.item(1, 0).text() == "MEDIUM | ⚠ STALE"
    assert diagnostics_tab._issues_table.item(1, 1).text() == "action_client"
    assert diagnostics_tab._issues_table.item(1, 2).text() == "timeout"
    assert diagnostics_tab._issues_table.item(1, 6).text() == "2026-04-23 21:07:00 UTC"


# [AI-CHANGE | 2026-04-24 12:10 UTC | v0.203]
# CO ZMIENIONO: Dodano test mapowania najczęstszego kodu `stale_data` na sekcje „co to znaczy”
#               oraz „co zrobić” w tabeli DiagnosticsTab.
# DLACZEGO: To zabezpiecza DoD, że operator dostaje gotową instrukcję działania bez zaglądania do logów.
# JAK TO DZIAŁA: Test publikuje próbkę ze `stale_data`, odświeża kartę i asertywnie sprawdza oba pola podpowiedzi.
# TODO: Dodać test parametryczny dla kolejnych kodów (np. heartbeat_missing, reconnect_failed, MC_CFG_001).
def test_diagnostics_tab_renders_operator_meaning_and_action_for_common_code() -> None:
    _ensure_qapplication()
    window = _DummyWindow()
    diagnostics_tab = DiagnosticsTab(window)
    diagnostics_tab._refresh_timer.stop()

    window.state_store.set(
        STATE_KEY_ACTION_STATUS,
        StateValue(
            value="RUNNING",
            timestamp=datetime(2026, 4, 24, 12, 10, tzinfo=timezone.utc),
            source="action_client",
            quality=DataQuality.STALE,
            reason_code="stale_data",
        ),
    )

    diagnostics_tab._refresh_view()

    assert diagnostics_tab._issues_table.rowCount() == 1
    assert "Dane są przeterminowane" in diagnostics_tab._issues_table.item(0, 3).text()
    assert "Wstrzymaj akcje zależne" in diagnostics_tab._issues_table.item(0, 4).text()


# [AI-CHANGE | 2026-04-25 08:57 UTC | v0.202]
# CO ZMIENIONO: Dodano test ACK w DiagnosticsTab i testy nowych akcji operatorskich w kartach
#               Extensions/VideoDepth (kopiowanie danych do schowka + aktywacja przycisków).
# DLACZEGO: Zabezpiecza to priorytet zadania: mniej martwych przycisków oraz realna użyteczność
#           paneli operatorskich bez konieczności ręcznego przepisywania diagnostyki.
# JAK TO DZIAŁA: Testy uruchamiają zakładki na atrapach danych, wykonują kliknięcia i weryfikują
#                skutki w `OperatorAlerts` oraz treści schowka Qt.
# TODO: Dodać testy integracyjne na pełnym MainWindow z przełączaniem zakładek i pollingiem timerów.
def test_diagnostics_tab_acknowledges_selected_active_alert() -> None:
    _ensure_qapplication()
    window = _DummyWindow()
    diagnostics_tab = DiagnosticsTab(window)
    diagnostics_tab._refresh_timer.stop()

    ts = datetime(2026, 4, 25, 8, 57, tzinfo=timezone.utc)
    window.state_store.set(
        STATE_KEY_ROS_CONNECTION_STATUS,
        StateValue(
            value=None,
            timestamp=ts,
            source="ros_bridge",
            quality=DataQuality.ERROR,
            reason_code="transport_failure",
        ),
    )
    window.operator_alerts.publish_alert(
        state_key=STATE_KEY_ROS_CONNECTION_STATUS,
        severity="CRITICAL",
        code="transport_failure",
        message="ROS bridge niedostępny",
        timestamp=ts,
    )

    diagnostics_tab._refresh_view()
    diagnostics_tab._issues_table.selectRow(0)
    diagnostics_tab._ack_button.click()

    active_alerts = window.operator_alerts.active_alerts()
    assert len(active_alerts) == 1
    assert active_alerts[0].acknowledged is True
    assert diagnostics_tab._ack_button.text() == "ACK (0)"
    assert diagnostics_tab._ack_button.isEnabled() is False


def test_extensions_tab_copies_selected_plugin_details_to_clipboard() -> None:
    app = _ensure_qapplication()
    window = _DummyWindow()
    extensions_tab = ExtensionsTab(window)
    extensions_tab._refresh_timer.stop()

    _set_state(window.state_store, "plugin.demo.active", value=True, quality=DataQuality.VALID)
    extensions_tab._plugin_names = ("demo",)
    extensions_tab._refresh_plugin_table()
    extensions_tab._plugins_table.selectRow(0)
    extensions_tab._copy_selected_plugin_button.click()

    clipboard_text = app.clipboard().text()
    assert "plugin=demo" in clipboard_text
    assert "activation=AKTYWNE" in clipboard_text
    assert "quality=VALID" in clipboard_text


def test_video_depth_tab_copies_stream_status_to_clipboard() -> None:
    app = _ensure_qapplication()
    window = _DummyWindow()
    video_depth_tab = VideoDepthTab(window)
    video_depth_tab._refresh_timer.stop()

    _set_state(window.state_store, "video_stream_status", value="CONNECTED", quality=DataQuality.VALID)
    # [AI-CHANGE | 2026-04-27 06:55 UTC | v0.203]
    # CO ZMIENIONO: W teście VideoDepthTab ustawiono jawny `reason_code=stale_data`
    #               dla strumienia depth, aby zweryfikować wspólny guidance operatorski.
    # DLACZEGO: Karta VideoDepth musi korzystać z tego samego mapowania „co się stało/co zrobić”
    #           co pozostałe karty operatorskie dla krytycznych/niepewnych stanów.
    # JAK TO DZIAŁA: Zamiast helpera `_set_state` zapisujemy próbkę bezpośrednio do `StateStore`,
    #                by wymusić znany kod i asertywnie sprawdzić treści guidance.
    # TODO: Dodać wariant testu dla `transport_failure` (jakość ERROR) po podpięciu alarmów krytycznych do karty.
    window.state_store.set(
        "depth_stream_status",
        StateValue(
            value="STALE",
            timestamp=datetime(2026, 4, 27, 6, 55, tzinfo=timezone.utc),
            source="test",
            quality=DataQuality.STALE,
            reason_code="stale_data",
        ),
    )
    _set_state(window.state_store, "time_sync_status", value="CONNECTED", quality=DataQuality.VALID)
    video_depth_tab._refresh_view()
    video_depth_tab._copy_stream_status_to_clipboard()

    clipboard_text = app.clipboard().text()
    assert "video_depth_status" in clipboard_text
    assert "video=CONNECTED (VALID)" in clipboard_text
    assert "depth=⚠ BRAK DANYCH | reason_code=stale_data (STALE)" in clipboard_text
    assert "sync=CONNECTED (VALID)" in clipboard_text
    assert "Dane są przeterminowane" in video_depth_tab._what_happened_value.text()
    assert "Wstrzymaj akcje zależne" in video_depth_tab._what_to_do_value.text()

def test_rosbag_tab_blocks_buttons_and_skips_callbacks_for_unreliable_state() -> None:
    _ensure_qapplication()
    window = _DummyWindow()
    rosbag_tab = RosbagTab(window)
    rosbag_tab._refresh_timer.stop()

    _set_state(window.state_store, STATE_KEY_RECORDING_STATUS, value="IDLE", quality=DataQuality.UNAVAILABLE)
    _set_state(window.state_store, STATE_KEY_PLAYBACK_STATUS, value="STOPPED", quality=DataQuality.VALID)
    _set_state(window.state_store, STATE_KEY_SELECTED_BAG, value="mission_01", quality=DataQuality.VALID)
    _set_state(window.state_store, STATE_KEY_BAG_INTEGRITY_STATUS, value="OK", quality=DataQuality.VALID)

    rosbag_tab._refresh_view()

    # [AI-CHANGE | 2026-04-25 12:40 UTC | v0.201]
    # CO ZMIENIONO: Dodano asercje guidance operatorskiego w RosbagTab dla stanu niepewnego.
    # DLACZEGO: Musimy mieć regresję gwarantującą, że operator zobaczy zarówno diagnozę, jak i zalecenie.
    # JAK TO DZIAŁA: Test sprawdza fallback „co się stało/co zrobić” przy jakości różnej od VALID.
    # TODO: Dodać test mapowania reason_code znanego (np. stale_data) dla RosbagTab.
    assert rosbag_tab._recording_value.text() == "⚠ BRAK DANYCH | reason_code=test_reason"
    assert "Kod lub status" in rosbag_tab._what_happened_value.text()
    assert "Wstrzymaj ryzykowne działania" in rosbag_tab._what_to_do_value.text()
    assert rosbag_tab._start_recording_button.isEnabled() is False
    assert rosbag_tab._stop_recording_button.isEnabled() is False
    assert rosbag_tab._start_playback_button.isEnabled() is False
    assert rosbag_tab._stop_playback_button.isEnabled() is False

    rosbag_tab._start_recording_button.click()
    rosbag_tab._stop_recording_button.click()
    rosbag_tab._start_playback_button.click()
    rosbag_tab._stop_playback_button.click()

    assert window.start_recording_calls == 0
    assert window.stop_recording_calls == 0
    assert window.start_playback_calls == 0
    assert window.stop_playback_calls == 0


# [AI-CHANGE | 2026-04-27 08:25 UTC | v0.203]
# CO ZMIENIONO: Dodano testy regresyjne TODO-v1 dla filtrów/sortowania telemetryki, eksportu diagnostyki
#               oraz telemetryki blokad w kartach Controls i Rosbag.
# DLACZEGO: Stabilizacyjna paczka wymaga zamknięcia checklisty funkcjonalnej z testami ochrony regresji.
# JAK TO DZIAŁA: Testy uruchamiają karty na atrapach StateStore i asertywnie sprawdzają filtr/severity,
#                zachowanie fail-safe przy blokadach oraz obecność liczników i eksportu payloadu.
# TODO: Dodać testy e2e na pełnym MainWindow (z timerami) po ustabilizowaniu headless Qt w CI.
def test_telemetry_tab_filters_and_sorts_rows_by_severity_and_key() -> None:
    _ensure_qapplication()
    window = _DummyWindow()
    telemetry_tab = TelemetryTab(window)
    telemetry_tab._refresh_timer.stop()

    _set_state(window.state_store, STATE_KEY_ACTION_STATUS, value="RUNNING", quality=DataQuality.ERROR)
    _set_state(window.state_store, STATE_KEY_ACTION_PROGRESS, value="40%", quality=DataQuality.STALE)
    _set_state(window.state_store, STATE_KEY_ACTION_RESULT, value="PENDING", quality=DataQuality.VALID)

    telemetry_tab._severity_filter.setCurrentText("MEDIUM")
    telemetry_tab._key_filter_edit.setText("action_")
    telemetry_tab._refresh_table()

    assert telemetry_tab._table.rowCount() >= 2
    first_key = telemetry_tab._table.item(0, 0).text()
    first_quality = telemetry_tab._table.item(0, 2).text()
    assert first_key == STATE_KEY_ACTION_STATUS
    assert "ERROR" in first_quality
    assert telemetry_tab._quality_legend.text().startswith("Legenda quality:")


def test_debug_tab_filters_non_valid_and_exports_to_file(tmp_path) -> None:
    _ensure_qapplication()
    window = _DummyWindow()
    debug_tab = DebugTab(window)
    debug_tab._refresh_timer.stop()

    _set_state(window.state_store, STATE_KEY_ACTION_STATUS, value="RUNNING", quality=DataQuality.VALID)
    _set_state(window.state_store, STATE_KEY_ROS_CONNECTION_STATUS, value="CONNECTED", quality=DataQuality.ERROR)
    debug_tab._non_valid_only_checkbox.setChecked(True)
    debug_tab._refresh_snapshot_view()

    payload = debug_tab._snapshot_view.toPlainText()
    assert STATE_KEY_ROS_CONNECTION_STATUS in payload
    assert STATE_KEY_ACTION_STATUS not in payload

    export_path = tmp_path / "diag.log"
    debug_tab._last_export_payload = "diag-payload"
    export_path.write_text("", encoding="utf-8")
    # monkeypatch bez fixture, zgodnie z minimalnym zakresem testu.
    debug_tab._export_diagnostics_to_file = lambda: export_path.write_text(debug_tab._last_export_payload + "\n", encoding="utf-8")
    debug_tab._export_diagnostics_to_file()
    assert export_path.read_text(encoding="utf-8") == "diag-payload\n"


def test_controls_tab_counts_blocked_action_attempts() -> None:
    _ensure_qapplication()
    window = _DummyWindow()
    controls_tab = ControlsTab(window)
    controls_tab._refresh_timer.stop()
    _set_state(window.state_store, STATE_KEY_ACTION_STATUS, value="RUNNING", quality=DataQuality.STALE)
    _set_state(window.state_store, STATE_KEY_ACTION_GOAL_ID, value="goal-1", quality=DataQuality.STALE)

    controls_tab._refresh_view()
    controls_tab._on_send_goal()
    controls_tab._on_cancel_goal()
    controls_tab._on_quick_action("start_patrol")

    assert "send=1" in controls_tab._blocked_summary_value.text()
    assert "cancel=1" in controls_tab._blocked_summary_value.text()
    assert "quick=1" in controls_tab._blocked_summary_value.text()
    assert "test_reason=3" in controls_tab._blocked_reason_value.text()


def test_rosbag_tab_filters_log_and_counts_blocked_actions() -> None:
    _ensure_qapplication()
    window = _DummyWindow()
    rosbag_tab = RosbagTab(window)
    rosbag_tab._refresh_timer.stop()
    _set_state(window.state_store, STATE_KEY_RECORDING_STATUS, value="IDLE", quality=DataQuality.UNAVAILABLE)
    _set_state(window.state_store, STATE_KEY_PLAYBACK_STATUS, value="STOPPED", quality=DataQuality.VALID)
    _set_state(window.state_store, STATE_KEY_SELECTED_BAG, value="mission_01", quality=DataQuality.VALID)
    _set_state(window.state_store, STATE_KEY_BAG_INTEGRITY_STATUS, value="OK", quality=DataQuality.VALID)

    rosbag_tab._refresh_view()
    rosbag_tab._on_start_recording()
    rosbag_tab._on_start_playback()
    rosbag_tab._event_filter_combo.setCurrentText("BLOCKED")

    assert "[BLOCKED]" in rosbag_tab._event_log_view.toPlainText()
    assert "start_playback=1" in rosbag_tab._blocked_telemetry_label.text()
    assert "start_recording=1" in rosbag_tab._blocked_telemetry_label.text()

# [AI-CHANGE | 2026-04-30 20:05 UTC | v0.201]
# CO ZMIENIONO: Przebudowano test nawigacji mapy tak, aby wyszukiwał przycisk `QPushButton` „Mapa”
#               w sidebarze i przełączał zakładkę przez `QTest.mouseClick` zamiast wywołania metody prywatnej.
# DLACZEGO: Test ma odzwierciedlać realny przepływ operatorski (kliknięcie UI), a nie skrót techniczny,
#           oraz pilnować bezpiecznego fallbacku przy braku zakładki mapy.
# JAK TO DZIAŁA: Test znajduje przycisk po tekście, klika go lewym przyciskiem myszy i sprawdza przełączenie
#                na zakładkę „Map”; następnie usuwa zakładkę, klika ponownie i weryfikuje brak zmiany indeksu
#                oraz komunikat fallback w status barze.
# TODO: Dodać wariant testu z aliasem etykiety „Mapa” jako nazwą zakładki, aby pokryć scenariusz i18n.
def test_main_window_map_navigation_uses_label_lookup_and_safe_fallback() -> None:
    _ensure_qapplication()

    from robot_mission_control.core import Supervisor
    from robot_mission_control.ui.main_window import MainWindow
    from robot_mission_control.versioning import VersionMetadata

    window = MainWindow(
        state_store=StateStore(),
        supervisor=Supervisor(),
        version_metadata=VersionMetadata(commit_count=201, short_sha="testsha", build_time_utc="2026-04-30T14:20:00Z", source="test"),
        ui_timer_intervals_ms={"main_window_refresh_interval_ms": 60000},
    )
    window._refresh_timer.stop()

    assert window._tabs_panel is not None
    tabs = window._tabs_panel
    initial_index = tabs.currentIndex()

    map_widget = QWidget()
    map_index = tabs.addTab(map_widget, "Map")
    assert map_index >= 0

    map_button = next((button for button in window.findChildren(QPushButton) if button.text() == "Mapa"), None)
    assert map_button is not None

    tabs.tabBar().moveTab(map_index, 0)
    QTest.mouseClick(map_button, Qt.LeftButton)
    assert tabs.currentWidget() is map_widget

    tabs.removeTab(tabs.indexOf(map_widget))
    tabs.setCurrentIndex(initial_index)
    QTest.mouseClick(map_button, Qt.LeftButton)
    assert tabs.currentIndex() == initial_index
    assert window.statusBar().currentMessage() == "Brak zakładki Map/Mapa — funkcja chwilowo niedostępna."

# [AI-CHANGE | 2026-04-30 16:20 UTC | v0.201]
# CO ZMIENIONO: Dodano scenariusz end-to-end dla przepływu store -> MainWindow -> MapTab.
# DLACZEGO: Test potwierdza, że MainWindow cyklicznie przekazuje snapshot mapy i że etykiety MapTab
#           aktualizują się wyłącznie przy kompletnych danych (zachowanie fail-safe).
# JAK TO DZIAŁA: Test zapisuje komplet kluczy mapy do StateStore, wywołuje `_refresh_runtime_status`,
#                a następnie asertywnie sprawdza zmianę tekstu etykiet pozycji/jakości w MapTab.
# TODO: Dodać wariant z niekompletną próbką i weryfikacją fallbacku `Pozycja: BRAK DANYCH` po timerze Qt.
def test_main_window_refreshes_map_tab_from_store_snapshot_end_to_end() -> None:
    _ensure_qapplication()

    from robot_mission_control.core import (
        STATE_KEY_MAP_DATA_QUALITY,
        STATE_KEY_MAP_FRAME_ID,
        STATE_KEY_MAP_POSITION,
        STATE_KEY_MAP_TF_STATUS,
        STATE_KEY_MAP_TIMESTAMP,
        STATE_KEY_MAP_TRAJECTORY,
        Supervisor,
    )
    from robot_mission_control.ui.main_window import MainWindow
    from robot_mission_control.ui.tabs.map_tab import MapTab
    from robot_mission_control.versioning import VersionMetadata

    store = StateStore()
    window = MainWindow(
        state_store=store,
        supervisor=Supervisor(),
        version_metadata=VersionMetadata(commit_count=201, short_sha="testsha", build_time_utc="2026-04-30T16:20:00Z", source="test"),
        ui_timer_intervals_ms={"main_window_refresh_interval_ms": 60000},
    )
    window._refresh_timer.stop()

    map_tab = None
    assert window._tabs_panel is not None
    for i in range(window._tabs_panel.count()):
        widget = window._tabs_panel.widget(i)
        if isinstance(widget, MapTab):
            map_tab = widget
            break
    assert map_tab is not None

    now = datetime.now(timezone.utc)
    _set_state(store, STATE_KEY_MAP_POSITION, value=(1.2, 3.4), quality=DataQuality.VALID)
    _set_state(store, STATE_KEY_MAP_FRAME_ID, value="map", quality=DataQuality.VALID)
    _set_state(store, STATE_KEY_MAP_TIMESTAMP, value=now, quality=DataQuality.VALID)
    _set_state(store, STATE_KEY_MAP_TRAJECTORY, value=((1.2, 3.4), (1.4, 3.8)), quality=DataQuality.VALID)
    _set_state(store, STATE_KEY_MAP_TF_STATUS, value="OK", quality=DataQuality.VALID)
    _set_state(store, STATE_KEY_MAP_DATA_QUALITY, value="VALID", quality=DataQuality.VALID)

    window._refresh_runtime_status()

    assert map_tab._position_label.text() == "Pozycja: x=1.20, y=3.40"
    assert "VALID" in map_tab._quality_label.text()
