from dataclasses import dataclass, field
import math
import time
from typing import Dict, Optional


@dataclass
class BindingState:
    qr_track_id: str
    parcel_box_track_id: str
    qr_payload: str
    association_score: float
    hits: int = 1
    last_update_time: float = field(default_factory=time.time)

    def age_sec(self) -> float:
        return max(0.0, time.time() - self.last_update_time)


def point_in_bbox(u: float, v: float, bbox) -> bool:
    x1, y1, x2, y2 = bbox
    return x1 <= u <= x2 and y1 <= v <= y2


def bbox_center_distance(qr_u: float, qr_v: float, box_u: float, box_v: float) -> float:
    return math.sqrt((qr_u - box_u) ** 2 + (qr_v - box_v) ** 2)


def association_score(qr_u: float, qr_v: float, box_u: float, box_v: float, box_bbox, max_center_px: float, inside_bonus: float) -> float:
    d = bbox_center_distance(qr_u, qr_v, box_u, box_v)
    if d > max_center_px:
        return -1.0
    score = max(0.0, 1.0 - d / max_center_px)
    if point_in_bbox(qr_u, qr_v, box_bbox):
        score += inside_bonus
    return score
