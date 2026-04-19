from __future__ import annotations

import copy

import rclpy
from geometry_msgs.msg import Twist
from rclpy.duration import Duration
from rclpy.node import Node
from rclpy.time import Time
from std_msgs.msg import Bool, Empty


class EmergencyStopNode(Node):
    """Węzeł fail-safe filtrujący komendy ruchu na podstawie sygnału E-STOP i heartbeat."""

    def __init__(self) -> None:
        super().__init__('emergency_stop_node')

        # [AI-CHANGE | 2026-04-19 21:11 UTC | v0.127]
        # CO ZMIENIONO: Przebudowano interfejs na wymagane wejścia/wyjścia:
        #   - subskrypcja `cmd_vel_in` (Twist),
        #   - subskrypcja `estop_signal` (Bool),
        #   - opcjonalna subskrypcja heartbeat `estop_heartbeat` jako Empty albo Bool,
        #   - publikacja `cmd_vel_out` (Twist).
        #   Dodano parametry bezpieczeństwa:
        #   - `use_heartbeat` (domyślnie False),
        #   - `heartbeat_msg_type` (`empty` lub `bool`),
        #   - `heartbeat_timeout_s` (domyślnie 0.5 sekundy).
        # DLACZEGO: Użytkownik oczekuje prostego filtra bezpieczeństwa, który ma domyślnie zatrzymywać robota
        #   i odblokowywać ruch wyłącznie po spełnieniu jawnych warunków bezpieczeństwa.
        # JAK TO DZIAŁA: Każda przychodząca komenda `cmd_vel_in` jest weryfikowana metodą `_is_safe_to_forward()`;
        #   jeśli warunki nie są spełnione, publikowane jest zero na `cmd_vel_out`.
        # TODO: Dodać diagnostykę na osobnym topicu (np. `diagnostics`) z precyzyjnym powodem blokady ruchu.
        self.declare_parameter('use_heartbeat', False)
        self.declare_parameter('heartbeat_msg_type', 'empty')
        self.declare_parameter('heartbeat_timeout_s', 0.5)

        self._use_heartbeat = bool(self.get_parameter('use_heartbeat').value)
        self._heartbeat_msg_type = str(self.get_parameter('heartbeat_msg_type').value).strip().lower()
        self._heartbeat_timeout_s = float(self.get_parameter('heartbeat_timeout_s').value)

        if self._heartbeat_timeout_s <= 0.0:
            self.get_logger().warn(
                'Parametr heartbeat_timeout_s <= 0.0, ustawiam wartość bezpieczną 0.5s.'
            )
            self._heartbeat_timeout_s = 0.5

        if self._heartbeat_msg_type not in {'empty', 'bool'}:
            self.get_logger().warn(
                "Nieobsługiwany heartbeat_msg_type='%s'; używam bezpiecznego domyślnego 'empty'."
                % self._heartbeat_msg_type
            )
            self._heartbeat_msg_type = 'empty'

        self._heartbeat_timeout = Duration(seconds=self._heartbeat_timeout_s)

        # [AI-CHANGE | 2026-04-19 21:11 UTC | v0.127]
        # CO ZMIENIONO: Wprowadzono stan startowy fail-safe:
        #   - `_estop_asserted = True` (na starcie traktujemy układ jako zatrzymany),
        #   - `_last_heartbeat_time = None` (brak heartbeat do czasu pierwszej wiadomości).
        # DLACZEGO: Zgodnie z zasadą bezpieczeństwa lepiej odrzucić sterowanie niż przepuścić niepewne dane.
        # JAK TO DZIAŁA: Odblokowanie ruchu wymaga co najmniej `estop_signal=False`; a jeśli heartbeat jest włączony,
        #   to dodatkowo wymagany jest świeży heartbeat w dopuszczalnym oknie czasu.
        # TODO: Rozważyć parametr `require_estop_release` z potwierdzeniem dwukanałowym dla systemów SIL.
        self._estop_asserted = True
        self._last_cmd = Twist()
        self._last_heartbeat_time: Time | None = None

        self._cmd_in_sub = self.create_subscription(Twist, 'cmd_vel_in', self._on_cmd_vel_in, 10)
        self._estop_signal_sub = self.create_subscription(Bool, 'estop_signal', self._on_estop_signal, 10)
        self._cmd_out_pub = self.create_publisher(Twist, 'cmd_vel_out', 10)

        self._heartbeat_sub = None
        if self._use_heartbeat:
            if self._heartbeat_msg_type == 'bool':
                self._heartbeat_sub = self.create_subscription(
                    Bool,
                    'estop_heartbeat',
                    self._on_heartbeat_bool,
                    10,
                )
            else:
                self._heartbeat_sub = self.create_subscription(
                    Empty,
                    'estop_heartbeat',
                    self._on_heartbeat_empty,
                    10,
                )

        # Natychmiastowa publikacja zera po starcie dla deterministycznego wejścia w tryb bezpieczny.
        self._publish_zero_cmd()
        self.get_logger().info('EmergencyStopNode uruchomiony w trybie fail-safe (zatrzymany).')

    def _on_cmd_vel_in(self, msg: Twist) -> None:
        """Przepuszcza komendę tylko przy spełnionych warunkach bezpieczeństwa."""
        self._last_cmd = copy.deepcopy(msg)
        if self._is_safe_to_forward():
            self._cmd_out_pub.publish(msg)
            return

        self._publish_zero_cmd()

    def _on_estop_signal(self, msg: Bool) -> None:
        """Aktualizuje stan E-STOP: True wymusza zatrzymanie, False pozwala na potencjalne odblokowanie."""
        self._estop_asserted = bool(msg.data)
        if self._estop_asserted:
            self.get_logger().warn('Odebrano estop_signal=True. Wymuszam zatrzymanie.')
            self._publish_zero_cmd()
        else:
            self.get_logger().info('Odebrano estop_signal=False. Oczekuję na spełnienie pozostałych warunków bezpieczeństwa.')

    def _on_heartbeat_empty(self, _msg: Empty) -> None:
        """Rejestruje heartbeat typu Empty."""
        self._last_heartbeat_time = self.get_clock().now()

    def _on_heartbeat_bool(self, msg: Bool) -> None:
        """Rejestruje heartbeat typu Bool tylko gdy wartość jest jawnie True."""
        if not msg.data:
            # Przy heartbeat typu Bool wartość False traktujemy jako brak ważnego heartbeat.
            return
        self._last_heartbeat_time = self.get_clock().now()

    def _is_safe_to_forward(self) -> bool:
        """Ocena bezpieczeństwa: True = wolno przepuścić cmd_vel, False = należy publikować zero."""
        if self._estop_asserted:
            return False

        if not self._use_heartbeat:
            return True

        if self._last_heartbeat_time is None:
            return False

        elapsed = self.get_clock().now() - self._last_heartbeat_time
        return elapsed <= self._heartbeat_timeout

    def _publish_zero_cmd(self) -> None:
        """Publikuje zerową prędkość na wyjście bezpieczeństwa."""
        self._cmd_out_pub.publish(Twist())


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
