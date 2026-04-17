from g1_light_tracking.safety import SafetyStopController


def test_estop_is_latched_until_manual_reset():
    controller = SafetyStopController(
        heartbeat_timeout_sec=0.5,
        auto_estop_on_missing_mission_sec=2.0,
        auto_estop_on_depth_obstacle=False,
        obstacle_clearance_threshold_m=0.45,
    )

    assert controller.trigger_estop('manual') is True
    assert controller.estop_latched is True
    assert controller.estop_reason == 'manual'

    # Ponowny trigger nie zmienia stanu latch i jest traktowany jako brak nowej zmiany.
    assert controller.trigger_estop('watchdog') is False
    assert controller.estop_latched is True

    assert controller.reset_estop() is True
    assert controller.estop_latched is False
    assert controller.estop_reason == 'none'


def test_watchdog_auto_estop_when_heartbeat_stale():
    controller = SafetyStopController(
        heartbeat_timeout_sec=0.5,
        auto_estop_on_missing_mission_sec=0.0,
        auto_estop_on_depth_obstacle=False,
        obstacle_clearance_threshold_m=0.45,
    )

    controller.observe_cmd(10.0)
    assert controller.evaluate_auto_estop(10.4) is None
    assert controller.evaluate_auto_estop(10.6) == 'watchdog'


def test_depth_obstacle_auto_estop_when_enabled():
    controller = SafetyStopController(
        heartbeat_timeout_sec=1.0,
        auto_estop_on_missing_mission_sec=0.0,
        auto_estop_on_depth_obstacle=True,
        obstacle_clearance_threshold_m=0.45,
    )

    assert controller.evaluate_depth_obstacle(depth_available=True, forward_clearance_m=0.30) == 'obstacle'
    assert controller.evaluate_depth_obstacle(depth_available=True, forward_clearance_m=0.60) is None
