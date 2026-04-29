from __future__ import annotations

import time
import unittest
import uuid
from typing import Any

import pytest

# [AI-CHANGE | 2026-04-29 00:00 UTC | v0.207]
# CO ZMIENIONO: Dodano warunkowe pomijanie testu E2E, gdy brak zależności ROS2 `launch`/`launch_ros`/`launch_testing`/`rclpy`.
# DLACZEGO: W CI bez pełnego środowiska ROS2 kolekcja testów kończyła się błędem importu, co przerywało cały etap testów.
# JAK TO DZIAŁA: `pytest.importorskip` sprawdza moduły podczas importu pliku; przy braku zależności test jest oznaczany jako
#                `skipped`, dzięki czemu pipeline nie raportuje fałszywego błędu kolekcji i zachowuje deterministyczny wynik.
# TODO: Rozdzielić testy E2E do osobnego joba CI z preinstalowanym ROS2 Jazzy i `launch_testing`.
# [AI-CHANGE | 2026-04-29 12:00 UTC | v0.207]
# CO ZMIENIONO: Zastąpiono importy `from ... import ...` po `pytest.importorskip` bezpiecznym pobieraniem symboli z modułów.
# DLACZEGO: Ruff zgłaszał E402, ponieważ importy były poniżej kodu wykonywalnego; to blokowało etap lint w CI.
# JAK TO DZIAŁA: Najpierw warunkowo ładujemy moduły przez `pytest.importorskip`, a następnie przypisujemy wymagane klasy
#                (`GoalStatus`, `ActionClient`, `Future`, `MissionStep`) z załadowanych modułów bez dodatkowych instrukcji `import`.
# TODO: Rozważyć wydzielenie helpera do warunkowego ładowania zależności ROS2, aby uniknąć duplikacji w innych testach E2E.
launch = pytest.importorskip("launch")
launch_ros_actions = pytest.importorskip("launch_ros.actions")
launch_testing = pytest.importorskip("launch_testing")
launch_testing_actions = pytest.importorskip("launch_testing.actions")
rclpy = pytest.importorskip("rclpy")

GoalStatus = pytest.importorskip("action_msgs.msg").GoalStatus
ActionClient = pytest.importorskip("rclpy.action").ActionClient
Future = pytest.importorskip("rclpy.task").Future
MissionStep = pytest.importorskip("robot_mission_control.action").MissionStep

# [AI-CHANGE | 2026-04-29 13:15 UTC | v0.332]
# CO ZMIENIONO: Test E2E importuje `MissionStep` z `robot_mission_control.action`.
# DLACZEGO: Po scaleniu kontrakt Action jest generowany w pakiecie aplikacji; import starego pakietu interfejsów
#           dawałby fałszywy błąd integracji albo wymagał instalacji nieistniejącego już pakietu.
# JAK TO DZIAŁA: `generate_test_description` startuje serwer testowy przez `launch_ros_actions.Node`,
#                a test klienta sprawdza akceptację, feedback, wynik, anulowanie oraz bezpieczne odrzucenie pustego goal.
# TODO: Dodać raportowanie metryk czasu (latencja accept/result/cancel) do diagnostyki wydajności E2E.
@pytest.mark.launch_test
def generate_test_description() -> tuple[launch.LaunchDescription, dict[str, Any]]:
    action_server = launch_ros_actions.Node(
        package="robot_mission_control",
        executable="mission_step_action_test_server",
        name="mission_step_action_test_server",
        output="screen",
        emulate_tty=True,
    )

    return (
        launch.LaunchDescription(
            [
                action_server,
                launch_testing_actions.ReadyToTest(),
            ]
        ),
        {"action_server": action_server},
    )


class TestMissionStepActionE2ERuntime(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        rclpy.init()

    @classmethod
    def tearDownClass(cls) -> None:
        rclpy.shutdown()

    def setUp(self) -> None:
        self._node = rclpy.create_node(f"mission_step_e2e_client_{uuid.uuid4().hex[:8]}")
        self._client = ActionClient(self._node, MissionStep, "/mission_control/execute_step")
        self.assertTrue(self._client.wait_for_server(timeout_sec=10.0))

    def tearDown(self) -> None:
        self._node.destroy_node()

    def _wait_future(self, future: Future, timeout_sec: float) -> None:
        deadline = time.monotonic() + timeout_sec
        while time.monotonic() < deadline:
            rclpy.spin_once(self._node, timeout_sec=0.05)
            if future.done():
                return
        self.fail("Future nie został zakończony w czasie oczekiwania.")

    def test_real_runtime_supports_accept_feedback_result_cancel_reject(
        self, proc_output: launch_testing.io_handler.ActiveIoHandler
    ) -> None:
        feedback_progress: list[float] = []

        def _collect_feedback(message: Any) -> None:
            feedback_progress.append(float(message.feedback.progress))

        accepted_goal = MissionStep.Goal()
        accepted_goal.goal = "start_patrol"
        accepted_goal.correlation_id = "accept-feedback-result"
        accepted_goal.parameters_json = "{}"

        send_future = self._client.send_goal_async(accepted_goal, feedback_callback=_collect_feedback)
        self._wait_future(send_future, timeout_sec=5.0)
        accepted_handle = send_future.result()
        self.assertIsNotNone(accepted_handle)
        self.assertTrue(accepted_handle.accepted, "Goal powinien zostać zaakceptowany.")

        result_future = accepted_handle.get_result_async()
        self._wait_future(result_future, timeout_sec=5.0)
        accepted_result = result_future.result()
        self.assertEqual(accepted_result.status, GoalStatus.STATUS_SUCCEEDED)
        self.assertTrue(accepted_result.result.success)
        self.assertEqual(accepted_result.result.outcome, "step_completed")
        self.assertGreater(len(feedback_progress), 0, "Serwer powinien opublikować feedback.")
        self.assertGreaterEqual(max(feedback_progress), 1.0)

        cancel_goal = MissionStep.Goal()
        cancel_goal.goal = "return_to_base"
        cancel_goal.correlation_id = "cancel-flow"
        cancel_goal.parameters_json = "{}"

        cancel_send_future = self._client.send_goal_async(cancel_goal, feedback_callback=lambda _: None)
        self._wait_future(cancel_send_future, timeout_sec=5.0)
        cancel_handle = cancel_send_future.result()
        self.assertIsNotNone(cancel_handle)
        self.assertTrue(cancel_handle.accepted, "Goal do anulowania powinien zostać zaakceptowany.")

        cancel_future = cancel_handle.cancel_goal_async()
        self._wait_future(cancel_future, timeout_sec=5.0)
        cancel_response = cancel_future.result()
        self.assertTrue(cancel_response.goals_canceling, "Serwer powinien potwierdzić anulowanie goal.")

        cancel_result_future = cancel_handle.get_result_async()
        self._wait_future(cancel_result_future, timeout_sec=5.0)
        cancel_result = cancel_result_future.result()
        self.assertEqual(cancel_result.status, GoalStatus.STATUS_CANCELED)
        self.assertEqual(cancel_result.result.reason_code, "cancelled_by_client")

        reject_goal = MissionStep.Goal()
        reject_goal.goal = "   "
        reject_goal.correlation_id = "reject-flow"
        reject_goal.parameters_json = "{}"

        reject_send_future = self._client.send_goal_async(reject_goal)
        self._wait_future(reject_send_future, timeout_sec=5.0)
        reject_handle = reject_send_future.result()
        self.assertIsNotNone(reject_handle)
        self.assertFalse(reject_handle.accepted, "Niepoprawny goal musi zostać odrzucony (bezpieczny fallback).")

        proc_output.assertWaitFor("Odrzucono goal: pole `goal` jest puste.", timeout=5.0)
