from g1_light_tracking.common import detection_template


def test_detection_template_has_required_keys():
    data = detection_template()
    assert 'light_spot' in data
    assert 'qr' in data
    assert 'apriltag' in data
    assert 'objects' in data
