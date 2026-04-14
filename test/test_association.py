from g1_light_tracking.utils.association import point_in_bbox, association_score

def test_point_in_bbox():
    assert point_in_bbox(5, 5, (0, 0, 10, 10)) is True
    assert point_in_bbox(15, 5, (0, 0, 10, 10)) is False

def test_association_score_prefers_inside():
    s1 = association_score(50, 50, 55, 55, (0, 0, 100, 100), 140.0, 0.35)
    s2 = association_score(50, 50, 120, 120, (80, 80, 160, 160), 140.0, 0.35)
    assert s1 > s2
