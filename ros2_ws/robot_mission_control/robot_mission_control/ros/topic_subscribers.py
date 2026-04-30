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


@dataclass(frozen=True, slots=True)
class MapPosePayload:
    """Zweryfikowana pozycja robota na mapie."""

    x: float
    y: float
    yaw: float


@dataclass(frozen=True, slots=True)
class MapPathPayload:
    """Zweryfikowana ścieżka robota na mapie."""

    points: tuple[tuple[float, float], ...]


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

    # [AI-CHANGE | 2026-04-30 12:00 UTC | v0.201]
    # CO ZMIENIONO: Dodano dedykowane mapowanie danych mapy (pose/path/frame_status) do StateStore
    #               wraz z twardą walidacją typów i bezpiecznym fallbackiem reason_code.
    # DLACZEGO: Dla mapy obowiązuje zasada bezpieczeństwa — przy niepewności wolimy brak pozycji niż
    #           pokazanie błędnego punktu/trasy mogących wprowadzić operatora w błąd.
    # JAK TO DZIAŁA: Każdy callback sprawdza kompletność i typ wejścia; przy błędzie zapisuje `None`
    #                z jakością UNAVAILABLE/ERROR przez `set_with_inference`, a tylko poprawne dane
    #                publikowane są jako `DataQuality.VALID`.
    # TODO: Dodać filtr outlierów geometrii (np. skok pozycji > limit) i mapować go na reason_code `pose_outlier`.
    def on_map_pose(
        self,
        *,
        state_key: str,
        payload: dict[str, Any] | None,
        source: str,
        sample_timestamp: datetime,
        correlation_id: str,
    ) -> None:
        normalized_timestamp = self._normalize_timestamp(sample_timestamp)
        if payload is None:
            self._state_store.set_with_inference(
                key=state_key,
                value=None,
                source=source,
                timestamp=normalized_timestamp,
                reason_code="map_pose_missing",
            )
            return
        try:
            pose = MapPosePayload(x=float(payload["x"]), y=float(payload["y"]), yaw=float(payload["yaw"]))
        except (KeyError, TypeError, ValueError):
            self._state_store.set_with_inference(
                key=state_key,
                value=None,
                source=source,
                timestamp=normalized_timestamp,
                is_corrupted=True,
                reason_code="map_pose_invalid",
            )
            self._log_rejection(reason="map_pose_invalid", correlation_id=correlation_id, details={"source": source})
            return
        self._state_store.set_with_inference(
            key=state_key,
            value=pose,
            source=source,
            timestamp=normalized_timestamp,
            max_age=self._max_timestamp_drift,
        )

    def on_map_path(
        self,
        *,
        state_key: str,
        payload: list[dict[str, Any]] | None,
        source: str,
        sample_timestamp: datetime,
        correlation_id: str,
    ) -> None:
        normalized_timestamp = self._normalize_timestamp(sample_timestamp)
        if payload is None:
            self._state_store.set_with_inference(
                key=state_key,
                value=None,
                source=source,
                timestamp=normalized_timestamp,
                reason_code="map_path_missing",
            )
            return
        try:
            points = tuple((float(point["x"]), float(point["y"])) for point in payload)
            path = MapPathPayload(points=points)
        except (KeyError, TypeError, ValueError):
            self._state_store.set_with_inference(
                key=state_key,
                value=None,
                source=source,
                timestamp=normalized_timestamp,
                is_corrupted=True,
                reason_code="map_path_invalid",
            )
            self._log_rejection(reason="map_path_invalid", correlation_id=correlation_id, details={"source": source})
            return
        self._state_store.set_with_inference(
            key=state_key,
            value=path,
            source=source,
            timestamp=normalized_timestamp,
            max_age=self._max_timestamp_drift,
        )

    def on_map_frame_status(
        self,
        *,
        state_key: str,
        payload: str | None,
        source: str,
        sample_timestamp: datetime,
        correlation_id: str,
    ) -> None:
        normalized_timestamp = self._normalize_timestamp(sample_timestamp)
        if payload is None:
            self._state_store.set_with_inference(
                key=state_key,
                value=None,
                source=source,
                timestamp=normalized_timestamp,
                reason_code="map_frame_status_missing",
            )
            return
        normalized_payload = payload.upper()
        if normalized_payload not in {"OK", "DEGRADED", "ERROR"}:
            self._state_store.set_with_inference(
                key=state_key,
                value=None,
                source=source,
                timestamp=normalized_timestamp,
                is_corrupted=True,
                reason_code="map_frame_status_invalid",
            )
            self._log_rejection(
                reason="map_frame_status_invalid",
                correlation_id=correlation_id,
                details={"source": source, "payload": normalized_payload},
            )
            return
        self._state_store.set_with_inference(
            key=state_key,
            value=normalized_payload,
            source=source,
            timestamp=normalized_timestamp,
            max_age=self._max_timestamp_drift,
        )


    # [AI-CHANGE | 2026-04-30 16:20 UTC | v0.201]
    # CO ZMIENIONO: Dodano publikację pełnego kontraktu pól mapy do osobnych kluczy store
    #               (position, frame_id, timestamp, trajectory, tf_status, data_quality, reason_code).
    # DLACZEGO: Sama łączność ROS jest niewystarczająca; UI mapy potrzebuje jawnych publikacji rekordów mapowych.
    # JAK TO DZIAŁA: Funkcja atomowo zapisuje wszystkie pola mapy. Przy niepewnych danych ustawia
    #                quality=UNAVAILABLE/ERROR oraz `None`, aby UI nie renderowało fałszywej pozycji.
    # TODO: Dodać wersjonowanie payloadu mapy i metryki odrzuceń per reason_code.
    def publish_map_snapshot_fields(
        self,
        *,
        position_key: str,
        frame_id_key: str,
        timestamp_key: str,
        trajectory_key: str,
        tf_status_key: str,
        data_quality_key: str,
        reason_code_key: str,
        position: tuple[float, float] | None,
        frame_id: str | None,
        sample_timestamp: datetime | None,
        trajectory: tuple[tuple[float, float], ...] | None,
        tf_status: str | None,
        source: str,
        reason_code: str | None = None,
    ) -> None:
        normalized_timestamp = self._normalize_timestamp(sample_timestamp or datetime.now(timezone.utc))
        inferred_reason = reason_code
        data_quality = "VALID"
        if position is None or frame_id is None or sample_timestamp is None or tf_status not in {"OK", "DEGRADED", "ERROR"}:
            data_quality = "UNAVAILABLE"
            inferred_reason = inferred_reason or "map_snapshot_incomplete"
        self._state_store.set_with_inference(key=position_key, value=position if data_quality == "VALID" else None, source=source, timestamp=normalized_timestamp, reason_code=inferred_reason)
        self._state_store.set_with_inference(key=frame_id_key, value=frame_id if data_quality == "VALID" else None, source=source, timestamp=normalized_timestamp, reason_code=inferred_reason)
        self._state_store.set_with_inference(key=timestamp_key, value=sample_timestamp if data_quality == "VALID" else None, source=source, timestamp=normalized_timestamp, reason_code=inferred_reason)
        self._state_store.set_with_inference(key=trajectory_key, value=trajectory if data_quality == "VALID" else None, source=source, timestamp=normalized_timestamp, reason_code=inferred_reason)
        self._state_store.set_with_inference(key=tf_status_key, value=tf_status if data_quality == "VALID" else None, source=source, timestamp=normalized_timestamp, reason_code=inferred_reason)
        self._state_store.set_with_inference(key=data_quality_key, value=data_quality, source=source, timestamp=normalized_timestamp, reason_code=inferred_reason)
        self._state_store.set_with_inference(key=reason_code_key, value=inferred_reason or "ok", source=source, timestamp=normalized_timestamp)
