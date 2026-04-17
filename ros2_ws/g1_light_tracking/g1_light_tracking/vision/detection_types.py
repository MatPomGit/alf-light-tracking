from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple


# [AI-CHANGE | 2026-04-17 16:19 UTC | v0.122]
# CO ZMIENIONO: Przeniesiono definicję modelu `Detection` z pliku `types.py`
# do nowego modułu `detection_types.py` o nazwie bezpiecznej dla importów Pythona.
# DLACZEGO: Poprzednia nazwa pliku kolidowała ze standardowym modułem `types`,
# przez co uruchomienie `detectors.py` mogło zepsuć importy biblioteki standardowej
# i zatrzymać cały pipeline jeszcze przed etapem detekcji.
# JAK TO DZIAŁA: Kod importuje teraz `Detection` z modułu, który nie zasłania
# bibliotek standardowych, więc interpreter może poprawnie załadować `types`
# i dopiero potem lokalne zależności pakietu `vision`.
# TODO: Rozważyć wydzielenie wszystkich modeli domenowych do osobnego modułu
# `models.py`, aby uniknąć podobnych kolizji nazw przy dalszym rozwoju pakietu.
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
