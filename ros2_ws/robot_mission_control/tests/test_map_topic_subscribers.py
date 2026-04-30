from __future__ import annotations

from datetime import datetime, timezone

from robot_mission_control.core import (
    DataQuality,
    STATE_KEY_MAP_FRAME_STATUS,
    STATE_KEY_MAP_PATH,
    STATE_KEY_MAP_POSE,
    StateStore,
)
from robot_mission_control.ros.topic_subscribers import MapPathPayload, MapPosePayload, TelemetryTopicSubscribers


# [AI-CHANGE | 2026-04-30 12:00 UTC | v0.201]
# CO ZMIENIONO: Dodano testy kontraktowe dla mapowania danych mapy (pose/path/frame_status)
#               do `StateStore`, ze sprawdzeniem jakości danych i reason_code fallbacku.
# DLACZEGO: Krytyczne jest egzekwowanie zasady bezpieczeństwa „lepiej brak wyniku niż wynik błędny”
#           w warstwie ROS -> UI dla danych mapy.
# JAK TO DZIAŁA: Testy podają poprawne i uszkodzone próbki; asercje weryfikują typ wartości,
#                `DataQuality` oraz wymagane `reason_code` przy degradacji.
# TODO: Dodać warianty testów z realnym ROS time i walidacją dryfu timestamp dla callbacków mapy.
def _build_subscriber() -> tuple[StateStore, TelemetryTopicSubscribers]:
    store = StateStore()
    subscriber = TelemetryTopicSubscribers(
        state_store=store,
        session_id="session-map",
        allowed_sources={"map_source"},
    )
    return store, subscriber


def test_on_map_pose_stores_typed_payload_for_valid_sample() -> None:
    store, subscriber = _build_subscriber()

    subscriber.on_map_pose(
        state_key=STATE_KEY_MAP_POSE,
        payload={"x": 1.5, "y": -2.0, "yaw": 0.1},
        source="map_source",
        sample_timestamp=datetime.now(timezone.utc),
        correlation_id="corr-map-pose-valid",
    )

    item = store.get(STATE_KEY_MAP_POSE)
    assert item is not None
    assert item.quality is DataQuality.VALID
    assert isinstance(item.value, MapPosePayload)


def test_on_map_pose_falls_back_to_error_for_invalid_payload() -> None:
    store, subscriber = _build_subscriber()

    subscriber.on_map_pose(
        state_key=STATE_KEY_MAP_POSE,
        payload={"x": "bad", "y": 2.0},
        source="map_source",
        sample_timestamp=datetime.now(timezone.utc),
        correlation_id="corr-map-pose-invalid",
    )

    item = store.get(STATE_KEY_MAP_POSE)
    assert item is not None
    assert item.value is None
    assert item.quality is DataQuality.ERROR
    assert item.reason_code == "map_pose_invalid"


def test_on_map_path_falls_back_to_error_for_invalid_points() -> None:
    store, subscriber = _build_subscriber()

    subscriber.on_map_path(
        state_key=STATE_KEY_MAP_PATH,
        payload=[{"x": 1.0}, {"x": 2.0, "y": 3.0}],
        source="map_source",
        sample_timestamp=datetime.now(timezone.utc),
        correlation_id="corr-map-path-invalid",
    )

    item = store.get(STATE_KEY_MAP_PATH)
    assert item is not None
    assert item.value is None
    assert item.quality is DataQuality.ERROR
    assert item.reason_code == "map_path_invalid"


def test_on_map_path_stores_typed_payload_for_valid_sample() -> None:
    store, subscriber = _build_subscriber()

    subscriber.on_map_path(
        state_key=STATE_KEY_MAP_PATH,
        payload=[{"x": 1.0, "y": 2.0}, {"x": 3.0, "y": 4.0}],
        source="map_source",
        sample_timestamp=datetime.now(timezone.utc),
        correlation_id="corr-map-path-valid",
    )

    item = store.get(STATE_KEY_MAP_PATH)
    assert item is not None
    assert item.quality is DataQuality.VALID
    assert isinstance(item.value, MapPathPayload)


def test_on_map_frame_status_rejects_unknown_status() -> None:
    store, subscriber = _build_subscriber()

    subscriber.on_map_frame_status(
        state_key=STATE_KEY_MAP_FRAME_STATUS,
        payload="unknown",
        source="map_source",
        sample_timestamp=datetime.now(timezone.utc),
        correlation_id="corr-map-frame-invalid",
    )

    item = store.get(STATE_KEY_MAP_FRAME_STATUS)
    assert item is not None
    assert item.value is None
    assert item.quality is DataQuality.ERROR
    assert item.reason_code == "map_frame_status_invalid"
