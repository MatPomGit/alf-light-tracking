"""Wspólne modele danych dla warstwy core modułu Mission Control."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any


# [AI-CHANGE | 2026-04-21 09:30 UTC | v0.166]
# CO ZMIENIONO: Dodano modele konfiguracji, zdarzeń operatorskich i reprezentacji błędów.
# DLACZEGO: Ujednolicone modele redukują ryzyko rozbieżności kontraktów między modułami core.
# JAK TO DZIAŁA: Dataclasses wymuszają jawne pola i typy, a enum `EventCategory`
#                określa semantykę zdarzeń publikowanych na szynie.
# TODO: Dodać wersjonowanie schematu modeli (np. schema_version) dla migracji kompatybilności.
class EventCategory(str, Enum):
    """Kategorie zdarzeń dla routingu na szynie eventów."""

    OPERATOR = "operator"
    SYSTEM = "system"


@dataclass(frozen=True, slots=True)
class MissionControlConfig:
    """Zweryfikowany model konfiguracji aplikacji."""

    session_id: str
    operator_timeout_sec: float
    max_event_queue_size: int
    log_level: str


@dataclass(frozen=True, slots=True)
class MissionEvent:
    """Kontrakt pojedynczego zdarzenia publikowanego na szynie."""

    name: str
    category: EventCategory
    correlation_id: str | None
    session_id: str
    payload: dict[str, Any]
    emitted_at: datetime


@dataclass(frozen=True, slots=True)
class ErrorDescriptor:
    """Opis błędu przekazywany do UI i logów."""

    code: str
    message: str
    details: str | None = None
