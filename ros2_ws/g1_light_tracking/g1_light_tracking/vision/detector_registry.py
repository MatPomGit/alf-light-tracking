# [AI-CHANGE | 2026-04-17 13:06 UTC | v0.91]
# CO ZMIENIONO: Dodano komentarze opisujące przeznaczenie klas i metod oraz motywację przyjętej struktury.
# DLACZEGO: Ułatwia to bezpieczne utrzymanie kodu R&D i ogranicza ryzyko błędnej interpretacji logiki detekcji.
# JAK TO DZIAŁA: Każda klasa/metoda posiada docstring z celem i uzasadnieniem, dzięki czemu intencja implementacji jest jawna.
# TODO: Rozszerzyć docstringi o kontrakty wejścia/wyjścia po ustabilizowaniu API między węzłami.

from __future__ import annotations

from typing import Dict, Type

from .detector_interfaces import BaseDetector
from .detectors import BrightnessDetector, ColorDetector


# Centralna mapa metod detekcji na klasy adapterów.
DETECTOR_REGISTRY: Dict[str, Type[BaseDetector]] = {
    "brightness": BrightnessDetector,
    "color": ColorDetector,
}


def get_detector_class(name: str) -> Type[BaseDetector]:
    """Zwraca klasę detektora dla podanej nazwy metody."""
    detector_cls = DETECTOR_REGISTRY.get(name)
    if detector_cls is None:
        available = ", ".join(sorted(DETECTOR_REGISTRY))
        raise ValueError(f"Nieznana metoda detekcji: {name}. Dostępne: {available}")
    return detector_cls


def get_default_params(name: str) -> dict:
    """Zwraca domyślne parametry dla metody detekcji."""
    return get_detector_class(name).default_params()


def available_detector_names() -> list[str]:
    """Zwraca posortowaną listę nazw wszystkich zarejestrowanych detektorów."""
    return sorted(DETECTOR_REGISTRY.keys())
