"""Main entrypoint for robot mission control desktop app."""

from __future__ import annotations

import importlib
import json
import importlib.util
import sys

# [AI-CHANGE | 2026-04-29 13:35 UTC | v0.333]
# CO ZMIENIONO: Oznaczono import PyYAML jako import bez stubów typów.
# DLACZEGO: Bootstrap wczytuje konfigurację YAML poprawnie w runtime, ale pełne `mypy` nie ma lokalnych stubów PyYAML.
# JAK TO DZIAŁA: Ignorowany jest tylko brak informacji typów biblioteki zewnętrznej; błędy walidacji konfiguracji
#                nadal przechodzą przez bezpieczne ścieżki fallbacku aplikacji.
# TODO: Uzupełnić zależności developerskie o `types-PyYAML` albo przenieść parser YAML za typowany adapter.
import yaml  # type: ignore[import-untyped]
from datetime import timedelta
from pathlib import Path
from types import ModuleType
from typing import Optional

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from robot_mission_control.core import (
    ActionStatusLabel,
    STATE_KEY_ACTION_GOAL_ID,
    STATE_KEY_ACTION_PROGRESS,
    STATE_KEY_ACTION_RESULT,
    STATE_KEY_ACTION_STATUS,
    STATE_KEY_BAG_INTEGRITY_STATUS,
    STATE_KEY_DATA_SOURCE_MODE,
    STATE_KEY_DEPENDENCY_STATUS,
    STATE_KEY_PLAYBACK_STATUS,
    STATE_KEY_RECORDING_STATUS,
    STATE_KEY_ROS_CONNECTION_STATUS,
    STATE_KEY_SELECTED_BAG,
    HealthMonitor,
    StateStore,
    Supervisor,
    WorkerModule,
    utc_now,
)
from robot_mission_control.ros.action_backend import ActionBackendConfig, Ros2MissionActionBackend
from robot_mission_control.ros.action_clients import ActionClientBindings, MissionActionClient
from robot_mission_control.ros.dependency_audit_client import DependencyStatusClient
from robot_mission_control.ros.node_manager import ReconnectPolicy, RosNodeManager
from robot_mission_control.core.config_loader import ConfigValidationError, load_config
from robot_mission_control.ui.main_window import MainWindow
from robot_mission_control.rosbag.integrity_checker import IntegrityChecker
from robot_mission_control.rosbag.playback_controller import PlaybackController
from robot_mission_control.rosbag.record_controller import RecordController
from robot_mission_control.versioning import resolve_version_metadata

# [AI-CHANGE | 2026-04-21 03:58 UTC | v0.160]
# CO ZMIENIONO: RosBridgeService zintegrowano z RosNodeManager (init/shutdown/reconnect/heartbeat)
#               i publikacją statusu połączenia `ros_connection_status` do StateStore.
# DLACZEGO: DoD wymaga, by utrata i odzyskanie połączenia były widoczne w UI na podstawie danych ze store.
# JAK TO DZIAŁA: Serwis deleguje zarządzanie cyklem życia ROS do node managera i wykonuje polling, który
#                publikuje heartbeat, wykrywa stale heartbeat oraz uruchamia reconnect z bezpiecznym fallbackiem.
# TODO: Podmienić polling timer na sygnały z warstwy ROS (event-driven), gdy pojawi się stabilny adapter.


class _RclpyRuntime:
    """Adapter runtime rclpy zgodny z kontraktem RosRuntime."""

    def __init__(self, module: object) -> None:
        self._module = module

    def init(self) -> None:
        init_fn = getattr(self._module, "init", None)
        if not callable(init_fn):
            raise RuntimeError("rclpy_init_missing")
        init_fn()

    def shutdown(self) -> None:
        shutdown_fn = getattr(self._module, "shutdown", None)
        if not callable(shutdown_fn):
            raise RuntimeError("rclpy_shutdown_missing")
        shutdown_fn()


# [AI-CHANGE | 2026-04-21 10:35 UTC | v0.169]
# CO ZMIENIONO: Zastąpiono lokalny transport unavailable pełnym backendem ROS2 Action
#               z dynamicznym ładowaniem typu akcji i bezpiecznym fallbackiem.
# DLACZEGO: Moduł operatorski ma korzystać z realnego backendu Action, a nie z warstwy bez transportu.
# JAK TO DZIAŁA: `Ros2MissionActionBackend` obsługuje send/progress/result/cancel przez rclpy ActionClient;
#                gdy kontrakt lub serwer są niedostępne, metody zwracają None/False (UNAVAILABLE).
# TODO: Dodać walidację payloadu goal względem jawnego schematu kontraktu Action.


class RosBridgeService:
    """Minimal ROS2 bridge abstraction used by the desktop app."""

    def __init__(self, supervisor: Supervisor) -> None:
        self._supervisor = supervisor
        # [AI-CHANGE | 2026-04-29 13:35 UTC | v0.333]
        # CO ZMIENIONO: Dodano jawny typ opcjonalnego modułu `rclpy`.
        # DLACZEGO: `rclpy` jest ładowany dynamicznie dopiero po audycie dostępności ROS2; bez adnotacji `mypy`
        #           traktował pole jako stałe `None` i odrzucał późniejsze przypisanie modułu.
        # JAK TO DZIAŁA: Pole przyjmuje `None` przed inicjalizacją i `ModuleType` po udanym imporcie; brak importu
        #                nadal ustawia stany na `UNAVAILABLE`, zgodnie z bezpiecznym fallbackiem.
        # TODO: Wydzielić dynamiczne ładowanie ROS2 do osobnego adaptera z protokołem metod `init`/`shutdown`.
        self._rclpy: ModuleType | None = None
        self._initialized = False
        self._state_store = StateStore()
        self._channel_name = "ros_bridge_channel"
        config_path = self._resolve_dependency_catalog_path()
        self._dependency_client = DependencyStatusClient(
            request_fn=self._request_dependency_status,
            dependencies_config_path=config_path,
        )
        self._integrity_checker = IntegrityChecker()
        self._playback_controller = PlaybackController(integrity_checker=self._integrity_checker)
        self._record_controller = RecordController()
        self._session_id = f"ros-bridge-{utc_now().strftime('%Y%m%d%H%M%S')}"
        self._node_manager: RosNodeManager | None = None
        self._action_backend: Ros2MissionActionBackend | None = None
        # [AI-CHANGE | 2026-04-21 18:06 UTC | v0.179]
        # CO ZMIENIONO: Dodano bufor ostatniego `reason_code` niedostępności backendu Action.
        # DLACZEGO: Potrzebujemy publikować dokładny powód awarii, a nie wyłącznie kod ogólny.
        # JAK TO DZIAŁA: Pole jest aktualizowane podczas walidacji configu oraz `start()` backendu.
        # TODO: Wystawić kod przyczyny także w dedykowanym panelu diagnostycznym UI.
        self._action_backend_unavailable_reason_code: str = "action_backend_unavailable"
        # [AI-CHANGE | 2026-04-23 21:40 UTC | v0.198]
        # CO ZMIENIONO: Dodano pola na finalne mapowania Goal/Feedback/Result ładowane z konfiguracji.
        # DLACZEGO: Kontrakt Action ma być sterowany przez `action_backend.yaml`, a nie literały w kodzie.
        # JAK TO DZIAŁA: Bridge przechowuje mapę szybkich komend, mapę statusów result i listę pól do renderu.
        # TODO: Wynieść te parametry do oddzielnego modelu konfiguracji z walidacją schematu.
        self._quick_command_map: dict[str, dict[str, object]] = {
            "start_patrol": {"goal": "start_patrol"},
            "return_to_base": {"goal": "return_to_base"},
            "pause_mission": {"goal": "pause_mission"},
            "resume_mission": {"goal": "resume_mission"},
        }
        self._action_result_status_map: dict[str, str] = {}
        self._action_result_display_fields: list[str] = []
        self._action_client = MissionActionClient(
            session_id=self._session_id,
            bindings=ActionClientBindings(
                send_goal=self._send_action_goal,
                cancel_goal=self._cancel_action_goal_transport,
                fetch_result=self._fetch_action_result,
                fetch_progress=self._fetch_action_progress,
            ),
        )
        self._active_goal_id: str | None = None

    def _resolve_dependency_catalog_path(self) -> Path:
        """Rozwiązuje położenie katalogu config dla obu ścieżek uruchamiania (moduł/pakiet)."""
        local_path = Path(__file__).resolve().parent / "config" / "dependency_catalog.yaml"
        if local_path.exists():
            return local_path
        return Path(__file__).resolve().parent.parent / "config" / "dependency_catalog.yaml"

    # [AI-CHANGE | 2026-04-21 10:35 UTC | v0.169]
    # CO ZMIENIONO: Dodano odczyt jawnej konfiguracji backendu Action z pliku YAML.
    # DLACZEGO: Typ i endpoint akcji nie mogą być ukryte w kodzie; muszą być konfigurowalne pod środowisko robota.
    # JAK TO DZIAŁA: Bridge rozwiązuje ścieżkę pliku, waliduje wymagane pola i tworzy `ActionBackendConfig`.
    # TODO: Dodać formalną walidację typów/liczb dodatnich przez dedykowany schemat (np. pydantic/cerberus).
    def _resolve_action_backend_config_path(self) -> Path:
        """Rozwiązuje położenie pliku konfiguracyjnego backendu Action."""
        local_path = Path(__file__).resolve().parent / "config" / "action_backend.yaml"
        if local_path.exists():
            return local_path
        return Path(__file__).resolve().parent.parent / "config" / "action_backend.yaml"

    # [AI-CHANGE | 2026-04-21 18:06 UTC | v0.179]
    # CO ZMIENIONO: Dodano walidację konfiguracji backendu Action z raportowaniem precyzyjnego `reason_code`.
    # DLACZEGO: Inicjalizacja ma rozróżniać błąd kontraktu (`action_contract_missing`) od innych awarii backendu.
    # JAK TO DZIAŁA: Metoda ustawia `self._action_backend_unavailable_reason_code` dla każdej ścieżki błędu
    #                i zwraca `None`, aby utrzymać bezpieczny fallback bez pozornego sukcesu startu.
    # TODO: Przenieść walidację do wspólnej funkcji współdzielonej przez wszystkie entrypointy aplikacji.
    def _load_action_backend_config(self) -> ActionBackendConfig | None:
        """Wczytuje konfigurację Action; przy błędzie zwraca None (bezpieczny fallback)."""
        config_path = self._resolve_action_backend_config_path()
        if not config_path.exists():
            self._action_backend_unavailable_reason_code = "action_contract_missing"
            return None

        try:
            raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            self._action_backend_unavailable_reason_code = "action_contract_missing"
            return None

        if not isinstance(raw, dict):
            self._action_backend_unavailable_reason_code = "action_contract_missing"
            return None

        required = [
            "action_name",
            "action_type_module",
            "action_type_name",
            "node_name",
            "server_wait_timeout_sec",
            "future_wait_timeout_sec",
        ]
        if any(key not in raw for key in required):
            self._action_backend_unavailable_reason_code = "action_contract_missing"
            return None

        try:
            config = ActionBackendConfig(
                action_name=str(raw["action_name"]),
                action_type_module=str(raw["action_type_module"]),
                action_type_name=str(raw["action_type_name"]),
                node_name=str(raw["node_name"]),
                server_wait_timeout_sec=float(raw["server_wait_timeout_sec"]),
                future_wait_timeout_sec=float(raw["future_wait_timeout_sec"]),
            )
            if (
                not config.action_name.strip()
                or not config.action_type_module.strip()
                or not config.action_type_name.strip()
                or not config.node_name.strip()
                or config.server_wait_timeout_sec <= 0.0
                or config.future_wait_timeout_sec <= 0.0
            ):
                self._action_backend_unavailable_reason_code = "action_contract_missing"
                return None
            # [AI-CHANGE | 2026-04-23 21:40 UTC | v0.198]
            # CO ZMIENIONO: Dodano odczyt mapowań Goal/Result z `action_backend.yaml`.
            # DLACZEGO: Ujednolica to bootstrap runtime z finalnym kontraktem Action.
            # JAK TO DZIAŁA: Gdy YAML zawiera poprawne sekcje, aktualizowane są mapy komend/statusów
            #                oraz lista pól result; przy błędnych strukturach zostają bezpieczne defaulty.
            # TODO: Dopiąć testy jednostkowe parsera konfiguracji dla uszkodzonych struktur YAML.
            goal_payload_map = raw.get("goal_payload_map")
            if isinstance(goal_payload_map, dict):
                parsed_map: dict[str, dict[str, object]] = {}
                for command_key, payload in goal_payload_map.items():
                    if isinstance(command_key, str) and isinstance(payload, dict) and payload:
                        parsed_map[command_key] = dict(payload)
                if parsed_map:
                    self._quick_command_map = parsed_map

            result_cfg = raw.get("result")
            if isinstance(result_cfg, dict):
                status_map_cfg = result_cfg.get("status_map")
                parsed_status_map: dict[str, str] = {}
                if isinstance(status_map_cfg, dict):
                    for status_key, status_label in status_map_cfg.items():
                        if isinstance(status_key, str) and isinstance(status_label, str):
                            parsed_status_map[status_key.upper()] = status_label.upper()
                self._action_result_status_map = parsed_status_map

                display_fields_cfg = result_cfg.get("display_fields")
                parsed_display_fields: list[str] = []
                if isinstance(display_fields_cfg, list):
                    for field_name in display_fields_cfg:
                        if isinstance(field_name, str) and field_name.strip():
                            parsed_display_fields.append(field_name.strip())
                self._action_result_display_fields = parsed_display_fields
            self._action_backend_unavailable_reason_code = "action_backend_unavailable"
            return config
        except Exception:  # noqa: BLE001
            self._action_backend_unavailable_reason_code = "action_contract_missing"
            return None

    # [AI-CHANGE | 2026-04-23 21:40 UTC | v0.198]
    # CO ZMIENIONO: Dodano helpery normalizujące status wyniku i renderujące wynik wg finalnego kontraktu.
    # DLACZEGO: Etykiety i payload Result muszą być deterministyczne oraz zgodne z mapowaniem w YAML.
    # JAK TO DZIAŁA: Status przechodzi przez `result.status_map`, a UI dostaje tylko pola z `display_fields`;
    #                przy niepewnym formacie zwracamy `BRAK DANYCH`.
    # TODO: Rozszerzyć render o politykę maskowania pól wrażliwych i dużych payloadów diagnostycznych.
    def _resolve_result_status_label(self, status_value: object) -> str:
        raw_status = str(status_value).upper()
        mapped_status = self._action_result_status_map.get(raw_status)
        if mapped_status is not None:
            return mapped_status
        return raw_status

    def _render_result_payload(self, payload: object) -> str:
        if not isinstance(payload, dict):
            return "BRAK DANYCH"

        if not self._action_result_display_fields:
            return json.dumps(payload, ensure_ascii=False)

        rendered_fields: list[str] = []
        for field_name in self._action_result_display_fields:
            if field_name in payload:
                rendered_fields.append(f"{field_name}={payload[field_name]}")
        if not rendered_fields:
            return "BRAK DANYCH"
        return ", ".join(rendered_fields)

    def init(self) -> None:
        """Prepare ROS bindings without crashing GUI boot."""
        if importlib.util.find_spec("rclpy") is None:
            self._initialized = False
            self._state_store.set_with_inference(
                key=STATE_KEY_DATA_SOURCE_MODE,
                value=None,
                source="ros_bridge",
                timestamp=utc_now(),
                reason_code="ros_unavailable",
            )
            self._state_store.set_with_inference(
                key=STATE_KEY_ROS_CONNECTION_STATUS,
                value=None,
                source="node_manager",
                timestamp=utc_now(),
                reason_code="ros_unavailable",
            )
            return

        rclpy_module = importlib.import_module("rclpy")
        self._rclpy = rclpy_module
        self._node_manager = RosNodeManager(
            runtime=_RclpyRuntime(rclpy_module),
            session_id=self._session_id,
            reconnect_policy=ReconnectPolicy(max_attempts=3, base_delay_seconds=0.5, max_delay_seconds=2.0),
            state_store=self._state_store,
        )
        self._initialized = self._node_manager.init_node(correlation_id="bridge_init")
        if not self._initialized:
            return

        action_config = self._load_action_backend_config()
        if action_config is None:
            self._action_backend = None
            return

        self._action_backend = Ros2MissionActionBackend(
            rclpy_module=rclpy_module,
            config=action_config,
        )
        # [AI-CHANGE | 2026-04-21 18:06 UTC | v0.179]
        # CO ZMIENIONO: Dodano propagację `last_start_reason_code` po nieudanym starcie backendu Action.
        # DLACZEGO: Inicjalizacja mostu ma raportować specyficzny powód niedostępności backendu.
        # JAK TO DZIAŁA: Przy `start()==False` kod przyczyny przechodzi do pola serwisu i jest używany dalej.
        # TODO: Pokryć tę ścieżkę testem end-to-end RosBridgeService z atrapą backendu.
        if not self._action_backend.start():
            self._action_backend_unavailable_reason_code = (
                self._action_backend.last_start_reason_code or "action_backend_unavailable"
            )
            self._action_backend = None

    def start(self) -> None:
        """Start ROS worker and publish safe source status."""
        if not self._initialized or self._node_manager is None:
            self._state_store.set_with_inference(
                key=STATE_KEY_DATA_SOURCE_MODE,
                value=None,
                source="ros_bridge",
                timestamp=utc_now(),
                reason_code="ros_unavailable",
            )
            self._publish_rosbag_snapshot(reason_code="ros_unavailable")
            self._publish_dependency_report()
            return

        self._poll_connection()
        self._publish_rosbag_snapshot(reason_code="waiting_for_topics")
        self._publish_dependency_report()

    def stop(self) -> None:
        """Safely shutdown ROS2 if it was initialized."""
        if self._action_backend is not None:
            self._action_backend.shutdown()
            self._action_backend = None

        if self._node_manager is not None:
            self._node_manager.shutdown_node(correlation_id="bridge_stop")

        self._state_store.set_with_inference(
            key=STATE_KEY_DATA_SOURCE_MODE,
            value=None,
            source="ros_bridge",
            timestamp=utc_now(),
            reason_code="app_shutdown",
        )
        self._publish_rosbag_snapshot(reason_code="app_shutdown")

    def _poll_connection(self) -> None:
        """Aktualizuje heartbeat i reconnect, publikując bezpieczny status połączenia."""
        if self._node_manager is None:
            self._state_store.set_with_inference(
                key=STATE_KEY_ROS_CONNECTION_STATUS,
                value=None,
                source="node_manager",
                timestamp=utc_now(),
                reason_code="node_manager_unavailable",
            )
            return

        now = utc_now()
        is_connected = self._node_manager.ensure_connected(correlation_id="bridge_poll_connect")
        if not is_connected:
            self._initialized = False
            self._state_store.set_with_inference(
                key=STATE_KEY_DATA_SOURCE_MODE,
                value=None,
                source="ros_bridge",
                timestamp=now,
                reason_code="reconnect_failed",
            )
            return

        self._initialized = True
        heartbeat = self._node_manager.heartbeat(correlation_id="bridge_poll_heartbeat")
        if heartbeat is None:
            self._initialized = False
            return

        if self._node_manager.is_heartbeat_stale(now=now, max_age=timedelta(seconds=5)):
            self._initialized = False
            return

        self._supervisor.heartbeat_channel(self._channel_name, heartbeat)

    def _send_action_goal(self, goal_payload: dict[str, object]) -> str | None:
        """Deleguje wysyłkę goal do backendu Action; brak backendu => None."""
        if self._action_backend is None:
            return None
        return self._action_backend.send_goal(goal_payload)

    def _cancel_action_goal_transport(self, goal_id: str) -> bool:
        """Deleguje cancel goal do backendu Action; brak backendu => False."""
        if self._action_backend is None:
            return False
        return self._action_backend.cancel_goal(goal_id)

    def _fetch_action_result(self, goal_id: str) -> dict[str, object] | None:
        """Deleguje pobranie result do backendu Action; brak backendu => None."""
        if self._action_backend is None:
            return None
        return self._action_backend.fetch_result(goal_id)

    def _fetch_action_progress(self, goal_id: str) -> float | None:
        """Deleguje pobranie feedback progress do backendu Action; brak backendu => None."""
        if self._action_backend is None:
            return None
        return self._action_backend.fetch_progress(goal_id)

    # [AI-CHANGE | 2026-04-21 16:02 UTC | v0.177]
    # CO ZMIENIONO: Ujednolicono ścieżkę wykonania akcji w bootstrapie z nowym UI Controls:
    #               dodano `submit_quick_action` i mapowanie szybkich komend operatorskich.
    # DLACZEGO: Runtime aplikacji działa przez `app/bootstrap.py`, więc brak tej zmiany powodował,
    #           że nowe przyciski szybkich akcji były wyświetlane, ale nie wykonywały komend ROS2.
    # JAK TO DZIAŁA: `submit_action_goal` deleguje do domyślnej szybkiej komendy, a `submit_quick_action`
    #                mapuje `command_key` na payload goal; przy nieznanej komendzie publikujemy `None`.
    # TODO: Przenieść mapę komend do pliku konfiguracyjnego, aby operator mógł ją rozszerzać bez zmian kodu.
    def submit_action_goal(self) -> None:
        """Wysyła domyślny goal operatora."""
        self.submit_quick_action("start_patrol")

    def submit_quick_action(self, command_key: str) -> None:
        """Wysyła predefiniowaną akcję operatorską i publikuje stan początkowy."""
        now = utc_now()
        if self._active_goal_id is not None:
            self._state_store.set_with_inference(
                key=STATE_KEY_ACTION_STATUS,
                value=None,
                source="action_client",
                timestamp=now,
                reason_code="goal_already_running",
            )
            return

        goal_payload = self._quick_command_map.get(command_key)
        if goal_payload is None:
            self._state_store.set_with_inference(
                key=STATE_KEY_ACTION_STATUS,
                value=None,
                source="action_client",
                timestamp=now,
                reason_code="unknown_quick_command",
            )
            return

        goal_id = self._action_client.send_goal(
            goal_payload=goal_payload,
            correlation_id=f"action_send_{command_key}_{now.strftime('%H%M%S')}",
        )
        if goal_id is None:
            # [AI-CHANGE | 2026-04-21 18:06 UTC | v0.179]
            # CO ZMIENIONO: Publikacja błędu wysyłki goal korzysta z konkretnego `reason_code` backendu.
            # DLACZEGO: Ujednoznacznia diagnostykę i eliminuje mylący kod ogólny w scenariuszach konfiguracji/importu.
            # JAK TO DZIAŁA: Zamiast stałej wartości zapisywany jest `self._action_backend_unavailable_reason_code`.
            # TODO: Dodać mapowanie tych kodów do jednoznacznych komunikatów operatorskich.
            self._state_store.set_with_inference(
                key=STATE_KEY_ACTION_STATUS,
                value=None,
                source="action_client",
                timestamp=now,
                reason_code=self._action_backend_unavailable_reason_code,
            )
            return

        self._active_goal_id = goal_id
        self._state_store.set_with_inference(key=STATE_KEY_ACTION_GOAL_ID, value=goal_id, source="action_client", timestamp=now)
        # [AI-CHANGE | 2026-04-21 17:42 UTC | v0.178]
        # CO ZMIENIONO: Publikację statusu akcji przy starcie goala przełączono na wspólny enum domenowy.
        # DLACZEGO: Ta sama semantyka statusów musi obowiązywać równolegle w UI i StateStore.
        # JAK TO DZIAŁA: Status aktywnego goala jest zapisywany jako `ActionStatusLabel.RUNNING.value`.
        # TODO: Rozszerzyć backend o etap ACCEPTED i publikować go przed właściwym wykonaniem.
        self._state_store.set_with_inference(
            key=STATE_KEY_ACTION_STATUS,
            value=ActionStatusLabel.RUNNING.value,
            source="action_client",
            timestamp=now,
        )
        self._state_store.set_with_inference(key=STATE_KEY_ACTION_PROGRESS, value="0%", source="action_client", timestamp=now)
        self._state_store.set_with_inference(
            key=STATE_KEY_ACTION_RESULT,
            value=f"WYSŁANO KOMENDĘ: {command_key}",
            source="action_client",
            timestamp=now,
        )

    def cancel_action_goal(self) -> None:
        """Anuluje aktywny goal i publikuje status anulowania."""
        now = utc_now()
        if self._active_goal_id is None:
            self._state_store.set_with_inference(
                key=STATE_KEY_ACTION_STATUS,
                value=None,
                source="action_client",
                timestamp=now,
                reason_code="no_active_goal",
            )
            return

        is_cancelled = self._action_client.cancel_goal(
            goal_id=self._active_goal_id,
            correlation_id=f"action_cancel_{now.strftime('%H%M%S')}",
        )
        self._state_store.set_with_inference(
            key=STATE_KEY_ACTION_STATUS,
            value=ActionStatusLabel.CANCEL_REQUESTED.value if is_cancelled else None,
            source="action_client",
            timestamp=now,
            reason_code=None if is_cancelled else "cancel_failed",
        )

    def poll_action_status(self) -> None:
        """Polluje progress i wynik aktywnego goala, stosując bezpieczne fallbacki."""
        now = utc_now()
        if self._active_goal_id is None:
            return

        goal_id = self._active_goal_id
        progress = self._action_client.get_progress(
            goal_id=goal_id,
            correlation_id=f"action_progress_{now.strftime('%H%M%S')}",
        )
        if progress is not None:
            progress_label = f"{int(progress * 100)}%"
            self._state_store.set_with_inference(
                key=STATE_KEY_ACTION_PROGRESS,
                value=progress_label,
                source="action_client",
                timestamp=now,
            )

        result = self._action_client.get_result(
            goal_id=goal_id,
            correlation_id=f"action_result_{now.strftime('%H%M%S')}",
        )
        if result is None:
            return

        status = self._resolve_result_status_label(result.get("status", "UNKNOWN"))
        self._state_store.set_with_inference(key=STATE_KEY_ACTION_STATUS, value=status, source="action_client", timestamp=now)
        self._state_store.set_with_inference(
            key=STATE_KEY_ACTION_RESULT,
            value=self._render_result_payload(result.get("result")),
            source="action_client",
            timestamp=now,
        )
        self._state_store.set_with_inference(
            key=STATE_KEY_ACTION_GOAL_ID,
            value=None,
            source="action_client",
            timestamp=now,
            reason_code="goal_finished",
        )
        self._active_goal_id = None

    def _request_dependency_status(self, payload: dict[str, object]) -> dict[str, object] | None:
        """Placeholder contract call returning conservative UNKNOWN when transport is unavailable."""
        dependencies = payload.get("dependencies")
        if not isinstance(dependencies, list):
            return None

        now_iso = utc_now().isoformat()
        return {
            "source": "system/dependency_status",
            "generated_at_utc": now_iso,
            "dependencies": [
                {
                    "name": str(item.get("name")),
                    "status": "UNKNOWN",
                    "detected_version": None,
                    "timestamp_utc": now_iso,
                    "source": "system/dependency_status",
                }
                for item in dependencies
                if isinstance(item, dict)
            ],
        }

    def _publish_rosbag_snapshot(self, *, reason_code: str | None = None) -> None:
        now = utc_now()
        playback_state = self._playback_controller.state
        selected_bag = playback_state.bag_path if playback_state.bag_path else None

        playback_status = "PLAYING" if playback_state.is_playing else "STOPPED"
        if playback_state.is_paused:
            playback_status = "PAUSED"

        bag_integrity = None
        if selected_bag:
            bag_integrity = self._integrity_checker.check(selected_bag).status

        self._state_store.set_with_inference(
            key=STATE_KEY_DATA_SOURCE_MODE,
            value=self._playback_controller.source_mode.value if self._initialized else None,
            source="ros_bridge",
            timestamp=now,
            reason_code=reason_code,
        )
        self._state_store.set_with_inference(
            key=STATE_KEY_RECORDING_STATUS,
            value=self._record_controller.status.value if self._initialized else None,
            source="ros_bridge",
            timestamp=now,
            reason_code=reason_code,
        )
        self._state_store.set_with_inference(
            key=STATE_KEY_PLAYBACK_STATUS,
            value=playback_status if self._initialized else None,
            source="ros_bridge",
            timestamp=now,
            reason_code=reason_code,
        )
        self._state_store.set_with_inference(
            key=STATE_KEY_SELECTED_BAG,
            value=selected_bag if self._initialized else None,
            source="ros_bridge",
            timestamp=now,
            reason_code=reason_code,
        )
        # Zasada bezpieczeństwa: przy niepewnej integralności publikujemy None zamiast ryzyka fałszywego "OK".
        self._state_store.set_with_inference(
            key=STATE_KEY_BAG_INTEGRITY_STATUS,
            value=bag_integrity if self._initialized else None,
            source="ros_bridge",
            timestamp=now,
            reason_code=reason_code if bag_integrity is None else None,
        )

    def _publish_dependency_report(self) -> None:
        report = self._dependency_client.fetch_report()
        # Zasada bezpieczeństwa: bez pełnego raportu wolimy brak danych niż potencjalnie fałszywe OK.
        self._state_store.set_with_inference(
            key=STATE_KEY_DEPENDENCY_STATUS,
            value=report if report.items else None,
            source=report.source,
            timestamp=report.generated_at_utc,
            reason_code="dependency_report_empty" if not report.items else None,
        )

    @property
    def state_store(self) -> StateStore:
        """Expose central state store for UI."""
        return self._state_store


def _install_global_excepthook(supervisor: Supervisor) -> None:
    """Install global boundary for unhandled UI/runtime exceptions."""

    def _hook(exc_type, exc, tb):  # noqa: ANN001
        _ = exc_type, tb
        supervisor.mark_panel_unavailable(panel_name="global_ui", exc=exc, now=utc_now())

    sys.excepthook = _hook


def main(argv: Optional[list[str]] = None) -> int:
    """Application entrypoint."""
    monitor = HealthMonitor(
        heartbeat_timeout=timedelta(seconds=10),
        base_backoff=timedelta(seconds=1),
        max_backoff=timedelta(seconds=20),
        breaker_threshold=3,
        breaker_cooldown=timedelta(seconds=30),
    )
    supervisor = Supervisor(health_monitor=monitor)
    _install_global_excepthook(supervisor)

    bridge = RosBridgeService(supervisor=supervisor)
    supervisor.register_channel("ros_bridge_channel")
    supervisor.register_worker(
        WorkerModule(
            name="ros_bridge",
            init_fn=bridge.init,
            start_fn=bridge.start,
            stop_fn=bridge.stop,
        )
    )

    now = utc_now()
    supervisor.init_worker("ros_bridge", now)
    supervisor.start_worker("ros_bridge", now)

    # [AI-CHANGE | 2026-04-23 18:29 UTC | v0.195]
    # CO ZMIENIONO: Dodano ładowanie i walidację konfiguracji runtime przed startem UI.
    # DLACZEGO: Interwały timerów mają być sterowane przez plik konfiguracyjny, a błędny config
    #           powinien zatrzymać start zamiast uruchamiać aplikację z niepewnymi wartościami.
    # JAK TO DZIAŁA: `load_config` waliduje `default.yaml`; przy błędzie rzucamy RuntimeError,
    #                co wymusza bezpieczne przerwanie startu aplikacji.
    # TODO: Dodać obsługę argumentu CLI `--config`, aby jawnie wskazywać plik konfiguracji.
    config_path_candidates = [
        Path(__file__).resolve().parents[2] / "config" / "default.yaml",
        Path(__file__).resolve().parents[3] / "config" / "default.yaml",
    ]
    config_path = next((path for path in config_path_candidates if path.exists()), None)
    if config_path is None:
        raise RuntimeError("mission_control_config_missing")
    try:
        runtime_config = load_config(config_path)
    except ConfigValidationError as exc:
        raise RuntimeError(f"mission_control_config_invalid: {exc.message}") from exc

    qt_app = QApplication(argv or sys.argv)
    # [AI-CHANGE | 2026-04-21 16:02 UTC | v0.177]
    # CO ZMIENIONO: Dodano przekazanie callbacku `submit_quick_action` do MainWindow.
    # DLACZEGO: Bez tego nowe przyciski z ControlsTab trafiały w no-op i nie wysyłały komend do robota.
    # JAK TO DZIAŁA: MainWindow deleguje command_key do bridge, który publikuje stan i wykonuje wywołanie ROS2.
    # TODO: Dodać test integracyjny UI->bridge dla każdego wspieranego `command_key`.
    window = MainWindow(
        state_store=bridge.state_store,
        supervisor=supervisor,
        version_metadata=resolve_version_metadata(),
        ui_timer_intervals_ms=runtime_config.ui_timer_intervals_ms,
        submit_action_goal=bridge.submit_action_goal,
        cancel_action_goal=bridge.cancel_action_goal,
        submit_quick_action=bridge.submit_quick_action,
    )
    window.show()
    # [AI-CHANGE | 2026-04-21 03:58 UTC | v0.160]
    # CO ZMIENIONO: Dodano cykliczny polling połączenia ROS w pętli UI (QTimer co 1 s).
    # DLACZEGO: Utrata i odzyskanie połączenia mają być widoczne w runtime, nie tylko przy starcie aplikacji.
    # JAK TO DZIAŁA: Timer uruchamia `_poll_connection` i odświeża snapshot rosbag; przy utracie połączenia
    #                store dostaje wartości bezpieczne (`None`), a po reconnect wraca status `CONNECTED`.
    # TODO: Dodać adaptacyjny interwał timera zależny od stanu (krótszy podczas reconnect, dłuższy gdy stabilnie).
    poll_timer = QTimer()
    # [AI-CHANGE | 2026-04-23 18:29 UTC | v0.195]
    # CO ZMIENIONO: Interwał pollingu bridge został podpięty do walidowanej konfiguracji.
    # DLACZEGO: Usuwamy hardcode 1000 ms i umożliwiamy zmianę częstotliwości reconnect/pollingu bez deployu kodu.
    # JAK TO DZIAŁA: Timer korzysta z klucza `bridge_poll_interval_ms` zwalidowanego przez `config_loader`.
    # TODO: Rozdzielić interwał pollingu łączności i interwał pollingu statusu akcji.
    poll_timer.setInterval(runtime_config.ui_timer_intervals_ms["bridge_poll_interval_ms"])

    def _tick() -> None:
        bridge._poll_connection()
        reason = None if bridge._initialized else "ros_unavailable"
        bridge._publish_rosbag_snapshot(reason_code=reason)
        bridge.poll_action_status()

    poll_timer.timeout.connect(_tick)
    poll_timer.start()

    exit_code = qt_app.exec()
    supervisor.stop_worker("ros_bridge", utc_now())
    return int(exit_code)


if __name__ == "__main__":
    raise SystemExit(main())
