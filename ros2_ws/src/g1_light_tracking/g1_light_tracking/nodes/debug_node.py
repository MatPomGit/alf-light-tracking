import rclpy
from rclpy.node import Node

from g1_light_tracking.msg import Detection2D, LocalizedTarget, TrackedTarget, MissionTarget, ParcelInfo, ParcelTrackBinding, ParcelTrack, MissionState, DepthNavHint


class DebugNode(Node):
    def __init__(self):
        super().__init__('debug_node')
        self.create_subscription(Detection2D, '/perception/detections', self.on_detection, 50)
        self.create_subscription(LocalizedTarget, '/localization/targets', self.on_localized, 50)
        self.create_subscription(TrackedTarget, '/tracking/targets', self.on_tracked, 50)
        self.create_subscription(ParcelTrackBinding, '/tracking/parcel_bindings', self.on_binding, 20)
        self.create_subscription(ParcelTrack, '/tracking/parcel_tracks', self.on_parcel_track, 20)
        self.create_subscription(MissionState, '/mission/state', self.on_state, 20)
        self.create_subscription(DepthNavHint, '/navigation/depth_hint', self.on_depth_hint, 20)
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
            f"TRK id={msg.track_id} type={msg.target_type} xyz=({msg.position.x:.2f},{msg.position.y:.2f},{msg.position.z:.2f}) bbox=({msg.x_min:.1f},{msg.y_min:.1f},{msg.x_max:.1f},{msg.y_max:.1f}) src={msg.source_method} confirmed={msg.is_confirmed} missed={msg.missed_frames}"
        )

    def on_binding(self, msg: ParcelTrackBinding):
        self.get_logger().info(
            f"BIND qr={msg.qr_track_id} -> box={msg.parcel_box_track_id} score={msg.association_score:.2f} confirmed={msg.is_confirmed}"
        )

    def on_parcel_track(self, msg: ParcelTrack):
        self.get_logger().info(
            f"PTRACK box={msg.parcel_box_track_id} qr={msg.qr_track_id} shipment={msg.shipment_id} state={msg.logistics_state} confirmed={msg.is_confirmed}"
        )

    def on_state(self, msg: MissionState):
        self.get_logger().info(
            f"STATE state={msg.state} prev={msg.previous_state} active_box={msg.active_parcel_box_track_id} shipment={msg.active_shipment_id} reason={msg.reason}"
        )

    def on_depth_hint(self, msg: DepthNavHint):
        self.get_logger().info(
            f"DEPTH depth={msg.depth_available} front={msg.forward_clearance_m:.2f} left={msg.left_clearance_m:.2f} right={msg.right_clearance_m:.2f} obstacle={msg.obstacle_ahead}"
        )

    def on_mission(self, msg: MissionTarget):
        self.get_logger().info(
            f"MISSION mode={msg.mode} target={msg.target_type} cls={msg.class_name} z={msg.position.z:.2f} color={msg.color_label}"
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
