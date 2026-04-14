import time
import rclpy
from rclpy.node import Node

from g1_light_tracking.msg import (
    TrackedTarget,
    MissionTarget,
    ParcelInfo,
    ParcelTrack,
    MissionState,
)


class MissionNode(Node):
    def __init__(self):
        super().__init__('mission_node')
        self.declare_parameter('tracked_topic', '/tracking/targets')
        self.declare_parameter('parcel_track_topic', '/tracking/parcel_tracks')
        self.declare_parameter('mission_topic', '/mission/target')
        self.declare_parameter('mission_state_topic', '/mission/state')
        self.declare_parameter('parcel_info_topic', '/mission/parcel_info')
        self.declare_parameter('color_pickup_values', ['green', 'yellow'])
        self.declare_parameter('color_dropoff_values', ['blue', 'red'])
        self.declare_parameter('prefer_identified_parcels', True)
        self.declare_parameter('parcel_timeout_sec', 3.0)
        self.declare_parameter('state_hold_sec', 1.0)

        self.pickup_colors = set(self.get_parameter('color_pickup_values').value)
        self.dropoff_colors = set(self.get_parameter('color_dropoff_values').value)
        self.prefer_identified_parcels = bool(self.get_parameter('prefer_identified_parcels').value)
        self.parcel_timeout_sec = float(self.get_parameter('parcel_timeout_sec').value)
        self.state_hold_sec = float(self.get_parameter('state_hold_sec').value)

        self.latest_tracked_by_id = {}
        self.latest_parcel_tracks = {}
        self.latest_parcel_time = {}
        self.latest_tracked_time = {}

        self.current_state = 'search'
        self.previous_state = ''
        self.state_since = time.time()
        self.active_parcel_box_track_id = ''
        self.active_shipment_id = ''

        self.mission_pub = self.create_publisher(MissionTarget, self.get_parameter('mission_topic').value, 20)
        self.state_pub = self.create_publisher(MissionState, self.get_parameter('mission_state_topic').value, 20)
        self.parcel_pub = self.create_publisher(ParcelInfo, self.get_parameter('parcel_info_topic').value, 20)

        self.create_subscription(TrackedTarget, self.get_parameter('tracked_topic').value, self.on_tracked, 50)
        self.create_subscription(ParcelTrack, self.get_parameter('parcel_track_topic').value, self.on_parcel_track, 20)

        self.timer = self.create_timer(0.20, self.tick)

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

    def tick(self):
        self.cleanup_stale()
        best_parcel = self.select_best_parcel_track()
        light = self.select_first_target('light_spot')
        shelf = self.select_first_target('shelf')
        person = self.select_first_target('person')
        planar = self.select_first_target('planar_surface')

        self.advance_state(best_parcel, light, shelf, person, planar)
        mission = self.build_mission(best_parcel, light, shelf, person, planar)
        self.mission_pub.publish(mission)
        self.state_pub.publish(self.build_state_msg(best_parcel, light, shelf, person, planar))

    def state_elapsed(self) -> float:
        return time.time() - self.state_since

    def set_state(self, new_state: str):
        if new_state != self.current_state:
            self.previous_state = self.current_state
            self.current_state = new_state
            self.state_since = time.time()

    def advance_state(self, parcel, light, shelf, person, planar):
        # search -> approach_person -> receive_parcel -> verify_qr -> navigate -> align -> drop
        if self.current_state == 'search':
            if parcel is not None:
                self.active_parcel_box_track_id = parcel.parcel_box_track_id
                self.active_shipment_id = parcel.shipment_id
                self.set_state('verify_qr' if parcel.has_qr else 'receive_parcel')
            elif person is not None:
                self.set_state('approach_person')
            elif shelf is not None:
                self.set_state('navigate')

        elif self.current_state == 'approach_person':
            if parcel is not None:
                self.active_parcel_box_track_id = parcel.parcel_box_track_id
                self.active_shipment_id = parcel.shipment_id
                self.set_state('verify_qr' if parcel.has_qr else 'receive_parcel')
            elif person is None and self.state_elapsed() > self.state_hold_sec:
                self.set_state('search')

        elif self.current_state == 'receive_parcel':
            if parcel is not None and parcel.has_qr:
                self.active_parcel_box_track_id = parcel.parcel_box_track_id
                self.active_shipment_id = parcel.shipment_id
                self.set_state('verify_qr')
            elif parcel is None and self.state_elapsed() > self.state_hold_sec:
                self.set_state('search')

        elif self.current_state == 'verify_qr':
            if parcel is not None and parcel.logistics_state == 'identified':
                self.set_state('navigate')
            elif parcel is None and self.state_elapsed() > self.state_hold_sec:
                self.set_state('search')

        elif self.current_state == 'navigate':
            if light is not None and light.color_label in ('blue', 'red', 'green', 'yellow'):
                self.set_state('align')
            elif planar is not None:
                # stay in navigate but with planar target hint
                pass
            elif shelf is None and parcel is None and self.state_elapsed() > max(2.0, self.state_hold_sec):
                self.set_state('search')

        elif self.current_state == 'align':
            if light is not None and abs(light.position.x) < 0.15 and light.position.z < 0.8:
                self.set_state('drop')
            elif light is None and self.state_elapsed() > self.state_hold_sec:
                self.set_state('navigate')

        elif self.current_state == 'drop':
            if self.state_elapsed() > 1.5:
                self.active_parcel_box_track_id = ''
                self.active_shipment_id = ''
                self.set_state('search')

    def build_mission(self, parcel, light, shelf, person, planar) -> MissionTarget:
        mission = MissionTarget()
        mission.mode = self.current_state

        if self.current_state == 'approach_person' and person is not None:
            return self.mission_from_tracked(person, 'approach_person')

        if self.current_state in ('receive_parcel', 'verify_qr', 'navigate') and parcel is not None:
            return self.mission_from_parcel_track(parcel, self.current_state)

        if self.current_state == 'align':
            if light is not None:
                return self.mission_from_light(light)
            if planar is not None:
                return self.mission_from_tracked(planar, 'planar_alignment')

        if self.current_state == 'drop':
            if light is not None:
                m = self.mission_from_light(light)
                m.mode = 'drop'
                return m

        # generic fallback
        if parcel is not None:
            return self.mission_from_parcel_track(parcel, 'parcel_approach')
        if light is not None:
            return self.mission_from_light(light)
        if shelf is not None:
            return self.mission_from_tracked(shelf, 'shelf_approach')
        if person is not None:
            return self.mission_from_tracked(person, 'handover_ready')
        if planar is not None:
            return self.mission_from_tracked(planar, 'planar_alignment')
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
            active_bonus = 1 if (self.active_parcel_box_track_id and msg.parcel_box_track_id == self.active_parcel_box_track_id) else 0
            if self.prefer_identified_parcels:
                return (active_bonus, identified, confirmed, has_qr, confidence, close_bonus)
            return (active_bonus, confirmed, has_qr, confidence, close_bonus)

        candidates.sort(key=rank, reverse=True)
        return candidates[0]

    def select_first_target(self, target_type: str):
        for target in self.latest_tracked_by_id.values():
            if target.target_type == target_type:
                return target
        return None

    def mission_from_parcel_track(self, parcel: ParcelTrack, mode: str) -> MissionTarget:
        mission = MissionTarget()
        mission.stamp = parcel.stamp
        mission.frame_id = parcel.frame_id
        mission.target_type = 'parcel_track'
        mission.class_name = 'parcel_box'
        mission.confidence = parcel.confidence
        mission.position = parcel.position
        mission.payload = parcel.raw_payload
        mission.mode = mode
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

    def build_state_msg(self, parcel, light, shelf, person, planar) -> MissionState:
        msg = MissionState()
        msg.state = self.current_state
        msg.previous_state = self.previous_state
        msg.active_parcel_box_track_id = self.active_parcel_box_track_id
        msg.active_shipment_id = self.active_shipment_id
        msg.has_active_parcel = parcel is not None
        msg.has_drop_target = (light is not None) or (planar is not None) or (shelf is not None)
        msg.is_terminal = (self.current_state == 'drop')
        msg.reason = self.describe_reason(parcel, light, shelf, person, planar)
        return msg

    def describe_reason(self, parcel, light, shelf, person, planar) -> str:
        if self.current_state == 'search':
            return 'searching for person, parcel, shelf or drop cue'
        if self.current_state == 'approach_person':
            return 'person detected but no active parcel yet'
        if self.current_state == 'receive_parcel':
            return 'parcel visible but QR not identified yet'
        if self.current_state == 'verify_qr':
            return 'parcel has QR or binding, waiting for identification'
        if self.current_state == 'navigate':
            return 'identified parcel available, navigating to destination cues'
        if self.current_state == 'align':
            return 'drop target visible, performing final alignment'
        if self.current_state == 'drop':
            return 'drop conditions satisfied'
        return 'unknown'

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
