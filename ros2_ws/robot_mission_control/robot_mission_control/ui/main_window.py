"""Main window layout for mission control desktop app."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Callable

from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QStatusBar,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from robot_mission_control.core import (
    DataQuality,
    STATE_KEY_ACTION_PROGRESS,
    STATE_KEY_ACTION_RESULT,
    STATE_KEY_ACTION_STATUS,
    STATE_KEY_BAG_INTEGRITY_STATUS,
    STATE_KEY_DATA_SOURCE_MODE,
    STATE_KEY_DEPENDENCY_STATUS,
    STATE_KEY_MAP_DATA_QUALITY,
    STATE_KEY_MAP_FRAME_ID,
    STATE_KEY_MAP_REASON_CODE,
    STATE_KEY_MAP_TF_STATUS,
    STATE_KEY_MAP_TIMESTAMP,
    STATE_KEY_MAP_TRAJECTORY,
    STATE_KEY_MAP_POSITION,
    STATE_KEY_PLAYBACK_STATUS,
    STATE_KEY_RECORDING_STATUS,
    STATE_KEY_ROS_CONNECTION_STATUS,
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
# [AI-CHANGE | 2026-04-30 10:28 UTC | v0.201]
# CO ZMIENIONO: Dodano import `MapTab` do rejestru kart ładowanych przez MainWindow.
# DLACZEGO: Bez jawnego importu MainWindow nie może bezpiecznie skonstruować zakładki mapy.
# JAK TO DZIAŁA: Klasa `MapTab` jest dostępna podczas budowania listy `tab_defs` i przechodzi przez
#                `_build_safe_tab`, dzięki czemu ewentualny błąd pozostaje lokalny dla tej karty.
# TODO: Rozważyć automatyczny rejestr kart, aby ograniczyć ręczne utrzymywanie listy importów.
from robot_mission_control.ui.tabs.map_tab import MapTab
from robot_mission_control.ui.tabs.overview_tab import OverviewTab
from robot_mission_control.ui.tabs.rosbag_tab import RosbagTab
from robot_mission_control.ui.tabs.telemetry_tab import TelemetryTab
from robot_mission_control.ui.tabs.video_depth_tab import VideoDepthTab
from robot_mission_control.ui.operator_alerts import OperatorAlerts
from robot_mission_control.versioning import VersionMetadata

# [AI-CHANGE | 2026-04-21 03:58 UTC | v0.160]
# CO ZMIENIONO: Dodano renderowanie i automatyczne odświeżanie statusu połączenia ROS (`ros_connection_status`)
#               w top bar i status bar wraz z timerem UI.
# DLACZEGO: Utrata i odzyskanie połączenia musi być natychmiast widoczne w UI na podstawie StateStore.
# JAK TO DZIAŁA: MainWindow utrzymuje referencje do etykiet i co 1 s odświeża tekst ze store;
#                przy niepewnym stanie wyświetla bezpieczny fallback `ROZŁĄCZONY`.
# TODO: Dodać kod kolorów (zielony/żółty/czerwony) zależny od jakości i reason_code dla szybszej diagnostyki.


# [AI-CHANGE | 2026-04-21 05:21 UTC | v0.163]
# CO ZMIENIONO: MainWindow rozszerzono o callbacki start/cancel akcji i render statusu akcji
#               (status, progress, wynik) w status barze aplikacji.
# DLACZEGO: Operator ma otrzymywać pełny stan wykonania akcji w czasie rzeczywistym bez dodatkowych narzędzi.
# JAK TO DZIAŁA: Okno trzyma referencje do callbacków z warstwy bridge oraz co 1 s odczytuje nowe klucze
#                StateStore; przy niepewnych danych używa fallbacku `BRAK DANYCH`.
# TODO: Dodać osobny pasek kolorystyczny statusu akcji (RUNNING/SUCCEEDED/CANCELED/FAILED).


class MainWindow(QMainWindow):
    """Main mission control desktop window."""

    def __init__(
        self,
        state_store: StateStore,
        supervisor: Supervisor,
        version_metadata: VersionMetadata,
        ui_timer_intervals_ms: dict[str, int] | None = None,
        map_config: dict[str, float | list[str]] | None = None,
        submit_action_goal: Callable[[], None] | None = None,
        cancel_action_goal: Callable[[], None] | None = None,
        submit_quick_action: Callable[[str], None] | None = None,
        start_recording: Callable[[], None] | None = None,
        stop_recording: Callable[[], None] | None = None,
        start_playback: Callable[[], None] | None = None,
        stop_playback: Callable[[], None] | None = None,
    ) -> None:
        super().__init__()
        # [AI-CHANGE | 2026-04-23 14:44 UTC | v0.189]
        # CO ZMIENIONO: Dodano ustawienie ikony okna aplikacji z lokalnego assetu SVG.
        # DLACZEGO: Użytkownik potrzebuje widocznego logo w interfejsie oraz spójnej identyfikacji aplikacji.
        # JAK TO DZIAŁA: Przy starcie MainWindow próbuje wczytać `ui/assets/app_logo.svg`;
        #                jeśli plik nie istnieje, używany jest bezpieczny fallback bez ikony.
        # TODO: Podmienić SVG na docelowy wariant PNG z pipeline brandingu i dodać test snapshot UI.
        self.setWindowTitle("Robot Mission Control")
        self.setWindowIcon(self._load_application_icon())
        self.resize(1400, 900)

        self._state_store = state_store
        self._supervisor = supervisor
        self._version_metadata = version_metadata
        # [AI-CHANGE | 2026-04-23 18:29 UTC | v0.195]
        # CO ZMIENIONO: Dodano mapę konfiguracyjną `ui_timer_intervals_ms` używaną do sterowania timerami UI.
        # DLACZEGO: Chcemy usunąć hardcode interwałów i umożliwić strojenie wydajności przez sam plik config.
        # JAK TO DZIAŁA: MainWindow przechowuje słownik interwałów i udostępnia bezpieczny odczyt po kluczu.
        # TODO: Przenieść klucze interwałów do stałych współdzielonych między loaderem i UI.
        self._ui_timer_intervals_ms = dict(ui_timer_intervals_ms or {})
        # [AI-CHANGE | 2026-04-30 23:20 UTC | v0.201]
        # CO ZMIENIONO: Dodano przechowywanie `map_config` przekazywanej z warstwy bootstrap do UI.
        # DLACZEGO: Parametry walidacji mapy mają być sterowane konfiguracją runtime, a nie stałymi w `MapTab`.
        # JAK TO DZIAŁA: MainWindow trzyma lokalną kopię słownika i przekazuje ją podczas budowy zakładki mapy.
        # TODO: Wydzielić wspólny walidator UI-config, aby logować przypadki uszkodzonej konfiguracji kart.
        self._map_config = dict(map_config or {})
        self._submit_action_goal = submit_action_goal or (lambda: None)
        self._cancel_action_goal = cancel_action_goal or (lambda: None)
        self._submit_quick_action = submit_quick_action or (lambda _command_key: None)
        # [AI-CHANGE | 2026-04-23 13:27 UTC | v0.185]
        # CO ZMIENIONO: Dodano callbacki operacji rosbag (start/stop recording oraz start/stop playback)
        #               delegowane przez MainWindow do warstwy bridge.
        # DLACZEGO: RosbagTab ma działać analogicznie do ControlsTab i nie może znać implementacji backendu.
        # JAK TO DZIAŁA: Gdy callback nie jest przekazany, MainWindow podstawia bezpieczny no-op.
        # TODO: Podpiąć callbacki do realnych komend ROS2 po stabilizacji kontraktu transportowego rosbag.
        self._start_recording = start_recording or (lambda: None)
        self._stop_recording = stop_recording or (lambda: None)
        self._start_playback = start_playback or (lambda: None)
        self._stop_playback = stop_playback or (lambda: None)
        # [AI-CHANGE | 2026-04-23 16:30 UTC | v0.188]
        # CO ZMIENIONO: Dodano centralny rejestr `OperatorAlerts` utrzymywany przez MainWindow.
        # DLACZEGO: Wszystkie zakładki mają konsumować identyczny stan alertów i nie dublować logiki.
        # JAK TO DZIAŁA: MainWindow cyklicznie synchronizuje alerty ze snapshotem StateStore, a zakładki
        #                pobierają dane przez property `operator_alerts`.
        # TODO: Dodać trwały storage alertów, aby historia przetrwała restart aplikacji.
        self._operator_alerts = OperatorAlerts()
        self._connection_label: QLabel | None = None
        self._source_quality_label: QLabel | None = None
        self._status_bar: QStatusBar | None = None
        self._tabs_panel: QTabWidget | None = None

        central = QWidget(self)
        root_layout = QVBoxLayout(central)
        root_layout.setContentsMargins(8, 8, 8, 8)
        root_layout.setSpacing(8)

        root_layout.addWidget(self._build_top_bar())
        root_layout.addLayout(self._build_middle_layout())

        self.setCentralWidget(central)
        self.setStatusBar(self._build_status_bar())
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setInterval(self._resolve_timer_interval_ms("main_window_refresh_interval_ms", default_ms=1000))
        self._refresh_timer.timeout.connect(self._refresh_runtime_status)
        self._refresh_timer.start()

    # [AI-CHANGE | 2026-04-23 18:29 UTC | v0.195]
    # CO ZMIENIONO: Dodano metodę `_resolve_timer_interval_ms` do walidowanego odczytu interwałów timerów.
    # DLACZEGO: Zakładki podrzędne muszą pobierać interwały z jednego, bezpiecznego punktu z fallbackiem.
    # JAK TO DZIAŁA: Metoda zwraca dodatnią wartość `int` z konfiguracji; przy błędzie zwraca `default_ms`.
    # TODO: Raportować do diagnostyki przypadki użycia fallbacku, aby szybciej wykrywać błędną konfigurację.
    def _resolve_timer_interval_ms(self, timer_key: str, *, default_ms: int) -> int:
        raw_value = self._ui_timer_intervals_ms.get(timer_key)
        if isinstance(raw_value, int) and raw_value > 0:
            return raw_value
        return default_ms

    def ui_timer_interval_ms(self, timer_key: str, *, default_ms: int) -> int:
        """Publiczny accessor interwału timera dla zakładek potomnych."""
        return self._resolve_timer_interval_ms(timer_key, default_ms=default_ms)

    @property
    def state_store(self) -> StateStore:
        """Eksponuje store dla zakładek odczytujących status operatorski."""
        return self._state_store

    @property
    def operator_alerts(self) -> OperatorAlerts:
        """Eksponuje rejestr alertów dla zakładek UI."""
        return self._operator_alerts

    def submit_operator_action_goal(self) -> None:
        """Deleguje start akcji do warstwy bridge."""
        self._submit_action_goal()

    def cancel_operator_action_goal(self) -> None:
        """Deleguje anulowanie akcji do warstwy bridge."""
        self._cancel_action_goal()

    # [AI-CHANGE | 2026-04-21 15:52 UTC | v0.176]
    # CO ZMIENIONO: Dodano callback MainWindow dla predefiniowanych szybkich komend operatora.
    # DLACZEGO: ControlsTab musi delegować skróty akcji do warstwy ROS bez bezpośredniego sprzężenia z bridge.
    # JAK TO DZIAŁA: Zakładka przekazuje `command_key`, a MainWindow transportuje go do callbacku z bootstrapu.
    # TODO: Dodać globalny skrót klawiaturowy i historię ostatnich komend dla operatora.
    def submit_quick_operator_action(self, command_key: str) -> None:
        """Deleguje szybką komendę operatora do warstwy bridge."""
        self._submit_quick_action(command_key)

    def start_rosbag_recording(self) -> None:
        """Deleguje start nagrywania rosbag do warstwy bridge."""
        self._start_recording()

    def stop_rosbag_recording(self) -> None:
        """Deleguje zatrzymanie nagrywania rosbag do warstwy bridge."""
        self._stop_recording()

    def start_rosbag_playback(self) -> None:
        """Deleguje start playback rosbag do warstwy bridge."""
        self._start_playback()

    def stop_rosbag_playback(self) -> None:
        """Deleguje zatrzymanie playback rosbag do warstwy bridge."""
        self._stop_playback()

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
        connection_item = self._state_store.get(STATE_KEY_ROS_CONNECTION_STATUS)
        self._connection_label = QLabel(
            f"Połączenie ROS: {self._render_value(connection_item, fallback='ROZŁĄCZONY')}",
            top_bar,
        )
        self._source_quality_label = QLabel(f"Jakość źródła: {self._render_quality(source_item)}", top_bar)

        # [AI-CHANGE | 2026-04-23 14:44 UTC | v0.189]
        # CO ZMIENIONO: Rozszerzono top bar o logo aplikacji, etykietę wersji i aktywny przycisk pomocy.
        # DLACZEGO: Operator ma mieć szybki dostęp do numeru wersji oraz instrukcji obsługi bez opuszczania aplikacji.
        # JAK TO DZIAŁA: `logo_label` renderuje asset SVG, `version_label` pokazuje `v0.<commit_count>`,
        #                a `help_button` otwiera okno dialogowe z instrukcją zarządzania aplikacją.
        # TODO: Dodać i18n (PL/EN) dla treści pomocy oraz skrót klawiaturowy otwierający okno help.
        logo_label = self._build_logo_label(top_bar)
        version_label = QLabel(f"Wersja: {self._version_metadata.version_tag}", top_bar)
        help_button = QPushButton("Help", top_bar)
        help_button.clicked.connect(self._show_help_dialog)

        unavailable_btn = QPushButton("NIEDOSTĘPNE W TEJ WERSJI", top_bar)
        unavailable_btn.setEnabled(False)
        layout.addWidget(title)
        layout.addStretch(1)
        layout.addWidget(logo_label)
        layout.addWidget(version_label)
        layout.addWidget(self._connection_label)
        layout.addWidget(self._source_quality_label)
        layout.addWidget(help_button)
        layout.addWidget(unavailable_btn)
        return top_bar

    # [AI-CHANGE | 2026-04-23 14:44 UTC | v0.189]
    # CO ZMIENIONO: Dodano funkcje pomocnicze do renderowania logo i obsługi okna Help.
    # DLACZEGO: Logika UI dla logo i pomocy nie powinna być rozproszona po metodzie budującej top bar.
    # JAK TO DZIAŁA: `_build_logo_label` pokazuje grafikę lub fallback tekstowy, a `_show_help_dialog`
    #                prezentuje instrukcję operacyjną w bezpiecznym modalu bez wpływu na stan misji.
    # TODO: Dodać walidację obecności assetu przy starcie aplikacji i telemetryczny event otwarcia pomocy.
    def _load_application_icon(self) -> QIcon:
        icon_path = Path(__file__).resolve().parent / "assets" / "app_logo.svg"
        if not icon_path.exists():
            return QIcon()
        return QIcon(str(icon_path))

    def _build_logo_label(self, parent: QWidget) -> QLabel:
        logo_label = QLabel(parent)
        logo_path = Path(__file__).resolve().parent / "assets" / "app_logo.svg"
        pixmap = QPixmap(str(logo_path))
        if pixmap.isNull():
            logo_label.setText("LOGO")
            logo_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            logo_label.setFixedSize(40, 40)
            return logo_label

        logo_label.setPixmap(
            pixmap.scaled(40, 40, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        )
        return logo_label

    def _show_help_dialog(self) -> None:
        QMessageBox.information(
            self,
            "Help — Robot Mission Control",
            (
                "Jak zarządzać aplikacją:\n"
                "1) Sprawdź status połączenia ROS oraz jakość źródła w górnym pasku.\n"
                "2) Używaj zakładki Controls do uruchamiania i anulowania akcji operatora.\n"
                "3) Zakładka Rosbag służy do nagrywania i odtwarzania danych diagnostycznych.\n"
                "4) Przed rozpoczęciem misji zweryfikuj panel alarmów i status zależności.\n"
                "5) Jeśli status pokazuje BRAK DANYCH, traktuj wynik jako niepewny i nie wykonuj krytycznych decyzji."
            ),
        )

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

        # [AI-CHANGE | 2026-04-30 14:20 UTC | v0.201]
        # CO ZMIENIONO: W sekcji „Nawigacja” utrzymano aktywny przycisk „Robot” oraz dodano aktywny
        #               przycisk „Mapa” z dedykowanym handlerem przełączania kart.
        # DLACZEGO: Użytkownik zgłosił, że przycisk „Robot” był bezużyteczny (disabled z etykietą
        #           „NIEDOSTĘPNE W TEJ WERSJI”), więc wdrożono podstawową, użyteczną nawigację.
        # JAK TO DZIAŁA: Kliknięcie „Robot” wywołuje `_activate_robot_navigation()`, która bezpiecznie
        #                sprawdza obecność QTabWidget i przełącza widok na indeks zakładki telemetrycznej.
        #                Gdy panel nie jest gotowy, metoda kończy się bez wyjątku (bezpieczny fallback).
        # TODO: Dodać telemetrię kliknięć sidebaru i statystyki brakujących zakładek dla operatora.
        mission_button = QPushButton("Misja — NIEDOSTĘPNE W TEJ WERSJI", sidebar)
        mission_button.setEnabled(False)
        layout.addWidget(mission_button)

        robot_button = QPushButton("Robot", sidebar)
        robot_button.clicked.connect(self._activate_robot_navigation)
        layout.addWidget(robot_button)

        map_button = QPushButton("Mapa", sidebar)
        map_button.clicked.connect(self._activate_map_navigation)
        layout.addWidget(map_button)

        for label in ["Łączność", "Zadania"]:
            button = QPushButton(f"{label} — NIEDOSTĘPNE W TEJ WERSJI", sidebar)
            button.setEnabled(False)
            layout.addWidget(button)

        layout.addStretch(1)
        return sidebar

    def _build_tabs_panel(self) -> QWidget:
        tabs = QTabWidget(self)
        tabs.setDocumentMode(True)
        self._tabs_panel = tabs

        # [AI-CHANGE | 2026-04-30 10:28 UTC | v0.201]
        # CO ZMIENIONO: Dodano tab definicję `Map` opartą o `MapTab` i bezpieczny mechanizm
        #               `_build_safe_tab(panel_name, panel_cls)` używany przez pozostałe karty.
        # DLACZEGO: Zakładka mapy musi być integralną częścią panelu tabs i korzystać z istniejącej
        #           granicy błędu, aby awaria pojedynczej karty nie destabilizowała całego UI.
        # JAK TO DZIAŁA: `MapTab` jest tworzony tak samo jak inne zakładki; przy wyjątku zostanie
        #                zastąpiony panelem unavailable bez przerwania inicjalizacji MainWindow.
        # TODO: Dodać politykę kolejności kart konfigurowalną per profil operatora (UX role-based).
        tab_defs = [
            ("Overview", "panel_overview", OverviewTab),
            ("Telemetry", "panel_telemetry", TelemetryTab),
            ("Map", "panel_map", MapTab),
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

    # [AI-CHANGE | 2026-04-30 14:20 UTC | v0.201]
    # CO ZMIENIONO: Zastąpiono przełączanie zakładek po indeksie metodami opartymi o etykiety oraz dodano
    #               aktywny handler nawigacji „Mapa” z bezpiecznym fallbackiem braku zakładki.
    # DLACZEGO: Układ kart może się zmieniać, więc indeksy liczbowe są kruche i prowadzą do regresji UI.
    # JAK TO DZIAŁA: `_find_tab_index_by_labels` iteruje po `tabText(i)` i zwraca pierwszy pasujący indeks.
    #                `_activate_robot_navigation` oraz `_activate_map_navigation` przełączają kartę tylko przy
    #                pewnym dopasowaniu; w przeciwnym razie pozostawiają bieżący widok i publikują komunikat operatora.
    # TODO: Przenieść aliasy etykiet kart do centralnej konfiguracji i18n, aby uniknąć duplikacji napisów.
    def _find_tab_index_by_labels(self, expected_labels: tuple[str, ...]) -> int | None:
        if self._tabs_panel is None:
            return None
        normalized_expected = {label.casefold() for label in expected_labels}
        for index in range(self._tabs_panel.count()):
            if self._tabs_panel.tabText(index).casefold() in normalized_expected:
                return index
        return None

    def _activate_robot_navigation(self) -> None:
        telemetry_tab_index = self._find_tab_index_by_labels(("Telemetry", "Robot"))
        if telemetry_tab_index is None:
            self.statusBar().showMessage("Brak zakładki Robot/Telemetry — przełączenie pominięte.", 4000)
            return
        self._tabs_panel.setCurrentIndex(telemetry_tab_index)

    def _activate_map_navigation(self) -> None:
        map_tab_index = self._find_tab_index_by_labels(("Map", "Mapa"))
        if map_tab_index is None:
            self.statusBar().showMessage("Brak zakładki Map/Mapa — funkcja chwilowo niedostępna.", 4000)
            return
        self._tabs_panel.setCurrentIndex(map_tab_index)

    def _build_safe_tab(self, panel_name: str, panel_cls: type[QWidget]) -> QWidget:
        """Build single tab with local failure boundary (only this panel becomes unavailable)."""
        now = utc_now()
        self._supervisor.register_channel(panel_name)
        self._supervisor.heartbeat_channel(panel_name, now)

        try:
            # [AI-CHANGE | 2026-04-30 23:20 UTC | v0.201]
            # CO ZMIENIONO: Dodano specjalne tworzenie `MapTab` z `map_config` zamiast domyślnego konstruktora.
            # DLACZEGO: Zakładka mapy wymaga parametrów bezpieczeństwa z konfiguracji i nie może polegać na hardcodzie.
            # JAK TO DZIAŁA: Dla `MapTab` przekazujemy `map_config`; pozostałe karty są tworzone jak wcześniej.
            # TODO: Ujednolicić fabrykę kart z mapowaniem klas na argumenty konstruktorów.
            panel = panel_cls(self, map_config=self._map_config) if panel_cls is MapTab else panel_cls(self)
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
        self._status_bar = status_bar
        self._refresh_runtime_status()
        return status_bar

    def _refresh_runtime_status(self) -> None:
        """Odświeża widoczne statusy na podstawie aktualnego snapshotu StateStore."""
        self._operator_alerts.sync_from_snapshot(self._state_store.snapshot())
        playback = self._render_value(self._state_store.get(STATE_KEY_PLAYBACK_STATUS))
        recording = self._render_value(self._state_store.get(STATE_KEY_RECORDING_STATUS))
        connection = self._render_value(
            self._state_store.get(STATE_KEY_ROS_CONNECTION_STATUS),
            fallback="ROZŁĄCZONY",
        )
        source_item = self._state_store.get(STATE_KEY_DATA_SOURCE_MODE)
        incidents_count = len(self._supervisor.incidents())
        action_status = self._render_value(self._state_store.get(STATE_KEY_ACTION_STATUS))
        action_progress = self._render_value(self._state_store.get(STATE_KEY_ACTION_PROGRESS))
        action_result = self._render_value(self._state_store.get(STATE_KEY_ACTION_RESULT))
        dependency_message = self._render_dependency_status()
        version_message = self._render_version_status()

        if self._connection_label is not None:
            self._connection_label.setText(f"Połączenie ROS: {connection}")
        if self._source_quality_label is not None:
            self._source_quality_label.setText(f"Jakość źródła: {self._render_quality(source_item)}")
        self._refresh_map_tab_from_snapshot()
        if self._status_bar is not None:
            self._status_bar.showMessage(
                f"{version_message} | STATUS: ROS={connection} PLAYBACK={playback} RECORDING={recording} "
                f"ACTION={action_status} PROGRESS={action_progress} RESULT={action_result} INCIDENTS={incidents_count} | "
                f"{dependency_message}"
            )

    # [AI-CHANGE | 2026-04-30 16:20 UTC | v0.201]
    # CO ZMIENIONO: Dodano cykliczne przekazywanie snapshotu mapy z MainWindow do MapTab.
    # DLACZEGO: Zakładka mapy nie może pozostawać w stanie domyślnym; musi otrzymywać aktualny rekord store.
    # JAK TO DZIAŁA: Podczas każdego odświeżenia UI MainWindow wyszukuje instancję MapTab i przekazuje
    #                pełny snapshot przez adapter `update_from_store_snapshot`, który stosuje twardy fallback do None.
    # TODO: Dodać sygnał Qt emitowany tylko przy zmianach kluczy mapy, aby ograniczyć koszt pełnego odświeżania.
    def _refresh_map_tab_from_snapshot(self) -> None:
        if self._tabs_panel is None:
            return
        snapshot = self._state_store.snapshot()
        for index in range(self._tabs_panel.count()):
            widget = self._tabs_panel.widget(index)
            if isinstance(widget, MapTab):
                widget.update_from_store_snapshot(snapshot)
                return

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
