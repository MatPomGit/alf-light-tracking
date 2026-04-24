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


# [AI-CHANGE | 2026-04-24 10:20 UTC | v0.200]
# CO ZMIENIONO: Dodano helper `render_card_value_with_warning`, który dla jakości != VALID
#               renderuje jednoznaczny komunikat operatorski: ostrzeżenie + `BRAK DANYCH` + `reason_code`.
# DLACZEGO: Karty UI muszą jawnie sygnalizować niepewną próbkę i nie mogą wyglądać jak stan operacyjny.
# JAK TO DZIAŁA: Dla próbki `VALID` funkcja zwraca normalną wartość; dla braku próbki zwraca fallback,
#                a dla jakości różnej od `VALID` buduje tekst `⚠ BRAK DANYCH | reason_code=...`.
# TODO: Dodać lokalizację poziomów ostrzeżeń i mapowanie `reason_code` na komunikaty operatorskie.
def render_card_value_with_warning(item: StateValue | None, fallback: str = "BRAK DANYCH") -> str:
    """Renderuje wartość dla kart z wymuszonym ostrzeżeniem przy jakości != VALID."""
    if item is None:
        return fallback
    if is_actionable(item):
        return str(item.value)
    reason_code = item.reason_code or "UNKNOWN_REASON"
    return f"⚠ {fallback} | reason_code={reason_code}"


def render_quality(item: StateValue | None) -> str:
    """Renderuje jakość próbki w postaci etykiety tekstowej."""
    if item is None:
        return DataQuality.UNAVAILABLE.value
    return item.quality.value


# [AI-CHANGE | 2026-04-23 17:10 UTC | v0.192]
# CO ZMIENIONO: Dodano jawny alias `render_state` dla statusów jakości
#               (`VALID/STALE/UNAVAILABLE/ERROR`) wykorzystywanych przez karty UI.
# DLACZEGO: Wymaganie wdrożeniowe mówi o wspólnym module helperów renderujących stan,
#           więc nazwa funkcji musi być semantycznie czytelna dla wszystkich kart.
# JAK TO DZIAŁA: `render_state` deleguje do `render_quality`, dzięki czemu każda karta
#                otrzymuje identyczne mapowanie stanu i spójne fallbacki dla braku próbki.
# TODO: Rozdzielić w przyszłości `render_state` na wariant surowy i wariant lokalizowany (PL/EN).
def render_state(item: StateValue | None) -> str:
    """Renderuje stan jakości danych dla etykiet kart UI."""
    return render_quality(item)
