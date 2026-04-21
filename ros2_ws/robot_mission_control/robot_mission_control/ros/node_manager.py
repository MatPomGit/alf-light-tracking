from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Protocol

from robot_mission_control.core.state_store import STATE_KEY_ROS_CONNECTION_STATUS, StateStore
from robot_mission_control.ros.dependency_audit_client import DependencyAuditClient


class RosRuntime(Protocol):
    """Minimalny kontrakt runtime ROS używany przez menedżer węzła."""

    def init(self) -> None: ...

    def shutdown(self) -> None: ...


# [AI-CHANGE | 2026-04-21 03:58 UTC | v0.160]
# CO ZMIENIONO: Rozszerzono RosNodeManager o publikację statusu połączenia do StateStore
#               oraz jawne stany `CONNECTED`, `DISCONNECTED` i `RECONNECTING`.
# DLACZEGO: UI ma pokazywać utratę/odzyskanie połączenia bezpośrednio na podstawie danych ze store.
# JAK TO DZIAŁA: Każda operacja init/shutdown/reconnect/heartbeat aktualizuje klucz
#                `ros_connection_status`; przy niepewnym stanie publikujemy `None` i reason_code.
# TODO: Dodać metrykę czasu przebywania w stanie RECONNECTING, aby wykrywać flapping połączenia.


@dataclass(frozen=True, slots=True)
class ReconnectPolicy:
    """Parametry polityki ponowień połączenia."""

    max_attempts: int = 3
    base_delay_seconds: float = 0.5
    max_delay_seconds: float = 5.0


class RosNodeManager:
    """Zarządza życiem node ROS i bezpiecznym utrzymaniem połączenia."""

    def __init__(
        self,
        *,
        runtime: RosRuntime,
        session_id: str,
        reconnect_policy: ReconnectPolicy | None = None,
        audit_client: DependencyAuditClient | None = None,
        state_store: StateStore | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        self._runtime = runtime
        self._session_id = session_id
        self._policy = reconnect_policy or ReconnectPolicy()
        self._audit = audit_client or DependencyAuditClient()
        self._state_store = state_store
        self._logger = logger or logging.getLogger("robot_mission_control.ros.node_manager")
        self._is_initialized = False
        self._last_heartbeat: datetime | None = None

    def init_node(self, *, correlation_id: str) -> bool:
        """Inicjalizuje node ROS. Zwraca False zamiast rzucać wyjątek przy błędzie."""
        self._log_call("init_node", correlation_id)
        try:
            self._runtime.init()
            self._is_initialized = True
            self._publish_connection_status(status="CONNECTED")
            self._audit.emit(
                component="node_manager",
                operation="init_node",
                status="ok",
                correlation_id=correlation_id,
                session_id=self._session_id,
            )
            return True
        except Exception as exc:  # noqa: BLE001
            self._is_initialized = False
            self._publish_connection_status(status=None, reason_code="init_failed")
            self._log_error("init_node", exc, correlation_id)
            self._audit.emit(
                component="node_manager",
                operation="init_node",
                status="error",
                correlation_id=correlation_id,
                session_id=self._session_id,
                details={"error": str(exc)},
            )
            return False

    def shutdown_node(self, *, correlation_id: str) -> bool:
        """Zamyka node ROS; błąd jest logowany i mapowany na False."""
        self._log_call("shutdown_node", correlation_id)
        if not self._is_initialized:
            self._publish_connection_status(status=None, reason_code="node_not_initialized")
            self._audit.emit(
                component="node_manager",
                operation="shutdown_node",
                status="skipped",
                correlation_id=correlation_id,
                session_id=self._session_id,
                details={"reason": "node_not_initialized"},
            )
            return True

        try:
            self._runtime.shutdown()
            self._is_initialized = False
            self._publish_connection_status(status=None, reason_code="node_shutdown")
            self._audit.emit(
                component="node_manager",
                operation="shutdown_node",
                status="ok",
                correlation_id=correlation_id,
                session_id=self._session_id,
            )
            return True
        except Exception as exc:  # noqa: BLE001
            self._publish_connection_status(status=None, reason_code="shutdown_failed")
            self._log_error("shutdown_node", exc, correlation_id)
            self._audit.emit(
                component="node_manager",
                operation="shutdown_node",
                status="error",
                correlation_id=correlation_id,
                session_id=self._session_id,
                details={"error": str(exc)},
            )
            return False

    def ensure_connected(self, *, correlation_id: str) -> bool:
        """Wykonuje reconnect policy jeśli node nie jest gotowy."""
        self._log_call("ensure_connected", correlation_id)
        if self._is_initialized:
            self._publish_connection_status(status="CONNECTED")
            return True

        self._publish_connection_status(status="RECONNECTING")
        for attempt in range(1, self._policy.max_attempts + 1):
            if self.init_node(correlation_id=correlation_id):
                return True
            delay = min(self._policy.base_delay_seconds * (2 ** (attempt - 1)), self._policy.max_delay_seconds)
            self._logger.warning(
                "node reconnect retry=%s delay=%.2fs correlation_id=%s session_id=%s",
                attempt,
                delay,
                correlation_id,
                self._session_id,
            )
            time.sleep(delay)

        self._publish_connection_status(status=None, reason_code="reconnect_failed")
        return False

    def heartbeat(self, *, correlation_id: str) -> datetime | None:
        """Aktualizuje heartbeat tylko gdy połączenie jest pewne."""
        self._log_call("heartbeat", correlation_id)
        if not self._is_initialized:
            self._publish_connection_status(status=None, reason_code="node_not_initialized")
            self._audit.emit(
                component="node_manager",
                operation="heartbeat",
                status="rejected",
                correlation_id=correlation_id,
                session_id=self._session_id,
                details={"reason": "node_not_initialized"},
            )
            return None

        timestamp = datetime.now(timezone.utc)
        self._last_heartbeat = timestamp
        self._publish_connection_status(status="CONNECTED")
        self._audit.emit(
            component="node_manager",
            operation="heartbeat",
            status="ok",
            correlation_id=correlation_id,
            session_id=self._session_id,
            details={"timestamp": timestamp.isoformat()},
        )
        return timestamp

    def is_heartbeat_stale(self, *, now: datetime, max_age: timedelta) -> bool:
        """Zwraca True dla niepewnego heartbeat, preferując ostrożny fallback."""
        if self._last_heartbeat is None:
            self._publish_connection_status(status=None, reason_code="heartbeat_missing")
            return True
        is_stale = now - self._last_heartbeat > max_age
        if is_stale:
            self._publish_connection_status(status=None, reason_code="heartbeat_stale")
        return is_stale

    def _publish_connection_status(self, *, status: str | None, reason_code: str | None = None) -> None:
        """Publikuje status połączenia do store z konserwatywnym fallbackiem."""
        if self._state_store is None:
            return
        self._state_store.set_with_inference(
            key=STATE_KEY_ROS_CONNECTION_STATUS,
            value=status,
            source="node_manager",
            timestamp=datetime.now(timezone.utc),
            reason_code=reason_code,
        )

    def _log_call(self, operation: str, correlation_id: str) -> None:
        self._logger.info(
            "call operation=%s correlation_id=%s session_id=%s",
            operation,
            correlation_id,
            self._session_id,
        )

    def _log_error(self, operation: str, exc: Exception, correlation_id: str) -> None:
        self._logger.error(
            "error operation=%s error=%s correlation_id=%s session_id=%s",
            operation,
            exc,
            correlation_id,
            self._session_id,
        )
