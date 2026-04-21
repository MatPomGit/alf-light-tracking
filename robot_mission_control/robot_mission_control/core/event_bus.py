"""Lekka szyna zdarzeń dla komunikacji między modułami Mission Control."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

from robot_mission_control.core.error_codes import DEFAULT_ERROR_MESSAGES, ErrorCode
from robot_mission_control.core.models import EventCategory, MissionEvent

EventHandler = Callable[[MissionEvent], None]


# [AI-CHANGE | 2026-04-21 09:30 UTC | v0.166]
# CO ZMIENIONO: Dodano prostą szynę zdarzeń z walidacją kontraktu dla zdarzeń operatorskich.
# DLACZEGO: Operacje operatora muszą być audytowalne end-to-end, dlatego correlation_id
#           jest wymagane i brak tego pola musi skutkować odrzuceniem zdarzenia.
# JAK TO DZIAŁA: `publish` waliduje payload i correlation_id, a następnie dystrybuuje event
#                do subskrybentów wg nazwy; przy błędzie rzuca `EventBusValidationError`.
# TODO: Dodać ograniczenie pojemności kolejki i tryb backpressure dla wysokiego wolumenu zdarzeń.
class EventBusValidationError(ValueError):
    """Błąd walidacji zdarzenia publikowanego na szynie."""

    def __init__(self, code: ErrorCode, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message


class EventBus:
    """In-memory event bus with explicit validation and safe dispatch."""

    def __init__(self) -> None:
        self._handlers: dict[str, list[EventHandler]] = defaultdict(list)

    def subscribe(self, event_name: str, handler: EventHandler) -> None:
        """Register event handler for selected event name."""
        self._handlers[event_name].append(handler)

    def publish(
        self,
        *,
        name: str,
        category: EventCategory,
        correlation_id: str | None,
        session_id: str,
        payload: dict[str, Any],
        emitted_at: datetime | None = None,
    ) -> MissionEvent:
        """Validate and publish event to all handlers bound to name."""
        self._validate_event(category=category, correlation_id=correlation_id, payload=payload)
        event = MissionEvent(
            name=name,
            category=category,
            correlation_id=correlation_id,
            session_id=session_id,
            payload=payload,
            emitted_at=emitted_at or datetime.now(timezone.utc),
        )
        for handler in self._handlers.get(name, []):
            handler(event)
        return event

    def _validate_event(
        self,
        *,
        category: EventCategory,
        correlation_id: str | None,
        payload: dict[str, Any],
    ) -> None:
        if not isinstance(payload, dict):
            raise EventBusValidationError(
                ErrorCode.EVENT_INVALID_PAYLOAD,
                DEFAULT_ERROR_MESSAGES[ErrorCode.EVENT_INVALID_PAYLOAD],
            )
        if category == EventCategory.OPERATOR and not (correlation_id and correlation_id.strip()):
            raise EventBusValidationError(
                ErrorCode.EVENT_MISSING_CORRELATION_ID,
                DEFAULT_ERROR_MESSAGES[ErrorCode.EVENT_MISSING_CORRELATION_ID],
            )
