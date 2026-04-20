from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from robot_mission_control.core.state_store import StateStore
from robot_mission_control.ros.dependency_audit_client import DependencyAuditClient


# [AI-CHANGE | 2026-04-20 19:24 UTC | v0.147]
# CO ZMIENIONO: Dodano mapowanie telemetry do state_store z walidacją typu, source oraz dryfu czasu.
# DLACZEGO: Dane z topiców mogą być uszkodzone lub spóźnione; bez walidacji UI mogłoby pokazać błędny stan robota.
# JAK TO DZIAŁA: TelemetryTopicSubscribers odrzuca niepewne próbki (brak wyniku), zapisuje bezpieczny fallback
#                przez `set_with_inference` i loguje każdy sukces/błąd z correlation_id + session_id.
# TODO: Dodać per-topic adaptacyjne progi driftu czasu zależnie od częstotliwości publikacji.


@dataclass(frozen=True, slots=True)
class TelemetryFieldSpec:
    """Specyfikacja walidacji pojedynczego pola telemetrycznego."""

    state_key: str
    expected_type: type


class TelemetryTopicSubscribers:
    """Warstwa mapowania danych z ROS topiców do StateStore."""

    def __init__(
        self,
        *,
        state_store: StateStore,
        session_id: str,
        allowed_sources: set[str],
        max_timestamp_drift: timedelta = timedelta(seconds=3),
        audit_client: DependencyAuditClient | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        self._state_store = state_store
        self._session_id = session_id
        self._allowed_sources = allowed_sources
        self._max_timestamp_drift = max_timestamp_drift
        self._audit = audit_client or DependencyAuditClient()
        self._logger = logger or logging.getLogger("robot_mission_control.ros.topic_subscribers")
        self._specs: dict[str, TelemetryFieldSpec] = {}

    def register_field(self, field_name: str, spec: TelemetryFieldSpec) -> None:
        """Rejestruje mapowanie pola telemetrycznego."""
        self._specs[field_name] = spec

    def on_telemetry(
        self,
        *,
        payload: dict[str, Any],
        source: str,
        sample_timestamp: datetime,
        correlation_id: str,
    ) -> None:
        """Przyjmuje próbkę telemetry i zapisuje tylko dane zweryfikowane."""
        self._logger.info(
            "call operation=on_telemetry correlation_id=%s session_id=%s source=%s",
            correlation_id,
            self._session_id,
            source,
        )

        if source not in self._allowed_sources:
            self._log_rejection(
                reason="invalid_source",
                correlation_id=correlation_id,
                details={"source": source},
            )
            return

        now = datetime.now(timezone.utc)
        if sample_timestamp.tzinfo is None:
            sample_timestamp = sample_timestamp.replace(tzinfo=timezone.utc)

        if abs(now - sample_timestamp) > self._max_timestamp_drift:
            self._log_rejection(
                reason="timestamp_drift",
                correlation_id=correlation_id,
                details={
                    "sample_timestamp": sample_timestamp.isoformat(),
                    "now": now.isoformat(),
                },
            )
            return

        for field_name, spec in self._specs.items():
            value = payload.get(field_name)
            if not isinstance(value, spec.expected_type):
                self._state_store.set_with_inference(
                    key=spec.state_key,
                    value=None,
                    source=source,
                    timestamp=sample_timestamp,
                    is_corrupted=True,
                    reason_code="invalid_type",
                )
                self._log_rejection(
                    reason="invalid_type",
                    correlation_id=correlation_id,
                    details={"field": field_name, "expected": spec.expected_type.__name__},
                )
                continue

            self._state_store.set_with_inference(
                key=spec.state_key,
                value=value,
                source=source,
                timestamp=sample_timestamp,
            )
            self._audit.emit(
                component="topic_subscribers",
                operation=f"map_field:{field_name}",
                status="ok",
                correlation_id=correlation_id,
                session_id=self._session_id,
                details={"state_key": spec.state_key},
            )

    def _log_rejection(self, *, reason: str, correlation_id: str, details: dict[str, Any]) -> None:
        self._logger.error(
            "rejected reason=%s correlation_id=%s session_id=%s details=%s",
            reason,
            correlation_id,
            self._session_id,
            details,
        )
        self._audit.emit(
            component="topic_subscribers",
            operation="on_telemetry",
            status="rejected",
            correlation_id=correlation_id,
            session_id=self._session_id,
            details={"reason": reason, **details},
        )
