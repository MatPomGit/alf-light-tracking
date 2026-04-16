"""Node ROS 2 do kontrolowanego nagrywania rosbag2 jako proces podrzędny.

Node wspiera dwa tryby pracy:
1) ręczne start/stop przez serwis SetBool,
2) automatyczne włączanie na podstawie aktywności misji (FSM z MissionState).
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import rclpy
from rclpy.node import Node
from std_srvs.srv import SetBool

from g1_light_tracking.msg import MissionState


MISSION_INACTIVE_STATES = {
    'idle',
    'standby',
    'waiting',
    'completed',
    'done',
    'failed',
    'error',
}


@dataclass
class SessionMetadata:
    """Metadane jednej sesji nagrywania zapisywane obok bag'a."""

    bag_uri: str
    started_at_utc: str
    stop_reason: str
    start_reason: str
    mission_active_on_start: bool
    mission_state_initial: dict[str, Any] | None
    scenario_hint: str


class RosbagRecorderNode(Node):
    """Node zarządzający procesem `ros2 bag record` z bezpiecznym zamykaniem."""

    def __init__(self) -> None:
        super().__init__('rosbag_recorder_node')

        # Parametry operacyjne nagrywania i sterowania.
        self.declare_parameter('output_dir', '/tmp/rosbags')
        self.declare_parameter('bag_prefix', 'session')
        self.declare_parameter('record_all_topics', True)
        self.declare_parameter('topics_allowlist', ['/mission/state', '/mission/target'])
        self.declare_parameter('compression_mode', '')
        self.declare_parameter('compression_format', '')
        self.declare_parameter('split_size_mb', 0)
        self.declare_parameter('start_on_launch', False)
        self.declare_parameter('record_only_when_mission_active', False)

        self.output_dir = Path(str(self.get_parameter('output_dir').value)).expanduser()
        self.bag_prefix = str(self.get_parameter('bag_prefix').value)
        self.record_all_topics = bool(self.get_parameter('record_all_topics').value)
        self.topics_allowlist = [str(t) for t in self.get_parameter('topics_allowlist').value]
        self.compression_mode = str(self.get_parameter('compression_mode').value)
        self.compression_format = str(self.get_parameter('compression_format').value)
        self.split_size_mb = int(self.get_parameter('split_size_mb').value)
        self.start_on_launch = bool(self.get_parameter('start_on_launch').value)
        self.record_only_when_mission_active = bool(
            self.get_parameter('record_only_when_mission_active').value
        )

        self.user_enabled = self.start_on_launch
        self.mission_is_active = False
        self.last_mission_state: MissionState | None = None

        self.record_process: subprocess.Popen[str] | None = None
        self.current_bag_uri = ''
        self.current_metadata_path = ''
        self.current_start_reason = ''

        self.create_subscription(MissionState, '/mission/state', self.on_mission_state, 20)
        self.enable_srv = self.create_service(SetBool, '/rosbag_recorder/enable', self.handle_enable)
        self.rotate_srv = self.create_service(SetBool, '/rosbag_recorder/rotate', self.handle_rotate)
        self.timer = self.create_timer(0.5, self.reconcile_recording_state)

        self.get_logger().info(
            'RosbagRecorderNode started. '
            f'output_dir={self.output_dir}, bag_prefix={self.bag_prefix}, '
            f'record_all_topics={self.record_all_topics}, '
            f'start_on_launch={self.start_on_launch}, '
            f'record_only_when_mission_active={self.record_only_when_mission_active}'
        )

        self.reconcile_recording_state()

    def on_mission_state(self, msg: MissionState) -> None:
        """Aktualizuje flagę aktywności misji i synchronizuje stan nagrywania."""
        self.last_mission_state = msg
        self.mission_is_active = self.is_mission_active(msg)
        self.reconcile_recording_state()

    def is_mission_active(self, msg: MissionState) -> bool:
        """Ocena aktywności misji na podstawie wiadomości FSM."""
        state = msg.state.strip().lower()
        if msg.is_terminal:
            return False
        if not state:
            return False
        return state not in MISSION_INACTIVE_STATES

    def desired_recording_enabled(self) -> bool:
        """Wylicza docelowy stan nagrywania wynikający z parametrów i FSM."""
        if not self.user_enabled:
            return False
        if not self.record_only_when_mission_active:
            return True
        return self.mission_is_active

    def reconcile_recording_state(self) -> None:
        """Doprowadza proces nagrywania do stanu oczekiwanego."""
        self.handle_unexpected_process_exit()

        should_record = self.desired_recording_enabled()
        is_recording = self.is_recording()

        if should_record and not is_recording:
            self.start_recording('automatic_reconcile')
        elif not should_record and is_recording:
            self.stop_recording('automatic_reconcile')

    def handle_enable(self, request: SetBool.Request, response: SetBool.Response) -> SetBool.Response:
        """Serwis SetBool do ręcznego włączenia/wyłączenia nagrywania."""
        self.user_enabled = bool(request.data)
        self.reconcile_recording_state()

        response.success = True
        response.message = (
            f'user_enabled={self.user_enabled}, '
            f'mission_active={self.mission_is_active}, '
            f'recording={self.is_recording()}'
        )
        return response

    def handle_rotate(self, request: SetBool.Request, response: SetBool.Response) -> SetBool.Response:
        """Opcjonalny obrót sesji: zamknięcie i otwarcie nowego bag'a."""
        if not request.data:
            response.success = True
            response.message = 'rotate ignored because request.data=false'
            return response

        if not self.is_recording():
            response.success = False
            response.message = 'rotate rejected because recorder is not running'
            return response

        self.stop_recording('manual_rotate')

        if self.desired_recording_enabled():
            self.start_recording('manual_rotate')
            response.success = self.is_recording()
            response.message = 'rotation completed'
            return response

        response.success = False
        response.message = 'rotation stopped recorder but desired state is disabled'
        return response

    def build_record_command(self, bag_uri: str) -> list[str]:
        """Buduje kompletną komendę `ros2 bag record` na bazie parametrów."""
        cmd = ['ros2', 'bag', 'record', '-o', bag_uri]

        if self.record_all_topics:
            cmd.append('-a')
        else:
            cmd.extend(self.topics_allowlist)

        if self.compression_mode:
            cmd.extend(['--compression-mode', self.compression_mode])
        if self.compression_format:
            cmd.extend(['--compression-format', self.compression_format])
        if self.split_size_mb > 0:
            cmd.extend(['--max-bag-size', str(self.split_size_mb * 1024 * 1024)])

        return cmd

    def start_recording(self, reason: str) -> None:
        """Startuje proces `ros2 bag record` i zapisuje metadane sesji."""
        if self.is_recording():
            return

        if not self.record_all_topics and not self.topics_allowlist:
            self.get_logger().error('Cannot start recording: topics_allowlist is empty.')
            return

        self.output_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')
        bag_name = f'{self.bag_prefix}_{timestamp}'
        bag_uri = str(self.output_dir / bag_name)
        metadata_path = str(self.output_dir / f'{bag_name}_session.json')

        cmd = self.build_record_command(bag_uri)
        self.get_logger().info(f'Starting rosbag recorder. reason={reason}, cmd={cmd}')

        try:
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                text=True,
                preexec_fn=os.setsid,
            )
        except Exception as exc:
            self.get_logger().error(f'Failed to start rosbag process: {exc}')
            return

        self.record_process = process
        self.current_bag_uri = bag_uri
        self.current_metadata_path = metadata_path
        self.current_start_reason = reason

        self.write_session_metadata(stop_reason='running')

    def stop_recording(self, reason: str) -> None:
        """Zamyka proces nagrywania (SIGINT -> timeout -> SIGTERM) i loguje przyczynę."""
        process = self.record_process
        if process is None:
            return

        if process.poll() is not None:
            self.get_logger().info(
                f'Recorder process already stopped. reason={reason}, exit_code={process.returncode}'
            )
            self.write_session_metadata(stop_reason=f'{reason}:already_stopped')
            self.clear_process_state()
            return

        self.get_logger().info(f'Stopping recorder with SIGINT. reason={reason}')

        try:
            os.killpg(os.getpgid(process.pid), signal.SIGINT)
            process.wait(timeout=8.0)
        except subprocess.TimeoutExpired:
            self.get_logger().warning('Recorder SIGINT timeout exceeded, sending SIGTERM fallback.')
            os.killpg(os.getpgid(process.pid), signal.SIGTERM)
            try:
                process.wait(timeout=4.0)
            except subprocess.TimeoutExpired:
                self.get_logger().error('Recorder SIGTERM timeout exceeded, sending SIGKILL fallback.')
                os.killpg(os.getpgid(process.pid), signal.SIGKILL)
                process.wait(timeout=2.0)

        self.get_logger().info(
            f'Recorder stopped. reason={reason}, exit_code={process.returncode}, bag_uri={self.current_bag_uri}'
        )
        self.write_session_metadata(stop_reason=reason)
        self.clear_process_state()

    def handle_unexpected_process_exit(self) -> None:
        """Wykrywa awaryjne zakończenie procesu i czyści stan node'a."""
        process = self.record_process
        if process is None:
            return

        if process.poll() is None:
            return

        self.get_logger().warning(
            f'Recorder exited unexpectedly with code={process.returncode}. '
            f'bag_uri={self.current_bag_uri}'
        )
        self.write_session_metadata(stop_reason='unexpected_exit')
        self.clear_process_state()

    def write_session_metadata(self, stop_reason: str) -> None:
        """Zapisuje JSON z metadanymi sesji obok katalogu bag'a."""
        if not self.current_metadata_path:
            return

        mission_state_payload = None
        scenario_hint = ''

        if self.last_mission_state is not None:
            mission_state_payload = {
                'state': self.last_mission_state.state,
                'previous_state': self.last_mission_state.previous_state,
                'reason': self.last_mission_state.reason,
                'active_target_mode': self.last_mission_state.active_target_mode,
                'active_target_type': self.last_mission_state.active_target_type,
                'active_shipment_id': self.last_mission_state.active_shipment_id,
                'is_terminal': self.last_mission_state.is_terminal,
            }
            scenario_hint = (
                self.last_mission_state.active_target_mode
                or self.last_mission_state.reason
                or self.last_mission_state.state
            )

        payload = SessionMetadata(
            bag_uri=self.current_bag_uri,
            started_at_utc=datetime.now(timezone.utc).isoformat(),
            stop_reason=stop_reason,
            start_reason=self.current_start_reason,
            mission_active_on_start=self.mission_is_active,
            mission_state_initial=mission_state_payload,
            scenario_hint=scenario_hint,
        )

        try:
            Path(self.current_metadata_path).write_text(
                json.dumps(payload.__dict__, indent=2, ensure_ascii=False),
                encoding='utf-8',
            )
        except Exception as exc:
            self.get_logger().error(f'Failed to write metadata JSON: {exc}')

    def is_recording(self) -> bool:
        """Sprawdza czy proces nagrywania aktualnie działa."""
        return self.record_process is not None and self.record_process.poll() is None

    def clear_process_state(self) -> None:
        """Czyści dane pomocnicze związane z bieżącą sesją."""
        self.record_process = None
        self.current_bag_uri = ''
        self.current_metadata_path = ''
        self.current_start_reason = ''

    def destroy_node(self) -> bool:
        """Zapewnia bezpieczne zatrzymanie nagrywania przy zamknięciu node'a."""
        if self.is_recording():
            self.stop_recording('node_shutdown')
        return super().destroy_node()


def main(args: list[str] | None = None) -> None:
    """Punkt wejścia procesu ROS 2."""
    rclpy.init(args=args)
    node = RosbagRecorderNode()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
