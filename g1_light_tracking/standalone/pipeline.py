from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
import time
import math

import cv2
import numpy as np

from g1_light_tracking.utils.geometry import dominant_color_bgr
from g1_light_tracking.utils.qr_schema import parse_parcel_qr
from g1_light_tracking.utils.association import association_score

try:
    from ultralytics import YOLO
except Exception:
    YOLO = None

try:
    from pyzbar.pyzbar import decode as decode_qr
except Exception:
    decode_qr = None

try:
    from pupil_apriltags import Detector as AprilTagDetector
except Exception:
    AprilTagDetector = None


@dataclass
class Detection:
    target_type: str
    class_name: str = ''
    confidence: float = 0.0
    bbox: Tuple[float, float, float, float] = (0, 0, 0, 0)
    center_u: float = 0.0
    center_v: float = 0.0
    color_label: str = ''
    payload: str = ''


@dataclass
class TrackedObject:
    track_id: str
    target_type: str
    class_name: str
    confidence: float
    bbox: Tuple[float, float, float, float]
    center_u: float
    center_v: float
    color_label: str = ''
    payload: str = ''
    hits: int = 1
    missed: int = 0
    updated_at: float = field(default_factory=time.time)


@dataclass
class ParcelTrackView:
    parcel_box_track_id: str
    qr_track_id: str = ''
    shipment_id: str = ''
    pickup_zone: str = ''
    dropoff_zone: str = ''
    parcel_type: str = ''
    mass_kg: float = 0.0
    confidence: float = 0.0
    bbox: Tuple[float, float, float, float] = (0, 0, 0, 0)
    logistics_state: str = 'box_detected'
    raw_payload: str = ''
    has_qr: bool = False


@dataclass
class FeatureFlags:
    enable_yolo: bool = True
    enable_qr: bool = True
    enable_apriltag: bool = True
    enable_light_spot: bool = True
    enable_tracking: bool = True
    enable_binding: bool = True


@dataclass
class RuntimeStatus:
    camera_open: bool
    yolo_loaded: bool
    qr_enabled: bool
    apriltag_enabled: bool
    light_spot_enabled: bool
    tracking_enabled: bool
    parcel_binding_enabled: bool
    gui_enabled: bool = False
    cli_enabled: bool = False
    model_path: str = ''
    active_functions: List[str] = field(default_factory=list)

    def as_lines(self) -> List[str]:
        return [
            f"Kamera: {'OK' if self.camera_open else 'BRAK'}",
            f"YOLO: {'AKTYWNY' if self.yolo_loaded else 'NIEDOSTEPNY'} ({self.model_path or '-'})",
            f"QR: {'AKTYWNY' if self.qr_enabled else 'NIEDOSTEPNY'}",
            f"AprilTag: {'AKTYWNY' if self.apriltag_enabled else 'NIEDOSTEPNY'}",
            f"Plamka swiatla: {'AKTYWNA' if self.light_spot_enabled else 'NIEAKTYWNA'}",
            f"Tracking: {'AKTYWNY' if self.tracking_enabled else 'NIEAKTYWNY'}",
            f"Wiazanie QR->karton: {'AKTYWNE' if self.parcel_binding_enabled else 'NIEAKTYWNE'}",
            f"Tryb CLI: {'TAK' if self.cli_enabled else 'NIE'}",
            f"Tryb GUI: {'TAK' if self.gui_enabled else 'NIE'}",
        ]


class PerceptionEngine:
    def __init__(self, model_path: str = 'yolov8n.pt', yolo_conf: float = 0.35, light_threshold: int = 240):
        self.model_path = model_path
        self.yolo_conf = yolo_conf
        self.light_threshold = light_threshold
        self.flags = FeatureFlags()
        self.model = None
        if YOLO is not None:
            try:
                self.model = YOLO(model_path)
            except Exception:
                self.model = None
        self.apriltag_detector = None
        if AprilTagDetector is not None:
            try:
                self.apriltag_detector = AprilTagDetector(families='tag36h11')
            except Exception:
                self.apriltag_detector = None

    def set_flag(self, name: str, value: bool) -> bool:
        if not hasattr(self.flags, name):
            return False
        setattr(self.flags, name, bool(value))
        return True

    def apply_profile(self, data: dict) -> dict:
        applied = {}
        for key, value in data.items():
            if hasattr(self.flags, key):
                setattr(self.flags, key, bool(value))
                applied[key] = bool(value)
        return applied

    def toggle_flag(self, name: str) -> Optional[bool]:
        if not hasattr(self.flags, name):
            return None
        new_value = not bool(getattr(self.flags, name))
        setattr(self.flags, name, new_value)
        return new_value

    def build_status(self, camera_open: bool, gui_enabled: bool = False, cli_enabled: bool = False) -> RuntimeStatus:
        active = []
        if camera_open:
            active.append('camera')
        if self.flags.enable_yolo and self.model is not None:
            active.append('yolo')
        if self.flags.enable_qr and decode_qr is not None:
            active.append('qr')
        if self.flags.enable_apriltag and self.apriltag_detector is not None:
            active.append('apriltag')
        if self.flags.enable_light_spot:
            active.append('light_spot')
        if self.flags.enable_tracking:
            active.append('tracking')
        if self.flags.enable_binding:
            active.append('parcel_binding')
        if gui_enabled:
            active.append('gui')
        if cli_enabled:
            active.append('cli')
        return RuntimeStatus(
            camera_open=camera_open,
            yolo_loaded=self.flags.enable_yolo and self.model is not None,
            qr_enabled=self.flags.enable_qr and decode_qr is not None,
            apriltag_enabled=self.flags.enable_apriltag and self.apriltag_detector is not None,
            light_spot_enabled=self.flags.enable_light_spot,
            tracking_enabled=self.flags.enable_tracking,
            parcel_binding_enabled=self.flags.enable_binding,
            gui_enabled=gui_enabled,
            cli_enabled=cli_enabled,
            model_path=self.model_path,
            active_functions=active,
        )

    def detect(self, frame: np.ndarray) -> List[Detection]:
        detections: List[Detection] = []
        if self.flags.enable_light_spot:
            light = self.detect_light_spot(frame)
            if light:
                detections.append(light)
        if self.flags.enable_qr:
            detections.extend(self.detect_qr(frame))
        if self.flags.enable_apriltag:
            detections.extend(self.detect_apriltag(frame))
        if self.flags.enable_yolo:
            detections.extend(self.detect_yolo(frame))
        return detections

    def detect_light_spot(self, frame: np.ndarray) -> Optional[Detection]:
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        _, mask = cv2.threshold(gray, self.light_threshold, 255, cv2.THRESH_BINARY)
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            return None
        contour = max(contours, key=cv2.contourArea)
        area = cv2.contourArea(contour)
        if area < 20.0:
            return None
        x, y, w, h = cv2.boundingRect(contour)
        roi = frame[y:y+h, x:x+w]
        return Detection(
            target_type='light_spot',
            confidence=1.0,
            bbox=(float(x), float(y), float(x + w), float(y + h)),
            center_u=float(x + w / 2.0),
            center_v=float(y + h / 2.0),
            color_label=dominant_color_bgr(roi),
        )

    def detect_qr(self, frame: np.ndarray) -> List[Detection]:
        out = []
        if decode_qr is None:
            return out
        try:
            decoded = decode_qr(frame)
            for item in decoded:
                rect = item.rect
                out.append(Detection(
                    target_type='qr',
                    confidence=1.0,
                    bbox=(float(rect.left), float(rect.top), float(rect.left + rect.width), float(rect.top + rect.height)),
                    center_u=float(rect.left + rect.width / 2.0),
                    center_v=float(rect.top + rect.height / 2.0),
                    payload=item.data.decode('utf-8', errors='ignore'),
                ))
        except Exception:
            pass
        return out

    def detect_apriltag(self, frame: np.ndarray) -> List[Detection]:
        out = []
        if self.apriltag_detector is None:
            return out
        try:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            tags = self.apriltag_detector.detect(gray)
            for tag in tags:
                pts = tag.corners
                xs = [float(p[0]) for p in pts]
                ys = [float(p[1]) for p in pts]
                out.append(Detection(
                    target_type='apriltag',
                    class_name='apriltag',
                    confidence=1.0,
                    bbox=(min(xs), min(ys), max(xs), max(ys)),
                    center_u=float(tag.center[0]),
                    center_v=float(tag.center[1]),
                    payload=f'tag_id={tag.tag_id}',
                ))
        except Exception:
            pass
        return out

    def detect_yolo(self, frame: np.ndarray) -> List[Detection]:
        out = []
        if self.model is None:
            return out
        try:
            results = self.model.predict(frame, conf=self.yolo_conf, verbose=False)
            if not results:
                return out
            result = results[0]
            if result.boxes is None:
                return out
            names = result.names
            for box in result.boxes:
                cls_id = int(box.cls[0].item())
                conf = float(box.conf[0].item())
                x1, y1, x2, y2 = [float(v) for v in box.xyxy[0].tolist()]
                class_name = str(names.get(cls_id, cls_id))
                semantic = class_name
                if class_name in {'box', 'package'}:
                    semantic = 'parcel_box'
                elif class_name in {'bookcase', 'shelf'}:
                    semantic = 'shelf'
                elif class_name == 'table':
                    semantic = 'planar_surface'
                out.append(Detection(
                    target_type=semantic,
                    class_name=class_name,
                    confidence=conf,
                    bbox=(x1, y1, x2, y2),
                    center_u=float((x1 + x2) / 2.0),
                    center_v=float((y1 + y2) / 2.0),
                ))
        except Exception:
            pass
        return out


class SimpleTracker:
    def __init__(self, max_dist_px: float = 120.0, max_missed: int = 10):
        self.max_dist_px = max_dist_px
        self.max_missed = max_missed
        self.tracks: Dict[str, TrackedObject] = {}
        self.next_id = 1

    def clear(self):
        self.tracks.clear()

    def update(self, detections: List[Detection], enabled: bool = True) -> List[TrackedObject]:
        if not enabled:
            self.clear()
            return [
                TrackedObject(
                    track_id=f"raw_{idx:04d}",
                    target_type=det.target_type,
                    class_name=det.class_name,
                    confidence=det.confidence,
                    bbox=det.bbox,
                    center_u=det.center_u,
                    center_v=det.center_v,
                    color_label=det.color_label,
                    payload=det.payload,
                    hits=1,
                    missed=0,
                )
                for idx, det in enumerate(detections, start=1)
            ]

        for tr in self.tracks.values():
            tr.missed += 1

        for det in detections:
            tr = self._match(det)
            if tr is None:
                track_id = f"{det.target_type}_{self.next_id:04d}"
                self.next_id += 1
                self.tracks[track_id] = TrackedObject(
                    track_id=track_id,
                    target_type=det.target_type,
                    class_name=det.class_name,
                    confidence=det.confidence,
                    bbox=det.bbox,
                    center_u=det.center_u,
                    center_v=det.center_v,
                    color_label=det.color_label,
                    payload=det.payload,
                    hits=1,
                    missed=0,
                    updated_at=time.time(),
                )
            else:
                a = 0.35
                tr.center_u = (1 - a) * tr.center_u + a * det.center_u
                tr.center_v = (1 - a) * tr.center_v + a * det.center_v
                tr.bbox = tuple((1 - a) * old + a * new for old, new in zip(tr.bbox, det.bbox))
                tr.confidence = max(tr.confidence * 0.7, det.confidence)
                tr.payload = det.payload or tr.payload
                tr.color_label = det.color_label or tr.color_label
                tr.class_name = det.class_name or tr.class_name
                tr.missed = 0
                tr.hits += 1
                tr.updated_at = time.time()

        stale = [k for k, tr in self.tracks.items() if tr.missed > self.max_missed]
        for k in stale:
            del self.tracks[k]
        return list(self.tracks.values())

    def _match(self, det: Detection) -> Optional[TrackedObject]:
        best = None
        best_dist = None
        for tr in self.tracks.values():
            if tr.target_type != det.target_type:
                continue
            d = math.sqrt((tr.center_u - det.center_u) ** 2 + (tr.center_v - det.center_v) ** 2)
            if d <= self.max_dist_px and (best_dist is None or d < best_dist):
                best = tr
                best_dist = d
        return best


class ParcelAggregator:
    def __init__(self, max_qr_to_box_center_px: float = 140.0, qr_inside_box_bonus: float = 0.35):
        self.max_qr_to_box_center_px = max_qr_to_box_center_px
        self.qr_inside_box_bonus = qr_inside_box_bonus

    def build(self, tracks: List[TrackedObject], enabled: bool = True) -> List[ParcelTrackView]:
        boxes = [t for t in tracks if t.target_type == 'parcel_box']
        qrs = [t for t in tracks if t.target_type == 'qr']
        parcel_tracks: List[ParcelTrackView] = []

        binding_by_box: Dict[str, TrackedObject] = {}
        if enabled:
            for qr in qrs:
                best_box = None
                best_score = -1.0
                for box in boxes:
                    score = association_score(
                        qr.center_u, qr.center_v,
                        box.center_u, box.center_v,
                        box.bbox,
                        self.max_qr_to_box_center_px,
                        self.qr_inside_box_bonus
                    )
                    if score > best_score:
                        best_score = score
                        best_box = box
                if best_box is not None and best_score >= 0.0:
                    binding_by_box[best_box.track_id] = qr

        for box in boxes:
            qr = binding_by_box.get(box.track_id)
            pt = ParcelTrackView(
                parcel_box_track_id=box.track_id,
                confidence=box.confidence,
                bbox=box.bbox,
                logistics_state='box_detected',
            )
            if qr is not None:
                pt.qr_track_id = qr.track_id
                pt.has_qr = True
                pt.raw_payload = qr.payload
                parsed = parse_parcel_qr(qr.payload)
                pt.shipment_id = str(parsed.get('shipment_id', ''))
                pt.pickup_zone = str(parsed.get('pickup_zone', ''))
                pt.dropoff_zone = str(parsed.get('dropoff_zone', ''))
                pt.parcel_type = str(parsed.get('parcel_type', ''))
                try:
                    pt.mass_kg = float(parsed.get('mass_kg', 0.0))
                except Exception:
                    pt.mass_kg = 0.0
                pt.logistics_state = 'identified' if qr.payload else 'qr_visible_unreadable'
            parcel_tracks.append(pt)

        return parcel_tracks


def summarize_functions(status: RuntimeStatus, detections: List[Detection], tracks: List[TrackedObject], parcel_tracks: List[ParcelTrackView]) -> List[str]:
    lines = []
    lines.extend(status.as_lines())
    lines.append(f"Detekcje biezace: {len(detections)}")
    lines.append(f"Tracki aktywne: {len(tracks)}")
    lines.append(f"ParcelTrack aktywne: {len(parcel_tracks)}")
    active_types = sorted({d.target_type for d in detections})
    lines.append("Typy obiektow w klatce: " + (", ".join(active_types) if active_types else "-"))
    return lines


def draw_overlay(frame: np.ndarray, tracks: List[TrackedObject], parcel_tracks: List[ParcelTrackView], state_text: str, status_lines: Optional[List[str]] = None, help_lines: Optional[List[str]] = None) -> np.ndarray:
    overlay = frame.copy()
    for tr in tracks:
        x1, y1, x2, y2 = map(int, tr.bbox)
        cv2.rectangle(overlay, (x1, y1), (x2, y2), (0, 255, 0), 2)
        label = f"{tr.track_id} {tr.target_type}"
        if tr.payload:
            label += f" {tr.payload[:24]}"
        if tr.color_label:
            label += f" {tr.color_label}"
        cv2.putText(overlay, label, (x1, max(20, y1 - 5)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)
    y = 25
    cv2.putText(overlay, f"state: {state_text}", (10, y), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
    y += 28
    for pt in parcel_tracks[:3]:
        txt = f"parcel {pt.parcel_box_track_id} qr={pt.qr_track_id} shipment={pt.shipment_id} state={pt.logistics_state}"
        cv2.putText(overlay, txt[:95], (10, y), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 0), 1)
        y += 22
    if status_lines:
        x = 10
        y = max(y + 12, 120)
        for line in status_lines[:12]:
            cv2.putText(overlay, line[:95], (x, y), cv2.FONT_HERSHEY_SIMPLEX, 0.48, (230, 230, 230), 1)
            y += 20
    if help_lines:
        x = 10
        y = y + 15 if status_lines else max(y + 15, 140)
        for line in help_lines[:12]:
            cv2.putText(overlay, line[:95], (x, y), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (180, 255, 180), 1)
            y += 18
    return overlay


@dataclass
class TopDownOdometry:
    x: float = 0.0
    y: float = 0.0
    yaw: float = 0.0
    path: List[Tuple[float, float]] = field(default_factory=lambda: [(0.0, 0.0)])

    def update_from_tracks(self, tracks: List[TrackedObject], dt: float = 0.05):
        # Uproszczona estymacja lokalnej odometrii do podglądu GUI.
        # Bazuje na aktywnym celu z przodu kadru: im większe odchylenie w bok, tym większy skręt.
        target = None
        for tr in tracks:
            if tr.target_type in ('parcel_box', 'person', 'shelf', 'light_spot'):
                target = tr
                break
        if target is None:
            return

        img_cx = 640.0 / 2.0
        norm_x = (target.center_u - img_cx) / img_cx
        turn_rate = float(max(-1.0, min(1.0, norm_x))) * 0.7
        forward = 0.02
        self.yaw += turn_rate * dt
        self.x += forward * math.cos(self.yaw)
        self.y += forward * math.sin(self.yaw)
        self.path.append((self.x, self.y))
        if len(self.path) > 500:
            self.path = self.path[-500:]


def draw_topdown(odom: TopDownOdometry, size: Tuple[int, int] = (420, 420)) -> np.ndarray:
    w, h = size
    img = np.zeros((h, w, 3), dtype=np.uint8)
    img[:] = (14, 20, 42)

    cv2.putText(img, 'Top-down odometry preview', (16, 26), cv2.FONT_HERSHEY_SIMPLEX, 0.62, (230, 230, 230), 1)
    cx, cy = w // 2, h // 2
    scale = 80.0

    cv2.line(img, (0, cy), (w, cy), (55, 70, 120), 1)
    cv2.line(img, (cx, 0), (cx, h), (55, 70, 120), 1)

    pts = []
    for px, py in odom.path:
        sx = int(cx + px * scale)
        sy = int(cy - py * scale)
        pts.append((sx, sy))
    for i in range(1, len(pts)):
        cv2.line(img, pts[i - 1], pts[i], (126, 231, 135), 2)

    robot_x = int(cx + odom.x * scale)
    robot_y = int(cy - odom.y * scale)
    cv2.circle(img, (robot_x, robot_y), 7, (110, 168, 254), -1)

    hx = int(robot_x + 20 * math.cos(odom.yaw))
    hy = int(robot_y - 20 * math.sin(odom.yaw))
    cv2.arrowedLine(img, (robot_x, robot_y), (hx, hy), (255, 209, 102), 2, tipLength=0.3)

    cv2.putText(img, f'x={odom.x:.2f} m', (16, h - 48), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (220, 220, 220), 1)
    cv2.putText(img, f'y={odom.y:.2f} m', (16, h - 28), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (220, 220, 220), 1)
    cv2.putText(img, f'yaw={odom.yaw:.2f} rad', (150, h - 28), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (220, 220, 220), 1)
    return img
