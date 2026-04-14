import time
from typing import Dict, Optional
import rclpy
from rclpy.node import Node

from g1_light_tracking.msg import TrackedTarget, ParcelTrackBinding
from g1_light_tracking.utils.association import BindingState, association_score


class AssociationNode(Node):
    def __init__(self):
        super().__init__('association_node')
        self.declare_parameter('tracked_topic', '/tracking/targets')
        self.declare_parameter('binding_topic', '/tracking/parcel_bindings')
        self.declare_parameter('max_qr_to_box_center_px', 140.0)
        self.declare_parameter('qr_inside_box_bonus', 0.35)
        self.declare_parameter('max_binding_age_sec', 3.0)
        self.declare_parameter('min_confirmed_matches', 2)

        self.max_qr_to_box_center_px = float(self.get_parameter('max_qr_to_box_center_px').value)
        self.qr_inside_box_bonus = float(self.get_parameter('qr_inside_box_bonus').value)
        self.max_binding_age_sec = float(self.get_parameter('max_binding_age_sec').value)
        self.min_confirmed_matches = int(self.get_parameter('min_confirmed_matches').value)

        self.pub = self.create_publisher(ParcelTrackBinding, self.get_parameter('binding_topic').value, 20)
        self.create_subscription(TrackedTarget, self.get_parameter('tracked_topic').value, self.cb, 100)

        self.qr_tracks: Dict[str, TrackedTarget] = {}
        self.box_tracks: Dict[str, TrackedTarget] = {}
        self.bindings: Dict[str, BindingState] = {}  # key: qr_track_id

    def cb(self, msg: TrackedTarget):
        now = time.time()
        if msg.target_type == 'qr':
            self.qr_tracks[msg.track_id] = msg
            self.try_bind_qr(msg, now)
        elif msg.target_type == 'parcel_box':
            self.box_tracks[msg.track_id] = msg
            self.try_rebind_all(now)

        self.cleanup(now)

    def try_bind_qr(self, qr_msg: TrackedTarget, now: float):
        best_box = None
        best_score = -1.0
        for box in self.box_tracks.values():
            box_bbox = self.estimate_box_bbox(box)
            score = association_score(
                qr_msg.center_u, qr_msg.center_v,
                box.center_u, box.center_v,
                box_bbox,
                self.max_qr_to_box_center_px,
                self.qr_inside_box_bonus
            )
            if score > best_score:
                best_score = score
                best_box = box

        if best_box is None or best_score < 0.0:
            return

        current = self.bindings.get(qr_msg.track_id)
        if current and current.parcel_box_track_id == best_box.track_id:
            current.hits += 1
            current.qr_payload = qr_msg.payload or current.qr_payload
            current.association_score = best_score
            current.last_update_time = now
            self.publish_binding(qr_msg, best_box.track_id, current)
            return

        self.bindings[qr_msg.track_id] = BindingState(
            qr_track_id=qr_msg.track_id,
            parcel_box_track_id=best_box.track_id,
            qr_payload=qr_msg.payload,
            association_score=best_score,
            hits=1,
            last_update_time=now,
        )
        self.publish_binding(qr_msg, best_box.track_id, self.bindings[qr_msg.track_id])

    def try_rebind_all(self, now: float):
        for qr in list(self.qr_tracks.values()):
            self.try_bind_qr(qr, now)

    def estimate_box_bbox(self, box_msg: TrackedTarget):
        return (
            float(box_msg.x_min),
            float(box_msg.y_min),
            float(box_msg.x_max),
            float(box_msg.y_max),
        )

    def publish_binding(self, qr_msg: TrackedTarget, parcel_box_track_id: str, binding: BindingState):
        out = ParcelTrackBinding()
        out.stamp = qr_msg.stamp
        out.qr_track_id = qr_msg.track_id
        out.parcel_box_track_id = parcel_box_track_id
        out.qr_payload = binding.qr_payload
        out.association_score = float(binding.association_score)
        out.is_confirmed = bool(binding.hits >= self.min_confirmed_matches)
        self.pub.publish(out)

    def cleanup(self, now: float):
        stale = [k for k, b in self.bindings.items() if (now - b.last_update_time) > self.max_binding_age_sec]
        for k in stale:
            del self.bindings[k]


def main(args=None):
    rclpy.init(args=args)
    node = AssociationNode()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()
