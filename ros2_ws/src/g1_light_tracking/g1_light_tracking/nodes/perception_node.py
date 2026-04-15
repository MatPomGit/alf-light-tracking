"""ROS 2 node odpowiedzialny za etap percepcji 2D.

Node odbiera obraz z kamery i publikuje zunifikowane detekcje w postaci `Detection2D`.
Łączy kilka źródeł informacji: klasyczne wykrywanie plamki światła, dekodowanie QR,
wykrywanie markerów AprilTag oraz opcjonalnie model YOLO dla obiektów ogólnych.

Celem modułu nie jest jeszcze estymacja 3D ani utrzymanie tożsamości w czasie.
PerceptionNode dostarcza jedynie chwilowy obraz sceny w układzie pikselowym,
który następne moduły zamieniają na pozycje przestrzenne i stabilne tracki.
"""

from typing import List, Optional
import cv2
import numpy as np
import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Image, CameraInfo
from cv_bridge import CvBridge

from g1_light_tracking.msg import Detection2D
from g1_light_tracking.utils.geometry import dominant_color_bgr

try:
    from ultralytics import YOLO
except Exception:
    YOLO = None

try:
    from pyzbar.pyzbar import decode as decode_qr
except Exception:
    decode_qr = None

try:
    from pupil_apriltags import Detector as AprilTagDetector
except Exception:
    AprilTagDetector = None


class PerceptionNode(Node):
    def __init__(self):
        super().__init__('perception_node')
        self.bridge = CvBridge()
        self.last_camera_info: Optional[CameraInfo] = None

        self.declare_parameter('image_topic', '/camera/image_raw')
        self.declare_parameter('camera_info_topic', '/camera/camera_info')
        self.declare_parameter('detection_topic', '/perception/detections')
        self.declare_parameter('debug_image_topic', '/debug/perception_image')
        self.declare_parameter('yolo_model_path', 'yolov8n.pt')
        self.declare_parameter('yolo_confidence', 0.35)
        self.declare_parameter('enable_qr', True)
        self.declare_parameter('enable_apriltag', True)
        self.declare_parameter('enable_light_spot', True)
        self.declare_parameter('light_threshold', 240)
        self.declare_parameter('target_classes', ['person', 'box', 'package', 'shelf', 'bookcase', 'table'])

        self.detection_topic = self.get_parameter('detection_topic').value
        self.yolo_conf = float(self.get_parameter('yolo_confidence').value)
        self.enable_qr = bool(self.get_parameter('enable_qr').value)
        self.enable_apriltag = bool(self.get_parameter('enable_apriltag').value)
        self.enable_light_spot = bool(self.get_parameter('enable_light_spot').value)
        self.light_threshold = int(self.get_parameter('light_threshold').value)
        self.target_classes = set(self.get_parameter('target_classes').value)

        self.pub = self.create_publisher(Detection2D, self.detection_topic, 50)
        self.debug_pub = self.create_publisher(Image, self.get_parameter('debug_image_topic').value, 10)

        self.create_subscription(Image, self.get_parameter('image_topic').value, self.image_cb, 10)
        self.create_subscription(CameraInfo, self.get_parameter('camera_info_topic').value, self.camera_info_cb, 10)

        self.model = None
        if YOLO is not None:
            try:
                self.model = YOLO(self.get_parameter('yolo_model_path').value)
                self.get_logger().info('YOLO model loaded')
            except Exception as exc:
                self.get_logger().warning(f'YOLO load failed: {exc}')

        self.apriltag_detector = None
        if AprilTagDetector is not None and self.enable_apriltag:
            try:
                self.apriltag_detector = AprilTagDetector(families='tag36h11')
                self.get_logger().info('AprilTag detector loaded')
            except Exception as exc:
                self.get_logger().warning(f'AprilTag init failed: {exc}')

    def camera_info_cb(self, msg: CameraInfo):
        self.last_camera_info = msg

    def image_cb(self, msg: Image):
        frame = self.bridge.imgmsg_to_cv2(msg, desired_encoding='bgr8')
        detections: List[Detection2D] = []

        if self.enable_light_spot:
            det = self.detect_light_spot(frame, msg)
            if det:
                detections.append(det)

        if self.enable_qr:
            detections.extend(self.detect_qr(frame, msg))

        if self.enable_apriltag:
            detections.extend(self.detect_apriltag(frame, msg))

        detections.extend(self.detect_yolo(frame, msg))

        for det in detections:
            self.pub.publish(det)

        debug = self.draw_debug(frame.copy(), detections)
        self.debug_pub.publish(self.bridge.cv2_to_imgmsg(debug, encoding='bgr8'))

    def build_det(self, image_msg: Image, target_type: str, class_name: str = ''):
        det = Detection2D()
        det.stamp = image_msg.header.stamp
        det.frame_id = image_msg.header.frame_id
        det.target_type = target_type
        det.class_name = class_name
        return det

    def detect_light_spot(self, frame, image_msg):
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        _, mask = cv2.threshold(gray, self.light_threshold, 255, cv2.THRESH_BINARY)
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            return None
        contour = max(contours, key=cv2.contourArea)
        if cv2.contourArea(contour) < 20.0:
            return None
        x, y, w, h = cv2.boundingRect(contour)
        roi = frame[y:y+h, x:x+w]
        det = self.build_det(image_msg, 'light_spot')
        det.confidence = 1.0
        det.x_min = float(x); det.y_min = float(y); det.x_max = float(x + w); det.y_max = float(y + h)
        det.center_u = float(x + w / 2.0); det.center_v = float(y + h / 2.0)
        det.color_label = dominant_color_bgr(roi)
        return det

    def detect_qr(self, frame, image_msg):
        out = []
        if decode_qr is None:
            return out
        try:
            decoded = decode_qr(frame)
            for item in decoded:
                rect = item.rect
                det = self.build_det(image_msg, 'qr')
                det.confidence = 1.0
                det.x_min = float(rect.left); det.y_min = float(rect.top)
                det.x_max = float(rect.left + rect.width); det.y_max = float(rect.top + rect.height)
                det.center_u = float(rect.left + rect.width / 2.0)
                det.center_v = float(rect.top + rect.height / 2.0)
                det.payload = item.data.decode('utf-8', errors='ignore')
                if item.polygon:
                    flat = []
                    for p in item.polygon[:4]:
                        flat.extend([float(p.x), float(p.y)])
                    det.image_points = flat
                out.append(det)
        except Exception as exc:
            self.get_logger().warning(f'QR detection failed: {exc}')
        return out

    def detect_apriltag(self, frame, image_msg):
        out = []
        if self.apriltag_detector is None:
            return out
        try:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            tags = self.apriltag_detector.detect(gray)
            for tag in tags:
                pts = tag.corners
                det = self.build_det(image_msg, 'apriltag', 'apriltag')
                det.confidence = 1.0
                xs = [float(p[0]) for p in pts]
                ys = [float(p[1]) for p in pts]
                det.x_min = min(xs); det.y_min = min(ys); det.x_max = max(xs); det.y_max = max(ys)
                det.center_u = float(tag.center[0]); det.center_v = float(tag.center[1])
                det.payload = f'tag_id={tag.tag_id}'
                flat = []
                for p in pts:
                    flat.extend([float(p[0]), float(p[1])])
                det.image_points = flat
                out.append(det)
        except Exception as exc:
            self.get_logger().warning(f'AprilTag detection failed: {exc}')
        return out

    def detect_yolo(self, frame, image_msg):
        out = []
        if self.model is None:
            return out
        try:
            results = self.model.predict(frame, conf=self.yolo_conf, verbose=False)
            if not results:
                return out
            result = results[0]
            if result.boxes is None:
                return out
            names = result.names
            for box in result.boxes:
                cls_id = int(box.cls[0].item())
                conf = float(box.conf[0].item())
                x1, y1, x2, y2 = [float(v) for v in box.xyxy[0].tolist()]
                class_name = str(names.get(cls_id, cls_id))
                if class_name not in self.target_classes:
                    continue
                semantic = class_name
                if class_name in {'box', 'package'}:
                    semantic = 'parcel_box'
                elif class_name in {'bookcase', 'shelf'}:
                    semantic = 'shelf'
                elif class_name == 'table':
                    semantic = 'planar_surface'
                det = self.build_det(image_msg, semantic, class_name)
                det.confidence = conf
                det.x_min = x1; det.y_min = y1; det.x_max = x2; det.y_max = y2
                det.center_u = float((x1 + x2) / 2.0); det.center_v = float((y1 + y2) / 2.0)
                out.append(det)
        except Exception as exc:
            self.get_logger().warning(f'YOLO inference failed: {exc}')
        return out

    def draw_debug(self, frame, detections):
        for det in detections:
            x1, y1, x2, y2 = int(det.x_min), int(det.y_min), int(det.x_max), int(det.y_max)
            cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
            label = det.target_type
            if det.class_name:
                label += f'({det.class_name})'
            if det.color_label:
                label += f' {det.color_label}'
            if det.payload:
                label += f' {det.payload[:20]}'
            cv2.putText(frame, label, (x1, max(20, y1 - 5)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)
        return frame

def main(args=None):
    rclpy.init(args=args)
    node = PerceptionNode()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()
