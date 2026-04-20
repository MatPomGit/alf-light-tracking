"""Main window layout for mission control desktop app."""

from __future__ import annotations

from dataclasses import dataclass

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

from robot_mission_control.ui.tabs.controls_tab import ControlsTab
from robot_mission_control.ui.tabs.debug_tab import DebugTab
from robot_mission_control.ui.tabs.diagnostics_tab import DiagnosticsTab
from robot_mission_control.ui.tabs.extensions_tab import ExtensionsTab
from robot_mission_control.ui.tabs.overview_tab import OverviewTab
from robot_mission_control.ui.tabs.rosbag_tab import RosbagTab
from robot_mission_control.ui.tabs.telemetry_tab import TelemetryTab
from robot_mission_control.ui.tabs.video_depth_tab import VideoDepthTab

# [AI-CHANGE | 2026-04-20 14:12 UTC | v0.141]
# CO ZMIENIONO: Dodano główne okno z pełnym szkieletem layoutu: top bar, sidebar, tabs, panel alarmów i status bar.
# DLACZEGO: To minimalna struktura wymagana do dalszego rozwijania Mission Control w kolejnych iteracjach.
# JAK TO DZIAŁA: Okno buduje sekcje UI warstwowo; komponenty niegotowe są jawnie zablokowane i opisane
#                etykietą "NIEDOSTĘPNE W TEJ WERSJI", a status startuje bezpiecznie jako BRAK DOSTĘPU/BRAK DANYCH.
# TODO: Dodać warstwę ViewModel i sygnały Qt do odświeżania statusów oraz alarmów w czasie rzeczywistym.


@dataclass(slots=True)
class RuntimeStateView:
    """Data passed from app runtime to main window."""

    connection_status: str
    data_status: str


class MainWindow(QMainWindow):
    """Main mission control desktop window."""

    def __init__(self, runtime_state: RuntimeStateView) -> None:
        super().__init__()
        self.setWindowTitle("Robot Mission Control")
        self.resize(1400, 900)

        self._runtime_state = runtime_state

        central = QWidget(self)
        root_layout = QVBoxLayout(central)
        root_layout.setContentsMargins(8, 8, 8, 8)
        root_layout.setSpacing(8)

        root_layout.addWidget(self._build_top_bar())
        root_layout.addLayout(self._build_middle_layout())

        self.setCentralWidget(central)
        self.setStatusBar(self._build_status_bar())

    def _build_top_bar(self) -> QWidget:
        top_bar = QFrame(self)
        top_bar.setFrameShape(QFrame.Shape.StyledPanel)

        layout = QHBoxLayout(top_bar)
        title = QLabel("Robot Mission Control", top_bar)
        title.setStyleSheet("font-size: 18px; font-weight: 600;")

        connection = QLabel(f"Połączenie: {self._runtime_state.connection_status}", top_bar)
        data = QLabel(f"Dane: {self._runtime_state.data_status}", top_bar)

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

        state_line = QLabel("BRAK DANYCH", alarms)
        state_line.setAlignment(Qt.AlignmentFlag.AlignCenter)

        unavailable = QLabel("NIEDOSTĘPNE W TEJ WERSJI", alarms)
        unavailable.setAlignment(Qt.AlignmentFlag.AlignCenter)

        layout.addWidget(title)
        layout.addWidget(state_line)
        layout.addWidget(unavailable)
        layout.addStretch(1)

        return alarms

    def _build_status_bar(self) -> QStatusBar:
        status_bar = QStatusBar(self)
        status_bar.showMessage(
            f"Status: {self._runtime_state.connection_status} | {self._runtime_state.data_status}"
        )
        return status_bar
