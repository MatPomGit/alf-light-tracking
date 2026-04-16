#!/usr/bin/env python3
"""Compatibility camera node imported from the legacy light-tracking stack.

Publishes:
- separate raw color/depth streams
- aligned color/depth streams (depth aligned to color)
- optional legacy color alias

Optionally loads camera intrinsics from a calibration YAML file and publishes
CameraInfo messages for both raw and aligned topics.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional
import re

import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Image, CameraInfo
from ament_index_python.packages import get_package_share_directory

try:
    import pyrealsense2 as rs
    _PYREALSENSE_IMPORT_ERROR = None
except ImportError as exc:
    rs = None
    _PYREALSENSE_IMPORT_ERROR = exc


class D435iNode(Node):
    def __init__(self) -> None:
        super().__init__('d435i_node')

        self.declare_parameter('width', 640)
        self.declare_parameter('height', 480)
        self.declare_parameter('fps', 30)
        self.declare_parameter('frame_timeout_ms', 100)

        self.declare_parameter('publish_aligned_streams', True)
        self.declare_parameter('publish_separate_streams', True)
        self.declare_parameter('publish_depth', True)
        self.declare_parameter('publish_camera_info', True)

        self.declare_parameter('aligned_image_topic', '/camera/aligned/image_raw')
        self.declare_parameter('aligned_camera_info_topic', '/camera/aligned/camera_info')
        self.declare_parameter('aligned_depth_topic', '/camera/aligned/depth/image_raw')
        self.declare_parameter('aligned_depth_camera_info_topic', '/camera/aligned/depth/camera_info')

        self.declare_parameter('separate_color_topic', '/camera/color/image_raw')
        self.declare_parameter('separate_color_camera_info_topic', '/camera/color/camera_info')
        self.declare_parameter('separate_depth_topic', '/camera/depth/image_raw')
        self.declare_parameter('separate_depth_camera_info_topic', '/camera/depth/camera_info')

        self.declare_parameter('legacy_color_topic', '/camera/image_raw')
        self.declare_parameter('publish_legacy_color_topic', True)

        self.declare_parameter('calibration_file', '')
        self.declare_parameter('frame_id', 'camera_color_optical_frame')
        self.declare_parameter('depth_frame_id', 'camera_depth_optical_frame')

        self.width = int(self.get_parameter('width').value)
        self.height = int(self.get_parameter('height').value)
        self.fps = int(self.get_parameter('fps').value)
        self.frame_timeout_ms = int(self.get_parameter('frame_timeout_ms').value)

        self.publish_aligned_streams = bool(self.get_parameter('publish_aligned_streams').value)
        self.publish_separate_streams = bool(self.get_parameter('publish_separate_streams').value)
        self.publish_depth = bool(self.get_parameter('publish_depth').value)
        self.publish_camera_info = bool(self.get_parameter('publish_camera_info').value)

        self.aligned_image_topic = str(self.get_parameter('aligned_image_topic').value)
        self.aligned_camera_info_topic = str(self.get_parameter('aligned_camera_info_topic').value)
        self.aligned_depth_topic = str(self.get_parameter('aligned_depth_topic').value)
        self.aligned_depth_camera_info_topic = str(
            self.get_parameter('aligned_depth_camera_info_topic').value
        )

        self.separate_color_topic = str(self.get_parameter('separate_color_topic').value)
        self.separate_color_camera_info_topic = str(
            self.get_parameter('separate_color_camera_info_topic').value
        )
        self.separate_depth_topic = str(self.get_parameter('separate_depth_topic').value)
        self.separate_depth_camera_info_topic = str(
            self.get_parameter('separate_depth_camera_info_topic').value
        )

        self.legacy_color_topic = str(self.get_parameter('legacy_color_topic').value)
        self.publish_legacy_color_topic = bool(
            self.get_parameter('publish_legacy_color_topic').value
        )

        self.calibration_file = str(self.get_parameter('calibration_file').value)
        self.frame_id = str(self.get_parameter('frame_id').value)
        self.depth_frame_id = str(self.get_parameter('depth_frame_id').value)

        self.aligned_image_pub = None
        self.aligned_camera_info_pub = None
        self.aligned_depth_pub = None
        self.aligned_depth_camera_info_pub = None

        if self.publish_aligned_streams:
            self.aligned_image_pub = self.create_publisher(Image, self.aligned_image_topic, 10)
            if self.publish_camera_info:
                self.aligned_camera_info_pub = self.create_publisher(
                    CameraInfo, self.aligned_camera_info_topic, 10
                )
            if self.publish_depth:
                self.aligned_depth_pub = self.create_publisher(Image, self.aligned_depth_topic, 10)
                if self.publish_camera_info:
                    self.aligned_depth_camera_info_pub = self.create_publisher(
                        CameraInfo, self.aligned_depth_camera_info_topic, 10
                    )

        self.separate_color_pub = None
        self.separate_color_camera_info_pub = None
        self.separate_depth_pub = None
        self.separate_depth_camera_info_pub = None

        if self.publish_separate_streams:
            self.separate_color_pub = self.create_publisher(Image, self.separate_color_topic, 10)
            if self.publish_camera_info:
                self.separate_color_camera_info_pub = self.create_publisher(
                    CameraInfo, self.separate_color_camera_info_topic, 10
                )
            if self.publish_depth:
                self.separate_depth_pub = self.create_publisher(Image, self.separate_depth_topic, 10)
                if self.publish_camera_info:
                    self.separate_depth_camera_info_pub = self.create_publisher(
                        CameraInfo, self.separate_depth_camera_info_topic, 10
                    )

        self.legacy_pub = None
        if self.publish_legacy_color_topic:
            self.legacy_pub = self.create_publisher(Image, self.legacy_color_topic, 10)

        self.color_camera_info_template = self._load_camera_info()
        self.depth_camera_info_template = self._make_depth_camera_info_template()

        if rs is None:
            raise RuntimeError(f'pyrealsense2 is required for d435i_node: {_PYREALSENSE_IMPORT_ERROR}')

        self.pipeline = rs.pipeline()
        self.config = rs.config()

        self.config.enable_stream(
            rs.stream.color,
            self.width,
            self.height,
            rs.format.bgr8,
            self.fps,
        )

        if self.publish_depth:
            self.config.enable_stream(
                rs.stream.depth,
                self.width,
                self.height,
                rs.format.z16,
                self.fps,
            )

        try:
            self.pipeline_profile = self.pipeline.start(self.config)
        except Exception as exc:
            self.get_logger().error(f'Failed to start RealSense D435i: {exc}')
            raise

        self.align = rs.align(rs.stream.color) if self.publish_depth else None

        timer_period = max(1.0 / float(self.fps), 0.001)
        self.timer = self.create_timer(timer_period, self.publish_frame)

        self.get_logger().info(
            f'D435i started: {self.width}x{self.height}@{self.fps}fps '
            f'aligned={self.publish_aligned_streams} separate={self.publish_separate_streams}'
        )

    def _candidate_calibration_paths(self) -> list[Path]:
        candidates: list[Path] = []
        pkg_share: Optional[Path] = None
        try:
            pkg_share = Path(get_package_share_directory('g1_light_tracking'))
        except Exception:
            pkg_share = None

        if self.calibration_file:
            path = Path(self.calibration_file)
            if path.is_absolute():
                candidates.append(path)
            else:
                candidates.append(Path.cwd() / path)
                if pkg_share is not None:
                    candidates.append(pkg_share / path)
        else:
            candidates.append(Path.cwd() / 'calibration' / 'camera_intrinsics.yaml')
            candidates.append(
                Path.cwd() / 'src' / 'g1_light_tracking' / 'calibration' / 'camera_intrinsics.yaml'
            )
            if pkg_share is not None:
                candidates.append(pkg_share / 'calibration' / 'camera_intrinsics.yaml')
                candidates.append(pkg_share / 'config' / 'camera_intrinsics.yaml')

        # Keep order but drop duplicates so logs stay clean.
        deduped: list[Path] = []
        seen: set[Path] = set()
        for candidate in candidates:
            if candidate in seen:
                continue
            seen.add(candidate)
            deduped.append(candidate)
        return deduped

    def _extract_numeric_list(self, text: str, field_name: str) -> list[float]:
        pattern = (
            rf'{field_name}:\s*\n'
            r'\s*rows:\s*\d+\s*\n'
            r'\s*cols:\s*\d+\s*\n'
            r'\s*data:\s*\[([^\]]+)\]'
        )
        match = re.search(pattern, text, re.MULTILINE)
        if not match:
            raise ValueError(f'Missing field: {field_name}')
        return [float(v.strip()) for v in match.group(1).split(',') if v.strip()]

    def _load_camera_info(self) -> Optional[CameraInfo]:
        if not self.publish_camera_info:
            return None

        chosen_path = None
        text = None
        for path in self._candidate_calibration_paths():
            if path.exists():
                chosen_path = path
                text = path.read_text(encoding='utf-8')
                print(f"Calibration file {chosen_path} loaded")
                break

        if chosen_path is None or text is None:
            print("No calibration file")
            return None

        try:
            width_match = re.search(r'image_width:\s*(\d+)', text)
            height_match = re.search(r'image_height:\s*(\d+)', text)
            distortion_match = re.search(r'distortion_model:\s*([^\n]+)', text)
            if not width_match or not height_match:
                raise ValueError('Missing image dimensions in calibration file')

            k = self._extract_numeric_list(text, 'camera_matrix')
            d = self._extract_numeric_list(text, 'distortion_coefficients')

            msg = CameraInfo()
            msg.width = int(width_match.group(1))
            msg.height = int(height_match.group(1))
            msg.distortion_model = distortion_match.group(1).strip() if distortion_match else 'plumb_bob'
            msg.k = k[:9]
            msg.d = d
            msg.r = [1.0, 0.0, 0.0,
                     0.0, 1.0, 0.0,
                     0.0, 0.0, 1.0]
            fx = msg.k[0]
            fy = msg.k[4]
            cx = msg.k[2]
            cy = msg.k[5]
            msg.p = [
                fx, 0.0, cx, 0.0,
                0.0, fy, cy, 0.0,
                0.0, 0.0, 1.0, 0.0,
            ]
            self.get_logger().info(f'Loaded calibration from {chosen_path}')
            return msg
        except Exception as exc:
            self.get_logger().error(f'Failed to parse calibration file {chosen_path}: {exc}')
            return None

    def _make_default_camera_info(self, width: int, height: int, frame_id: str, stamp_msg) -> CameraInfo:
        msg = CameraInfo()
        msg.width = width
        msg.height = height
        msg.distortion_model = 'plumb_bob'
        msg.k = [0.0] * 9
        msg.d = []
        msg.r = [1.0, 0.0, 0.0,
                 0.0, 1.0, 0.0,
                 0.0, 0.0, 1.0]
        msg.p = [0.0] * 12
        msg.header.stamp = stamp_msg
        msg.header.frame_id = frame_id
        return msg

    def _make_color_camera_info(self, stamp_msg, width: int, height: int, frame_id: str) -> CameraInfo:
        if self.color_camera_info_template is None:
            return self._make_default_camera_info(width, height, frame_id, stamp_msg)

        msg = CameraInfo()
        msg.width = self.color_camera_info_template.width
        msg.height = self.color_camera_info_template.height
        msg.distortion_model = self.color_camera_info_template.distortion_model
        msg.k = list(self.color_camera_info_template.k)
        msg.d = list(self.color_camera_info_template.d)
        msg.r = list(self.color_camera_info_template.r)
        msg.p = list(self.color_camera_info_template.p)
        msg.header.stamp = stamp_msg
        msg.header.frame_id = frame_id
        return msg

    def _make_depth_camera_info_template(self) -> Optional[CameraInfo]:
        if self.color_camera_info_template is None:
            return None
        msg = CameraInfo()
        msg.width = self.color_camera_info_template.width
        msg.height = self.color_camera_info_template.height
        msg.distortion_model = self.color_camera_info_template.distortion_model
        msg.k = list(self.color_camera_info_template.k)
        msg.d = list(self.color_camera_info_template.d)
        msg.r = list(self.color_camera_info_template.r)
        msg.p = list(self.color_camera_info_template.p)
        return msg

    def _make_depth_camera_info(self, stamp_msg, width: int, height: int, frame_id: str) -> CameraInfo:
        if self.depth_camera_info_template is None:
            return self._make_default_camera_info(width, height, frame_id, stamp_msg)

        msg = CameraInfo()
        msg.width = self.depth_camera_info_template.width
        msg.height = self.depth_camera_info_template.height
        msg.distortion_model = self.depth_camera_info_template.distortion_model
        msg.k = list(self.depth_camera_info_template.k)
        msg.d = list(self.depth_camera_info_template.d)
        msg.r = list(self.depth_camera_info_template.r)
        msg.p = list(self.depth_camera_info_template.p)
        msg.header.stamp = stamp_msg
        msg.header.frame_id = frame_id
        return msg

    def publish_frame(self) -> None:
        try:
            raw_frames = self.pipeline.wait_for_frames(timeout_ms=self.frame_timeout_ms)
        except Exception:
            return

        raw_color_frame = raw_frames.get_color_frame()
        if not raw_color_frame:
            return

        raw_depth_frame = None
        if self.publish_depth:
            raw_depth_frame = raw_frames.get_depth_frame()
            if not raw_depth_frame:
                return

        aligned_frames = raw_frames
        if self.align is not None:
            try:
                aligned_frames = self.align.process(raw_frames)
            except Exception as exc:
                self.get_logger().warn(f'Failed to align depth to color: {exc}')
                return

        aligned_color_frame = aligned_frames.get_color_frame()
        if not aligned_color_frame:
            return

        aligned_depth_frame = None
        if self.publish_depth:
            aligned_depth_frame = aligned_frames.get_depth_frame()
            if not aligned_depth_frame:
                return

        stamp_msg = self.get_clock().now().to_msg()

        if self.publish_separate_streams:
            color_msg = Image()
            color_msg.header.stamp = stamp_msg
            color_msg.header.frame_id = self.frame_id
            color_msg.height = int(raw_color_frame.get_height())
            color_msg.width = int(raw_color_frame.get_width())
            color_msg.encoding = 'bgr8'
            color_msg.is_bigendian = 0
            color_msg.step = color_msg.width * 3
            color_msg.data = bytes(raw_color_frame.get_data())

            if self.separate_color_pub is not None:
                self.separate_color_pub.publish(color_msg)

            if self.separate_color_camera_info_pub is not None:
                self.separate_color_camera_info_pub.publish(
                    self._make_color_camera_info(
                        stamp_msg,
                        color_msg.width,
                        color_msg.height,
                        self.frame_id,
                    )
                )

            if self.publish_depth and raw_depth_frame is not None:
                depth_msg = Image()
                depth_msg.header.stamp = stamp_msg
                depth_msg.header.frame_id = self.depth_frame_id
                depth_msg.height = int(raw_depth_frame.get_height())
                depth_msg.width = int(raw_depth_frame.get_width())
                depth_msg.encoding = '16UC1'
                depth_msg.is_bigendian = 0
                depth_msg.step = depth_msg.width * 2
                depth_msg.data = bytes(raw_depth_frame.get_data())

                if self.separate_depth_pub is not None:
                    self.separate_depth_pub.publish(depth_msg)

                if self.separate_depth_camera_info_pub is not None:
                    self.separate_depth_camera_info_pub.publish(
                        self._make_depth_camera_info(
                            stamp_msg,
                            depth_msg.width,
                            depth_msg.height,
                            self.depth_frame_id,
                        )
                    )

        if self.publish_aligned_streams:
            aligned_color_msg = Image()
            aligned_color_msg.header.stamp = stamp_msg
            aligned_color_msg.header.frame_id = self.frame_id
            aligned_color_msg.height = int(aligned_color_frame.get_height())
            aligned_color_msg.width = int(aligned_color_frame.get_width())
            aligned_color_msg.encoding = 'bgr8'
            aligned_color_msg.is_bigendian = 0
            aligned_color_msg.step = aligned_color_msg.width * 3
            aligned_color_msg.data = bytes(aligned_color_frame.get_data())

            if self.aligned_image_pub is not None:
                self.aligned_image_pub.publish(aligned_color_msg)

            if self.aligned_camera_info_pub is not None:
                self.aligned_camera_info_pub.publish(
                    self._make_color_camera_info(
                        stamp_msg,
                        aligned_color_msg.width,
                        aligned_color_msg.height,
                        self.frame_id,
                    )
                )

            if self.publish_depth and aligned_depth_frame is not None:
                aligned_depth_msg = Image()
                aligned_depth_msg.header.stamp = stamp_msg
                aligned_depth_msg.header.frame_id = self.depth_frame_id
                aligned_depth_msg.height = int(aligned_depth_frame.get_height())
                aligned_depth_msg.width = int(aligned_depth_frame.get_width())
                aligned_depth_msg.encoding = '16UC1'
                aligned_depth_msg.is_bigendian = 0
                aligned_depth_msg.step = aligned_depth_msg.width * 2
                aligned_depth_msg.data = bytes(aligned_depth_frame.get_data())

                if self.aligned_depth_pub is not None:
                    self.aligned_depth_pub.publish(aligned_depth_msg)

                if self.aligned_depth_camera_info_pub is not None:
                    self.aligned_depth_camera_info_pub.publish(
                        self._make_depth_camera_info(
                            stamp_msg,
                            aligned_depth_msg.width,
                            aligned_depth_msg.height,
                            self.depth_frame_id,
                        )
                    )

            if self.legacy_pub is not None:
                self.legacy_pub.publish(aligned_color_msg)

    def destroy_node(self) -> bool:
        try:
            self.pipeline.stop()
        except Exception:
            pass
        return super().destroy_node()


def main(args=None) -> None:
    rclpy.init(args=args)
    node = D435iNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
