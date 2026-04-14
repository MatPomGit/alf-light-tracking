import numpy as np
import rclpy
from rclpy.node import Node
from sensor_msgs.msg import CameraInfo, Image
from cv_bridge import CvBridge

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
        self.bridge = CvBridge()
        self.latest_depth = None
        self.last_depth_time = None

        self.declare_parameter('detection_topic', '/perception/detections')
        self.declare_parameter('localized_topic', '/localization/targets')
        self.declare_parameter('camera_info_topic', '/camera/camera_info')
        self.declare_parameter('depth_image_topic', '/camera/depth/image_raw')
        self.declare_parameter('enable_depth_assist', True)
        self.declare_parameter('depth_timeout_sec', 1.0)
        self.declare_parameter('depth_roi_scale', 0.35)
        self.declare_parameter('floor_z_in_base', 0.0)
        self.declare_parameter('qr_size_m', 0.08)
        self.declare_parameter('apriltag_size_m', 0.10)
        self.declare_parameter('parcel_box_dims_m', [0.30, 0.20, 0.18])

        self.enable_depth_assist = bool(self.get_parameter('enable_depth_assist').value)
        self.depth_timeout_sec = float(self.get_parameter('depth_timeout_sec').value)
        self.depth_roi_scale = float(self.get_parameter('depth_roi_scale').value)
        self.floor_z = float(self.get_parameter('floor_z_in_base').value)
        self.qr_size_m = float(self.get_parameter('qr_size_m').value)
        self.apriltag_size_m = float(self.get_parameter('apriltag_size_m').value)
        self.parcel_dims = list(self.get_parameter('parcel_box_dims_m').value)

        self.pub = self.create_publisher(LocalizedTarget, self.get_parameter('localized_topic').value, 50)
        self.create_subscription(Detection2D, self.get_parameter('detection_topic').value, self.det_cb, 50)
        self.create_subscription(CameraInfo, self.get_parameter('camera_info_topic').value, self.cam_cb, 10)
        self.create_subscription(Image, self.get_parameter('depth_image_topic').value, self.depth_cb, 10)

    def cam_cb(self, msg: CameraInfo):
        self.camera_matrix = np.array(msg.k, dtype=np.float64).reshape(3, 3)
        self.dist_coeffs = np.array(msg.d, dtype=np.float64) if msg.d else np.zeros((5,), dtype=np.float64)

    def depth_cb(self, msg: Image):
        if not self.enable_depth_assist:
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
        if not self.enable_depth_assist or self.latest_depth is None or self.last_depth_time is None:
            return False
        age = (self.get_clock().now() - self.last_depth_time).nanoseconds / 1e9
        return age <= self.depth_timeout_sec

    def depth_xyz_from_detection(self, det: Detection2D):
        if self.camera_matrix is None or not self.depth_available():
            return None
        depth = self.latest_depth
        if depth is None:
            return None

        x1 = max(0, int(det.x_min))
        y1 = max(0, int(det.y_min))
        x2 = min(depth.shape[1] - 1, int(det.x_max))
        y2 = min(depth.shape[0] - 1, int(det.y_max))
        if x2 <= x1 or y2 <= y1:
            return None

        cx = int((x1 + x2) / 2)
        cy = int((y1 + y2) / 2)
        rw = max(2, int((x2 - x1) * self.depth_roi_scale / 2.0))
        rh = max(2, int((y2 - y1) * self.depth_roi_scale / 2.0))
        rx1 = max(0, cx - rw)
        ry1 = max(0, cy - rh)
        rx2 = min(depth.shape[1] - 1, cx + rw)
        ry2 = min(depth.shape[0] - 1, cy + rh)

        roi = depth[ry1:ry2, rx1:rx2]
        valid = roi[np.isfinite(roi) & (roi > 0.05) & (roi < 20.0)]
        if valid.size < 5:
            return None

        z = float(np.median(valid))
        fx = float(self.camera_matrix[0, 0])
        fy = float(self.camera_matrix[1, 1])
        cx0 = float(self.camera_matrix[0, 2])
        cy0 = float(self.camera_matrix[1, 2])
        x = float((det.center_u - cx0) * z / fx)
        y = float((det.center_v - cy0) * z / fy)
        return x, y, z

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
        t = self.base_target(det)
        if self.camera_matrix is None:
            return t
        xyz = pixel_to_floor_plane(self.camera_matrix, det.center_u, det.center_v, self.floor_z)
        if xyz is not None:
            t.position.x, t.position.y, t.position.z = [float(v) for v in xyz]
            t.source_method = 'floor_projection'
        else:
            t.source_method = 'unknown_light'
        return t

    def localize_square_marker(self, det: Detection2D, marker_size_m: float, source_method: str):
        t = self.base_target(det)

        depth_xyz = self.depth_xyz_from_detection(det)
        if depth_xyz is not None:
            t.position.x, t.position.y, t.position.z = [float(v) for v in depth_xyz]
            t.dimensions.x = marker_size_m
            t.dimensions.y = marker_size_m
            t.dimensions.z = 0.01
            t.source_method = source_method + '_depth'
            return t

        if self.camera_matrix is None or not det.pnp_points_2d:
            t.source_method = source_method + '_unavailable'
            return t

        corners = [(pt.x, pt.y) for pt in det.pnp_points_2d]
        result = solve_square_pnp(self.camera_matrix, self.dist_coeffs, corners, marker_size_m)
        if result is None:
            t.source_method = source_method + '_failed'
            return t

        tvec, _ = result
        t.position.x = float(tvec[0])
        t.position.y = float(tvec[1])
        t.position.z = float(tvec[2])
        t.dimensions.x = marker_size_m
        t.dimensions.y = marker_size_m
        t.dimensions.z = 0.01
        t.source_method = source_method
        return t

    def localize_parcel_box(self, det: Detection2D):
        t = self.base_target(det)
        depth_xyz = self.depth_xyz_from_detection(det)
        if depth_xyz is not None:
            t.position.x, t.position.y, t.position.z = [float(v) for v in depth_xyz]
            t.dimensions.x = float(self.parcel_dims[0])
            t.dimensions.y = float(self.parcel_dims[1])
            t.dimensions.z = float(self.parcel_dims[2])
            t.source_method = 'depth_box'
            return t

        width_px = max(1.0, det.x_max - det.x_min)
        z = estimate_depth_from_known_width(self.camera_matrix, width_px, self.parcel_dims[0]) if self.camera_matrix is not None else 1.5
        t.position.z = float(z)
        t.position.x = float((det.center_u - (self.camera_matrix[0, 2] if self.camera_matrix is not None else 320.0)) / 600.0)
        t.position.y = 0.0
        t.dimensions.x = float(self.parcel_dims[0])
        t.dimensions.y = float(self.parcel_dims[1])
        t.dimensions.z = float(self.parcel_dims[2])
        t.source_method = 'known_width_box'
        return t

    def localize_bbox_target(self, det: Detection2D):
        t = self.base_target(det)
        depth_xyz = self.depth_xyz_from_detection(det)
        if depth_xyz is not None:
            t.position.x, t.position.y, t.position.z = [float(v) for v in depth_xyz]
            t.source_method = 'depth_bbox'
            return t

        width_px = max(1.0, det.x_max - det.x_min)
        nominal_width = 0.5 if det.target_type == 'person' else 0.8
        z = estimate_depth_from_known_width(self.camera_matrix, width_px, nominal_width) if self.camera_matrix is not None else 2.0
        t.position.z = float(z)
        t.position.x = float((det.center_u - (self.camera_matrix[0, 2] if self.camera_matrix is not None else 320.0)) / 600.0)
        t.position.y = 0.0
        t.source_method = 'known_width_bbox'
        return t


def main(args=None):
    rclpy.init(args=args)
    node = LocalizationNode()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()
