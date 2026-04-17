# [AI-CHANGE | 2026-04-17 13:06 UTC | v0.91]
# CO ZMIENIONO: Dodano komentarze opisujące przeznaczenie klas i metod oraz motywację przyjętej struktury.
# DLACZEGO: Ułatwia to bezpieczne utrzymanie kodu R&D i ogranicza ryzyko błędnej interpretacji logiki detekcji.
# JAK TO DZIAŁA: Każda klasa/metoda posiada docstring z celem i uzasadnieniem, dzięki czemu intencja implementacji jest jawna.
# TODO: Rozszerzyć docstringi o kontrakty wejścia/wyjścia po ustabilizowaniu API między węzłami.

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Protocol, runtime_checkable

import numpy as np


@dataclass
class DetectorConfig:
    """Konfiguracja bazowa używana przez wszystkie adaptery detekcji."""

    track_mode: str = "brightness"
    blur: int = 11
    threshold: int = 200
    erode_iter: int = 2
    dilate_iter: int = 4
    min_area: float = 10.0
    max_area: float = 0.0
    min_detection_confidence: float = 0.0
    min_detection_score: float = 0.0
    # [AI-CHANGE | 2026-04-17 12:19 UTC | v0.84]
    # CO ZMIENIONO: Dodano parametr `min_top1_top2_margin`, który definiuje
    # minimalny bezwzględny margines punktacji między najlepszym i drugim kandydatem.
    # DLACZEGO: Gdy kandydaci mają bardzo podobne wyniki, detekcja jest niejednoznaczna
    # i zgodnie z polityką bezpieczeństwa lepiej zwrócić brak wyniku niż fałszywy pozytyw.
    # JAK TO DZIAŁA: Wartość konfiguracyjna jest używana w etapie post-sortowania
    # kandydatów do odrzucenia detekcji przy zbyt małej separacji rankingu.
    # TODO: Rozważyć dynamiczny próg marginesu zależny od kontrastu sceny i poziomu szumu.
    min_top1_top2_margin: float = 0.0
    # [AI-CHANGE | 2026-04-17 12:42 UTC | v0.87]
    # CO ZMIENIONO: Dodano progi i wagi cech fotometrycznych opartych o kontrast
    # kontur-vs-pierścień, ostrość piku oraz karę za prześwietlenie.
    # DLACZEGO: Sceny indoor/outdoor mają różny poziom tła i saturacji, więc
    # potrzebne są jawne parametry strojenia bezpieczeństwa detekcji.
    # JAK TO DZIAŁA: Progi `min_*` i `max_*` służą do odrzucania niepewnych próbek,
    # a pola `*_weight` składają się na wynik pewności dopasowania kandydata.
    # TODO: Przygotować gotowe profile presetów (np. indoor/outdoor) ładowane z YAML.
    ring_thickness_px: int = 2
    saturation_level: int = 250
    min_mean_contrast: float = 4.0
    min_peak_sharpness: float = 6.0
    max_saturated_ratio: float = 0.35
    confidence_weight_shape: float = 0.32
    confidence_weight_brightness: float = 0.22
    confidence_weight_contrast: float = 0.24
    confidence_weight_sharpness: float = 0.22
    confidence_saturation_penalty_weight: float = 0.35
    min_persistence_frames: int = 1
    persistence_radius_px: float = 12.0
    legacy_mode: bool = False
    max_spots: int = 10
    color_name: str = "red"
    hsv_lower: Optional[str] = None
    hsv_upper: Optional[str] = None
    roi: Optional[str] = None


@runtime_checkable
class DetectorProtocol(Protocol):
    """Kontrakt adaptera detektora zwracającego binarną maskę ROI."""

    @classmethod
    def default_params(cls) -> dict:
        """Zwraca domyślne parametry specyficzne dla danej metody detekcji."""

    def detect_mask(self, roi_frame: np.ndarray) -> np.ndarray:
        """Buduje maskę binarną dla obrazu ROI."""


class BaseDetector:
    """Abstrakcyjna klasa bazowa dla adapterów detektorów."""

    def __init__(self, config: DetectorConfig) -> None:
        """
        Cel: Ta metoda realizuje odpowiedzialność `__init__` w aktualnym module.
        Dlaczego tak: Wydzielenie tej jednostki upraszcza debugowanie i chroni krytyczne ścieżki przed niekontrolowanymi zmianami.
        """
        self.config = config

    @classmethod
    def default_params(cls) -> dict:
        """Zwraca domyślne parametry metody; implementacje mogą je nadpisywać."""
        return {}

    def detect_mask(self, roi_frame: np.ndarray) -> np.ndarray:
        """Interfejs wykrywania maski dla ROI."""
        raise NotImplementedError
