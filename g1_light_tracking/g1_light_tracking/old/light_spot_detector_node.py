from __future__ import annotations

import json
import math
from datetime import datetime, timezone

import cv2
import numpy as np
import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Image
from std_msgs.msg import String

from .vision import DetectorConfig, detect_spots_with_config


class LightSpotDetectorNode(Node):
    def __init__(self) -> None:
        super().__init__('light_spot_detector_node')

        self.declare_parameter('camera_topic', '/camera/image_raw')
        self.declare_parameter('detection_topic', '/light_tracking/detection_json')
        self.declare_parameter('camera_frame', 'camera_link')
        self.declare_parameter('log_detections', True)
        self.declare_parameter('detection_log_interval_s', 0.5)

        self.camera_topic = self.get_parameter('camera_topic').get_parameter_value().string_value
        self.detection_topic = self.get_parameter('detection_topic').get_parameter_value().string_value
        self.camera_frame = self.get_parameter('camera_frame').get_parameter_value().string_value
        self.log_detections = self.get_parameter('log_detections').get_parameter_value().bool_value
        self.detection_log_interval_s = float(
            self.get_parameter('detection_log_interval_s').get_parameter_value().double_value
        )
        self.track_id = 1
        self.detector_config = DetectorConfig(max_spots=1)
        self._unsupported_encodings_warned: set[str] = set()
        self._last_detection_log_time = None

        self.image_sub = self.create_subscription(Image, self.camera_topic, self.on_image, 10)
        self.detection_pub = self.create_publisher(String, self.detection_topic, 10)

        self.get_logger().info(
            f'Listening on {self.camera_topic}, publishing JSON detections to {self.detection_topic}'
        )

    def on_image(self, msg: Image) -> None:
        payload = self._empty_payload(msg)
        frame = self._image_msg_to_bgr(msg)
        if frame is not None:
            detections, _, _ = detect_spots_with_config(frame, self.detector_config)
            best = detections[0] if detections else None
            if best is not None:
                payload.update(
                    {
                        'detected': True,
                        'x': float(best.x),
                        'y': float(best.y),
                        'area': float(best.area),
                        'perimeter': float(best.perimeter),
                        'circularity': float(best.circularity),
                        'radius': float(best.radius),
                        'track_id': self.track_id,
                        'rank': int(best.rank),
                        'kalman_predicted': False,
                    }
                )

        out = String()
        out.data = json.dumps(payload, separators=(',', ':'))
        self.detection_pub.publish(out)
        self._maybe_log_detection(payload)

    def _maybe_log_detection(self, payload: dict) -> None:
        if not self.log_detections or not bool(payload.get('detected', False)):
            return

        now = self.get_clock().now()
        if self._last_detection_log_time is not None:
            elapsed = (now - self._last_detection_log_time).nanoseconds / 1e9
            if elapsed < self.detection_log_interval_s:
                return

        self._last_detection_log_time = now
        self.get_logger().info(
            'Detection: '
            f"x={float(payload.get('x', math.nan)):.3f}, "
            f"y={float(payload.get('y', math.nan)):.3f}, "
            f"area={float(payload.get('area', 0.0)):.1f}, "
            f"radius={float(payload.get('radius', 0.0)):.2f}, "
            f"track_id={int(payload.get('track_id', 0))}"
        )

    def _image_msg_to_bgr(self, msg: Image) -> np.ndarray | None:
        encoding = msg.encoding.lower()
        if msg.height <= 0 or msg.width <= 0:
            return None

        if encoding not in {'bgr8', 'rgb8', 'mono8', 'bgra8', 'rgba8'}:
            if encoding not in self._unsupported_encodings_warned:
                self._unsupported_encodings_warned.add(encoding)
                self.get_logger().warn(f'Unsupported image encoding: {msg.encoding}')
            return None

        channels = 1 if encoding == 'mono8' else (4 if encoding in {'bgra8', 'rgba8'} else 3)
        data = np.frombuffer(msg.data, dtype=np.uint8)
        needed = msg.height * msg.step
        if data.size < needed or msg.step < (msg.width * channels):
            return None

        rows = data[:needed].reshape((msg.height, msg.step))
        image = rows[:, : msg.width * channels].reshape((msg.height, msg.width, channels))

        if encoding == 'bgr8':
            return image
        if encoding == 'rgb8':
            return cv2.cvtColor(image, cv2.COLOR_RGB2BGR)
        if encoding == 'mono8':
            return cv2.cvtColor(image[:, :, 0], cv2.COLOR_GRAY2BGR)
        if encoding == 'bgra8':
            return cv2.cvtColor(image, cv2.COLOR_BGRA2BGR)
        return cv2.cvtColor(image, cv2.COLOR_RGBA2BGR)

    def _empty_payload(self, msg: Image) -> dict:
        return {
            'stamp': datetime.now(timezone.utc).isoformat(),
            'frame_id': msg.header.frame_id or self.camera_frame,
            'detected': False,
            'x': math.nan,
            'y': math.nan,
            'z': math.nan,
            'x_world': math.nan,
            'y_world': math.nan,
            'z_world': math.nan,
            'area': 0.0,
            'perimeter': 0.0,
            'circularity': 0.0,
            'radius': 0.0,
            'track_id': 0,
            'rank': 0,
            'kalman_predicted': False,
        }


def main(args=None) -> None:
    rclpy.init(args=args)
    node = LightSpotDetectorNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
