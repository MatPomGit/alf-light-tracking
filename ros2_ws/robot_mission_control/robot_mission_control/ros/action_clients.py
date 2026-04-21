from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable

from robot_mission_control.ros.dependency_audit_client import DependencyAuditClient

GoalSender = Callable[[dict[str, Any]], str | None]
GoalCanceler = Callable[[str], bool]
ResultFetcher = Callable[[str], dict[str, Any] | None]
ProgressFetcher = Callable[[str], float | None]


# [AI-CHANGE | 2026-04-20 19:24 UTC | v0.147]
# CO ZMIENIONO: Dodano klienta akcji z obsługą goal/progress/cancel/result i pełnym logowaniem operacji.
# DLACZEGO: Interfejs sterowania misją potrzebuje deterministycznej kontroli przebiegu akcji i jawnej obsługi błędów.
# JAK TO DZIAŁA: MissionActionClient odrzuca niepewne odpowiedzi (None), zapisuje audyt każdego kroku
#                oraz gwarantuje logowanie correlation_id/session_id dla wywołań i wyjątków.
# TODO: Dodać bufor historii progresu per goal_id dla diagnostyki trendu wykonania.


@dataclass(frozen=True, slots=True)
class ActionClientBindings:
    """Wiązania funkcji transportowych dla pojedynczego klienta akcji."""

    send_goal: GoalSender
    cancel_goal: GoalCanceler
    fetch_result: ResultFetcher
    fetch_progress: ProgressFetcher


class MissionActionClient:
    """Klient akcji misji z bezpiecznym fallbackiem na brak danych."""

    def __init__(
        self,
        *,
        session_id: str,
        bindings: ActionClientBindings,
        audit_client: DependencyAuditClient | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        self._session_id = session_id
        self._bindings = bindings
        self._audit = audit_client or DependencyAuditClient()
        self._logger = logger or logging.getLogger("robot_mission_control.ros.action_clients")

    def send_goal(self, *, goal_payload: dict[str, Any], correlation_id: str) -> str | None:
        """Wysyła goal i zwraca goal_id lub None przy niepewnym wyniku."""
        self._log_call("send_goal", correlation_id, extra=goal_payload)
        try:
            goal_id = self._bindings.send_goal(goal_payload)
        except Exception as exc:  # noqa: BLE001
            self._log_error("send_goal", exc, correlation_id)
            return None

        if not goal_id:
            self._audit.emit(
                component="action_clients",
                operation="send_goal",
                status="rejected",
                correlation_id=correlation_id,
                session_id=self._session_id,
                details={"reason": "empty_goal_id"},
            )
            return None

        self._audit.emit(
            component="action_clients",
            operation="send_goal",
            status="ok",
            correlation_id=correlation_id,
            session_id=self._session_id,
            details={"goal_id": goal_id},
        )
        return goal_id

    def get_progress(self, *, goal_id: str, correlation_id: str) -> float | None:
        """Pobiera progres goal; None oznacza brak pewnego odczytu."""
        self._log_call("get_progress", correlation_id, extra={"goal_id": goal_id})
        try:
            progress = self._bindings.fetch_progress(goal_id)
        except Exception as exc:  # noqa: BLE001
            self._log_error("get_progress", exc, correlation_id)
            return None

        if progress is None or progress < 0.0 or progress > 1.0:
            self._audit.emit(
                component="action_clients",
                operation="get_progress",
                status="rejected",
                correlation_id=correlation_id,
                session_id=self._session_id,
                details={"goal_id": goal_id, "reason": "invalid_progress"},
            )
            return None

        self._audit.emit(
            component="action_clients",
            operation="get_progress",
            status="ok",
            correlation_id=correlation_id,
            session_id=self._session_id,
            details={"goal_id": goal_id, "progress": progress},
        )
        return progress

    def cancel_goal(self, *, goal_id: str, correlation_id: str) -> bool:
        """Anuluje goal i zwraca status powodzenia."""
        self._log_call("cancel_goal", correlation_id, extra={"goal_id": goal_id})
        try:
            is_cancelled = bool(self._bindings.cancel_goal(goal_id))
        except Exception as exc:  # noqa: BLE001
            self._log_error("cancel_goal", exc, correlation_id)
            return False

        status = "ok" if is_cancelled else "error"
        self._audit.emit(
            component="action_clients",
            operation="cancel_goal",
            status=status,
            correlation_id=correlation_id,
            session_id=self._session_id,
            details={"goal_id": goal_id},
        )
        return is_cancelled

    def get_result(self, *, goal_id: str, correlation_id: str) -> dict[str, Any] | None:
        """Pobiera rezultat akcji; brak pewnych danych zwraca None."""
        self._log_call("get_result", correlation_id, extra={"goal_id": goal_id})
        try:
            result = self._bindings.fetch_result(goal_id)
        except Exception as exc:  # noqa: BLE001
            self._log_error("get_result", exc, correlation_id)
            return None

        if result is None:
            self._audit.emit(
                component="action_clients",
                operation="get_result",
                status="rejected",
                correlation_id=correlation_id,
                session_id=self._session_id,
                details={"goal_id": goal_id, "reason": "no_result"},
            )
            return None

        self._audit.emit(
            component="action_clients",
            operation="get_result",
            status="ok",
            correlation_id=correlation_id,
            session_id=self._session_id,
            details={"goal_id": goal_id},
        )
        return result

    def _log_call(self, operation: str, correlation_id: str, extra: dict[str, Any] | None = None) -> None:
        self._logger.info(
            "call operation=%s correlation_id=%s session_id=%s extra=%s",
            operation,
            correlation_id,
            self._session_id,
            extra or {},
        )

    def _log_error(self, operation: str, exc: Exception, correlation_id: str) -> None:
        self._logger.error(
            "error operation=%s error=%s correlation_id=%s session_id=%s",
            operation,
            exc,
            correlation_id,
            self._session_id,
        )
        self._audit.emit(
            component="action_clients",
            operation=operation,
            status="error",
            correlation_id=correlation_id,
            session_id=self._session_id,
            details={"error": str(exc)},
        )
