import csv
import json
import math
from datetime import datetime, timezone

import rclpy
from rclpy.node import Node
from std_msgs.msg import String


class CsvDetectionReplayNode(Node):
    def __init__(self) -> None:
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

        self.pub = self.create_publisher(String, self.detection_topic, 10)
        self.rows = self._load_rows(self.csv_file)
        self.index = 0
        self.start_time = self.get_clock().now()
        self.timer = self.create_timer(0.01, self.on_timer)

        self.get_logger().info(
            f'CSV replay ready: rows={len(self.rows)}, rate={self.playback_rate}x, loop={self.loop}'
        )

    def _load_rows(self, path: str) -> list:
        if not path:
            self.get_logger().error('Parameter csv_file is empty.')
            return []

        rows = []
        with open(path, 'r', newline='') as f:
            reader = csv.DictReader(f)
            for row in reader:
                row['_time_sec'] = self._to_float(row.get('time_sec'), default=0.0)
                rows.append(row)

        rows.sort(key=lambda r: r['_time_sec'])
        return rows

    def on_timer(self) -> None:
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
        if value is None:
            return default
        text = str(value).strip().lower()
        if text in ('1', 'true', 't', 'yes', 'y'):
            return True
        if text in ('0', 'false', 'f', 'no', 'n', ''):
            return False
        return default


def main(args=None) -> None:
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
