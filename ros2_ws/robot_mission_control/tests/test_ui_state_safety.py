from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

qt_widgets = pytest.importorskip("PySide6.QtWidgets", reason="Brak bibliotek systemowych Qt (np. libGL) w środowisku testowym.")
QApplication = qt_widgets.QApplication
QWidget = qt_widgets.QWidget

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
from robot_mission_control.ui.tabs.overview_tab import OverviewTab
from robot_mission_control.ui.tabs.rosbag_tab import RosbagTab
from robot_mission_control.ui.tabs.state_rendering import render_value


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

    assert controls_tab._status_value.text() == "BRAK DANYCH"
    assert controls_tab._goal_id_value.text() == "BRAK DANYCH"
    assert controls_tab._progress_value.text() == "BRAK DANYCH"
    assert controls_tab._result_value.text() == "BRAK DANYCH"
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

    assert overview_tab._action_status_value.text() == "BRAK DANYCH"
    assert overview_tab._quality_value.text() == DataQuality.STALE.value


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

    assert rosbag_tab._recording_value.text() == "BRAK DANYCH"
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
