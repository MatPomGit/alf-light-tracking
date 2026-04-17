"""Pomocnicze struktury i operacje filtru Kalmana używanego przez tracking.

Model stanu zakłada pozycję 3D i prędkość liniową. Funkcje w tym module odpowiadają za
inicjalizację, predykcję i aktualizację stanu oraz za metryki geometryczne pomocne
podczas dopasowywania obserwacji do torów.
"""

from dataclasses import dataclass, field
import math
import time
from typing import Optional, Tuple
import numpy as np


@dataclass
class TrackState:
    track_id: str
    target_type: str
    class_name: str
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
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0
    x_min: float = 0.0
    y_min: float = 0.0
    x_max: float = 0.0
    y_max: float = 0.0
    state: Optional[np.ndarray] = None
    cov: Optional[np.ndarray] = None

    def age_sec(self) -> float:
        return float(max(0.0, self.updated_time - self.created_time))

    def bbox(self) -> Tuple[float, float, float, float]:
        return (self.x_min, self.y_min, self.x_max, self.y_max)


def same_semantics(track: TrackState, target_type: str, class_name: str) -> bool:
    if track.target_type != target_type:
        return False
    if target_type in {'person', 'parcel_box', 'shelf', 'planar_surface'}:
        if track.class_name and class_name and track.class_name != class_name:
            return False
    return True


def distance_3d(track: TrackState, x: float, y: float, z: float) -> float:
    return math.sqrt((track.x - x) ** 2 + (track.y - y) ** 2 + (track.z - z) ** 2)


def distance_uv(track: TrackState, u: float, v: float) -> float:
    return math.sqrt((track.center_u - u) ** 2 + (track.center_v - v) ** 2)


def bbox_center_jump(track: TrackState, x_min: float, y_min: float, x_max: float, y_max: float) -> float:
    cu1 = (track.x_min + track.x_max) / 2.0
    cv1 = (track.y_min + track.y_max) / 2.0
    cu2 = (x_min + x_max) / 2.0
    cv2 = (y_min + y_max) / 2.0
    return math.sqrt((cu1 - cu2) ** 2 + (cv1 - cv2) ** 2)


def bbox_iou(a: Tuple[float, float, float, float], b: Tuple[float, float, float, float]) -> float:
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    ix1 = max(ax1, bx1)
    iy1 = max(ay1, by1)
    ix2 = min(ax2, bx2)
    iy2 = min(ay2, by2)
    iw = max(0.0, ix2 - ix1)
    ih = max(0.0, iy2 - iy1)
    inter = iw * ih
    a_area = max(0.0, ax2 - ax1) * max(0.0, ay2 - ay1)
    b_area = max(0.0, bx2 - bx1) * max(0.0, by2 - by1)
    denom = a_area + b_area - inter
    if denom <= 1e-9:
        return 0.0
    return float(inter / denom)


def init_kalman_state(x: float, y: float, z: float):
    state = np.array([[x], [y], [z], [0.0], [0.0], [0.0]], dtype=float)
    cov = np.eye(6, dtype=float) * 1.0
    cov[3:, 3:] *= 10.0
    return state, cov


def predict_kalman(track: TrackState, dt: float, process_noise_pos: float, process_noise_vel: float) -> None:
    if track.state is None or track.cov is None:
        return
    F = np.array([
        [1, 0, 0, dt, 0, 0],
        [0, 1, 0, 0, dt, 0],
        [0, 0, 1, 0, 0, dt],
        [0, 0, 0, 1, 0, 0],
        [0, 0, 0, 0, 1, 0],
        [0, 0, 0, 0, 0, 1],
    ], dtype=float)
    Q = np.diag([
        process_noise_pos, process_noise_pos, process_noise_pos,
        process_noise_vel, process_noise_vel, process_noise_vel,
    ])
    track.state = F @ track.state
    track.cov = F @ track.cov @ F.T + Q
    track.x = float(track.state[0, 0])
    track.y = float(track.state[1, 0])
    track.z = float(track.state[2, 0])


def update_kalman(track: TrackState, meas_x: float, meas_y: float, meas_z: float, measurement_noise_pos: float) -> None:
    if track.state is None or track.cov is None:
        track.state, track.cov = init_kalman_state(meas_x, meas_y, meas_z)
    H = np.array([
        [1, 0, 0, 0, 0, 0],
        [0, 1, 0, 0, 0, 0],
        [0, 0, 1, 0, 0, 0],
    ], dtype=float)
    R = np.eye(3, dtype=float) * measurement_noise_pos
    z = np.array([[meas_x], [meas_y], [meas_z]], dtype=float)
    innovation = z - H @ track.state
    S = H @ track.cov @ H.T + R
    K = track.cov @ H.T @ np.linalg.inv(S)
    I = np.eye(6, dtype=float)
    track.state = track.state + K @ innovation
    track.cov = (I - K @ H) @ track.cov
    track.x = float(track.state[0, 0])
    track.y = float(track.state[1, 0])
    track.z = float(track.state[2, 0])
