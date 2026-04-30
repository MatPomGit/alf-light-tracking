"""Testy walidacji loadera konfiguracji Mission Control."""

from __future__ import annotations

from pathlib import Path

import pytest

from robot_mission_control.core.config_loader import ConfigValidationError, load_config


def _write_config(tmp_path: Path, content: str) -> Path:
    config_path = tmp_path / "default.yaml"
    config_path.write_text(content, encoding="utf-8")
    return config_path


# [AI-CHANGE | 2026-04-23 18:29 UTC | v0.195]
# CO ZMIENIONO: Dodano testy walidacji nowych interwałów timerów w `ui_timer_intervals_ms`.
# DLACZEGO: Musimy gwarantować, że konfiguracja sterująca timerami jest kompletna i bezpieczna.
# JAK TO DZIAŁA: Testy pokrywają zarówno ścieżkę poprawną, jak i błąd brakującego klucza timera.
# TODO: Dodać testy graniczne dla wartości skrajnych (np. 1 ms i bardzo duże interwały).
def test_load_config_accepts_complete_ui_timer_configuration(tmp_path: Path) -> None:
    config_path = _write_config(
        tmp_path,
        """
session_id: "session-1"
operator_timeout_sec: 2.5
max_event_queue_size: 100
log_level: "INFO"
ui_timer_intervals_ms:
  bridge_poll_interval_ms: 1000
  main_window_refresh_interval_ms: 1000
  controls_tab_refresh_interval_ms: 500
  debug_tab_refresh_interval_ms: 1000
  video_depth_tab_refresh_interval_ms: 700
  telemetry_tab_refresh_interval_ms: 700
  rosbag_tab_refresh_interval_ms: 500
  diagnostics_tab_refresh_interval_ms: 1200
  extensions_tab_refresh_interval_ms: 1500
  overview_tab_refresh_interval_ms: 700
map:
  max_sample_age_s: 2.5
  max_speed_mps: 3.5
  allowed_frames: ["map"]
""".strip(),
    )

    config = load_config(config_path)
    assert config.ui_timer_intervals_ms["bridge_poll_interval_ms"] == 1000
    assert config.ui_timer_intervals_ms["overview_tab_refresh_interval_ms"] == 700


def test_load_config_rejects_missing_ui_timer_key(tmp_path: Path) -> None:
    config_path = _write_config(
        tmp_path,
        """
session_id: "session-1"
operator_timeout_sec: 2.5
max_event_queue_size: 100
log_level: "INFO"
ui_timer_intervals_ms:
  bridge_poll_interval_ms: 1000
  main_window_refresh_interval_ms: 1000
  controls_tab_refresh_interval_ms: 500
  debug_tab_refresh_interval_ms: 1000
  video_depth_tab_refresh_interval_ms: 700
  telemetry_tab_refresh_interval_ms: 700
  rosbag_tab_refresh_interval_ms: 500
  diagnostics_tab_refresh_interval_ms: 1200
  extensions_tab_refresh_interval_ms: 1500
""".strip(),
    )

    with pytest.raises(ConfigValidationError):
        load_config(config_path)


# [AI-CHANGE | 2026-04-30 23:20 UTC | v0.201]
# CO ZMIENIONO: Dodano testy walidacji sekcji `map` dla poprawnej konfiguracji i uszkodzonych danych.
# DLACZEGO: Nowe pola mapy muszą mieć rygorystyczną walidację, aby nie dopuścić do niepewnej detekcji pozycji.
# JAK TO DZIAŁA: Testy sprawdzają pozytywną ścieżkę odczytu oraz błąd dla nieprawidłowej listy `allowed_frames`.
# TODO: Dodać testy odrzucające wartości graniczne `max_sample_age_s=0` i `max_speed_mps=0`.
def test_load_config_accepts_map_configuration(tmp_path: Path) -> None:
    config_path = _write_config(
        tmp_path,
        """
session_id: "session-1"
operator_timeout_sec: 2.5
max_event_queue_size: 100
log_level: "INFO"
ui_timer_intervals_ms:
  bridge_poll_interval_ms: 1000
  main_window_refresh_interval_ms: 1000
  controls_tab_refresh_interval_ms: 500
  debug_tab_refresh_interval_ms: 1000
  video_depth_tab_refresh_interval_ms: 700
  telemetry_tab_refresh_interval_ms: 700
  rosbag_tab_refresh_interval_ms: 500
  diagnostics_tab_refresh_interval_ms: 1200
  extensions_tab_refresh_interval_ms: 1500
  overview_tab_refresh_interval_ms: 700
map:
  max_sample_age_s: 3.0
  max_speed_mps: 2.25
  allowed_frames: ["map", "odom"]
""".strip(),
    )
    config = load_config(config_path)
    assert config.map_config["max_sample_age_s"] == 3.0
    assert config.map_config["max_speed_mps"] == 2.25
    assert config.map_config["allowed_frames"] == ["map", "odom"]


def test_load_config_rejects_empty_map_allowed_frames(tmp_path: Path) -> None:
    config_path = _write_config(
        tmp_path,
        """
session_id: "session-1"
operator_timeout_sec: 2.5
max_event_queue_size: 100
log_level: "INFO"
ui_timer_intervals_ms:
  bridge_poll_interval_ms: 1000
  main_window_refresh_interval_ms: 1000
  controls_tab_refresh_interval_ms: 500
  debug_tab_refresh_interval_ms: 1000
  video_depth_tab_refresh_interval_ms: 700
  telemetry_tab_refresh_interval_ms: 700
  rosbag_tab_refresh_interval_ms: 500
  diagnostics_tab_refresh_interval_ms: 1200
  extensions_tab_refresh_interval_ms: 1500
  overview_tab_refresh_interval_ms: 700
map:
  max_sample_age_s: 3.0
  max_speed_mps: 2.25
  allowed_frames: []
""".strip(),
    )
    with pytest.raises(ConfigValidationError):
        load_config(config_path)
