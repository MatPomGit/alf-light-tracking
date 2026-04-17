import math

from g1_light_tracking.utils.legacy_adapter import normalize_legacy_payload


def test_normalize_legacy_payload_builds_bbox_from_radius_and_area():
    payload = {
        'detected': True,
        'frame_id': 'camera_optical',
        'x': 320.0,
        'y': 120.0,
        'radius': 8.0,
        'area': 200.0,
        'confidence': 0.9,
        'track_id': 7,
    }
    det = normalize_legacy_payload(payload)
    assert det.frame_id == 'camera_optical'
    assert det.track_id == '7'
    assert det.x_min == 312.0
    assert det.x_max == 328.0
    assert det.y_min == 112.0
    assert det.y_max == 128.0
    assert det.is_confirmed is True


def test_normalize_legacy_payload_uses_world_position_when_available():
    payload = {
        'detected': True,
        'x': 400.0,
        'y': 120.0,
        'z_world': 2.2,
        'x_world': 0.35,
        'y_world': -0.1,
        'confidence': 0.8,
    }
    det = normalize_legacy_payload(payload, min_confidence=0.5)
    assert math.isclose(det.position_x, 0.35)
    assert math.isclose(det.position_y, -0.1)
    assert math.isclose(det.position_z, 2.2)
    assert det.is_confirmed is True


def test_normalize_legacy_payload_estimates_lateral_position_from_pixels():
    payload = {
        'detected': True,
        'x': 419.5,
        'y': 180.0,
        'z': 1.5,
        'confidence': 0.4,
    }
    det = normalize_legacy_payload(payload, camera_cx=319.5, camera_fx=500.0, min_confidence=0.5)
    assert math.isclose(det.position_x, 0.3, rel_tol=1e-6)
    assert math.isclose(det.position_z, 1.5, rel_tol=1e-6)
    assert det.is_confirmed is False
