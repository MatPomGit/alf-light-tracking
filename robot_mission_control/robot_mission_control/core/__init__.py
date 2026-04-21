"""Core domain primitives for robot mission control."""

# [AI-CHANGE | 2026-04-21 03:58 UTC | v0.160]
# CO ZMIENIONO: Rozszerzono publiczne API `core` o klucz `STATE_KEY_ROS_CONNECTION_STATUS`.
# DLACZEGO: Warstwy app/UI muszą używać jednego źródła nazw dla statusu połączenia ROS.
# JAK TO DZIAŁA: Import i `__all__` publikują nową stałą, dzięki czemu wszystkie moduły pobierają ten sam klucz.
# TODO: Zastąpić ręczne `__all__` generowaniem statycznym z testem spójności eksportów.

# [AI-CHANGE | 2026-04-21 05:21 UTC | v0.163]
# CO ZMIENIONO: Rozszerzono eksporty publiczne `core` o klucze stanu akcji dla UI i warstwy aplikacji.
# DLACZEGO: Moduły bootstrap/main_window/controls_tab wymagają wspólnych stałych bez lokalnego duplikowania.
# JAK TO DZIAŁA: Nowe klucze są importowane z `state_store` i publikowane w `__all__`.
# TODO: Dodać test kontraktowy pilnujący zgodności `__all__` z rzeczywistymi importami.

from robot_mission_control.core.health_monitor import (
    HealthMonitor,
    IncidentRecord,
    WorkerLifecycleState,
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
]
