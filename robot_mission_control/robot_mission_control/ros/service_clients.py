from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any, Callable

from robot_mission_control.ros.dependency_audit_client import DependencyAuditClient


ServiceInvoker = Callable[[dict[str, Any]], bool]
PreconditionFn = Callable[[], bool]


# [AI-CHANGE | 2026-04-20 19:24 UTC | v0.147]
# CO ZMIENIONO: Dodano klientów krytycznych usług (E-stop/start/stop/mode) z precondition, timeout, retry i audytem.
# DLACZEGO: Operacje krytyczne muszą mieć kontrolę bezpieczeństwa i pełny ślad, aby uniknąć błędnych komend oraz silent-fail.
# JAK TO DZIAŁA: Każda komenda przechodzi przez `_run_critical_command`; przy braku precondition lub timeout zwracamy False,
#                rejestrujemy błąd i audyt zamiast propagowania niepewnego rezultatu.
# TODO: Dodać rozróżnienie klas błędów transportowych i domenowych dla bardziej precyzyjnych polityk retry.


@dataclass(frozen=True, slots=True)
class ServicePolicy:
    """Parametry wykonania komend krytycznych."""

    timeout_seconds: float = 2.0
    max_retries: int = 2
    retry_delay_seconds: float = 0.25


class CriticalServiceClients:
    """Klienci usług krytycznych z ostrożną polityką błędów."""

    def __init__(
        self,
        *,
        session_id: str,
        invokers: dict[str, ServiceInvoker],
        preconditions: dict[str, PreconditionFn],
        policy: ServicePolicy | None = None,
        audit_client: DependencyAuditClient | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        self._session_id = session_id
        self._invokers = invokers
        self._preconditions = preconditions
        self._policy = policy or ServicePolicy()
        self._audit = audit_client or DependencyAuditClient()
        self._logger = logger or logging.getLogger("robot_mission_control.ros.service_clients")

    def send_estop(self, *, correlation_id: str) -> bool:
        return self._run_critical_command(name="estop", payload={}, correlation_id=correlation_id)

    def send_start(self, *, correlation_id: str) -> bool:
        return self._run_critical_command(name="start", payload={}, correlation_id=correlation_id)

    def send_stop(self, *, correlation_id: str) -> bool:
        return self._run_critical_command(name="stop", payload={}, correlation_id=correlation_id)

    def send_mode(self, *, mode: str, correlation_id: str) -> bool:
        return self._run_critical_command(name="mode", payload={"mode": mode}, correlation_id=correlation_id)

    def _run_critical_command(self, *, name: str, payload: dict[str, Any], correlation_id: str) -> bool:
        self._logger.info(
            "call service=%s correlation_id=%s session_id=%s payload=%s",
            name,
            correlation_id,
            self._session_id,
            payload,
        )

        precondition = self._preconditions.get(name)
        invoker = self._invokers.get(name)
        if precondition is None or invoker is None:
            self._log_error(name=name, reason="service_not_configured", correlation_id=correlation_id)
            return False

        if not precondition():
            self._log_error(name=name, reason="precondition_failed", correlation_id=correlation_id)
            return False

        for attempt in range(1, self._policy.max_retries + 2):
            started = time.monotonic()
            try:
                result = bool(invoker(payload))
            except Exception as exc:  # noqa: BLE001
                self._log_error(name=name, reason=f"exception:{exc}", correlation_id=correlation_id)
                result = False

            elapsed = time.monotonic() - started
            if elapsed > self._policy.timeout_seconds:
                self._log_error(name=name, reason="timeout", correlation_id=correlation_id)
                result = False

            if result:
                self._audit.emit(
                    component="service_clients",
                    operation=name,
                    status="ok",
                    correlation_id=correlation_id,
                    session_id=self._session_id,
                    details={"attempt": attempt},
                )
                return True

            if attempt <= self._policy.max_retries:
                time.sleep(self._policy.retry_delay_seconds)

        self._audit.emit(
            component="service_clients",
            operation=name,
            status="error",
            correlation_id=correlation_id,
            session_id=self._session_id,
            details={"payload": payload},
        )
        return False

    def _log_error(self, *, name: str, reason: str, correlation_id: str) -> None:
        self._logger.error(
            "service_error service=%s reason=%s correlation_id=%s session_id=%s",
            name,
            reason,
            correlation_id,
            self._session_id,
        )
