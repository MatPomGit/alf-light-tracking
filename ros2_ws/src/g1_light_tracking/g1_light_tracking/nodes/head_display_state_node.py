"""Node mapujący stan misji na efekt LED wyświetlany na head display.

Node jest celowo lekki: nie steruje sprzętem bezpośrednio, tylko publikuje efekt logiczny,
który może zostać obsłużony przez różne backendy (np. mock, terminal, vendor API).
"""

from __future__ import annotations

import rclpy
from rclpy.node import Node
from std_msgs.msg import String

from g1_light_tracking.msg import MissionState


class HeadDisplayStateNode(Node):
    """Publikuje nazwę efektu LED wynikającą z aktualnego stanu misji."""

    def __init__(self) -> None:
        super().__init__('head_display_state_node')

        self.declare_parameter('mission_state_topic', '/mission/state')
        self.declare_parameter('effect_topic', '/head_display/effect')
        self.declare_parameter('backend', 'mock')

        self.backend = str(self.get_parameter('backend').value).strip() or 'mock'
        self.effect_topic = str(self.get_parameter('effect_topic').value)
        self.current_effect = 'idle'

        self.effect_pub = self.create_publisher(String, self.effect_topic, 10)
        self.create_subscription(
            MissionState,
            str(self.get_parameter('mission_state_topic').value),
            self.on_mission_state,
            20,
        )

        # Heartbeat statusu efektu pozwala monitorom zobaczyć stan nawet bez zmian misji.
        self.create_timer(1.0, self.publish_current_effect)

        self.get_logger().info(
            'HeadDisplayStateNode started: '
            f'backend={self.backend}, mission_state_topic={self.get_parameter("mission_state_topic").value}, '
            f'effect_topic={self.effect_topic}'
        )

    def map_state_to_effect(self, msg: MissionState) -> str:
        """Mapuje stan FSM na semantyczny efekt LED."""
        state = msg.state.strip().lower()

        if msg.is_terminal or state in {'failed', 'error'}:
            return 'error_red_pulse'
        if state in {'approaching', 'tracking', 'pickup', 'pickup_approach'}:
            return 'tracking_blue'
        if state in {'dropoff', 'dropoff_approach', 'delivery'}:
            return 'delivery_green'
        if state in {'searching', 'scan', 'scan_for_target'}:
            return 'scan_yellow'
        if state in {'paused', 'hold', 'standby', 'waiting'}:
            return 'standby_white'
        return 'idle'

    def on_mission_state(self, msg: MissionState) -> None:
        """Aktualizuje i publikuje efekt, gdy zmienia się kontekst misji."""
        mapped_effect = self.map_state_to_effect(msg)
        if mapped_effect != self.current_effect:
            self.current_effect = mapped_effect
            self.get_logger().info(
                f'Head display effect changed: effect={self.current_effect}, '
                f'mission_state={msg.state}, backend={self.backend}'
            )

        self.publish_current_effect()

    def publish_current_effect(self) -> None:
        """Publikuje ostatni efekt jako stan obserwowalny dla debug/TUI/integracji."""
        out = String()
        out.data = self.current_effect
        self.effect_pub.publish(out)


def main(args: list[str] | None = None) -> None:
    rclpy.init(args=args)
    node = HeadDisplayStateNode()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()
