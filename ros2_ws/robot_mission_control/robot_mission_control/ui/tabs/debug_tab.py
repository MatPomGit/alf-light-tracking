"""Debug tab with engineering-mode diagnostics preview."""

from __future__ import annotations

from datetime import datetime, timezone

from PySide6.QtCore import QTimer
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QLabel, QPushButton, QTextEdit, QVBoxLayout, QWidget

from robot_mission_control.core import StateStore, StateValue
from .state_rendering import render_state, render_value


# [AI-CHANGE | 2026-04-23 13:40 UTC | v0.186]
# CO ZMIENIONO: Zastąpiono placeholder DebugTab aktywną zakładką debug z widocznym oznaczeniem
#               "TRYB INŻYNIERSKI", podglądem snapshotu StateStore (QTextEdit tylko do odczytu)
#               oraz szybkim eksportem diagnostyki do schowka.
# DLACZEGO: Inżynier potrzebuje szybkiego i bezpiecznego podglądu surowego stanu runtime bez ryzyka,
#           że dane niepewne zostaną pokazane jako poprawne; dodatkowo potrzebny jest natychmiastowy
#           transfer diagnostyki do zgłoszeń/incydentów.
# JAK TO DZIAŁA: Zakładka odświeża snapshot cyklicznie przez QTimer, renderuje każdą pozycję w formacie
#                tekstowym i maskuje value jako "BRAK DANYCH", gdy quality != VALID. Przycisk eksportu
#                kopiuje ostatni wyrenderowany tekst do schowka systemowego bez modyfikacji stanu aplikacji.
# TODO: Rozszerzyć eksport o opcjonalny zapis do pliku .log z podpisem hosta i numerem sesji operatora.
class DebugTab(QWidget):
    """Panel debug do bezpiecznego podglądu snapshotu StateStore."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._state_store = self._resolve_state_store(parent)
        self._last_export_payload = ""

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(8)

        self._engineering_badge = QLabel("TRYB INŻYNIERSKI", self)
        self._engineering_badge.setStyleSheet(
            "font-size: 12px; font-weight: 700; color: #111; background: #f4b400; padding: 4px 8px;"
        )
        root.addWidget(self._engineering_badge)

        self._title = QLabel("Podgląd snapshotu StateStore (read-only)", self)
        self._title.setStyleSheet("font-size: 15px; font-weight: 600;")
        root.addWidget(self._title)

        self._snapshot_view = QTextEdit(self)
        self._snapshot_view.setReadOnly(True)
        self._snapshot_view.setPlaceholderText("Oczekiwanie na dane diagnostyczne...")
        root.addWidget(self._snapshot_view)

        self._copy_button = QPushButton("Kopiuj diagnostykę do schowka", self)
        self._copy_button.clicked.connect(self._copy_diagnostics_to_clipboard)
        root.addWidget(self._copy_button)

        self._copy_status = QLabel("Schowek: brak eksportu", self)
        root.addWidget(self._copy_status)

        self._refresh_timer = QTimer(self)
        self._refresh_timer.setInterval(1000)
        self._refresh_timer.timeout.connect(self._refresh_snapshot_view)
        self._refresh_timer.start()

        self._refresh_snapshot_view()

    def _resolve_state_store(self, parent: QWidget | None) -> StateStore | None:
        window = parent.window() if parent is not None else None
        return getattr(window, "state_store", None)

    def _refresh_snapshot_view(self) -> None:
        snapshot = self._state_store.snapshot() if self._state_store is not None else {}
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        lines = [f"Debug snapshot @ {now}", f"keys={len(snapshot)}"]

        for key in sorted(snapshot.keys()):
            item = snapshot[key]
            lines.append(self._render_snapshot_line(key, item))

        if not snapshot:
            lines.append("- BRAK DANYCH (snapshot pusty)")

        self._last_export_payload = "\n".join(lines)
        self._snapshot_view.setPlainText(self._last_export_payload)

    # [AI-CHANGE | 2026-04-23 17:10 UTC | v0.192]
    # CO ZMIENIONO: DebugTab przełączono na wspólne helpery `render_value` i `render_state`
    #               podczas renderowania pojedynczej linii snapshotu.
    # DLACZEGO: Utrzymujemy jeden mechanizm maskowania wartości operacyjnych dla quality != VALID
    #           oraz wspólne nazewnictwo stanów `VALID/STALE/UNAVAILABLE/ERROR`.
    # JAK TO DZIAŁA: `render_value` zwraca bezpieczny fallback `BRAK DANYCH`, a `render_state`
    #                odpowiada za status jakości wpisywany do payloadu diagnostycznego.
    # TODO: Dodać opcję filtrowania wyłącznie rekordów `quality != VALID` w trybie debug.
    def _render_snapshot_line(self, key: str, item: StateValue) -> str:
        safe_value = render_value(item)
        timestamp = item.timestamp
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)
        timestamp_label = timestamp.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        return (
            f"- {key}: value={safe_value}; quality={render_state(item)}; reason={item.reason_code or '-'}; "
            f"source={item.source or '-'}; ts={timestamp_label}"
        )

    def _copy_diagnostics_to_clipboard(self) -> None:
        clipboard = QGuiApplication.clipboard()
        clipboard.setText(self._last_export_payload)
        exported_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        self._copy_status.setText(f"Schowek: skopiowano ({exported_at})")
