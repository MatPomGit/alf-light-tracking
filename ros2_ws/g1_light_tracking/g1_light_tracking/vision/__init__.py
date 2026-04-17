from .detector_interfaces import BaseDetector, DetectorConfig
from .detectors import DetectionPersistenceFilter, detect_spots, detect_spots_with_config
# [AI-CHANGE | 2026-04-17 16:19 UTC | v0.122]
# CO ZMIENIONO: Zmieniono eksport `Detection` na import z `detection_types.py`.
# DLACZEGO: Publiczne API pakietu musi wskazywać na nową lokalizację klasy po
# usunięciu pliku `types.py`, który kolidował ze standardową biblioteką.
# JAK TO DZIAŁA: Import `from .vision import Detection` pozostaje stabilny, ale
# pod spodem korzysta już z bezpiecznego modułu bez konfliktu nazw.
# TODO: Dodać test publicznego API pakietu `vision`, aby pilnować kompatybilności eksportów.
from .detection_types import Detection

__all__ = [
    "BaseDetector",
    "Detection",
    "DetectionPersistenceFilter",
    "DetectorConfig",
    "detect_spots",
    "detect_spots_with_config",
]
