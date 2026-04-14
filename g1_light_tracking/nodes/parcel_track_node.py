import time
from typing import Dict, Optional
import rclpy
from rclpy.node import Node

from g1_light_tracking.msg import TrackedTarget, ParcelTrackBinding, ParcelTrack
from g1_light_tracking.utils.qr_schema import parse_parcel_qr


class ParcelTrackNode(Node):
    def __init__(self):
        super().__init__('parcel_track_node')
        self.declare_parameter('tracked_topic', '/tracking/targets')
        self.declare_parameter('binding_topic', '/tracking/parcel_bindings')
        self.declare_parameter('parcel_track_topic', '/tracking/parcel_tracks')
        self.declare_parameter('max_track_age_sec', 4.0)

        self.max_track_age_sec = float(self.get_parameter('max_track_age_sec').value)

        self.pub = self.create_publisher(ParcelTrack, self.get_parameter('parcel_track_topic').value, 20)
        self.create_subscription(TrackedTarget, self.get_parameter('tracked_topic').value, self.on_tracked, 100)
        self.create_subscription(ParcelTrackBinding, self.get_parameter('binding_topic').value, self.on_binding, 50)

        self.box_tracks: Dict[str, TrackedTarget] = {}
        self.qr_tracks: Dict[str, TrackedTarget] = {}
        self.bindings_by_box: Dict[str, ParcelTrackBinding] = {}
        self.updated_at: Dict[str, float] = {}

    def on_binding(self, msg: ParcelTrackBinding):
        self.bindings_by_box[msg.parcel_box_track_id] = msg
        self.updated_at[msg.parcel_box_track_id] = time.time()
        self.publish_if_possible(msg.parcel_box_track_id)

    def on_tracked(self, msg: TrackedTarget):
        now = time.time()
        if msg.target_type == 'parcel_box':
            self.box_tracks[msg.track_id] = msg
            self.updated_at[msg.track_id] = now
            self.publish_if_possible(msg.track_id)
        elif msg.target_type == 'qr':
            self.qr_tracks[msg.track_id] = msg
            self.publish_all_for_qr(msg.track_id)
        self.cleanup(now)

    def publish_all_for_qr(self, qr_track_id: str):
        for box_id, binding in list(self.bindings_by_box.items()):
            if binding.qr_track_id == qr_track_id:
                self.publish_if_possible(box_id)

    def publish_if_possible(self, parcel_box_track_id: str):
        box = self.box_tracks.get(parcel_box_track_id)
        if box is None:
            return

        binding = self.bindings_by_box.get(parcel_box_track_id)
        qr = self.qr_tracks.get(binding.qr_track_id) if binding else None

        msg = ParcelTrack()
        msg.stamp = box.stamp
        msg.frame_id = box.frame_id
        msg.parcel_box_track_id = box.track_id
        msg.position = box.position
        msg.dimensions = box.dimensions
        msg.confidence = box.confidence
        msg.source_method = box.source_method
        msg.logistics_state = self.infer_logistics_state(box, binding, qr)
        msg.is_confirmed = bool(box.is_confirmed and (binding.is_confirmed if binding else False))
        msg.has_qr = bool(binding is not None and qr is not None)

        if binding is not None:
            msg.qr_track_id = binding.qr_track_id

        raw_payload = ""
        if qr is not None and qr.payload:
            raw_payload = qr.payload
        elif binding is not None and binding.qr_payload:
            raw_payload = binding.qr_payload

        msg.raw_payload = raw_payload

        if raw_payload:
            parsed = parse_parcel_qr(raw_payload)
            msg.shipment_id = str(parsed.get('shipment_id', ''))
            msg.pickup_zone = str(parsed.get('pickup_zone', ''))
            msg.dropoff_zone = str(parsed.get('dropoff_zone', ''))
            msg.parcel_type = str(parsed.get('parcel_type', ''))
            try:
                msg.mass_kg = float(parsed.get('mass_kg', 0.0))
            except Exception:
                msg.mass_kg = 0.0

        self.pub.publish(msg)

    def infer_logistics_state(self, box: TrackedTarget, binding: Optional[ParcelTrackBinding], qr: Optional[TrackedTarget]) -> str:
        if box.target_type != 'parcel_box':
            return 'unknown'
        if binding is None:
            return 'box_detected'
        if binding is not None and not binding.is_confirmed:
            return 'binding_pending'
        if qr is None:
            return 'binding_confirmed_qr_not_visible'
        if qr.payload:
            return 'identified'
        return 'qr_visible_unreadable'

    def cleanup(self, now: float):
        stale_box_ids = [k for k, t in self.updated_at.items() if (now - t) > self.max_track_age_sec]
        for box_id in stale_box_ids:
            self.updated_at.pop(box_id, None)
            self.box_tracks.pop(box_id, None)
            self.bindings_by_box.pop(box_id, None)


def main(args=None):
    rclpy.init(args=args)
    node = ParcelTrackNode()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()
