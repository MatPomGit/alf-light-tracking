from __future__ import annotations

from statistics import median
from typing import Iterable, List, Tuple


def clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


class SwayCompensator:
    def __init__(self, alpha: float = 0.20, max_shift_px: float = 45.0):
        self.alpha = float(alpha)
        self.max_shift_px = float(max_shift_px)
        self.shift_u = 0.0
        self.shift_v = 0.0

    def update_from_deltas(self, deltas: Iterable[Tuple[float, float]]) -> Tuple[float, float]:
        deltas = list(deltas)
        if not deltas:
            self.shift_u *= 0.85
            self.shift_v *= 0.85
            return self.shift_u, self.shift_v

        du = median([d[0] for d in deltas])
        dv = median([d[1] for d in deltas])
        du = clamp(du, -self.max_shift_px, self.max_shift_px)
        dv = clamp(dv, -self.max_shift_px, self.max_shift_px)

        a = self.alpha
        self.shift_u = (1.0 - a) * self.shift_u + a * du
        self.shift_v = (1.0 - a) * self.shift_v + a * dv
        return self.shift_u, self.shift_v

    def compensate_uv(self, u: float, v: float) -> Tuple[float, float]:
        return float(u - self.shift_u), float(v - self.shift_v)

    def compensate_bbox(self, x_min: float, y_min: float, x_max: float, y_max: float) -> Tuple[float, float, float, float]:
        return (
            float(x_min - self.shift_u),
            float(y_min - self.shift_v),
            float(x_max - self.shift_u),
            float(y_max - self.shift_v),
        )
