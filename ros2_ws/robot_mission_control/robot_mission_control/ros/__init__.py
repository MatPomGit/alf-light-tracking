"""Warstwa integracji ROS dla Mission Control."""

# [AI-CHANGE | 2026-04-21 10:19 UTC | v0.168]
# CO ZMIENIONO: Dodano brakujący plik `__init__.py` dla podpakietu `robot_mission_control.ros`.
# DLACZEGO: Jawny podpakiet upraszcza importy narzędziowe i eliminuje niejednoznaczność namespace package.
# JAK TO DZIAŁA: Moduł eksportuje stabilne API klienta action, managera noda, klientów usług i subskryberów telemetrycznych.
# TODO: Ograniczyć publiczne API do warstwy facade po wdrożeniu pełnych kontraktów ROS Action.

from robot_mission_control.ros.action_clients import ActionClientBindings, MissionActionClient
from robot_mission_control.ros.node_manager import ReconnectPolicy, RosNodeManager
from robot_mission_control.ros.service_clients import CommandResult, CriticalServiceClients, ServicePolicy
from robot_mission_control.ros.topic_subscribers import TelemetryFieldSpec, TelemetryTopicSubscribers

__all__ = [
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
