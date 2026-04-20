"""ROS bag recording controller with conservative safety states."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum


# [AI-CHANGE | 2026-04-20 19:41 UTC | v0.149]
# CO ZMIENIONO: Dodano kontroler nagrywania z trybami wyboru topiców, konfiguracją kompresji/split
#               oraz bezpiecznym statusem "NIEZWERYFIKOWANY STAN NAGRYWANIA" przy braku potwierdzenia zapisu.
# DLACZEGO: Operator musi mieć czytelny status nagrania, ale system ma preferować stan niepewny zamiast
#           ryzyka raportowania błędnego "nagrywa" bez twardego potwierdzenia.
# JAK TO DZIAŁA: Start tworzy sesję pending; dopiero confirm_write() ustawia RECORDING. Brak potwierdzenia
#                utrzymuje stan UNVERIFIED_RECORDING_STATE. Stop zawsze kończy sesję i czyści status.
# TODO: Dodać adapter do realnego `ros2 bag record` z walidacją sygnału flush/fsync z warstwy storage.


class TopicSelectionMode(Enum):
    """Tryby wyboru topiców do nagrywania."""

    ALL = "ALL"
    INCLUDE_LIST = "INCLUDE_LIST"
    EXCLUDE_LIST = "EXCLUDE_LIST"
    REGEX = "REGEX"


class RecordingStatus(Enum):
    """Stan logiczny kontrolera nagrywania."""

    STOPPED = "STOPPED"
    STARTING = "STARTING"
    RECORDING = "RECORDING"
    UNVERIFIED_RECORDING_STATE = "NIEZWERYFIKOWANY STAN NAGRYWANIA"


@dataclass(frozen=True, slots=True)
class RecordingConfig:
    """Konfiguracja sesji nagrywania rosbag."""

    topic_mode: TopicSelectionMode
    topics: tuple[str, ...] = ()
    regex: str | None = None
    use_compression: bool = False
    split_size_mb: int | None = None


@dataclass(slots=True)
class RecordingSession:
    """Bieżąca sesja nagrywania i potwierdzenie zapisu."""

    bag_name: str
    config: RecordingConfig
    started_at: datetime
    write_confirmed: bool = False


class RecordController:
    """Kontroler start/stop nagrywania z polityką bezpiecznych stanów."""

    def __init__(self) -> None:
        self._session: RecordingSession | None = None
        self._status = RecordingStatus.STOPPED

    @property
    def status(self) -> RecordingStatus:
        """Zwraca aktualny status nagrywania."""
        return self._status

    @property
    def active_session(self) -> RecordingSession | None:
        """Zwraca aktywną sesję lub None."""
        return self._session

    def start(self, *, bag_name: str, config: RecordingConfig) -> RecordingStatus:
        """Uruchamia sesję nagrywania i przechodzi w stan oczekiwania na potwierdzenie zapisu."""
        self._session = RecordingSession(
            bag_name=bag_name,
            config=config,
            started_at=datetime.now(timezone.utc),
            write_confirmed=False,
        )
        self._status = RecordingStatus.UNVERIFIED_RECORDING_STATE
        return self._status

    def confirm_write(self) -> RecordingStatus:
        """Potwierdza realny zapis i ustawia status RECORDING."""
        if self._session is None:
            self._status = RecordingStatus.STOPPED
            return self._status

        self._session.write_confirmed = True
        self._status = RecordingStatus.RECORDING
        return self._status

    def stop(self) -> RecordingStatus:
        """Kończy sesję nagrywania i czyści stan kontrolera."""
        self._session = None
        self._status = RecordingStatus.STOPPED
        return self._status
