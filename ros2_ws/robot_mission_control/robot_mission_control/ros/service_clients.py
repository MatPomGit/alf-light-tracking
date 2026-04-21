from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any, Callable

from robot_mission_control.ros.dependency_audit_client import DependencyAuditClient


ServiceInvoker = Callable[[dict[str, Any]], object]
PreconditionFn = Callable[[], bool]


# [AI-CHANGE | 2026-04-21 04:49 UTC | v0.162]
# CO ZMIENIONO: Przebudowano klientów krytycznych usług (E-stop/start/stop/mode), aby każda akcja zwracała
#               obiekt wyniku zawierający success/fail, reason i status zapisu audytu.
# DLACZEGO: Wymaganie DoD wymusza pełną obserwowalność i brak trybu fire-and-forget dla komend krytycznych.
# JAK TO DZIAŁA: Każda komenda przechodzi przez precondition, blokujące wywołanie z timeout/retry, a następnie
#                zawsze zapisuje audyt i zwraca CommandResult. Brak odpowiedzi (None) jest traktowany jako błąd
#                fire-and-forget i odrzucany zgodnie z zasadą bezpieczeństwa.
# TODO: Dodać klasyfikację reason na kody domenowe i telemetrię czasu round-trip do audytu.


@dataclass(frozen=True, slots=True)
class ServicePolicy:
    """Konfiguracja timeout/retry dla komend krytycznych."""

    timeout_seconds: float = 2.0
    max_retries: int = 2
    retry_delay_seconds: float = 0.25


@dataclass(frozen=True, slots=True)
class CommandResult:
    """Wynik pojedynczej komendy krytycznej wymagany przez DoD."""

    success: bool
    reason: str
    audit_logged: bool


class CriticalServiceClients:
    """Klienci usług krytycznych z polityką: lepiej odrzucić niż zwrócić niepewny sukces."""

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

    def send_estop(self, *, correlation_id: str) -> CommandResult:
        """Wysyła E-stop i zwraca zweryfikowany wynik z powodem."""

        return self._run_critical_command(name="estop", payload={}, correlation_id=correlation_id)

    def send_start(self, *, correlation_id: str) -> CommandResult:
        """Wysyła start i zwraca zweryfikowany wynik z powodem."""

        return self._run_critical_command(name="start", payload={}, correlation_id=correlation_id)

    def send_stop(self, *, correlation_id: str) -> CommandResult:
        """Wysyła stop i zwraca zweryfikowany wynik z powodem."""

        return self._run_critical_command(name="stop", payload={}, correlation_id=correlation_id)

    def send_mode(self, *, mode: str, correlation_id: str) -> CommandResult:
        """Wysyła zmianę trybu i zwraca zweryfikowany wynik z powodem."""

        return self._run_critical_command(name="mode", payload={"mode": mode}, correlation_id=correlation_id)

    def _run_critical_command(self, *, name: str, payload: dict[str, Any], correlation_id: str) -> CommandResult:
        """Realizuje blokujące wywołanie krytyczne z precondition/timeout/retry i audytem."""

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
            return self._finalize_result(
                name=name,
                payload=payload,
                correlation_id=correlation_id,
                success=False,
                reason="service_not_configured",
                attempt=0,
            )

        if not precondition():
            return self._finalize_result(
                name=name,
                payload=payload,
                correlation_id=correlation_id,
                success=False,
                reason="precondition_failed",
                attempt=0,
            )

        for attempt in range(1, self._policy.max_retries + 2):
            started = time.monotonic()
            reason = "service_returned_false"
            success = False

            try:
                raw_result = invoker(payload)
                if raw_result is None:
                    reason = "fire_and_forget_forbidden"
                else:
                    success = bool(raw_result)
            except Exception as exc:  # noqa: BLE001
                reason = f"exception:{type(exc).__name__}"

            elapsed = time.monotonic() - started
            if elapsed > self._policy.timeout_seconds:
                success = False
                reason = "timeout"

            if success:
                return self._finalize_result(
                    name=name,
                    payload=payload,
                    correlation_id=correlation_id,
                    success=True,
                    reason="ok",
                    attempt=attempt,
                )

            self._log_error(name=name, reason=reason, correlation_id=correlation_id, attempt=attempt)
            if attempt <= self._policy.max_retries:
                time.sleep(self._policy.retry_delay_seconds)

        return self._finalize_result(
            name=name,
            payload=payload,
            correlation_id=correlation_id,
            success=False,
            reason=reason,
            attempt=self._policy.max_retries + 1,
        )

    def _finalize_result(
        self,
        *,
        name: str,
        payload: dict[str, Any],
        correlation_id: str,
        success: bool,
        reason: str,
        attempt: int,
    ) -> CommandResult:
        """Kończy komendę jednolitym wpisem audytu i zwraca obiekt wyniku."""

        audit_logged = self._emit_audit(
            name=name,
            payload=payload,
            correlation_id=correlation_id,
            success=success,
            reason=reason,
            attempt=attempt,
        )
        return CommandResult(success=success, reason=reason, audit_logged=audit_logged)

    def _emit_audit(
        self,
        *,
        name: str,
        payload: dict[str, Any],
        correlation_id: str,
        success: bool,
        reason: str,
        attempt: int,
    ) -> bool:
        """Zapisuje audyt i zwraca, czy log został przyjęty."""

        try:
            self._audit.emit(
                component="service_clients",
                operation=name,
                status="ok" if success else "error",
                correlation_id=correlation_id,
                session_id=self._session_id,
                details={"payload": payload, "attempt": attempt, "reason": reason},
            )
        except Exception as exc:  # noqa: BLE001
            self._logger.error(
                "audit_emit_failed service=%s reason=%s correlation_id=%s session_id=%s",
                name,
                type(exc).__name__,
                correlation_id,
                self._session_id,
            )
            return False
        return True

    def _log_error(self, *, name: str, reason: str, correlation_id: str, attempt: int) -> None:
        """Loguje błąd wykonania krytycznej komendy wraz z numerem próby."""

        self._logger.error(
            "service_error service=%s reason=%s attempt=%s correlation_id=%s session_id=%s",
            name,
            reason,
            attempt,
            correlation_id,
            self._session_id,
        )
