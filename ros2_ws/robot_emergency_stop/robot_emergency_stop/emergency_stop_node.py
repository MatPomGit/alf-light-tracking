from __future__ import annotations

import copy

import rclpy
from geometry_msgs.msg import Twist
from rclpy.node import Node
from std_msgs.msg import Bool
from std_srvs.srv import Trigger


class EmergencyStopNode(Node):
    """Węzeł filtrujący komendy ruchu na podstawie stanu awaryjnego STOP."""

    def __init__(self) -> None:
        super().__init__('emergency_stop_node')

        # [AI-CHANGE | 2026-04-19 20:47 UTC | v0.125]
        # CO ZMIENIONO: Dodano pełny interfejs topic/service dla awaryjnego zatrzymania:
        #   - subskrypcja `~/input_cmd_vel` (Twist),
        #   - subskrypcja `~/trigger` (Bool),
        #   - publikacja `~/output_cmd_vel` (Twist),
        #   - publikacja `~/status` (Bool),
        #   - usługa `~/reset` (Trigger).
        # DLACZEGO: Interfejs ma działać niezależnie od innych pakietów i zapewniać bezpieczne odcięcie ruchu po aktywacji STOP.
        # JAK TO DZIAŁA: Po `trigger=True` węzeł wymusza publikację zerowej prędkości i odrzuca każdą kolejną komendę ruchu aż do ręcznego resetu usługą.
        # TODO: Rozszerzyć logikę o timeout bezpieczeństwa (automatyczny STOP przy braku heartbeat z kontrolera nadrzędnego).
        self._stop_active = False
        self._last_cmd = Twist()

        self._cmd_in_sub = self.create_subscription(
            Twist,
            '~/input_cmd_vel',
            self._on_input_cmd_vel,
            10,
        )
        self._trigger_sub = self.create_subscription(
            Bool,
            '~/trigger',
            self._on_trigger,
            10,
        )

        self._cmd_out_pub = self.create_publisher(Twist, '~/output_cmd_vel', 10)
        self._status_pub = self.create_publisher(Bool, '~/status', 10)
        self._reset_srv = self.create_service(Trigger, '~/reset', self._on_reset)

        self._publish_status()
        self.get_logger().info('Emergency stop node started.')

    def _on_input_cmd_vel(self, msg: Twist) -> None:
        """Przekazuje komendę ruchu tylko wtedy, gdy STOP nie jest aktywny."""
        if self._stop_active:
            self._cmd_out_pub.publish(Twist())
            return

        self._last_cmd = copy.deepcopy(msg)
        self._cmd_out_pub.publish(msg)

    def _on_trigger(self, msg: Bool) -> None:
        """Aktywuje/dezaktywuje stop; aktywacja zawsze natychmiast publikuje komendę zerową."""
        if msg.data:
            if not self._stop_active:
                self.get_logger().warn('Emergency STOP activated.')
            self._stop_active = True
            self._cmd_out_pub.publish(Twist())
            self._publish_status()
            return

        # Bezpieczna polityka: ignorujemy `False` na triggerze, aby przypadkowo nie zwolnić blokady.
        self.get_logger().debug('Received trigger=False; stop remains unchanged until manual reset.')

    def _on_reset(self, _request: Trigger.Request, response: Trigger.Response) -> Trigger.Response:
        """Ręcznie resetuje blokadę awaryjnego zatrzymania."""
        self._stop_active = False
        self._publish_status()
        response.success = True
        response.message = 'Emergency stop has been reset.'

        # Po resecie publikujemy ostatnią znaną komendę, aby wznowienie było jawne i deterministyczne.
        self._cmd_out_pub.publish(copy.deepcopy(self._last_cmd))
        self.get_logger().info('Emergency STOP reset via service.')
        return response

    def _publish_status(self) -> None:
        """Publikuje aktualny status awaryjnego zatrzymania."""
        status = Bool()
        status.data = self._stop_active
        self._status_pub.publish(status)


def main(args: list[str] | None = None) -> None:
    rclpy.init(args=args)
    node = EmergencyStopNode()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
