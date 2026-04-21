from __future__ import annotations

import logging
import sys
import types
import uuid
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any

import pytest

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


# [AI-CHANGE | 2026-04-21 18:06 UTC | v0.179]
# CO ZMIENIONO: Dodano scenariusz E2E klient-serwer Action (`goal -> feedback -> result`) na atrapach runtime
#               oraz testy reason_code dla błędów kontraktu/importu backendu.
# DLACZEGO: Potrzebujemy regresji, która potwierdza nominalny przepływ bez fallbacku `action_backend_unavailable`
#           i rozróżnia przyczynę awarii startu backendu.
# JAK TO DZIAŁA: Test tworzy atrapę `rclpy.action.ActionClient`, emuluje feedback i finalny result, a potem
#                asertywnie sprawdza dane domenowe i brak wpisów o `action_backend_unavailable` w logach.
# TODO: Dodać wariant integracyjny z realnym `rclpy` i serwerem ROS2 Action uruchamianym przez `launch_testing`.


class _FakeFuture:
    def __init__(self, value: Any = None, done: bool = True) -> None:
        self._value = value
        self._done = done

    def done(self) -> bool:
        return self._done

    def result(self) -> Any:
        return self._value


class _FakeResultMessage:
    def __init__(self, outcome: str) -> None:
        self.outcome = outcome

    def get_fields_and_field_types(self) -> dict[str, str]:
        return {"outcome": "string"}


@dataclass
class _FakeWrappedResult:
    status: int
    result: _FakeResultMessage


class _FakeGoalHandle:
    def __init__(self, goal_id_bytes: bytes, wrapped_result: _FakeWrappedResult) -> None:
        self.accepted = True
        self.goal_id = SimpleNamespace(uuid=goal_id_bytes)
        self._wrapped_result = wrapped_result

    def get_result_async(self) -> _FakeFuture:
        return _FakeFuture(self._wrapped_result)

    def cancel_goal_async(self) -> _FakeFuture:
        return _FakeFuture(SimpleNamespace(goals_canceling=[1]))


class _FakeActionClient:
    def __init__(self, node: object, action_type: type, action_name: str) -> None:
        self._feedback_callback = None
        self._goal_id = uuid.UUID("12345678-1234-5678-1234-567812345678").bytes

    def wait_for_server(self, timeout_sec: float) -> bool:  # noqa: ARG002
        return True

    def send_goal_async(self, goal_msg: object, feedback_callback: Any) -> _FakeFuture:  # noqa: ARG002
        self._feedback_callback = feedback_callback
        wrapped_result = _FakeWrappedResult(status=4, result=_FakeResultMessage(outcome="ok"))
        return _FakeFuture(_FakeGoalHandle(self._goal_id, wrapped_result))

    def emit_feedback(self, progress: float) -> None:
        assert self._feedback_callback is not None
        feedback_msg = SimpleNamespace(
            goal_id=SimpleNamespace(uuid=self._goal_id),
            feedback=SimpleNamespace(progress=progress),
        )
        self._feedback_callback(feedback_msg)


class _FakeRclpyModule:
    def __init__(self) -> None:
        self._node = SimpleNamespace(destroy_node=lambda: None)

    def create_node(self, node_name: str) -> object:  # noqa: ARG002
        return self._node

    def spin_once(self, node: object, timeout_sec: float) -> None:  # noqa: ARG002
        return

    def spin_until_future_complete(self, node: object, future: _FakeFuture, timeout_sec: float) -> None:  # noqa: ARG002
        return


def _install_fake_action_module() -> None:
    fake_action_mod = types.ModuleType("rclpy.action")
    fake_action_mod.ActionClient = _FakeActionClient
    sys.modules["rclpy.action"] = fake_action_mod


def _install_fake_contract_module(module_name: str = "fake_contract") -> None:
    fake_contract_mod = types.ModuleType(module_name)

    class _MissionStep:
        class Goal:
            def __init__(self) -> None:
                self.goal = ""

    fake_contract_mod.MissionStep = _MissionStep
    sys.modules[module_name] = fake_contract_mod


def test_action_backend_e2e_goal_feedback_result_nominal_without_unavailable_logs(caplog: pytest.LogCaptureFixture) -> None:
    _install_fake_action_module()
    _install_fake_contract_module("fake_contract_nominal")
    caplog.set_level(logging.ERROR)

    backend = Ros2MissionActionBackend(
        rclpy_module=_FakeRclpyModule(),
        config=ActionBackendConfig(
            action_name="/mission_control/execute_step",
            action_type_module="fake_contract_nominal",
            action_type_name="MissionStep",
            node_name="test_node",
            server_wait_timeout_sec=1.0,
            future_wait_timeout_sec=1.0,
        ),
    )

    assert backend.start() is True
    goal_id = backend.send_goal({"goal": "start_patrol"})
    assert goal_id is not None

    action_client = backend._action_client
    assert isinstance(action_client, _FakeActionClient)
    action_client.emit_feedback(progress=0.5)

    assert backend.fetch_progress(goal_id) == 0.5
    result = backend.fetch_result(goal_id)
    assert result is not None
    assert result["status"] == "SUCCEEDED"
    assert result["result"] == {"outcome": "ok"}
    assert "action_backend_unavailable" not in caplog.text


def test_action_backend_start_returns_contract_reason_code_for_missing_contract() -> None:
    backend = Ros2MissionActionBackend(
        rclpy_module=_FakeRclpyModule(),
        config=ActionBackendConfig(
            action_name="/mission_control/execute_step",
            action_type_module="",
            action_type_name="MissionStep",
            node_name="test_node",
            server_wait_timeout_sec=1.0,
            future_wait_timeout_sec=1.0,
        ),
    )

    assert backend.start() is False
    assert backend.last_start_reason_code == "action_contract_missing"


def test_action_backend_start_returns_import_reason_code_for_missing_module() -> None:
    _install_fake_action_module()
    backend = Ros2MissionActionBackend(
        rclpy_module=_FakeRclpyModule(),
        config=ActionBackendConfig(
            action_name="/mission_control/execute_step",
            action_type_module="module_does_not_exist_abc",
            action_type_name="MissionStep",
            node_name="test_node",
            server_wait_timeout_sec=1.0,
            future_wait_timeout_sec=1.0,
        ),
    )

    assert backend.start() is False
    assert backend.last_start_reason_code == "action_type_import_failed"
