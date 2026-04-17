# [MatPom-CHANGE | 2026-04-17 13:06 UTC | v0.91]
# CO ZMIENIONO: Dodano komentarze opisujące przeznaczenie klas i metod oraz motywację przyjętej struktury.
# DLACZEGO: Ułatwia to bezpieczne utrzymanie kodu R&D i ogranicza ryzyko błędnej interpretacji logiki detekcji.
# JAK TO DZIAŁA: Każda klasa/metoda posiada docstring z celem i uzasadnieniem, dzięki czemu intencja implementacji jest jawna.
# TODO: Rozszerzyć docstringi o kontrakty wejścia/wyjścia po ustabilizowaniu API między węzłami.

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
    """
    Cel: Ta klasa realizuje odpowiedzialność `LightSpotDetectorNode` w aktualnym module.
    Dlaczego tak: Wydzielenie tej jednostki upraszcza debugowanie i chroni krytyczne ścieżki przed niekontrolowanymi zmianami.
    """
    def __init__(self) -> None:
        """
        Cel: Ta metoda realizuje odpowiedzialność `__init__` w aktualnym module.
        Dlaczego tak: Wydzielenie tej jednostki upraszcza debugowanie i chroni krytyczne ścieżki przed niekontrolowanymi zmianami.
        """
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
        # [MatPom-CHANGE | 2026-04-17 14:20 UTC | v0.103]
        # CO ZMIENIONO: Zaktualizowano domyślne wartości deklarowanych progów
        # `min_detection_score` i `min_top1_top2_margin` na wartości startowe z YAML.
        # DLACZEGO: Spójność domyślnych parametrów noda i konfiguracji plikowej
        # ogranicza ryzyko niejawnego rozjazdu zachowania detektora.
        # JAK TO DZIAŁA: Gdy YAML nie poda wartości, node użyje bezpiecznych progów
        # 0.10 i 0.04, które preferują odrzucenie niepewnych kandydatów.
        # TODO: Dodać test jednostkowy sprawdzający zgodność domyślnych wartości
        # między `perception.yaml`, deklaracją ROS i `DetectorConfig`.
        self.declare_parameter('min_detection_confidence', 0.62)
        self.declare_parameter('min_detection_score', 0.10)
        self.declare_parameter('min_top1_top2_margin', 0.04)
        # [MatPom-CHANGE | 2026-04-17 14:20 UTC | v0.103]
        # CO ZMIENIONO: Dodano deklaracje parametrów jakości fotometrycznej i wag
        # pewności, które są mapowane bezpośrednio do `DetectorConfig`.
        # DLACZEGO: Parametry mają być jawnie konfigurowalne z YAML, aby strojenie
        # bezpieczeństwa nie wymagało zmian kodu.
        # JAK TO DZIAŁA: Każde pole ma wartość domyślną zgodną z `DetectorConfig`,
        # a dalsza walidacja klamruje skrajnie ryzykowne wartości.
        # TODO: Dodać callback `on_set_parameters` z walidacją online bez restartu noda.
        self.declare_parameter('ring_thickness_px', 2)
        self.declare_parameter('saturation_level', 250)
        self.declare_parameter('min_mean_contrast', 4.0)
        self.declare_parameter('min_peak_sharpness', 6.0)
        self.declare_parameter('max_saturated_ratio', 0.35)
        self.declare_parameter('confidence_weight_shape', 0.32)
        self.declare_parameter('confidence_weight_brightness', 0.22)
        self.declare_parameter('confidence_weight_contrast', 0.24)
        self.declare_parameter('confidence_weight_sharpness', 0.22)
        self.declare_parameter('confidence_saturation_penalty_weight', 0.35)
        self.declare_parameter('min_persistence_frames', 1)
        # [MatPom-CHANGE | 2026-04-17 13:12 UTC | v0.99]
        # CO ZMIENIONO: Dodano parametry ROS dla dynamicznego ROI.
        # DLACZEGO: Konfiguracja musi umożliwiać zawężanie/rozszerzanie obszaru
        # detekcji wokół przewidywanej pozycji toru bez modyfikacji kodu.
        # JAK TO DZIAŁA: Parametry sterują aktywacją trybu, bazowym rozmiarem okna
        # i krokiem rozszerzania przy kolejnych klatkach bez potwierdzonej detekcji.
        # TODO: Dodać walidację zależną od rozdzielczości strumienia kamery.
        self.declare_parameter('dynamic_roi_enabled', False)
        self.declare_parameter('dynamic_roi_size_px', 160)
        self.declare_parameter('dynamic_roi_expand_on_miss', 40)
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
        # [MatPom-CHANGE | 2026-04-17 11:41 UTC | v0.74]
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
        # [MatPom-CHANGE | 2026-04-17 12:19 UTC | v0.84]
        # CO ZMIENIONO: Dodano odczyt parametru `min_top1_top2_margin` z walidacją
        # dolnego ograniczenia do zera przed przekazaniem do konfiguracji detektora.
        # DLACZEGO: Parametr steruje odrzucaniem niejednoznacznych detekcji, więc
        # wartości ujemne nie mają sensu i mogłyby osłabić regułę bezpieczeństwa.
        # JAK TO DZIAŁA: Wartość pobierana z ROS jest klamrowana przez `max(0.0, ...)`,
        # a potem używana w `DetectorConfig` do decyzji top1-vs-top2.
        # TODO: Udostępnić dynamiczną rekonfigurację progu bez restartu noda.
        min_top1_top2_margin = max(0.0, float(self.get_parameter('min_top1_top2_margin').value))
        # [MatPom-CHANGE | 2026-04-17 14:20 UTC | v0.103]
        # CO ZMIENIONO: Dodano centralną walidację i klamrowanie nowych parametrów
        # jakości detekcji (progi, poziom saturacji, grubość pierścienia, wagi pewności).
        # DLACZEGO: Skrajne wartości mogą osłabić selekcję kandydatów albo destabilizować
        # scoring, dlatego muszą być bezpiecznie ograniczane przed użyciem.
        # JAK TO DZIAŁA: Lokalne helpery `_clamp_float` i `_clamp_int` ograniczają
        # wartości do zakresu roboczego; dodatkowo normalizujemy sumę wag > 0.
        # TODO: Dodać licznik metryk pokazujący częstość klamrowania parametrów w runtime.
        def _clamp_float(name: str, value: float, lower: float, upper: float) -> float:
            clamped = max(lower, min(upper, value))
            if clamped != value:
                self.get_logger().warn(
                    f'Parameter {name}={value} out of range [{lower}, {upper}], '
                    f'using {clamped} for safety.'
                )
            return clamped

        def _clamp_int(name: str, value: int, lower: int, upper: int) -> int:
            clamped = max(lower, min(upper, value))
            if clamped != value:
                self.get_logger().warn(
                    f'Parameter {name}={value} out of range [{lower}, {upper}], '
                    f'using {clamped} for safety.'
                )
            return clamped

        ring_thickness_px = _clamp_int('ring_thickness_px', int(self.get_parameter('ring_thickness_px').value), 1, 32)
        saturation_level = _clamp_int('saturation_level', int(self.get_parameter('saturation_level').value), 1, 255)
        min_mean_contrast = _clamp_float(
            'min_mean_contrast',
            float(self.get_parameter('min_mean_contrast').value),
            0.0,
            255.0,
        )
        min_peak_sharpness = _clamp_float(
            'min_peak_sharpness',
            float(self.get_parameter('min_peak_sharpness').value),
            0.0,
            255.0,
        )
        max_saturated_ratio = _clamp_float(
            'max_saturated_ratio',
            float(self.get_parameter('max_saturated_ratio').value),
            0.0,
            1.0,
        )
        confidence_weight_shape = _clamp_float(
            'confidence_weight_shape',
            float(self.get_parameter('confidence_weight_shape').value),
            0.0,
            1.0,
        )
        confidence_weight_brightness = _clamp_float(
            'confidence_weight_brightness',
            float(self.get_parameter('confidence_weight_brightness').value),
            0.0,
            1.0,
        )
        confidence_weight_contrast = _clamp_float(
            'confidence_weight_contrast',
            float(self.get_parameter('confidence_weight_contrast').value),
            0.0,
            1.0,
        )
        confidence_weight_sharpness = _clamp_float(
            'confidence_weight_sharpness',
            float(self.get_parameter('confidence_weight_sharpness').value),
            0.0,
            1.0,
        )
        confidence_saturation_penalty_weight = _clamp_float(
            'confidence_saturation_penalty_weight',
            float(self.get_parameter('confidence_saturation_penalty_weight').value),
            0.0,
            1.0,
        )
        confidence_weight_sum = (
            confidence_weight_shape
            + confidence_weight_brightness
            + confidence_weight_contrast
            + confidence_weight_sharpness
        )
        if confidence_weight_sum <= 0.0:
            self.get_logger().warn(
                'Confidence weights sum to 0.0; restoring safe defaults '
                '(shape=0.32, brightness=0.22, contrast=0.24, sharpness=0.22).'
            )
            confidence_weight_shape = 0.32
            confidence_weight_brightness = 0.22
            confidence_weight_contrast = 0.24
            confidence_weight_sharpness = 0.22
        min_persistence_frames = max(1, int(self.get_parameter('min_persistence_frames').value))
        # [MatPom-CHANGE | 2026-04-17 13:12 UTC | v0.99]
        # CO ZMIENIONO: Dodano odczyt i walidację parametrów dynamicznego ROI.
        # DLACZEGO: Potrzebujemy bezpiecznych wartości wejściowych, aby nie tworzyć
        # zbyt małego lub ujemnie rozszerzanego okna detekcji.
        # JAK TO DZIAŁA: Rozmiar ROI jest klamrowany do minimum 1 px, a przyrost
        # rozszerzania przy missie do zakresu >=0, co eliminuje konfiguracje patologiczne.
        # TODO: Publikować ostrzeżenie, gdy parametry zostały skorygowane klamrowaniem.
        dynamic_roi_enabled = bool(self.get_parameter('dynamic_roi_enabled').value)
        dynamic_roi_size_px = max(1, int(self.get_parameter('dynamic_roi_size_px').value))
        dynamic_roi_expand_on_miss = max(0, int(self.get_parameter('dynamic_roi_expand_on_miss').value))
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
            min_top1_top2_margin=min_top1_top2_margin,
            ring_thickness_px=ring_thickness_px,
            saturation_level=saturation_level,
            min_mean_contrast=min_mean_contrast,
            min_peak_sharpness=min_peak_sharpness,
            max_saturated_ratio=max_saturated_ratio,
            confidence_weight_shape=confidence_weight_shape,
            confidence_weight_brightness=confidence_weight_brightness,
            confidence_weight_contrast=confidence_weight_contrast,
            confidence_weight_sharpness=confidence_weight_sharpness,
            confidence_saturation_penalty_weight=confidence_saturation_penalty_weight,
            min_persistence_frames=min_persistence_frames,
            persistence_radius_px=12.0,
            dynamic_roi_enabled=dynamic_roi_enabled,
            dynamic_roi_size_px=dynamic_roi_size_px,
            dynamic_roi_expand_on_miss=dynamic_roi_expand_on_miss,
            legacy_mode=legacy_mode,
        )
        self.persistence_filter = None
        if not self.detector_config.legacy_mode:
            # [MatPom-CHANGE | 2026-04-17 13:12 UTC | v0.99]
            # CO ZMIENIONO: Filtr persystencji otrzymuje parametry dynamicznego ROI.
            # DLACZEGO: Bez przekazania tych pól filtr nie mógłby sterować obszarem
            # przeszukiwania na podstawie potwierdzonego toru i serii missów.
            # JAK TO DZIAŁA: Konstruktor filtra dostaje konfigurację `dynamic_roi_*`,
            # dzięki czemu `detect_spots_with_config` może wyznaczać lokalne ROI.
            # TODO: Ujednolicić inicjalizację konfiguracji przez jedną fabrykę obiektów.
            self.persistence_filter = DetectionPersistenceFilter(
                min_persistence_frames=self.detector_config.min_persistence_frames,
                persistence_radius_px=self.detector_config.persistence_radius_px,
                dynamic_roi_enabled=self.detector_config.dynamic_roi_enabled,
                dynamic_roi_size_px=self.detector_config.dynamic_roi_size_px,
                dynamic_roi_expand_on_miss=self.detector_config.dynamic_roi_expand_on_miss,
            )
        self._unsupported_encodings_warned: set[str] = set()
        self._last_detection_log_time = None

        self.image_sub = self.create_subscription(Image, self.camera_topic, self.on_image, 10)
        self.detection_pub = self.create_publisher(String, self.detection_topic, 10)

        self.get_logger().info(
            f'Listening on {self.camera_topic}, publishing JSON detections to {self.detection_topic}'
        )

    def on_image(self, msg: Image) -> None:
        """
        Cel: Ta metoda realizuje odpowiedzialność `on_image` w aktualnym module.
        Dlaczego tak: Wydzielenie tej jednostki upraszcza debugowanie i chroni krytyczne ścieżki przed niekontrolowanymi zmianami.
        """
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
                detections, _, _, diagnostics = detect_spots_with_config(
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
                # [MatPom-CHANGE | 2026-04-17 12:19 UTC | v0.84]
                # CO ZMIENIONO: Dodano throttlowane logowanie przyczyn odrzucenia
                # detekcji, w szczególności `ambiguous_candidates` i marginesu top1-top2.
                # DLACZEGO: Diagnostyka ułatwia strojenie progu i pozwala odróżnić
                # brak detekcji od aktywnego odrzucenia niepewnego wyniku.
                # JAK TO DZIAŁA: Gdy detekcja jest pusta i moduł poda `rejection_reason`,
                # node emituje ostrzeżenie z wartościami marginesu i progu, z throttlingiem.
                # TODO: Wystawić powód odrzucenia także w payloadzie diagnostycznym ROS.
                if best is None and diagnostics.get('rejection_reason'):
                    reason = str(diagnostics.get('rejection_reason'))
                    margin = float(diagnostics.get('top1_top2_margin', 0.0))
                    margin_pct = float(diagnostics.get('top1_top2_margin_pct', 0.0))
                    min_margin = float(diagnostics.get('min_top1_top2_margin', 0.0))
                    self.get_logger().warn(
                        'Detection rejected: '
                        f'reason={reason}, margin={margin:.4f}, '
                        f'margin_pct={margin_pct:.2f}%, min_margin={min_margin:.4f}',
                        throttle_duration_sec=2.0,
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
        """
        Cel: Ta metoda realizuje odpowiedzialność `_maybe_log_detection` w aktualnym module.
        Dlaczego tak: Wydzielenie tej jednostki upraszcza debugowanie i chroni krytyczne ścieżki przed niekontrolowanymi zmianami.
        """
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
        """
        Cel: Ta metoda realizuje odpowiedzialność `_image_msg_to_bgr` w aktualnym module.
        Dlaczego tak: Wydzielenie tej jednostki upraszcza debugowanie i chroni krytyczne ścieżki przed niekontrolowanymi zmianami.
        """
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

    # [MatPom-CHANGE | 2026-04-17 11:35 UTC | v0.70]
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
        """
        Cel: Ta metoda realizuje odpowiedzialność `_ros_stamp_to_iso_utc` w aktualnym module.
        Dlaczego tak: Wydzielenie tej jednostki upraszcza debugowanie i chroni krytyczne ścieżki przed niekontrolowanymi zmianami.
        """
        if sec == 0 and nanosec == 0:
            return None
        if sec < 0 or nanosec < 0 or nanosec >= 1_000_000_000:
            return None
        total_seconds = sec + (nanosec / 1_000_000_000.0)
        return datetime.fromtimestamp(total_seconds, tz=timezone.utc).isoformat()

    def _empty_payload(self, msg: Image) -> dict:
        """
        Cel: Ta metoda realizuje odpowiedzialność `_empty_payload` w aktualnym module.
        Dlaczego tak: Wydzielenie tej jednostki upraszcza debugowanie i chroni krytyczne ścieżki przed niekontrolowanymi zmianami.
        """
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
    """
    Cel: Ta funkcja realizuje odpowiedzialność `main` w aktualnym module.
    Dlaczego tak: Wydzielenie tej jednostki upraszcza debugowanie i chroni krytyczne ścieżki przed niekontrolowanymi zmianami.
    """
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
