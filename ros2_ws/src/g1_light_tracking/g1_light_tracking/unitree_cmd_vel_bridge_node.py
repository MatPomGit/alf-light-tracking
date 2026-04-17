from __future__ import annotations

"""Compatibility bridge from /cmd_vel to the Unitree sport API.

This module comes from the legacy JSON-based light tracking stack and is kept
side-by-side with the newer mission/control pipeline.
"""

import rclpy
from geometry_msgs.msg import Twist
from rclpy.node import Node
try:
    from unitree_api.msg import Request, Response
    _UNITREE_API_IMPORT_ERROR = None
except ImportError as exc:
    Request = None
    Response = None
    _UNITREE_API_IMPORT_ERROR = exc


class UnitreeCmdVelBridgeNode(Node):
    def __init__(self) -> None:
        if Request is None or Response is None:
            raise RuntimeError(f'unitree_api messages are required for unitree_cmd_vel_bridge_node: {_UNITREE_API_IMPORT_ERROR}')

        super().__init__('unitree_cmd_vel_bridge_node')

        self.declare_parameter('cmd_vel_topic', '/cmd_vel')
        self.declare_parameter('unitree_request_topic', 'api/sport/request')
        self.declare_parameter('max_vx', 0.3)
        self.declare_parameter('max_vy', 0.3)
        self.declare_parameter('max_vyaw', 0.8)
        self.declare_parameter('cmd_timeout_s', 0.5)
        self.declare_parameter('publish_rate_hz', 10.0)
        self.declare_parameter('api_response_topic', '/api/sport/response')
        self.declare_parameter('switch_to_normal', False)
        self.declare_parameter('startup_delay_s', 1.5)
        self.declare_parameter('start_fsm_id', 500)
        self.declare_parameter('enable_balance_mode', True)
        self.declare_parameter('balance_mode', 1)
        self.declare_parameter('velocity_duration_s', 0.2)
        self.declare_parameter('log_cmd_vel_rx', True)
        self.declare_parameter('log_cmd_vel_tx', True)
        self.declare_parameter('log_subscribers', True)
        self.declare_parameter('log_interval_s', 1.0)

        self.cmd_vel_topic = self.get_parameter('cmd_vel_topic').get_parameter_value().string_value
        self.unitree_request_topic = self.get_parameter(
            'unitree_request_topic'
        ).get_parameter_value().string_value
        self.max_vx = float(self.get_parameter('max_vx').get_parameter_value().double_value)
        self.max_vy = float(self.get_parameter('max_vy').get_parameter_value().double_value)
        self.max_vyaw = float(self.get_parameter('max_vyaw').get_parameter_value().double_value)
        self.cmd_timeout = float(self.get_parameter('cmd_timeout_s').get_parameter_value().double_value)
        publish_rate = float(self.get_parameter('publish_rate_hz').get_parameter_value().double_value)
        self.api_response_topic = self.get_parameter(
            'api_response_topic'
        ).get_parameter_value().string_value
        self.switch_to_normal = self.get_parameter('switch_to_normal').get_parameter_value().bool_value
        self.startup_delay_s = float(self.get_parameter('startup_delay_s').get_parameter_value().double_value)
        self.start_fsm_id = int(self.get_parameter('start_fsm_id').get_parameter_value().integer_value)
        self.enable_balance_mode = self.get_parameter('enable_balance_mode').get_parameter_value().bool_value
        self.balance_mode = int(self.get_parameter('balance_mode').get_parameter_value().integer_value)
        self.velocity_duration_s = float(
            self.get_parameter('velocity_duration_s').get_parameter_value().double_value
        )
        self.log_cmd_vel_rx = self.get_parameter('log_cmd_vel_rx').get_parameter_value().bool_value
        self.log_cmd_vel_tx = self.get_parameter('log_cmd_vel_tx').get_parameter_value().bool_value
        self.log_subscribers = self.get_parameter('log_subscribers').get_parameter_value().bool_value
        self.log_interval_s = float(self.get_parameter('log_interval_s').get_parameter_value().double_value)

        # G1 loco API on /api/sport/request
        self.api_id_move = 7105
        self.api_id_set_fsm = 7101
        self.api_id_set_balance_mode = 7102
        self.api_id_motion_release = 1003
        self.api_id_stop = 1003
        self.api_id_enable_obstacle_avoidance = 2048

        self.last_twist = Twist()
        self.last_cmd_time = self.get_clock().now()
        self.request_id = 0
        self.is_moving = False
        self.sent_ids = {}
        self._last_rx_log_time = None
        self._last_tx_log_time = None
        self._last_subscribers_log_time = None

        self.cmd_sub = self.create_subscription(Twist, self.cmd_vel_topic, self.cmd_vel_callback, 10)
        self.unitree_pub = self.create_publisher(Request, self.unitree_request_topic, 10)
        self.response_sub = self.create_subscription(
            Response, self.api_response_topic, self._on_response, 10
        )
        self.timer = self.create_timer(1.0 / max(publish_rate, 1.0), self.send_move)

        self.get_logger().info(
            f'Bridge online: {self.cmd_vel_topic} -> {self.unitree_request_topic}, rate={publish_rate}Hz'
        )

        self._send_startup_sequence()

    def _publish_api(self, api_id: int, payload: dict | None, tag: str) -> int:
        req = Request()
        req_id = self.get_next_id()
        req.header.identity.id = req_id
        req.header.identity.api_id = api_id
        req.parameter = json.dumps(payload) if payload is not None else ''
        self.unitree_pub.publish(req)
        self.sent_ids[req_id] = tag
        return req_id

    def _send_startup_sequence(self) -> None:
        if self.switch_to_normal:
            req_id = self._publish_api(self.api_id_motion_release, {}, 'motion_release')
            self.get_logger().info(
                f'ReleaseMode sent (api_id={self.api_id_motion_release}, req_id={req_id}), waiting {self.startup_delay_s:.1f}s'
            )
            time.sleep(max(0.0, self.startup_delay_s))

        req_id = self._publish_api(self.api_id_set_fsm, {'data': self.start_fsm_id}, 'set_fsm')
        self.get_logger().info(
            f'SetFsmId sent (api_id={self.api_id_set_fsm}, req_id={req_id}, fsm_id={self.start_fsm_id})'
        )

        if self.enable_balance_mode:
            req_id = self._publish_api(
                self.api_id_set_balance_mode, {'data': self.balance_mode}, 'set_balance_mode'
            )
            self.get_logger().info(
                'SetBalanceMode sent '
                f'(api_id={self.api_id_set_balance_mode}, req_id={req_id}, mode={self.balance_mode})'
            )

    def get_next_id(self) -> int:
        self.request_id += 1
        return self.request_id

    @staticmethod
    def clamp(value: float, min_val: float, max_val: float) -> float:
        return max(min_val, min(max_val, value))

    def cmd_vel_callback(self, msg: Twist) -> None:
        self.last_twist = msg
        self.last_cmd_time = self.get_clock().now()
        if self.log_cmd_vel_rx:
            now = self.get_clock().now()
            if self._last_rx_log_time is None:
                self._last_rx_log_time = now
                self.get_logger().info(
                    f'cmd_vel rx: vx={msg.linear.x:.3f}, vy={msg.linear.y:.3f}, wz={msg.angular.z:.3f}'
                )
            else:
                elapsed = (now - self._last_rx_log_time).nanoseconds / 1e9
                if elapsed >= self.log_interval_s:
                    self._last_rx_log_time = now
                    self.get_logger().info(
                        f'cmd_vel rx: vx={msg.linear.x:.3f}, vy={msg.linear.y:.3f}, wz={msg.angular.z:.3f}'
                    )

    def send_move(self) -> None:
        self._maybe_log_topic_subscribers()
        elapsed = (self.get_clock().now() - self.last_cmd_time).nanoseconds / 1e9

        if elapsed > self.cmd_timeout:
            if self.is_moving:
                self.get_logger().info('cmd_vel timeout -> stop')
                self.is_moving = False
            vx, vy, vyaw = 0.0, 0.0, 0.0
        else:
            vx = self.clamp(self.last_twist.linear.x, -self.max_vx, self.max_vx)
            vy = self.clamp(self.last_twist.linear.y, -self.max_vy, self.max_vy)
            vyaw = self.clamp(self.last_twist.angular.z, -self.max_vyaw, self.max_vyaw)

            if not self.is_moving and (vx != 0.0 or vy != 0.0 or vyaw != 0.0):
                self.get_logger().info('Robot motion command active')
                self.is_moving = True

        duration = max(0.1, self.velocity_duration_s)
        params = {'velocity': [float(vx), float(vy), float(vyaw)], 'duration': duration}
        req_id = self._publish_api(self.api_id_move, params, 'set_velocity')
        self._maybe_log_tx(req_id, elapsed, vx, vy, vyaw, duration)

    def _on_response(self, msg: Response) -> None:
        req_id = int(msg.header.identity.id)
        tag = self.sent_ids.pop(req_id, None)
        if tag is None:
            return

        code = int(msg.header.status.code)
        if code != 0:
            self.get_logger().warn(
                'Unitree API error: '
                f'tag={tag}, req_id={req_id}, api_id={msg.header.identity.api_id}, '
                f'code={code}, data={msg.data}'
            )

    def _maybe_log_topic_subscribers(self) -> None:
        if not self.log_subscribers:
            return

        now = self.get_clock().now()
        if self._last_subscribers_log_time is not None:
            elapsed = (now - self._last_subscribers_log_time).nanoseconds / 1e9
            if elapsed < self.log_interval_s:
                return

        self._last_subscribers_log_time = now
        count = self.unitree_pub.get_subscription_count()
        if count == 0:
            self.get_logger().warn(f'{self.unitree_request_topic} subscribers={count}')
        else:
            self.get_logger().info(f'{self.unitree_request_topic} subscribers={count}')

    def _maybe_log_tx(
        self, req_id: int, cmd_age_s: float, vx: float, vy: float, vyaw: float, duration: float
    ) -> None:
        if not self.log_cmd_vel_tx:
            return

        now = self.get_clock().now()
        if self._last_tx_log_time is not None:
            elapsed = (now - self._last_tx_log_time).nanoseconds / 1e9
            if elapsed < self.log_interval_s:
                return

        self._last_tx_log_time = now
        self.get_logger().info(
            'unitree tx: '
            f'req_id={req_id}, api_id={self.api_id_move}, age={cmd_age_s:.3f}s, '
            f'vel=[{vx:.3f},{vy:.3f},{vyaw:.3f}], duration={duration:.3f}s'
        )

    def send_stop(self) -> None:
        req = Request()
        req.header.identity.id = self.get_next_id()
        req.header.identity.api_id = self.api_id_stop
        req.parameter = ''
        self.unitree_pub.publish(req)
        self.get_logger().info(f'Stop sent (api_id={self.api_id_stop})')


def main(args=None) -> None:
    if Request is None or Response is None:
        raise RuntimeError(f'unitree_api messages are required for unitree_cmd_vel_bridge_node: {_UNITREE_API_IMPORT_ERROR}')

    rclpy.init(args=args)
    node = UnitreeCmdVelBridgeNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        node.send_stop()
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
