import numpy as np
import rclpy
from rclpy.node import Node
from sensor_msgs.msg import CameraInfo

from g1_light_tracking.msg import Detection2D, LocalizedTarget
from g1_light_tracking.utils.geometry import (
    solve_square_pnp,
    pixel_to_floor_plane,
    estimate_depth_from_known_width,
)


class LocalizationNode(Node):
    def __init__(self):
        super().__init__('localization_node')
        self.camera_matrix = None
        self.dist_coeffs = None

        self.declare_parameter('detection_topic', '/perception/detections')
        self.declare_parameter('localized_topic', '/localization/targets')
        self.declare_parameter('camera_info_topic', '/camera/camera_info')
        self.declare_parameter('floor_z_in_base', 0.0)
        self.declare_parameter('qr_size_m', 0.08)
        self.declare_parameter('apriltag_size_m', 0.10)
        self.declare_parameter('parcel_box_dims_m', [0.30, 0.20, 0.18])

        self.floor_z = float(self.get_parameter('floor_z_in_base').value)
        self.qr_size_m = float(self.get_parameter('qr_size_m').value)
        self.apriltag_size_m = float(self.get_parameter('apriltag_size_m').value)
        self.parcel_dims = list(self.get_parameter('parcel_box_dims_m').value)

        self.pub = self.create_publisher(LocalizedTarget, self.get_parameter('localized_topic').value, 50)
        self.create_subscription(Detection2D, self.get_parameter('detection_topic').value, self.det_cb, 50)
        self.create_subscription(CameraInfo, self.get_parameter('camera_info_topic').value, self.cam_cb, 10)

    def cam_cb(self, msg: CameraInfo):
        self.camera_matrix = np.array(msg.k, dtype=np.float64).reshape(3, 3)
        self.dist_coeffs = np.array(msg.d, dtype=np.float64) if msg.d else np.zeros((5,), dtype=np.float64)

    def det_cb(self, det: Detection2D):
        target = None
        if det.target_type == 'light_spot':
            target = self.localize_light(det)
        elif det.target_type == 'qr':
            target = self.localize_square_marker(det, self.qr_size_m, 'pnp_qr')
        elif det.target_type == 'apriltag':
            target = self.localize_square_marker(det, self.apriltag_size_m, 'pnp_apriltag')
        elif det.target_type == 'parcel_box':
            target = self.localize_parcel_box(det)
        elif det.target_type in ('person', 'shelf', 'planar_surface'):
            target = self.localize_bbox_target(det)
        if target is not None:
            self.pub.publish(target)

    def base_target(self, det: Detection2D):
        t = LocalizedTarget()
        t.stamp = det.stamp
        t.frame_id = det.frame_id
        t.target_type = det.target_type
        t.class_name = det.class_name
        t.confidence = det.confidence
        t.center_u = det.center_u
        t.center_v = det.center_v
        t.x_min = det.x_min
        t.y_min = det.y_min
        t.x_max = det.x_max
        t.y_max = det.y_max
        t.color_label = det.color_label
        t.payload = det.payload
        return t

    def localize_light(self, det: Detection2D):
        if self.camera_matrix is None:
            return None
        xyz = pixel_to_floor_plane(det.center_u, det.center_v, self.camera_matrix, self.floor_z)
        if xyz is None:
            return None
        t = self.base_target(det)
        t.position.x, t.position.y, t.position.z = xyz
        t.source_method = 'floor_projection'
        return t

    def localize_square_marker(self, det: Detection2D, size_m: float, source_method: str):
        if self.camera_matrix is None or self.dist_coeffs is None or len(det.image_points) != 8:
            return None
        points = []
        vals = list(det.image_points)
        for i in range(0, 8, 2):
            points.append([vals[i], vals[i + 1]])
        result = solve_square_pnp(points, self.camera_matrix, self.dist_coeffs, size_m)
        if result is None:
            return None
        _rvec, tvec = result
        t = self.base_target(det)
        t.position.x = float(tvec[0][0])
        t.position.y = float(tvec[1][0])
        t.position.z = float(tvec[2][0])
        t.source_method = source_method
        return t

    def localize_parcel_box(self, det: Detection2D):
        # Preferred path: QR attached to the carton and handled by qr PnP.
        # Fallback path here: estimate depth from known carton width and camera intrinsics.
        if self.camera_matrix is None:
            return self.localize_bbox_target(det)
        pixel_width = max(1.0, float(det.x_max - det.x_min))
        focal_x = float(self.camera_matrix[0, 0])
        real_width = float(self.parcel_dims[0]) if self.parcel_dims else 0.30
        z = estimate_depth_from_known_width(pixel_width, focal_x, real_width)
        if z is None:
            return self.localize_bbox_target(det)
        t = self.base_target(det)
        x_norm = float((det.center_u - self.camera_matrix[0, 2]) / max(1.0, focal_x))
        t.position.x = x_norm * z
        t.position.y = 0.0
        t.position.z = z
        t.dimensions.x = real_width
        t.dimensions.y = float(self.parcel_dims[1]) if len(self.parcel_dims) > 1 else 0.20
        t.dimensions.z = float(self.parcel_dims[2]) if len(self.parcel_dims) > 2 else 0.18
        t.source_method = 'bbox_known_dimensions'
        return t

    def localize_bbox_target(self, det: Detection2D):
        if self.camera_matrix is None:
            return None
        pixel_width = max(1.0, float(det.x_max - det.x_min))
        z = max(0.5, min(5.0, 300.0 / pixel_width))
        focal_x = float(self.camera_matrix[0, 0])
        x_norm = float((det.center_u - self.camera_matrix[0, 2]) / max(1.0, focal_x))
        t = self.base_target(det)
        t.position.x = x_norm * z
        t.position.y = 0.0
        t.position.z = z
        t.source_method = 'bbox_heuristic'
        return t

def main(args=None):
    rclpy.init(args=args)
    node = LocalizationNode()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()
