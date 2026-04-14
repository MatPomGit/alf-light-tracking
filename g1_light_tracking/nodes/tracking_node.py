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
    init_kalman_state,
    predict_kalman,
    update_kalman,
)


class TrackingNode(Node):
    def __init__(self):
        super().__init__('tracking_node')
        self.declare_parameter('localized_topic', '/localization/targets')
        self.declare_parameter('tracked_topic', '/tracking/targets')
        self.declare_parameter('association_distance_m', 1.00)
        self.declare_parameter('association_uv_px', 100.0)
        self.declare_parameter('ema_alpha', 0.35)
        self.declare_parameter('max_missed_frames', 10)
        self.declare_parameter('min_confirmed_hits', 2)
        self.declare_parameter('kalman_target_types', ['person', 'parcel_box', 'shelf'])
        self.declare_parameter('process_noise_pos', 1.0e-2)
        self.declare_parameter('process_noise_vel', 5.0e-2)
        self.declare_parameter('measurement_noise_pos', 8.0e-2)

        self.association_distance_m = float(self.get_parameter('association_distance_m').value)
        self.association_uv_px = float(self.get_parameter('association_uv_px').value)
        self.ema_alpha = float(self.get_parameter('ema_alpha').value)
        self.max_missed_frames = int(self.get_parameter('max_missed_frames').value)
        self.min_confirmed_hits = int(self.get_parameter('min_confirmed_hits').value)
        self.kalman_target_types = set(self.get_parameter('kalman_target_types').value)
        self.process_noise_pos = float(self.get_parameter('process_noise_pos').value)
        self.process_noise_vel = float(self.get_parameter('process_noise_vel').value)
        self.measurement_noise_pos = float(self.get_parameter('measurement_noise_pos').value)

        self.pub = self.create_publisher(TrackedTarget, self.get_parameter('tracked_topic').value, 50)
        self.create_subscription(LocalizedTarget, self.get_parameter('localized_topic').value, self.target_cb, 50)

        self.tracks: Dict[str, TrackState] = {}
        self.next_id = 1
        self.last_cleanup_time = time.time()

    def target_cb(self, msg: LocalizedTarget):
        now = time.time()
        self.predict_and_age_tracks(now)

        track = self.match_track(msg)
        if track is None:
            track = self.create_track(msg, now)
        else:
            self.update_track(track, msg, now)

        self.publish_track(track, msg)
        self.cleanup_tracks(now)

    def uses_kalman(self, target_type: str) -> bool:
        return target_type in self.kalman_target_types

    def predict_and_age_tracks(self, now: float):
        for track in self.tracks.values():
            dt = max(1.0 / 30.0, now - track.updated_time)
            if self.uses_kalman(track.target_type):
                predict_kalman(track, dt, self.process_noise_pos, self.process_noise_vel)
            track.missed_frames += 1

    def match_track(self, msg: LocalizedTarget) -> Optional[TrackState]:
        candidates: List[Tuple[float, TrackState]] = []
        x = float(msg.position.x)
        y = float(msg.position.y)
        z = float(msg.position.z)
        u = float(msg.center_u)
        v = float(msg.center_v)
        class_name = msg.class_name

        for track in self.tracks.values():
            if not same_semantics(track, msg.target_type, class_name):
                continue
            d3 = distance_3d(track, x, y, z)
            duv = distance_uv(track, u, v)
            if d3 <= self.association_distance_m or duv <= self.association_uv_px:
                score = d3 + 0.002 * duv + 0.1 * track.missed_frames
                candidates.append((score, track))

        if not candidates:
            return None
        candidates.sort(key=lambda item: item[0])
        return candidates[0][1]

    def create_track(self, msg: LocalizedTarget, now: float) -> TrackState:
        track_id = f'{msg.target_type}_{self.next_id:04d}'
        self.next_id += 1
        track = TrackState(
            track_id=track_id,
            target_type=msg.target_type,
            class_name=msg.class_name,
            x=float(msg.position.x),
            y=float(msg.position.y),
            z=float(msg.position.z),
            center_u=float(msg.center_u),
            center_v=float(msg.center_v),
            x_min=float(msg.x_min),
            y_min=float(msg.y_min),
            x_max=float(msg.x_max),
            y_max=float(msg.y_max),
            confidence=float(msg.confidence),
            color_label=msg.color_label,
            payload=msg.payload,
            source_method=msg.source_method,
            hits=1,
            missed_frames=0,
            created_time=now,
            updated_time=now,
        )
        if self.uses_kalman(msg.target_type):
            track.state, track.cov = init_kalman_state(track.x, track.y, track.z)
        self.tracks[track_id] = track
        return track

    def update_track(self, track: TrackState, msg: LocalizedTarget, now: float):
        meas_x = float(msg.position.x)
        meas_y = float(msg.position.y)
        meas_z = float(msg.position.z)

        if self.uses_kalman(track.target_type):
            update_kalman(track, meas_x, meas_y, meas_z, self.measurement_noise_pos)
        else:
            a = self.ema_alpha
            track.x = (1.0 - a) * track.x + a * meas_x
            track.y = (1.0 - a) * track.y + a * meas_y
            track.z = (1.0 - a) * track.z + a * meas_z

        a = self.ema_alpha
        track.center_u = (1.0 - a) * track.center_u + a * float(msg.center_u)
        track.center_v = (1.0 - a) * track.center_v + a * float(msg.center_v)
        track.x_min = (1.0 - a) * track.x_min + a * float(msg.x_min)
        track.y_min = (1.0 - a) * track.y_min + a * float(msg.y_min)
        track.x_max = (1.0 - a) * track.x_max + a * float(msg.x_max)
        track.y_max = (1.0 - a) * track.y_max + a * float(msg.y_max)

        track.confidence = max(track.confidence * 0.7, float(msg.confidence))
        track.color_label = msg.color_label or track.color_label
        track.payload = msg.payload or track.payload
        track.source_method = msg.source_method or track.source_method
        track.class_name = msg.class_name or track.class_name
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
        to_delete = [tid for tid, tr in self.tracks.items() if tr.missed_frames > self.max_missed_frames]
        for tid in to_delete:
            del self.tracks[tid]
        self.last_cleanup_time = now


def main(args=None):
    rclpy.init(args=args)
    node = TrackingNode()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()
