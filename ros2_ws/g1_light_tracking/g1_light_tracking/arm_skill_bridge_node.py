import struct
import sys
import threading
from typing import Optional

import rclpy
from rclpy.node import Node
from std_srvs.srv import Trigger

try:
    # [AI-CHANGE | 2026-04-29 13:35 UTC | v0.333]
    # CO ZMIENIONO: Usunięto nieużywane komentarze `type: ignore` z opcjonalnego importu `unitree_hg`.
    # DLACZEGO: W środowisku z dostępnymi stubami komentarze były raportowane jako nieużywane i blokowały pełne `mypy`.
    # JAK TO DZIAŁA: Import pozostaje opcjonalny; brak pakietu nadal zapisuje błąd w `_UNITREE_HG_IMPORT_ERROR`
    #                i pozwala warstwie runtime odrzucić uruchomienie zależne od brakującego typu.
    # TODO: Dodać minimalne stuby lokalne dla `unitree_hg.msg`, aby typować konstrukcję LowCmd/LowState bez importu runtime.
    from unitree_hg.msg import LowCmd, LowState
    _UNITREE_HG_IMPORT_ERROR = None
except ImportError as exc:
    LowCmd = None
    LowState = None
    _UNITREE_HG_IMPORT_ERROR = exc

from g1_light_tracking.arm_skill_controller import ArmSkillController


class _RosPublisherAdapter:
    """
    Cel: Ta klasa realizuje odpowiedzialność `_RosPublisherAdapter` w aktualnym module.
    Dlaczego tak: Wydzielenie tej jednostki upraszcza debugowanie i chroni krytyczne ścieżki przed niekontrolowanymi zmianami.
    """
    def __init__(self, publisher):
        """
        Cel: Ta metoda realizuje odpowiedzialność `__init__` w aktualnym module.
        Dlaczego tak: Wydzielenie tej jednostki upraszcza debugowanie i chroni krytyczne ścieżki przed niekontrolowanymi zmianami.
        """
        self._publisher = publisher

    def Write(self, msg) -> None:
        """
        Cel: Ta metoda realizuje odpowiedzialność `Write` w aktualnym module.
        Dlaczego tak: Wydzielenie tej jednostki upraszcza debugowanie i chroni krytyczne ścieżki przed niekontrolowanymi zmianami.
        """
        self._publisher.publish(msg)


class _LowCmdCrc:
    """CRC dla unitree_hg/msg/LowCmd zgodny z unitree_ros2 motor_crc_hg.cpp."""

    _POLYNOMIAL = 0x04C11DB7
    _INIT = 0xFFFFFFFF

    def Crc(self, msg: LowCmd) -> int:
        """
        Cel: Ta metoda realizuje odpowiedzialność `Crc` w aktualnym module.
        Dlaczego tak: Wydzielenie tej jednostki upraszcza debugowanie i chroni krytyczne ścieżki przed niekontrolowanymi zmianami.
        """
        words = self._to_words(msg)
        return self._crc32_core(words)

    def _to_words(self, msg: LowCmd):
        """
        Cel: Ta metoda realizuje odpowiedzialność `_to_words` w aktualnym module.
        Dlaczego tak: Wydzielenie tej jednostki upraszcza debugowanie i chroni krytyczne ścieżki przed niekontrolowanymi zmianami.
        """
        raw = bytearray()
        raw.extend(struct.pack('<BB2x', int(msg.mode_pr), int(msg.mode_machine)))

        for motor in msg.motor_cmd:
            raw.extend(
                struct.pack(
                    '<B3x5fI',
                    int(motor.mode),
                    float(motor.q),
                    float(motor.dq),
                    float(motor.tau),
                    float(motor.kp),
                    float(motor.kd),
                    int(motor.reserve),
                )
            )

        reserve = list(msg.reserve)
        if len(reserve) < 4:
            reserve = reserve + [0] * (4 - len(reserve))
        raw.extend(struct.pack('<4I', int(reserve[0]), int(reserve[1]), int(reserve[2]), int(reserve[3])))

        # 1000 bajtow = 250 slow uint32 (bez pola crc)
        return struct.unpack('<250I', bytes(raw[:1000]))

    def _crc32_core(self, words) -> int:
        """
        Cel: Ta metoda realizuje odpowiedzialność `_crc32_core` w aktualnym module.
        Dlaczego tak: Wydzielenie tej jednostki upraszcza debugowanie i chroni krytyczne ścieżki przed niekontrolowanymi zmianami.
        """
        crc = self._INIT
        for data in words:
            xbit = 1 << 31
            for _ in range(32):
                if crc & 0x80000000:
                    crc = ((crc << 1) & 0xFFFFFFFF) ^ self._POLYNOMIAL
                else:
                    crc = (crc << 1) & 0xFFFFFFFF

                if data & xbit:
                    crc ^= self._POLYNOMIAL
                xbit >>= 1
        return crc & 0xFFFFFFFF


class ArmSkillBridgeNode(Node):
    """ROS2 bridge dla sekwencji ramion: pick_box/place_box (pure ROS topics)."""

    def __init__(self) -> None:
        """
        Cel: Ta metoda realizuje odpowiedzialność `__init__` w aktualnym module.
        Dlaczego tak: Wydzielenie tej jednostki upraszcza debugowanie i chroni krytyczne ścieżki przed niekontrolowanymi zmianami.
        """
        super().__init__('arm_skill_bridge_node')

        self.declare_parameter('service_prefix', '/arm_skills')
        self.declare_parameter('arm_sdk_topic', '/arm_sdk')
        self.declare_parameter('lowstate_topic', '/lowstate')

        self._service_prefix = str(self.get_parameter('service_prefix').value).rstrip('/')
        self._arm_sdk_topic = str(self.get_parameter('arm_sdk_topic').value)
        self._lowstate_topic = str(self.get_parameter('lowstate_topic').value)

        if not self._service_prefix:
            self._service_prefix = '/arm_skills'

        self._lock = threading.Lock()
        self._worker = None  # type: Optional[threading.Thread]
        self._current_action = None  # type: Optional[str]

        self._low_state = None
        self._arm_controller = None  # type: Optional[ArmSkillController]
        self._init_error = None  # type: Optional[str]

        self._init_ros_topics()

        self._pick_srv = self.create_service(Trigger, self._service_name('pick_box'), self._handle_pick_box)
        self._place_srv = self.create_service(Trigger, self._service_name('place_box'), self._handle_place_box)
        self._stop_srv = self.create_service(Trigger, self._service_name('stop'), self._handle_stop)

        self.get_logger().info(
            'Arm bridge ready. Services: %s, %s, %s'
            % (
                self._service_name('pick_box'),
                self._service_name('place_box'),
                self._service_name('stop'),
            )
        )

    def _service_name(self, suffix: str) -> str:
        """
        Cel: Ta metoda realizuje odpowiedzialność `_service_name` w aktualnym module.
        Dlaczego tak: Wydzielenie tej jednostki upraszcza debugowanie i chroni krytyczne ścieżki przed niekontrolowanymi zmianami.
        """
        return '%s/%s' % (self._service_prefix, suffix)

    def _init_ros_topics(self) -> None:
        """
        Cel: Ta metoda realizuje odpowiedzialność `_init_ros_topics` w aktualnym module.
        Dlaczego tak: Wydzielenie tej jednostki upraszcza debugowanie i chroni krytyczne ścieżki przed niekontrolowanymi zmianami.
        """
        try:
            arm_pub = self.create_publisher(LowCmd, self._arm_sdk_topic, 10)
            self._low_sub = self.create_subscription(
                LowState,
                self._lowstate_topic,
                self._on_low_state,
                10,
            )
            self._arm_controller = ArmSkillController(
                low_cmd_ctor=LowCmd,
                arm_publisher=_RosPublisherAdapter(arm_pub),
                crc=_LowCmdCrc(),
                get_low_state=self._get_low_state,
                log_fn=self._log_arm,
            )
            self.get_logger().info(
                'ROS arm bridge initialized (arm topic=%s, lowstate topic=%s).'
                % (self._arm_sdk_topic, self._lowstate_topic)
            )
        except Exception as exc:
            self._init_error = 'Nieudana inicjalizacja ROS bridge: %s' % exc
            self.get_logger().error(self._init_error)

    def _on_low_state(self, msg: LowState) -> None:
        """
        Cel: Ta metoda realizuje odpowiedzialność `_on_low_state` w aktualnym module.
        Dlaczego tak: Wydzielenie tej jednostki upraszcza debugowanie i chroni krytyczne ścieżki przed niekontrolowanymi zmianami.
        """
        self._low_state = msg

    def _get_low_state(self):
        """
        Cel: Ta metoda realizuje odpowiedzialność `_get_low_state` w aktualnym module.
        Dlaczego tak: Wydzielenie tej jednostki upraszcza debugowanie i chroni krytyczne ścieżki przed niekontrolowanymi zmianami.
        """
        return self._low_state

    def _handle_pick_box(self, _request, response):
        """
        Cel: Ta metoda realizuje odpowiedzialność `_handle_pick_box` w aktualnym module.
        Dlaczego tak: Wydzielenie tej jednostki upraszcza debugowanie i chroni krytyczne ścieżki przed niekontrolowanymi zmianami.
        """
        return self._start_action(ArmSkillController.ACTION_PICK, response)

    def _handle_place_box(self, _request, response):
        """
        Cel: Ta metoda realizuje odpowiedzialność `_handle_place_box` w aktualnym module.
        Dlaczego tak: Wydzielenie tej jednostki upraszcza debugowanie i chroni krytyczne ścieżki przed niekontrolowanymi zmianami.
        """
        return self._start_action(ArmSkillController.ACTION_PLACE, response)

    def _handle_stop(self, _request, response):
        """
        Cel: Ta metoda realizuje odpowiedzialność `_handle_stop` w aktualnym module.
        Dlaczego tak: Wydzielenie tej jednostki upraszcza debugowanie i chroni krytyczne ścieżki przed niekontrolowanymi zmianami.
        """
        if self._arm_controller is None:
            response.success = False
            response.message = self._init_error or 'Arm controller not initialized.'
            return response
        self._arm_controller.stop()
        response.success = True
        response.message = 'Stop requested.'
        return response

    def _start_action(self, action_name: str, response):
        """
        Cel: Ta metoda realizuje odpowiedzialność `_start_action` w aktualnym module.
        Dlaczego tak: Wydzielenie tej jednostki upraszcza debugowanie i chroni krytyczne ścieżki przed niekontrolowanymi zmianami.
        """
        if self._arm_controller is None:
            response.success = False
            response.message = self._init_error or 'Arm controller not initialized.'
            return response

        with self._lock:
            if self._current_action is not None:
                response.success = False
                response.message = 'Action %s already running. Try later.' % self._current_action
                return response
            self._current_action = action_name
            self._worker = threading.Thread(
                target=self._run_action_worker,
                args=(action_name,),
                daemon=True,
            )
            self._worker.start()

        response.success = True
        response.message = 'Started action: %s' % action_name
        return response

    def _run_action_worker(self, action_name: str) -> None:
        """
        Cel: Ta metoda realizuje odpowiedzialność `_run_action_worker` w aktualnym module.
        Dlaczego tak: Wydzielenie tej jednostki upraszcza debugowanie i chroni krytyczne ścieżki przed niekontrolowanymi zmianami.
        """
        assert self._arm_controller is not None
        self.get_logger().info('Starting arm action: %s' % action_name)
        try:
            self._arm_controller.run_action(action_name)
            self.get_logger().info('Arm action completed: %s' % action_name)
        except Exception as exc:
            self.get_logger().error('Arm action failed (%s): %s' % (action_name, exc))
        finally:
            with self._lock:
                if self._current_action == action_name:
                    self._current_action = None

    def _log_arm(self, message: str) -> None:
        """
        Cel: Ta metoda realizuje odpowiedzialność `_log_arm` w aktualnym module.
        Dlaczego tak: Wydzielenie tej jednostki upraszcza debugowanie i chroni krytyczne ścieżki przed niekontrolowanymi zmianami.
        """
        self.get_logger().info('[arm] %s' % message)

    def destroy_node(self) -> bool:
        """
        Cel: Ta metoda realizuje odpowiedzialność `destroy_node` w aktualnym module.
        Dlaczego tak: Wydzielenie tej jednostki upraszcza debugowanie i chroni krytyczne ścieżki przed niekontrolowanymi zmianami.
        """
        if self._arm_controller is not None:
            try:
                self._arm_controller.stop()
            except Exception:
                pass
        return super().destroy_node()


def main(args=None) -> None:
    """
    Cel: Ta funkcja realizuje odpowiedzialność `main` w aktualnym module.
    Dlaczego tak: Wydzielenie tej jednostki upraszcza debugowanie i chroni krytyczne ścieżki przed niekontrolowanymi zmianami.
    """
    if _UNITREE_HG_IMPORT_ERROR is not None:
        sys.stderr.write(
            'arm_skill_bridge_node requires ROS messages from package "unitree_hg".\n'
            'Import error: %s\n'
            'Build and source the workspace that provides unitree_hg, then retry.\n'
            % _UNITREE_HG_IMPORT_ERROR
        )
        return

    rclpy.init(args=args)
    node = ArmSkillBridgeNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
