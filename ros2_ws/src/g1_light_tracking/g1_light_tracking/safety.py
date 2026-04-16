"""Narzędzia safety dla warstwy E-STOP.

Moduł zawiera czystą logikę bezpieczeństwa bez zależności od runtime ROS2,
dzięki czemu można ją łatwo testować jednostkowo.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class SafetyStopController:
    """Kontroler logiki E-STOP niezależny od transportu ROS."""

    heartbeat_timeout_sec: float
    auto_estop_on_missing_mission_sec: float
    auto_estop_on_depth_obstacle: bool
    obstacle_clearance_threshold_m: float

    estop_latched: bool = False
    estop_reason: str = 'none'
    last_cmd_time_sec: float | None = None
    last_mission_time_sec: float | None = None

    def trigger_estop(self, reason: str) -> bool:
        """Aktywuje E-STOP i zwraca informację, czy był to nowy trigger."""
        was_active = self.estop_latched
        self.estop_latched = True
        self.estop_reason = reason
        return not was_active

    def reset_estop(self) -> bool:
        """Resetuje latch E-STOP i zwraca informację, czy stan faktycznie się zmienił."""
        was_active = self.estop_latched
        self.estop_latched = False
        self.estop_reason = 'none'
        return was_active

    def observe_cmd(self, now_sec: float) -> None:
        """Aktualizuje heartbeat źródła komend ruchu."""
        self.last_cmd_time_sec = now_sec

    def observe_mission(self, now_sec: float) -> None:
        """Aktualizuje heartbeat stanu misji."""
        self.last_mission_time_sec = now_sec

    def evaluate_auto_estop(self, now_sec: float) -> str | None:
        """Sprawdza warunki automatycznego E-STOP i zwraca przyczynę, jeśli zaszła."""
        if self.estop_latched:
            return None

        if self.heartbeat_timeout_sec > 0.0 and self.last_cmd_time_sec is not None:
            if now_sec - self.last_cmd_time_sec > self.heartbeat_timeout_sec:
                return 'watchdog'

        if self.auto_estop_on_missing_mission_sec > 0.0 and self.last_mission_time_sec is not None:
            if now_sec - self.last_mission_time_sec > self.auto_estop_on_missing_mission_sec:
                return 'mission_timeout'

        return None

    def evaluate_depth_obstacle(self, depth_available: bool, forward_clearance_m: float) -> str | None:
        """Weryfikuje warunek E-STOP oparty o mapę głębi."""
        if self.estop_latched or not self.auto_estop_on_depth_obstacle:
            return None
        if depth_available and forward_clearance_m <= self.obstacle_clearance_threshold_m:
            return 'obstacle'
        return None
