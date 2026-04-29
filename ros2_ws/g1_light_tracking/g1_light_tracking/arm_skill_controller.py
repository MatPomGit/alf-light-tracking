"""Kontroler sekwencji ramion (grasp skills) dla scenariusza move parcel."""

from __future__ import annotations

import threading
import time
from typing import Any, Callable, List, Optional, Set, cast


class ArmSkillController:
    """Wykonuje akcje ramion przez Unitree arm_sdk."""

    ACTION_PICK = 'pick_box'
    ACTION_PLACE = 'place_box'

    ARM_JOINTS = [
        15, 16, 17, 18, 19, 20, 21,
        22, 23, 24, 25, 26, 27, 28,
        12, 13, 14,
    ]
    ARM_ENABLE_JOINT = 29

    CONTROL_DT_S = 0.02
    KP = 80.0
    KD = 2.0

    PICK_T_MOVE_S = 2.0

    PLACE_T_SNAP_S = 1.0
    PLACE_T_MOVE_S = 2.0
    PLACE_T_RETURN_S = 1.0
    PLACE_T_RELEASE_S = 1.0

    # rece_pozycja_7_5_pobranie.py (P0..P6)
    PICK_P0 = [
        +0.2910, +0.0000, +0.0000, +0.0000, +0.0000, +0.0000, +0.0000,
        +0.2390, +0.0000, +0.0000, +0.0000, +0.0000, +0.0000, +0.0000,
        +0.0000, +0.0000, +0.0000,
    ]
    PICK_P1 = [
        +0.6330, +0.3020, +0.1090, -0.6580, -0.3620, +0.0600, +0.1150,
        +0.6330, -0.3020, -0.1090, -0.6580, +0.3620, +0.0600, -0.1150,
        +0.0000, +0.0000, +0.0000,
    ]
    PICK_P2 = [
        -0.7280, +0.2980, -0.1620, +0.6090, +0.0740, +0.1560, +0.1960,
        -0.7280, -0.2980, +0.1620, +0.6090, -0.0740, +0.1560, -0.1960,
        +0.0000, +0.0000, +0.0000,
    ]
    PICK_P3 = [
        -0.8280, +0.2480, -0.1620, +0.6090, +0.0740, +0.1560, +0.5960,
        -0.7780, -0.0480, +0.1620, +0.6090, -0.0740, +0.1560, -0.8960,
        +0.0000, +0.0000, +0.0000,
    ]
    PICK_P4 = [
        -0.8280, +0.0480, -0.1620, +0.6090, +0.0740, +0.1560, +0.1960,
        -0.7780, +0.0020, +0.1620, +0.6090, -0.0740, +0.1560, -0.1960,
        +0.0000, +0.0000, +0.0000,
    ]
    PICK_P5 = [
        -0.8780, +0.0480, -0.2620, +0.3090, +0.0740, +0.3560, +0.4960,
        -0.8780, -0.0480, +0.2620, +0.3090, -0.0740, +0.3560, -0.4960,
        +0.0000, +0.0000, +0.0000,
    ]
    PICK_P6 = [
        -0.4780, +0.0480, -0.2620, -0.1910, +0.0740, +0.3560, +0.4960,
        -0.4780, -0.0480, +0.2620, -0.1910, -0.0740, +0.3560, -0.4960,
        +0.0000, +0.0000, +0.0000,
    ]

    PICK_POSITIONS = [PICK_P0, PICK_P1, PICK_P2, PICK_P3, PICK_P4, PICK_P5, PICK_P6]
    PLACE_POSITIONS = [PICK_P5, PICK_P4, PICK_P3, PICK_P2]
    ZERO = [0.0] * len(ARM_JOINTS)

    def __init__(
        self,
        low_cmd_ctor,
        arm_publisher,
        crc,
        get_low_state: Callable[[], Optional[object]],
        log_fn: Callable[[str], None],
    ):
        """
        Cel: Ta metoda realizuje odpowiedzialność `__init__` w aktualnym module.
        Dlaczego tak: Wydzielenie tej jednostki upraszcza debugowanie i chroni krytyczne ścieżki przed niekontrolowanymi zmianami.
        """
        self._LowCmdCtor = low_cmd_ctor
        self._arm_publisher = arm_publisher
        self._crc = crc
        self._get_low_state = get_low_state
        self._log = log_fn
        self._stop_event = threading.Event()

    @property
    def action_names(self) -> Set[str]:
        """
        Cel: Ta metoda realizuje odpowiedzialność `action_names` w aktualnym module.
        Dlaczego tak: Wydzielenie tej jednostki upraszcza debugowanie i chroni krytyczne ścieżki przed niekontrolowanymi zmianami.
        """
        return {self.ACTION_PICK, self.ACTION_PLACE}

    def run_action(self, action_name: str):
        """
        Cel: Ta metoda realizuje odpowiedzialność `run_action` w aktualnym module.
        Dlaczego tak: Wydzielenie tej jednostki upraszcza debugowanie i chroni krytyczne ścieżki przed niekontrolowanymi zmianami.
        """
        self._stop_event.clear()
        if action_name == self.ACTION_PICK:
            self._run_pick_sequence()
            return
        if action_name == self.ACTION_PLACE:
            self._run_place_sequence()
            return
        raise ValueError(f'Nieobsługiwana akcja ramion: {action_name}')

    def stop(self):
        """Wymusza awaryjne przerwanie sekwencji i wyłączenie arm_sdk."""
        self._stop_event.set()
        self._publish_sdk_enable(value=0.0)
        self._log('Wymuszono stop sekwencji ramion (arm_sdk disable).')

    def _run_pick_sequence(self):
        """rece_pozycja_7_5_pobranie: q_act -> P0 -> ... -> P6, bez release."""
        self._wait_for_low_state(timeout_s=5.0)

        previous = self._snapshot_current_pose()
        for position in self.PICK_POSITIONS:
            self._run_interpolation_stage(
                from_pose=previous,
                to_pose=position,
                duration_s=self.PICK_T_MOVE_S,
                weight_start=1.0,
                weight_end=1.0,
            )
            previous = position

        self._publish_pose(self.PICK_POSITIONS[-1], weight=1.0)
        self._log('Zakończono sekwencję ramion: pick_box (7_5).')

    def _run_place_sequence(self):
        """rece_pozycja_8_5_odlozenie: q_act -> P5..P2 -> 0 -> release."""
        self._wait_for_low_state(timeout_s=5.0)

        snap_start = self._snapshot_current_pose()
        self._run_interpolation_stage(
            from_pose=snap_start,
            to_pose=self.PICK_P5,
            duration_s=self.PLACE_T_SNAP_S,
            weight_start=1.0,
            weight_end=1.0,
        )

        previous = self.PICK_P5
        for position in self.PLACE_POSITIONS:
            self._run_interpolation_stage(
                from_pose=previous,
                to_pose=position,
                duration_s=self.PLACE_T_MOVE_S,
                weight_start=1.0,
                weight_end=1.0,
            )
            previous = position

        return_start = self._snapshot_current_pose()
        self._run_interpolation_stage(
            from_pose=return_start,
            to_pose=self.ZERO,
            duration_s=self.PLACE_T_RETURN_S,
            weight_start=1.0,
            weight_end=1.0,
        )

        self._run_interpolation_stage(
            from_pose=self.ZERO,
            to_pose=self.ZERO,
            duration_s=self.PLACE_T_RELEASE_S,
            weight_start=1.0,
            weight_end=0.0,
        )
        self._publish_pose(self.ZERO, weight=0.0)
        self._log('Zakończono sekwencję ramion: place_box (8_5).')

    def _run_interpolation_stage(
        self,
        from_pose: List[float],
        to_pose: List[float],
        duration_s: float,
        weight_start: float,
        weight_end: float,
    ):
        """
        Cel: Ta metoda realizuje odpowiedzialność `_run_interpolation_stage` w aktualnym module.
        Dlaczego tak: Wydzielenie tej jednostki upraszcza debugowanie i chroni krytyczne ścieżki przed niekontrolowanymi zmianami.
        """
        duration_s = max(float(duration_s), 0.0)
        if duration_s <= 0.0:
            self._publish_pose(to_pose, weight=weight_end)
            return

        start = time.monotonic()
        while True:
            self._raise_if_stop_requested()
            elapsed = time.monotonic() - start
            if elapsed >= duration_s:
                break

            ratio = self._clip01(elapsed / duration_s)
            pose = self._interp(from_pose, to_pose, ratio)
            weight = (1.0 - ratio) * weight_start + ratio * weight_end
            self._publish_pose(pose, weight=weight)
            time.sleep(self.CONTROL_DT_S)

        self._publish_pose(to_pose, weight=weight_end)

    def _publish_pose(self, pose: List[float], weight: float):
        """
        Cel: Ta metoda realizuje odpowiedzialność `_publish_pose` w aktualnym module.
        Dlaczego tak: Wydzielenie tej jednostki upraszcza debugowanie i chroni krytyczne ścieżki przed niekontrolowanymi zmianami.
        """
        low_state = self._get_low_state()
        if low_state is None:
            raise RuntimeError('Brak stanu low_state w trakcie sekwencji ramion.')

        low_cmd = self._LowCmdCtor()
        low_cmd.motor_cmd[self.ARM_ENABLE_JOINT].q = float(weight)

        for idx, joint in enumerate(self.ARM_JOINTS):
            cmd = low_cmd.motor_cmd[joint]
            cmd.tau = 0.0
            cmd.q = float(pose[idx])
            cmd.dq = 0.0
            cmd.kp = self.KP
            cmd.kd = self.KD

        low_cmd.crc = self._crc.Crc(low_cmd)
        self._arm_publisher.Write(low_cmd)

    def _publish_sdk_enable(self, value: float):
        """
        Cel: Ta metoda realizuje odpowiedzialność `_publish_sdk_enable` w aktualnym module.
        Dlaczego tak: Wydzielenie tej jednostki upraszcza debugowanie i chroni krytyczne ścieżki przed niekontrolowanymi zmianami.
        """
        low_cmd = self._LowCmdCtor()
        low_cmd.motor_cmd[self.ARM_ENABLE_JOINT].q = float(value)
        low_cmd.crc = self._crc.Crc(low_cmd)
        self._arm_publisher.Write(low_cmd)

    def _snapshot_current_pose(self) -> List[float]:
        """
        Cel: Ta metoda realizuje odpowiedzialność `_snapshot_current_pose` w aktualnym module.
        Dlaczego tak: Wydzielenie tej jednostki upraszcza debugowanie i chroni krytyczne ścieżki przed niekontrolowanymi zmianami.
        """
        low_state = self._get_low_state()
        if low_state is None:
            raise RuntimeError('Brak stanu low_state w trakcie sekwencji ramion.')
        # [AI-CHANGE | 2026-04-29 13:35 UTC | v0.333]
        # CO ZMIENIONO: Zawężono typ `low_state` do obiektu dynamicznego przed odczytem `motor_state`.
        # DLACZEGO: SDK Unitree dostarcza typy runtime bez kompletnych adnotacji, więc `mypy` widzi wynik jako `object`
        #           i blokuje dostęp do pola mimo wcześniejszej walidacji obecności stanu.
        # JAK TO DZIAŁA: Po odrzuceniu `None` rzutowanie na `Any` dotyczy tylko odczytu snapshotu pozycji;
        #                jeśli SDK zwróci niepoprawny obiekt, wyjątek nadal zatrzyma sekwencję zamiast zwrócić fałszywą pozę.
        # TODO: Dodać lokalny `Protocol` dla LowState z polami `motor_state[].q`, aby zastąpić `Any` typem strukturalnym.
        typed_low_state = cast(Any, low_state)
        return [float(typed_low_state.motor_state[joint].q) for joint in self.ARM_JOINTS]

    def _wait_for_low_state(self, timeout_s: float):
        """
        Cel: Ta metoda realizuje odpowiedzialność `_wait_for_low_state` w aktualnym module.
        Dlaczego tak: Wydzielenie tej jednostki upraszcza debugowanie i chroni krytyczne ścieżki przed niekontrolowanymi zmianami.
        """
        start = time.monotonic()
        while self._get_low_state() is None:
            if (time.monotonic() - start) >= timeout_s:
                raise RuntimeError('Brak wiadomości lowstate (timeout).')
            time.sleep(0.05)

    def _raise_if_stop_requested(self):
        """
        Cel: Ta metoda realizuje odpowiedzialność `_raise_if_stop_requested` w aktualnym module.
        Dlaczego tak: Wydzielenie tej jednostki upraszcza debugowanie i chroni krytyczne ścieżki przed niekontrolowanymi zmianami.
        """
        if not self._stop_event.is_set():
            return
        self._publish_sdk_enable(value=0.0)
        raise RuntimeError('Sekwencja ramion przerwana awaryjnie.')

    @staticmethod
    def _clip01(value: float) -> float:
        """
        Cel: Ta metoda realizuje odpowiedzialność `_clip01` w aktualnym module.
        Dlaczego tak: Wydzielenie tej jednostki upraszcza debugowanie i chroni krytyczne ścieżki przed niekontrolowanymi zmianami.
        """
        return max(0.0, min(1.0, value))

    @staticmethod
    def _interp(a: List[float], b: List[float], ratio: float) -> List[float]:
        """
        Cel: Ta metoda realizuje odpowiedzialność `_interp` w aktualnym module.
        Dlaczego tak: Wydzielenie tej jednostki upraszcza debugowanie i chroni krytyczne ścieżki przed niekontrolowanymi zmianami.
        """
        return [(1.0 - ratio) * av + ratio * bv for av, bv in zip(a, b)]
