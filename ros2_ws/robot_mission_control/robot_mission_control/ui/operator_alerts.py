"""Lekki rejestr alertów operatorskich dla zakładek UI."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from threading import RLock

from robot_mission_control.core import DataQuality, StateValue


# [AI-CHANGE | 2026-04-23 16:30 UTC | v0.188]
# CO ZMIENIONO: Dodano model `OperatorAlert` i rejestr `OperatorAlerts` z obsługą publikacji,
#               listy aktywnych alertów, ACK operatora oraz automatycznego zamykania alertów
#               podczas synchronizacji ze snapshotem StateStore.
# DLACZEGO: UI potrzebuje jednego, deterministycznego źródła prawdy dla alarmów operacyjnych,
#           aby DiagnosticsTab i OverviewTab pokazywały ten sam stan bez ryzyka niespójności.
# JAK TO DZIAŁA: `sync_from_snapshot` tworzy/odświeża alert dla jakości UNAVAILABLE/ERROR,
#                a dla kluczy z jakością VALID zamyka aktywny alert; `ack_alert` oznacza alert
#                jako potwierdzony bez zamykania incydentu, dzięki czemu operator zachowuje widoczność.
# TODO: Dodać retencję historii i eksport alertów do CSV/JSONL z limitami pamięci.
@dataclass(frozen=True, slots=True)
class OperatorAlert:
    """Kontrakt pojedynczego alertu operatorskiego."""

    alert_id: str
    state_key: str
    severity: str
    code: str
    message: str
    opened_at: datetime
    updated_at: datetime
    acknowledged: bool = False
    acknowledged_by: str | None = None
    acknowledged_at: datetime | None = None
    closed_at: datetime | None = None

    @property
    def is_active(self) -> bool:
        return self.closed_at is None


class OperatorAlerts:
    """In-memory registry alertów używany przez widoki operatorskie."""

    def __init__(self) -> None:
        self._lock = RLock()
        self._alerts: dict[str, OperatorAlert] = {}
        self._active_by_state_key: dict[str, str] = {}
        self._last_critical_alert_id: str | None = None

    def sync_from_snapshot(self, snapshot: dict[str, StateValue]) -> None:
        """Synchronizuje alerty na podstawie jakości próbek w snapshotcie StateStore."""
        for key, item in snapshot.items():
            if item.quality in (DataQuality.UNAVAILABLE, DataQuality.ERROR):
                severity = "CRITICAL" if item.quality is DataQuality.ERROR else "HIGH"
                code = item.reason_code or f"state_{item.quality.value.lower()}"
                message = f"{key}: {item.source} ({item.quality.value})"
                self.publish_alert(
                    state_key=key,
                    severity=severity,
                    code=code,
                    message=message,
                    timestamp=item.timestamp,
                )
                continue
            if item.quality is DataQuality.VALID:
                self.close_alert_for_key(state_key=key, timestamp=item.timestamp)

    def publish_alert(
        self,
        *,
        state_key: str,
        severity: str,
        code: str,
        message: str,
        timestamp: datetime,
    ) -> OperatorAlert:
        """Publikuje nowy alert albo odświeża istniejący aktywny alert dla klucza stanu."""
        normalized_timestamp = self._normalize_timestamp(timestamp)
        with self._lock:
            active_id = self._active_by_state_key.get(state_key)
            if active_id is not None:
                current = self._alerts[active_id]
                updated = replace(
                    current,
                    severity=severity,
                    code=code,
                    message=message,
                    updated_at=normalized_timestamp,
                )
                self._alerts[active_id] = updated
                if severity == "CRITICAL":
                    self._last_critical_alert_id = updated.alert_id
                return updated

            alert_id = f"{state_key}:{normalized_timestamp.isoformat()}"
            created = OperatorAlert(
                alert_id=alert_id,
                state_key=state_key,
                severity=severity,
                code=code,
                message=message,
                opened_at=normalized_timestamp,
                updated_at=normalized_timestamp,
            )
            self._alerts[alert_id] = created
            self._active_by_state_key[state_key] = alert_id
            if severity == "CRITICAL":
                self._last_critical_alert_id = alert_id
            return created

    def close_alert_for_key(self, *, state_key: str, timestamp: datetime) -> OperatorAlert | None:
        """Zamyka aktywny alert dla podanego klucza stanu, jeżeli istnieje."""
        normalized_timestamp = self._normalize_timestamp(timestamp)
        with self._lock:
            active_id = self._active_by_state_key.pop(state_key, None)
            if active_id is None:
                return None
            current = self._alerts[active_id]
            closed = replace(current, updated_at=normalized_timestamp, closed_at=normalized_timestamp)
            self._alerts[active_id] = closed
            return closed

    def ack_alert(self, *, alert_id: str, operator_id: str = "operator") -> OperatorAlert | None:
        """Potwierdza alert przez operatora bez wymuszania zamknięcia alertu."""
        with self._lock:
            alert = self._alerts.get(alert_id)
            if alert is None:
                return None
            acknowledged_at = self._normalize_timestamp(datetime.now(timezone.utc))
            acknowledged = replace(
                alert,
                acknowledged=True,
                acknowledged_by=operator_id,
                acknowledged_at=acknowledged_at,
                updated_at=acknowledged_at,
            )
            self._alerts[alert_id] = acknowledged
            return acknowledged

    def active_alerts(self) -> list[OperatorAlert]:
        """Zwraca listę aktualnie aktywnych alertów posortowanych malejąco po czasie."""
        with self._lock:
            active = [self._alerts[alert_id] for alert_id in self._active_by_state_key.values()]
            return sorted(active, key=lambda item: item.updated_at, reverse=True)

    def last_critical_alert(self) -> OperatorAlert | None:
        """Zwraca ostatni alert krytyczny (aktywny lub historyczny)."""
        with self._lock:
            if self._last_critical_alert_id is None:
                return None
            return self._alerts.get(self._last_critical_alert_id)

    def _normalize_timestamp(self, timestamp: datetime) -> datetime:
        if timestamp.tzinfo is None:
            return timestamp.replace(tzinfo=timezone.utc)
        return timestamp.astimezone(timezone.utc)
