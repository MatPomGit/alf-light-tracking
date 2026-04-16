"""Narzędzia do ładowania i wykonywania scenariuszy FSM z pliku YAML.

Moduł pozwala definiować wiele nazwanych scenariuszy w jednym pliku YAML
i wybierać je po nazwie misji. Dzięki temu `mission_node` może obsługiwać
różne warianty zachowania robota bez przepisywania samego kodu node'a.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml


@dataclass
class ScenarioTransition:
    """Pojedyncze przejście pomiędzy stanami FSM."""

    target: str
    condition: Any
    min_state_time: float = 0.0
    max_state_time: Optional[float] = None
    actions: List[str] = field(default_factory=list)


@dataclass
class ScenarioState:
    """Opis pojedynczego stanu FSM."""

    name: str
    target_policy: str = "generic"
    reason: str = ""
    transitions: List[ScenarioTransition] = field(default_factory=list)


@dataclass
class ScenarioDefinition:
    """Pełna definicja jednego scenariusza FSM."""

    name: str
    initial_state: str
    terminal_states: List[str]
    states: Dict[str, ScenarioState]


def default_mission_scenario_dict() -> Dict[str, Any]:
    return {
        "name": "delivery_default",
        "initial_state": "search",
        "terminal_states": ["drop"],
        "states": {
            "search": {
                "target_policy": "generic",
                "reason": "searching for person, parcel, shelf or drop cue",
                "transitions": [
                    {
                        "target": "verify_qr",
                        "condition": {"all": ["parcel_exists", "parcel_has_qr"]},
                        "actions": ["set_active_parcel_from_parcel"],
                    },
                    {
                        "target": "receive_parcel",
                        "condition": "parcel_exists",
                        "actions": ["set_active_parcel_from_parcel"],
                    },
                    {"target": "approach_person", "condition": "person_exists"},
                    {"target": "navigate", "condition": "shelf_exists"},
                ],
            },
            "approach_person": {
                "target_policy": "person",
                "reason": "person detected but no active parcel yet",
                "transitions": [
                    {
                        "target": "verify_qr",
                        "condition": {"all": ["parcel_exists", "parcel_has_qr"]},
                        "actions": ["set_active_parcel_from_parcel"],
                    },
                    {
                        "target": "receive_parcel",
                        "condition": "parcel_exists",
                        "actions": ["set_active_parcel_from_parcel"],
                    },
                    {"target": "search", "condition": "person_missing_timeout"},
                ],
            },
            "receive_parcel": {
                "target_policy": "parcel",
                "reason": "parcel visible but QR not identified yet",
                "transitions": [
                    {
                        "target": "verify_qr",
                        "condition": {"all": ["parcel_exists", "parcel_has_qr"]},
                        "actions": ["set_active_parcel_from_parcel"],
                    },
                    {"target": "search", "condition": "parcel_missing_timeout"},
                ],
            },
            "verify_qr": {
                "target_policy": "parcel",
                "reason": "parcel has QR or binding, waiting for identification",
                "transitions": [
                    {"target": "navigate", "condition": "parcel_identified"},
                    {"target": "search", "condition": "parcel_missing_timeout"},
                ],
            },
            "navigate": {
                "target_policy": "parcel",
                "reason": "identified parcel available, navigating to destination cues",
                "transitions": [
                    {"target": "align", "condition": "light_color_in_zone"},
                    {"target": "search", "condition": "navigate_missing_timeout"},
                ],
            },
            "align": {
                "target_policy": "align",
                "reason": "drop target visible, performing final alignment",
                "transitions": [
                    {"target": "drop", "condition": "light_aligned_for_drop"},
                    {"target": "navigate", "condition": "light_missing_timeout"},
                ],
            },
            "drop": {
                "target_policy": "drop",
                "reason": "drop conditions satisfied",
                "transitions": [
                    {
                        "target": "search",
                        "condition": "drop_finished_timeout",
                        "actions": ["clear_active_parcel"],
                    }
                ],
            },
        },
    }


def scenario_from_dict(data: Dict[str, Any]) -> ScenarioDefinition:
    states: Dict[str, ScenarioState] = {}
    for state_name, raw_state in data.get("states", {}).items():
        transitions = []
        for raw_transition in raw_state.get("transitions", []):
            transitions.append(
                ScenarioTransition(
                    target=str(raw_transition["target"]),
                    condition=raw_transition.get("condition", True),
                    min_state_time=float(raw_transition.get("min_state_time", 0.0)),
                    max_state_time=(
                        float(raw_transition["max_state_time"])
                        if "max_state_time" in raw_transition
                        else None
                    ),
                    actions=list(raw_transition.get("actions", [])),
                )
            )
        states[state_name] = ScenarioState(
            name=state_name,
            target_policy=str(raw_state.get("target_policy", "generic")),
            reason=str(raw_state.get("reason", "")),
            transitions=transitions,
        )

    initial_state = str(data.get("initial_state", "search"))
    if initial_state not in states:
        raise ValueError(f"initial_state={initial_state!r} nie istnieje w states")

    return ScenarioDefinition(
        name=str(data.get("name", "unnamed_scenario")),
        initial_state=initial_state,
        terminal_states=list(data.get("terminal_states", [])),
        states=states,
    )


def _extract_registry(data: Dict[str, Any]) -> Tuple[Optional[str], Dict[str, Any]]:
    if "scenarios" in data:
        registry = data.get("scenarios", {})
        if not isinstance(registry, dict) or not registry:
            raise ValueError("Pole 'scenarios' musi być niepustą mapą YAML")
        default_name = data.get("default_scenario")
        return (str(default_name) if default_name else None), registry

    scenario_name = str(data.get("name", "default"))
    return scenario_name, {scenario_name: data}


def load_named_scenario_definition(path: str | Path | None, scenario_name: str | None) -> ScenarioDefinition:
    if not path:
        return scenario_from_dict(default_mission_scenario_dict())

    scenario_path = Path(path)
    if not scenario_path.is_absolute():
        scenario_path = Path.cwd() / scenario_path
    if not scenario_path.exists():
        raise FileNotFoundError(f"Plik scenariusza nie istnieje: {scenario_path}")

    data = yaml.safe_load(scenario_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Plik scenariusza musi zawierać mapę YAML")

    default_name, registry = _extract_registry(data)
    selected_name = scenario_name or default_name or next(iter(registry.keys()))
    if selected_name not in registry:
        available = ", ".join(sorted(registry.keys()))
        raise ValueError(f"Nie znaleziono scenariusza {selected_name!r}. Dostępne: {available}")

    selected = dict(registry[selected_name])
    selected.setdefault("name", selected_name)
    return scenario_from_dict(selected)


def load_scenario_definition(path: str | Path | None) -> ScenarioDefinition:
    return load_named_scenario_definition(path, None)


def evaluate_condition(expr: Any, predicates: Dict[str, bool]) -> bool:
    if isinstance(expr, bool):
        return expr
    if isinstance(expr, str):
        return bool(predicates.get(expr, False))
    if isinstance(expr, dict):
        if "not" in expr:
            return not evaluate_condition(expr["not"], predicates)
        if "all" in expr:
            return all(evaluate_condition(item, predicates) for item in expr["all"])
        if "any" in expr:
            return any(evaluate_condition(item, predicates) for item in expr["any"])
    raise ValueError(f"Nieobsługiwany warunek scenariusza: {expr!r}")
