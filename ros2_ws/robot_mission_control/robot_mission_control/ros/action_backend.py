from __future__ import annotations

import importlib
import logging
import uuid
from dataclasses import dataclass
from typing import Any

from robot_mission_control.core.action_status import (
    ACTION_STATUS_FROM_GOAL_STATUS_CODE,
    ActionStatusLabel,
)


# [AI-CHANGE | 2026-04-21 10:35 UTC | v0.169]
# CO ZMIENIONO: Dodano produkcyjny backend ROS2 Action oparty o `rclpy.action.ActionClient`.
# DLACZEGO: Moduł operatorski potrzebuje realnej komunikacji Action zamiast transportu symulowanego/placeholderowego.
# JAK TO DZIAŁA: Backend dynamicznie ładuje typ akcji, wysyła goal, odbiera feedback/result i mapuje brak pewnych
#                danych do `None`, zachowując zasadę bezpieczeństwa "brak danych > dane błędne".
# TODO: Dodać mapowanie domenowe feedback/result na stabilny kontrakt DTO niezależny od typu ROS action.


@dataclass(frozen=True, slots=True)
class ActionBackendConfig:
    """Konfiguracja klienta ROS2 Action."""

    action_name: str = "/mission_control/execute_step"
    # [AI-CHANGE | 2026-04-29 13:15 UTC | v0.332]
    # CO ZMIENIONO: Domyślny moduł Action wskazuje teraz `robot_mission_control.action`.
    # DLACZEGO: Typ `MissionStep` jest generowany w pakiecie aplikacji; odwołanie do usuniętego pakietu interfejsów
    #           powodowałoby niedostępność backendu i mogłoby zachęcać do ręcznego obejścia błędu importu.
    # JAK TO DZIAŁA: Dynamiczny loader importuje lokalny moduł i przy niepowodzeniu zachowuje bezpieczny brak backendu.
    # TODO: Dodać diagnostykę rozróżniającą brak wygenerowanego typu od błędnej nazwy klasy w konfiguracji.
    action_type_module: str = "robot_mission_control.action"
    action_type_name: str = "MissionStep"
    node_name: str = "robot_mission_control_action_client"
    server_wait_timeout_sec: float = 1.0
    future_wait_timeout_sec: float = 2.0


class Ros2MissionActionBackend:
    """Backend realizujący transport Action na żywym runtime ROS2."""

    # [AI-CHANGE | 2026-04-21 18:06 UTC | v0.179]
    # CO ZMIENIONO: Dodano pole `last_start_reason_code` udostępniane przez property do diagnostyki startu backendu.
    # DLACZEGO: Warstwa bridge musi odczytać konkretną przyczynę awarii i opublikować ją jako `reason_code`.
    # JAK TO DZIAŁA: Po każdym `start()` backend zapisuje kod błędu; property zwraca ostatnią wartość albo `None`.
    # TODO: Wystawić ten kod także w telemetrii metryk runtime, aby skrócić diagnostykę operacyjną.
    def __init__(self, *, rclpy_module: Any, config: ActionBackendConfig, logger: logging.Logger | None = None) -> None:
        self._rclpy = rclpy_module
        self._config = config
        self._logger = logger or logging.getLogger("robot_mission_control.ros.action_backend")

        self._node = None
        self._action_client = None
        self._action_type = None
        self._goal_handles: dict[str, Any] = {}
        self._result_futures: dict[str, Any] = {}
        self._feedback_by_goal: dict[str, float] = {}
        self._last_start_reason_code: str | None = None

    @property
    def last_start_reason_code(self) -> str | None:
        """Zwraca ostatni kod przyczyny błędu startu backendu Action."""
        return self._last_start_reason_code

    # [AI-CHANGE | 2026-04-21 18:06 UTC | v0.179]
    # CO ZMIENIONO: Rozszerzono start backendu o precyzyjne `reason_code` dla błędów kontraktu i importu typu Action.
    # DLACZEGO: Warstwa wyżej musi raportować konkretną przyczynę awarii, zamiast ogólnego `action_backend_unavailable`.
    # JAK TO DZIAŁA: Start resetuje i zapisuje `self._last_start_reason_code`; przy błędzie kontraktu/importu/runtime
    #                ustawia dedykowany kod (`action_contract_missing`, `action_type_import_failed`, itd.) i zwraca `False`.
    # TODO: Dodać telemetrię liczników per `reason_code`, żeby mierzyć najczęstsze przyczyny awarii backendu.
    def start(self) -> bool:
        """Inicjalizuje node i klienta Action; przy braku kontraktu zwraca False."""
        self._last_start_reason_code = None
        if not self._has_valid_action_contract():
            self._last_start_reason_code = "action_contract_missing"
            self._logger.error("action_backend_start_failed reason_code=%s", self._last_start_reason_code)
            return False
        try:
            self._action_type = self._load_action_type()
            action_mod = importlib.import_module("rclpy.action")
            action_client_cls = getattr(action_mod, "ActionClient", None)
            create_node = getattr(self._rclpy, "create_node", None)
            if action_client_cls is None or not callable(create_node):
                self._last_start_reason_code = "action_runtime_missing"
                self._logger.error("action_backend_start_failed reason_code=%s", self._last_start_reason_code)
                return False

            self._node = create_node(self._config.node_name)
            self._action_client = action_client_cls(self._node, self._action_type, self._config.action_name)
            return True
        except (ImportError, ModuleNotFoundError) as exc:
            self._last_start_reason_code = "action_type_import_failed"
            self._logger.error(
                "action_backend_start_failed reason_code=%s error=%s",
                self._last_start_reason_code,
                exc,
            )
            self._node = None
            self._action_client = None
            self._action_type = None
            return False
        except RuntimeError as exc:
            if str(exc) == "action_type_not_found":
                self._last_start_reason_code = "action_contract_missing"
            else:
                self._last_start_reason_code = "action_backend_start_failed"
            self._logger.error(
                "action_backend_start_failed reason_code=%s error=%s",
                self._last_start_reason_code,
                exc,
            )
            self._node = None
            self._action_client = None
            self._action_type = None
            return False
        except Exception as exc:  # noqa: BLE001
            self._last_start_reason_code = "action_backend_start_failed"
            self._logger.error(
                "action_backend_start_failed reason_code=%s error=%s",
                self._last_start_reason_code,
                exc,
            )
            self._node = None
            self._action_client = None
            self._action_type = None
            return False

    def shutdown(self) -> None:
        """Zamyka backend i czyści lokalny cache goal/result."""
        self._goal_handles.clear()
        self._result_futures.clear()
        self._feedback_by_goal.clear()

        if self._node is not None:
            destroy = getattr(self._node, "destroy_node", None)
            if callable(destroy):
                destroy()
        self._node = None
        self._action_client = None
        self._action_type = None

    def send_goal(self, goal_payload: dict[str, Any]) -> str | None:
        """Wysyła goal i zwraca goal_id; brak pewności zwraca None."""
        if self._node is None or self._action_client is None or self._action_type is None:
            return None

        if not self._action_client.wait_for_server(timeout_sec=self._config.server_wait_timeout_sec):
            return None

        goal_msg = self._build_goal_message(goal_payload)
        if goal_msg is None:
            return None

        future = self._action_client.send_goal_async(goal_msg, feedback_callback=self._on_feedback)
        if not self._spin_until_complete(future, timeout_sec=self._config.future_wait_timeout_sec):
            return None

        goal_handle = future.result()
        if goal_handle is None or not getattr(goal_handle, "accepted", False):
            return None

        goal_id = self._extract_goal_id(goal_handle)
        if goal_id is None:
            return None

        self._goal_handles[goal_id] = goal_handle
        self._result_futures[goal_id] = goal_handle.get_result_async()
        self._feedback_by_goal.setdefault(goal_id, None)
        return goal_id

    def fetch_progress(self, goal_id: str) -> float | None:
        """Zwraca progress z feedbacku; gdy niepewny -> None."""
        self._spin_once()
        progress = self._feedback_by_goal.get(goal_id)
        if progress is None:
            return None
        if progress < 0.0 or progress > 1.0:
            return None
        return float(progress)

    def fetch_result(self, goal_id: str) -> dict[str, Any] | None:
        """Zwraca wynik akcji po zakończeniu; wcześniej zwraca None."""
        self._spin_once()
        result_future = self._result_futures.get(goal_id)
        if result_future is None or not result_future.done():
            return None

        wrapped = result_future.result()
        if wrapped is None:
            return None

        status = getattr(wrapped, "status", None)
        result_msg = getattr(wrapped, "result", None)
        result_payload = self._serialize_message(result_msg)

        self._goal_handles.pop(goal_id, None)
        self._result_futures.pop(goal_id, None)
        self._feedback_by_goal.pop(goal_id, None)

        return {
            "status": self._status_to_label(status),
            "result": result_payload,
            "goal_id": goal_id,
        }

    def cancel_goal(self, goal_id: str) -> bool:
        """Anuluje goal po stronie serwera Action."""
        goal_handle = self._goal_handles.get(goal_id)
        if goal_handle is None:
            return False

        cancel_future = goal_handle.cancel_goal_async()
        if not self._spin_until_complete(cancel_future, timeout_sec=self._config.future_wait_timeout_sec):
            return False

        cancel_response = cancel_future.result()
        goals_canceling = getattr(cancel_response, "goals_canceling", None)
        is_cancelled = bool(goals_canceling)
        if is_cancelled:
            self._goal_handles.pop(goal_id, None)
            self._result_futures.pop(goal_id, None)
            self._feedback_by_goal.pop(goal_id, None)
        return is_cancelled

    def _load_action_type(self) -> Any:
        action_module = importlib.import_module(self._config.action_type_module)
        action_type = getattr(action_module, self._config.action_type_name, None)
        if action_type is None:
            raise RuntimeError("action_type_not_found")
        return action_type

    def _has_valid_action_contract(self) -> bool:
        action_name = self._config.action_name.strip()
        action_type_module = self._config.action_type_module.strip()
        action_type_name = self._config.action_type_name.strip()
        node_name = self._config.node_name.strip()
        if not all((action_name, action_type_module, action_type_name, node_name)):
            return False
        if self._config.server_wait_timeout_sec <= 0.0:
            return False
        if self._config.future_wait_timeout_sec <= 0.0:
            return False
        return True

    def _build_goal_message(self, goal_payload: dict[str, Any]) -> Any | None:
        goal_msg = self._action_type.Goal()
        mapped_any = False
        for key, value in goal_payload.items():
            if not hasattr(goal_msg, key):
                continue
            try:
                setattr(goal_msg, key, value)
            except Exception:  # noqa: BLE001
                continue
            mapped_any = True

        if mapped_any:
            return goal_msg

        fallback_field = "goal"
        if hasattr(goal_msg, fallback_field):
            try:
                setattr(goal_msg, fallback_field, str(goal_payload.get("goal", "")))
                return goal_msg
            except Exception:  # noqa: BLE001
                return None

        return None

    def _on_feedback(self, feedback_message: Any) -> None:
        goal_id = self._extract_goal_id_from_feedback(feedback_message)
        if goal_id is None:
            return

        feedback = getattr(feedback_message, "feedback", None)
        if feedback is None:
            return

        progress = self._extract_progress(feedback)
        if progress is None:
            return

        self._feedback_by_goal[goal_id] = progress

    def _extract_goal_id(self, goal_handle: Any) -> str | None:
        raw_goal_id = getattr(goal_handle, "goal_id", None)
        if raw_goal_id is None:
            return None

        raw_uuid = getattr(raw_goal_id, "uuid", None)
        if raw_uuid is None:
            return None

        try:
            return uuid.UUID(bytes=bytes(raw_uuid)).hex
        except Exception:  # noqa: BLE001
            return None

    def _extract_goal_id_from_feedback(self, feedback_message: Any) -> str | None:
        goal_id_obj = getattr(feedback_message, "goal_id", None)
        if goal_id_obj is None:
            return None
        raw_uuid = getattr(goal_id_obj, "uuid", None)
        if raw_uuid is None:
            return None
        try:
            return uuid.UUID(bytes=bytes(raw_uuid)).hex
        except Exception:  # noqa: BLE001
            return None

    def _extract_progress(self, feedback_msg: Any) -> float | None:
        for field_name in ("progress", "percentage", "percent_complete"):
            if hasattr(feedback_msg, field_name):
                value = getattr(feedback_msg, field_name)
                try:
                    numeric = float(value)
                except Exception:  # noqa: BLE001
                    return None
                if numeric > 1.0:
                    numeric = numeric / 100.0
                return numeric
        return None

    def _spin_once(self) -> None:
        if self._node is None:
            return
        try:
            self._rclpy.spin_once(self._node, timeout_sec=0.0)
        except Exception:  # noqa: BLE001
            return

    def _spin_until_complete(self, future: Any, *, timeout_sec: float) -> bool:
        if self._node is None:
            return False
        try:
            self._rclpy.spin_until_future_complete(self._node, future, timeout_sec=timeout_sec)
        except Exception:  # noqa: BLE001
            return False
        return bool(future.done())

    # [AI-CHANGE | 2026-04-21 17:42 UTC | v0.178]
    # CO ZMIENIONO: Zastąpiono lokalne, błędne mapowanie statusów ROS2 Action translacją opartą o
    #               `action_msgs/msg/GoalStatus` (kody 0-6) do jednego domenowego słownika UI/StateStore.
    # DLACZEGO: Poprzednio kod 2 był mapowany jako `CANCELED`, co mieszało status transportowy i domenowy
    #           oraz mogło prezentować operatorowi nieprawidłowy stan wykonania.
    # JAK TO DZIAŁA: Funkcja rzutuje wejście do int i pobiera etykietę z tabeli `ACTION_STATUS_FROM_GOAL_STATUS_CODE`;
    #                przy nieparsowalnym kodzie lub braku klucza zwraca bezpieczny fallback `UNKNOWN`.
    # TODO: Dodać telemetryczny licznik nieznanych kodów statusu, aby łatwiej wykrywać niezgodności kontraktu ROS.
    def _status_to_label(self, status: Any) -> str:
        try:
            status_int = int(status)
        except Exception:  # noqa: BLE001
            return ActionStatusLabel.UNKNOWN.value
        return ACTION_STATUS_FROM_GOAL_STATUS_CODE.get(status_int, ActionStatusLabel.UNKNOWN).value

    def _serialize_message(self, msg: Any) -> Any:
        if msg is None:
            return None
        if isinstance(msg, (str, int, float, bool)):
            return msg
        if isinstance(msg, list):
            return [self._serialize_message(item) for item in msg]
        if isinstance(msg, tuple):
            return [self._serialize_message(item) for item in msg]
        if hasattr(msg, "get_fields_and_field_types"):
            serialized: dict[str, Any] = {}
            for field_name in msg.get_fields_and_field_types().keys():
                serialized[field_name] = self._serialize_message(getattr(msg, field_name))
            return serialized
        return str(msg)
