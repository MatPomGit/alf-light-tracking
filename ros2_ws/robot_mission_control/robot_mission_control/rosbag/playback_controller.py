"""ROS bag playback controller with global data source locks."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from robot_mission_control.rosbag.integrity_checker import IntegrityChecker, IntegrityResult


# [AI-CHANGE | 2026-04-20 19:41 UTC | v0.149]
# CO ZMIENIONO: Dodano kontroler playback z komendami play/pause/stop/restart/seek/speed/loop,
#               filtrem topiców, globalnym wskaźnikiem źródła LIVE|PLAYBACK i blokadą komend krytycznych.
# DLACZEGO: Podczas odtwarzania dane testowe nie mogą mieszać się z trybem LIVE, a komendy krytyczne
#           (np. sterowanie ruchem) muszą być blokowane dla bezpieczeństwa operacyjnego.
# JAK TO DZIAŁA: play() ustawia source=PLAYBACK tylko po pozytywnej weryfikacji integralności; stop()
#                przywraca LIVE. critical_commands_blocked() zwraca True gdy aktywny playback.
# TODO: Podłączyć backend sterowania `ros2 bag play` i synchroniczny feedback pozycji osi czasu.


class DataSourceMode(Enum):
    """Globalne źródło danych dla aplikacji."""

    LIVE = "LIVE"
    PLAYBACK = "PLAYBACK"


@dataclass(slots=True)
class PlaybackState:
    """Stan sesji odtwarzania rosbaga."""

    bag_path: str | None = None
    is_playing: bool = False
    is_paused: bool = False
    position_seconds: float = 0.0
    speed: float = 1.0
    loop: bool = False
    topic_filter: tuple[str, ...] = ()


class PlaybackController:
    """Kontroler odtwarzania z blokadą komend krytycznych."""

    def __init__(self, integrity_checker: IntegrityChecker | None = None) -> None:
        self._integrity_checker = integrity_checker or IntegrityChecker()
        self._source_mode = DataSourceMode.LIVE
        self._state = PlaybackState()
        self._last_integrity: IntegrityResult | None = None

    @property
    def source_mode(self) -> DataSourceMode:
        """Zwraca globalny tryb źródła danych."""
        return self._source_mode

    @property
    def state(self) -> PlaybackState:
        """Zwraca aktualny stan playback."""
        return self._state

    def play(self, *, bag_path: str, allow_recovery: bool = False) -> bool:
        """Rozpocznij playback tylko dla integralnego pliku lub jawnego trybu recovery."""
        result = self._integrity_checker.check(bag_path)
        self._last_integrity = result
        if not self._integrity_checker.can_play(result, allow_recovery=allow_recovery):
            self._source_mode = DataSourceMode.LIVE
            self._state = PlaybackState(bag_path=None, is_playing=False)
            return False

        self._source_mode = DataSourceMode.PLAYBACK
        self._state.bag_path = bag_path
        self._state.is_playing = True
        self._state.is_paused = False
        return True

    def pause(self) -> None:
        """Wstrzymaj aktywny playback."""
        if self._state.is_playing:
            self._state.is_paused = True

    def stop(self) -> None:
        """Zatrzymaj playback i wróć do trybu LIVE."""
        self._state = PlaybackState()
        self._source_mode = DataSourceMode.LIVE

    def restart(self) -> bool:
        """Zrestartuj playback od początku aktualnego baga."""
        if not self._state.bag_path:
            return False
        bag_path = self._state.bag_path
        self.stop()
        return self.play(bag_path=bag_path)

    def seek(self, position_seconds: float) -> bool:
        """Ustaw pozycję osi czasu, odrzucając wartości ujemne."""
        if position_seconds < 0:
            return False
        self._state.position_seconds = position_seconds
        return True

    def set_speed(self, speed: float) -> bool:
        """Ustaw prędkość odtwarzania dla dodatnich wartości."""
        if speed <= 0:
            return False
        self._state.speed = speed
        return True

    def set_loop(self, enabled: bool) -> None:
        """Włącz/wyłącz zapętlenie playback."""
        self._state.loop = enabled

    def set_topic_filter(self, topics: list[str] | tuple[str, ...]) -> None:
        """Ustaw filtr topiców dla playback."""
        self._state.topic_filter = tuple(topics)

    def critical_commands_blocked(self) -> bool:
        """Blokuj komendy krytyczne, gdy źródło danych to PLAYBACK."""
        return self._source_mode is DataSourceMode.PLAYBACK
