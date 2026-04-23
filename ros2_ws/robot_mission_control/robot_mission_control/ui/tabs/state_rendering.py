"""Wspólne helpery renderowania stanu dla zakładek UI."""

from __future__ import annotations

from robot_mission_control.core import DataQuality, StateValue

# [AI-CHANGE | 2026-04-23 14:15 UTC | v0.187]
# CO ZMIENIONO: Dodano wspólny moduł helperów renderowania dla StateValue:
#               `render_value`, `render_quality` oraz `is_actionable`.
# DLACZEGO: Kilka zakładek dublowało tę samą logikę fallbacków i bramkowania jakości, co utrudniało
#           utrzymanie spójnej zasady bezpieczeństwa „lepiej brak wyniku niż błędny wynik”.
# JAK TO DZIAŁA: `is_actionable` dopuszcza tylko próbki z `quality == VALID` i niepustą wartością.
#                `render_value` korzysta z tej bramki i dla każdego stanu niepewnego zwraca fallback,
#                więc wartość operacyjna nigdy nie wycieka przy jakości różnej od VALID.
#                `render_quality` zwraca jawny tag jakości albo `UNAVAILABLE`, gdy próbki brak.
# TODO: Dodać mapowanie quality -> kolor/ikonę oraz wariant renderowania dla widoków z priorytetami alarmów.
def is_actionable(item: StateValue | None) -> bool:
    """Zwraca True tylko dla bezpiecznej, operacyjnej próbki danych."""
    if item is None:
        return False
    if item.quality is not DataQuality.VALID:
        return False
    return item.value is not None


def render_value(item: StateValue | None, fallback: str = "BRAK DANYCH") -> str:
    """Renderuje wartość z bezpiecznym fallbackiem dla danych niepewnych."""
    if not is_actionable(item):
        return fallback
    return str(item.value)


def render_quality(item: StateValue | None) -> str:
    """Renderuje jakość próbki w postaci etykiety tekstowej."""
    if item is None:
        return DataQuality.UNAVAILABLE.value
    return item.quality.value
