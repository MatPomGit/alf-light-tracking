"""Core domain primitives for robot mission control."""

# [AI-CHANGE | 2026-04-21 09:30 UTC | v0.166]
# CO ZMIENIONO: Rozszerzono publiczne API `core` o nowe moduły backlogu (config/event/log/error/models)
#               przy zachowaniu kompatybilności dotychczasowych importów Supervisor.
# DLACZEGO: Warstwy aplikacji i integracje zewnętrzne potrzebują jednego miejsca importu stabilnych kontraktów.
# JAK TO DZIAŁA: `__all__` publikuje zarówno istniejące prymitywy monitoringu, jak i nowe klasy/funkcje core.
# TODO: Dodać test jednostkowy, który waliduje kompletność eksportów względem dokumentacji architektury.
from robot_mission_control.core.action_status import ACTION_STATUS_FROM_GOAL_STATUS_CODE, ActionStatusLabel
from robot_mission_control.core.config_loader import ConfigValidationError, load_config
from robot_mission_control.core.error_boundary import (
    ErrorBoundary as UiErrorBoundary,
)
from robot_mission_control.core.error_boundary import GuardedExecutionResult
from robot_mission_control.core.error_codes import DEFAULT_ERROR_MESSAGES, ErrorCode as CoreErrorCode
from robot_mission_control.core.event_bus import EventBus, EventBusValidationError
from robot_mission_control.core.health_monitor import (
    HealthMonitor,
    IncidentRecord,
    WorkerLifecycleState,
)
from robot_mission_control.core.logger import MissionControlFormatter, get_logger
from robot_mission_control.core.models import (
    ErrorDescriptor,
    EventCategory,
    MissionControlConfig,
    MissionEvent,
)
from robot_mission_control.core.state_store import (
    DataQuality,
    GLOBAL_STATE_KEYS,
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
    StateStore,
    StateValue,
    infer_quality,
    quality_for_corrupted,
    quality_for_missing,
    quality_for_stale,
    utc_now,
)
from robot_mission_control.core.supervisor import ErrorBoundary, ErrorCode, Supervisor, WorkerModule

__all__ = [
    "ActionStatusLabel",
    "ACTION_STATUS_FROM_GOAL_STATUS_CODE",
    "DataQuality",
    "GLOBAL_STATE_KEYS",
    "STATE_KEY_ACTION_GOAL_ID",
    "STATE_KEY_ACTION_PROGRESS",
    "STATE_KEY_ACTION_RESULT",
    "STATE_KEY_ACTION_STATUS",
    "STATE_KEY_BAG_INTEGRITY_STATUS",
    "STATE_KEY_DATA_SOURCE_MODE",
    "STATE_KEY_DEPENDENCY_STATUS",
    "STATE_KEY_PLAYBACK_STATUS",
    "STATE_KEY_RECORDING_STATUS",
    "STATE_KEY_ROS_CONNECTION_STATUS",
    "STATE_KEY_SELECTED_BAG",
    "StateStore",
    "StateValue",
    "infer_quality",
    "quality_for_corrupted",
    "quality_for_missing",
    "quality_for_stale",
    "utc_now",
    "HealthMonitor",
    "IncidentRecord",
    "WorkerLifecycleState",
    "ErrorBoundary",
    "ErrorCode",
    "Supervisor",
    "WorkerModule",
    "load_config",
    "ConfigValidationError",
    "EventBus",
    "EventBusValidationError",
    "MissionControlFormatter",
    "get_logger",
    "MissionControlConfig",
    "MissionEvent",
    "EventCategory",
    "ErrorDescriptor",
    "UiErrorBoundary",
    "GuardedExecutionResult",
    "CoreErrorCode",
    "DEFAULT_ERROR_MESSAGES",
]
