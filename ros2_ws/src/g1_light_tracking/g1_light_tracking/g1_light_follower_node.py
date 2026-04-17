"""Legacy closed-loop follower consuming JSON detections and outputting /cmd_vel."""

import json
import math

import rclpy
from geometry_msgs.msg import Twist
from rclpy.node import Node
from std_msgs.msg import String


class G1LightFollowerNode(Node):
    def __init__(self) -> None:
        super().__init__('g1_light_follower_node')

        self.declare_parameter('detection_topic', '/light_tracking/detection_json')
        self.declare_parameter('cmd_vel_topic', '/cmd_vel')
        self.declare_parameter('control_rate_hz', 20.0)
        self.declare_parameter('target_distance_m', 0.8)
        self.declare_parameter('detection_timeout_s', 0.3)
        self.declare_parameter('min_area', 8.0)
        self.declare_parameter('k_linear', 0.7)
        self.declare_parameter('k_angular', 1.5)
        self.declare_parameter('max_linear_speed', 0.5)
        self.declare_parameter('max_angular_speed', 1.0)
        self.declare_parameter('allow_backward', False)
        self.declare_parameter('linear_no_depth_speed', 0.2)
        self.declare_parameter('camera_cx', 319.5)
        self.declare_parameter('log_nonzero_cmd_vel', True)
        self.declare_parameter('cmd_vel_log_interval_s', 0.5)
        self.declare_parameter('cmd_vel_nonzero_eps', 1e-3)
        self.declare_parameter('log_rejection_reasons', True)
        self.declare_parameter('rejection_log_interval_s', 1.0)
        self.declare_parameter('log_cmd_vel_subscribers', True)
        self.declare_parameter('cmd_vel_subscribers_log_interval_s', 2.0)

        self.detection_topic = self.get_parameter('detection_topic').get_parameter_value().string_value
        self.cmd_vel_topic = self.get_parameter('cmd_vel_topic').get_parameter_value().string_value
        self.control_rate_hz = float(self.get_parameter('control_rate_hz').get_parameter_value().double_value)
        self.target_distance_m = float(self.get_parameter('target_distance_m').get_parameter_value().double_value)
        self.detection_timeout_s = float(
            self.get_parameter('detection_timeout_s').get_parameter_value().double_value
        )
        self.min_area = float(self.get_parameter('min_area').get_parameter_value().double_value)
        self.k_linear = float(self.get_parameter('k_linear').get_parameter_value().double_value)
        self.k_angular = float(self.get_parameter('k_angular').get_parameter_value().double_value)
        self.max_linear_speed = float(
            self.get_parameter('max_linear_speed').get_parameter_value().double_value
        )
        self.max_angular_speed = float(
            self.get_parameter('max_angular_speed').get_parameter_value().double_value
        )
        self.allow_backward = self.get_parameter('allow_backward').get_parameter_value().bool_value
        self.linear_no_depth_speed = float(
            self.get_parameter('linear_no_depth_speed').get_parameter_value().double_value
        )
        self.camera_cx = float(self.get_parameter('camera_cx').get_parameter_value().double_value)
        self.log_nonzero_cmd_vel = self.get_parameter(
            'log_nonzero_cmd_vel'
        ).get_parameter_value().bool_value
        self.cmd_vel_log_interval_s = float(
            self.get_parameter('cmd_vel_log_interval_s').get_parameter_value().double_value
        )
        self.cmd_vel_nonzero_eps = float(
            self.get_parameter('cmd_vel_nonzero_eps').get_parameter_value().double_value
        )
        self.log_rejection_reasons = self.get_parameter(
            'log_rejection_reasons'
        ).get_parameter_value().bool_value
        self.rejection_log_interval_s = float(
            self.get_parameter('rejection_log_interval_s').get_parameter_value().double_value
        )
        self.log_cmd_vel_subscribers = self.get_parameter(
            'log_cmd_vel_subscribers'
        ).get_parameter_value().bool_value
        self.cmd_vel_subscribers_log_interval_s = float(
            self.get_parameter('cmd_vel_subscribers_log_interval_s').get_parameter_value().double_value
        )

        self.latest_detection = None
        self.latest_detection_time = None
        self._last_cmd_log_time = None
        self._last_rejection_log_time = None
        self._last_subscribers_log_time = None

        self.sub = self.create_subscription(String, self.detection_topic, self.on_detection, 10)
        self.pub = self.create_publisher(Twist, self.cmd_vel_topic, 10)
        self.timer = self.create_timer(1.0 / max(self.control_rate_hz, 1.0), self.on_timer)

        self.get_logger().info(
            f'Listening JSON on {self.detection_topic}, publishing cmd_vel on {self.cmd_vel_topic}'
        )

    def on_detection(self, msg: String) -> None:
        try:
            payload = json.loads(msg.data)
        except json.JSONDecodeError:
            self.get_logger().warn('Invalid JSON detection payload, skipping.')
            return

        self.latest_detection = payload
        self.latest_detection_time = self.get_clock().now()

    def on_timer(self) -> None:
        cmd = Twist()
        self._maybe_log_cmd_vel_subscribers()

        if not self._has_fresh_detection():
            self.pub.publish(cmd)
            self._maybe_log_rejection('stale_or_missing_detection')
            return

        msg = self.latest_detection
        if msg is None or not bool(msg.get('detected', False)):
            self.pub.publish(cmd)
            self._maybe_log_rejection('detection_flag_false')
            return

        area = self._to_float(msg.get('area'))
        if math.isnan(area) or area < self.min_area:
            self.pub.publish(cmd)
            self._maybe_log_rejection(
                f'area_below_min area={area:.3f} min_area={self.min_area:.3f}'
                if not math.isnan(area)
                else 'area_invalid_nan'
            )
            return

        lateral_error = self._pick_lateral(msg)
        distance = self._pick_distance(msg)

        if not math.isnan(lateral_error):
            cmd.angular.z = self._clamp(-self.k_angular * lateral_error, self.max_angular_speed)

        if not math.isnan(distance):
            linear = self.k_linear * (distance - self.target_distance_m)
            if not self.allow_backward:
                linear = max(0.0, linear)
            cmd.linear.x = self._clamp(linear, self.max_linear_speed)
        else:
            cmd.linear.x = self._clamp(self.linear_no_depth_speed, self.max_linear_speed)

        self.pub.publish(cmd)
        self._maybe_log_nonzero_cmd(cmd)

    def _has_fresh_detection(self) -> bool:
        if self.latest_detection_time is None:
            return False
        age = (self.get_clock().now() - self.latest_detection_time).nanoseconds / 1e9
        return age <= self.detection_timeout_s

    @staticmethod
    def _to_float(value) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return math.nan

    @staticmethod
    def _clamp(value: float, max_abs_value: float) -> float:
        return max(-max_abs_value, min(max_abs_value, value))

    def _pick_lateral(self, msg: dict) -> float:
        x_world = self._to_float(msg.get('x_world'))
        if not math.isnan(x_world):
            return x_world
        x_pixel = self._to_float(msg.get('x'))
        if math.isnan(x_pixel):
            return math.nan
        return x_pixel - self.camera_cx

    def _pick_distance(self, msg: dict) -> float:
        z_world = self._to_float(msg.get('z_world'))
        if not math.isnan(z_world):
            return z_world
        return self._to_float(msg.get('z'))

    def _maybe_log_nonzero_cmd(self, cmd: Twist) -> None:
        if not self.log_nonzero_cmd_vel:
            return

        is_nonzero = (
            abs(cmd.linear.x) > self.cmd_vel_nonzero_eps
            or abs(cmd.linear.y) > self.cmd_vel_nonzero_eps
            or abs(cmd.angular.z) > self.cmd_vel_nonzero_eps
        )
        if not is_nonzero:
            return

        now = self.get_clock().now()
        if self._last_cmd_log_time is not None:
            elapsed = (now - self._last_cmd_log_time).nanoseconds / 1e9
            if elapsed < self.cmd_vel_log_interval_s:
                return

        self._last_cmd_log_time = now
        self.get_logger().info(
            f'cmd_vel non-zero: vx={cmd.linear.x:.3f}, vy={cmd.linear.y:.3f}, wz={cmd.angular.z:.3f}'
        )

    def _maybe_log_rejection(self, reason: str) -> None:
        if not self.log_rejection_reasons:
            return

        now = self.get_clock().now()
        if self._last_rejection_log_time is not None:
            elapsed = (now - self._last_rejection_log_time).nanoseconds / 1e9
            if elapsed < self.rejection_log_interval_s:
                return

        self._last_rejection_log_time = now
        self.get_logger().info(f'cmd_vel zero reason: {reason}')

    def _maybe_log_cmd_vel_subscribers(self) -> None:
        if not self.log_cmd_vel_subscribers:
            return

        now = self.get_clock().now()
        if self._last_subscribers_log_time is not None:
            elapsed = (now - self._last_subscribers_log_time).nanoseconds / 1e9
            if elapsed < self.cmd_vel_subscribers_log_interval_s:
                return

        self._last_subscribers_log_time = now
        count = self.pub.get_subscription_count()
        if count == 0:
            self.get_logger().warn(f'/cmd_vel subscribers={count}')
        else:
            self.get_logger().info(f'/cmd_vel subscribers={count}')


def main(args=None) -> None:
    rclpy.init(args=args)
    node = G1LightFollowerNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
