from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple


@dataclass
class Detection:
    """
    Cel: Ta klasa realizuje odpowiedzialność `Detection` w aktualnym module.
    Dlaczego tak: Wydzielenie tej jednostki upraszcza debugowanie i chroni krytyczne ścieżki przed niekontrolowanymi zmianami.
    """
    x: float
    y: float
    area: float
    perimeter: float
    circularity: float
    radius: float
    bbox_x: int
    bbox_y: int
    bbox_w: int
    bbox_h: int
    confidence: float = 0.0
    ellipse_center: Optional[Tuple[float, float]] = None
    ellipse_axes: Optional[Tuple[float, float]] = None
    ellipse_angle: Optional[float] = None
    rank: int = 0
