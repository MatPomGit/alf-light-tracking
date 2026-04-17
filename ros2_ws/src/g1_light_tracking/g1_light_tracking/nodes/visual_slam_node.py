"""Lekki, eksperymentalny visual odometry / visual SLAM node.

Moduł używa cech ORB oraz dopasowań między kolejnymi klatkami do oszacowania względnego ruchu
kamery. Jeśli dostępna jest głębia, próbuje dodatkowo ustalić skalę translacji. Publikuje
odometrię i ścieżkę, ale należy go traktować jako komponent diagnostyczny lub badawczy,
a nie produkcyjny system SLAM.
"""

from __future__ import annotations

import math
import cv2
import numpy as np
import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Image, CameraInfo
from nav_msgs.msg import Odometry, Path
from geometry_msgs.msg import PoseStamped
from cv_bridge import CvBridge


def yaw_to_quaternion(yaw: float):
    qz = math.sin(yaw / 2.0)
    qw = math.cos(yaw / 2.0)
    return 0.0, 0.0, qz, qw


class VisualSlamNode(Node):
    def __init__(self):
        super().__init__('visual_slam_node')
        self.bridge = CvBridge()
        self.camera_matrix = None
        self.dist_coeffs = None
        self.latest_depth = None
        self.last_depth_time = None
        self.prev_gray = None
        self.prev_kp = None
        self.prev_desc = None

        self.position = np.zeros((3,), dtype=np.float64)
        self.rotation = np.eye(3, dtype=np.float64)
        self.bad_frame_count = 0
        self.last_mode = 'init'

        self.declare_parameter('image_topic', '/camera/image_raw')
        self.declare_parameter('depth_image_topic', '/camera/depth/image_raw')
        self.declare_parameter('camera_info_topic', '/camera/camera_info')
        self.declare_parameter('odom_topic', '/visual_slam/odom')
        self.declare_parameter('path_topic', '/visual_slam/path')
        self.declare_parameter('debug_image_topic', '/visual_slam/debug_image')
        self.declare_parameter('use_depth_if_available', True)
        self.declare_parameter('depth_timeout_sec', 1.0)
        self.declare_parameter('max_features', 1200)
        self.declare_parameter('good_match_ratio', 0.75)
        self.declare_parameter('min_inliers', 25)
        self.declare_parameter('feature_quality_reset_frames', 8)
        self.declare_parameter('scale_from_depth_min_m', 0.20)
        self.declare_parameter('scale_from_depth_max_m', 6.0)
        self.declare_parameter('debug_draw_matches', True)

        self.use_depth_if_available = bool(self.get_parameter('use_depth_if_available').value)
        self.depth_timeout_sec = float(self.get_parameter('depth_timeout_sec').value)
        self.max_features = int(self.get_parameter('max_features').value)
        self.good_match_ratio = float(self.get_parameter('good_match_ratio').value)
        self.min_inliers = int(self.get_parameter('min_inliers').value)
        self.feature_quality_reset_frames = int(self.get_parameter('feature_quality_reset_frames').value)
        self.scale_from_depth_min_m = float(self.get_parameter('scale_from_depth_min_m').value)
        self.scale_from_depth_max_m = float(self.get_parameter('scale_from_depth_max_m').value)
        self.debug_draw_matches = bool(self.get_parameter('debug_draw_matches').value)

        self.orb = cv2.ORB_create(nfeatures=self.max_features)
        self.matcher = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=False)

        self.odom_pub = self.create_publisher(Odometry, self.get_parameter('odom_topic').value, 20)
        self.path_pub = self.create_publisher(Path, self.get_parameter('path_topic').value, 10)
        self.debug_pub = self.create_publisher(Image, self.get_parameter('debug_image_topic').value, 10)

        self.create_subscription(CameraInfo, self.get_parameter('camera_info_topic').value, self.cam_cb, 10)
        self.create_subscription(Image, self.get_parameter('depth_image_topic').value, self.depth_cb, 10)
        self.create_subscription(Image, self.get_parameter('image_topic').value, self.image_cb, 10)

        self.path_msg = Path()
        self.path_msg.header.frame_id = 'map'

    def cam_cb(self, msg: CameraInfo):
        self.camera_matrix = np.array(msg.k, dtype=np.float64).reshape(3, 3)
        self.dist_coeffs = np.array(msg.d, dtype=np.float64) if msg.d else np.zeros((5,), dtype=np.float64)

    def depth_cb(self, msg: Image):
        if not self.use_depth_if_available:
            return
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
        if not self.use_depth_if_available or self.latest_depth is None or self.last_depth_time is None:
            return False
        age = (self.get_clock().now() - self.last_depth_time).nanoseconds / 1e9
        return age <= self.depth_timeout_sec

    def image_cb(self, msg: Image):
        if self.camera_matrix is None:
            return
        frame = self.bridge.imgmsg_to_cv2(msg, desired_encoding='bgr8')
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        kp, desc = self.orb.detectAndCompute(gray, None)

        if desc is None or kp is None or len(kp) < self.min_inliers:
            self.bad_frame_count += 1
            return

        if self.prev_desc is None or self.prev_kp is None or self.prev_gray is None:
            self.reset_reference(gray, kp, desc)
            self.last_mode = 'bootstrap'
            self.publish_state(msg.header.stamp)
            return

        matches = self.matcher.knnMatch(self.prev_desc, desc, k=2)
        good = []
        for pair in matches:
            if len(pair) != 2:
                continue
            m, n = pair
            if m.distance < self.good_match_ratio * n.distance:
                good.append(m)

        if len(good) < self.min_inliers:
            self.bad_frame_count += 1
            if self.bad_frame_count >= self.feature_quality_reset_frames:
                self.reset_reference(gray, kp, desc)
            return

        prev_pts = np.float32([self.prev_kp[m.queryIdx].pt for m in good]).reshape(-1, 2)
        curr_pts = np.float32([kp[m.trainIdx].pt for m in good]).reshape(-1, 2)

        used_depth = False
        success = False
        inlier_mask = None

        if self.depth_available():
            success, inlier_mask = self.try_rgbd_pnp(prev_pts, curr_pts)
            used_depth = success

        if not success:
            success, inlier_mask = self.try_mono_essential(prev_pts, curr_pts)
            used_depth = False

        if not success:
            self.bad_frame_count += 1
            if self.bad_frame_count >= self.feature_quality_reset_frames:
                self.reset_reference(gray, kp, desc)
            return

        self.bad_frame_count = 0
        self.last_mode = 'rgbd_vo' if used_depth else 'mono_vo'
        self.publish_debug(frame, prev_pts, curr_pts, inlier_mask)
        self.reset_reference(gray, kp, desc)
        self.publish_state(msg.header.stamp)

    def reset_reference(self, gray, kp, desc):
        self.prev_gray = gray
        self.prev_kp = kp
        self.prev_desc = desc

    def try_rgbd_pnp(self, prev_pts, curr_pts):
        if self.latest_depth is None or self.camera_matrix is None:
            return False, None
        depth = self.latest_depth
        fx = float(self.camera_matrix[0, 0]); fy = float(self.camera_matrix[1, 1])
        cx = float(self.camera_matrix[0, 2]); cy = float(self.camera_matrix[1, 2])

        obj_pts = []
        img_pts = []
        for (u0, v0), (u1, v1) in zip(prev_pts, curr_pts):
            ui = int(round(u0)); vi = int(round(v0))
            if not (0 <= ui < depth.shape[1] and 0 <= vi < depth.shape[0]):
                continue
            z = float(depth[vi, ui])
            if not np.isfinite(z) or z < self.scale_from_depth_min_m or z > self.scale_from_depth_max_m:
                continue
            x = (u0 - cx) * z / fx
            y = (v0 - cy) * z / fy
            obj_pts.append([x, y, z])
            img_pts.append([u1, v1])

        if len(obj_pts) < self.min_inliers:
            return False, None

        obj_pts = np.array(obj_pts, dtype=np.float32)
        img_pts = np.array(img_pts, dtype=np.float32)

        ok, rvec, tvec, inliers = cv2.solvePnPRansac(
            obj_pts, img_pts, self.camera_matrix, self.dist_coeffs,
            flags=cv2.SOLVEPNP_ITERATIVE, reprojectionError=4.0, confidence=0.99, iterationsCount=100
        )
        if not ok or inliers is None or len(inliers) < self.min_inliers:
            return False, None

        R, _ = cv2.Rodrigues(rvec)
        self.position = self.position + self.rotation @ tvec.reshape(3)
        self.rotation = self.rotation @ R
        return True, inliers

    def try_mono_essential(self, prev_pts, curr_pts):
        E, mask = cv2.findEssentialMat(prev_pts, curr_pts, self.camera_matrix, method=cv2.RANSAC, prob=0.999, threshold=1.0)
        if E is None or mask is None or int(mask.sum()) < self.min_inliers:
            return False, None
        _, R, t, mask_pose = cv2.recoverPose(E, prev_pts, curr_pts, self.camera_matrix)
        if mask_pose is None or int(mask_pose.sum()) < self.min_inliers:
            return False, None

        scale = 0.08
        if self.depth_available():
            scale = self.estimate_scale_from_depth(prev_pts)
        self.position = self.position + self.rotation @ (t.reshape(3) * scale)
        self.rotation = self.rotation @ R
        return True, mask_pose

    def estimate_scale_from_depth(self, prev_pts):
        depth = self.latest_depth
        if depth is None:
            return 0.08
        vals = []
        for (u0, v0) in prev_pts[:80]:
            ui = int(round(u0)); vi = int(round(v0))
            if 0 <= ui < depth.shape[1] and 0 <= vi < depth.shape[0]:
                z = float(depth[vi, ui])
                if np.isfinite(z) and self.scale_from_depth_min_m <= z <= self.scale_from_depth_max_m:
                    vals.append(z * 0.03)
        return float(np.median(vals)) if vals else 0.08

    def publish_debug(self, frame, prev_pts, curr_pts, inlier_mask):
        if not self.debug_draw_matches:
            return
        dbg = frame.copy()
        mask = inlier_mask.flatten().tolist() if inlier_mask is not None else [1] * min(len(prev_pts), len(curr_pts))
        for (p0, p1, ok) in zip(prev_pts[:120], curr_pts[:120], mask[:120]):
            color = (0, 255, 0) if ok else (0, 100, 255)
            cv2.line(dbg, (int(p0[0]), int(p0[1])), (int(p1[0]), int(p1[1])), color, 1)
            cv2.circle(dbg, (int(p1[0]), int(p1[1])), 2, color, -1)
        cv2.putText(dbg, f"mode={self.last_mode}", (20, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255,255,255), 2)
        self.debug_pub.publish(self.bridge.cv2_to_imgmsg(dbg, encoding='bgr8'))

    def publish_state(self, stamp):
        yaw = math.atan2(self.rotation[1, 0], self.rotation[0, 0])
        odom = Odometry()
        odom.header.stamp = stamp
        odom.header.frame_id = 'map'
        odom.child_frame_id = 'base_link'
        odom.pose.pose.position.x = float(self.position[0])
        odom.pose.pose.position.y = float(self.position[1])
        odom.pose.pose.position.z = float(self.position[2])
        qx, qy, qz, qw = yaw_to_quaternion(yaw)
        odom.pose.pose.orientation.x = qx
        odom.pose.pose.orientation.y = qy
        odom.pose.pose.orientation.z = qz
        odom.pose.pose.orientation.w = qw
        self.odom_pub.publish(odom)

        pose = PoseStamped()
        pose.header = odom.header
        pose.pose = odom.pose.pose
        self.path_msg.header.stamp = stamp
        self.path_msg.poses.append(pose)
        if len(self.path_msg.poses) > 2000:
            self.path_msg.poses = self.path_msg.poses[-2000:]
        self.path_pub.publish(self.path_msg)

def main(args=None):
    rclpy.init(args=args)
    node = VisualSlamNode()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()
