from __future__ import annotations

import time
from typing import Any

import rclpy
from rclpy.action import ActionServer, CancelResponse, GoalResponse
from rclpy.node import Node

from robot_mission_control.action import MissionStep

# [AI-CHANGE | 2026-04-29 13:15 UTC | v0.332]
# CO ZMIENIONO: Serwer testowy importuje `MissionStep` z lokalnego pakietu `robot_mission_control.action`.
# DLACZEGO: Po scaleniu pakietów typ Action nie jest już dostarczany przez `robot_mission_control_interfaces`;
#           import ze starej lokalizacji blokowałby test E2E i mógłby ukryć brak wygenerowanego kontraktu.
# JAK TO DZIAŁA: Serwer akceptuje wyłącznie poprawne cele (`goal` niepusty), publikuje progres 0.2..1.0,
#                obsługuje cancel przez `goal_handle.is_cancel_requested` i zwraca spójny `Result` z reason_code.
# TODO: Rozszerzyć serwer o profile scenariuszy (success/abort/timeout) sterowane parametrem ROS2.
class MissionStepActionTestServer(Node):
    def __init__(self) -> None:
        super().__init__("mission_step_action_test_server")
        self._action_server = ActionServer(
            self,
            MissionStep,
            "/mission_control/execute_step",
            goal_callback=self._on_goal,
            cancel_callback=self._on_cancel,
            execute_callback=self._execute,
        )

    def _on_goal(self, goal_request: MissionStep.Goal) -> GoalResponse:
        if not goal_request.goal.strip():
            self.get_logger().warning("Odrzucono goal: pole `goal` jest puste.")
            return GoalResponse.REJECT
        return GoalResponse.ACCEPT

    def _on_cancel(self, goal_handle: Any) -> CancelResponse:  # noqa: ARG002
        return CancelResponse.ACCEPT

    def _execute(self, goal_handle: Any) -> MissionStep.Result:
        for step in range(1, 6):
            if goal_handle.is_cancel_requested:
                goal_handle.canceled()
                cancel_result = MissionStep.Result()
                cancel_result.outcome = "cancelled"
                cancel_result.success = False
                cancel_result.reason_code = "cancelled_by_client"
                return cancel_result

            feedback_msg = MissionStep.Feedback()
            feedback_msg.progress = step / 5.0
            feedback_msg.stage = f"stage_{step}"
            feedback_msg.detail = "processing"
            goal_handle.publish_feedback(feedback_msg)
            time.sleep(0.2)

        goal_handle.succeed()
        result = MissionStep.Result()
        result.outcome = "step_completed"
        result.success = True
        result.reason_code = ""
        return result


def main() -> None:
    rclpy.init()
    node = MissionStepActionTestServer()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
