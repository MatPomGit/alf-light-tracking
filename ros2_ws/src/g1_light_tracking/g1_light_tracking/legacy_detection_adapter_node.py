"""Bridge legacy JSON detections into the modern ROS 2 message pipeline.

This node subscribes to the historical ``std_msgs/String`` JSON topic used by the
legacy proof-of-concept stack and republishes the same observation as:

- ``Detection2D`` on the modern perception topic, so localization can consume it.
- ``TrackedTarget`` on the modern tracking topic, so mission/control can already
  work even when localization and tracking nodes are not present.

The bridge is intentionally additive. It does not replace the current pipeline.
It only mirrors legacy observations into the newer contracts.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

import rclpy
from rclpy.node import Node
from std_msgs.msg import String

from g1_light_tracking.msg import Detection2D, TrackedTarget
from g1_light_tracking.utils.legacy_adapter import parse_legacy_payload, normalize_legacy_payload


class LegacyDetectionAdapterNode(Node):
    def __init__(self) -> None:
        super().__init__('legacy_detection_adapter_node')
        # Parameters are deliberately explicit because this node is used as a transition
        # layer between the historical JSON topic names and the modern ROS 2 contracts.
        self.declare_parameter('legacy_detection_topic', '/light_tracking/detection_json')
        self.declare_parameter('detection_topic', '/perception/detections')
        self.declare_parameter('tracked_topic', '/tracking/targets')
        self.declare_parameter('default_frame_id', 'camera_link')
        self.declare_parameter('default_target_type', 'light_spot')
        self.declare_parameter('default_class_name', 'legacy_light')
        self.declare_parameter('camera_cx', 319.5)
        self.declare_parameter('camera_fx', 600.0)
        self.declare_parameter('assumed_depth_m', 1.0)
        self.declare_parameter('min_confidence', 0.0)
        self.declare_parameter('publish_detection2d', True)
        self.declare_parameter('publish_tracked_target', True)
        # TODO: Add adaptive calibration parameters loaded from CameraInfo so the
        # adapter can estimate x/z more accurately than the current fixed pinhole
        # approximation used during migration.
        self.declare_parameter('log_invalid_payloads', True)

        self.legacy_detection_topic = str(self.get_parameter('legacy_detection_topic').value)
        self.detection_topic = str(self.get_parameter('detection_topic').value)
        self.tracked_topic = str(self.get_parameter('tracked_topic').value)
        self.default_frame_id = str(self.get_parameter('default_frame_id').value)
        self.default_target_type = str(self.get_parameter('default_target_type').value)
        self.default_class_name = str(self.get_parameter('default_class_name').value)
        self.camera_cx = float(self.get_parameter('camera_cx').value)
        self.camera_fx = float(self.get_parameter('camera_fx').value)
        self.assumed_depth_m = float(self.get_parameter('assumed_depth_m').value)
        self.min_confidence = float(self.get_parameter('min_confidence').value)
        self.publish_detection2d = bool(self.get_parameter('publish_detection2d').value)
        self.publish_tracked_target = bool(self.get_parameter('publish_tracked_target').value)
        self.log_invalid_payloads = bool(self.get_parameter('log_invalid_payloads').value)

        self.det_pub = self.create_publisher(Detection2D, self.detection_topic, 20)
        self.track_pub = self.create_publisher(TrackedTarget, self.tracked_topic, 20)
        # The legacy producer already publishes JSON as plain strings, so the adapter
        # keeps that wire format and performs normalization locally.
        self.create_subscription(String, self.legacy_detection_topic, self.on_detection, 20)

        # TODO: Expose diagnostics counters (accepted / rejected / downgraded
        # payloads) on a status topic or via diagnostics_msgs for easier migration
        # monitoring in production deployments.
        self.get_logger().info(
            'Bridging legacy JSON detections from '
            f'{self.legacy_detection_topic} to {self.detection_topic} and {self.tracked_topic}'
        )

    def on_detection(self, msg: String) -> None:
        # Payload parsing and normalization happen before any ROS message is constructed.
        # That way both Detection2D and TrackedTarget are generated from the same source
        # of truth and stay numerically consistent.
        try:
            payload = parse_legacy_payload(msg.data)
            det = normalize_legacy_payload(
                payload,
                default_frame_id=self.default_frame_id,
                default_target_type=self.default_target_type,
                default_class_name=self.default_class_name,
                camera_cx=self.camera_cx,
                camera_fx=self.camera_fx,
                assumed_depth_m=self.assumed_depth_m,
                min_confidence=self.min_confidence,
            )
        except Exception as exc:
            if self.log_invalid_payloads:
                self.get_logger().warn(f'Invalid legacy JSON payload skipped: {exc}')
            return

        if not det.detected:
            return

        stamp = self.get_clock().now().to_msg()
        # Detection2D is the preferred migration target because it feeds the modern
        # localization and tracking stages without bypassing them.
        # Detection2D is the preferred migration path because it lets the modern
        # localization and tracking nodes stay in charge of downstream semantics.
        if self.publish_detection2d:
            self.det_pub.publish(self._build_detection_msg(det, stamp))
        # Publishing TrackedTarget remains optional. It exists mainly for pure legacy
        # mode where localization/tracking nodes may be intentionally absent.
        # TrackedTarget publishing is optional and exists mainly for pure legacy mode,
        # where mission/control may need data even without modern tracking enabled.
        if self.publish_tracked_target:
            self.track_pub.publish(self._build_tracked_target_msg(det, stamp))

    def _build_detection_msg(self, det, stamp):
        msg = Detection2D()
        msg.stamp = stamp
        msg.frame_id = det.frame_id
        msg.target_type = det.target_type
        msg.class_name = det.class_name
        msg.confidence = float(det.confidence)
        msg.x_min = float(det.x_min)
        msg.y_min = float(det.y_min)
        msg.x_max = float(det.x_max)
        msg.y_max = float(det.y_max)
        msg.center_u = float(det.center_u)
        msg.center_v = float(det.center_v)
        msg.color_label = det.color_label
        msg.payload = det.payload
        msg.image_points = []
        return msg

    def _build_tracked_target_msg(self, det, stamp):
        msg = TrackedTarget()
        msg.stamp = stamp
        msg.frame_id = det.frame_id
        msg.track_id = det.track_id or 'legacy-light-1'
        msg.target_type = det.target_type
        msg.class_name = det.class_name
        msg.confidence = float(det.confidence)
        msg.position.x = float(det.position_x)
        msg.position.y = float(det.position_y)
        msg.position.z = float(det.position_z)
        msg.dimensions.x = float(max(det.x_max - det.x_min, 0.0))
        msg.dimensions.y = float(max(det.y_max - det.y_min, 0.0))
        msg.dimensions.z = 0.0
        msg.center_u = float(det.center_u)
        msg.center_v = float(det.center_v)
        msg.x_min = float(det.x_min)
        msg.y_min = float(det.y_min)
        msg.x_max = float(det.x_max)
        msg.y_max = float(det.y_max)
        msg.color_label = det.color_label
        msg.payload = det.payload
        msg.source_method = det.source_method
        msg.age_sec = 0.0
        msg.missed_frames = 0
        msg.is_confirmed = bool(det.is_confirmed)
        return msg


def main(args=None) -> None:
    rclpy.init(args=args)
    node = LegacyDetectionAdapterNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
