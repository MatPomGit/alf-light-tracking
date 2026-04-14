from __future__ import annotations

import math
from typing import List, Tuple

import cv2
import numpy as np
import rclpy
from rclpy.node import Node
from nav_msgs.msg import Odometry


class TopDownOdomViewerNode(Node):
    def __init__(self):
        super().__init__('topdown_odom_viewer_node')
        self.declare_parameter('odom_topic', '/odom')
        self.declare_parameter('window_name', 'g1_light_tracking ROS2 Top-Down')
        self.declare_parameter('scale_px_per_m', 80.0)
        self.declare_parameter('canvas_width', 640)
        self.declare_parameter('canvas_height', 640)
        self.declare_parameter('max_points', 2000)

        self.window_name = str(self.get_parameter('window_name').value)
        self.scale = float(self.get_parameter('scale_px_per_m').value)
        self.width = int(self.get_parameter('canvas_width').value)
        self.height = int(self.get_parameter('canvas_height').value)
        self.max_points = int(self.get_parameter('max_points').value)

        self.path_points: List[Tuple[float, float]] = []
        self.last_pose = (0.0, 0.0, 0.0)

        self.create_subscription(Odometry, self.get_parameter('odom_topic').value, self.odom_cb, 20)
        self.timer = self.create_timer(0.05, self.render)

        self.get_logger().info(f"Top-down odom viewer listening on {self.get_parameter('odom_topic').value}")

    def odom_cb(self, msg: Odometry):
        x = float(msg.pose.pose.position.x)
        y = float(msg.pose.pose.position.y)
        qx = float(msg.pose.pose.orientation.x)
        qy = float(msg.pose.pose.orientation.y)
        qz = float(msg.pose.pose.orientation.z)
        qw = float(msg.pose.pose.orientation.w)
        yaw = self.quaternion_to_yaw(qx, qy, qz, qw)

        self.last_pose = (x, y, yaw)
        self.path_points.append((x, y))
        if len(self.path_points) > self.max_points:
            self.path_points = self.path_points[-self.max_points:]

    def quaternion_to_yaw(self, x: float, y: float, z: float, w: float) -> float:
        siny_cosp = 2.0 * (w * z + x * y)
        cosy_cosp = 1.0 - 2.0 * (y * y + z * z)
        return math.atan2(siny_cosp, cosy_cosp)

    def render(self):
        img = np.zeros((self.height, self.width, 3), dtype=np.uint8)
        img[:] = (14, 20, 42)

        cv2.putText(img, 'ROS2 /odom top-down preview', (18, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (235, 235, 235), 1)

        cx, cy = self.width // 2, self.height // 2
        cv2.line(img, (0, cy), (self.width, cy), (55, 70, 120), 1)
        cv2.line(img, (cx, 0), (cx, self.height), (55, 70, 120), 1)

        pts = []
        for px, py in self.path_points:
            sx = int(cx + px * self.scale)
            sy = int(cy - py * self.scale)
            pts.append((sx, sy))

        for i in range(1, len(pts)):
            cv2.line(img, pts[i - 1], pts[i], (126, 231, 135), 2)

        x, y, yaw = self.last_pose
        rx = int(cx + x * self.scale)
        ry = int(cy - y * self.scale)
        cv2.circle(img, (rx, ry), 7, (110, 168, 254), -1)
        hx = int(rx + 24 * math.cos(yaw))
        hy = int(ry - 24 * math.sin(yaw))
        cv2.arrowedLine(img, (rx, ry), (hx, hy), (255, 209, 102), 2, tipLength=0.3)

        cv2.putText(img, f'x={x:.2f} m', (18, self.height - 54), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (220, 220, 220), 1)
        cv2.putText(img, f'y={y:.2f} m', (18, self.height - 30), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (220, 220, 220), 1)
        cv2.putText(img, f'yaw={yaw:.2f} rad', (180, self.height - 30), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (220, 220, 220), 1)

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
