# [AI-CHANGE | 2026-04-17 13:06 UTC | v0.91]
# CO ZMIENIONO: Dodano komentarze opisujące przeznaczenie klas i metod oraz motywację przyjętej struktury.
# DLACZEGO: Ułatwia to bezpieczne utrzymanie kodu R&D i ogranicza ryzyko błędnej interpretacji logiki detekcji.
# JAK TO DZIAŁA: Każda klasa/metoda posiada docstring z celem i uzasadnieniem, dzięki czemu intencja implementacji jest jawna.
# TODO: Rozszerzyć docstringi o kontrakty wejścia/wyjścia po ustabilizowaniu API między węzłami.

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
