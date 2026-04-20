"""Core domain primitives for robot mission control."""

# [AI-CHANGE | 2026-04-20 18:27 UTC | v0.143]
# CO ZMIENIONO: Dodano eksporty publiczne modułu core ze store stanu i modelami jakości danych.
# DLACZEGO: Upraszcza to importy w warstwie app/UI i promuje jeden punkt wejścia dla logiki stanu.
# JAK TO DZIAŁA: __all__ wskazuje klasy/funkcje używane przez most ROS i okno główne.
# TODO: Rozszerzyć API o wersjonowanie schematu stanu po stabilizacji kontraktów między modułami.

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
]
