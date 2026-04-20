"""Main window layout for mission control desktop app."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QStatusBar,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from robot_mission_control.core import (
    DataQuality,
    STATE_KEY_BAG_INTEGRITY_STATUS,
    STATE_KEY_DATA_SOURCE_MODE,
    STATE_KEY_PLAYBACK_STATUS,
    STATE_KEY_RECORDING_STATUS,
    STATE_KEY_SELECTED_BAG,
    StateStore,
    StateValue,
)
from robot_mission_control.ui.tabs.controls_tab import ControlsTab
from robot_mission_control.ui.tabs.debug_tab import DebugTab
from robot_mission_control.ui.tabs.diagnostics_tab import DiagnosticsTab
from robot_mission_control.ui.tabs.extensions_tab import ExtensionsTab
from robot_mission_control.ui.tabs.overview_tab import OverviewTab
from robot_mission_control.ui.tabs.rosbag_tab import RosbagTab
from robot_mission_control.ui.tabs.telemetry_tab import TelemetryTab
from robot_mission_control.ui.tabs.video_depth_tab import VideoDepthTab

# [AI-CHANGE | 2026-04-20 18:27 UTC | v0.143]
# CO ZMIENIONO: MainWindow przyjmuje wyłącznie StateStore i renderuje statusy tylko z danych zapisanych w store.
# DLACZEGO: Eliminuje to ryzyko bezpośredniego wstrzykiwania surowych wartości z ROS do komponentów UI.
# JAK TO DZIAŁA: Metody _render_* pobierają klucze globalne ze store; gdy jakość != VALID, UI pokazuje
#                bezpieczne BRAK DANYCH/NIEDOSTĘPNE zamiast domyślnych liczb.
# TODO: Dodać cykliczny refresh przez QTimer/sygnały, aby UI reagował na aktualizacje store w czasie rzeczywistym.


class MainWindow(QMainWindow):
    """Main mission control desktop window."""

    def __init__(self, state_store: StateStore) -> None:
        super().__init__()
        self.setWindowTitle("Robot Mission Control")
        self.resize(1400, 900)

        self._state_store = state_store

        central = QWidget(self)
        root_layout = QVBoxLayout(central)
        root_layout.setContentsMargins(8, 8, 8, 8)
        root_layout.setSpacing(8)

        root_layout.addWidget(self._build_top_bar())
        root_layout.addLayout(self._build_middle_layout())

        self.setCentralWidget(central)
        self.setStatusBar(self._build_status_bar())

    def _render_value(self, item: StateValue | None, *, fallback: str = "BRAK DANYCH") -> str:
        """Render store value with quality-aware safety fallback."""
        if item is None:
            return fallback
        if item.quality is not DataQuality.VALID:
            if item.quality is DataQuality.ERROR:
                return "BŁĄD DANYCH"
            if item.quality is DataQuality.STALE:
                return "DANE PRZETERMINOWANE"
            return fallback
        return str(item.value)

    def _render_quality(self, item: StateValue | None) -> str:
        """Render compact quality tag for operator visibility."""
        if item is None:
            return DataQuality.UNAVAILABLE.value
        return item.quality.value

    def _build_top_bar(self) -> QWidget:
        top_bar = QFrame(self)
        top_bar.setFrameShape(QFrame.Shape.StyledPanel)

        layout = QHBoxLayout(top_bar)
        title = QLabel("Robot Mission Control", top_bar)
        title.setStyleSheet("font-size: 18px; font-weight: 600;")

        source_item = self._state_store.get(STATE_KEY_DATA_SOURCE_MODE)
        connection = QLabel(f"Źródło danych: {self._render_value(source_item, fallback='NIEDOSTĘPNE')}", top_bar)
        data = QLabel(f"Jakość: {self._render_quality(source_item)}", top_bar)

        unavailable_btn = QPushButton("NIEDOSTĘPNE W TEJ WERSJI", top_bar)
        unavailable_btn.setEnabled(False)

        layout.addWidget(title)
        layout.addStretch(1)
        layout.addWidget(connection)
        layout.addWidget(data)
        layout.addWidget(unavailable_btn)
        return top_bar

    def _build_middle_layout(self) -> QHBoxLayout:
        layout = QHBoxLayout()
        layout.setSpacing(8)

        layout.addWidget(self._build_sidebar(), 1)
        layout.addWidget(self._build_tabs_panel(), 4)
        layout.addWidget(self._build_alarm_panel(), 2)
        return layout

    def _build_sidebar(self) -> QWidget:
        sidebar = QFrame(self)
        sidebar.setFrameShape(QFrame.Shape.StyledPanel)
        layout = QVBoxLayout(sidebar)

        layout.addWidget(QLabel("Nawigacja", sidebar))

        for label in [
            "Misja",
            "Robot",
            "Łączność",
            "Mapa",
            "Zadania",
        ]:
            button = QPushButton(f"{label} — NIEDOSTĘPNE W TEJ WERSJI", sidebar)
            button.setEnabled(False)
            layout.addWidget(button)

        layout.addStretch(1)
        return sidebar

    def _build_tabs_panel(self) -> QWidget:
        tabs = QTabWidget(self)
        tabs.setDocumentMode(True)

        tabs.addTab(OverviewTab(self), "Overview")
        tabs.addTab(TelemetryTab(self), "Telemetry")
        tabs.addTab(VideoDepthTab(self), "Video & Depth")
        tabs.addTab(ControlsTab(self), "Controls")
        tabs.addTab(DiagnosticsTab(self), "Diagnostics")
        tabs.addTab(DebugTab(self), "Debug")
        tabs.addTab(RosbagTab(self), "Rosbag")
        tabs.addTab(ExtensionsTab(self), "Extensions")

        return tabs

    def _build_alarm_panel(self) -> QWidget:
        alarms = QFrame(self)
        alarms.setFrameShape(QFrame.Shape.StyledPanel)
        layout = QVBoxLayout(alarms)

        title = QLabel("Panel alarmów", alarms)
        title.setStyleSheet("font-size: 14px; font-weight: 600;")

        bag_integrity_item = self._state_store.get(STATE_KEY_BAG_INTEGRITY_STATUS)
        state_line = QLabel(self._render_value(bag_integrity_item), alarms)
        state_line.setAlignment(Qt.AlignmentFlag.AlignCenter)

        selected_bag_item = self._state_store.get(STATE_KEY_SELECTED_BAG)
        unavailable = QLabel(
            f"Rosbag: {self._render_value(selected_bag_item, fallback='NIE WYBRANO')}",
            alarms,
        )
        unavailable.setAlignment(Qt.AlignmentFlag.AlignCenter)

        layout.addWidget(title)
        layout.addWidget(state_line)
        layout.addWidget(unavailable)
        layout.addStretch(1)

        return alarms

    def _build_status_bar(self) -> QStatusBar:
        status_bar = QStatusBar(self)
        playback = self._render_quality(self._state_store.get(STATE_KEY_PLAYBACK_STATUS))
        recording = self._render_quality(self._state_store.get(STATE_KEY_RECORDING_STATUS))
        status_bar.showMessage(f"Status store: PLAYBACK={playback} | RECORDING={recording}")
        return status_bar
