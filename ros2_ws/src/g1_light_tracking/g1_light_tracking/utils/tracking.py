"""Pomocnicze struktury i funkcje do prostego trackingu bez filtru Kalmana.

Ten moduł opisuje minimalny stan toru oraz metryki dopasowania używane tam, gdzie wystarcza
lekki model śledzenia oparty na wygładzaniu i bramkowaniu odległości.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
import math
import time


@dataclass
class TrackState:
    track_id: str
    target_type: str
    class_name: str
    x: float
    y: float
    z: float
    center_u: float
    center_v: float
    confidence: float
    color_label: str = ''
    payload: str = ''
    source_method: str = ''
    hits: int = 1
    missed_frames: int = 0
    created_time: float = field(default_factory=time.time)
    updated_time: float = field(default_factory=time.time)

    def age_sec(self) -> float:
        return float(max(0.0, self.updated_time - self.created_time))


def distance_3d(a: TrackState, x: float, y: float, z: float) -> float:
    return math.sqrt((a.x - x)**2 + (a.y - y)**2 + (a.z - z)**2)

def distance_uv(a: TrackState, u: float, v: float) -> float:
    return math.sqrt((a.center_u - u)**2 + (a.center_v - v)**2)

def same_semantics(track: TrackState, target_type: str, class_name: str) -> bool:
    if track.target_type != target_type:
        return False
    # keep flexibility when class name missing
    if track.class_name and class_name and track.class_name != class_name:
        return False
    return True
