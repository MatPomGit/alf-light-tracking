"""Diagnostics tab with active issues and dependency status."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from PySide6.QtCore import QTimer
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHeaderView,
    QCheckBox,
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
from robot_mission_control.ui.operator_alerts import OperatorAlerts
from .operator_guidance import resolve_operator_guidance
from .state_rendering import (
    is_actionable,
    quality_color_hex,
    render_card_value_with_warning,
    render_quality,
    render_quality_with_icon,
    render_value,
    severity_from_quality,
)

# [AI-CHANGE | 2026-04-25 12:40 UTC | v0.201]
# CO ZMIENIONO: DiagnosticsTab importuje teraz współdzielony resolver guidance operatorskiego.
# DLACZEGO: Dzięki temu wszystkie zakładki używają jednej mapy „co się stało/co zrobić”.
# JAK TO DZIAŁA: `resolve_operator_guidance` zastępuje lokalne słowniki mapowań i fallbacki.
# TODO: Dodać test kontraktowy pilnujący, że wszystkie karty używają tego samego resolvera.


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
    quality_label: str
    quality_color: str
    is_problem: bool
    source: str
    cause: str
    meaning: str
    action: str
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
    _SEVERITY_PRIORITY: dict[str, int] = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3, "INFO": 4}

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
        self._operator_alerts = self._resolve_operator_alerts(parent)

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
        # [AI-CHANGE | 2026-04-25 16:20 UTC | v0.201]
        # CO ZMIENIONO: Dodano filtry operatorskie „Tylko krytyczne” i „Tylko problemy”
        #               bezpośrednio w panelu Diagnostics.
        # DLACZEGO: Operator powinien jednym kliknięciem zawęzić listę do incydentów pilnych,
        #           aby skrócić czas reakcji podczas eskalacji.
        # JAK TO DZIAŁA: `Tylko problemy` ukrywa wiersze z próbkami VALID, a `Tylko krytyczne`
        #                pozostawia wyłącznie rekordy o severity CRITICAL.
        # TODO: Zapamiętywać stan filtrów per operator (profil dyżurny).
        self._critical_only_checkbox = QCheckBox("Tylko krytyczne", controls)
        self._critical_only_checkbox.toggled.connect(self._refresh_view)
        self._problems_only_checkbox = QCheckBox("Tylko problemy", controls)
        self._problems_only_checkbox.setChecked(True)
        self._problems_only_checkbox.toggled.connect(self._refresh_view)
        # [AI-CHANGE | 2026-04-25 08:57 UTC | v0.202]
        # CO ZMIENIONO: Przycisk ACK został uruchomiony i podpięty do potwierdzania aktywnych alertów
        #               z rejestru `OperatorAlerts` zamiast pozostawienia martwej kontrolki.
        # DLACZEGO: Priorytet operatorski wymaga szybkiego potwierdzania incydentów bez opuszczania
        #           zakładki Diagnostics; martwy przycisk utrudniał pracę dyżurną.
        # JAK TO DZIAŁA: Kliknięcie ACK potwierdza alert dla zaznaczonego wiersza (po `state_key`),
        #                a gdy brak selekcji, potwierdzany jest najnowszy niepotwierdzony alert aktywny.
        # TODO: Dodać dialog wyboru operatora i powód ACK (np. "analiza w toku", "eskalowano L2").
        self._ack_button = QPushButton("ACK (0)", controls)
        self._ack_button.clicked.connect(self._ack_selected_or_latest_alert)
        self._last_refresh_value = QLabel("Ostatnie odświeżenie: -", controls)
        controls_layout.addWidget(self._refresh_button, 0, 0)
        controls_layout.addWidget(self._critical_only_checkbox, 0, 1)
        controls_layout.addWidget(self._problems_only_checkbox, 0, 2)
        controls_layout.addWidget(self._ack_button, 0, 3)
        controls_layout.addWidget(self._last_refresh_value, 0, 4)
        root.addWidget(controls)

        # [AI-CHANGE | 2026-04-24 12:10 UTC | v0.203]
        # CO ZMIENIONO: Rozszerzono tabelę diagnostyczną o kolumny „Co to znaczy” i „Co zrobić”.
        # DLACZEGO: Operator ma dostać gotową interpretację kodu i instrukcję reakcji bez analizy logów.
        # JAK TO DZIAŁA: Tabela ma teraz 7 kolumn; dwie nowe kolumny renderują znaczenie i zalecane działanie
        #                wyliczane na podstawie mapy najczęstszych kodów diagnostycznych.
        # TODO: Dodać możliwość kopiowania pojedynczego wiersza (kod + instrukcja) do schowka operatora.
        self._issues_table = QTableWidget(self)
        self._issues_table.setColumnCount(7)
        self._issues_table.setHorizontalHeaderLabels(
            ["Severity", "Źródło", "Przyczyna", "Co to znaczy", "Co zrobić", "Klucz", "Czas UTC"]
        )
        self._issues_table.verticalHeader().setVisible(False)
        self._issues_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._issues_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._issues_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._issues_table.setAlternatingRowColors(True)
        self._issues_table.itemSelectionChanged.connect(self._sync_ack_button_state)
        issues_header = self._issues_table.horizontalHeader()
        issues_header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        issues_header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        issues_header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        issues_header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        issues_header.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        issues_header.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        issues_header.setSectionResizeMode(6, QHeaderView.ResizeMode.ResizeToContents)
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

    def _resolve_operator_alerts(self, parent: QWidget | None) -> OperatorAlerts | None:
        window = parent.window() if parent is not None else None
        candidate = getattr(window, "operator_alerts", None)
        return candidate if isinstance(candidate, OperatorAlerts) else None

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
        self._sync_ack_button_state()
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        self._last_refresh_value.setText(f"Ostatnie odświeżenie: {now}")

    # [AI-CHANGE | 2026-04-25 08:57 UTC | v0.202]
    # CO ZMIENIONO: Dodano logikę aktualizacji i obsługi ACK: mapowanie zaznaczonego problemu na alert,
    #               fallback do najnowszego alertu oraz automatyczne odświeżanie etykiety przycisku.
    # DLACZEGO: Operator powinien widzieć, czy ACK jest możliwe i ile alertów nadal wymaga potwierdzenia,
    #           aby szybko zamknąć pętlę reakcji bez ryzyka ACK "w ciemno".
    # JAK TO DZIAŁA: `_sync_ack_button_state` liczy niepotwierdzone alerty aktywne i blokuje ACK,
    #                gdy brak kandydatów; `_ack_selected_or_latest_alert` wykonuje ACK tylko przy
    #                jednoznacznym dopasowaniu do alertu aktywnego.
    # TODO: Dodać licznik ACK per zmiana operatorska i telemetrykę czasu od otwarcia alertu do ACK.
    def _sync_ack_button_state(self) -> None:
        if self._operator_alerts is None:
            self._ack_button.setText("ACK — NIEDOSTĘPNE W TEJ WERSJI")
            self._ack_button.setEnabled(False)
            return

        pending_alerts = [alert for alert in self._operator_alerts.active_alerts() if not alert.acknowledged]
        self._ack_button.setText(f"ACK ({len(pending_alerts)})")
        selected_key = self._selected_state_key()
        if selected_key is None:
            self._ack_button.setEnabled(bool(pending_alerts))
            return
        self._ack_button.setEnabled(any(alert.state_key == selected_key for alert in pending_alerts))

    def _selected_state_key(self) -> str | None:
        selected_items = self._issues_table.selectedItems()
        if not selected_items:
            return None
        selected_row = selected_items[0].row()
        key_item = self._issues_table.item(selected_row, 5)
        if key_item is None:
            return None
        state_key = key_item.text().strip()
        return state_key or None

    def _ack_selected_or_latest_alert(self) -> None:
        if self._operator_alerts is None:
            return
        active_alerts = self._operator_alerts.active_alerts()
        pending_alerts = [alert for alert in active_alerts if not alert.acknowledged]
        if not pending_alerts:
            self._sync_ack_button_state()
            return

        selected_key = self._selected_state_key()
        target_alert = next((alert for alert in pending_alerts if alert.state_key == selected_key), None)
        if target_alert is None:
            target_alert = pending_alerts[0]

        self._operator_alerts.ack_alert(alert_id=target_alert.alert_id, operator_id="diagnostics_ui")
        self._sync_ack_button_state()

    # [AI-CHANGE | 2026-04-23 21:10 UTC | v0.194]
    # CO ZMIENIONO: Tabela diagnostyczna jest filtrowana (`tylko problemy`/`tylko krytyczne`)
    #               i renderuje severity wraz z kolorami/ikonami quality.
    # DLACZEGO: Zapewnia to pełną transparentność: każdy wpis problemu ma widoczną przyczynę
    #           i czas wystąpienia, a operator szybciej odróżnia incydenty krytyczne od informacyjnych.
    # JAK TO DZIAŁA: `_build_problem_rows` zwraca pełną listę wpisów, następnie `_apply_row_filters`
    #                ogranicza ją wg checkboxów, a `_apply_row_visual_style` koduje kolor i ikonę.
    # TODO: Dodać tryb filtrowania po subsystemie (vision/control/navigation).
    def _render_issues_table(self, snapshot: dict[str, StateValue]) -> None:
        all_rows = self._build_problem_rows(snapshot)
        filtered_rows = self._apply_row_filters(all_rows)
        self._issues_table.setRowCount(len(filtered_rows))

        for row_index, problem in enumerate(filtered_rows):
            severity_item = QTableWidgetItem(problem.severity)
            self._apply_row_visual_style(severity_item, problem.quality_label, problem.quality_color)
            self._issues_table.setItem(row_index, 0, severity_item)
            self._issues_table.setItem(row_index, 1, QTableWidgetItem(problem.source))
            self._issues_table.setItem(row_index, 2, QTableWidgetItem(problem.cause))
            self._issues_table.setItem(row_index, 3, QTableWidgetItem(problem.meaning))
            self._issues_table.setItem(row_index, 4, QTableWidgetItem(problem.action))
            self._issues_table.setItem(row_index, 5, QTableWidgetItem(problem.state_key))
            self._issues_table.setItem(row_index, 6, QTableWidgetItem(self._format_timestamp(problem.timestamp)))

    # [AI-CHANGE | 2026-04-25 12:40 UTC | v0.201]
    # CO ZMIENIONO: DiagnosticsTab korzysta ze współdzielonego modułu `operator_guidance`
    #               zamiast lokalnego słownika `COMMON_CODE_HINTS`.
    # DLACZEGO: Ujednolicamy komunikaty „co się stało/co zrobić” między Diagnostics/Overview/Controls/Rosbag,
    #           aby operator dostawał tę samą instrukcję niezależnie od miejsca obserwacji problemu.
    # JAK TO DZIAŁA: Dla każdego rekordu nie-VALID wyliczamy `cause_code` i wywołujemy
    #                `resolve_operator_guidance`, a następnie zapisujemy `meaning/action` do `ProblemRow`.
    # TODO: Dodać telemetrykę pokrycia mapowania (ile kodów trafia na fallback w produkcji).
    def _build_problem_rows(self, snapshot: dict[str, StateValue]) -> list[ProblemRow]:
        rows: list[ProblemRow] = []
        for state_key, item in snapshot.items():
            cause_code = item.reason_code or item.quality.value
            guidance = resolve_operator_guidance(reason_code=cause_code, status=str(item.value))
            rows.append(
                ProblemRow(
                    state_key=state_key,
                    severity=severity_from_quality(item),
                    quality_label=render_quality_with_icon(item),
                    quality_color=quality_color_hex(item),
                    is_problem=item.quality is not DataQuality.VALID,
                    source=item.source or "unknown",
                    cause=cause_code,
                    meaning=guidance.meaning,
                    action=guidance.action,
                    timestamp=item.timestamp,
                )
            )
        return sorted(
            rows,
            key=lambda row: (
                self._SEVERITY_PRIORITY.get(row.severity, 99),
                -row.timestamp.timestamp(),
                row.state_key,
            ),
        )

    # [AI-CHANGE | 2026-04-25 16:20 UTC | v0.201]
    # CO ZMIENIONO: Dodano etap filtrowania rekordów po wyborach operatora.
    # DLACZEGO: Jedna tabela ma obsłużyć zarówno przegląd pełny, jak i tryb alarmowy „tylko krytyczne”.
    # JAK TO DZIAŁA: Metoda respektuje dwa niezależne checkboxy i nigdy nie dopuszcza
    #                promocji wpisu niekrytycznego do widoku „tylko krytyczne”.
    # TODO: Dodać licznik wyników po filtracji (np. „8/42 rekordów”).
    def _apply_row_filters(self, rows: list[ProblemRow]) -> list[ProblemRow]:
        critical_only = self._critical_only_checkbox.isChecked()
        problems_only = self._problems_only_checkbox.isChecked()
        filtered_rows = rows
        if problems_only:
            filtered_rows = [row for row in filtered_rows if row.is_problem]
        if critical_only:
            filtered_rows = [row for row in filtered_rows if row.severity == "CRITICAL"]
        return filtered_rows

    # [AI-CHANGE | 2026-04-25 16:20 UTC | v0.201]
    # CO ZMIENIONO: Dodano stylowanie komórki severity na bazie mapowania quality -> kolor.
    # DLACZEGO: Kolor skraca czas rozpoznania priorytetu incydentu bez czytania pełnej treści.
    # JAK TO DZIAŁA: Komórka dostaje kolor foreground zgodny z `quality_color_hex`,
    #                a dodatkowo dopisywana jest ikona quality dla natychmiastowej orientacji.
    # TODO: Rozważyć też kolor tła całego wiersza dla rekordów CRITICAL.
    def _apply_row_visual_style(self, severity_item: QTableWidgetItem, quality_label: str, quality_color: str) -> None:
        severity_item.setForeground(QColor(quality_color))
        severity_item.setText(f"{severity_item.text()} | {quality_label}")

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
        # [AI-CHANGE | 2026-04-24 10:20 UTC | v0.200]
        # CO ZMIENIONO: W karcie diagnostycznej łączność ROS renderuje teraz jawny komunikat
        #               ostrzegawczy z reason_code dla quality != VALID.
        # DLACZEGO: Pole łączności jest krytyczne operacyjnie i nie może ukrywać przyczyny odrzucenia próbki.
        # JAK TO DZIAŁA: Dla próbki nie-VALID wyświetlany jest format `⚠ BRAK DANYCH | reason_code=...`,
        #                a przy próbce VALID pozostaje bieżąca wartość stanu połączenia.
        # TODO: Dodać osobny licznik czasu od ostatniej próbki VALID w etykiecie łączności.
        self._ros_connection_value.setText(render_card_value_with_warning(item, fallback="BRAK DANYCH"))

    def _format_timestamp(self, timestamp: datetime) -> str:
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)
        return timestamp.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
