"""Helpers for translating legacy JSON detections into modern message-shaped data.

The legacy stack emits a compact JSON payload on ``/light_tracking/detection_json``.
The modern stack expects structured ROS 2 messages such as ``Detection2D`` and
``TrackedTarget``. This module normalizes the legacy payload and computes a stable
set of geometric fields so that a ROS node can publish both representations.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import math
from typing import Any


@dataclass(frozen=True)
class LegacyNormalizedDetection:
    detected: bool
    frame_id: str
    target_type: str
    class_name: str
    confidence: float
    center_u: float
    center_v: float
    x_min: float
    y_min: float
    x_max: float
    y_max: float
    color_label: str
    payload: str
    track_id: str
    position_x: float
    position_y: float
    position_z: float
    source_method: str
    is_confirmed: bool
    raw: dict[str, Any]


def _to_float(value: Any, default: float = math.nan) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _finite_or(value: float, fallback: float) -> float:
    return value if math.isfinite(value) else fallback


def _compute_half_extent(area: float, radius: float) -> float:
    if math.isfinite(radius) and radius > 0.0:
        return max(radius, 2.0)
    if math.isfinite(area) and area > 0.0:
        return max(math.sqrt(area / math.pi), 2.0)
    return 6.0


def parse_legacy_payload(data: str) -> dict[str, Any]:
    payload = json.loads(data)
    if not isinstance(payload, dict):
        raise ValueError('Legacy detection payload must be a JSON object.')
    return payload


def normalize_legacy_payload(
    payload: dict[str, Any],
    *,
    default_frame_id: str = 'camera_link',
    default_target_type: str = 'light_spot',
    default_class_name: str = 'legacy_light',
    camera_cx: float = 319.5,
    camera_fx: float = 600.0,
    assumed_depth_m: float = 1.0,
    min_confidence: float = 0.0,
) -> LegacyNormalizedDetection:
    detected = bool(payload.get('detected', False))
    frame_id = str(payload.get('frame_id') or default_frame_id)
    target_type = str(payload.get('target_type') or default_target_type)
    class_name = str(payload.get('class_name') or default_class_name)

    confidence = max(0.0, min(1.0, _to_float(payload.get('confidence'), 0.0)))
    if not detected:
        confidence = 0.0

    center_u = _to_float(payload.get('x'))
    center_v = _to_float(payload.get('y'))
    if not math.isfinite(center_u):
        center_u = _to_float(payload.get('center_u'), camera_cx)
    if not math.isfinite(center_v):
        center_v = _to_float(payload.get('center_v'), 0.0)

    area = _to_float(payload.get('area'))
    radius = _to_float(payload.get('radius'))
    half_extent = _compute_half_extent(area, radius)
    x_min = _to_float(payload.get('x_min'), center_u - half_extent)
    y_min = _to_float(payload.get('y_min'), center_v - half_extent)
    x_max = _to_float(payload.get('x_max'), center_u + half_extent)
    y_max = _to_float(payload.get('y_max'), center_v + half_extent)

    if x_max < x_min:
        x_min, x_max = x_max, x_min
    if y_max < y_min:
        y_min, y_max = y_max, y_min

    color_label = str(payload.get('color_label') or '')
    track_id_raw = payload.get('track_id', '')
    track_id = str(track_id_raw).strip() if track_id_raw not in (None, '') else ''
    if detected and not track_id:
        track_id = 'legacy-light-1'

    payload_text = str(payload.get('payload') or '')
    if not payload_text:
        payload_text = json.dumps(payload, separators=(',', ':'), sort_keys=True)

    x_world = _to_float(payload.get('x_world'))
    y_world = _to_float(payload.get('y_world'))
    z_world = _to_float(payload.get('z_world'))
    x_local = _to_float(payload.get('x'))
    y_local = _to_float(payload.get('y'))
    z_local = _to_float(payload.get('z'))

    position_z = _finite_or(z_world, _finite_or(z_local, assumed_depth_m))
    if position_z <= 0.0:
        position_z = assumed_depth_m
    position_x = _finite_or(x_world, 0.0)
    position_y = _finite_or(y_world, _finite_or(y_local, 0.0))
    if not math.isfinite(x_world):
        # Convert pixel offset into a coarse lateral estimate in camera frame.
        position_x = (center_u - camera_cx) * position_z / max(camera_fx, 1e-6)

    source_method = str(payload.get('source_method') or 'legacy_json_adapter')
    is_confirmed = detected and confidence >= min_confidence

    return LegacyNormalizedDetection(
        detected=detected,
        frame_id=frame_id,
        target_type=target_type,
        class_name=class_name,
        confidence=confidence,
        center_u=center_u,
        center_v=center_v,
        x_min=x_min,
        y_min=y_min,
        x_max=x_max,
        y_max=y_max,
        color_label=color_label,
        payload=payload_text,
        track_id=track_id,
        position_x=position_x,
        position_y=position_y,
        position_z=position_z,
        source_method=source_method,
        is_confirmed=is_confirmed,
        raw=dict(payload),
    )
