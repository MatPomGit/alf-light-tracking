from g1_light_tracking.utils.tracking import TrackState, distance_3d, distance_uv, same_semantics

def test_distance_helpers():
    tr = TrackState(
        track_id='person_0001',
        target_type='person',
        class_name='person',
        x=1.0, y=0.0, z=2.0,
        center_u=100.0, center_v=50.0,
        confidence=0.9
    )
    assert round(distance_3d(tr, 1.0, 0.0, 3.0), 3) == 1.0
    assert round(distance_uv(tr, 110.0, 50.0), 3) == 10.0
    assert same_semantics(tr, 'person', 'person') is True
    assert same_semantics(tr, 'parcel_box', 'box') is False
