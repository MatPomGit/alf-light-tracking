from __future__ import annotations

from pathlib import Path

import yaml

# [AI-CHANGE | 2026-04-29 13:15 UTC | v0.332]
# CO ZMIENIONO: Test zgodności kontraktu odczytuje `MissionStep.action` z pakietu `robot_mission_control`.
# DLACZEGO: Interfejs jest teraz częścią pojedynczego pakietu; test ma blokować powrót do zależności od
#           `robot_mission_control_interfaces` i chronić runtime przed błędnym importem typu.
# JAK TO DZIAŁA: Test parsuje lokalny kontrakt Action i config runtime, a następnie sprawdza moduł typu,
#                obecność kluczowych pól oraz kompatybilność quick-akcji i `display_fields`.
# TODO: Dodać test uruchamiany po `colcon build`, który zweryfikuje także introspekcję wygenerowanego typu ROS2.
def _parse_action_contract_fields(action_text: str) -> tuple[set[str], set[str], set[str]] | None:
    sections = action_text.split("---")
    if len(sections) != 3:
        return None

    parsed_sections: list[set[str]] = []
    for section in sections:
        fields: set[str] = set()
        for raw_line in section.splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            tokens = line.split()
            if len(tokens) < 2:
                continue
            fields.add(tokens[1].strip())
        parsed_sections.append(fields)
    return parsed_sections[0], parsed_sections[1], parsed_sections[2]


def test_mission_step_contract_is_runtime_compatible_with_action_backend_and_ui() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    action_path = repo_root / "robot_mission_control" / "action" / "MissionStep.action"
    backend_config_path = repo_root / "robot_mission_control" / "config" / "action_backend.yaml"

    raw_config = yaml.safe_load(backend_config_path.read_text(encoding="utf-8"))
    assert isinstance(raw_config, dict)
    assert raw_config.get("action_type_module") == "robot_mission_control.action"
    assert raw_config.get("action_type_name") == "MissionStep"

    parsed_fields = _parse_action_contract_fields(action_path.read_text(encoding="utf-8"))
    assert parsed_fields is not None
    goal_fields, feedback_fields, result_fields = parsed_fields
    assert "goal" in goal_fields
    assert "progress" in feedback_fields
    assert "outcome" in result_fields

    goal_payload_map = raw_config.get("goal_payload_map")
    assert isinstance(goal_payload_map, dict)
    for command_payload in goal_payload_map.values():
        assert isinstance(command_payload, dict)
        for payload_key in command_payload.keys():
            assert payload_key in goal_fields

    result_cfg = raw_config.get("result")
    assert isinstance(result_cfg, dict)
    display_fields = result_cfg.get("display_fields")
    assert isinstance(display_fields, list)
    for field_name in display_fields:
        assert isinstance(field_name, str)
        assert field_name in result_fields
