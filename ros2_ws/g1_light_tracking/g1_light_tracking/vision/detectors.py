from __future__ import annotations

import logging
import math
from typing import Dict, List, Optional, Tuple, Type

import cv2
import numpy as np

from .detector_interfaces import BaseDetector, DetectorConfig
from .types import Detection

# [AI-CHANGE | 2026-04-17 12:31 UTC | v0.85]
# CO ZMIENIONO: Wprowadzono logger modułowy i pamięć ostatniej konfiguracji
# (`_LAST_CONFIG_SNAPSHOT`) do wykrywania zmian parametrów pomiędzy wywołaniami.
# DLACZEGO: Pozwala to raportować zmiany strojenia bez ingerencji w API funkcji.
# JAK TO DZIAŁA: Snapshot ostatniej konfiguracji jest porównywany z bieżącym
# i aktualizowany po każdym wywołaniu adaptera konfiguracyjnego.
# TODO: Dodać możliwość całkowitego wyłączenia tych logów flagą środowiskową.
LOGGER = logging.getLogger(__name__)
_LAST_CONFIG_SNAPSHOT: Optional[Dict[str, float | int | str | bool | None]] = None


COLOR_PRESETS: Dict[str, List[Tuple[Tuple[int, int, int], Tuple[int, int, int]]]] = {
    "red": [((0, 80, 80), (10, 255, 255)), ((170, 80, 80), (180, 255, 255))],
    "green": [((35, 60, 60), (90, 255, 255))],
    "blue": [((90, 60, 60), (130, 255, 255))],
    "yellow": [((18, 80, 80), (40, 255, 255))],
    "white": [((0, 0, 180), (180, 60, 255))],
    "orange": [((8, 100, 80), (22, 255, 255))],
    "purple": [((130, 60, 60), (165, 255, 255))],
}


def parse_roi(roi_text: Optional[str], frame_shape: Tuple[int, int, int]) -> Tuple[int, int, int, int]:
    if not roi_text:
        h, w = frame_shape[:2]
        return 0, 0, w, h
    parts = [int(v) for v in roi_text.split(",")]
    if len(parts) != 4:
        raise ValueError("ROI musi mieć format x,y,w,h")
    x, y, w, h = parts
    H, W = frame_shape[:2]
    x = max(0, min(x, W - 1))
    y = max(0, min(y, H - 1))
    w = max(1, min(w, W - x))
    h = max(1, min(h, H - y))
    return x, y, w, h


def ensure_odd(value: int) -> int:
    return value if value % 2 == 1 else value + 1


def parse_hsv_pair(text: Optional[str], fallback: Tuple[int, int, int]) -> Tuple[int, int, int]:
    if not text:
        return fallback
    parts = [int(v.strip()) for v in text.split(",")]
    if len(parts) != 3:
        raise ValueError("Zakres HSV musi mieć 3 wartości: h,s,v")
    return tuple(parts)  # type: ignore


class BrightnessDetector(BaseDetector):
    @classmethod
    def default_params(cls) -> dict:
        return {
            "blur": 11,
            "threshold": 200,
            "erode_iter": 2,
            "dilate_iter": 4,
        }

    def detect_mask(self, roi_frame: np.ndarray) -> np.ndarray:
        blur = ensure_odd(self.config.blur)
        gray = cv2.cvtColor(roi_frame, cv2.COLOR_BGR2GRAY)
        blurred = cv2.GaussianBlur(gray, (blur, blur), 0)
        _, mask = cv2.threshold(blurred, self.config.threshold, 255, cv2.THRESH_BINARY)
        return _apply_morphology(mask, erode_iter=self.config.erode_iter, dilate_iter=self.config.dilate_iter)


class ColorDetector(BaseDetector):
    @classmethod
    def default_params(cls) -> dict:
        return {
            "blur": 11,
            "color_name": "red",
            "hsv_lower": None,
            "hsv_upper": None,
            "erode_iter": 2,
            "dilate_iter": 4,
        }

    def detect_mask(self, roi_frame: np.ndarray) -> np.ndarray:
        blur = ensure_odd(self.config.blur)
        hsv = cv2.cvtColor(roi_frame, cv2.COLOR_BGR2HSV)
        if self.config.color_name == "custom":
            lower = parse_hsv_pair(self.config.hsv_lower, (0, 80, 80))
            upper = parse_hsv_pair(self.config.hsv_upper, (10, 255, 255))
            ranges = [(lower, upper)]
        else:
            if self.config.color_name not in COLOR_PRESETS:
                raise ValueError(f"Nieznany preset koloru: {self.config.color_name}")
            ranges = COLOR_PRESETS[self.config.color_name]

        mask = np.zeros(hsv.shape[:2], dtype=np.uint8)
        for low, high in ranges:
            local = cv2.inRange(hsv, np.array(low, dtype=np.uint8), np.array(high, dtype=np.uint8))
            mask = cv2.bitwise_or(mask, local)
        if blur > 1:
            mask = cv2.GaussianBlur(mask, (blur, blur), 0)
            _, mask = cv2.threshold(mask, 127, 255, cv2.THRESH_BINARY)
        return _apply_morphology(mask, erode_iter=self.config.erode_iter, dilate_iter=self.config.dilate_iter)


def _apply_morphology(mask: np.ndarray, erode_iter: int, dilate_iter: int) -> np.ndarray:
    if erode_iter > 0:
        mask = cv2.erode(mask, None, iterations=erode_iter)
    if dilate_iter > 0:
        mask = cv2.dilate(mask, None, iterations=dilate_iter)
    return mask


class DetectionPersistenceFilter:
    """Lekki filtr stanowy potwierdzający detekcję dopiero po utrzymaniu w czasie."""

    def __init__(
        self,
        min_persistence_frames: int = 1,
        persistence_radius_px: float = 12.0,
        max_missed_frames: int = 1,
        association_cost_limit: float = 2.5,
    ) -> None:
        if min_persistence_frames <= 0:
            raise ValueError("min_persistence_frames musi być dodatnie.")
        if persistence_radius_px < 0:
            raise ValueError("persistence_radius_px nie może być ujemne.")
        if max_missed_frames < 0:
            raise ValueError("max_missed_frames nie może być ujemne.")
        if association_cost_limit <= 0:
            raise ValueError("association_cost_limit musi być dodatnie.")
        self.min_persistence_frames = int(min_persistence_frames)
        self.persistence_radius_px = float(persistence_radius_px)
        self.max_missed_frames = int(max_missed_frames)
        self.association_cost_limit = float(association_cost_limit)
        self._frame_shape: Optional[Tuple[int, int]] = None
        self._roi_box: Optional[Tuple[int, int, int, int]] = None
        self._last_centroid: Optional[Tuple[float, float]] = None
        self._last_area: Optional[float] = None
        self._last_brightness: Optional[float] = None
        self._hit_count: int = 0
        self._miss_count: int = 0

    def reset(self) -> None:
        self._frame_shape = None
        self._roi_box = None
        self._last_centroid = None
        self._last_area = None
        self._last_brightness = None
        self._hit_count = 0
        self._miss_count = 0

    def _ensure_geometry(self, frame_shape: Tuple[int, int], roi_box: Tuple[int, int, int, int]) -> None:
        if self._frame_shape is not None and (self._frame_shape != frame_shape or self._roi_box != roi_box):
            self.reset()
        self._frame_shape = frame_shape
        self._roi_box = roi_box

    def _handle_miss(self) -> List[Detection]:
        self._miss_count += 1
        self._hit_count = max(0, self._hit_count - 1)
        if self._miss_count > self.max_missed_frames:
            self.reset()
        return []

    def _detection_brightness(self, frame_gray: np.ndarray, detection: Detection) -> float:
        x0 = max(0, int(detection.bbox_x))
        y0 = max(0, int(detection.bbox_y))
        x1 = min(frame_gray.shape[1], int(detection.bbox_x + detection.bbox_w))
        y1 = min(frame_gray.shape[0], int(detection.bbox_y + detection.bbox_h))
        if x1 <= x0 or y1 <= y0:
            return 0.0
        patch = frame_gray[y0:y1, x0:x1]
        if patch.size == 0:
            return 0.0
        return float(np.mean(patch))

    def _association_cost(
        self,
        candidate: Detection,
        candidate_brightness: float,
        missed_frames: int,
    ) -> float:
        if self._last_centroid is None or self._last_area is None or self._last_brightness is None:
            return float("inf")
        dx = float(candidate.x) - self._last_centroid[0]
        dy = float(candidate.y) - self._last_centroid[1]
        miss_radius_boost = min(1.0, 0.25 * float(missed_frames))
        allowed_radius = max(1.0, self.persistence_radius_px * (1.0 + miss_radius_boost))
        distance_cost = math.hypot(dx, dy) / allowed_radius
        area_cost = abs(float(candidate.area) - self._last_area) / max(self._last_area, 1.0)
        brightness_cost = abs(candidate_brightness - self._last_brightness) / 255.0
        return (0.60 * distance_cost) + (0.25 * area_cost) + (0.15 * brightness_cost)

    def apply(
        self,
        detections: List[Detection],
        frame: np.ndarray,
        roi_box: Tuple[int, int, int, int],
    ) -> List[Detection]:
        # [AI-CHANGE | 2026-04-17 18:36 UTC | v0.82]
        # CO ZMIENIONO: Filtr asocjuje pełną listę kandydatów względem poprzedniego
        # toru i wybiera detekcję o najmniejszym koszcie (dystans + różnica pola +
        # różnica jasności), zamiast brać pierwszy element listy.
        # DLACZEGO: Wybór pierwszego kandydata był podatny na pomyłki rankingowe.
        # Asocjacja kosztowa stabilizuje tor i ogranicza skoki między obiektami.
        # JAK TO DZIAŁA: Dla każdego kandydata liczony jest koszt znormalizowany
        # do geometrii poprzedniego kroku. Kandydat jest akceptowany tylko gdy koszt
        # <= `association_cost_limit`. Gdy brak dopasowania, filtr zwraca pusty wynik,
        # zgodnie z zasadą bezpieczeństwa „lepiej brak niż błędna detekcja”.
        # TODO: Rozszerzyć koszt o predykcję ruchu (np. prosty model prędkości),
        # aby poprawić asocjację przy szybkich manewrach obiektu.
        if frame.ndim < 2:
            raise ValueError("frame musi mieć co najmniej 2 wymiary.")

        self._ensure_geometry((int(frame.shape[0]), int(frame.shape[1])), roi_box)
        if not detections:
            return self._handle_miss()

        frame_gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        brightness_cache: List[Tuple[Detection, float]] = [
            (candidate, self._detection_brightness(frame_gray=frame_gray, detection=candidate))
            for candidate in detections
        ]

        if self._last_centroid is None or self._last_area is None or self._last_brightness is None:
            init_candidate, init_brightness = max(brightness_cache, key=lambda item: item[0].confidence)
            self._last_centroid = (float(init_candidate.x), float(init_candidate.y))
            self._last_area = float(init_candidate.area)
            self._last_brightness = float(init_brightness)
            self._miss_count = 0
            self._hit_count = 1
            if self._hit_count < self.min_persistence_frames:
                return []
            return [init_candidate]

        missed_frames = self._miss_count
        best_candidate: Optional[Detection] = None
        best_brightness: float = 0.0
        best_cost = float("inf")
        for candidate, candidate_brightness in brightness_cache:
            cost = self._association_cost(
                candidate=candidate,
                candidate_brightness=candidate_brightness,
                missed_frames=missed_frames,
            )
            if cost < best_cost:
                best_cost = cost
                best_candidate = candidate
                best_brightness = candidate_brightness

        if best_candidate is None or best_cost > self.association_cost_limit:
            return self._handle_miss()

        self._miss_count = 0
        self._hit_count += 1
        self._last_centroid = (float(best_candidate.x), float(best_candidate.y))
        self._last_area = float(best_candidate.area)
        self._last_brightness = float(best_brightness)
        if self._hit_count < self.min_persistence_frames:
            return []
        return [best_candidate]


def _resolve_detector_class(track_mode: str) -> Type[BaseDetector]:
    from .detector_registry import get_detector_class

    normalized_mode = "brightness" if track_mode == "brightest" else track_mode
    return get_detector_class(normalized_mode)


def contour_to_detection(contour: np.ndarray, offset_x: int = 0, offset_y: int = 0) -> Optional[Detection]:
    area = float(cv2.contourArea(contour))
    if area <= 0:
        return None
    perimeter = float(cv2.arcLength(contour, True))
    moments = cv2.moments(contour)
    if moments["m00"] == 0:
        return None

    x = float(moments["m10"] / moments["m00"]) + offset_x
    y = float(moments["m01"] / moments["m00"]) + offset_y
    circ = float(4.0 * math.pi * area / (perimeter * perimeter)) if perimeter > 0 else 0.0
    (_, _), radius = cv2.minEnclosingCircle(contour)
    bx, by, bw, bh = cv2.boundingRect(contour)
    ellipse_center: Optional[Tuple[float, float]] = None
    ellipse_axes: Optional[Tuple[float, float]] = None
    ellipse_angle: Optional[float] = None
    if len(contour) >= 5:
        (ecx, ecy), (axis_a, axis_b), angle = cv2.fitEllipse(contour)
        ellipse_center = (float(ecx + offset_x), float(ecy + offset_y))
        ellipse_axes = (float(axis_a), float(axis_b))
        ellipse_angle = float(angle)
    return Detection(
        x=x,
        y=y,
        area=area,
        perimeter=perimeter,
        circularity=circ,
        radius=float(radius),
        bbox_x=bx + offset_x,
        bbox_y=by + offset_y,
        bbox_w=bw,
        bbox_h=bh,
        confidence=0.0,
        ellipse_center=ellipse_center,
        ellipse_axes=ellipse_axes,
        ellipse_angle=ellipse_angle,
    )


def _clip01(value: float) -> float:
    return float(max(0.0, min(1.0, value)))


def _contour_peak_intensity(gray_roi: np.ndarray, contour: np.ndarray) -> float:
    local_mask = np.zeros(gray_roi.shape, dtype=np.uint8)
    cv2.drawContours(local_mask, [contour], contourIdx=-1, color=255, thickness=-1)
    _, max_val, _, _ = cv2.minMaxLoc(gray_roi, mask=local_mask)
    return float(max_val)


def _contour_solidity(contour: np.ndarray, contour_area: float) -> float:
    hull = cv2.convexHull(contour)
    hull_area = float(cv2.contourArea(hull))
    if hull_area <= 0:
        return 0.0
    return float(contour_area / hull_area)


# [AI-CHANGE | 2026-04-17 12:42 UTC | v0.87]
# CO ZMIENIONO: Dodano helper normalizujący dodatnie wagi cech do sumy 1.0.
# DLACZEGO: Przy strojeniu indoor/outdoor użytkownik może podać dowolne skale wag;
# normalizacja utrzymuje stabilną interpretację confidence niezależnie od skali.
# JAK TO DZIAŁA: Wagi ujemne są obcinane do zera, a przy sumie <= 0 zwracany jest
# rozkład równy między wszystkie cechy.
# TODO: Dodać ostrzeżenie diagnostyczne, gdy wejściowe wagi wymagają korekty.
def _normalize_weights(*weights: float) -> List[float]:
    positive_weights = [max(0.0, float(weight)) for weight in weights]
    total = sum(positive_weights)
    if total <= 0.0:
        return [1.0 / len(positive_weights)] * len(positive_weights)
    return [weight / total for weight in positive_weights]


# [AI-CHANGE | 2026-04-17 12:42 UTC | v0.87]
# CO ZMIENIONO: Dodano ekstrakcję cech intensywności dla konturu oraz cienkiego
# pierścienia tła (`dylatacja(maski) - maska`) wokół obiektu.
# DLACZEGO: Średnia z patcha bounding box rozmywa kontrast; cecha ring-based lepiej
# separuje obiekt od lokalnego tła i pozwala bezpiecznie odrzucać niepewne próbki.
# JAK TO DZIAŁA: Funkcja liczy `mean_inside`, `mean_ring`, kontrast różnicowy,
# ostrość piku (P95 inside - P95 ring) i udział pikseli blisko saturacji.
# Brak pierścienia lub brak pikseli wewnątrz skutkuje `None`, aby preferować brak
# wyniku zamiast potencjalnie błędnej detekcji.
# TODO: Dodać adaptacyjną grubość pierścienia zależną od pola konturu i rozdzielczości.
def _contour_intensity_features(
    gray_roi: np.ndarray,
    contour: np.ndarray,
    ring_thickness_px: int,
    saturation_level: int,
) -> Optional[Dict[str, float]]:
    contour_mask = np.zeros(gray_roi.shape, dtype=np.uint8)
    cv2.drawContours(contour_mask, [contour], -1, color=255, thickness=-1)
    inside_pixels = gray_roi[contour_mask > 0]
    if inside_pixels.size == 0:
        return None

    thickness = max(1, int(ring_thickness_px))
    kernel_size = max(3, (2 * thickness) + 1)
    ring_kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (kernel_size, kernel_size))
    dilated_mask = cv2.dilate(contour_mask, ring_kernel, iterations=1)
    ring_mask = cv2.subtract(dilated_mask, contour_mask)
    ring_pixels = gray_roi[ring_mask > 0]
    if ring_pixels.size == 0:
        return None

    mean_inside = float(np.mean(inside_pixels))
    mean_ring = float(np.mean(ring_pixels))
    p95_inside = float(np.percentile(inside_pixels, 95))
    p95_ring = float(np.percentile(ring_pixels, 95))
    clipped_saturation_level = int(max(1, min(255, saturation_level)))
    saturated_ratio = float(np.mean(inside_pixels >= clipped_saturation_level))

    return {
        "mean_inside": mean_inside,
        "mean_ring": mean_ring,
        "mean_contrast": mean_inside - mean_ring,
        "peak_sharpness": p95_inside - p95_ring,
        "saturated_ratio": saturated_ratio,
    }


def _compute_detection_confidence(
    contour: np.ndarray,
    detection: Detection,
    area_reference: float,
    intensity_features: Dict[str, float],
    config: DetectorConfig,
) -> float:
    circularity_score = _clip01(detection.circularity)
    axis_ratio_score = 1.0
    if detection.ellipse_axes and min(detection.ellipse_axes) > 0:
        major_axis = max(detection.ellipse_axes)
        minor_axis = min(detection.ellipse_axes)
        axis_ratio = major_axis / minor_axis
        axis_ratio_score = _clip01(1.0 / axis_ratio)
    solidity_score = _clip01(_contour_solidity(contour, detection.area))
    shape_score = 0.55 * circularity_score + 0.25 * axis_ratio_score + 0.20 * solidity_score

    brightness_norm = _clip01(float(intensity_features["mean_inside"]) / 255.0)
    contrast_norm = _clip01((float(intensity_features["mean_contrast"]) + 64.0) / 128.0)
    sharpness_norm = _clip01((float(intensity_features["peak_sharpness"]) + 32.0) / 128.0)
    saturation_penalty = _clip01(float(intensity_features["saturated_ratio"]))

    ref_area = max(float(area_reference), 1.0)
    size_error = abs(float(detection.area) - ref_area) / ref_area
    size_stability_score = _clip01(1.0 - size_error)

    # [AI-CHANGE | 2026-04-17 12:42 UTC | v0.87]
    # CO ZMIENIONO: Zmieniono agregację confidence na ważoną kombinację cech:
    # kształt + jasność + kontrast ring-based + ostrość piku oraz karę saturacji.
    # DLACZEGO: Nowe cechy lepiej odróżniają wiarygodny hotspot od tła i refleksów.
    # JAK TO DZIAŁA: Wagi są konfigurowalne i normalizowane; kara za prześwietlenie
    # jest odejmowana od wyniku końcowego. Wynik jest zawsze klamrowany do [0, 1].
    # TODO: Rozważyć osobną normalizację cech dla kamer HDR i 8-bit LDR.
    w_shape, w_brightness, w_contrast, w_sharpness = _normalize_weights(
        float(config.confidence_weight_shape),
        float(config.confidence_weight_brightness),
        float(config.confidence_weight_contrast),
        float(config.confidence_weight_sharpness),
    )
    confidence = (
        (w_shape * shape_score)
        + (w_brightness * brightness_norm)
        + (w_contrast * contrast_norm)
        + (w_sharpness * sharpness_norm)
    )
    confidence = (0.85 * confidence) + (0.15 * size_stability_score)
    confidence -= float(config.confidence_saturation_penalty_weight) * saturation_penalty
    return _clip01(confidence)


def _detection_score(
    det: Detection,
    peak_intensity: float,
    area_ref: float,
    intensity_features: Dict[str, float],
) -> float:
    area_norm = float(np.clip(det.area / max(area_ref, 1.0), 0.0, 1.0))
    circularity_norm = float(np.clip(det.circularity, 0.0, 1.0))
    peak_norm = float(np.clip(peak_intensity / 255.0, 0.0, 1.0))
    contrast_norm = _clip01((float(intensity_features["mean_contrast"]) + 64.0) / 128.0)
    sharpness_norm = _clip01((float(intensity_features["peak_sharpness"]) + 32.0) / 128.0)
    saturation_penalty = _clip01(float(intensity_features["saturated_ratio"]))
    return (
        (0.30 * area_norm)
        + (0.20 * circularity_norm)
        + (0.15 * peak_norm)
        + (0.20 * contrast_norm)
        + (0.15 * sharpness_norm)
        - (0.20 * saturation_penalty)
    )


def _config_snapshot(config: DetectorConfig) -> Dict[str, float | int | str | bool | None]:
    # [AI-CHANGE | 2026-04-17 12:31 UTC | v0.85]
    # CO ZMIENIONO: Dodano normalizację `DetectorConfig` do słownika prymitywów.
    # DLACZEGO: Jednolita reprezentacja upraszcza porównanie parametrów i logowanie.
    # JAK TO DZIAŁA: Funkcja konwertuje pola konfiguracji do typów prostych
    # (`int`, `float`, `str`, `bool`, `None`) gotowych do porównania i serializacji.
    # TODO: Rozważyć automatyczne generowanie snapshotu z adnotacji dataclass.
    # [AI-CHANGE | 2026-04-17 12:42 UTC | v0.87]
    # CO ZMIENIONO: Rozszerzono snapshot o nowe progi i wagi cech ring-based.
    # DLACZEGO: Bez tych pól zmiany strojenia nie byłyby widoczne w logowaniu diffów.
    # JAK TO DZIAŁA: Każde nowe pole z `DetectorConfig` jest serializowane do typu
    # prostego i porównywane między kolejnymi wywołaniami.
    # TODO: Uzupełnić snapshot o wersję schematu konfiguracji.
    return {
        "track_mode": config.track_mode,
        "blur": int(config.blur),
        "threshold": int(config.threshold),
        "erode_iter": int(config.erode_iter),
        "dilate_iter": int(config.dilate_iter),
        "min_area": float(config.min_area),
        "max_area": float(config.max_area),
        "max_spots": int(config.max_spots),
        "min_detection_confidence": float(config.min_detection_confidence),
        "min_detection_score": float(config.min_detection_score),
        "min_top1_top2_margin": float(config.min_top1_top2_margin),
        "ring_thickness_px": int(config.ring_thickness_px),
        "saturation_level": int(config.saturation_level),
        "min_mean_contrast": float(config.min_mean_contrast),
        "min_peak_sharpness": float(config.min_peak_sharpness),
        "max_saturated_ratio": float(config.max_saturated_ratio),
        "confidence_weight_shape": float(config.confidence_weight_shape),
        "confidence_weight_brightness": float(config.confidence_weight_brightness),
        "confidence_weight_contrast": float(config.confidence_weight_contrast),
        "confidence_weight_sharpness": float(config.confidence_weight_sharpness),
        "confidence_saturation_penalty_weight": float(config.confidence_saturation_penalty_weight),
        "min_persistence_frames": int(config.min_persistence_frames),
        "persistence_radius_px": float(config.persistence_radius_px),
        "legacy_mode": bool(config.legacy_mode),
        "color_name": config.color_name,
        "hsv_lower": config.hsv_lower,
        "hsv_upper": config.hsv_upper,
        "roi": config.roi,
    }


def _log_parameter_changes(config: DetectorConfig) -> None:
    global _LAST_CONFIG_SNAPSHOT
    current_snapshot = _config_snapshot(config)
    if _LAST_CONFIG_SNAPSHOT is None:
        _LAST_CONFIG_SNAPSHOT = current_snapshot
        return
    changed_params = [
        (name, _LAST_CONFIG_SNAPSHOT[name], current_value)
        for name, current_value in current_snapshot.items()
        if _LAST_CONFIG_SNAPSHOT.get(name) != current_value
    ]
    # [AI-CHANGE | 2026-04-17 12:31 UTC | v0.85]
    # CO ZMIENIONO: Dodano logowanie zmian parametrów detektora pomiędzy kolejnymi
    # wywołaniami, bazujące na migawce konfiguracji.
    # DLACZEGO: Przy strojeniu online ważna jest szybka diagnoza, które parametry
    # zostały zmienione i jak wpływają na wynik detekcji.
    # JAK TO DZIAŁA: Funkcja porównuje bieżący snapshot z poprzednim i emituje log
    # `INFO` tylko dla różniących się pól, po czym aktualizuje snapshot referencyjny.
    # TODO: Zastąpić globalny snapshot cachem per-strumień kamery, gdy pipeline
    # będzie obsługiwać wiele źródeł obrazu równolegle.
    if changed_params:
        details = ", ".join([f"{name}: {old_value} -> {new_value}" for name, old_value, new_value in changed_params])
        LOGGER.info("DetectorConfig changed: %s", details)
    _LAST_CONFIG_SNAPSHOT = current_snapshot


def detect_spots(
    frame: np.ndarray,
    track_mode: str,
    blur: int,
    threshold: int,
    erode_iter: int,
    dilate_iter: int,
    min_area: float,
    max_area: float,
    max_spots: int,
    min_detection_confidence: float,
    min_detection_score: float,
    min_top1_top2_margin: float,
    ring_thickness_px: int,
    saturation_level: int,
    min_mean_contrast: float,
    min_peak_sharpness: float,
    max_saturated_ratio: float,
    confidence_weight_shape: float,
    confidence_weight_brightness: float,
    confidence_weight_contrast: float,
    confidence_weight_sharpness: float,
    confidence_saturation_penalty_weight: float,
    color_name: str,
    hsv_lower: Optional[str],
    hsv_upper: Optional[str],
    roi: Optional[str],
    legacy_mode: bool = False,
) -> Tuple[List[Detection], np.ndarray, Tuple[int, int, int, int], Dict[str, float | str | bool]]:
    # [AI-CHANGE | 2026-04-17 12:42 UTC | v0.87]
    # CO ZMIENIONO: Rozszerzono API funkcji o parametry progów i wag cech
    # fotometrycznych (kontrast ring-based, sharpness i kara saturacji).
    # DLACZEGO: Umożliwia to strojenie pracy detektora pod różne warunki oświetlenia.
    # JAK TO DZIAŁA: Parametry wejściowe są mapowane do `DetectorConfig`, a następnie
    # używane przez pipeline filtrowania kandydatów i obliczania confidence.
    # TODO: Rozważyć zastąpienie długiej listy argumentów wyłącznie obiektem config.
    x0, y0, w, h = parse_roi(roi, frame.shape)
    roi_frame = frame[y0 : y0 + h, x0 : x0 + w]
    detector_cls = _resolve_detector_class(track_mode)
    detector_config = DetectorConfig(
        track_mode=track_mode,
        blur=blur,
        threshold=threshold,
        erode_iter=erode_iter,
        dilate_iter=dilate_iter,
        color_name=color_name,
        hsv_lower=hsv_lower,
        hsv_upper=hsv_upper,
        ring_thickness_px=ring_thickness_px,
        saturation_level=saturation_level,
        min_mean_contrast=min_mean_contrast,
        min_peak_sharpness=min_peak_sharpness,
        max_saturated_ratio=max_saturated_ratio,
        confidence_weight_shape=confidence_weight_shape,
        confidence_weight_brightness=confidence_weight_brightness,
        confidence_weight_contrast=confidence_weight_contrast,
        confidence_weight_sharpness=confidence_weight_sharpness,
        confidence_saturation_penalty_weight=confidence_saturation_penalty_weight,
    )
    mask = detector_cls(detector_config).detect_mask(roi_frame)

    contours, _ = cv2.findContours(mask.copy(), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    candidates: List[Tuple[Detection, np.ndarray]] = []
    for contour in contours:
        det = contour_to_detection(contour, offset_x=x0, offset_y=y0)
        if det is None:
            continue
        if det.area < min_area:
            continue
        if max_area > 0 and det.area > max_area:
            continue
        candidates.append((det, contour))

    if legacy_mode:
        detections = [det for det, _ in candidates]
        detections.sort(key=lambda d: d.area, reverse=True)
        detections = detections[:max_spots]
        for idx, det in enumerate(detections, start=1):
            det.rank = idx
        return detections, mask, (x0, y0, w, h), {}

    roi_gray = cv2.cvtColor(roi_frame, cv2.COLOR_BGR2GRAY)
    scored_detections: List[Tuple[float, Detection]] = []

    area_reference = float(np.median([det.area for det, _ in candidates])) if candidates else 0.0
    detections: List[Detection] = []
    # [AI-CHANGE | 2026-04-17 12:42 UTC | v0.87]
    # CO ZMIENIONO: Dodano etap twardej walidacji fotometrycznej kandydatów na bazie
    # cech ring-based (kontrast średni, sharpness P95 i udział prześwietleń).
    # DLACZEGO: Polityka jakości wymaga odrzucania niepewnych pików zanim trafią do rankingu.
    # JAK TO DZIAŁA: Kandydat przechodzi dalej tylko gdy spełni wszystkie progi:
    # `mean_contrast >= min_mean_contrast`, `peak_sharpness >= min_peak_sharpness`
    # oraz `saturated_ratio <= max_saturated_ratio`.
    # TODO: Dodać licznik odrzuceń per-próg do diagnostyki strojenia outdoor.
    for det, contour in candidates:
        peak_intensity = _contour_peak_intensity(roi_gray, contour)
        intensity_features = _contour_intensity_features(
            gray_roi=roi_gray,
            contour=contour,
            ring_thickness_px=detector_config.ring_thickness_px,
            saturation_level=detector_config.saturation_level,
        )
        if intensity_features is None:
            continue
        if float(intensity_features["mean_contrast"]) < float(detector_config.min_mean_contrast):
            continue
        if float(intensity_features["peak_sharpness"]) < float(detector_config.min_peak_sharpness):
            continue
        if float(intensity_features["saturated_ratio"]) > float(detector_config.max_saturated_ratio):
            continue
        det.confidence = _compute_detection_confidence(
            contour=contour,
            detection=det,
            area_reference=area_reference,
            intensity_features=intensity_features,
            config=detector_config,
        )
        if det.confidence < float(min_detection_confidence):
            continue
        score = _detection_score(
            det,
            peak_intensity=peak_intensity,
            area_ref=area_reference if area_reference > 0 else (max_area if max_area > 0 else (w * h)),
            intensity_features=intensity_features,
        )
        if score < float(min_detection_score):
            continue
        detections.append(det)
        scored_detections.append((score, det))

    scored_detections.sort(key=lambda item: item[0], reverse=True)
    diagnostics: Dict[str, float | str | bool] = {}
    # [AI-CHANGE | 2026-04-17 12:19 UTC | v0.84]
    # CO ZMIENIONO: Dodano obliczanie marginesu `top1-top2` po sortowaniu ocen
    # kandydatów i warunek odrzucenia wyniku przy zbyt małej separacji.
    # DLACZEGO: Mały margines oznacza niejednoznaczność klasyfikacji; zgodnie
    # z zasadą jakości bezpieczniej zwrócić pusty wynik niż ryzykować błędną detekcję.
    # JAK TO DZIAŁA: Dla >=2 kandydatów liczony jest `top1_top2_margin` oraz
    # `top1_top2_margin_pct` (względem `best_score`). Jeżeli margines absolutny
    # jest mniejszy niż `min_top1_top2_margin`, funkcja zwraca `[]` i zapisuje
    # diagnostykę `rejection_reason=ambiguous_candidates`.
    # TODO: Dodać alternatywny próg względny (percentylowy), aby lepiej skalować
    # decyzję dla scen o różnych rozkładach jasności.
    if len(scored_detections) >= 2:
        best_score = float(scored_detections[0][0])
        second_score = float(scored_detections[1][0])
        top1_top2_margin = best_score - second_score
        top1_top2_margin_pct = (top1_top2_margin / best_score * 100.0) if best_score > 0.0 else 0.0
        diagnostics.update(
            {
                "top1_top2_margin": float(top1_top2_margin),
                "top1_top2_margin_pct": float(top1_top2_margin_pct),
                "min_top1_top2_margin": float(min_top1_top2_margin),
            }
        )
        if top1_top2_margin < float(min_top1_top2_margin):
            diagnostics["rejection_reason"] = "ambiguous_candidates"
            diagnostics["rejected"] = True
            return [], mask, (x0, y0, w, h), diagnostics

    detections = [det for _, det in scored_detections]
    detections = detections[:max_spots]
    for idx, det in enumerate(detections, start=1):
        det.rank = idx

    return detections, mask, (x0, y0, w, h), diagnostics


def detect_spots_with_config(
    frame: np.ndarray,
    config: DetectorConfig,
    persistence_filter: Optional[DetectionPersistenceFilter] = None,
):
    _log_parameter_changes(config)
    # [AI-CHANGE | 2026-04-17 12:19 UTC | v0.84]
    # CO ZMIENIONO: Adapter konfiguracyjny przekazuje nowy próg
    # `min_top1_top2_margin` oraz propaguje słownik diagnostyczny z detektora.
    # DLACZEGO: Node nadrzędny potrzebuje jawnej informacji o przyczynie odrzucenia,
    # aby logować przypadki niejednoznacznych kandydatów.
    # JAK TO DZIAŁA: Funkcja zwraca teraz 4 elementy (detekcje, maska, ROI, diagnostyka),
    # a parametry konfiguracji są mapowane 1:1 do `detect_spots`.
    # TODO: Ustabilizować kontrakt API przez dedykowaną klasę `DetectionDiagnostics`.
    detections, mask, roi_box, diagnostics = detect_spots(
        frame=frame,
        track_mode=config.track_mode,
        blur=config.blur,
        threshold=config.threshold,
        erode_iter=config.erode_iter,
        dilate_iter=config.dilate_iter,
        min_area=config.min_area,
        max_area=config.max_area,
        max_spots=config.max_spots,
        min_detection_confidence=config.min_detection_confidence,
        min_detection_score=config.min_detection_score,
        min_top1_top2_margin=config.min_top1_top2_margin,
        # [AI-CHANGE | 2026-04-17 12:42 UTC | v0.87]
        # CO ZMIENIONO: Adapter przekazuje do rdzenia detekcji nowe progi/wagi
        # związane z kontrastem kontur-vs-ring, sharpness i saturacją.
        # DLACZEGO: Brak propagacji uniemożliwiałby realne strojenie przez `DetectorConfig`.
        # JAK TO DZIAŁA: Pola konfiguracji są mapowane 1:1 do argumentów `detect_spots`.
        # TODO: Uprościć mapowanie przez przekazywanie całego obiektu config bez rozpakowywania.
        ring_thickness_px=config.ring_thickness_px,
        saturation_level=config.saturation_level,
        min_mean_contrast=config.min_mean_contrast,
        min_peak_sharpness=config.min_peak_sharpness,
        max_saturated_ratio=config.max_saturated_ratio,
        confidence_weight_shape=config.confidence_weight_shape,
        confidence_weight_brightness=config.confidence_weight_brightness,
        confidence_weight_contrast=config.confidence_weight_contrast,
        confidence_weight_sharpness=config.confidence_weight_sharpness,
        confidence_saturation_penalty_weight=config.confidence_saturation_penalty_weight,
        legacy_mode=config.legacy_mode,
        color_name=config.color_name,
        hsv_lower=config.hsv_lower,
        hsv_upper=config.hsv_upper,
        roi=config.roi,
    )
    if persistence_filter is not None:
        # [AI-CHANGE | 2026-04-17 18:36 UTC | v0.82]
        # CO ZMIENIONO: Przekazywana jest pełna lista kandydatów do filtra
        # persystencji, a po filtracji wynik jest redukowany do 0/1 detekcji.
        # DLACZEGO: Filtr musi mieć pełen kontekst kandydatów, aby wykonać
        # asocjację minimalnego kosztu i odrzucić niepewne dopasowania.
        # JAK TO DZIAŁA: `DetectionPersistenceFilter.apply` dostaje wszystkie
        # kandydatury i całą ramkę. Jeżeli nie ma bezpiecznego dopasowania,
        # zwraca `[]`; w przeciwnym razie pojedynczy wynik toru.
        # TODO: Dodać metrykę diagnostyczną (np. odsetek odrzuceń przez koszt),
        # aby szybciej stroić `association_cost_limit` na danych terenowych.
        detections = persistence_filter.apply(detections=detections, frame=frame, roi_box=roi_box)
        detections = detections[:1]
    return detections, mask, roi_box, diagnostics
