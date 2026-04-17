"""ROS 2 node do kalibracji intrinsics kamery na podstawie wzorca szachownicy.

Node zbiera próbki narożników, pilnuje minimalnego zróżnicowania między kolejnymi ujęciami,
a po zgromadzeniu wymaganej liczby obserwacji uruchamia `cv2.calibrateCamera`. Wynik może zostać
zapisany do YAML oraz opublikowany jako `CameraInfo` do dalszych etapów pipeline’u.
"""

from __future__ import annotations

from pathlib import Path
from typing import List

import cv2
import numpy as np
import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Image, CameraInfo
from cv_bridge import CvBridge


class CameraCalibrationNode(Node):
    def __init__(self):
        super().__init__('camera_calibration_node')
        self.bridge = CvBridge()

        self.declare_parameter('image_topic', '/camera/image_raw')
        self.declare_parameter('camera_info_output', '/camera/camera_info_calibrated')
        self.declare_parameter('board_cols', 9)
        self.declare_parameter('board_rows', 6)
        self.declare_parameter('square_size_m', 0.024)
        self.declare_parameter('min_samples', 20)
        self.declare_parameter('preview_topic', '/debug/calibration_preview')
        self.declare_parameter('output_yaml', 'calibration/camera_intrinsics.yaml')

        self.board_cols = int(self.get_parameter('board_cols').value)
        self.board_rows = int(self.get_parameter('board_rows').value)
        self.square_size_m = float(self.get_parameter('square_size_m').value)
        self.min_samples = int(self.get_parameter('min_samples').value)
        self.output_yaml = str(self.get_parameter('output_yaml').value)

        self.pattern_size = (self.board_cols, self.board_rows)
        self.criteria = (
            cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER,
            30,
            0.001,
        )

        self.objp = np.zeros((self.board_rows * self.board_cols, 3), np.float32)
        self.objp[:, :2] = np.mgrid[0:self.board_cols, 0:self.board_rows].T.reshape(-1, 2)
        self.objp *= self.square_size_m

        self.objpoints: List[np.ndarray] = []
        self.imgpoints: List[np.ndarray] = []
        self.image_size = None
        self.calibrated = False

        self.info_pub = self.create_publisher(CameraInfo, self.get_parameter('camera_info_output').value, 10)
        self.preview_pub = self.create_publisher(Image, self.get_parameter('preview_topic').value, 10)
        self.create_subscription(Image, self.get_parameter('image_topic').value, self.image_cb, 10)

        self.get_logger().info(
            f'Camera calibration node ready. Chessboard={self.board_cols}x{self.board_rows}, square={self.square_size_m} m, min_samples={self.min_samples}'
        )

    def image_cb(self, msg: Image):
        frame = self.bridge.imgmsg_to_cv2(msg, desired_encoding='bgr8')
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        self.image_size = (gray.shape[1], gray.shape[0])

        found, corners = cv2.findChessboardCorners(gray, self.pattern_size, None)
        preview = frame.copy()

        if found:
            corners2 = cv2.cornerSubPix(gray, corners, (11, 11), (-1, -1), self.criteria)
            cv2.drawChessboardCorners(preview, self.pattern_size, corners2, found)

            if self.should_add_sample(corners2):
                self.objpoints.append(self.objp.copy())
                self.imgpoints.append(corners2)
                self.get_logger().info(f'Added calibration sample {len(self.imgpoints)}/{self.min_samples}')

        cv2.putText(
            preview,
            f'samples: {len(self.imgpoints)}/{self.min_samples}',
            (20, 30),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.8,
            (0, 255, 255),
            2
        )

        if (not self.calibrated) and len(self.imgpoints) >= self.min_samples:
            self.run_calibration()

        if self.calibrated:
            cv2.putText(
                preview,
                'CALIBRATED',
                (20, 65),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.8,
                (0, 255, 0),
                2
            )

        self.preview_pub.publish(self.bridge.cv2_to_imgmsg(preview, encoding='bgr8'))

    def should_add_sample(self, corners: np.ndarray) -> bool:
        if not self.imgpoints:
            return True
        prev = self.imgpoints[-1]
        mean_dist = float(np.linalg.norm(corners.reshape(-1, 2) - prev.reshape(-1, 2), axis=1).mean())
        return mean_dist > 8.0

    def run_calibration(self):
        if self.image_size is None:
            return
        ok, camera_matrix, dist_coeffs, rvecs, tvecs = cv2.calibrateCamera(
            self.objpoints,
            self.imgpoints,
            self.image_size,
            None,
            None,
        )
        if not ok:
            self.get_logger().error('Calibration failed')
            return

        mean_error = 0.0
        for i in range(len(self.objpoints)):
            imgpoints2, _ = cv2.projectPoints(self.objpoints[i], rvecs[i], tvecs[i], camera_matrix, dist_coeffs)
            error = cv2.norm(self.imgpoints[i], imgpoints2, cv2.NORM_L2) / len(imgpoints2)
            mean_error += error
        mean_error /= max(1, len(self.objpoints))

        self.write_yaml(camera_matrix, dist_coeffs, mean_error)
        self.publish_camera_info(camera_matrix, dist_coeffs)
        self.calibrated = True
        self.get_logger().info(f'Calibration complete. Mean reprojection error: {mean_error:.5f}')

    def publish_camera_info(self, camera_matrix, dist_coeffs):
        if self.image_size is None:
            return
        msg = CameraInfo()
        msg.width = int(self.image_size[0])
        msg.height = int(self.image_size[1])
        msg.k = [float(x) for x in camera_matrix.reshape(-1).tolist()]
        msg.d = [float(x) for x in dist_coeffs.reshape(-1).tolist()]
        msg.r = [1.0,0.0,0.0,0.0,1.0,0.0,0.0,0.0,1.0]
        msg.p = [
            float(camera_matrix[0,0]), 0.0, float(camera_matrix[0,2]), 0.0,
            0.0, float(camera_matrix[1,1]), float(camera_matrix[1,2]), 0.0,
            0.0, 0.0, 1.0, 0.0
        ]
        self.info_pub.publish(msg)

    def write_yaml(self, camera_matrix, dist_coeffs, mean_error: float):
        out_path = Path(self.output_yaml)
        if not out_path.is_absolute():
            out_path = Path.cwd() / out_path
        out_path.parent.mkdir(parents=True, exist_ok=True)
        text = (
            "image_width: %d\n"
            "image_height: %d\n"
            "camera_name: g1_camera\n"
            "camera_matrix:\n"
            "  rows: 3\n"
            "  cols: 3\n"
            "  data: [%s]\n"
            "distortion_model: plumb_bob\n"
            "distortion_coefficients:\n"
            "  rows: 1\n"
            "  cols: %d\n"
            "  data: [%s]\n"
            "mean_reprojection_error: %.8f\n"
        ) % (
            self.image_size[0],
            self.image_size[1],
            ", ".join(f"{float(v):.10f}" for v in camera_matrix.reshape(-1)),
            int(dist_coeffs.reshape(-1).shape[0]),
            ", ".join(f"{float(v):.10f}" for v in dist_coeffs.reshape(-1)),
            float(mean_error),
        )
        out_path.write_text(text, encoding='utf-8')


def main(args=None):
    rclpy.init(args=args)
    node = CameraCalibrationNode()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()
