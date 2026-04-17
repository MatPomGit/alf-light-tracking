"""Node wizualizacyjny prezentujący odometrię w rzucie z góry.

Służy do szybkiej diagnostyki trajektorii wyliczanej przez moduły odometrii / SLAM. Nie wpływa
na pipeline percepcji ani sterowanie.
"""

from __future__ import annotations

import math
from typing import Dict, List, Tuple

import cv2
import numpy as np
import rclpy
from rclpy.node import Node
from nav_msgs.msg import Odometry
from tf2_ros import Buffer, TransformListener

from g1_light_tracking.msg import MissionTarget, ParcelTrack, TrackedTarget


CLASS_COLORS: Dict[str, Tuple[int, int, int]] = {
    'person': (255, 120, 120),
    'parcel_box': (255, 209, 102),
    'shelf': (126, 231, 135),
    'light_spot': (110, 168, 254),
    'qr': (200, 160, 255),
    'apriltag': (255, 160, 220),
    'planar_surface': (120, 220, 220),
    'parcel_track': (255, 225, 150),
    'mission_target': (255, 80, 80),
}


class TopDownOdomViewerNode(Node):
    def __init__(self):
        super().__init__('topdown_odom_viewer_node')
        self.declare_parameter('odom_topic', '/odom')
        self.declare_parameter('tracked_topic', '/tracking/targets')
        self.declare_parameter('parcel_track_topic', '/tracking/parcel_tracks')
        self.declare_parameter('mission_target_topic', '/mission/target')
        self.declare_parameter('window_name', 'g1_light_tracking ROS2 Top-Down')
        self.declare_parameter('scale_px_per_m', 80.0)
        self.declare_parameter('canvas_width', 920)
        self.declare_parameter('canvas_height', 920)
        self.declare_parameter('max_points', 3000)
        self.declare_parameter('use_global_frame', True)
        self.declare_parameter('global_frame', 'map')
        self.declare_parameter('odom_frame', 'odom')
        self.declare_parameter('base_frame', 'base_link')
        self.declare_parameter('draw_local_path', True)
        self.declare_parameter('grid_spacing_m', 0.5)
        self.declare_parameter('major_grid_every', 2)
        self.declare_parameter('draw_targets', True)
        self.declare_parameter('draw_parcels', True)
        self.declare_parameter('draw_mission_target', True)
        self.declare_parameter('draw_legend', True)

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
        self.grid_spacing_m = float(self.get_parameter('grid_spacing_m').value)
        self.major_grid_every = int(self.get_parameter('major_grid_every').value)
        self.draw_targets = bool(self.get_parameter('draw_targets').value)
        self.draw_parcels = bool(self.get_parameter('draw_parcels').value)
        self.draw_mission_target = bool(self.get_parameter('draw_mission_target').value)
        self.draw_legend = bool(self.get_parameter('draw_legend').value)

        self.local_path_points: List[Tuple[float, float]] = []
        self.global_path_points: List[Tuple[float, float]] = []
        self.last_local_pose = (0.0, 0.0, 0.0)
        self.last_global_pose = (0.0, 0.0, 0.0)
        self.last_tf_ok = False

        self.latest_tracked: Dict[str, TrackedTarget] = {}
        self.latest_parcels: Dict[str, ParcelTrack] = {}
        self.latest_mission_target: MissionTarget | None = None

        self.tf_buffer = Buffer()
        self.tf_listener = TransformListener(self.tf_buffer, self)

        self.create_subscription(Odometry, self.get_parameter('odom_topic').value, self.odom_cb, 20)
        self.create_subscription(TrackedTarget, self.get_parameter('tracked_topic').value, self.tracked_cb, 50)
        self.create_subscription(ParcelTrack, self.get_parameter('parcel_track_topic').value, self.parcel_cb, 20)
        self.create_subscription(MissionTarget, self.get_parameter('mission_target_topic').value, self.mission_cb, 20)
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

    def tracked_cb(self, msg: TrackedTarget):
        self.latest_tracked[msg.track_id] = msg
        if len(self.latest_tracked) > 200:
            keys = list(self.latest_tracked.keys())[-200:]
            self.latest_tracked = {k: self.latest_tracked[k] for k in keys}

    def parcel_cb(self, msg: ParcelTrack):
        self.latest_parcels[msg.parcel_box_track_id] = msg
        if len(self.latest_parcels) > 100:
            keys = list(self.latest_parcels.keys())[-100:]
            self.latest_parcels = {k: self.latest_parcels[k] for k in keys}

    def mission_cb(self, msg: MissionTarget):
        self.latest_mission_target = msg

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

    def color_for_type(self, target_type: str) -> Tuple[int, int, int]:
        return CLASS_COLORS.get(target_type, (200, 200, 200))

    def draw_grid(self, img: np.ndarray, cx: int, cy: int):
        spacing_px = max(8, int(self.grid_spacing_m * self.scale))
        major_every = max(1, self.major_grid_every)

        idx = 0
        for x in range(cx, self.width, spacing_px):
            color = (60, 80, 135) if idx % major_every else (85, 110, 170)
            cv2.line(img, (x, 0), (x, self.height), color, 1)
            meters = (x - cx) / self.scale
            if idx % major_every == 0:
                cv2.putText(img, f"{meters:.1f}m", (x + 3, cy - 6), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (150, 170, 220), 1)
            idx += 1
        idx = 1
        for x in range(cx - spacing_px, -1, -spacing_px):
            color = (60, 80, 135) if idx % major_every else (85, 110, 170)
            cv2.line(img, (x, 0), (x, self.height), color, 1)
            meters = (x - cx) / self.scale
            if idx % major_every == 0:
                cv2.putText(img, f"{meters:.1f}m", (max(0, x + 3), cy - 6), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (150, 170, 220), 1)
            idx += 1

        idx = 0
        for y in range(cy, self.height, spacing_px):
            color = (60, 80, 135) if idx % major_every else (85, 110, 170)
            cv2.line(img, (0, y), (self.width, y), color, 1)
            meters = -(y - cy) / self.scale
            if idx % major_every == 0:
                cv2.putText(img, f"{meters:.1f}m", (6, max(14, y - 4)), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (150, 170, 220), 1)
            idx += 1
        idx = 1
        for y in range(cy - spacing_px, -1, -spacing_px):
            color = (60, 80, 135) if idx % major_every else (85, 110, 170)
            cv2.line(img, (0, y), (self.width, y), color, 1)
            meters = -(y - cy) / self.scale
            if idx % major_every == 0:
                cv2.putText(img, f"{meters:.1f}m", (6, max(14, y - 4)), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (150, 170, 220), 1)
            idx += 1

        cv2.line(img, (0, cy), (self.width, cy), (120, 145, 210), 1)
        cv2.line(img, (cx, 0), (cx, self.height), (120, 145, 210), 1)
        cv2.putText(img, '0,0', (cx + 6, cy - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (200, 210, 245), 1)

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

    def draw_targets_overlay(self, img: np.ndarray, cx: int, cy: int):
        if self.draw_targets:
            for target in list(self.latest_tracked.values())[-40:]:
                x = float(target.position.x)
                y = float(target.position.y)
                sx, sy = self.world_to_screen(x, y, cx, cy)
                color = self.color_for_type(target.target_type)
                cv2.circle(img, (sx, sy), 5, color, -1)
                label = f"{target.target_type}"
                cv2.putText(img, label[:16], (sx + 6, sy - 4), cv2.FONT_HERSHEY_SIMPLEX, 0.42, color, 1)

        if self.draw_parcels:
            for parcel in list(self.latest_parcels.values())[-20:]:
                x = float(parcel.position.x)
                y = float(parcel.position.y)
                sx, sy = self.world_to_screen(x, y, cx, cy)
                color = self.color_for_type('parcel_track')
                cv2.rectangle(img, (sx - 6, sy - 6), (sx + 6, sy + 6), color, 2)
                label = parcel.shipment_id if parcel.shipment_id else parcel.parcel_box_track_id
                cv2.putText(img, label[:18], (sx + 8, sy + 12), cv2.FONT_HERSHEY_SIMPLEX, 0.42, color, 1)

        if self.draw_mission_target and self.latest_mission_target is not None:
            target = self.latest_mission_target
            x = float(target.position.x)
            y = float(target.position.y)
            sx, sy = self.world_to_screen(x, y, cx, cy)
            color = self.color_for_type('mission_target')
            cv2.circle(img, (sx, sy), 10, color, 2)
            cv2.line(img, (sx - 14, sy), (sx + 14, sy), color, 1)
            cv2.line(img, (sx, sy - 14), (sx, sy + 14), color, 1)
            cv2.putText(img, f"mission:{target.mode}"[:26], (sx + 10, sy - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.45, color, 1)

    def draw_legend_panel(self, img: np.ndarray):
        if not self.draw_legend:
            return
        x0, y0, w, h = self.width - 250, 18, 220, 240
        cv2.rectangle(img, (x0, y0), (x0 + w, y0 + h), (20, 28, 54), -1)
        cv2.rectangle(img, (x0, y0), (x0 + w, y0 + h), (70, 90, 145), 1)
        cv2.putText(img, 'Legenda klas', (x0 + 14, y0 + 24), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (240, 240, 240), 1)

        legend_items = [
            ('person', 'Osoba'),
            ('parcel_box', 'Karton'),
            ('shelf', 'Regał'),
            ('light_spot', 'Plamka światła'),
            ('qr', 'QR'),
            ('apriltag', 'AprilTag'),
            ('planar_surface', 'Płaszczyzna'),
            ('parcel_track', 'Przesyłka'),
            ('mission_target', 'Cel misji'),
        ]
        y = y0 + 50
        for key, label in legend_items:
            color = self.color_for_type(key)
            cv2.circle(img, (x0 + 18, y - 4), 5, color, -1)
            cv2.putText(img, label, (x0 + 34, y), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)
            y += 22

    def render(self):
        img = np.zeros((self.height, self.width, 3), dtype=np.uint8)
        img[:] = (14, 20, 42)

        cv2.putText(img, 'ROS2 Global Top-Down Preview', (18, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.75, (235, 235, 235), 1)
        cv2.putText(img, f'global frame: {self.global_frame}', (18, 54), cv2.FONT_HERSHEY_SIMPLEX, 0.58, (190, 210, 255), 1)
        tf_status = 'TF OK' if self.last_tf_ok else 'TF fallback -> /odom'
        cv2.putText(img, tf_status, (18, 78), cv2.FONT_HERSHEY_SIMPLEX, 0.58, (126, 231, 135) if self.last_tf_ok else (255, 209, 102), 1)

        cx, cy = self.width // 2, self.height // 2
        self.draw_grid(img, cx, cy)
        self.draw_path(img, self.global_path_points, (126, 231, 135), cx, cy)
        self.draw_robot(img, self.last_global_pose, cx, cy)

        if self.draw_local_path and self.local_path_points:
            self.draw_path(img, self.local_path_points, (90, 110, 180), cx, cy)

        self.draw_targets_overlay(img, cx, cy)
        self.draw_legend_panel(img)

        gx, gy, gyaw = self.last_global_pose
        lx, ly, _ = self.last_local_pose

        cv2.putText(img, f'global x={gx:.2f} m', (18, self.height - 78), cv2.FONT_HERSHEY_SIMPLEX, 0.58, (220, 220, 220), 1)
        cv2.putText(img, f'global y={gy:.2f} m', (18, self.height - 54), cv2.FONT_HERSHEY_SIMPLEX, 0.58, (220, 220, 220), 1)
        cv2.putText(img, f'global yaw={gyaw:.2f} rad', (220, self.height - 54), cv2.FONT_HERSHEY_SIMPLEX, 0.58, (220, 220, 220), 1)
        cv2.putText(img, f'odom x={lx:.2f} m', (18, self.height - 28), cv2.FONT_HERSHEY_SIMPLEX, 0.56, (150, 170, 220), 1)
        cv2.putText(img, f'odom y={ly:.2f} m', (160, self.height - 28), cv2.FONT_HERSHEY_SIMPLEX, 0.56, (150, 170, 220), 1)
        cv2.putText(img, f'tracked={len(self.latest_tracked)} parcels={len(self.latest_parcels)}', (420, self.height - 28), cv2.FONT_HERSHEY_SIMPLEX, 0.56, (180, 220, 180), 1)

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
