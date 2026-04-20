from __future__ import annotations

import copy
from enum import Enum

import rclpy
from geometry_msgs.msg import Twist
from rclpy.duration import Duration
from rclpy.node import Node
from rclpy.time import Time
from std_msgs.msg import Bool, Empty
from std_srvs.srv import Trigger


class RunState(str, Enum):
    """Prosta maszyna stanów dostępu do ruchu."""

    STOPPED = 'STOPPED'
    RUN_ALLOWED = 'RUN_ALLOWED'


class EmergencyStopNode(Node):
    """Węzeł fail-safe filtrujący komendy ruchu na podstawie sygnału E-STOP i heartbeat."""

    def __init__(self) -> None:
        super().__init__('emergency_stop_node')

        # [AI-CHANGE | 2026-04-19 22:02 UTC | v0.129]
        # CO ZMIENIONO: Rozszerzono konfigurację o opcjonalne serwisy Trigger i jawny sygnał arm:
        #   - `enable_trigger_services` steruje wystawieniem `/emergency_stop/trigger` i `/emergency_stop/clear`,
        #   - `require_arm_to_clear` wymusza aktywny arm przy `clear`,
        #   - subskrypcja `estop_arm` (Bool) uzupełnia warunek bezpieczeństwa.
        #   Zachowano `estop_signal` jako główny interfejs produkcyjny.
        # DLACZEGO: Integracja między projektami wymaga prostego interfejsu topic (`estop_signal`) oraz
        #   opcjonalnego API serwisowego do ręcznego trigger/clear z dodatkowymi zabezpieczeniami.
        # JAK TO DZIAŁA: `estop_signal=True` zawsze zatrzymuje, `estop_signal=False` może odblokować ruch
        #   tylko po spełnieniu warunków heartbeat (jeśli aktywny) oraz arm (jeśli wymagany).
        # TODO: Dodać parametr określający minimalny czas stabilnego arm przed akceptacją `clear`.
        self.declare_parameter('use_heartbeat', False)
        self.declare_parameter('heartbeat_msg_type', 'empty')
        self.declare_parameter('heartbeat_timeout_s', 0.5)
        self.declare_parameter('enable_trigger_services', True)
        self.declare_parameter('require_arm_to_clear', True)
        # [AI-CHANGE | 2026-04-20 06:28 UTC | v0.135]
        # CO ZMIENIONO: Dodano parametr `safety_tick_hz`, który uruchamia cykliczny watchdog bezpieczeństwa.
        # DLACZEGO: Bez cyklicznego sprawdzania heartbeat i stanu STOP istnieje ryzyko opóźnionej reakcji,
        #   gdy do node'a nie napływają nowe wiadomości wejściowe.
        # JAK TO DZIAŁA: Timer watchdog działa z częstotliwością `safety_tick_hz` i wymusza regularną ewaluację
        #   reguł, a w stanie STOP cyklicznie publikuje zero, by nadpisywać potencjalnie zakolejkowane komendy.
        # TODO: Dodać dynamiczną rekonfigurację `safety_tick_hz` i metrykę jittera timera dla diagnostyki RT.
        self.declare_parameter('safety_tick_hz', 20.0)

        self._use_heartbeat = bool(self.get_parameter('use_heartbeat').value)
        self._heartbeat_msg_type = str(self.get_parameter('heartbeat_msg_type').value).strip().lower()
        self._heartbeat_timeout_s = float(self.get_parameter('heartbeat_timeout_s').value)
        self._enable_trigger_services = bool(self.get_parameter('enable_trigger_services').value)
        self._require_arm_to_clear = bool(self.get_parameter('require_arm_to_clear').value)
        self._safety_tick_hz = float(self.get_parameter('safety_tick_hz').value)

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
        if self._safety_tick_hz <= 0.0:
            self.get_logger().warn(
                'Parametr safety_tick_hz <= 0.0, ustawiam wartość bezpieczną 20.0 Hz.'
            )
            self._safety_tick_hz = 20.0

        # [AI-CHANGE | 2026-04-19 22:02 UTC | v0.129]
        # CO ZMIENIONO: Wprowadzono jawną maszynę stanów `STOPPED`/`RUN_ALLOWED` wraz z rejestrem powodów przejść.
        #   Dodano pola `_estop_asserted`, `_armed`, `_state` i metody `_evaluate_and_apply_state` oraz `_set_state`.
        # DLACZEGO: Uproszczona i deterministyczna logika stanu zwiększa czytelność bezpieczeństwa oraz ułatwia audyt.
        # JAK TO DZIAŁA: Każde zdarzenie wejściowe (signal/heartbeat/arm/serwis) wywołuje ocenę reguł.
        #   Stan przełącza się wyłącznie przez `_set_state`, która loguje konkretny powód (`manual_trigger`,
        #   `heartbeat_timeout`, `signal_false`, `service_clear`, itp.) i publikuje zero przy przejściu do STOPPED.
        # TODO: Dodać licznik i metryki częstości przejść stanów dla monitoringu runtime.
        self._estop_asserted = True
        self._armed = False
        self._last_cmd = Twist()
        self._last_heartbeat_time: Time | None = None
        self._state = RunState.STOPPED

        self._cmd_in_sub = self.create_subscription(Twist, 'cmd_vel_in', self._on_cmd_vel_in, 10)
        self._estop_signal_sub = self.create_subscription(Bool, 'estop_signal', self._on_estop_signal, 10)
        self._estop_arm_sub = self.create_subscription(Bool, 'estop_arm', self._on_estop_arm, 10)
        self._cmd_out_pub = self.create_publisher(Twist, 'cmd_vel_out', 10)
        self._estop_active_pub = self.create_publisher(Bool, '/emergency_stop/active', 10)

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

        self._trigger_srv = None
        self._clear_srv = None
        if self._enable_trigger_services:
            self._trigger_srv = self.create_service(
                Trigger,
                '/emergency_stop/trigger',
                self._on_trigger_service,
            )
            self._clear_srv = self.create_service(
                Trigger,
                '/emergency_stop/clear',
                self._on_clear_service,
            )

        # [AI-CHANGE | 2026-04-20 06:28 UTC | v0.135]
        # CO ZMIENIONO: Dodano timer watchdog bezpieczeństwa i publikację stanu E-STOP na topicu
        #   `/emergency_stop/active` (Bool).
        # DLACZEGO: Integratory i bridge robota potrzebują jawnego sygnału STOP, a sam watchdog ma
        #   wymuszać reakcję nawet bez nowych wiadomości wejściowych.
        # JAK TO DZIAŁA: Timer cyklicznie wywołuje `_on_safety_tick`, która odświeża stan i publikuje
        #   wyjścia bezpieczeństwa; topic `/emergency_stop/active` jest `True` w stanie STOPPED.
        # TODO: Dodać osobny topic diagnostyczny ze stringiem powodu ostatniego przejścia stanu.
        self._safety_timer = self.create_timer(1.0 / max(self._safety_tick_hz, 1.0), self._on_safety_tick)
        self._publish_safety_outputs()
        self.get_logger().info('EmergencyStopNode uruchomiony w trybie fail-safe (stan=STOPPED).')

    def _on_cmd_vel_in(self, msg: Twist) -> None:
        """Przepuszcza komendę tylko w stanie RUN_ALLOWED."""
        self._last_cmd = copy.deepcopy(msg)
        self._evaluate_and_apply_state(reason_hint='cmd_input_check')
        if self._state == RunState.RUN_ALLOWED:
            self._cmd_out_pub.publish(msg)
            return
        self._publish_zero_cmd()

    def _on_estop_signal(self, msg: Bool) -> None:
        """Główny interfejs produkcyjny: `True` zatrzymuje, `False` zezwala na próbę odblokowania."""
        self._estop_asserted = bool(msg.data)
        reason = 'manual_trigger' if self._estop_asserted else 'signal_false'
        self._evaluate_and_apply_state(reason_hint=reason)

    def _on_estop_arm(self, msg: Bool) -> None:
        """Aktualizuje status uzbrojenia systemu wymagany do bezpiecznego clear."""
        self._armed = bool(msg.data)
        reason = 'arm_true' if self._armed else 'arm_false'
        self._evaluate_and_apply_state(reason_hint=reason)

    def _on_heartbeat_empty(self, _msg: Empty) -> None:
        """Rejestruje heartbeat typu Empty i ponownie ocenia warunki odblokowania."""
        self._last_heartbeat_time = self.get_clock().now()
        self._evaluate_and_apply_state(reason_hint='heartbeat_received')

    def _on_heartbeat_bool(self, msg: Bool) -> None:
        """Rejestruje heartbeat Bool tylko gdy wartość jest jawnie True."""
        if not msg.data:
            return
        self._last_heartbeat_time = self.get_clock().now()
        self._evaluate_and_apply_state(reason_hint='heartbeat_received')

    def _on_trigger_service(self, _request: Trigger.Request, response: Trigger.Response) -> Trigger.Response:
        """Ręczne wymuszenie STOP przez opcjonalny serwis administracyjny."""
        self._estop_asserted = True
        self._evaluate_and_apply_state(reason_hint='manual_trigger')
        response.success = True
        response.message = 'E-STOP aktywowany.'
        return response

    def _on_clear_service(self, _request: Trigger.Request, response: Trigger.Response) -> Trigger.Response:
        """Próba wyjścia ze STOP tylko gdy spełnione są warunki bezpieczeństwa."""
        self._estop_asserted = False
        self._evaluate_and_apply_state(reason_hint='service_clear')
        if self._state == RunState.RUN_ALLOWED:
            response.success = True
            response.message = 'E-STOP wyczyszczony, RUN_ALLOWED.'
            return response

        self._estop_asserted = True
        self._evaluate_and_apply_state(reason_hint='clear_rejected')
        response.success = False
        response.message = 'Odrzucono clear: niespełnione warunki heartbeat/arm.'
        return response

    def _evaluate_and_apply_state(self, reason_hint: str) -> None:
        """Ocena reguł bezpieczeństwa i zastosowanie właściwego stanu maszyny."""
        if self._estop_asserted:
            self._set_state(RunState.STOPPED, reason_hint)
            return

        if self._use_heartbeat:
            if self._last_heartbeat_time is None:
                self._set_state(RunState.STOPPED, 'heartbeat_missing')
                return
            elapsed = self.get_clock().now() - self._last_heartbeat_time
            if elapsed > self._heartbeat_timeout:
                self._set_state(RunState.STOPPED, 'heartbeat_timeout')
                return

        if self._require_arm_to_clear and not self._armed:
            self._set_state(RunState.STOPPED, 'arm_required')
            return

        self._set_state(RunState.RUN_ALLOWED, reason_hint)

    def _set_state(self, new_state: RunState, reason: str) -> None:
        """Ustawia nowy stan i loguje powód przejścia."""
        if self._state == new_state:
            return

        previous_state = self._state
        self._state = new_state
        self.get_logger().info(
            'Przejście stanu: %s -> %s (powód=%s)'
            % (previous_state.value, new_state.value, reason)
        )
        if new_state == RunState.STOPPED:
            self._publish_zero_cmd()
        self._publish_estop_active()

    def _on_safety_tick(self) -> None:
        """Cykliczny watchdog bezpieczeństwa aktualizujący stan i wymuszający sygnał STOP."""
        self._evaluate_and_apply_state(reason_hint='safety_tick')
        if self._state == RunState.STOPPED:
            self._publish_zero_cmd()
        self._publish_estop_active()

    def _publish_zero_cmd(self) -> None:
        """Publikuje zerową prędkość na wyjście bezpieczeństwa."""
        self._cmd_out_pub.publish(Twist())

    def _publish_estop_active(self) -> None:
        """Publikuje jawny status aktywnego E-STOP dla innych modułów wykonawczych."""
        msg = Bool()
        msg.data = self._state == RunState.STOPPED
        self._estop_active_pub.publish(msg)

    def _publish_safety_outputs(self) -> None:
        """Publikuje komplet wyjść bezpieczeństwa przy starcie i zmianach krytycznych."""
        self._publish_zero_cmd()
        self._publish_estop_active()


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
