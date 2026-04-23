"""Extensions tab with plugin discovery and activation status."""

from __future__ import annotations

from pathlib import Path

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
        self._plugins_table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        header = self._plugins_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        root.addWidget(self._plugins_table)

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
        self._refresh_timer.setInterval(1500)
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
        if bool(item.value):
            return "AKTYWNE"
        return "NIEAKTYWNE"

    def _render_quality(self, item: StateValue | None) -> str:
        return render_state(item)

    def _render_reason_code(self, item: StateValue | None) -> str:
        if item is None:
            return "missing_state"
        return item.reason_code or "-"
