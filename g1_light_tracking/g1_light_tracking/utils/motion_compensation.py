from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

import cv2
import numpy as np


@dataclass
class MotionEstimate:
    shift_u: float = 0.0
    shift_v: float = 0.0
    confidence: float = 0.0
    used_homography: bool = False


class GlobalMotionCompensator:
    def __init__(
        self,
        max_corners: int = 250,
        quality_level: float = 0.01,
        min_distance: float = 8.0,
        block_size: int = 7,
        lk_win_size: int = 21,
        lk_max_level: int = 3,
        homography_ransac_thresh: float = 3.0,
        alpha: float = 0.25,
        max_shift_px: float = 60.0,
    ):
        self.max_corners = int(max_corners)
        self.quality_level = float(quality_level)
        self.min_distance = float(min_distance)
        self.block_size = int(block_size)
        self.lk_win_size = int(lk_win_size)
        self.lk_max_level = int(lk_max_level)
        self.homography_ransac_thresh = float(homography_ransac_thresh)
        self.alpha = float(alpha)
        self.max_shift_px = float(max_shift_px)

        self.prev_gray: Optional[np.ndarray] = None
        self.shift_u = 0.0
        self.shift_v = 0.0

    def reset(self):
        self.prev_gray = None
        self.shift_u = 0.0
        self.shift_v = 0.0

    def _clamp(self, value: float) -> float:
        return max(-self.max_shift_px, min(self.max_shift_px, float(value)))

    def update_from_frame(self, frame_bgr: np.ndarray) -> MotionEstimate:
        gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
        if self.prev_gray is None:
            self.prev_gray = gray
            return MotionEstimate(0.0, 0.0, 0.0, False)

        prev_pts = cv2.goodFeaturesToTrack(
            self.prev_gray,
            maxCorners=self.max_corners,
            qualityLevel=self.quality_level,
            minDistance=self.min_distance,
            blockSize=self.block_size,
        )
        if prev_pts is None or len(prev_pts) < 8:
            self.prev_gray = gray
            self.shift_u *= 0.85
            self.shift_v *= 0.85
            return MotionEstimate(self.shift_u, self.shift_v, 0.1, False)

        next_pts, status, _ = cv2.calcOpticalFlowPyrLK(
            self.prev_gray,
            gray,
            prev_pts,
            None,
            winSize=(self.lk_win_size, self.lk_win_size),
            maxLevel=self.lk_max_level,
            criteria=(cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 30, 0.01),
        )
        if next_pts is None or status is None:
            self.prev_gray = gray
            return MotionEstimate(self.shift_u, self.shift_v, 0.0, False)

        good_prev = prev_pts[status.flatten() == 1]
        good_next = next_pts[status.flatten() == 1]
        if len(good_prev) < 8:
            self.prev_gray = gray
            return MotionEstimate(self.shift_u, self.shift_v, 0.05, False)

        H, mask = cv2.findHomography(good_prev, good_next, cv2.RANSAC, self.homography_ransac_thresh)
        used_h = H is not None and mask is not None and int(mask.sum()) >= 8

        if used_h:
            du = float(H[0, 2])
            dv = float(H[1, 2])
            confidence = float(mask.sum()) / float(len(mask))
        else:
            deltas = (good_next.reshape(-1, 2) - good_prev.reshape(-1, 2))
            du = float(np.median(deltas[:, 0]))
            dv = float(np.median(deltas[:, 1]))
            confidence = min(0.5, len(good_prev) / max(1.0, self.max_corners))

        du = self._clamp(du)
        dv = self._clamp(dv)

        a = self.alpha
        self.shift_u = (1.0 - a) * self.shift_u + a * du
        self.shift_v = (1.0 - a) * self.shift_v + a * dv
        self.prev_gray = gray
        return MotionEstimate(self.shift_u, self.shift_v, confidence, used_h)

    def compensate_uv(self, u: float, v: float) -> Tuple[float, float]:
        return float(u - self.shift_u), float(v - self.shift_v)

    def compensate_bbox(self, x_min: float, y_min: float, x_max: float, y_max: float) -> Tuple[float, float, float, float]:
        return (
            float(x_min - self.shift_u),
            float(y_min - self.shift_v),
            float(x_max - self.shift_u),
            float(y_max - self.shift_v),
        )
