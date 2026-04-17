"""Node ROS2 realizujący warstwę bezpieczeństwa E-STOP dla `cmd_vel`.

Node działa jako filtr pomiędzy `control_node` a końcowym topiciem ruchu robota.
Zapewnia latched E-STOP (wymaga jawnego resetu) oraz automatyczne przejście do E-STOP,
gdy wykryte zostaną warunki bezpieczeństwa (watchdog, brak stanu misji, przeszkoda depth).
"""

from __future__ import annotations

import rclpy
from geometry_msgs.msg import Twist
from g1_light_tracking.msg import DepthNavHint, MissionState
from rclpy.node import Node
from std_msgs.msg import Bool
from std_srvs.srv import Trigger

from g1_light_tracking.safety import SafetyStopController


class SafetyStopNode(Node):
    """Node bezpieczeństwa publikujący końcowe `cmd_vel` po filtrze E-STOP."""

    def __init__(self) -> None:
        super().__init__('safety_stop_node')

        self.declare_parameter('input_cmd_vel_topic', '/cmd_vel/raw')
        self.declare_parameter('output_cmd_vel_topic', '/cmd_vel')
        self.declare_parameter('status_topic', '/safety/estop_state')
        self.declare_parameter('mission_state_topic', '/mission/state')
        self.declare_parameter('depth_hint_topic', '/navigation/depth_hint')
        self.declare_parameter('auto_estop_on_missing_mission_sec', 3.0)
        self.declare_parameter('auto_estop_on_depth_obstacle', False)
        self.declare_parameter('heartbeat_timeout_sec', 0.75)
        self.declare_parameter('obstacle_clearance_threshold_m', 0.45)
        self.declare_parameter('watchdog_publish_rate_hz', 20.0)

        self.controller = SafetyStopController(
            heartbeat_timeout_sec=float(self.get_parameter('heartbeat_timeout_sec').value),
            auto_estop_on_missing_mission_sec=float(
                self.get_parameter('auto_estop_on_missing_mission_sec').value
            ),
            auto_estop_on_depth_obstacle=bool(self.get_parameter('auto_estop_on_depth_obstacle').value),
            obstacle_clearance_threshold_m=float(
                self.get_parameter('obstacle_clearance_threshold_m').value
            ),
        )

        self.cmd_pub = self.create_publisher(Twist, self.get_parameter('output_cmd_vel_topic').value, 20)
        self.status_pub = self.create_publisher(Bool, self.get_parameter('status_topic').value, 10)

        self.create_subscription(
            Twist,
            self.get_parameter('input_cmd_vel_topic').value,
            self.on_raw_cmd,
            20,
        )
        self.create_subscription(
            MissionState,
            self.get_parameter('mission_state_topic').value,
            self.on_mission_state,
            20,
        )
        self.create_subscription(
            DepthNavHint,
            self.get_parameter('depth_hint_topic').value,
            self.on_depth_hint,
            20,
        )

        self.create_service(Trigger, '/safety/estop/trigger', self.on_manual_trigger)
        self.create_service(Trigger, '/safety/estop/reset', self.on_manual_reset)

        timer_period_sec = 1.0 / max(1.0, float(self.get_parameter('watchdog_publish_rate_hz').value))
        self.timer = self.create_timer(timer_period_sec, self.on_watchdog_tick)

        self.get_logger().info(
            'SafetyStopNode started: '
            f"input={self.get_parameter('input_cmd_vel_topic').value}, "
            f"output={self.get_parameter('output_cmd_vel_topic').value}, "
            f"status={self.get_parameter('status_topic').value}"
        )

    def now_sec(self) -> float:
        """Zwraca bieżący czas node'a w sekundach."""
        return self.get_clock().now().nanoseconds / 1e9

    def on_raw_cmd(self, msg: Twist) -> None:
        """Przetwarza wejściową komendę ruchu i przepuszcza ją tylko poza E-STOP."""
        now_sec = self.now_sec()
        self.controller.observe_cmd(now_sec)
        if self.controller.estop_latched:
            return
        self.cmd_pub.publish(msg)

    def on_mission_state(self, _msg: MissionState) -> None:
        """Odświeża heartbeat stanu misji używany przez regułę auto E-STOP."""
        self.controller.observe_mission(self.now_sec())

    def on_depth_hint(self, msg: DepthNavHint) -> None:
        """Aktywuje E-STOP po wykryciu przeszkody, jeśli flaga bezpieczeństwa jest aktywna."""
        reason = self.controller.evaluate_depth_obstacle(msg.depth_available, float(msg.forward_clearance_m))
        if reason is not None and self.controller.trigger_estop(reason):
            self.log_estop_transition(reason)

    def on_manual_trigger(self, _request: Trigger.Request, response: Trigger.Response) -> Trigger.Response:
        """Serwis ręcznego aktywowania E-STOP."""
        changed = self.controller.trigger_estop('manual')
        if changed:
            self.log_estop_transition('manual')
        response.success = True
        response.message = 'E-STOP active (latched)'
        return response

    def on_manual_reset(self, _request: Trigger.Request, response: Trigger.Response) -> Trigger.Response:
        """Serwis resetu E-STOP.

        Reset jest jawny i zawsze wymaga wywołania usługi `/safety/estop/reset`.
        """
        changed = self.controller.reset_estop()
        if changed:
            self.get_logger().warning('[E-STOP] reset performed, motion commands are enabled again.')
        response.success = True
        response.message = 'E-STOP reset' if changed else 'E-STOP was already inactive'
        return response

    def on_watchdog_tick(self) -> None:
        """Wykonuje cykliczne sprawdzenie watchdogów i publikuje status bezpieczeństwa."""
        now_sec = self.now_sec()
        auto_reason = self.controller.evaluate_auto_estop(now_sec)
        if auto_reason is not None and self.controller.trigger_estop(auto_reason):
            self.log_estop_transition(auto_reason)

        status_msg = Bool()
        status_msg.data = self.controller.estop_latched
        self.status_pub.publish(status_msg)

        if self.controller.estop_latched:
            # Watchdog bezpieczeństwa: w stanie E-STOP stale nadpisujemy ruch zerowym Twist.
            self.cmd_pub.publish(Twist())

    def log_estop_transition(self, reason: str) -> None:
        """Loguje jednolity komunikat diagnostyczny dla przyczyny wejścia w E-STOP."""
        self.get_logger().error(
            '[E-STOP] active=true, '
            f'reason={reason}, '
            f'heartbeat_timeout_sec={self.controller.heartbeat_timeout_sec:.2f}, '
            f'missing_mission_sec={self.controller.auto_estop_on_missing_mission_sec:.2f}'
        )


def main(args: list[str] | None = None) -> None:
    """Punkt wejścia dla wykonania node'a safety stop."""
    rclpy.init(args=args)
    node = SafetyStopNode()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()
