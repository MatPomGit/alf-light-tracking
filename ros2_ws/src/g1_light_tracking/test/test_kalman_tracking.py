from g1_light_tracking.utils.kalman_tracking import TrackState, init_kalman_state, predict_kalman, update_kalman

def test_kalman_predict_update():
    tr = TrackState(
        track_id='person_0001',
        target_type='person',
        class_name='person',
        x=0.0, y=0.0, z=2.0,
        center_u=100.0, center_v=50.0,
        confidence=0.9
    )
    tr.state, tr.cov = init_kalman_state(0.0, 0.0, 2.0)
    predict_kalman(tr, 0.1, 1.0e-2, 5.0e-2)
    update_kalman(tr, 0.1, 0.0, 2.1, 8.0e-2)
    assert tr.state is not None
    assert tr.cov is not None
    assert tr.z > 2.0
