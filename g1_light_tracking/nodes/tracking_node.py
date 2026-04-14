import time
from typing import Dict, List, Optional, Tuple

import rclpy
from rclpy.node import Node
from cv_bridge import CvBridge
from sensor_msgs.msg import Image
from std_msgs.msg import String

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
from g1_light_tracking.utils.motion_compensation import GlobalMotionCompensator


class TrackingNode(Node):
    def __init__(self):
        super().__init__('tracking_node')
        self.bridge = CvBridge()

        self.declare_parameter('localized_topic', '/localization/targets')
        self.declare_parameter('tracked_topic', '/tracking/targets')
        self.declare_parameter('debug_motion_topic', '/tracking/global_motion_debug')
        self.declare_parameter('motion_source_topic', '/debug/calibration_preview')
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
        self.declare_parameter('enable_global_motion_compensation', True)
        self.declare_parameter('gmc_alpha', 0.25)
        self.declare_parameter('gmc_max_shift_px', 60.0)
        self.declare_parameter('gmc_max_corners', 250)
        self.declare_parameter('gmc_quality_level', 0.01)
        self.declare_parameter('gmc_min_distance', 8.0)
        self.declare_parameter('gmc_block_size', 7)
        self.declare_parameter('gmc_lk_win_size', 21)
        self.declare_parameter('gmc_lk_max_level', 3)
        self.declare_parameter('gmc_homography_ransac_thresh', 3.0)
        self.declare_parameter('ignore_gmc_for_marker_types', ['qr', 'apriltag'])

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
        self.enable_gmc = bool(self.get_parameter('enable_global_motion_compensation').value)
        self.ignore_gmc_for_marker_types = set(self.get_parameter('ignore_gmc_for_marker_types').value)

        self.pub = self.create_publisher(TrackedTarget, self.get_parameter('tracked_topic').value, 50)
        self.motion_pub = self.create_publisher(String, self.get_parameter('debug_motion_topic').value, 10)
        self.create_subscription(LocalizedTarget, self.get_parameter('localized_topic').value, self.target_cb, 50)
        self.create_subscription(Image, self.get_parameter('motion_source_topic').value, self.image_cb, 10)

        self.tracks: Dict[str, TrackState] = {}
        self.next_id = 1
        self.last_cleanup_time = time.time()
        self.gmc = GlobalMotionCompensator(
            max_corners=int(self.get_parameter('gmc_max_corners').value),
            quality_level=float(self.get_parameter('gmc_quality_level').value),
            min_distance=float(self.get_parameter('gmc_min_distance').value),
            block_size=int(self.get_parameter('gmc_block_size').value),
            lk_win_size=int(self.get_parameter('gmc_lk_win_size').value),
            lk_max_level=int(self.get_parameter('gmc_lk_max_level').value),
            homography_ransac_thresh=float(self.get_parameter('gmc_homography_ransac_thresh').value),
            alpha=float(self.get_parameter('gmc_alpha').value),
            max_shift_px=float(self.get_parameter('gmc_max_shift_px').value),
        )
        self.last_motion = None

    def image_cb(self, msg: Image):
        if not self.enable_gmc:
            return
        try:
            frame = self.bridge.imgmsg_to_cv2(msg, desired_encoding='bgr8')
            motion = self.gmc.update_from_frame(frame)
            self.last_motion = motion
            dbg = String()
            dbg.data = f"du={motion.shift_u:.2f};dv={motion.shift_v:.2f};conf={motion.confidence:.3f};homography={int(motion.used_homography)}"
            self.motion_pub.publish(dbg)
        except Exception:
            pass

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

        if self.enable_gmc and self.last_motion is not None and msg.target_type not in self.ignore_gmc_for_marker_types:
            u, v = self.gmc.compensate_uv(u, v)
            x_min, y_min, x_max, y_max = self.gmc.compensate_bbox(x_min, y_min, x_max, y_max)

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
