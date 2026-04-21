"""Core domain primitives for robot mission control."""

# [AI-CHANGE | 2026-04-21 03:58 UTC | v0.160]
# CO ZMIENIONO: Rozszerzono publiczne API `core` o klucz `STATE_KEY_ROS_CONNECTION_STATUS`.
# DLACZEGO: Warstwy app/UI muszą używać jednego źródła nazw dla statusu połączenia ROS.
# JAK TO DZIAŁA: Import i `__all__` publikują nową stałą, dzięki czemu wszystkie moduły pobierają ten sam klucz.
# TODO: Zastąpić ręczne `__all__` generowaniem statycznym z testem spójności eksportów.

from robot_mission_control.core.health_monitor import (
    HealthMonitor,
    IncidentRecord,
    WorkerLifecycleState,
)
from robot_mission_control.core.state_store import (
    DataQuality,
    GLOBAL_STATE_KEYS,
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
    "DataQuality",
    "GLOBAL_STATE_KEYS",
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
]
