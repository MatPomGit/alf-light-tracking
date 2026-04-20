"""Main window layout for mission control desktop app."""

from __future__ import annotations

from datetime import datetime

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
    STATE_KEY_DEPENDENCY_STATUS,
    STATE_KEY_PLAYBACK_STATUS,
    STATE_KEY_RECORDING_STATUS,
    STATE_KEY_SELECTED_BAG,
    StateStore,
    StateValue,
    Supervisor,
    utc_now,
)
from robot_mission_control.ros.dependency_audit_client import DependencyStatusCode, DependencyStatusReport
from robot_mission_control.ui.tabs.controls_tab import ControlsTab
from robot_mission_control.ui.tabs.debug_tab import DebugTab
from robot_mission_control.ui.tabs.diagnostics_tab import DiagnosticsTab
from robot_mission_control.ui.tabs.extensions_tab import ExtensionsTab
from robot_mission_control.ui.tabs.overview_tab import OverviewTab
from robot_mission_control.ui.tabs.rosbag_tab import RosbagTab
from robot_mission_control.ui.tabs.telemetry_tab import TelemetryTab
from robot_mission_control.ui.tabs.video_depth_tab import VideoDepthTab
from robot_mission_control.versioning import VersionMetadata

# [AI-CHANGE | 2026-04-20 22:05 UTC | v0.158]
# CO ZMIENIONO: Ujednolicono odczyt statusów w UI tak, aby status bar renderował `recording_status`
#               i `playback_status` jako wartości ze StateStore (z fallbackiem jakości), bez logiki ROS w UI.
# DLACZEGO: Kryterium DoD wymaga, by warstwa UI czytała stan wyłącznie ze store i nie polegała na bezpośrednich update'ach widgetów.
# JAK TO DZIAŁA: `_build_status_bar` pobiera klucze globalne przez `_render_value`; przy danych niepewnych
#                wyświetla komunikat bezpieczny (`BRAK DANYCH`), co ogranicza ryzyko mylącego statusu operatora.
# TODO: Dodać timer odświeżania status bar, aby zmiany store były widoczne runtime bez rekonstrukcji okna.


class MainWindow(QMainWindow):
    """Main mission control desktop window."""

    def __init__(self, state_store: StateStore, supervisor: Supervisor, version_metadata: VersionMetadata) -> None:
        super().__init__()
        self.setWindowTitle("Robot Mission Control")
        self.resize(1400, 900)

        self._state_store = state_store
        self._supervisor = supervisor
        self._version_metadata = version_metadata

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

        tab_defs = [
            ("Overview", "panel_overview", OverviewTab),
            ("Telemetry", "panel_telemetry", TelemetryTab),
            ("Video & Depth", "panel_video_depth", VideoDepthTab),
            ("Controls", "panel_controls", ControlsTab),
            ("Diagnostics", "panel_diagnostics", DiagnosticsTab),
            ("Debug", "panel_debug", DebugTab),
            ("Rosbag", "panel_rosbag", RosbagTab),
            ("Extensions", "panel_extensions", ExtensionsTab),
        ]
        for label, panel_name, panel_cls in tab_defs:
            tabs.addTab(self._build_safe_tab(panel_name, panel_cls), label)

        return tabs

    def _build_safe_tab(self, panel_name: str, panel_cls: type[QWidget]) -> QWidget:
        """Build single tab with local failure boundary (only this panel becomes unavailable)."""
        now = utc_now()
        self._supervisor.register_channel(panel_name)
        self._supervisor.heartbeat_channel(panel_name, now)

        try:
            panel = panel_cls(self)
            self._supervisor.record_channel_success(panel_name, now)
            return panel
        except Exception as exc:  # noqa: BLE001
            self._supervisor.mark_panel_unavailable(panel_name, exc, now)
            is_open, _ = self._supervisor.record_channel_failure(panel_name, now)
            return self._build_unavailable_panel(panel_name, incident_time=now, breaker_open=is_open)

    def _build_unavailable_panel(self, panel_name: str, *, incident_time: datetime, breaker_open: bool) -> QWidget:
        """Create fallback panel used when given tab fails."""
        panel = QFrame(self)
        layout = QVBoxLayout(panel)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        title = QLabel(f"{panel_name}", panel)
        title.setStyleSheet("font-size: 16px; font-weight: 600;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)

        state = QLabel("UNAVAILABLE", panel)
        state.setStyleSheet("font-weight: 700; color: #a94442;")
        state.setAlignment(Qt.AlignmentFlag.AlignCenter)

        detail = QLabel(
            f"Awaria od: {incident_time.isoformat()} | Circuit breaker: {'OPEN' if breaker_open else 'CLOSED'}",
            panel,
        )
        detail.setAlignment(Qt.AlignmentFlag.AlignCenter)

        layout.addWidget(title)
        layout.addWidget(state)
        layout.addWidget(detail)
        return panel

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
        playback = self._render_value(self._state_store.get(STATE_KEY_PLAYBACK_STATUS))
        recording = self._render_value(self._state_store.get(STATE_KEY_RECORDING_STATUS))
        incidents_count = len(self._supervisor.incidents())
        dependency_message = self._render_dependency_status()
        version_message = self._render_version_status()

        status_bar.showMessage(
            f"{version_message} | STATUS: PLAYBACK={playback} RECORDING={recording} INCIDENTS={incidents_count} | {dependency_message}"
        )
        return status_bar

    def _render_version_status(self) -> str:
        short_sha = self._version_metadata.short_sha or "---"
        build_time = self._version_metadata.build_time_utc or "---"
        return (
            f"WERSJA={self._version_metadata.version_tag} "
            f"SHA={short_sha} BUILD={build_time} SRC={self._version_metadata.source}"
        )

    def _render_dependency_status(self) -> str:
        state_item = self._state_store.get(STATE_KEY_DEPENDENCY_STATUS)
        if state_item is None or state_item.quality is not DataQuality.VALID:
            return "DEPENDENCIES: WERSJA NIEDOSTĘPNA"

        report = state_item.value
        if not isinstance(report, DependencyStatusReport):
            return "DEPENDENCIES: WERSJA NIEDOSTĘPNA"

        counters: dict[DependencyStatusCode, int] = {
            DependencyStatusCode.OK: 0,
            DependencyStatusCode.MISSING: 0,
            DependencyStatusCode.WRONG_VERSION: 0,
            DependencyStatusCode.UNKNOWN: 0,
        }
        latest_timestamp = report.generated_at_utc
        for item in report.items:
            counters[item.status] = counters.get(item.status, 0) + 1
            if item.timestamp_utc > latest_timestamp:
                latest_timestamp = item.timestamp_utc

        return (
            "DEPENDENCIES: "
            f"OK={counters[DependencyStatusCode.OK]} "
            f"MISSING={counters[DependencyStatusCode.MISSING]} "
            f"WRONG_VERSION={counters[DependencyStatusCode.WRONG_VERSION]} "
            f"UNKNOWN={counters[DependencyStatusCode.UNKNOWN]} "
            f"TS={latest_timestamp.isoformat()} SRC={report.source}"
        )
