"""Extensions tab with plugin discovery and activation status."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QApplication,
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

from robot_mission_control.core import StateStore, StateValue
from .state_rendering import is_actionable, render_state


# [AI-CHANGE | 2026-04-23 13:40 UTC | v0.186]
# CO ZMIENIONO: Zastąpiono placeholder ExtensionsTab widokiem listy wykrytych pluginów z katalogu
#               `robot_mission_control/plugins`, statusem aktywacji każdego rozszerzenia oraz sekcją
#               niezaimplementowanych integracji jako disabled przyciski z etykietą
#               "NIEDOSTĘPNE W TEJ WERSJI".
# DLACZEGO: Operator i inżynier muszą jednoznacznie widzieć, jakie rozszerzenia zostały wykryte i czy
#           ich stan aktywacji jest wiarygodny; jednocześnie niedostępne funkcje muszą być jawnie
#           zablokowane, aby nie sugerować gotowości.
# JAK TO DZIAŁA: Zakładka skanuje moduły pluginów w katalogu projektu, a następnie cyklicznie odczytuje
#                snapshot StateStore. Dla każdej pozycji pokazuje aktywację tylko przy quality == VALID;
#                w przeciwnym razie wymusza bezpieczny fallback "BRAK DANYCH" i status niepewny.
# TODO: Zastąpić heurystykę klucza `plugin.<name>.active` formalnym kontraktem API pluginów i rejestrem capabilities.
class ExtensionsTab(QWidget):
    """Panel rozszerzeń z konserwatywną prezentacją statusów."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._state_store = self._resolve_state_store(parent)
        self._plugin_names = self._discover_plugins()

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(8)

        title = QLabel("Wykryte rozszerzenia", self)
        title.setStyleSheet("font-size: 16px; font-weight: 600;")
        root.addWidget(title)

        self._plugins_table = QTableWidget(self)
        self._plugins_table.setColumnCount(4)
        self._plugins_table.setHorizontalHeaderLabels(["Plugin", "Aktywacja", "Quality", "Reason code"])
        self._plugins_table.verticalHeader().setVisible(False)
        self._plugins_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._plugins_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self._plugins_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._plugins_table.itemSelectionChanged.connect(self._sync_plugin_action_buttons)
        header = self._plugins_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        root.addWidget(self._plugins_table)

        # [AI-CHANGE | 2026-04-25 08:57 UTC | v0.202]
        # CO ZMIENIONO: Dodano realne akcje operatorskie w ExtensionsTab:
        #               ręczne odświeżenie tabeli oraz kopiowanie szczegółów wybranego pluginu.
        # DLACZEGO: Celem jest redukcja martwych punktów UI i skrócenie czasu reakcji operatora
        #           przy eskalacji problemów pluginów (bez przepisywania danych ręcznie).
        # JAK TO DZIAŁA: „Odśwież pluginy teraz” wymusza natychmiastowy odczyt snapshotu, a
        #                „Kopiuj szczegóły pluginu” buduje bezpieczny tekst diagnostyczny tylko
        #                dla jednoznacznie wybranego wiersza i zapisuje go do schowka.
        # TODO: Dodać akcję „Pokaż historię jakości” opartą o retencję próbek pluginów.
        actions_card = QFrame(self)
        actions_layout = QGridLayout(actions_card)
        self._refresh_now_button = QPushButton("Odśwież pluginy teraz", actions_card)
        self._refresh_now_button.clicked.connect(self._refresh_plugin_table)
        actions_layout.addWidget(self._refresh_now_button, 0, 0)
        self._copy_selected_plugin_button = QPushButton("Kopiuj szczegóły pluginu", actions_card)
        self._copy_selected_plugin_button.clicked.connect(self._copy_selected_plugin_details)
        actions_layout.addWidget(self._copy_selected_plugin_button, 0, 1)
        root.addWidget(actions_card)

        integrations_card = QFrame(self)
        integrations_layout = QGridLayout(integrations_card)
        integrations_layout.addWidget(QLabel("Integracje (roadmapa):", integrations_card), 0, 0, 1, 2)

        self._cloud_sync_button = QPushButton("Cloud Sync — NIEDOSTĘPNE W TEJ WERSJI", integrations_card)
        self._cloud_sync_button.setEnabled(False)
        integrations_layout.addWidget(self._cloud_sync_button, 1, 0)

        self._remote_registry_button = QPushButton("Remote Registry — NIEDOSTĘPNE W TEJ WERSJI", integrations_card)
        self._remote_registry_button.setEnabled(False)
        integrations_layout.addWidget(self._remote_registry_button, 1, 1)

        self._marketplace_button = QPushButton("Marketplace — NIEDOSTĘPNE W TEJ WERSJI", integrations_card)
        self._marketplace_button.setEnabled(False)
        integrations_layout.addWidget(self._marketplace_button, 2, 0)

        root.addWidget(integrations_card)

        self._refresh_timer = QTimer(self)
        # [AI-CHANGE | 2026-04-23 18:29 UTC | v0.195]
        # CO ZMIENIONO: ExtensionsTab odczytuje interwał timera z konfiguracji UI zamiast stałej.
        # DLACZEGO: Hardcode 1500 ms utrudniał strojenie częstotliwości odświeżania listy pluginów.
        # JAK TO DZIAŁA: Zakładka używa klucza `extensions_tab_refresh_interval_ms` z MainWindow,
        #                a przy braku konfiguracji przechodzi na fallback 1500 ms.
        # TODO: Dodać ręczny przycisk „odśwież teraz” niezależny od timera.
        window = self.window()
        timer_fn = getattr(window, "ui_timer_interval_ms", None)
        interval_ms = timer_fn("extensions_tab_refresh_interval_ms", default_ms=1500) if callable(timer_fn) else 1500
        self._refresh_timer.setInterval(interval_ms)
        self._refresh_timer.timeout.connect(self._refresh_plugin_table)
        self._refresh_timer.start()

        self._refresh_plugin_table()

    def _resolve_state_store(self, parent: QWidget | None) -> StateStore | None:
        window = parent.window() if parent is not None else None
        return getattr(window, "state_store", None)

    def _discover_plugins(self) -> tuple[str, ...]:
        plugins_dir = Path(__file__).resolve().parents[2] / "plugins"
        discovered = sorted(
            module_path.stem
            for module_path in plugins_dir.glob("*.py")
            if module_path.is_file() and module_path.stem != "__init__"
        )
        if not discovered:
            return ("(brak pluginów)",)
        return tuple(discovered)

    def _refresh_plugin_table(self) -> None:
        snapshot = self._state_store.snapshot() if self._state_store is not None else {}
        self._plugins_table.setRowCount(len(self._plugin_names))

        for row_index, plugin_name in enumerate(self._plugin_names):
            state_item = self._state_item_for_plugin(plugin_name, snapshot)
            self._plugins_table.setItem(row_index, 0, QTableWidgetItem(plugin_name))
            self._plugins_table.setItem(row_index, 1, QTableWidgetItem(self._render_activation(state_item)))
            self._plugins_table.setItem(row_index, 2, QTableWidgetItem(self._render_quality(state_item)))
            self._plugins_table.setItem(row_index, 3, QTableWidgetItem(self._render_reason_code(state_item)))
        self._sync_plugin_action_buttons()

    # [AI-CHANGE | 2026-04-25 08:57 UTC | v0.202]
    # CO ZMIENIONO: Dodano helpery do akcji operatorskich dla zaznaczonego pluginu.
    # DLACZEGO: Akcje UI muszą działać deterministycznie i nie mogą wykonywać operacji,
    #           gdy selekcja jest niejednoznaczna albo brak danych.
    # JAK TO DZIAŁA: Przycisk kopiowania aktywuje się wyłącznie przy poprawnym wyborze wiersza;
    #                treść do schowka zawiera nazwę pluginu, aktywację, quality i reason_code.
    # TODO: Rozszerzyć kopiowany payload o timestamp próbki i źródło po stronie bridge.
    def _sync_plugin_action_buttons(self) -> None:
        self._copy_selected_plugin_button.setEnabled(self._selected_plugin_name() is not None)

    def _selected_plugin_name(self) -> str | None:
        selected_items = self._plugins_table.selectedItems()
        if not selected_items:
            return None
        selected_row = selected_items[0].row()
        plugin_item = self._plugins_table.item(selected_row, 0)
        if plugin_item is None:
            return None
        plugin_name = plugin_item.text().strip()
        if not plugin_name or plugin_name == "(brak pluginów)":
            return None
        return plugin_name

    def _copy_selected_plugin_details(self) -> None:
        plugin_name = self._selected_plugin_name()
        if plugin_name is None:
            return
        snapshot = self._state_store.snapshot() if self._state_store is not None else {}
        state_item = self._state_item_for_plugin(plugin_name, snapshot)
        payload = (
            f"plugin={plugin_name} | activation={self._render_activation(state_item)} "
            f"| quality={self._render_quality(state_item)} | reason_code={self._render_reason_code(state_item)}"
        )
        clipboard = QApplication.clipboard()
        if clipboard is not None:
            clipboard.setText(payload)

    def _state_item_for_plugin(self, plugin_name: str, snapshot: dict[str, StateValue]) -> StateValue | None:
        if plugin_name == "(brak pluginów)":
            return None
        activation_key = f"plugin.{plugin_name}.active"
        return snapshot.get(activation_key)

    # [AI-CHANGE | 2026-04-23 17:10 UTC | v0.192]
    # CO ZMIENIONO: Ujednolicono renderowanie statusu aktywacji/quality pluginów przez helpery
    #               `is_actionable` i `render_state` z modułu współdzielonego.
    # DLACZEGO: Karta Extensions musi respektować ten sam kontrakt bezpieczeństwa co pozostałe karty:
    #           brak wartości operacyjnej przy quality != VALID.
    # JAK TO DZIAŁA: `is_actionable` blokuje interpretację aktywacji dla próbek niepewnych, a
    #                `render_state` dostarcza spójną etykietę stanu jakości do kolumny tabeli.
    # TODO: Dodać osobny znacznik „NIEPEWNE AKTYWOWANIE” dla przypadków z value=True i quality!=VALID.
    def _render_activation(self, item: StateValue | None) -> str:
        if not is_actionable(item):
            return "BRAK DANYCH"
        # [AI-CHANGE | 2026-04-29 13:35 UTC | v0.333]
        # CO ZMIENIONO: Dodano asercję zawężającą próbkę aktywacji pluginu po walidacji jakości.
        # DLACZEGO: `mypy` nie wie, że `is_actionable` odrzuca `None`, a UI nie powinno interpretować aktywacji
        #           pluginu bez pewnej próbki.
        # JAK TO DZIAŁA: Dla braku danych zwracamy `BRAK DANYCH`; dopiero potwierdzona próbka trafia do mapowania
        #                `AKTYWNE`/`NIEAKTYWNE`.
        # TODO: Dodać typowany helper `actionable_value`, który zwraca wartość albo `None` bez potrzeby asercji w UI.
        assert item is not None
        if bool(item.value):
            return "AKTYWNE"
        return "NIEAKTYWNE"

    def _render_quality(self, item: StateValue | None) -> str:
        return render_state(item)

    def _render_reason_code(self, item: StateValue | None) -> str:
        if item is None:
            return "missing_state"
        return item.reason_code or "-"
