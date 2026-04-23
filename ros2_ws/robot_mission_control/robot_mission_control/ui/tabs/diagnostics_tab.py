"""Diagnostics tab with active issues and dependency status."""

from __future__ import annotations

from datetime import datetime, timezone

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHeaderView,
    QLabel,
    QPushButton,
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
        self._last_refresh_value = QLabel("Ostatnie odświeżenie: -", controls)
        controls_layout.addWidget(self._refresh_button, 0, 0)
        controls_layout.addWidget(self._last_refresh_value, 0, 1)
        root.addWidget(controls)

        self._issues_table = QTableWidget(self)
        self._issues_table.setColumnCount(5)
        self._issues_table.setHorizontalHeaderLabels(["Klucz", "Źródło", "Reason code", "Timestamp", "Severity"])
        self._issues_table.verticalHeader().setVisible(False)
        self._issues_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._issues_table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self._issues_table.setAlternatingRowColors(True)
        issues_header = self._issues_table.horizontalHeader()
        issues_header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        issues_header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        issues_header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        issues_header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
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
        self._refresh_timer.setInterval(1200)
        self._refresh_timer.timeout.connect(self._refresh_view)
        self._refresh_timer.start()

        self._refresh_view()

    def _resolve_state_store(self, parent: QWidget | None) -> StateStore | None:
        window = parent.window() if parent is not None else None
        return getattr(window, "state_store", None)

    def _refresh_view(self) -> None:
        snapshot = self._state_store.snapshot() if self._state_store is not None else {}
        self._render_issues_table(snapshot)
        self._render_dependency_status(snapshot)
        self._render_ros_connection(snapshot)
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        self._last_refresh_value.setText(f"Ostatnie odświeżenie: {now}")

    def _render_issues_table(self, snapshot: dict[str, StateValue]) -> None:
        problem_rows: list[tuple[str, StateValue]] = []
        for key, item in snapshot.items():
            if item.quality is DataQuality.VALID:
                continue
            problem_rows.append((key, item))

        problem_rows.sort(key=lambda row: row[0])
        self._issues_table.setRowCount(len(problem_rows))

        for row_index, (key, item) in enumerate(problem_rows):
            self._issues_table.setItem(row_index, 0, QTableWidgetItem(key))
            self._issues_table.setItem(row_index, 1, QTableWidgetItem(item.source or "unknown"))
            self._issues_table.setItem(row_index, 2, QTableWidgetItem(item.reason_code or "-"))
            self._issues_table.setItem(row_index, 3, QTableWidgetItem(self._format_timestamp(item.timestamp)))
            self._issues_table.setItem(row_index, 4, QTableWidgetItem(self._severity_for_quality(item.quality)))

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

    def _severity_for_quality(self, quality: DataQuality) -> str:
        severity_map: dict[DataQuality, str] = {
            DataQuality.ERROR: "CRITICAL",
            DataQuality.UNAVAILABLE: "HIGH",
            DataQuality.STALE: "MEDIUM",
            DataQuality.VALID: "INFO",
        }
        return severity_map.get(quality, "HIGH")

    def _format_timestamp(self, timestamp: datetime) -> str:
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)
        return timestamp.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
