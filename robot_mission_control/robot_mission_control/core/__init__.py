"""Core domain primitives for robot mission control."""

# [AI-CHANGE | 2026-04-20 19:12 UTC | v0.145]
# CO ZMIENIONO: Rozszerzono publiczne API `core` o Supervisor, HealthMonitor i modele incydentów/lifecycle.
# DLACZEGO: Ujednolicone importy upraszczają integrację warstwy app/UI z mechanizmami izolacji awarii.
# JAK TO DZIAŁA: `__all__` eksportuje nowe klasy monitoringu i nadzoru, dzięki czemu moduły klienckie
#                mogą używać jednej przestrzeni nazw `robot_mission_control.core`.
# TODO: Rozważyć podział eksportów na podmoduły `core.runtime` i `core.state`, aby ograniczyć sprzężenie API.

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
