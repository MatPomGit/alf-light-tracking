"""Main entrypoint for robot mission control desktop app."""

from __future__ import annotations

import importlib
import importlib.util
import sys
from datetime import timedelta
from pathlib import Path
from typing import Optional

# [AI-CHANGE | 2026-04-21 14:43 UTC | v0.175]
# CO ZMIENIONO: Rozszerzono bootstrap ścieżek importu i przeniesiono go przed importy zewnętrzne (PySide6),
#               aby zawsze przygotować poprawne `sys.path` jeszcze przed ładowaniem modułów aplikacji.
# DLACZEGO: W części środowisk uruchomieniowych (np. uruchomienie pliku po absolutnej ścieżce przez IDE)
#           pojedyncze dodanie `parent.parent` nie wystarczało i nadal pojawiał się `ModuleNotFoundError`
#           dla pakietu `robot_mission_control`.
# JAK TO DZIAŁA: Dla trybu skryptowego (`__package__` puste) kod sprawdza kilka katalogów nadrzędnych
#                i dodaje do `sys.path` pierwszy, który realnie zawiera pakiet `robot_mission_control`.
#                Jeżeli żaden kandydat nie pasuje, nic nie dopina (bezpieczny fallback bez fałszywych założeń).
# TODO: Dodać test uruchomieniowy CLI, który waliduje start zarówno przez `python app.py`, jak i `python -m`.
if __package__ in (None, ""):
    app_file = Path(__file__).resolve()
    path_candidates = (app_file.parent.parent, app_file.parent.parent.parent)
    for candidate in path_candidates:
        package_init_file = candidate / "robot_mission_control" / "__init__.py"
        if package_init_file.exists():
            candidate_str = str(candidate)
            if candidate_str not in sys.path:
                sys.path.insert(0, candidate_str)
            break

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


class RosBridgeService:
    """Minimal ROS2 bridge abstraction used by the desktop app."""

    def __init__(self, supervisor: Supervisor) -> None:
        self._supervisor = supervisor
        self._rclpy = None
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
        # CO ZMIENIONO: Dodano pamiętanie ostatniego `reason_code` niedostępności backendu Action.
        # DLACZEGO: Status UI ma pokazywać precyzyjny powód awarii startu zamiast ogólnego fallbacku.
        # JAK TO DZIAŁA: Pole jest aktualizowane podczas walidacji configu i startu backendu.
        # TODO: Zmapować reason_code na opis operatorski w panelu sterowania.
        self._action_backend_unavailable_reason_code: str = "action_backend_unavailable"
        # [AI-CHANGE | 2026-04-23 21:40 UTC | v0.198]
        # CO ZMIENIONO: Dodano pola konfigurowalne dla kontraktu Goal/Feedback/Result klienta Action.
        # DLACZEGO: Mapowania nie powinny być hardkodowane; finalny kontrakt musi być spójny z `action_backend.yaml`.
        # JAK TO DZIAŁA: Bridge trzyma mapę payloadów goal, mapę statusów wyniku i listę pól wyniku do renderu.
        # TODO: Przenieść te ustawienia do dedykowanego obiektu DTO walidowanego schematem.
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

    # [AI-CHANGE | 2026-04-21 15:52 UTC | v0.176]
    # CO ZMIENIONO: Dodano ładowanie konfiguracji backendu ROS2 Action z pliku `config/action_backend.yaml`.
    # DLACZEGO: Zakres komunikacji z robotem ma być konfigurowalny i rozszerzalny bez zmian kodu UI.
    # JAK TO DZIAŁA: Przy poprawnym pliku tworzony jest `ActionBackendConfig`; przy błędzie zwracamy `None`
    #                i cały moduł przechodzi w bezpieczny fallback `BRAK DANYCH` bez ryzyka fałszywych sukcesów.
    # TODO: Dodać walidację schematu YAML (typy/liczby dodatnie) oraz testy kontraktu konfiguracji.
    def _resolve_action_backend_config_path(self) -> Path:
        """Rozwiązuje położenie pliku konfiguracyjnego backendu Action."""
        local_path = Path(__file__).resolve().parent / "config" / "action_backend.yaml"
        if local_path.exists():
            return local_path
        return Path(__file__).resolve().parent.parent / "config" / "action_backend.yaml"

    # [AI-CHANGE | 2026-04-29 13:15 UTC | v0.332]
    # CO ZMIENIONO: Walidacja kontraktu szuka `MissionStep.action` w lokalnym pakiecie `robot_mission_control`.
    # DLACZEGO: Po scaleniu pakietów stara ścieżka `robot_mission_control_interfaces/action` jest niepoprawna;
    #           przy niezgodnej konfiguracji bezpieczniej wyłączyć backend niż uruchomić go na złym typie.
    # JAK TO DZIAŁA: Loader akceptuje tylko moduł `robot_mission_control.action`, odczytuje lokalny plik `.action`,
    #                parsuje pola Goal/Feedback/Result i przy każdym rozjeździe zwraca `False`.
    # TODO: Dodać równoległą walidację przez introspekcję wygenerowanego typu ROS2 w install-space.
    def _resolve_local_action_contract_path(self, config: ActionBackendConfig) -> Path | None:
        """Zwraca ścieżkę do lokalnego pliku `.action` zgodnego z aktualnym configiem."""
        if config.action_type_name.strip() != "MissionStep":
            return None
        if config.action_type_module.strip() != "robot_mission_control.action":
            return None

        workspace_candidate = Path(__file__).resolve().parent.parent / "action" / "MissionStep.action"
        if workspace_candidate.exists():
            return workspace_candidate
        return None

    def _parse_action_contract_fields(self, action_text: str) -> tuple[set[str], set[str], set[str]] | None:
        """Parsuje pola Goal/Feedback/Result z treści pliku `.action`."""
        sections = action_text.split("---")
        if len(sections) != 3:
            return None

        parsed_sections: list[set[str]] = []
        for section in sections:
            section_fields: set[str] = set()
            for raw_line in section.splitlines():
                line = raw_line.strip()
                if not line or line.startswith("#"):
                    continue
                tokens = line.split()
                if len(tokens) < 2:
                    continue
                field_name = tokens[1].strip()
                if field_name:
                    section_fields.add(field_name)
            parsed_sections.append(section_fields)

        return parsed_sections[0], parsed_sections[1], parsed_sections[2]

    def _is_action_contract_runtime_compatible(self, config: ActionBackendConfig) -> bool:
        """Weryfikuje zgodność kontraktu Action z konfiguracją backendu i UI."""
        contract_path = self._resolve_local_action_contract_path(config)
        if contract_path is None:
            return True

        try:
            parsed = self._parse_action_contract_fields(contract_path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            return False

        if parsed is None:
            return False

        goal_fields, feedback_fields, result_fields = parsed
        if "goal" not in goal_fields:
            return False
        if "progress" not in feedback_fields:
            return False

        for payload in self._quick_command_map.values():
            for payload_key in payload.keys():
                if payload_key not in goal_fields:
                    return False

        for field_name in self._action_result_display_fields:
            if field_name not in result_fields:
                return False

        return True

    # [AI-CHANGE | 2026-04-21 18:06 UTC | v0.179]
    # CO ZMIENIONO: Dodano walidację startową konfiguracji backendu Action z precyzyjnym `reason_code`.
    # DLACZEGO: Przy błędnym kontrakcie mamy raportować konkretną przyczynę (`action_contract_missing`),
    #           zamiast ogólnego stanu niedostępności backendu.
    # JAK TO DZIAŁA: Funkcja zapisuje `self._action_backend_unavailable_reason_code` dla każdego błędu walidacji
    #                (brak pliku, błąd YAML, brak kluczy, timeout <= 0), a poprawny config resetuje kod do wartości domyślnej.
    # TODO: Podmienić ręczną walidację na schemat (np. Pydantic), by zwracać szczegóły per pole.
    def _load_action_backend_config(self) -> ActionBackendConfig | None:
        """Wczytuje konfigurację backendu Action lub zwraca None przy niepewności."""
        config_path = self._resolve_action_backend_config_path()
        if not config_path.exists():
            self._action_backend_unavailable_reason_code = "action_contract_missing"
            return None

        try:
            import yaml

            raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            self._action_backend_unavailable_reason_code = "action_contract_missing"
            return None

        if not isinstance(raw, dict):
            self._action_backend_unavailable_reason_code = "action_contract_missing"
            return None

        required_keys = [
            "action_name",
            "action_type_module",
            "action_type_name",
            "node_name",
            "server_wait_timeout_sec",
            "future_wait_timeout_sec",
        ]
        if any(key not in raw for key in required_keys):
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
            # CO ZMIENIONO: Dodano wczytywanie mapowań Goal/Result z `action_backend.yaml`.
            # DLACZEGO: Kontrakt Action ma być konfigurowalny i spójny z runtime bez edycji kodu.
            # JAK TO DZIAŁA: Jeśli YAML zawiera poprawne mapy, nadpisują domyślne ustawienia; przy błędzie
            #                parser pozostawia bezpieczne wartości domyślne, by uniknąć fałszywych danych.
            # TODO: Rozszerzyć walidację o wykrywanie niespójności pól `display_fields` z realnym typem Result.
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
            if not self._is_action_contract_runtime_compatible(config):
                self._action_backend_unavailable_reason_code = "action_contract_missing"
                return None
            self._action_backend_unavailable_reason_code = "action_backend_unavailable"
            return config
        except Exception:  # noqa: BLE001
            self._action_backend_unavailable_reason_code = "action_contract_missing"
            return None

    # [AI-CHANGE | 2026-04-23 21:40 UTC | v0.198]
    # CO ZMIENIONO: Dodano normalizację statusu wyniku akcji i bezpieczny render payloadu Result.
    # DLACZEGO: Chcemy spójnie mapować statusy z backendu zgodnie z configiem i ograniczyć prezentację
    #           do uzgodnionych pól kontraktu, aby nie eksponować niepewnych danych.
    # JAK TO DZIAŁA: `_resolve_result_status_label` korzysta z mapy `result.status_map`, a
    #                `_render_result_payload` renderuje wyłącznie `display_fields`; gdy brak danych, zwraca `BRAK DANYCH`.
    # TODO: Dodać obsługę zagnieżdżonych ścieżek pól result (np. `summary.outcome`) z walidacją typu.
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
            return str(payload)

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

        self._action_backend = Ros2MissionActionBackend(rclpy_module=rclpy_module, config=action_config)
        # [AI-CHANGE | 2026-04-21 18:06 UTC | v0.179]
        # CO ZMIENIONO: Po nieudanym starcie backendu propagujemy dedykowany `reason_code` z warstwy Action.
        # DLACZEGO: Chcemy odróżnić błąd kontraktu od błędu importu typu akcji i innych awarii runtime.
        # JAK TO DZIAŁA: `last_start_reason_code` backendu nadpisuje domyślny kod niedostępności.
        # TODO: Dodać test integracyjny RosBridgeService sprawdzający propagację kodu do StateStore.
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

    # [AI-CHANGE | 2026-04-21 15:52 UTC | v0.176]
    # CO ZMIENIONO: Dodano pełną obsługę sterowania akcją misji (goal/cancel/progress/result)
    #               oraz predefiniowane szybkie komendy operatorskie.
    # DLACZEGO: Moduł kontroli misji wymaga szerszej komunikacji ROS2 i szybkiego wyzwalania najczęstszych funkcji.
    # JAK TO DZIAŁA: Bridge wysyła payload z mapy `quick_command_map`, zapisuje status do StateStore i stale
    #                odpyta progress/result; przy niepewności backendu zapisuje brak danych zamiast błędnej detekcji.
    # TODO: Rozszerzyć mapę komend o parametryzację z poziomu konfiguracji operatora (np. dynamiczne waypointy).
    def _send_action_goal(self, goal_payload: dict[str, object]) -> str | None:
        """Deleguje wysyłkę goal do backendu Action; brak backendu = None."""
        if self._action_backend is None:
            return None
        return self._action_backend.send_goal(goal_payload)

    def _cancel_action_goal_transport(self, goal_id: str) -> bool:
        """Deleguje cancel goal do backendu Action; brak backendu = False."""
        if self._action_backend is None:
            return False
        return self._action_backend.cancel_goal(goal_id)

    def _fetch_action_result(self, goal_id: str) -> dict[str, object] | None:
        """Deleguje pobranie rezultatu goal do backendu Action."""
        if self._action_backend is None:
            return None
        return self._action_backend.fetch_result(goal_id)

    def _fetch_action_progress(self, goal_id: str) -> float | None:
        """Deleguje pobranie feedback progress do backendu Action."""
        if self._action_backend is None:
            return None
        return self._action_backend.fetch_progress(goal_id)

    def submit_action_goal(self) -> None:
        """Wysyła domyślny goal operatora."""
        self.submit_quick_action("start_patrol")

    def submit_quick_action(self, command_key: str) -> None:
        """Wysyła predefiniowaną akcję operatorską do robota."""
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
            # CO ZMIENIONO: Zastąpiono stały kod `action_backend_unavailable` dynamicznym kodem przyczyny.
            # DLACZEGO: Operator potrzebuje konkretnej diagnozy awarii backendu już na etapie wysyłki goal.
            # JAK TO DZIAŁA: Przy braku `goal_id` publikowany jest ostatni znany kod niedostępności backendu.
            # TODO: Uzupełnić mapowanie reason_code -> podpowiedź działań naprawczych w UI.
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
        # CO ZMIENIONO: Użyto wspólnego enum `ActionStatusLabel` przy publikacji statusu do StateStore.
        # DLACZEGO: Ogranicza to ryzyko rozjazdu literałów i utrzymuje jedną semantykę statusów dla UI.
        # JAK TO DZIAŁA: Po zaakceptowaniu wysyłki goal status domenowy przechodzi na `RUNNING`.
        # TODO: Rozszerzyć przepływ o status `ACCEPTED`, gdy backend wystawia etap przed wykonaniem.
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
        """Anuluje aktualnie wykonywany goal."""
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
        """Aktualizuje progress i wynik aktywnego goal."""
        now = utc_now()
        if self._active_goal_id is None:
            return

        goal_id = self._active_goal_id
        progress = self._action_client.get_progress(
            goal_id=goal_id,
            correlation_id=f"action_progress_{now.strftime('%H%M%S')}",
        )
        if progress is not None:
            self._state_store.set_with_inference(
                key=STATE_KEY_ACTION_PROGRESS,
                value=f"{int(progress * 100)}%",
                source="action_client",
                timestamp=now,
            )

        result = self._action_client.get_result(
            goal_id=goal_id,
            correlation_id=f"action_result_{now.strftime('%H%M%S')}",
        )
        if result is None:
            return

        result_status = self._resolve_result_status_label(result.get("status", "UNKNOWN"))
        self._state_store.set_with_inference(key=STATE_KEY_ACTION_STATUS, value=result_status, source="action_client", timestamp=now)
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
    # CO ZMIENIONO: Dodano walidowane wczytywanie konfiguracji aplikacji przed inicjalizacją UI.
    # DLACZEGO: Interwały timerów muszą być sterowane YAML-em i nie mogą pozostać hardcodowane.
    # JAK TO DZIAŁA: `load_config` waliduje `default.yaml`; błąd konfiguracji przerywa start aplikacji.
    # TODO: Obsłużyć parametryzację ścieżki configu przez argument CLI.
    config_path_candidates = [
        Path(__file__).resolve().parents[1] / "config" / "default.yaml",
        Path(__file__).resolve().parents[2] / "config" / "default.yaml",
    ]
    config_path = next((path for path in config_path_candidates if path.exists()), None)
    if config_path is None:
        raise RuntimeError("mission_control_config_missing")
    try:
        runtime_config = load_config(config_path)
    except ConfigValidationError as exc:
        raise RuntimeError(f"mission_control_config_invalid: {exc.message}") from exc

    qt_app = QApplication(argv or sys.argv)
    # [AI-CHANGE | 2026-04-21 15:52 UTC | v0.176]
    # CO ZMIENIONO: Rozszerzono przekazywane callbacki MainWindow o szybkie akcje operatora.
    # DLACZEGO: UI ControlsTab musi wywoływać predefiniowane komendy bez bezpośredniej zależności od bridge.
    # JAK TO DZIAŁA: MainWindow dostaje `submit_quick_action`, który deleguje komendę do RosBridgeService.
    # TODO: Dodać telemetrykę czasu reakcji UI->ROS dla każdego command_key.
    window = MainWindow(
        state_store=bridge.state_store,
        supervisor=supervisor,
        version_metadata=resolve_version_metadata(),
        ui_timer_intervals_ms=runtime_config.ui_timer_intervals_ms,
        # [AI-CHANGE | 2026-04-30 23:20 UTC | v0.201]
        # CO ZMIENIONO: Dodano przekazanie `map_config` do MainWindow podczas inicjalizacji aplikacji.
        # DLACZEGO: Zakładka mapy ma używać limitów z konfiguracji, a nie wartości hardcodowanych.
        # JAK TO DZIAŁA: MainWindow przekazuje słownik do konstruktora `MapTab`, który stosuje walidację/fallback.
        # TODO: Ujednolicić przekazywanie wszystkich sekcji configu przez pojedynczy obiekt RuntimeSettings.
        map_config=runtime_config.map_config,
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
    # CO ZMIENIONO: Polling bridge używa interwału z walidowanej konfiguracji zamiast stałej 1000 ms.
    # DLACZEGO: Kryterium ukończenia wymaga kontroli interwałów przez config bez zmiany kodu.
    # JAK TO DZIAŁA: Timer czyta `bridge_poll_interval_ms` z `runtime_config.ui_timer_intervals_ms`.
    # TODO: Dodać telemetrykę rzeczywistego jittera ticków pollingu bridge.
    poll_timer.setInterval(runtime_config.ui_timer_intervals_ms["bridge_poll_interval_ms"])

    def _tick() -> None:
        bridge._poll_connection()
        reason = None if bridge._initialized else "ros_unavailable"
        bridge._publish_rosbag_snapshot(reason_code=reason)
        # [AI-CHANGE | 2026-04-21 15:52 UTC | v0.176]
        # CO ZMIENIONO: W pętli timera dodano cykliczny polling statusu aktywnej akcji.
        # DLACZEGO: Operator musi otrzymywać progres i wynik akcji w czasie rzeczywistym.
        # JAK TO DZIAŁA: Każdy tick aktualizuje `action_progress` i `action_result`, a po finale czyści `goal_id`.
        # TODO: Rozdzielić częstotliwość pollingu połączenia i akcji dla lepszej responsywności dużych misji.
        bridge.poll_action_status()

    poll_timer.timeout.connect(_tick)
    poll_timer.start()

    exit_code = qt_app.exec()
    supervisor.stop_worker("ros_bridge", utc_now())
    return int(exit_code)


if __name__ == "__main__":
    raise SystemExit(main())
