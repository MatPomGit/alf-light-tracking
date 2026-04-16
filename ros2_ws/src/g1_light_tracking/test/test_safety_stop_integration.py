from g1_light_tracking.safety import SafetyStopController


def test_command_flow_and_latched_stop_reset_cycle():
    """Prosty test integracyjny reguł przepływu cmd_vel bez uruchamiania ROS graph."""
    controller = SafetyStopController(
        heartbeat_timeout_sec=0.25,
        auto_estop_on_missing_mission_sec=0.0,
        auto_estop_on_depth_obstacle=False,
        obstacle_clearance_threshold_m=0.45,
    )

    # Etap 1: heartbeat jest świeży, więc nie ma auto E-STOP.
    controller.observe_cmd(0.0)
    assert controller.evaluate_auto_estop(0.10) is None

    # Etap 2: po przekroczeniu timeout aktywuje się watchdogowy E-STOP.
    reason = controller.evaluate_auto_estop(0.30)
    assert reason == 'watchdog'
    assert controller.trigger_estop(reason) is True
    assert controller.estop_latched is True

    # Etap 3: nawet po nadejściu heartbeat latch pozostaje aktywny do ręcznego resetu.
    controller.observe_cmd(0.31)
    assert controller.estop_latched is True

    # Etap 4: reset przywraca przepuszczanie komend.
    assert controller.reset_estop() is True
    assert controller.estop_latched is False

    # Etap 5: po resecie i świeżym heartbeat system ponownie działa normalnie.
    controller.observe_cmd(0.32)
    assert controller.evaluate_auto_estop(0.40) is None
