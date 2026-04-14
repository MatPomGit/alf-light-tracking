from g1_light_tracking.utils.association import point_in_bbox

def test_qr_inside_real_bbox():
    bbox = (100.0, 120.0, 220.0, 260.0)
    assert point_in_bbox(150.0, 180.0, bbox) is True
    assert point_in_bbox(90.0, 180.0, bbox) is False
