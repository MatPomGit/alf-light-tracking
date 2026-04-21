from __future__ import annotations

from robot_mission_control.ros.action_backend import ActionBackendConfig, Ros2MissionActionBackend


def _build_backend() -> Ros2MissionActionBackend:
    return Ros2MissionActionBackend(rclpy_module=object(), config=ActionBackendConfig())


# [AI-CHANGE | 2026-04-21 17:42 UTC | v0.178]
# CO ZMIENIONO: Dodano testy jednostkowe mapowania `_status_to_label` dla pełnego zakresu kodów 0-6.
# DLACZEGO: Chroni to kontrakt translacji `GoalStatus` -> status domenowy przed regresją i błędną prezentacją UI.
# JAK TO DZIAŁA: Każdy kod ma osobną asercję oczekiwanej etykiety; test obejmuje stany terminalne i przejściowe.
# TODO: Dodać test parametryzowany dla wartości spoza zakresu oraz danych nienumerycznych (fallback `UNKNOWN`).
def test_status_to_label_maps_goal_status_codes_0_to_6() -> None:
    backend = _build_backend()

    assert backend._status_to_label(0) == "UNKNOWN"
    assert backend._status_to_label(1) == "ACCEPTED"
    assert backend._status_to_label(2) == "RUNNING"
    assert backend._status_to_label(3) == "CANCEL_REQUESTED"
    assert backend._status_to_label(4) == "SUCCEEDED"
    assert backend._status_to_label(5) == "CANCELED"
    assert backend._status_to_label(6) == "ABORTED"
