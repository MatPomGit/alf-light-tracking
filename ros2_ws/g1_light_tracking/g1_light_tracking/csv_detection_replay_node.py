import csv
import json
import math
from datetime import datetime, timezone

import rclpy
from rclpy.node import Node
from std_msgs.msg import String


class CsvDetectionReplayNode(Node):
    """
    Cel: Ta klasa realizuje odpowiedzialność `CsvDetectionReplayNode` w aktualnym module.
    Dlaczego tak: Wydzielenie tej jednostki upraszcza debugowanie i chroni krytyczne ścieżki przed niekontrolowanymi zmianami.
    """
    def __init__(self) -> None:
        """
        Cel: Ta metoda realizuje odpowiedzialność `__init__` w aktualnym module.
        Dlaczego tak: Wydzielenie tej jednostki upraszcza debugowanie i chroni krytyczne ścieżki przed niekontrolowanymi zmianami.
        """
        super().__init__('csv_detection_replay_node')

        self.declare_parameter('csv_file', '')
        self.declare_parameter('detection_topic', '/light_tracking/detection_json')
        self.declare_parameter('frame_id', 'camera_link')
        self.declare_parameter('playback_rate', 1.0)
        self.declare_parameter('loop', True)

        self.csv_file = str(self.get_parameter('csv_file').value)
        self.detection_topic = str(self.get_parameter('detection_topic').value)
        self.frame_id = str(self.get_parameter('frame_id').value)
        self.playback_rate = float(self.get_parameter('playback_rate').value)
        self.loop = bool(self.get_parameter('loop').value)
        # [AI-CHANGE | 2026-04-17 15:53 UTC | v0.120]
        # CO ZMIENIONO: Dodano normalizację `playback_rate` do bezpiecznej wartości
        # dodatniej przed startem timera.
        # DLACZEGO: Wartości `<= 0` powodują niepoprawny harmonogram odtwarzania
        # (brak progresu czasu lub cofanie), co skutkowało ciszą na topicu i
        # trudnym debugowaniem.
        # JAK TO DZIAŁA: Gdy użytkownik poda `playback_rate <= 0`, node loguje
        # ostrzeżenie i wymusza `1.0`, dzięki czemu odtwarzanie zawsze postępuje.
        # TODO: Dodać callback walidacji parametrów runtime (`on_set_parameters`)
        # aby odrzucać niepoprawne wartości przed ich przyjęciem przez node.
        if self.playback_rate <= 0.0:
            self.get_logger().warning(
                'Parameter playback_rate <= 0.0. Fallback do 1.0, aby uniknąć niepewnego odtwarzania.'
            )
            self.playback_rate = 1.0

        self.pub = self.create_publisher(String, self.detection_topic, 10)
        self.rows = self._load_rows(self.csv_file)
        self.index = 0
        self.start_time = self.get_clock().now()
        self.timer = self.create_timer(0.01, self.on_timer)

        self.get_logger().info(
            f'CSV replay ready: rows={len(self.rows)}, rate={self.playback_rate}x, loop={self.loop}'
        )

    def _load_rows(self, path: str) -> list:
        """
        Cel: Ta metoda realizuje odpowiedzialność `_load_rows` w aktualnym module.
        Dlaczego tak: Wydzielenie tej jednostki upraszcza debugowanie i chroni krytyczne ścieżki przed niekontrolowanymi zmianami.
        """
        if not path:
            self.get_logger().error('Parameter csv_file is empty.')
            return []

        rows = []
        # [AI-CHANGE | 2026-04-17 15:53 UTC | v0.120]
        # CO ZMIENIONO: Dodano obsługę błędów I/O podczas odczytu CSV oraz
        # filtrowanie rekordów z niepoprawnym `time_sec`.
        # DLACZEGO: Brak pliku lub uszkodzony rekord mógł przerwać node albo
        # doprowadzić do publikowania danych z niejednoznacznym czasem.
        # JAK TO DZIAŁA: Błędy otwarcia są zamieniane na pusty wynik i log błędu.
        # Rekord z `NaN/Inf` w `time_sec` jest pomijany, aby nie publikować
        # potencjalnie błędnych danych (lepszy brak wyniku niż fałszywy rekord).
        # TODO: Raportować licznik odrzuconych rekordów przez osobny topic diagnostyczny.
        try:
            with open(path, 'r', newline='') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    parsed_time = self._to_float(row.get('time_sec'), default=math.nan)
                    if not math.isfinite(parsed_time):
                        continue
                    row['_time_sec'] = parsed_time
                    rows.append(row)
        except OSError as exc:
            self.get_logger().error(f'Cannot read CSV file: {path}. Error: {exc}')
            return []

        rows.sort(key=lambda r: r['_time_sec'])
        return rows

    def on_timer(self) -> None:
        """
        Cel: Ta metoda realizuje odpowiedzialność `on_timer` w aktualnym module.
        Dlaczego tak: Wydzielenie tej jednostki upraszcza debugowanie i chroni krytyczne ścieżki przed niekontrolowanymi zmianami.
        """
        if not self.rows:
            return

        elapsed = (self.get_clock().now() - self.start_time).nanoseconds / 1e9
        elapsed *= self.playback_rate

        while self.index < len(self.rows) and self.rows[self.index]['_time_sec'] <= elapsed:
            payload = self._row_to_payload(self.rows[self.index])
            out = String()
            out.data = json.dumps(payload, separators=(',', ':'))
            self.pub.publish(out)
            self.index += 1

        if self.index >= len(self.rows):
            if self.loop:
                self.index = 0
                self.start_time = self.get_clock().now()
            else:
                self.timer.cancel()
                self.get_logger().info('CSV replay finished.')

    def _row_to_payload(self, row: dict) -> dict:
        """
        Cel: Ta metoda realizuje odpowiedzialność `_row_to_payload` w aktualnym module.
        Dlaczego tak: Wydzielenie tej jednostki upraszcza debugowanie i chroni krytyczne ścieżki przed niekontrolowanymi zmianami.
        """
        detected = self._to_bool(row.get('detected'))
        return {
            'stamp': datetime.now(timezone.utc).isoformat(),
            'frame_id': self.frame_id,
            'detected': detected,
            'x': self._to_float(row.get('x')),
            'y': self._to_float(row.get('y')),
            'z': self._to_float(row.get('z')),
            'x_world': self._to_float(row.get('x_world')),
            'y_world': self._to_float(row.get('y_world')),
            'z_world': self._to_float(row.get('z_world')),
            'area': self._to_float(row.get('area'), default=0.0),
            'perimeter': self._to_float(row.get('perimeter'), default=0.0),
            'circularity': self._to_float(row.get('circularity'), default=0.0),
            'radius': self._to_float(row.get('radius'), default=0.0),
            'track_id': self._to_int(row.get('track_id')),
            'rank': self._to_int(row.get('rank')),
            'kalman_predicted': self._to_bool(row.get('kalman_predicted')),
        }

    @staticmethod
    def _to_float(value, default=math.nan) -> float:
        """
        Cel: Ta metoda realizuje odpowiedzialność `_to_float` w aktualnym module.
        Dlaczego tak: Wydzielenie tej jednostki upraszcza debugowanie i chroni krytyczne ścieżki przed niekontrolowanymi zmianami.
        """
        if value is None:
            return default
        text = str(value).strip()
        if text == '':
            return default
        try:
            return float(text)
        except ValueError:
            return default

    @staticmethod
    def _to_int(value, default=0) -> int:
        """
        Cel: Ta metoda realizuje odpowiedzialność `_to_int` w aktualnym module.
        Dlaczego tak: Wydzielenie tej jednostki upraszcza debugowanie i chroni krytyczne ścieżki przed niekontrolowanymi zmianami.
        """
        if value is None:
            return default
        text = str(value).strip()
        if text == '':
            return default
        try:
            return int(float(text))
        except ValueError:
            return default

    @staticmethod
    def _to_bool(value, default=False) -> bool:
        """
        Cel: Ta metoda realizuje odpowiedzialność `_to_bool` w aktualnym module.
        Dlaczego tak: Wydzielenie tej jednostki upraszcza debugowanie i chroni krytyczne ścieżki przed niekontrolowanymi zmianami.
        """
        if value is None:
            return default
        text = str(value).strip().lower()
        if text in ('1', 'true', 't', 'yes', 'y'):
            return True
        if text in ('0', 'false', 'f', 'no', 'n', ''):
            return False
        return default


def main(args=None) -> None:
    """
    Cel: Ta funkcja realizuje odpowiedzialność `main` w aktualnym module.
    Dlaczego tak: Wydzielenie tej jednostki upraszcza debugowanie i chroni krytyczne ścieżki przed niekontrolowanymi zmianami.
    """
    rclpy.init(args=args)
    node = CsvDetectionReplayNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
