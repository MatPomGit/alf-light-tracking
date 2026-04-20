from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any


# [AI-CHANGE | 2026-04-20 19:24 UTC | v0.147]
# CO ZMIENIONO: Dodano klient audytu zależności zbierający zdarzenia usług/akcji wraz z correlation_id i session_id.
# DLACZEGO: Wymagane jest pełne śledzenie wywołań oraz błędów bez silent-fail i możliwość późniejszej analizy incydentów.
# JAK TO DZIAŁA: DependencyAuditClient tworzy rekord audytowy, zapisuje go w pamięci oraz loguje strukturalnie do loggera.
# TODO: Zaimplementować eksport audytu do trwałego backendu (np. plik JSONL albo OTLP).


@dataclass(frozen=True, slots=True)
class AuditRecord:
    """Pojedynczy rekord audytu dla operacji ROS."""

    timestamp: datetime
    component: str
    operation: str
    status: str
    correlation_id: str
    session_id: str
    details: dict[str, Any]


class DependencyAuditClient:
    """Prosty klient audytu dla krytycznych operacji mostu ROS."""

    def __init__(self, logger: logging.Logger | None = None) -> None:
        self._logger = logger or logging.getLogger("robot_mission_control.ros.audit")
        self._records: list[AuditRecord] = []

    def emit(
        self,
        *,
        component: str,
        operation: str,
        status: str,
        correlation_id: str,
        session_id: str,
        details: dict[str, Any] | None = None,
    ) -> AuditRecord:
        """Zapisuje rekord audytowy i loguje jego skrót."""
        payload = details or {}
        record = AuditRecord(
            timestamp=datetime.utcnow(),
            component=component,
            operation=operation,
            status=status,
            correlation_id=correlation_id,
            session_id=session_id,
            details=payload,
        )
        self._records.append(record)
        self._logger.info(
            "audit component=%s operation=%s status=%s correlation_id=%s session_id=%s details=%s",
            component,
            operation,
            status,
            correlation_id,
            session_id,
            payload,
        )
        return record

    def snapshot(self) -> tuple[AuditRecord, ...]:
        """Zwraca niemodyfikowalny snapshot audytu."""
        return tuple(self._records)
