"""Granica wyjątków zapewniająca degradację działania bez blokowania UI."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Generic, TypeVar

from robot_mission_control.core.error_codes import DEFAULT_ERROR_MESSAGES, ErrorCode
from robot_mission_control.core.models import ErrorDescriptor

T = TypeVar("T")


# [AI-CHANGE | 2026-04-21 09:30 UTC | v0.166]
# CO ZMIENIONO: Dodano mapowanie wyjątków na kody błędów oraz bezpieczne wykonanie operacji
#               z degradacją zamiast propagowania wyjątku do pętli UI.
# DLACZEGO: Nieobsłużony wyjątek w callbacku UI może zamrozić interfejs; wymagamy przewidywalnego
#           fallbacku i jawnego sygnału błędu, aby utrzymać responsywność aplikacji.
# JAK TO DZIAŁA: `run_guarded` wykonuje operację, a przy błędzie zwraca `GuardedExecutionResult`
#                z `value=None` i deskryptorem błędu, który UI może pokazać bez crash/freeze.
# TODO: Dodać metryki liczby degradacji per moduł i alarm po przekroczeniu progu.
@dataclass(frozen=True, slots=True)
class GuardedExecutionResult(Generic[T]):
    """Wynik operacji wykonanej w granicy błędów."""

    value: T | None
    error: ErrorDescriptor | None
    degraded: bool


class ErrorBoundary:
    """Exception mapper and guarded executor for UI-safe degradation."""

    def map_exception(self, exc: BaseException) -> ErrorDescriptor:
        """Map exception instance to stable error descriptor."""
        if isinstance(exc, TimeoutError):
            code = ErrorCode.UI_GUARDED_OPERATION_FAILED
            return ErrorDescriptor(code=code, message="Przekroczono limit czasu operacji UI.", details=str(exc))
        if isinstance(exc, ConnectionError):
            code = ErrorCode.UI_GUARDED_OPERATION_FAILED
            return ErrorDescriptor(code=code, message="Utracono połączenie z usługą zależną.", details=str(exc))
        if isinstance(exc, (ValueError, TypeError)):
            code = ErrorCode.CONFIG_INVALID_VALUE
            return ErrorDescriptor(code=code, message="Odrzucono nieprawidłowe dane wejściowe.", details=str(exc))

        code = ErrorCode.UNKNOWN_RUNTIME_ERROR
        return ErrorDescriptor(code=code, message=DEFAULT_ERROR_MESSAGES[code], details=str(exc))

    def run_guarded(self, operation: Callable[[], T]) -> GuardedExecutionResult[T]:
        """Run operation and degrade gracefully on exception."""
        try:
            return GuardedExecutionResult(value=operation(), error=None, degraded=False)
        except Exception as exc:  # noqa: BLE001
            return GuardedExecutionResult(
                value=None,
                error=self.map_exception(exc),
                degraded=True,
            )
