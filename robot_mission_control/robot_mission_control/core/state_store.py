"""Central state store for UI-safe mission control data flow."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from threading import RLock
from typing import Any


# [AI-CHANGE | 2026-04-21 03:58 UTC | v0.160]
# CO ZMIENIONO: Dodano globalny klucz `ros_connection_status` do StateStore.
# DLACZEGO: Status utraty i odzyskania połączenia ma być publikowany centralnie i renderowany przez UI.
# JAK TO DZIAŁA: Bootstrap store tworzy wpis dla nowego klucza w stanie UNAVAILABLE; warstwa ROS
#                nadpisuje go przez `set_with_inference`, a UI otrzymuje bezpieczny fallback.
# TODO: Wprowadzić enum domenowy dla statusu połączenia zamiast surowego stringa.


class DataQuality(Enum):
    """Canonical quality states shared by ROS bridge and UI layers."""

    VALID = "VALID"
    STALE = "STALE"
    UNAVAILABLE = "UNAVAILABLE"
    ERROR = "ERROR"


@dataclass(frozen=True, slots=True)
class StateValue:
    """Single typed state item used by all UI-facing bindings."""

    value: Any
    timestamp: datetime
    source: str
    quality: DataQuality
    reason_code: str | None = None


STATE_KEY_DATA_SOURCE_MODE = "data_source_mode"
STATE_KEY_RECORDING_STATUS = "recording_status"
STATE_KEY_PLAYBACK_STATUS = "playback_status"
STATE_KEY_SELECTED_BAG = "selected_bag"
STATE_KEY_BAG_INTEGRITY_STATUS = "bag_integrity_status"
STATE_KEY_DEPENDENCY_STATUS = "dependency_status"
STATE_KEY_ROS_CONNECTION_STATUS = "ros_connection_status"

GLOBAL_STATE_KEYS = (
    STATE_KEY_DATA_SOURCE_MODE,
    STATE_KEY_RECORDING_STATUS,
    STATE_KEY_PLAYBACK_STATUS,
    STATE_KEY_SELECTED_BAG,
    STATE_KEY_BAG_INTEGRITY_STATUS,
    STATE_KEY_DEPENDENCY_STATUS,
    STATE_KEY_ROS_CONNECTION_STATUS,
)


def utc_now() -> datetime:
    """Return timezone-aware UTC timestamp."""
    return datetime.now(timezone.utc)


def quality_for_missing(*, reason_code: str = "missing_data") -> DataQuality:
    """Map missing data to a safe quality value."""
    _ = reason_code
    return DataQuality.UNAVAILABLE


def quality_for_stale(*, reason_code: str = "stale_data") -> DataQuality:
    """Map stale data to a safe quality value."""
    _ = reason_code
    return DataQuality.STALE


def quality_for_corrupted(*, reason_code: str = "corrupted_data") -> DataQuality:
    """Map corrupted data to a safe quality value."""
    _ = reason_code
    return DataQuality.ERROR


def infer_quality(
    *,
    value: Any,
    timestamp: datetime | None,
    now: datetime | None = None,
    max_age: timedelta = timedelta(seconds=5),
    is_corrupted: bool = False,
) -> DataQuality:
    """Infer data quality with conservative rules (prefer no result over wrong result)."""
    if is_corrupted:
        return quality_for_corrupted()

    if value is None or timestamp is None:
        return quality_for_missing()

    current_time = now or utc_now()
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)

    if current_time - timestamp > max_age:
        return quality_for_stale()

    return DataQuality.VALID


class StateStore:
    """Thread-safe state container consumed by UI and populated by integrations."""

    def __init__(self) -> None:
        self._lock = RLock()
        self._state: dict[str, StateValue] = {}
        self._bootstrap_defaults()

    def _bootstrap_defaults(self) -> None:
        now = utc_now()
        for key in GLOBAL_STATE_KEYS:
            self._state[key] = StateValue(
                value=None,
                timestamp=now,
                source="bootstrap",
                quality=DataQuality.UNAVAILABLE,
                reason_code="not_initialized",
            )

    def set(self, key: str, item: StateValue) -> None:
        """Store validated value; caller is responsible for precomputing quality."""
        with self._lock:
            self._state[key] = item

    def set_with_inference(
        self,
        *,
        key: str,
        value: Any,
        source: str,
        timestamp: datetime | None = None,
        max_age: timedelta = timedelta(seconds=5),
        is_corrupted: bool = False,
        reason_code: str | None = None,
    ) -> StateValue:
        """Store value with deterministic quality mapping."""
        effective_timestamp = timestamp or utc_now()
        quality = infer_quality(
            value=value,
            timestamp=effective_timestamp,
            max_age=max_age,
            is_corrupted=is_corrupted,
        )

        if quality is DataQuality.VALID:
            effective_reason_code = reason_code
        elif quality is DataQuality.STALE:
            effective_reason_code = reason_code or "stale_data"
        elif quality is DataQuality.ERROR:
            effective_reason_code = reason_code or "corrupted_data"
        else:
            effective_reason_code = reason_code or "missing_data"

        item = StateValue(
            value=value if quality is DataQuality.VALID else None,
            timestamp=effective_timestamp,
            source=source,
            quality=quality,
            reason_code=effective_reason_code,
        )
        self.set(key, item)
        return item

    def get(self, key: str) -> StateValue | None:
        """Read state item for key."""
        with self._lock:
            return self._state.get(key)

    def snapshot(self) -> dict[str, StateValue]:
        """Read atomic snapshot for full UI render pass."""
        with self._lock:
            return dict(self._state)
