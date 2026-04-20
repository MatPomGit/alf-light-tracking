"""Core domain primitives for robot mission control."""

# [AI-CHANGE | 2026-04-20 20:05 UTC | v0.151]
# CO ZMIENIONO: Rozszerzono publiczne API `core` o stałą `STATE_KEY_DEPENDENCY_STATUS`.
# DLACZEGO: Warstwy app/UI muszą używać wspólnego klucza do publikacji i renderowania raportu zależności.
# JAK TO DZIAŁA: `__all__` i importy eksportują nowy klucz, dzięki czemu dostęp odbywa się przez
#                pojedynczą przestrzeń nazw `robot_mission_control.core`.
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
