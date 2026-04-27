from __future__ import annotations

import pytest

from robot_mission_control.ui.tabs.operator_guidance import FALLBACK_GUIDANCE, resolve_operator_guidance


# [AI-CHANGE | 2026-04-27 06:55 UTC | v0.203]
# CO ZMIENIONO: Dodano test kontraktowy dla krytycznych `reason_code`, które muszą zwracać
#               dedykowane i spójne komunikaty operatorskie (bez fallbacku).
# DLACZEGO: DoD wymaga jednolitego „co się stało / co zrobić” dla kodów krytycznych
#           niezależnie od zakładki, więc mapa guidance musi być kompletna i stabilna.
# JAK TO DZIAŁA: Test parametryczny wywołuje `resolve_operator_guidance` dla każdego kodu
#                krytycznego i sprawdza, że wynik nie jest fallbackiem oraz zawiera treść instrukcyjną.
# TODO: Rozszerzyć listę o kody pojawiające się dynamicznie z backendów zewnętrznych (telemetria produkcyjna).
@pytest.mark.parametrize(
    "reason_code",
    (
        "transport_failure",
        "timeout",
        "bridge_error",
        "node_manager_unavailable",
        "waiting_for_topics",
        "app_shutdown",
        "shutdown_failed",
        "node_shutdown",
        "goal_already_running",
        "unknown_quick_command",
        "no_active_goal",
        "goal_finished",
        "not_initialized",
    ),
)
def test_critical_reason_codes_have_dedicated_operator_guidance(reason_code: str) -> None:
    guidance = resolve_operator_guidance(reason_code=reason_code, status=None)
    assert guidance != FALLBACK_GUIDANCE
    assert guidance.meaning
    assert guidance.action
