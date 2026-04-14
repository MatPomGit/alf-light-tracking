from __future__ import annotations

import math
from typing import List, Tuple, Optional

import cv2
import numpy as np
import rclpy
from rclpy.node import Node
from nav_msgs.msg import Odometry
from tf2_ros import Buffer, TransformListener


class TopDownOdomViewerNode(Node):
    def __init__(self):
        super().__init__('topdown_odom_viewer_node')
        self.declare_parameter('odom_topic', '/odom')
        self.declare_parameter('window_name', 'g1_light_tracking ROS2 Top-Down')
        self.declare_parameter('scale_px_per_m', 80.0)
        self.declare_parameter('canvas_width', 760)
        self.declare_parameter('canvas_height', 760)
        self.declare_parameter('max_points', 3000)
        self.declare_parameter('use_global_frame', True)
        self.declare_parameter('global_frame', 'map')
        self.declare_parameter('odom_frame', 'odom')
        self.declare_parameter('base_frame', 'base_link')
        self.declare_parameter('draw_local_path', True)

        self.window_name = str(self.get_parameter('window_name').value)
        self.scale = float(self.get_parameter('scale_px_per_m').value)
        self.width = int(self.get_parameter('canvas_width').value)
        self.height = int(self.get_parameter('canvas_height').value)
        self.max_points = int(self.get_parameter('max_points').value)
        self.use_global_frame = bool(self.get_parameter('use_global_frame').value)
        self.global_frame = str(self.get_parameter('global_frame').value)
        self.odom_frame = str(self.get_parameter('odom_frame').value)
        self.base_frame = str(self.get_parameter('base_frame').value)
        self.draw_local_path = bool(self.get_parameter('draw_local_path').value)

        self.local_path_points: List[Tuple[float, float]] = []
        self.global_path_points: List[Tuple[float, float]] = []
        self.last_local_pose = (0.0, 0.0, 0.0)
        self.last_global_pose = (0.0, 0.0, 0.0)
        self.last_tf_ok = False

        self.tf_buffer = Buffer()
        self.tf_listener = TransformListener(self.tf_buffer, self)

        self.create_subscription(Odometry, self.get_parameter('odom_topic').value, self.odom_cb, 20)
        self.timer = self.create_timer(0.05, self.render)

        self.get_logger().info(
            f"Top-down odom viewer listening on {self.get_parameter('odom_topic').value}, "
            f"use_global_frame={self.use_global_frame}, global_frame={self.global_frame}, base_frame={self.base_frame}"
        )

    def odom_cb(self, msg: Odometry):
        x = float(msg.pose.pose.position.x)
        y = float(msg.pose.pose.position.y)
        qx = float(msg.pose.pose.orientation.x)
        qy = float(msg.pose.pose.orientation.y)
        qz = float(msg.pose.pose.orientation.z)
        qw = float(msg.pose.pose.orientation.w)
        yaw = self.quaternion_to_yaw(qx, qy, qz, qw)

        self.last_local_pose = (x, y, yaw)
        self.local_path_points.append((x, y))
        if len(self.local_path_points) > self.max_points:
            self.local_path_points = self.local_path_points[-self.max_points:]

        self.update_global_pose()

    def update_global_pose(self):
        if not self.use_global_frame:
            self.last_global_pose = self.last_local_pose
            self.global_path_points = list(self.local_path_points)
            self.last_tf_ok = False
            return

        try:
            tf_msg = self.tf_buffer.lookup_transform(
                self.global_frame,
                self.base_frame,
                rclpy.time.Time()
            )
            tx = float(tf_msg.transform.translation.x)
            ty = float(tf_msg.transform.translation.y)
            qx = float(tf_msg.transform.rotation.x)
            qy = float(tf_msg.transform.rotation.y)
            qz = float(tf_msg.transform.rotation.z)
            qw = float(tf_msg.transform.rotation.w)
            yaw = self.quaternion_to_yaw(qx, qy, qz, qw)

            self.last_global_pose = (tx, ty, yaw)
            self.global_path_points.append((tx, ty))
            if len(self.global_path_points) > self.max_points:
                self.global_path_points = self.global_path_points[-self.max_points:]
            self.last_tf_ok = True
        except Exception:
            self.last_tf_ok = False
            # fallback: keep using local pose when TF is unavailable
            self.last_global_pose = self.last_local_pose
            self.global_path_points.append((self.last_local_pose[0], self.last_local_pose[1]))
            if len(self.global_path_points) > self.max_points:
                self.global_path_points = self.global_path_points[-self.max_points:]

    def quaternion_to_yaw(self, x: float, y: float, z: float, w: float) -> float:
        siny_cosp = 2.0 * (w * z + x * y)
        cosy_cosp = 1.0 - 2.0 * (y * y + z * z)
        return math.atan2(siny_cosp, cosy_cosp)

    def world_to_screen(self, x: float, y: float, cx: int, cy: int) -> Tuple[int, int]:
        sx = int(cx + x * self.scale)
        sy = int(cy - y * self.scale)
        return sx, sy

    def draw_path(self, img: np.ndarray, points: List[Tuple[float, float]], color: Tuple[int, int, int], cx: int, cy: int):
        screen_pts = [self.world_to_screen(px, py, cx, cy) for px, py in points]
        for i in range(1, len(screen_pts)):
            cv2.line(img, screen_pts[i - 1], screen_pts[i], color, 2)

    def draw_robot(self, img: np.ndarray, pose: Tuple[float, float, float], cx: int, cy: int, color_body=(110, 168, 254), color_heading=(255, 209, 102)):
        x, y, yaw = pose
        rx, ry = self.world_to_screen(x, y, cx, cy)
        cv2.circle(img, (rx, ry), 7, color_body, -1)
        hx = int(rx + 24 * math.cos(yaw))
        hy = int(ry - 24 * math.sin(yaw))
        cv2.arrowedLine(img, (rx, ry), (hx, hy), color_heading, 2, tipLength=0.3)

    def render(self):
        img = np.zeros((self.height, self.width, 3), dtype=np.uint8)
        img[:] = (14, 20, 42)

        cv2.putText(img, 'ROS2 Top-Down Preview', (18, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.75, (235, 235, 235), 1)
        cv2.putText(img, f'global frame: {self.global_frame}', (18, 54), cv2.FONT_HERSHEY_SIMPLEX, 0.58, (190, 210, 255), 1)
        tf_status = 'TF OK' if self.last_tf_ok else 'TF fallback -> /odom'
        cv2.putText(img, tf_status, (18, 78), cv2.FONT_HERSHEY_SIMPLEX, 0.58, (126, 231, 135) if self.last_tf_ok else (255, 209, 102), 1)

        cx, cy = self.width // 2, self.height // 2
        cv2.line(img, (0, cy), (self.width, cy), (55, 70, 120), 1)
        cv2.line(img, (cx, 0), (cx, self.height), (55, 70, 120), 1)

        # draw global path as primary
        self.draw_path(img, self.global_path_points, (126, 231, 135), cx, cy)
        self.draw_robot(img, self.last_global_pose, cx, cy)

        # optional local overlay
        if self.draw_local_path and self.local_path_points:
            self.draw_path(img, self.local_path_points, (90, 110, 180), cx, cy)

        gx, gy, gyaw = self.last_global_pose
        lx, ly, lyaw = self.last_local_pose

        cv2.putText(img, f'global x={gx:.2f} m', (18, self.height - 74), cv2.FONT_HERSHEY_SIMPLEX, 0.58, (220, 220, 220), 1)
        cv2.putText(img, f'global y={gy:.2f} m', (18, self.height - 50), cv2.FONT_HERSHEY_SIMPLEX, 0.58, (220, 220, 220), 1)
        cv2.putText(img, f'global yaw={gyaw:.2f} rad', (220, self.height - 50), cv2.FONT_HERSHEY_SIMPLEX, 0.58, (220, 220, 220), 1)

        cv2.putText(img, f'odom x={lx:.2f} m', (18, self.height - 24), cv2.FONT_HERSHEY_SIMPLEX, 0.56, (150, 170, 220), 1)
        cv2.putText(img, f'odom y={ly:.2f} m', (160, self.height - 24), cv2.FONT_HERSHEY_SIMPLEX, 0.56, (150, 170, 220), 1)

        cv2.imshow(self.window_name, img)
        key = cv2.waitKey(1) & 0xFF
        if key == ord('q'):
            self.get_logger().info('Closing top-down odom viewer.')
            rclpy.shutdown()


def main(args=None):
    rclpy.init(args=args)
    node = TopDownOdomViewerNode()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        cv2.destroyAllWindows()
        if rclpy.ok():
            rclpy.shutdown()
