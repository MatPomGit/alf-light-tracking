"""Supervisor for worker lifecycle and failure isolation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Callable

from robot_mission_control.core.health_monitor import HealthMonitor, WorkerLifecycleState


# [AI-CHANGE | 2026-04-20 19:12 UTC | v0.145]
# CO ZMIENIONO: Dodano Supervisor do zarządzania cyklem życia workerów (init/start/stop/restart),
#               izolacją awarii modułów, heartbeatem i obsługą błędnych kanałów z backoff/circuit breaker.
# DLACZEGO: Wymagane jest ograniczenie skutków awarii do pojedynczego modułu/panelu, bez zatrzymania
#           całej aplikacji oraz z pełnym śladem incydentów operacyjnych.
# JAK TO DZIAŁA: Supervisor opakowuje wywołania workerów w bezpieczne granice błędów, mapuje wyjątki,
#                aktualizuje HealthMonitor i pozwala oznaczać konkretny panel jako UNAVAILABLE.
# TODO: Dodać asynchroniczny scheduler restartów, aby realizować opóźnione restarty bez blokowania wątku UI.


LifecycleStep = Callable[[], None]


@dataclass(slots=True)
class WorkerModule:
    """Single worker contract with init/start/stop hooks."""

    name: str
    init_fn: LifecycleStep
    start_fn: LifecycleStep
    stop_fn: LifecycleStep


@dataclass(frozen=True, slots=True)
class ErrorCode:
    """Mapped error code record for UI/system incidents."""

    code: str
    message: str


class ErrorBoundary:
    """Global error mapper used by supervisor and UI."""

    def map_exception(self, exc: BaseException) -> ErrorCode:
        """Map runtime exception class to stable error code."""
        if isinstance(exc, TimeoutError):
            return ErrorCode(code="ERR_TIMEOUT", message="Przekroczono limit czasu operacji modułu")
        if isinstance(exc, ConnectionError):
            return ErrorCode(code="ERR_CHANNEL", message="Błąd kanału komunikacji")
        if isinstance(exc, ValueError):
            return ErrorCode(code="ERR_DATA", message="Odrzucono nieprawidłowe dane wejściowe")
        return ErrorCode(code="ERR_UI_UNHANDLED", message="Nieobsłużony wyjątek warstwy UI/modułu")


class Supervisor:
    """Coordinates worker lifecycle, restarts, channel policy and incident recording."""

    def __init__(self, health_monitor: HealthMonitor | None = None) -> None:
        self._health_monitor = health_monitor or HealthMonitor()
        self._error_boundary = ErrorBoundary()
        self._workers: dict[str, WorkerModule] = {}
        self._panel_states: dict[str, str] = {}

    def register_worker(self, module: WorkerModule) -> None:
        """Register module and initialize its lifecycle metadata."""
        self._workers[module.name] = module
        self._health_monitor.register_worker(module.name)
        self._panel_states.setdefault(module.name, "AVAILABLE")

    def register_channel(self, channel: str) -> None:
        """Register communication channel for health policies."""
        self._health_monitor.register_channel(channel)

    def init_worker(self, module_name: str, now: datetime) -> bool:
        """Initialize module in isolation boundary."""
        return self._run_worker_step(module_name, "INIT", now)

    def start_worker(self, module_name: str, now: datetime) -> bool:
        """Start module in isolation boundary."""
        return self._run_worker_step(module_name, "START", now)

    def stop_worker(self, module_name: str, now: datetime) -> bool:
        """Stop module in isolation boundary."""
        return self._run_worker_step(module_name, "STOP", now)

    def restart_worker(self, module_name: str, now: datetime) -> bool:
        """Restart module with isolated stop/start sequence."""
        self._health_monitor.set_worker_state(module_name, WorkerLifecycleState.RESTARTING)
        stop_ok = self.stop_worker(module_name, now)
        start_ok = self.start_worker(module_name, now)
        return stop_ok and start_ok

    def heartbeat_worker(self, module_name: str, now: datetime) -> None:
        """Publish worker heartbeat."""
        self._health_monitor.heartbeat_worker(module_name, now)

    def heartbeat_channel(self, channel: str, now: datetime) -> None:
        """Publish communication heartbeat."""
        self._health_monitor.heartbeat_channel(channel, now)

    def record_channel_failure(self, channel: str, now: datetime) -> tuple[bool, timedelta]:
        """Record channel error and evaluate retry/circuit breaker policy."""
        is_open, delay = self._health_monitor.record_channel_failure(channel, now)
        self._health_monitor.record_incident(
            module=channel,
            code="ERR_CHANNEL_FAILURE",
            message="Kanał komunikacji zgłosił błąd; zastosowano retry policy",
            timestamp=now,
            details=f"breaker_open={is_open}; next_retry_in={delay.total_seconds():.2f}s",
        )
        if is_open:
            self._panel_states[channel] = "UNAVAILABLE"
        return is_open, delay

    def record_channel_success(self, channel: str, now: datetime) -> None:
        """Reset channel failure counters after successful probe."""
        self._health_monitor.record_channel_success(channel)
        self._health_monitor.heartbeat_channel(channel, now)
        self._panel_states[channel] = "AVAILABLE"

    def can_use_channel(self, channel: str, now: datetime) -> bool:
        """Return False when channel circuit breaker remains open."""
        is_open = self._health_monitor.is_channel_open(channel, now)
        return not is_open

    def mark_panel_unavailable(self, panel_name: str, exc: BaseException, now: datetime) -> ErrorCode:
        """Mark only selected panel as unavailable and record mapped incident."""
        error = self._error_boundary.map_exception(exc)
        self._panel_states[panel_name] = "UNAVAILABLE"
        self._health_monitor.record_incident(
            module=panel_name,
            code=error.code,
            message=error.message,
            timestamp=now,
            details=str(exc),
        )
        self._health_monitor.set_worker_state(panel_name, WorkerLifecycleState.FAILED)
        return error

    def panel_state(self, panel_name: str) -> str:
        """Return panel availability state."""
        return self._panel_states.get(panel_name, "UNAVAILABLE")

    def incidents(self):
        """Expose incident log snapshot."""
        return self._health_monitor.incidents()

    def _run_worker_step(self, module_name: str, step: str, now: datetime) -> bool:
        worker = self._workers.get(module_name)
        if worker is None:
            self._health_monitor.record_incident(
                module=module_name,
                code="ERR_WORKER_NOT_REGISTERED",
                message="Próba wywołania niezarejestrowanego workera",
                timestamp=now,
                details=f"step={step}",
            )
            return False

        try:
            if step == "INIT":
                worker.init_fn()
                self._health_monitor.set_worker_state(module_name, WorkerLifecycleState.INIT)
            elif step == "START":
                worker.start_fn()
                self._health_monitor.set_worker_state(module_name, WorkerLifecycleState.RUNNING)
            elif step == "STOP":
                worker.stop_fn()
                self._health_monitor.set_worker_state(module_name, WorkerLifecycleState.STOPPED)
            else:
                raise ValueError(f"Unsupported step: {step}")

            self._health_monitor.heartbeat_worker(module_name, now)
            self._panel_states[module_name] = "AVAILABLE"
            return True
        except Exception as exc:  # noqa: BLE001
            error = self.mark_panel_unavailable(module_name, exc, now)
            self._health_monitor.record_incident(
                module=module_name,
                code="ERR_WORKER_STEP_FAILED",
                message="Błąd kroku lifecycle workera",
                timestamp=now,
                details=f"step={step}; mapped={error.code}",
            )
            return False
