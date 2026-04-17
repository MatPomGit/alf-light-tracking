import rclpy.time
from typing import Optional

class PIDController:
    """Regulator PID z anty-windup (metoda całkowania z ograniczeniem i wyzerowaniem przy nasyceniu)."""
    def __init__(self, kp: float, ki: float, kd: float, output_limits: tuple = (-1.0, 1.0), anti_windup: bool = True):
        self.kp = kp
        self.ki = ki
        self.kd = kd
        self.output_limits = output_limits
        self.anti_windup = anti_windup

        self._integral = 0.0
        self._prev_error = 0.0
        self._prev_time: Optional[rclpy.time.Time] = None

    def reset(self):
        self._integral = 0.0
        self._prev_error = 0.0
        self._prev_time = None

    def update(self, error: float, dt: float) -> float:
        # Proporcjonalny
        p = self.kp * error

        # Całkowy (z ograniczeniem)
        self._integral += error * dt
        # Opcjonalne ograniczenie całki (anty-windup)
        if self.anti_windup:
            max_integral = self.output_limits[1] / (self.ki + 1e-6)
            self._integral = max(-max_integral, min(max_integral, self._integral))
        i = self.ki * self._integral

        # Różniczkowy (używamy pochodnej błędu)
        if dt > 0:
            derivative = (error - self._prev_error) / dt
        else:
            derivative = 0.0
        d = self.kd * derivative
        self._prev_error = error

        output = p + i + d
        # Nasycenie wyjścia
        if self.output_limits:
            output = max(self.output_limits[0], min(self.output_limits[1], output))
            # Anty-windup: jeśli nasycone, to nie akumuluj całki
            if self.anti_windup and (output <= self.output_limits[0] or output >= self.output_limits[1]):
                self._integral -= error * dt  # wycofanie ostatniego przyrostu całki
        return output