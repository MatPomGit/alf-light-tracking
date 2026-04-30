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


# [AI-CHANGE | 2026-04-30 13:10 UTC | v0.201]
# CO ZMIENIONO: Dodano testy mapowania nowych kodów mapy/lokalizacji na guidance operatorskie
#               oraz test fallbacku dla nieznanego `reason_code`.
# DLACZEGO: Wymagania UI mapy wymagają spójnego „co się stało / co zrobić” i bezpiecznego
#           zachowania dla kodów spoza słownika (wstrzymanie działań krytycznych).
# JAK TO DZIAŁA: Test parametryczny potwierdza, że kody mapowe nie trafiają do fallbacku,
#                a osobny test sprawdza, że nieznany kod zwraca ostrożną instrukcję.
# TODO: Rozszerzyć testy o automatyczne porównanie listy kodów mapy używanych w `MapTab`.
@pytest.mark.parametrize(
    "reason_code",
    (
        "MAP_TF_MISSING",
        "MAP_POSE_STALE",
        "MAP_FRAME_MISMATCH",
    ),
)
def test_map_reason_codes_have_dedicated_operator_guidance(reason_code: str) -> None:
    guidance = resolve_operator_guidance(reason_code=reason_code, status=None)
    assert guidance != FALLBACK_GUIDANCE
    assert "Brakuje" in guidance.meaning or "przeterminowana" in guidance.meaning or "niespójne" in guidance.meaning
    assert guidance.action


def test_unknown_reason_code_uses_cautious_fallback() -> None:
    guidance = resolve_operator_guidance(reason_code="MAP_FUTURE_UNKNOWN", status="RUNNING")
    assert guidance == FALLBACK_GUIDANCE
    assert "Wstrzymaj ryzykowne działania" in guidance.action
