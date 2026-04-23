"""Rosbag operator tab with safe fallback gating."""

from __future__ import annotations

from collections import deque

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from robot_mission_control.core import (
    STATE_KEY_BAG_INTEGRITY_STATUS,
    STATE_KEY_PLAYBACK_STATUS,
    STATE_KEY_RECORDING_STATUS,
    STATE_KEY_SELECTED_BAG,
    StateStore,
    utc_now,
)
from .state_rendering import is_actionable, render_value

# [AI-CHANGE | 2026-04-23 13:27 UTC | v0.185]
# CO ZMIENIONO: Zastąpiono placeholder pełnym panelem Rosbag z sekcjami Recording/Playback/Wybrany bag/Integralność,
#               przyciskami akcji (start/stop recording i playback) oraz lokalnym logiem działań operatora.
# DLACZEGO: Operator musi mieć przejrzysty, pojedynczy panel do obsługi rosbag i bezpieczną blokadę akcji,
#           gdy źródło danych nie ma pewnej jakości.
# JAK TO DZIAŁA: Zakładka odświeża statusy ze StateStore co 500 ms; jeśli którykolwiek stan krytyczny nie ma
#                jakości VALID, UI pokazuje `BRAK DANYCH`, wyłącza krytyczne przyciski i wpisuje zdarzenia do lokalnego logu.
# TODO: Dodać mapowanie statusów na kolory (zielony/żółty/czerwony) i filtr logu po typie akcji.


class RosbagTab(QWidget):
    """Operator panel for rosbag recording and playback actions."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._state_store = self._resolve_state_store(parent)
        self._event_log: deque[str] = deque(maxlen=12)

        root = QVBoxLayout(self)
        card = QFrame(self)
        root.addWidget(card)

        layout = QVBoxLayout(card)
        title = QLabel("Zarządzanie rosbag", card)
        title.setStyleSheet("font-size: 16px; font-weight: 600;")

        status_box = QGroupBox("Status rosbag", card)
        status_grid = QGridLayout(status_box)
        self._recording_value = QLabel("BRAK DANYCH", status_box)
        self._playback_value = QLabel("BRAK DANYCH", status_box)
        self._selected_bag_value = QLabel("BRAK DANYCH", status_box)
        self._integrity_value = QLabel("BRAK DANYCH", status_box)

        status_grid.addWidget(QLabel("Recording:", status_box), 0, 0)
        status_grid.addWidget(self._recording_value, 0, 1)
        status_grid.addWidget(QLabel("Playback:", status_box), 1, 0)
        status_grid.addWidget(self._playback_value, 1, 1)
        status_grid.addWidget(QLabel("Wybrany bag:", status_box), 2, 0)
        status_grid.addWidget(self._selected_bag_value, 2, 1)
        status_grid.addWidget(QLabel("Integralność:", status_box), 3, 0)
        status_grid.addWidget(self._integrity_value, 3, 1)

        actions_box = QGroupBox("Akcje", card)
        actions_layout = QHBoxLayout(actions_box)
        self._start_recording_button = QPushButton("Start recording", actions_box)
        self._stop_recording_button = QPushButton("Stop recording", actions_box)
        self._start_playback_button = QPushButton("Start playback", actions_box)
        self._stop_playback_button = QPushButton("Stop playback", actions_box)

        self._start_recording_button.clicked.connect(self._on_start_recording)
        self._stop_recording_button.clicked.connect(self._on_stop_recording)
        self._start_playback_button.clicked.connect(self._on_start_playback)
        self._stop_playback_button.clicked.connect(self._on_stop_playback)

        actions_layout.addWidget(self._start_recording_button)
        actions_layout.addWidget(self._stop_recording_button)
        actions_layout.addWidget(self._start_playback_button)
        actions_layout.addWidget(self._stop_playback_button)

        log_box = QGroupBox("Ostatnie zdarzenia operatora", card)
        log_layout = QVBoxLayout(log_box)
        self._event_log_view = QTextEdit(log_box)
        self._event_log_view.setReadOnly(True)
        self._event_log_view.setMinimumHeight(120)
        log_layout.addWidget(self._event_log_view)

        layout.addWidget(title)
        layout.addWidget(status_box)
        layout.addWidget(actions_box)
        layout.addWidget(log_box)
        layout.addStretch(1)

        self._refresh_timer = QTimer(self)
        self._refresh_timer.setInterval(500)
        self._refresh_timer.timeout.connect(self._refresh_view)
        self._refresh_timer.start()

        self._append_event("Zakładka rosbag uruchomiona.")
        self._refresh_view()

    def _resolve_state_store(self, parent: QWidget | None) -> StateStore | None:
        window = parent.window() if parent is not None else None
        return getattr(window, "state_store", None)

    # [AI-CHANGE | 2026-04-23 14:15 UTC | v0.187]
    # CO ZMIENIONO: Zastąpiono lokalną walidację item.quality przez wspólne helpery
    #               `is_actionable` i `render_value`.
    # DLACZEGO: Panel rosbag ma współdzielić identyczną semantykę bezpieczeństwa z innymi zakładkami.
    # JAK TO DZIAŁA: Dla quality != VALID helper zawsze zwraca fallback i znacznik `ok=False`, więc
    #                przyciski krytyczne zostają zablokowane zanim operator wykona ryzykowną akcję.
    # TODO: Dodać telemetryczny licznik blokad akcji z rozbiciem po reason_code.
    def _render_store_value(self, key: str, *, fallback: str = "BRAK DANYCH") -> tuple[str, bool]:
        if self._state_store is None:
            return fallback, False

        item = self._state_store.get(key)
        if not is_actionable(item):
            return fallback, False
        return render_value(item, fallback=fallback), True

    def _append_event(self, message: str) -> None:
        timestamp = utc_now().strftime("%H:%M:%S")
        self._event_log.appendleft(f"[{timestamp}] {message}")
        self._event_log_view.setPlainText("\n".join(self._event_log))

    def _invoke_window_callback(self, callback_name: str, event_name: str) -> None:
        # [AI-CHANGE | 2026-04-23 19:05 UTC | v0.189]
        # CO ZMIENIONO: Dodano defensywne sprawdzenie aktywności przycisku przed wywołaniem callbacku.
        # DLACZEGO: Programowe wywołanie handlera nie może omijać blokady UI dla niepewnego stanu danych.
        # JAK TO DZIAŁA: Dla callbacków mapowanych na disabled przycisk metoda kończy się bez side effectów
        #                i zapisuje zdarzenie o pominięciu akcji.
        # TODO: Dodać reason_code do wpisu logu, aby łatwiej diagnozować przyczynę blokady.
        callback_to_button = {
            "start_rosbag_recording": self._start_recording_button,
            "stop_rosbag_recording": self._stop_recording_button,
            "start_rosbag_playback": self._start_playback_button,
            "stop_rosbag_playback": self._stop_playback_button,
        }
        mapped_button = callback_to_button.get(callback_name)
        if mapped_button is not None and not mapped_button.isEnabled():
            self._append_event(f"Pominięto: {event_name} (stan niewiarygodny).")
            self._refresh_view()
            return

        window = self.window()
        callback = getattr(window, callback_name, None)
        if callable(callback):
            callback()
            self._append_event(f"Wykonano: {event_name}.")
        else:
            self._append_event(f"Pominięto: {event_name} (callback niedostępny).")
        self._refresh_view()

    def _on_start_recording(self) -> None:
        self._invoke_window_callback("start_rosbag_recording", "start recording")

    def _on_stop_recording(self) -> None:
        self._invoke_window_callback("stop_rosbag_recording", "stop recording")

    def _on_start_playback(self) -> None:
        self._invoke_window_callback("start_rosbag_playback", "start playback")

    def _on_stop_playback(self) -> None:
        self._invoke_window_callback("stop_rosbag_playback", "stop playback")

    def _refresh_view(self) -> None:
        recording, recording_ok = self._render_store_value(STATE_KEY_RECORDING_STATUS)
        playback, playback_ok = self._render_store_value(STATE_KEY_PLAYBACK_STATUS)
        selected_bag, selected_bag_ok = self._render_store_value(STATE_KEY_SELECTED_BAG)
        integrity, integrity_ok = self._render_store_value(STATE_KEY_BAG_INTEGRITY_STATUS)

        self._recording_value.setText(recording)
        self._playback_value.setText(playback)
        self._selected_bag_value.setText(selected_bag)
        self._integrity_value.setText(integrity)

        critical_state_ok = recording_ok and playback_ok and selected_bag_ok and integrity_ok

        if not critical_state_ok:
            self._start_recording_button.setEnabled(False)
            self._stop_recording_button.setEnabled(False)
            self._start_playback_button.setEnabled(False)
            self._stop_playback_button.setEnabled(False)
            return

        is_recording = recording.upper() == "RECORDING"
        is_playing = playback.upper() == "PLAYING"
        can_playback = integrity.upper() in {"OK", "VALID", "PASSED"} and selected_bag != "BRAK DANYCH"

        self._start_recording_button.setEnabled(not is_recording and not is_playing)
        self._stop_recording_button.setEnabled(is_recording)
        self._start_playback_button.setEnabled(can_playback and not is_recording and not is_playing)
        self._stop_playback_button.setEnabled(is_playing)
