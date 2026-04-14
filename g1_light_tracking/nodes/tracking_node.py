import time
from typing import Dict, List, Optional, Tuple
import rclpy
from rclpy.node import Node

from g1_light_tracking.msg import LocalizedTarget, TrackedTarget
from g1_light_tracking.utils.kalman_tracking import (
    TrackState,
    same_semantics,
    distance_3d,
    distance_uv,
    bbox_iou,
    bbox_center_jump,
    init_kalman_state,
    predict_kalman,
    update_kalman,
)
from g1_light_tracking.utils.motion_compensation import SwayCompensator


class TrackingNode(Node):
    def __init__(self):
        super().__init__('tracking_node')
        self.declare_parameter('localized_topic', '/localization/targets')
        self.declare_parameter('tracked_topic', '/tracking/targets')
        self.declare_parameter('association_distance_m', 0.75)
        self.declare_parameter('association_uv_px', 75.0)
        self.declare_parameter('ema_alpha', 0.30)
        self.declare_parameter('max_missed_frames', 8)
        self.declare_parameter('min_confirmed_hits', 3)
        self.declare_parameter('kalman_target_types', ['person', 'parcel_box', 'shelf'])
        self.declare_parameter('process_noise_pos', 1.0e-2)
        self.declare_parameter('process_noise_vel', 5.0e-2)
        self.declare_parameter('measurement_noise_pos', 8.0e-2)
        self.declare_parameter('publish_unconfirmed', False)
        self.declare_parameter('reject_low_confidence_before_hits', 2)
        self.declare_parameter('min_confidence_default', 0.45)
        self.declare_parameter('min_confidence_person', 0.55)
        self.declare_parameter('min_confidence_parcel_box', 0.50)
        self.declare_parameter('min_confidence_shelf', 0.45)
        self.declare_parameter('min_confidence_qr', 0.80)
        self.declare_parameter('min_confidence_apriltag', 0.80)
        self.declare_parameter('min_confidence_light_spot', 0.95)
        self.declare_parameter('bbox_iou_gate', 0.10)
        self.declare_parameter('max_bbox_center_jump_px', 110.0)
        self.declare_parameter('stale_unconfirmed_purge_hits', 1)
        self.declare_parameter('enable_sway_compensation', True)
        self.declare_parameter('sway_uv_alpha', 0.20)
        self.declare_parameter('max_sway_shift_px', 45.0)
        self.declare_parameter('use_bbox_center_median_shift', True)
        self.declare_parameter('ignore_sway_for_marker_types', ['qr', 'apriltag'])

        self.association_distance_m = float(self.get_parameter('association_distance_m').value)
        self.association_uv_px = float(self.get_parameter('association_uv_px').value)
        self.ema_alpha = float(self.get_parameter('ema_alpha').value)
        self.max_missed_frames = int(self.get_parameter('max_missed_frames').value)
        self.min_confirmed_hits = int(self.get_parameter('min_confirmed_hits').value)
        self.kalman_target_types = set(self.get_parameter('kalman_target_types').value)
        self.process_noise_pos = float(self.get_parameter('process_noise_pos').value)
        self.process_noise_vel = float(self.get_parameter('process_noise_vel').value)
        self.measurement_noise_pos = float(self.get_parameter('measurement_noise_pos').value)
        self.publish_unconfirmed = bool(self.get_parameter('publish_unconfirmed').value)
        self.reject_low_confidence_before_hits = int(self.get_parameter('reject_low_confidence_before_hits').value)
        self.bbox_iou_gate = float(self.get_parameter('bbox_iou_gate').value)
        self.max_bbox_center_jump_px = float(self.get_parameter('max_bbox_center_jump_px').value)
        self.stale_unconfirmed_purge_hits = int(self.get_parameter('stale_unconfirmed_purge_hits').value)
        self.enable_sway_compensation = bool(self.get_parameter('enable_sway_compensation').value)
        self.use_bbox_center_median_shift = bool(self.get_parameter('use_bbox_center_median_shift').value)
        self.ignore_sway_for_marker_types = set(self.get_parameter('ignore_sway_for_marker_types').value)

        self.pub = self.create_publisher(TrackedTarget, self.get_parameter('tracked_topic').value, 50)
        self.create_subscription(LocalizedTarget, self.get_parameter('localized_topic').value, self.target_cb, 50)

        self.tracks: Dict[str, TrackState] = {}
        self.next_id = 1
        self.last_cleanup_time = time.time()
        self.sway = SwayCompensator(
            alpha=float(self.get_parameter('sway_uv_alpha').value),
            max_shift_px=float(self.get_parameter('max_sway_shift_px').value),
        )
        self.last_shift = (0.0, 0.0)

    def confidence_threshold(self, target_type: str) -> float:
        specific_map = {
            'person': float(self.get_parameter('min_confidence_person').value),
            'parcel_box': float(self.get_parameter('min_confidence_parcel_box').value),
            'shelf': float(self.get_parameter('min_confidence_shelf').value),
            'qr': float(self.get_parameter('min_confidence_qr').value),
            'apriltag': float(self.get_parameter('min_confidence_apriltag').value),
            'light_spot': float(self.get_parameter('min_confidence_light_spot').value),
        }
        return specific_map.get(target_type, float(self.get_parameter('min_confidence_default').value))

    def target_cb(self, msg: LocalizedTarget):
        if float(msg.confidence) < self.confidence_threshold(msg.target_type):
            return

        now = time.time()
        self.predict_and_age_tracks(now)

        comp = self.prepare_compensated_measurement(msg)
        track = self.match_track(comp)
        if track is None:
            track = self.create_track(comp, now)
        else:
            self.update_track(track, comp, now)

        if self.publish_unconfirmed or track.hits >= self.min_confirmed_hits:
            self.publish_track(track, msg)
        self.cleanup_tracks(now)

    def prepare_compensated_measurement(self, msg: LocalizedTarget) -> dict:
        u = float(msg.center_u)
        v = float(msg.center_v)
        x_min = float(msg.x_min)
        y_min = float(msg.y_min)
        x_max = float(msg.x_max)
        y_max = float(msg.y_max)

        shift_u, shift_v = self.estimate_sway_shift(msg)
        self.last_shift = (shift_u, shift_v)

        if self.enable_sway_compensation and msg.target_type not in self.ignore_sway_for_marker_types:
            u, v = self.sway.compensate_uv(u, v)
            x_min, y_min, x_max, y_max = self.sway.compensate_bbox(x_min, y_min, x_max, y_max)

        return {
            'msg': msg,
            'target_type': msg.target_type,
            'class_name': msg.class_name,
            'confidence': float(msg.confidence),
            'x': float(msg.position.x),
            'y': float(msg.position.y),
            'z': float(msg.position.z),
            'u': u,
            'v': v,
            'x_min': x_min,
            'y_min': y_min,
            'x_max': x_max,
            'y_max': y_max,
            'color_label': msg.color_label,
            'payload': msg.payload,
            'source_method': msg.source_method,
            'dimensions': msg.dimensions,
        }

    def estimate_sway_shift(self, msg: LocalizedTarget) -> Tuple[float, float]:
        if not self.enable_sway_compensation or not self.tracks or msg.target_type in self.ignore_sway_for_marker_types:
            return self.sway.update_from_deltas([])

        deltas = []
        current_cx = float((msg.x_min + msg.x_max) / 2.0)
        current_cy = float((msg.y_min + msg.y_max) / 2.0)

        for track in self.tracks.values():
            if not same_semantics(track, msg.target_type, msg.class_name):
                continue
            prev_cx = float((track.x_min + track.x_max) / 2.0)
            prev_cy = float((track.y_min + track.y_max) / 2.0)
            du = current_cx - prev_cx
            dv = current_cy - prev_cy
            deltas.append((du, dv))

        return self.sway.update_from_deltas(deltas if self.use_bbox_center_median_shift else [])

    def uses_kalman(self, target_type: str) -> bool:
        return target_type in self.kalman_target_types

    def predict_and_age_tracks(self, now: float):
        for track in self.tracks.values():
            dt = max(1.0 / 30.0, now - track.updated_time)
            if self.uses_kalman(track.target_type):
                predict_kalman(track, dt, self.process_noise_pos, self.process_noise_vel)
            track.missed_frames += 1

    def passes_bbox_gate(self, track: TrackState, comp: dict) -> bool:
        incoming_bbox = (comp['x_min'], comp['y_min'], comp['x_max'], comp['y_max'])
        current_bbox = track.bbox()
        iou = bbox_iou(current_bbox, incoming_bbox)
        jump = bbox_center_jump(track, *incoming_bbox)

        special_types = {'qr', 'apriltag', 'light_spot'}
        if comp['target_type'] in special_types:
            return jump <= self.max_bbox_center_jump_px
        return (iou >= self.bbox_iou_gate) or (jump <= self.max_bbox_center_jump_px)

    def match_track(self, comp: dict) -> Optional[TrackState]:
        candidates: List[Tuple[float, TrackState]] = []
        for track in self.tracks.values():
            if not same_semantics(track, comp['target_type'], comp['class_name']):
                continue
            if not self.passes_bbox_gate(track, comp):
                continue
            d3 = distance_3d(track, comp['x'], comp['y'], comp['z'])
            duv = distance_uv(track, comp['u'], comp['v'])
            if d3 <= self.association_distance_m or duv <= self.association_uv_px:
                score = d3 + 0.0025 * duv + 0.12 * track.missed_frames
                candidates.append((score, track))

        if not candidates:
            return None
        candidates.sort(key=lambda item: item[0])
        return candidates[0][1]

    def create_track(self, comp: dict, now: float) -> TrackState:
        track_id = f"{comp['target_type']}_{self.next_id:04d}"
        self.next_id += 1
        track = TrackState(
            track_id=track_id,
            target_type=comp['target_type'],
            class_name=comp['class_name'],
            x=comp['x'],
            y=comp['y'],
            z=comp['z'],
            center_u=comp['u'],
            center_v=comp['v'],
            x_min=comp['x_min'],
            y_min=comp['y_min'],
            x_max=comp['x_max'],
            y_max=comp['y_max'],
            confidence=comp['confidence'],
            color_label=comp['color_label'],
            payload=comp['payload'],
            source_method=comp['source_method'],
            hits=1,
            missed_frames=0,
            created_time=now,
            updated_time=now,
        )
        if self.uses_kalman(comp['target_type']):
            track.state, track.cov = init_kalman_state(track.x, track.y, track.z)
        self.tracks[track_id] = track
        return track

    def update_track(self, track: TrackState, comp: dict, now: float):
        if self.uses_kalman(track.target_type):
            update_kalman(track, comp['x'], comp['y'], comp['z'], self.measurement_noise_pos)
        else:
            a = self.ema_alpha
            track.x = (1.0 - a) * track.x + a * comp['x']
            track.y = (1.0 - a) * track.y + a * comp['y']
            track.z = (1.0 - a) * track.z + a * comp['z']

        a = self.ema_alpha
        track.center_u = (1.0 - a) * track.center_u + a * comp['u']
        track.center_v = (1.0 - a) * track.center_v + a * comp['v']
        track.x_min = (1.0 - a) * track.x_min + a * comp['x_min']
        track.y_min = (1.0 - a) * track.y_min + a * comp['y_min']
        track.x_max = (1.0 - a) * track.x_max + a * comp['x_max']
        track.y_max = (1.0 - a) * track.y_max + a * comp['y_max']

        track.confidence = max(track.confidence * 0.7, comp['confidence'])
        track.color_label = comp['color_label'] or track.color_label
        track.payload = comp['payload'] or track.payload
        track.source_method = comp['source_method'] or track.source_method
        track.class_name = comp['class_name'] or track.class_name
        track.missed_frames = 0
        track.hits += 1
        track.updated_time = now

    def publish_track(self, track: TrackState, src_msg: LocalizedTarget):
        out = TrackedTarget()
        out.stamp = src_msg.stamp
        out.frame_id = src_msg.frame_id
        out.track_id = track.track_id
        out.target_type = track.target_type
        out.class_name = track.class_name
        out.confidence = float(track.confidence)
        out.position.x = float(track.x)
        out.position.y = float(track.y)
        out.position.z = float(track.z)
        out.dimensions = src_msg.dimensions
        out.center_u = float(track.center_u)
        out.center_v = float(track.center_v)
        out.x_min = float(track.x_min)
        out.y_min = float(track.y_min)
        out.x_max = float(track.x_max)
        out.y_max = float(track.y_max)
        out.color_label = track.color_label
        out.payload = track.payload
        out.source_method = track.source_method
        out.age_sec = float(track.age_sec())
        out.missed_frames = int(track.missed_frames)
        out.is_confirmed = bool(track.hits >= self.min_confirmed_hits)
        self.pub.publish(out)

    def cleanup_tracks(self, now: float):
        if now - self.last_cleanup_time < 0.2:
            return
        to_delete = []
        for tid, tr in self.tracks.items():
            if tr.missed_frames > self.max_missed_frames:
                to_delete.append(tid)
                continue
            if tr.hits <= self.stale_unconfirmed_purge_hits and tr.missed_frames >= self.reject_low_confidence_before_hits:
                to_delete.append(tid)
                continue
            if tr.hits < self.min_confirmed_hits and tr.confidence < self.confidence_threshold(tr.target_type):
                if tr.missed_frames >= 1:
                    to_delete.append(tid)
        for tid in to_delete:
            self.tracks.pop(tid, None)
        self.last_cleanup_time = now


def main(args=None):
    rclpy.init(args=args)
    node = TrackingNode()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()
