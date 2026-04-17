from __future__ import annotations

import json
import math
from datetime import datetime, timezone

import cv2
import numpy as np
import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Image
from std_msgs.msg import String

from .vision import DetectionPersistenceFilter, DetectorConfig, detect_spots_with_config


class LightSpotDetectorNode(Node):
    def __init__(self) -> None:
        super().__init__('light_spot_detector_node')

        self.declare_parameter('camera_topic', '/camera/image_raw')
        self.declare_parameter('detection_topic', '/light_tracking/detection_json')
        self.declare_parameter('camera_frame', 'camera_link')
        self.declare_parameter('log_detections', True)
        self.declare_parameter('detection_log_interval_s', 0.5)
        self.declare_parameter('brightness_threshold', 200)
        self.declare_parameter('blur_kernel', 11)
        self.declare_parameter('morph_kernel', 0)
        self.declare_parameter('min_area', 10.0)
        self.declare_parameter('min_detection_confidence', 0.62)
        self.declare_parameter('min_detection_score', 0.0)
        self.declare_parameter('min_persistence_frames', 1)
        self.declare_parameter('legacy_mode', False)

        self.camera_topic = self.get_parameter('camera_topic').get_parameter_value().string_value
        self.detection_topic = self.get_parameter('detection_topic').get_parameter_value().string_value
        self.camera_frame = self.get_parameter('camera_frame').get_parameter_value().string_value
        self.log_detections = self.get_parameter('log_detections').get_parameter_value().bool_value
        self.detection_log_interval_s = float(
            self.get_parameter('detection_log_interval_s').get_parameter_value().double_value
        )
        self.track_id = 1
        threshold = int(self.get_parameter('brightness_threshold').value)
        blur = int(self.get_parameter('blur_kernel').value)
        morph_kernel = int(self.get_parameter('morph_kernel').value)
        erode_iter = max(0, morph_kernel)
        dilate_iter = max(0, morph_kernel)
        min_detection_confidence = float(self.get_parameter('min_detection_confidence').value)
        # [AI-CHANGE | 2026-04-17 11:41 UTC | v0.74]
        # CO ZMIENIONO: Dodano odczyt parametru `min_detection_score` oraz klamrowanie
        # wartości do bezpiecznego zakresu [0.0, 1.0] przed przekazaniem do konfiguracji.
        # DLACZEGO: Ten próg steruje drugim etapem filtrowania jakości detekcji i musi być
        # odporny na błędne wartości wejściowe, aby nie dopuścić do niestabilnego działania.
        # JAK TO DZIAŁA: Wartość pobieramy z parametrów ROS, następnie ograniczamy przez
        # `max(0.0, min(1.0, ...))`; dzięki temu algorytm nigdy nie dostaje progu spoza
        # dozwolonego zakresu, co wspiera zasadę „lepiej brak wyniku niż błędny wynik”.
        # TODO: Rozważyć log ostrzegawczy, gdy wejściowy parametr został skorygowany
        # (klamrowanie), aby szybciej diagnozować nieprawidłową konfigurację.
        min_detection_score = float(self.get_parameter('min_detection_score').value)
        min_detection_score = max(0.0, min(1.0, min_detection_score))
        min_persistence_frames = max(1, int(self.get_parameter('min_persistence_frames').value))
        legacy_mode = bool(self.get_parameter('legacy_mode').value)
        self.detector_config = DetectorConfig(
            track_mode='brightness',
            blur=max(1, blur),
            threshold=max(0, min(255, threshold)),
            erode_iter=erode_iter,
            dilate_iter=dilate_iter,
            min_area=float(self.get_parameter('min_area').value),
            max_area=0.0,
            max_spots=1,
            color_name='red',
            hsv_lower=None,
            hsv_upper=None,
            roi=None,
            min_detection_confidence=max(0.0, min(1.0, min_detection_confidence)),
            min_detection_score=min_detection_score,  # Próg drugiego etapu filtrowania jakości detekcji.
            min_persistence_frames=min_persistence_frames,
            persistence_radius_px=12.0,
            legacy_mode=legacy_mode,
        )
        self.persistence_filter = None
        if not self.detector_config.legacy_mode:
            self.persistence_filter = DetectionPersistenceFilter(
                min_persistence_frames=self.detector_config.min_persistence_frames,
                persistence_radius_px=self.detector_config.persistence_radius_px,
            )
        self._unsupported_encodings_warned: set[str] = set()
        self._last_detection_log_time = None

        self.image_sub = self.create_subscription(Image, self.camera_topic, self.on_image, 10)
        self.detection_pub = self.create_publisher(String, self.detection_topic, 10)

        self.get_logger().info(
            f'Listening on {self.camera_topic}, publishing JSON detections to {self.detection_topic}'
        )

    def on_image(self, msg: Image) -> None:
        payload = self._empty_payload(msg)
        frame = self._image_msg_to_bgr(msg)
        if frame is not None:
            # --- ZMIANA (runtime safety) START ---
            # Zmieniony fragment: wywołanie detektora zostało osłonięte try/except.
            # Dlaczego: w środowisku R&D pojedynczy błąd konfiguracji lub jednorazowy
            # wyjątek z algorytmu nie powinien zatrzymywać callbacku i destabilizować noda.
            # Jak działa teraz: w razie wyjątku publikujemy nadal pusty payload
            # (detected=false) zamiast ryzykować publikację błędnych danych.
            # Innymi słowy: lepiej nie zwrócić detekcji niż zwrócić "głupoty".
            try:
                detections, _, _ = detect_spots_with_config(
                    frame,
                    self.detector_config,
                    persistence_filter=self.persistence_filter,
                )
                best = detections[0] if detections else None
                if best is not None:
                    payload.update(
                        {
                            'detected': True,
                            'x': float(best.x),
                            'y': float(best.y),
                            'area': float(best.area),
                            'perimeter': float(best.perimeter),
                            'circularity': float(best.circularity),
                            'radius': float(best.radius),
                            'confidence': float(best.confidence),
                            'track_id': self.track_id,
                            'rank': int(best.rank),
                            'kalman_predicted': False,
                        }
                    )
            except Exception as exc:
                # Uwaga: ostrzeżenie jest throttlowane, żeby nie floodować logów przy
                # powtarzalnym błędzie z tej samej przyczyny.
                self.get_logger().warn(
                    f'Spot detection failed: {type(exc).__name__}: {exc}',
                    throttle_duration_sec=5.0,
                )
                # TODO: dodać licznik/metrykę błędów detekcji (np. diagnostyka ROS),
                # aby monitorować trend awarii i szybciej identyfikować regresje.
            # --- ZMIANA (runtime safety) END ---

        out = String()
        out.data = json.dumps(payload, separators=(',', ':'))
        self.detection_pub.publish(out)
        self._maybe_log_detection(payload)

    def _maybe_log_detection(self, payload: dict) -> None:
        if not self.log_detections or not bool(payload.get('detected', False)):
            return

        now = self.get_clock().now()
        if self._last_detection_log_time is not None:
            elapsed = (now - self._last_detection_log_time).nanoseconds / 1e9
            if elapsed < self.detection_log_interval_s:
                return

        self._last_detection_log_time = now
        self.get_logger().info(
            'Detection: '
            f"x={float(payload.get('x', math.nan)):.3f}, "
            f"y={float(payload.get('y', math.nan)):.3f}, "
            f"area={float(payload.get('area', 0.0)):.1f}, "
            f"radius={float(payload.get('radius', 0.0)):.2f}, "
            f"track_id={int(payload.get('track_id', 0))}"
        )

    def _image_msg_to_bgr(self, msg: Image) -> np.ndarray | None:
        encoding = msg.encoding.lower()
        if msg.height <= 0 or msg.width <= 0:
            return None

        if encoding not in {'bgr8', 'rgb8', 'mono8', 'bgra8', 'rgba8'}:
            if encoding not in self._unsupported_encodings_warned:
                self._unsupported_encodings_warned.add(encoding)
                self.get_logger().warn(f'Unsupported image encoding: {msg.encoding}')
            return None

        channels = 1 if encoding == 'mono8' else (4 if encoding in {'bgra8', 'rgba8'} else 3)
        data = np.frombuffer(msg.data, dtype=np.uint8)
        needed = msg.height * msg.step
        if data.size < needed or msg.step < (msg.width * channels):
            return None

        rows = data[:needed].reshape((msg.height, msg.step))
        image = rows[:, : msg.width * channels].reshape((msg.height, msg.width, channels))

        if encoding == 'bgr8':
            return image
        if encoding == 'rgb8':
            return cv2.cvtColor(image, cv2.COLOR_RGB2BGR)
        if encoding == 'mono8':
            return cv2.cvtColor(image[:, :, 0], cv2.COLOR_GRAY2BGR)
        if encoding == 'bgra8':
            return cv2.cvtColor(image, cv2.COLOR_BGRA2BGR)
        return cv2.cvtColor(image, cv2.COLOR_RGBA2BGR)

    # [AI-CHANGE | 2026-04-17 11:35 UTC | v0.70]
    # CO ZMIENIONO: Dodano helper `_ros_stamp_to_iso_utc`, który konwertuje czas ROS
    # (`sec`, `nanosec`) na znacznik ISO-8601 w strefie UTC i zwraca `None` dla pustego
    # lub niepoprawnego znacznika.
    # DLACZEGO: Timestamp publikowany w payloadzie powinien opisywać czas pozyskania klatki,
    # a nie czas przetwarzania callbacku; to ogranicza ryzyko błędnej korelacji danych.
    # JAK TO DZIAŁA: Funkcja sprawdza, czy nagłówek ma sensowne wartości czasu. Gdy `sec`
    # i `nanosec` są zerowe (brak stempla) albo format jest błędny, zwraca `None`.
    # W przeciwnym razie buduje obiekt `datetime` w UTC i zwraca `isoformat()`.
    # TODO: Rozważyć walidację monotoniczności stempli klatek i odrzucanie ramek z czasem
    # odstającym od zegara ROS o konfigurowalny próg.
    def _ros_stamp_to_iso_utc(self, sec: int, nanosec: int) -> str | None:
        if sec == 0 and nanosec == 0:
            return None
        if sec < 0 or nanosec < 0 or nanosec >= 1_000_000_000:
            return None
        total_seconds = sec + (nanosec / 1_000_000_000.0)
        return datetime.fromtimestamp(total_seconds, tz=timezone.utc).isoformat()

    def _empty_payload(self, msg: Image) -> dict:
        header_stamp = msg.header.stamp
        # Timestamp ma odzwierciedlać czas klatki z nagłówka ROS, a nie czas przetwarzania.
        # Fallback do czasu systemowego stosujemy tylko przy pustym/zerowym nagłówku.
        payload_stamp = self._ros_stamp_to_iso_utc(header_stamp.sec, header_stamp.nanosec)
        return {
            'stamp': payload_stamp or datetime.now(timezone.utc).isoformat(),
            'frame_id': msg.header.frame_id or self.camera_frame,
            'detected': False,
            'x': math.nan,
            'y': math.nan,
            'z': math.nan,
            'x_world': math.nan,
            'y_world': math.nan,
            'z_world': math.nan,
            'area': 0.0,
            'perimeter': 0.0,
            'circularity': 0.0,
            'radius': 0.0,
            'confidence': 0.0,
            'track_id': 0,
            'rank': 0,
            'kalman_predicted': False,
        }


def main(args=None) -> None:
    rclpy.init(args=args)
    node = LightSpotDetectorNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
