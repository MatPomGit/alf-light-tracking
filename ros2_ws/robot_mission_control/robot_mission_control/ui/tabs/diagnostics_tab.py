"""Diagnostics tab with active issues and dependency status."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QAbstractItemView,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from robot_mission_control.core import (
    STATE_KEY_DEPENDENCY_STATUS,
    STATE_KEY_ROS_CONNECTION_STATUS,
    DataQuality,
    StateStore,
    StateValue,
)
from .state_rendering import is_actionable, render_quality, render_value


# [AI-CHANGE | 2026-04-23 21:10 UTC | v0.194]
# CO ZMIENIONO: Dodano model `ProblemRow` do deterministycznego renderowania tabeli problemów
#               bezpośrednio ze snapshotu StateStore.
# DLACZEGO: Kryterium ukończenia wymaga, aby każdy problem miał jawnie podane źródło, przyczynę
#           i czas wystąpienia, niezależnie od warstwy alertów operatorskich.
# JAK TO DZIAŁA: `ProblemRow` przechowuje klucz stanu, severity, source, cause i timestamp,
#                które są mapowane 1:1 z rekordów snapshotu o jakości różnej od VALID.
# TODO: Rozszerzyć `ProblemRow` o pole `domain`, aby grupować problemy wg subsystemów.
@dataclass(frozen=True, slots=True)
class ProblemRow:
    state_key: str
    severity: str
    source: str
    cause: str
    timestamp: datetime


# [AI-CHANGE | 2026-04-23 13:22 UTC | v0.184]
# CO ZMIENIONO: Zastąpiono placeholder DiagnosticsTab pełnym widokiem diagnostycznym z tabelą aktywnych
#               problemów (source/reason_code/timestamp/severity), sekcją statusu zależności i łączności ROS,
#               przyciskiem „Odśwież teraz” oraz pasywnym odświeżaniem przez QTimer.
# DLACZEGO: Operator potrzebuje jawnej diagnostyki stanu bieżącego na podstawie snapshotu StateStore bez ryzyka,
#           że UI zamaskuje błąd historycznie „zielonym” stanem.
# JAK TO DZIAŁA: Zakładka odczytuje wyłącznie aktualny snapshot i buduje rekord problemu dla każdego klucza,
#                którego quality != VALID; severity wynika bezpośrednio z jakości. Sekcja zależności opiera się
#                o STATE_KEY_DEPENDENCY_STATUS i nie pokazuje „OK”, jeśli aktualna jakość jest UNAVAILABLE/ERROR.
# TODO: Dodać filtrowanie po source/severity oraz eksport aktywnych problemów do pliku diagnostycznego CSV.
class DiagnosticsTab(QWidget):
    """Panel diagnostyczny oparty o aktualny stan StateStore."""

    # [AI-CHANGE | 2026-04-23 21:10 UTC | v0.194]
    # CO ZMIENIONO: Dostosowano inicjalizację tabeli diagnostycznej do widoku problemów opartych
    #               o snapshot (`severity`, `źródło`, `przyczyna`, `klucz`, `czas UTC`).
    # DLACZEGO: Operator musi widzieć pełny kontekst problemu bez przełączania się na inne panele.
    # JAK TO DZIAŁA: Konfiguracja kolumn i nagłówków odzwierciedla pola `ProblemRow`, dzięki czemu
    #                tabela pokazuje bezpośrednio dane z aktualnego snapshotu StateStore.
    # TODO: Dodać checkbox ukrywający problemy o severity MEDIUM/LOW w trybie operacyjnym.
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._state_store = self._resolve_state_store(parent)

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(8)

        title = QLabel("Diagnostyka runtime", self)
        title.setStyleSheet("font-size: 16px; font-weight: 600;")
        root.addWidget(title)

        controls = QFrame(self)
        controls_layout = QGridLayout(controls)
        controls_layout.setContentsMargins(0, 0, 0, 0)
        self._refresh_button = QPushButton("Odśwież teraz", controls)
        self._refresh_button.clicked.connect(self._refresh_view)
        self._ack_button = QPushButton("ACK — NIEDOSTĘPNE W TEJ WERSJI", controls)
        self._ack_button.setEnabled(False)
        self._last_refresh_value = QLabel("Ostatnie odświeżenie: -", controls)
        controls_layout.addWidget(self._refresh_button, 0, 0)
        controls_layout.addWidget(self._ack_button, 0, 1)
        controls_layout.addWidget(self._last_refresh_value, 0, 2)
        root.addWidget(controls)

        self._issues_table = QTableWidget(self)
        self._issues_table.setColumnCount(5)
        self._issues_table.setHorizontalHeaderLabels(["Severity", "Źródło", "Przyczyna", "Klucz", "Czas UTC"])
        self._issues_table.verticalHeader().setVisible(False)
        self._issues_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._issues_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._issues_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._issues_table.setAlternatingRowColors(True)
        issues_header = self._issues_table.horizontalHeader()
        issues_header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        issues_header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        issues_header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        issues_header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        issues_header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        root.addWidget(self._issues_table)

        dependency_card = QFrame(self)
        dependency_layout = QGridLayout(dependency_card)
        dependency_layout.addWidget(QLabel("Status zależności:"), 0, 0)
        self._dependency_status_value = QLabel("BRAK DANYCH", dependency_card)
        dependency_layout.addWidget(self._dependency_status_value, 0, 1)

        dependency_layout.addWidget(QLabel("Status połączenia ROS:"), 1, 0)
        self._ros_connection_value = QLabel("ROZŁĄCZONY", dependency_card)
        dependency_layout.addWidget(self._ros_connection_value, 1, 1)

        root.addWidget(dependency_card)

        self._refresh_timer = QTimer(self)
        # [AI-CHANGE | 2026-04-23 18:29 UTC | v0.195]
        # CO ZMIENIONO: DiagnosticsTab pobiera interwał odświeżania z konfiguracji timera UI.
        # DLACZEGO: Stała 1200 ms została usunięta, aby umożliwić zmianę rytmu diagnostyki z pliku YAML.
        # JAK TO DZIAŁA: Zakładka odczytuje `diagnostics_tab_refresh_interval_ms` z MainWindow;
        #                przy niedostępności konfiguracji używa fallbacku 1200 ms.
        # TODO: Wprowadzić osobne interwały dla sekcji alertów i sekcji tabel diagnostycznych.
        window = self.window()
        timer_fn = getattr(window, "ui_timer_interval_ms", None)
        interval_ms = timer_fn("diagnostics_tab_refresh_interval_ms", default_ms=1200) if callable(timer_fn) else 1200
        self._refresh_timer.setInterval(interval_ms)
        self._refresh_timer.timeout.connect(self._refresh_view)
        self._refresh_timer.start()

        self._refresh_view()

    def _resolve_state_store(self, parent: QWidget | None) -> StateStore | None:
        window = parent.window() if parent is not None else None
        return getattr(window, "state_store", None)

    # [AI-CHANGE | 2026-04-23 21:10 UTC | v0.194]
    # CO ZMIENIONO: Odświeżanie widoku przełączono na jedno źródło prawdy: bieżący `snapshot()`
    #               przekazywany bezpośrednio do renderowania tabeli problemów.
    # DLACZEGO: Eliminuje to ryzyko niespójności między rejestrem alertów a aktualnym stanem telemetrii.
    # JAK TO DZIAŁA: `_refresh_view` pobiera snapshot raz, a następnie używa go w renderowaniu problemów
    #                oraz sekcji statusu zależności/ROS, zachowując spójną chwilę czasową UI.
    # TODO: Dodać licznik trendu (ile problemów pojawiło się od poprzedniego odświeżenia).
    def _refresh_view(self) -> None:
        snapshot = self._state_store.snapshot() if self._state_store is not None else {}
        self._render_issues_table(snapshot)
        self._render_dependency_status(snapshot)
        self._render_ros_connection(snapshot)
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        self._last_refresh_value.setText(f"Ostatnie odświeżenie: {now}")

    # [AI-CHANGE | 2026-04-23 21:10 UTC | v0.194]
    # CO ZMIENIONO: Tabela problemów jest teraz budowana bezpośrednio ze snapshotu StateStore
    #               z kolumnami: severity, source, przyczyna, klucz i timestamp UTC.
    # DLACZEGO: Zapewnia to pełną transparentność: każdy wpis problemu ma widoczną przyczynę
    #           i czas wystąpienia, co spełnia kryterium ukończenia zadania.
    # JAK TO DZIAŁA: `_build_problem_rows` filtruje rekordy quality != VALID i mapuje je
    #                do `ProblemRow`; render tabeli nie zależy od historii/ACK alertów.
    # TODO: Dodać sortowanie po severity i czasie wraz z filtrem „tylko krytyczne”.
    def _render_issues_table(self, snapshot: dict[str, StateValue]) -> None:
        problem_rows = self._build_problem_rows(snapshot)
        self._issues_table.setRowCount(len(problem_rows))

        for row_index, problem in enumerate(problem_rows):
            severity_item = QTableWidgetItem(problem.severity)
            self._issues_table.setItem(row_index, 0, severity_item)
            self._issues_table.setItem(row_index, 1, QTableWidgetItem(problem.source))
            self._issues_table.setItem(row_index, 2, QTableWidgetItem(problem.cause))
            self._issues_table.setItem(row_index, 3, QTableWidgetItem(problem.state_key))
            self._issues_table.setItem(row_index, 4, QTableWidgetItem(self._format_timestamp(problem.timestamp)))

    def _build_problem_rows(self, snapshot: dict[str, StateValue]) -> list[ProblemRow]:
        rows: list[ProblemRow] = []
        severity_by_quality = {
            DataQuality.ERROR: "CRITICAL",
            DataQuality.UNAVAILABLE: "HIGH",
            DataQuality.STALE: "MEDIUM",
        }
        for state_key, item in snapshot.items():
            if item.quality is DataQuality.VALID:
                continue
            rows.append(
                ProblemRow(
                    state_key=state_key,
                    severity=severity_by_quality.get(item.quality, "LOW"),
                    source=item.source or "unknown",
                    cause=item.reason_code or item.quality.value,
                    timestamp=item.timestamp,
                )
            )
        return sorted(rows, key=lambda row: row.timestamp, reverse=True)

    def _render_dependency_status(self, snapshot: dict[str, StateValue]) -> None:
        item = snapshot.get(STATE_KEY_DEPENDENCY_STATUS)
        # [AI-CHANGE | 2026-04-23 14:15 UTC | v0.187]
        # CO ZMIENIONO: Ujednolicono fallbacki dependency/ROS przez helpery `render_value`,
        #               `render_quality` i `is_actionable`.
        # DLACZEGO: Diagnostyka ma stosować dokładnie tę samą regułę bezpieczeństwa, co reszta UI:
        #           brak wartości operacyjnej dla quality różnego od VALID.
        # JAK TO DZIAŁA: Dla nieoperacyjnej próbki widok zwraca `BRAK DANYCH` z dopisanym znacznikiem
        #                quality; szczególny komunikat STALE pozostaje jawny dla operatora.
        # TODO: Dodać mapowanie severity -> kolor etykiety statusu zależności i łączności ROS.
        if item is None:
            self._dependency_status_value.setText(render_value(None))
            return

        # Zasada bezpieczeństwa: nie wolno propagować historycznego "OK", gdy bieżący stan jest niepewny.
        if not is_actionable(item):
            if item.quality is DataQuality.STALE:
                self._dependency_status_value.setText("DANE PRZETERMINOWANE")
                return
            self._dependency_status_value.setText(f"{render_value(item)} ({render_quality(item)})")
            return

        report = item.value
        report_items = getattr(report, "items", None)
        if report_items is None:
            self._dependency_status_value.setText("FORMAT RAPORTU NIEOBSŁUGIWANY")
            return

        counters: dict[str, int] = {"OK": 0, "MISSING": 0, "WRONG_VERSION": 0, "UNKNOWN": 0}
        for dependency_item in report_items:
            status = str(getattr(getattr(dependency_item, "status", None), "value", "UNKNOWN"))
            counters[status] = counters.get(status, 0) + 1

        self._dependency_status_value.setText(
            " ".join(
                [
                    f"OK={counters.get('OK', 0)}",
                    f"MISSING={counters.get('MISSING', 0)}",
                    f"WRONG_VERSION={counters.get('WRONG_VERSION', 0)}",
                    f"UNKNOWN={counters.get('UNKNOWN', 0)}",
                ]
            )
        )

    def _render_ros_connection(self, snapshot: dict[str, StateValue]) -> None:
        item = snapshot.get(STATE_KEY_ROS_CONNECTION_STATUS)
        self._ros_connection_value.setText(render_value(item, fallback="ROZŁĄCZONY"))

    def _format_timestamp(self, timestamp: datetime) -> str:
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)
        return timestamp.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
