import rclpy
from rclpy.node import Node

from g1_light_tracking.msg import TrackedTarget, MissionTarget, ParcelInfo, ParcelTrackBinding
from g1_light_tracking.utils.qr_schema import parse_parcel_qr


class MissionNode(Node):
    def __init__(self):
        super().__init__('mission_node')
        self.declare_parameter('tracked_topic', '/tracking/targets')
        self.declare_parameter('mission_topic', '/mission/target')
        self.declare_parameter('parcel_info_topic', '/mission/parcel_info')
        self.declare_parameter('binding_topic', '/tracking/parcel_bindings')
        self.declare_parameter('color_pickup_values', ['green', 'yellow'])
        self.declare_parameter('color_dropoff_values', ['blue', 'red'])

        self.pickup_colors = set(self.get_parameter('color_pickup_values').value)
        self.dropoff_colors = set(self.get_parameter('color_dropoff_values').value)

        self.latest_bindings = {}
        self.mission_pub = self.create_publisher(MissionTarget, self.get_parameter('mission_topic').value, 20)
        self.parcel_pub = self.create_publisher(ParcelInfo, self.get_parameter('parcel_info_topic').value, 20)
        self.create_subscription(TrackedTarget, self.get_parameter('tracked_topic').value, self.cb, 50)
        self.create_subscription(ParcelTrackBinding, self.get_parameter('binding_topic').value, self.on_binding, 20)

    def on_binding(self, msg: ParcelTrackBinding):
        self.latest_bindings[msg.qr_track_id] = msg

    def cb(self, target: TrackedTarget):
        mission = MissionTarget()
        mission.stamp = target.stamp
        mission.frame_id = target.frame_id
        mission.target_type = target.target_type
        mission.class_name = target.class_name
        mission.confidence = target.confidence
        mission.position = target.position
        mission.color_label = target.color_label
        mission.payload = target.payload

        if target.target_type == 'qr' and target.payload:
            mission.mode = 'qr_guided'
            binding = self.latest_bindings.get(target.track_id)
            if binding and binding.is_confirmed:
                mission.payload = f"parcel_box_track_id={binding.parcel_box_track_id};" + target.payload
            parcel = parse_parcel_qr(target.payload)
            p = ParcelInfo()
            p.stamp = target.stamp
            p.shipment_id = str(parcel.get('shipment_id', ''))
            p.pickup_zone = str(parcel.get('pickup_zone', ''))
            p.dropoff_zone = str(parcel.get('dropoff_zone', ''))
            p.parcel_type = str(parcel.get('parcel_type', ''))
            try:
                p.mass_kg = float(parcel.get('mass_kg', 0.0))
            except Exception:
                p.mass_kg = 0.0
            p.raw_payload = target.payload
            self.parcel_pub.publish(p)
        elif target.target_type == 'light_spot':
            mission.mode = 'light_guided'
            if target.color_label in self.pickup_colors:
                mission.zone_mode = 'pickup'
            elif target.color_label in self.dropoff_colors:
                mission.zone_mode = 'dropoff'
            else:
                mission.zone_mode = 'unknown'
        elif target.target_type == 'shelf':
            mission.mode = 'shelf_approach'
        elif target.target_type == 'parcel_box':
            mission.mode = 'parcel_approach'
        elif target.target_type == 'person':
            mission.mode = 'handover_ready'
        elif target.target_type == 'planar_surface':
            mission.mode = 'planar_alignment'
        else:
            mission.mode = 'idle'

        self.mission_pub.publish(mission)

def main(args=None):
    rclpy.init(args=args)
    node = MissionNode()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()
