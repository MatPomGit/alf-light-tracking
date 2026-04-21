"""Warstwa integracji ROS dla Mission Control."""

# [AI-CHANGE | 2026-04-21 10:19 UTC | v0.168]
# CO ZMIENIONO: Dodano brakujący plik `__init__.py` dla podpakietu `robot_mission_control.ros`.
# DLACZEGO: Jawny podpakiet upraszcza importy narzędziowe i eliminuje niejednoznaczność namespace package.
# JAK TO DZIAŁA: Moduł eksportuje stabilne API klienta action, managera noda, klientów usług i subskryberów telemetrycznych.
# TODO: Ograniczyć publiczne API do warstwy facade po wdrożeniu pełnych kontraktów ROS Action.

# [AI-CHANGE | 2026-04-21 10:35 UTC | v0.169]
# CO ZMIENIONO: Rozszerzono publiczne API o produkcyjny backend `Ros2MissionActionBackend` i jego konfigurację.
# DLACZEGO: Integracja bootstrapu potrzebuje jawnie eksportowanych klas backendu Action.
# JAK TO DZIAŁA: Importy z `robot_mission_control.ros` udostępniają zarówno abstrakcję klienta, jak i transport ROS2.
# TODO: Dodać test stabilności `__all__`, aby zmiany eksportów były wykrywane automatycznie.

from robot_mission_control.ros.action_backend import ActionBackendConfig, Ros2MissionActionBackend
from robot_mission_control.ros.action_clients import ActionClientBindings, MissionActionClient
from robot_mission_control.ros.node_manager import ReconnectPolicy, RosNodeManager
from robot_mission_control.ros.service_clients import CommandResult, CriticalServiceClients, ServicePolicy
from robot_mission_control.ros.topic_subscribers import TelemetryFieldSpec, TelemetryTopicSubscribers

__all__ = [
    "ActionBackendConfig",
    "Ros2MissionActionBackend",
    "ActionClientBindings",
    "MissionActionClient",
    "ReconnectPolicy",
    "RosNodeManager",
    "CommandResult",
    "CriticalServiceClients",
    "ServicePolicy",
    "TelemetryFieldSpec",
    "TelemetryTopicSubscribers",
]
