import time
import rclpy
from rclpy.node import Node

from g1_light_tracking.msg import (
    TrackedTarget,
    MissionTarget,
    ParcelInfo,
    ParcelTrackBinding,
    ParcelTrack,
)


class MissionNode(Node):
    def __init__(self):
        super().__init__('mission_node')
        self.declare_parameter('tracked_topic', '/tracking/targets')
        self.declare_parameter('parcel_track_topic', '/tracking/parcel_tracks')
        self.declare_parameter('mission_topic', '/mission/target')
        self.declare_parameter('parcel_info_topic', '/mission/parcel_info')
        self.declare_parameter('binding_topic', '/tracking/parcel_bindings')
        self.declare_parameter('color_pickup_values', ['green', 'yellow'])
        self.declare_parameter('color_dropoff_values', ['blue', 'red'])
        self.declare_parameter('prefer_identified_parcels', True)
        self.declare_parameter('parcel_timeout_sec', 3.0)

        self.pickup_colors = set(self.get_parameter('color_pickup_values').value)
        self.dropoff_colors = set(self.get_parameter('color_dropoff_values').value)
        self.prefer_identified_parcels = bool(self.get_parameter('prefer_identified_parcels').value)
        self.parcel_timeout_sec = float(self.get_parameter('parcel_timeout_sec').value)

        self.latest_bindings = {}
        self.latest_tracked_by_id = {}
        self.latest_parcel_tracks = {}
        self.latest_parcel_time = {}
        self.latest_tracked_time = {}

        self.mission_pub = self.create_publisher(MissionTarget, self.get_parameter('mission_topic').value, 20)
        self.parcel_pub = self.create_publisher(ParcelInfo, self.get_parameter('parcel_info_topic').value, 20)

        self.create_subscription(TrackedTarget, self.get_parameter('tracked_topic').value, self.on_tracked, 50)
        self.create_subscription(ParcelTrackBinding, self.get_parameter('binding_topic').value, self.on_binding, 20)
        self.create_subscription(ParcelTrack, self.get_parameter('parcel_track_topic').value, self.on_parcel_track, 20)

        self.timer = self.create_timer(0.20, self.publish_mission)

    def on_binding(self, msg: ParcelTrackBinding):
        self.latest_bindings[msg.qr_track_id] = msg

    def on_tracked(self, msg: TrackedTarget):
        self.latest_tracked_by_id[msg.track_id] = msg
        self.latest_tracked_time[msg.track_id] = time.time()

    def on_parcel_track(self, msg: ParcelTrack):
        self.latest_parcel_tracks[msg.parcel_box_track_id] = msg
        self.latest_parcel_time[msg.parcel_box_track_id] = time.time()

        p = ParcelInfo()
        p.stamp = msg.stamp
        p.shipment_id = msg.shipment_id
        p.pickup_zone = msg.pickup_zone
        p.dropoff_zone = msg.dropoff_zone
        p.parcel_type = msg.parcel_type
        p.mass_kg = msg.mass_kg
        p.raw_payload = msg.raw_payload
        if msg.has_qr:
            self.parcel_pub.publish(p)

    def publish_mission(self):
        self.cleanup_stale()
        mission = self.choose_mission()
        self.mission_pub.publish(mission)

    def choose_mission(self) -> MissionTarget:
        parcel = self.select_best_parcel_track()
        if parcel is not None:
            return self.mission_from_parcel_track(parcel)

        # Fallback path: raw tracked targets if no parcel-track exists.
        for target in self.latest_tracked_by_id.values():
            if target.target_type == 'light_spot':
                return self.mission_from_light(target)
        for target in self.latest_tracked_by_id.values():
            if target.target_type == 'shelf':
                return self.mission_from_tracked(target, 'shelf_approach')
        for target in self.latest_tracked_by_id.values():
            if target.target_type == 'person':
                return self.mission_from_tracked(target, 'handover_ready')
        for target in self.latest_tracked_by_id.values():
            if target.target_type == 'planar_surface':
                return self.mission_from_tracked(target, 'planar_alignment')
        for target in self.latest_tracked_by_id.values():
            if target.target_type == 'qr':
                return self.mission_from_tracked(target, 'qr_guided')

        mission = MissionTarget()
        mission.mode = 'idle'
        return mission

    def select_best_parcel_track(self):
        if not self.latest_parcel_tracks:
            return None

        candidates = list(self.latest_parcel_tracks.values())

        def rank(msg: ParcelTrack):
            identified = 1 if msg.logistics_state == 'identified' else 0
            confirmed = 1 if msg.is_confirmed else 0
            has_qr = 1 if msg.has_qr else 0
            confidence = float(msg.confidence)
            close_bonus = -float(msg.position.z)
            if self.prefer_identified_parcels:
                return (identified, confirmed, has_qr, confidence, close_bonus)
            return (confirmed, has_qr, confidence, close_bonus)

        candidates.sort(key=rank, reverse=True)
        return candidates[0]

    def mission_from_parcel_track(self, parcel: ParcelTrack) -> MissionTarget:
        mission = MissionTarget()
        mission.stamp = parcel.stamp
        mission.frame_id = parcel.frame_id
        mission.target_type = 'parcel_track'
        mission.class_name = 'parcel_box'
        mission.confidence = parcel.confidence
        mission.position = parcel.position
        mission.payload = parcel.raw_payload

        if parcel.logistics_state == 'identified':
            mission.mode = 'parcel_approach'
        elif parcel.logistics_state == 'binding_pending':
            mission.mode = 'parcel_verify'
        elif parcel.logistics_state == 'binding_confirmed_qr_not_visible':
            mission.mode = 'parcel_hold_track'
        elif parcel.logistics_state == 'box_detected':
            mission.mode = 'parcel_approach'
        else:
            mission.mode = 'parcel_approach'

        return mission

    def mission_from_light(self, target: TrackedTarget) -> MissionTarget:
        mission = MissionTarget()
        mission.stamp = target.stamp
        mission.frame_id = target.frame_id
        mission.target_type = target.target_type
        mission.class_name = target.class_name
        mission.confidence = target.confidence
        mission.position = target.position
        mission.color_label = target.color_label
        mission.payload = target.payload
        mission.mode = 'light_guided'
        if target.color_label in self.pickup_colors:
            mission.zone_mode = 'pickup'
        elif target.color_label in self.dropoff_colors:
            mission.zone_mode = 'dropoff'
        else:
            mission.zone_mode = 'unknown'
        return mission

    def mission_from_tracked(self, target: TrackedTarget, mode: str) -> MissionTarget:
        mission = MissionTarget()
        mission.stamp = target.stamp
        mission.frame_id = target.frame_id
        mission.target_type = target.target_type
        mission.class_name = target.class_name
        mission.confidence = target.confidence
        mission.position = target.position
        mission.color_label = target.color_label
        mission.payload = target.payload
        mission.mode = mode
        return mission

    def cleanup_stale(self):
        now = time.time()
        stale_parcels = [k for k, t in self.latest_parcel_time.items() if (now - t) > self.parcel_timeout_sec]
        for k in stale_parcels:
            self.latest_parcel_time.pop(k, None)
            self.latest_parcel_tracks.pop(k, None)

        stale_targets = [k for k, t in self.latest_tracked_time.items() if (now - t) > self.parcel_timeout_sec]
        for k in stale_targets:
            self.latest_tracked_time.pop(k, None)
            self.latest_tracked_by_id.pop(k, None)


def main(args=None):
    rclpy.init(args=args)
    node = MissionNode()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()
