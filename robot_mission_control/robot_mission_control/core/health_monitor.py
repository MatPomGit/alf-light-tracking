"""Health monitoring primitives for workers and communication channels."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum


# [AI-CHANGE | 2026-04-20 19:12 UTC | v0.145]
# CO ZMIENIONO: Dodano model monitoringu zdrowia workerów i kanałów komunikacji z heartbeat,
#               rejestracją incydentów, polityką restartu (exponential backoff) oraz circuit breaker.
# DLACZEGO: Potrzebujemy izolacji awarii oraz deterministycznej reakcji na stale błędne kanały,
#           aby utrzymać działanie reszty aplikacji i nie propagować błędnych stanów.
# JAK TO DZIAŁA: HealthMonitor przechowuje heartbeat per worker/kanał, zlicza błędy,
#                wylicza opóźnienie restartu, otwiera/zamyka circuit breaker i zapisuje incydenty.
# TODO: Dodać trwały eksport incydentów do dedykowanego backendu telemetrycznego (np. plik JSONL/OTLP).


class WorkerLifecycleState(Enum):
    """Lifecycle state for managed workers."""

    INIT = "INIT"
    RUNNING = "RUNNING"
    STOPPED = "STOPPED"
    FAILED = "FAILED"
    RESTARTING = "RESTARTING"


@dataclass(slots=True)
class HeartbeatState:
    """Current heartbeat metadata for worker/channel."""

    last_seen: datetime | None = None
    misses: int = 0


@dataclass(slots=True)
class CircuitBreakerState:
    """Circuit breaker state for unstable channels."""

    consecutive_failures: int = 0
    opened_until: datetime | None = None


@dataclass(frozen=True, slots=True)
class IncidentRecord:
    """Single operational incident used for diagnostics and audits."""

    timestamp: datetime
    module: str
    code: str
    message: str
    details: str | None = None


class HealthMonitor:
    """Tracks worker/channel health with conservative error handling."""

    def __init__(
        self,
        *,
        heartbeat_timeout: timedelta = timedelta(seconds=10),
        base_backoff: timedelta = timedelta(seconds=1),
        max_backoff: timedelta = timedelta(seconds=30),
        breaker_threshold: int = 3,
        breaker_cooldown: timedelta = timedelta(seconds=30),
    ) -> None:
        self._heartbeat_timeout = heartbeat_timeout
        self._base_backoff = base_backoff
        self._max_backoff = max_backoff
        self._breaker_threshold = breaker_threshold
        self._breaker_cooldown = breaker_cooldown

        self._worker_heartbeat: dict[str, HeartbeatState] = {}
        self._channel_heartbeat: dict[str, HeartbeatState] = {}
        self._worker_states: dict[str, WorkerLifecycleState] = {}
        self._channel_breakers: dict[str, CircuitBreakerState] = {}
        self._incidents: list[IncidentRecord] = []

    def register_worker(self, module: str) -> None:
        """Register worker in INIT state."""
        self._worker_states[module] = WorkerLifecycleState.INIT
        self._worker_heartbeat[module] = HeartbeatState()

    def register_channel(self, channel: str) -> None:
        """Register channel health tracking."""
        self._channel_heartbeat[channel] = HeartbeatState()
        self._channel_breakers[channel] = CircuitBreakerState()

    def set_worker_state(self, module: str, state: WorkerLifecycleState) -> None:
        """Update lifecycle state for worker."""
        self._worker_states[module] = state

    def heartbeat_worker(self, module: str, now: datetime) -> None:
        """Mark worker heartbeat as alive."""
        state = self._worker_heartbeat.setdefault(module, HeartbeatState())
        state.last_seen = now
        state.misses = 0

    def heartbeat_channel(self, channel: str, now: datetime) -> None:
        """Mark channel heartbeat as alive."""
        state = self._channel_heartbeat.setdefault(channel, HeartbeatState())
        state.last_seen = now
        state.misses = 0

    def check_worker_timeout(self, module: str, now: datetime) -> bool:
        """Return True when worker heartbeat is stale."""
        state = self._worker_heartbeat.get(module)
        if state is None or state.last_seen is None:
            return True
        is_stale = now - state.last_seen > self._heartbeat_timeout
        if is_stale:
            state.misses += 1
        return is_stale

    def check_channel_timeout(self, channel: str, now: datetime) -> bool:
        """Return True when channel heartbeat is stale."""
        state = self._channel_heartbeat.get(channel)
        if state is None or state.last_seen is None:
            return True
        is_stale = now - state.last_seen > self._heartbeat_timeout
        if is_stale:
            state.misses += 1
        return is_stale

    def record_incident(
        self,
        *,
        module: str,
        code: str,
        message: str,
        timestamp: datetime,
        details: str | None = None,
    ) -> IncidentRecord:
        """Store incident and return stored record."""
        item = IncidentRecord(
            timestamp=timestamp,
            module=module,
            code=code,
            message=message,
            details=details,
        )
        self._incidents.append(item)
        return item

    def record_channel_failure(self, channel: str, now: datetime) -> tuple[bool, timedelta]:
        """Increase failure count and return (breaker_open, restart_delay)."""
        breaker = self._channel_breakers.setdefault(channel, CircuitBreakerState())
        breaker.consecutive_failures += 1

        delay_seconds = self._base_backoff.total_seconds() * (2 ** max(breaker.consecutive_failures - 1, 0))
        delay = timedelta(seconds=min(delay_seconds, self._max_backoff.total_seconds()))

        if breaker.consecutive_failures >= self._breaker_threshold:
            breaker.opened_until = now + self._breaker_cooldown
            return True, delay

        return False, delay

    def record_channel_success(self, channel: str) -> None:
        """Reset breaker after successful communication."""
        breaker = self._channel_breakers.setdefault(channel, CircuitBreakerState())
        breaker.consecutive_failures = 0
        breaker.opened_until = None

    def is_channel_open(self, channel: str, now: datetime) -> bool:
        """Check whether circuit breaker is open for channel."""
        breaker = self._channel_breakers.get(channel)
        if breaker is None or breaker.opened_until is None:
            return False
        if now >= breaker.opened_until:
            breaker.opened_until = None
            breaker.consecutive_failures = 0
            return False
        return True

    def get_worker_state(self, module: str) -> WorkerLifecycleState:
        """Return lifecycle state for worker or FAILED when unknown."""
        return self._worker_states.get(module, WorkerLifecycleState.FAILED)

    def incidents(self) -> tuple[IncidentRecord, ...]:
        """Read-only incident log snapshot."""
        return tuple(self._incidents)
