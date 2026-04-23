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
