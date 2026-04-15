"""ROS 2 node ekstrakcji prostych wskazówek nawigacyjnych z obrazu głębi.

Node analizuje mapę głębi i estymuje, czy przed robotem jest wolna przestrzeń oraz w którą
stronę warto skręcić. Wynik jest publikowany jako `DepthNavHint` i może być użyty przez
`control_node` do bardziej ostrożnego podejścia do celu.

To lekka warstwa reaktywna. Nie buduje trwałej mapy świata i nie planuje trajektorii.
"""

from __future__ import annotations

import math
import numpy as np
import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Image, CameraInfo
from nav_msgs.msg import OccupancyGrid, Odometry
from cv_bridge import CvBridge

from g1_light_tracking.msg import DepthNavHint


class DepthMapperNode(Node):
    def __init__(self):
        super().__init__('depth_mapper_node')
        self.bridge = CvBridge()
        self.camera_matrix = None
        self.latest_depth = None
        self.last_depth_time = None
        self.latest_odom = None

        self.declare_parameter('depth_image_topic', '/camera/depth/image_raw')
        self.declare_parameter('camera_info_topic', '/camera/camera_info')
        self.declare_parameter('odom_topic', '/odom')
        self.declare_parameter('local_grid_topic', '/mapping/local_depth_grid')
        self.declare_parameter('depth_hint_topic', '/navigation/depth_hint')
        self.declare_parameter('depth_timeout_sec', 1.0)
        self.declare_parameter('max_depth_m', 4.0)
        self.declare_parameter('min_depth_m', 0.20)
        self.declare_parameter('grid_resolution_m', 0.10)
        self.declare_parameter('grid_width_m', 6.0)
        self.declare_parameter('grid_height_m', 6.0)
        self.declare_parameter('sample_stride_px', 8)
        self.declare_parameter('front_obstacle_threshold_m', 0.85)
        self.declare_parameter('side_band_ratio', 0.25)
        self.declare_parameter('center_band_ratio', 0.25)

        self.depth_timeout_sec = float(self.get_parameter('depth_timeout_sec').value)
        self.max_depth_m = float(self.get_parameter('max_depth_m').value)
        self.min_depth_m = float(self.get_parameter('min_depth_m').value)
        self.grid_resolution_m = float(self.get_parameter('grid_resolution_m').value)
        self.grid_width_m = float(self.get_parameter('grid_width_m').value)
        self.grid_height_m = float(self.get_parameter('grid_height_m').value)
        self.sample_stride_px = int(self.get_parameter('sample_stride_px').value)
        self.front_obstacle_threshold_m = float(self.get_parameter('front_obstacle_threshold_m').value)
        self.side_band_ratio = float(self.get_parameter('side_band_ratio').value)
        self.center_band_ratio = float(self.get_parameter('center_band_ratio').value)

        self.grid_pub = self.create_publisher(OccupancyGrid, self.get_parameter('local_grid_topic').value, 10)
        self.hint_pub = self.create_publisher(DepthNavHint, self.get_parameter('depth_hint_topic').value, 10)

        self.create_subscription(Image, self.get_parameter('depth_image_topic').value, self.depth_cb, 10)
        self.create_subscription(CameraInfo, self.get_parameter('camera_info_topic').value, self.cam_cb, 10)
        self.create_subscription(Odometry, self.get_parameter('odom_topic').value, self.odom_cb, 10)

        self.timer = self.create_timer(0.2, self.process)

    def cam_cb(self, msg: CameraInfo):
        self.camera_matrix = np.array(msg.k, dtype=np.float32).reshape(3, 3)

    def odom_cb(self, msg: Odometry):
        self.latest_odom = msg

    def depth_cb(self, msg: Image):
        try:
            depth = self.bridge.imgmsg_to_cv2(msg, desired_encoding='passthrough')
            if depth is None:
                return
            if depth.dtype != np.float32:
                depth = depth.astype(np.float32)
                if np.nanmax(depth) > 20.0:
                    depth = depth / 1000.0
            self.latest_depth = depth
            self.last_depth_time = self.get_clock().now()
        except Exception:
            pass

    def depth_available(self) -> bool:
        if self.latest_depth is None or self.last_depth_time is None or self.camera_matrix is None:
            return False
        age = (self.get_clock().now() - self.last_depth_time).nanoseconds / 1e9
        return age <= self.depth_timeout_sec

    def process(self):
        if not self.depth_available():
            self.publish_hint(depth_available=False)
            return
        depth = self.latest_depth
        self.publish_grid(depth)
        self.publish_hint(depth_available=True, depth=depth)

    def publish_grid(self, depth):
        grid = OccupancyGrid()
        grid.header.frame_id = 'base_link'
        grid.header.stamp = self.get_clock().now().to_msg()
        grid.info.resolution = self.grid_resolution_m
        grid.info.width = int(self.grid_width_m / self.grid_resolution_m)
        grid.info.height = int(self.grid_height_m / self.grid_resolution_m)
        grid.info.origin.position.x = 0.0
        grid.info.origin.position.y = -self.grid_height_m / 2.0
        grid.info.origin.orientation.w = 1.0

        data = np.full((grid.info.height, grid.info.width), -1, dtype=np.int8)
        fx = float(self.camera_matrix[0, 0])
        fy = float(self.camera_matrix[1, 1])
        cx = float(self.camera_matrix[0, 2])
        cy = float(self.camera_matrix[1, 2])

        for v in range(0, depth.shape[0], self.sample_stride_px):
            for u in range(0, depth.shape[1], self.sample_stride_px):
                z = float(depth[v, u])
                if not np.isfinite(z) or z < self.min_depth_m or z > self.max_depth_m:
                    continue
                x = (u - cx) * z / fx
                y = (v - cy) * z / fy
                forward = z
                lateral = x
                gx = int(forward / self.grid_resolution_m)
                gy = int((lateral + self.grid_height_m / 2.0) / self.grid_resolution_m)
                if 0 <= gx < grid.info.width and 0 <= gy < grid.info.height:
                    data[gy, gx] = 100

        grid.data = data.reshape(-1).tolist()
        self.grid_pub.publish(grid)

    def clearance_in_roi(self, depth, x1, x2):
        roi = depth[:, x1:x2]
        valid = roi[np.isfinite(roi) & (roi > self.min_depth_m) & (roi < self.max_depth_m)]
        if valid.size < 5:
            return self.max_depth_m
        return float(np.percentile(valid, 20))

    def publish_hint(self, depth_available: bool, depth=None):
        msg = DepthNavHint()
        msg.stamp = self.get_clock().now().to_msg()
        msg.frame_id = 'base_link'
        msg.depth_available = bool(depth_available)
        msg.source_method = 'depth_mapper'
        if not depth_available or depth is None:
            msg.forward_clearance_m = 99.0
            msg.left_clearance_m = 99.0
            msg.right_clearance_m = 99.0
            msg.recommended_linear_scale = 1.0
            msg.recommended_angular_bias = 0.0
            msg.obstacle_ahead = False
            self.hint_pub.publish(msg)
            return

        w = depth.shape[1]
        left_end = int(w * self.side_band_ratio)
        center_w = int(w * self.center_band_ratio)
        center_start = int((w - center_w) / 2)
        center_end = center_start + center_w
        right_start = int(w * (1.0 - self.side_band_ratio))

        left = self.clearance_in_roi(depth, 0, max(1, left_end))
        center = self.clearance_in_roi(depth, max(0, center_start), min(w, center_end))
        right = self.clearance_in_roi(depth, max(0, right_start), w)

        msg.left_clearance_m = float(left)
        msg.forward_clearance_m = float(center)
        msg.right_clearance_m = float(right)
        msg.obstacle_ahead = bool(center < self.front_obstacle_threshold_m)

        if center < self.front_obstacle_threshold_m:
            msg.recommended_linear_scale = max(0.0, min(1.0, (center - self.obstacle_soft_stop()) / max(0.05, self.front_obstacle_threshold_m - self.obstacle_soft_stop())))
        else:
            msg.recommended_linear_scale = 1.0

        msg.recommended_angular_bias = float(max(-1.0, min(1.0, (left - right) / max(0.05, left + right))))
        self.hint_pub.publish(msg)

    def obstacle_soft_stop(self):
        return max(self.min_depth_m + 0.1, self.front_obstacle_threshold_m * 0.55)


def main(args=None):
    rclpy.init(args=args)
    node = DepthMapperNode()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()
