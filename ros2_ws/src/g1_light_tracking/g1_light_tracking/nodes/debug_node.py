"""ROS 2 node diagnostyczny wypisujący strumienie wiadomości w czytelnej formie.

Node subskrybuje najważniejsze tematy pipeline’u i loguje ich zawartość. Nie zmienia danych
i nie bierze udziału w sterowaniu — jego rolą jest obserwowalność systemu podczas strojenia,
uruchomień integracyjnych i analiz błędów.
"""

from __future__ import annotations

import rclpy
from rclpy.node import Node
from std_msgs.msg import Bool, String

from g1_light_tracking.msg import (
    DepthNavHint,
    Detection2D,
    LocalizedTarget,
    MissionState,
    MissionTarget,
    ParcelInfo,
    ParcelTrack,
    ParcelTrackBinding,
    TrackedTarget,
)


class DebugNode(Node):
    """Node agregujący kluczowe informacje diagnostyczne z całego pipeline'u."""

    def __init__(self) -> None:
        super().__init__('debug_node')

        # Parametry topików są jawne, aby operator mógł łatwo dopasować node do środowiska.
        self.declare_parameter('detections_topic', '/perception/detections')
        self.declare_parameter('localized_topic', '/localization/targets')
        self.declare_parameter('tracks_topic', '/tracking/targets')
        self.declare_parameter('binding_topic', '/tracking/parcel_bindings')
        self.declare_parameter('parcel_track_topic', '/tracking/parcel_tracks')
        self.declare_parameter('mission_state_topic', '/mission/state')
        self.declare_parameter('depth_hint_topic', '/navigation/depth_hint')
        self.declare_parameter('mission_target_topic', '/mission/target')
        self.declare_parameter('parcel_info_topic', '/mission/parcel_info')
        self.declare_parameter('estop_state_topic', '/safety/estop_state')
        self.declare_parameter('head_display_effect_topic', '/head_display/effect')
        self.declare_parameter('rosbag_status_topic', '/rosbag_recorder/status')

        self.create_subscription(
            Detection2D,
            str(self.get_parameter('detections_topic').value),
            self.on_detection,
            50,
        )
        self.create_subscription(
            LocalizedTarget,
            str(self.get_parameter('localized_topic').value),
            self.on_localized,
            50,
        )
        self.create_subscription(
            TrackedTarget,
            str(self.get_parameter('tracks_topic').value),
            self.on_tracked,
            50,
        )
        self.create_subscription(
            ParcelTrackBinding,
            str(self.get_parameter('binding_topic').value),
            self.on_binding,
            20,
        )
        self.create_subscription(
            ParcelTrack,
            str(self.get_parameter('parcel_track_topic').value),
            self.on_parcel_track,
            20,
        )
        self.create_subscription(
            MissionState,
            str(self.get_parameter('mission_state_topic').value),
            self.on_state,
            20,
        )
        self.create_subscription(
            DepthNavHint,
            str(self.get_parameter('depth_hint_topic').value),
            self.on_depth_hint,
            20,
        )
        self.create_subscription(
            MissionTarget,
            str(self.get_parameter('mission_target_topic').value),
            self.on_mission,
            20,
        )
        self.create_subscription(
            ParcelInfo,
            str(self.get_parameter('parcel_info_topic').value),
            self.on_parcel,
            20,
        )
        self.create_subscription(
            Bool,
            str(self.get_parameter('estop_state_topic').value),
            self.on_estop_state,
            20,
        )
        self.create_subscription(
            String,
            str(self.get_parameter('head_display_effect_topic').value),
            self.on_head_display_effect,
            20,
        )
        self.create_subscription(
            String,
            str(self.get_parameter('rosbag_status_topic').value),
            self.on_rosbag_status,
            20,
        )

    def on_detection(self, msg: Detection2D) -> None:
        self.get_logger().debug(
            f"DET {msg.target_type} cls={msg.class_name} conf={msg.confidence:.2f} "
            f"uv=({msg.center_u:.1f},{msg.center_v:.1f}) payload={msg.payload[:30]}"
        )

    def on_localized(self, msg: LocalizedTarget) -> None:
        self.get_logger().debug(
            f"LOC {msg.target_type} xyz=({msg.position.x:.2f},{msg.position.y:.2f},{msg.position.z:.2f}) "
            f"src={msg.source_method}"
        )

    def on_tracked(self, msg: TrackedTarget) -> None:
        self.get_logger().debug(
            f"TRK id={msg.track_id} type={msg.target_type} "
            f"xyz=({msg.position.x:.2f},{msg.position.y:.2f},{msg.position.z:.2f}) "
            f"bbox=({msg.x_min:.1f},{msg.y_min:.1f},{msg.x_max:.1f},{msg.y_max:.1f}) "
            f"src={msg.source_method} confirmed={msg.is_confirmed} missed={msg.missed_frames}"
        )

    def on_binding(self, msg: ParcelTrackBinding) -> None:
        self.get_logger().info(
            f"BIND qr={msg.qr_track_id} -> box={msg.parcel_box_track_id} "
            f"score={msg.association_score:.2f} confirmed={msg.is_confirmed}"
        )

    def on_parcel_track(self, msg: ParcelTrack) -> None:
        self.get_logger().info(
            f"PTRACK box={msg.parcel_box_track_id} qr={msg.qr_track_id} "
            f"shipment={msg.shipment_id} state={msg.logistics_state} confirmed={msg.is_confirmed}"
        )

    def on_state(self, msg: MissionState) -> None:
        self.get_logger().info(
            f"STATE state={msg.state} prev={msg.previous_state} active_box={msg.active_parcel_box_track_id} "
            f"shipment={msg.active_shipment_id} reason={msg.reason}"
        )

    def on_depth_hint(self, msg: DepthNavHint) -> None:
        self.get_logger().info(
            f"DEPTH depth={msg.depth_available} front={msg.forward_clearance_m:.2f} "
            f"left={msg.left_clearance_m:.2f} right={msg.right_clearance_m:.2f} "
            f"obstacle={msg.obstacle_ahead}"
        )

    def on_mission(self, msg: MissionTarget) -> None:
        self.get_logger().info(
            f"MISSION mode={msg.mode} target={msg.target_type} cls={msg.class_name} "
            f"z={msg.position.z:.2f} color={msg.color_label}"
        )

    def on_parcel(self, msg: ParcelInfo) -> None:
        self.get_logger().info(
            f"PARCEL id={msg.shipment_id} pickup={msg.pickup_zone} "
            f"dropoff={msg.dropoff_zone} mass={msg.mass_kg:.2f}"
        )

    def on_estop_state(self, msg: Bool) -> None:
        # Jawny podgląd E-STOP ułatwia szybką diagnozę źródła zatrzymania robota.
        self.get_logger().info(f"E_STOP active={msg.data}")

    def on_head_display_effect(self, msg: String) -> None:
        # Efekt LED jest publikowany jako prosty status operatorski i warto go logować.
        self.get_logger().info(f"HEAD_DISPLAY effect={msg.data}")

    def on_rosbag_status(self, msg: String) -> None:
        # Status nagrywania rosbag informuje, czy telemetria sesji jest zbierana.
        self.get_logger().info(f"ROSBAG status={msg.data}")


def main(args: list[str] | None = None) -> None:
    rclpy.init(args=args)
    node = DebugNode()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()
