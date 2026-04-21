from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from robot_mission_control.core.state_store import StateStore
from robot_mission_control.ros.dependency_audit_client import DependencyAuditClient


# [AI-CHANGE | 2026-04-21 04:42 UTC | v0.161]
# CO ZMIENIONO: Rozszerzono mapowanie telemetryki o jawne fallbacki STALE/UNAVAILABLE
#               dla danych starych, brakujących i z niepoprawnego źródła, przy zachowaniu
#               walidacji source/timestamp/type.
# DLACZEGO: KPI i wykresy muszą pokazywać albo dane rzeczywiste, albo jednoznaczny brak danych,
#           bez ryzyka prezentacji błędnych wartości jako poprawnych.
# JAK TO DZIAŁA: Subskrybent waliduje źródło i timestamp, a następnie dla każdego pola
#                zapisuje stan do store. Gdy próbka jest stara -> STALE, gdy niekompletna
#                lub z niedozwolonego źródła -> UNAVAILABLE, gdy typ błędny -> ERROR.
# TODO: Dodać per-field politykę jakości (np. dla liczników kumulacyjnych dopuszczać większy max_age).


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
            self._set_all_fields_unavailable(source=source, timestamp=sample_timestamp, reason_code="invalid_source")
            self._log_rejection(
                reason="invalid_source",
                correlation_id=correlation_id,
                details={"source": source},
            )
            return

        normalized_timestamp = self._normalize_timestamp(sample_timestamp)
        now = datetime.now(timezone.utc)
        if normalized_timestamp > now + self._max_timestamp_drift:
            self._set_all_fields_unavailable(
                source=source,
                timestamp=now,
                reason_code="future_timestamp",
            )
            self._log_rejection(
                reason="future_timestamp",
                correlation_id=correlation_id,
                details={"sample_timestamp": normalized_timestamp.isoformat(), "now": now.isoformat()},
            )
            return

        if now - normalized_timestamp > self._max_timestamp_drift:
            self._set_all_fields_stale(source=source, timestamp=normalized_timestamp)
            self._log_rejection(
                reason="timestamp_stale",
                correlation_id=correlation_id,
                details={"sample_timestamp": normalized_timestamp.isoformat(), "now": now.isoformat()},
            )
            return

        for field_name, spec in self._specs.items():
            if field_name not in payload:
                self._state_store.set_with_inference(
                    key=spec.state_key,
                    value=None,
                    source=source,
                    timestamp=normalized_timestamp,
                    reason_code="missing_field",
                )
                self._log_rejection(
                    reason="missing_field",
                    correlation_id=correlation_id,
                    details={"field": field_name},
                )
                continue

            value = payload[field_name]
            if not isinstance(value, spec.expected_type):
                self._state_store.set_with_inference(
                    key=spec.state_key,
                    value=None,
                    source=source,
                    timestamp=normalized_timestamp,
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
                timestamp=normalized_timestamp,
                max_age=self._max_timestamp_drift,
            )
            self._audit.emit(
                component="topic_subscribers",
                operation=f"map_field:{field_name}",
                status="ok",
                correlation_id=correlation_id,
                session_id=self._session_id,
                details={"state_key": spec.state_key},
            )

    def _normalize_timestamp(self, sample_timestamp: datetime) -> datetime:
        """Normalizuje timestamp do UTC aware, aby walidacja czasu była deterministyczna."""
        if sample_timestamp.tzinfo is None:
            return sample_timestamp.replace(tzinfo=timezone.utc)
        return sample_timestamp.astimezone(timezone.utc)

    def _set_all_fields_unavailable(self, *, source: str, timestamp: datetime, reason_code: str) -> None:
        """Wymusza bezpieczny fallback UNAVAILABLE dla wszystkich mapowanych pól."""
        for spec in self._specs.values():
            self._state_store.set_with_inference(
                key=spec.state_key,
                value=None,
                source=source,
                timestamp=self._normalize_timestamp(timestamp),
                reason_code=reason_code,
            )

    def _set_all_fields_stale(self, *, source: str, timestamp: datetime) -> None:
        """Wymusza fallback STALE dla wszystkich mapowanych pól przy przeterminowanej próbce."""
        for spec in self._specs.values():
            self._state_store.set_with_inference(
                key=spec.state_key,
                value="stale_sample",
                source=source,
                timestamp=self._normalize_timestamp(timestamp),
                max_age=self._max_timestamp_drift,
                reason_code="stale_data",
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
