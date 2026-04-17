from __future__ import annotations

import math
from typing import Dict, List, Optional, Tuple, Type

import cv2
import numpy as np

from .detector_interfaces import BaseDetector, DetectorConfig
from .types import Detection


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

    def __init__(self, min_persistence_frames: int = 1, persistence_radius_px: float = 12.0) -> None:
        if min_persistence_frames <= 0:
            raise ValueError("min_persistence_frames musi być dodatnie.")
        if persistence_radius_px < 0:
            raise ValueError("persistence_radius_px nie może być ujemne.")
        self.min_persistence_frames = int(min_persistence_frames)
        self.persistence_radius_px = float(persistence_radius_px)
        self._frame_shape: Optional[Tuple[int, int]] = None
        self._roi_box: Optional[Tuple[int, int, int, int]] = None
        self._last_centroid: Optional[Tuple[float, float]] = None
        self._hit_count: int = 0

    def reset(self) -> None:
        self._frame_shape = None
        self._roi_box = None
        self._last_centroid = None
        self._hit_count = 0

    def _ensure_geometry(self, frame_shape: Tuple[int, int], roi_box: Tuple[int, int, int, int]) -> None:
        if self._frame_shape is not None and (self._frame_shape != frame_shape or self._roi_box != roi_box):
            self.reset()
        self._frame_shape = frame_shape
        self._roi_box = roi_box

    def apply(
        self,
        detections: List[Detection],
        frame_shape: Tuple[int, int, int],
        roi_box: Tuple[int, int, int, int],
    ) -> List[Detection]:
        if self.min_persistence_frames <= 1:
            return detections

        self._ensure_geometry((int(frame_shape[0]), int(frame_shape[1])), roi_box)
        if not detections:
            self._last_centroid = None
            self._hit_count = 0
            return []

        current = detections[0]
        current_centroid = (float(current.x), float(current.y))
        if self._last_centroid is None:
            self._last_centroid = current_centroid
            self._hit_count = 1
            return []

        dx = current_centroid[0] - self._last_centroid[0]
        dy = current_centroid[1] - self._last_centroid[1]
        if math.hypot(dx, dy) <= self.persistence_radius_px:
            self._hit_count += 1
        else:
            self._hit_count = 1
        self._last_centroid = current_centroid
        if self._hit_count < self.min_persistence_frames:
            return []
        return detections


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


def _compute_detection_confidence(
    contour: np.ndarray,
    detection: Detection,
    roi_frame: np.ndarray,
    area_reference: float,
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

    gray_roi = cv2.cvtColor(roi_frame, cv2.COLOR_BGR2GRAY)
    contour_mask = np.zeros(gray_roi.shape, dtype=np.uint8)
    cv2.drawContours(contour_mask, [contour], -1, color=255, thickness=-1)
    object_pixels = gray_roi[contour_mask > 0]
    mean_obj = float(np.mean(object_pixels)) if object_pixels.size else 0.0
    x, y, w, h = cv2.boundingRect(contour)
    patch = gray_roi[y : y + h, x : x + w]
    mean_patch = float(np.mean(patch)) if patch.size else mean_obj
    brightness_norm = _clip01(mean_obj / 255.0)
    contrast_norm = _clip01((mean_obj - mean_patch + 128.0) / 255.0)
    brightness_score = 0.6 * brightness_norm + 0.4 * contrast_norm

    ref_area = max(float(area_reference), 1.0)
    size_error = abs(float(detection.area) - ref_area) / ref_area
    size_stability_score = _clip01(1.0 - size_error)

    confidence = 0.45 * shape_score + 0.35 * brightness_score + 0.20 * size_stability_score
    return _clip01(confidence)


def _detection_score(det: Detection, peak_intensity: float, area_ref: float) -> float:
    area_norm = float(np.clip(det.area / max(area_ref, 1.0), 0.0, 1.0))
    circularity_norm = float(np.clip(det.circularity, 0.0, 1.0))
    peak_norm = float(np.clip(peak_intensity / 255.0, 0.0, 1.0))
    return (0.45 * area_norm) + (0.35 * circularity_norm) + (0.20 * peak_norm)


# [AI-CHANGE | 2026-04-17 11:50 UTC | v0.76]
# CO ZMIENIONO: Dodano strażnik `_is_ambiguous_top_detection`, który wykrywa sytuację
# niejednoznacznego wyboru lidera (dwie najlepsze detekcje o bardzo zbliżonym score).
# DLACZEGO: W scenach z refleksami lub wieloma podobnymi punktami detektor mógł zwrócić
# arbitralnie „pierwszy” kandydat, co zwiększa ryzyko fałszywego śledzenia.
# JAK TO DZIAŁA: Jeżeli różnica score pomiędzy TOP-1 i TOP-2 jest mniejsza od progu i
# kandydaci są rozdzieleni przestrzennie, wynik jest uznawany za niepewny.
# TODO: Rozbudować o wariant adaptacyjny progu niejednoznaczności zależny od dynamiki
# sceny (np. histogram jasności i liczba kandydatów w ROI).
def _is_ambiguous_top_detection(
    scored_detections: List[Tuple[float, Detection]],
    score_margin: float = 0.03,
    min_spatial_separation_px: float = 8.0,
) -> bool:
    if len(scored_detections) < 2:
        return False
    (best_score, best_det), (second_score, second_det) = scored_detections[0], scored_detections[1]
    if (best_score - second_score) > score_margin:
        return False
    dx = float(best_det.x - second_det.x)
    dy = float(best_det.y - second_det.y)
    return math.hypot(dx, dy) >= min_spatial_separation_px


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
    color_name: str,
    hsv_lower: Optional[str],
    hsv_upper: Optional[str],
    roi: Optional[str],
    legacy_mode: bool = False,
) -> Tuple[List[Detection], np.ndarray, Tuple[int, int, int, int]]:
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
        return detections, mask, (x0, y0, w, h)

    roi_gray = cv2.cvtColor(roi_frame, cv2.COLOR_BGR2GRAY)
    scored_detections: List[Tuple[float, Detection]] = []

    area_reference = float(np.median([det.area for det, _ in candidates])) if candidates else 0.0
    detections: List[Detection] = []
    for det, contour in candidates:
        peak_intensity = _contour_peak_intensity(roi_gray, contour)
        det.confidence = _compute_detection_confidence(
            contour=contour,
            detection=det,
            roi_frame=roi_frame,
            area_reference=area_reference,
        )
        if det.confidence < float(min_detection_confidence):
            continue
        score = _detection_score(
            det,
            peak_intensity=peak_intensity,
            area_ref=area_reference if area_reference > 0 else (max_area if max_area > 0 else (w * h)),
        )
        if score < float(min_detection_score):
            continue
        detections.append(det)
        scored_detections.append((score, det))

    scored_detections.sort(key=lambda item: item[0], reverse=True)

    # [AI-CHANGE | 2026-04-17 11:50 UTC | v0.76]
    # CO ZMIENIONO: Dodano odrzucenie całej paczki detekcji, gdy lider jest
    # niejednoznaczny względem drugiego kandydata.
    # DLACZEGO: Priorytetem projektu jest uniknięcie błędnej detekcji; przy remisie
    # jakościowym bezpieczniej zwrócić brak wyniku niż losowo wskazać obiekt.
    # JAK TO DZIAŁA: Po sortowaniu score uruchamiamy `_is_ambiguous_top_detection`.
    # Gdy zwróci `True`, funkcja oddaje pustą listę i maskę bez publikacji punktu.
    # TODO: Dodać metadane diagnostyczne (np. kod odrzucenia), aby łatwiej stroić
    # progi `score_margin` i `min_spatial_separation_px` na danych z produkcji.
    if _is_ambiguous_top_detection(scored_detections):
        return [], mask, (x0, y0, w, h)

    detections = [det for _, det in scored_detections]
    detections = detections[:max_spots]
    for idx, det in enumerate(detections, start=1):
        det.rank = idx

    return detections, mask, (x0, y0, w, h)


def detect_spots_with_config(
    frame: np.ndarray,
    config: DetectorConfig,
    persistence_filter: Optional[DetectionPersistenceFilter] = None,
):
    detections, mask, roi_box = detect_spots(
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
        legacy_mode=config.legacy_mode,
        color_name=config.color_name,
        hsv_lower=config.hsv_lower,
        hsv_upper=config.hsv_upper,
        roi=config.roi,
    )
    if persistence_filter is not None:
        detections = persistence_filter.apply(detections=detections, frame_shape=frame.shape, roi_box=roi_box)
    return detections, mask, roi_box
