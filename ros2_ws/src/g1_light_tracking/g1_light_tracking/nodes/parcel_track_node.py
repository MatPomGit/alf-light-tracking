"""ROS 2 node agregujący stan logistyczny przesyłki.

Node scala ogólne tracki obiektów z odczytami QR. Jego zadaniem jest przypisanie markera QR
do odpowiadającego mu kartonu, a następnie zbudowanie ustrukturyzowanego widoku przesyłki
(`ParcelTrack`) zawierającego identyfikator, strefy, typ przesyłki i bieżący stan procesu.

Moduł stanowi warstwę domenową ponad ogólnym trackingiem: zamiast abstrakcyjnych obiektów
robot otrzymuje już pojęcie konkretnej paczki i jej statusu.
"""

import time
from typing import Dict, Optional
import rclpy
from rclpy.node import Node

from g1_light_tracking.msg import TrackedTarget, ParcelTrackBinding, ParcelTrack
from g1_light_tracking.utils.qr_schema import parse_parcel_qr
from g1_light_tracking.utils.association import association_score


class BindingState:
    def __init__(self, qr_track_id: str, parcel_box_track_id: str, qr_payload: str, association_score_value: float):
        self.qr_track_id = qr_track_id
        self.parcel_box_track_id = parcel_box_track_id
        self.qr_payload = qr_payload
        self.association_score = association_score_value
        self.hits = 1
        self.last_update_time = time.time()


# TODO: Extend parcel binding with multi-hypothesis association so temporary
# occlusions or overlapping boxes do not immediately collapse a shipment match.
class ParcelTrackNode(Node):
    def __init__(self):
        super().__init__('parcel_track_node')
        self.declare_parameter('tracked_topic', '/tracking/targets')
        self.declare_parameter('binding_topic', '/tracking/parcel_bindings')
        self.declare_parameter('parcel_track_topic', '/tracking/parcel_tracks')
        self.declare_parameter('max_track_age_sec', 4.0)
        self.declare_parameter('max_qr_to_box_center_px', 140.0)
        self.declare_parameter('qr_inside_box_bonus', 0.35)
        self.declare_parameter('max_binding_age_sec', 3.0)
        # TODO: Read parcel identity priors from an external manifest or WMS feed
        # so shipment_id inference can be validated against operational data.
        self.declare_parameter('min_confirmed_matches', 2)

        self.max_track_age_sec = float(self.get_parameter('max_track_age_sec').value)
        self.max_qr_to_box_center_px = float(self.get_parameter('max_qr_to_box_center_px').value)
        self.qr_inside_box_bonus = float(self.get_parameter('qr_inside_box_bonus').value)
        self.max_binding_age_sec = float(self.get_parameter('max_binding_age_sec').value)
        self.min_confirmed_matches = int(self.get_parameter('min_confirmed_matches').value)

        self.binding_pub = self.create_publisher(ParcelTrackBinding, self.get_parameter('binding_topic').value, 20)
        self.parcel_pub = self.create_publisher(ParcelTrack, self.get_parameter('parcel_track_topic').value, 20)
        self.create_subscription(TrackedTarget, self.get_parameter('tracked_topic').value, self.on_tracked, 100)

        self.box_tracks: Dict[str, TrackedTarget] = {}
        self.qr_tracks: Dict[str, TrackedTarget] = {}
        self.bindings_by_qr: Dict[str, BindingState] = {}
        self.bindings_by_box: Dict[str, BindingState] = {}
        self.updated_at: Dict[str, float] = {}

    def on_tracked(self, msg: TrackedTarget):
        now = time.time()

        if msg.target_type == 'parcel_box':
            self.box_tracks[msg.track_id] = msg
            self.updated_at[msg.track_id] = now
            self.try_rebind_all(now)
            self.publish_if_possible(msg.track_id)
        elif msg.target_type == 'qr':
            self.qr_tracks[msg.track_id] = msg
            self.try_bind_qr(msg, now)
        else:
            return

        self.cleanup(now)

    def try_rebind_all(self, now: float):
        for qr in list(self.qr_tracks.values()):
            self.try_bind_qr(qr, now)

    def try_bind_qr(self, qr_msg: TrackedTarget, now: float):
        best_box = None
        best_score = -1.0
        for box in self.box_tracks.values():
            box_bbox = (float(box.x_min), float(box.y_min), float(box.x_max), float(box.y_max))
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

        # If the same QR keeps matching the same box, we strengthen the binding instead
        # of rebuilding it from scratch. This reduces flicker in logistics state outputs.
        current = self.bindings_by_qr.get(qr_msg.track_id)
        if current and current.parcel_box_track_id == best_box.track_id:
            current.hits += 1
            current.qr_payload = qr_msg.payload or current.qr_payload
            current.association_score = best_score
            current.last_update_time = now
            self.bindings_by_box[current.parcel_box_track_id] = current
            self.publish_binding(qr_msg, current)
            self.publish_if_possible(current.parcel_box_track_id)
            return

        binding = BindingState(
            qr_track_id=qr_msg.track_id,
            parcel_box_track_id=best_box.track_id,
            qr_payload=qr_msg.payload,
            association_score_value=best_score,
        )
        self.bindings_by_qr[qr_msg.track_id] = binding
        self.bindings_by_box[best_box.track_id] = binding
        self.publish_binding(qr_msg, binding)
        self.publish_if_possible(best_box.track_id)

    def publish_binding(self, qr_msg: TrackedTarget, binding: BindingState):
        out = ParcelTrackBinding()
        out.stamp = qr_msg.stamp
        out.qr_track_id = binding.qr_track_id
        out.parcel_box_track_id = binding.parcel_box_track_id
        out.qr_payload = binding.qr_payload
        out.association_score = float(binding.association_score)
        out.is_confirmed = bool(binding.hits >= self.min_confirmed_matches)
        self.binding_pub.publish(out)

    def publish_if_possible(self, parcel_box_track_id: str):
        # ParcelTrack is published even for partially observed parcels because higher-level
        # mission logic may still benefit from a box without a confirmed QR yet.
        box = self.box_tracks.get(parcel_box_track_id)
        if box is None:
            return

        binding = self.bindings_by_box.get(parcel_box_track_id)
        qr = self.qr_tracks.get(binding.qr_track_id) if binding else None

        msg = ParcelTrack()
        msg.stamp = box.stamp
        msg.frame_id = box.frame_id
        msg.parcel_box_track_id = box.track_id
        msg.track_id = box.track_id
        msg.position = box.position
        msg.dimensions = box.dimensions
        msg.confidence = box.confidence
        msg.source_method = box.source_method
        msg.logistics_state = self.infer_logistics_state(box, binding, qr)
        msg.is_confirmed = bool(box.is_confirmed and (binding.hits >= self.min_confirmed_matches if binding else False))
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

        self.parcel_pub.publish(msg)

    def infer_logistics_state(self, box: TrackedTarget, binding: Optional[BindingState], qr: Optional[TrackedTarget]) -> str:
        if box.target_type != 'parcel_box':
            return 'unknown'
        if binding is None:
            return 'box_detected'
        if binding is not None and binding.hits < self.min_confirmed_matches:
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

        stale_qr_ids = [k for k, b in self.bindings_by_qr.items() if (now - b.last_update_time) > self.max_binding_age_sec]
        for qr_id in stale_qr_ids:
            binding = self.bindings_by_qr.pop(qr_id, None)
            if binding is not None:
                if self.bindings_by_box.get(binding.parcel_box_track_id) is binding:
                    self.bindings_by_box.pop(binding.parcel_box_track_id, None)
            self.qr_tracks.pop(qr_id, None)


def main(args=None):
    rclpy.init(args=args)
    node = ParcelTrackNode()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()
