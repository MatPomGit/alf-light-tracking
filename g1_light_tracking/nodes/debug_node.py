import rclpy
from rclpy.node import Node

from g1_light_tracking.msg import Detection2D, LocalizedTarget, TrackedTarget, MissionTarget, ParcelInfo, ParcelTrackBinding


class DebugNode(Node):
    def __init__(self):
        super().__init__('debug_node')
        self.create_subscription(Detection2D, '/perception/detections', self.on_detection, 50)
        self.create_subscription(LocalizedTarget, '/localization/targets', self.on_localized, 50)
        self.create_subscription(TrackedTarget, '/tracking/targets', self.on_tracked, 50)
        self.create_subscription(ParcelTrackBinding, '/tracking/parcel_bindings', self.on_binding, 20)
        self.create_subscription(MissionTarget, '/mission/target', self.on_mission, 20)
        self.create_subscription(ParcelInfo, '/mission/parcel_info', self.on_parcel, 20)

    def on_detection(self, msg: Detection2D):
        self.get_logger().debug(
            f"DET {msg.target_type} cls={msg.class_name} conf={msg.confidence:.2f} "
            f"uv=({msg.center_u:.1f},{msg.center_v:.1f}) payload={msg.payload[:30]}"
        )

    def on_localized(self, msg: LocalizedTarget):
        self.get_logger().debug(
            f"LOC {msg.target_type} xyz=({msg.position.x:.2f},{msg.position.y:.2f},{msg.position.z:.2f}) "
            f"src={msg.source_method}"
        )

    def on_tracked(self, msg: TrackedTarget):
        self.get_logger().debug(
            f"TRK id={msg.track_id} type={msg.target_type} xyz=({msg.position.x:.2f},{msg.position.y:.2f},{msg.position.z:.2f}) src={msg.source_method} confirmed={msg.is_confirmed} missed={msg.missed_frames}"
        )

    def on_binding(self, msg: ParcelTrackBinding):
        self.get_logger().info(
            f"BIND qr={msg.qr_track_id} -> box={msg.parcel_box_track_id} score={msg.association_score:.2f} confirmed={msg.is_confirmed}"
        )

    def on_mission(self, msg: MissionTarget):
        self.get_logger().info(
            f"MISSION mode={msg.mode} target={msg.target_type} z={msg.position.z:.2f} color={msg.color_label}"
        )

    def on_parcel(self, msg: ParcelInfo):
        self.get_logger().info(
            f"PARCEL id={msg.shipment_id} pickup={msg.pickup_zone} dropoff={msg.dropoff_zone} mass={msg.mass_kg:.2f}"
        )

def main(args=None):
    rclpy.init(args=args)
    node = DebugNode()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()
