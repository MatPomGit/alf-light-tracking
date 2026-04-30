"""Wspólne modele danych dla warstwy core modułu Mission Control."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any


# [AI-CHANGE | 2026-04-21 09:30 UTC | v0.166]
# CO ZMIENIONO: Dodano modele konfiguracji, zdarzeń operatorskich i reprezentacji błędów.
# DLACZEGO: Ujednolicone modele redukują ryzyko rozbieżności kontraktów między modułami core.
# JAK TO DZIAŁA: Dataclasses wymuszają jawne pola i typy, a enum `EventCategory`
#                określa semantykę zdarzeń publikowanych na szynie.
# TODO: Dodać wersjonowanie schematu modeli (np. schema_version) dla migracji kompatybilności.
class EventCategory(str, Enum):
    """Kategorie zdarzeń dla routingu na szynie eventów."""

    OPERATOR = "operator"
    SYSTEM = "system"


@dataclass(frozen=True, slots=True)
class MissionControlConfig:
    """Zweryfikowany model konfiguracji aplikacji."""

    # [AI-CHANGE | 2026-04-23 18:29 UTC | v0.195]
    # CO ZMIENIONO: Rozszerzono model konfiguracji o mapę `ui_timer_intervals_ms`.
    # DLACZEGO: Interwały timerów UI nie mogą być hardcodowane; muszą być sterowane z walidowanej konfiguracji.
    # JAK TO DZIAŁA: Loader wypełnia słownik nazwanych interwałów (ms), a warstwa UI pobiera wartości po kluczu.
    # TODO: Dodać typowaną klasę (`dataclass`) dla interwałów, aby wyeliminować literówki kluczy.
    session_id: str
    operator_timeout_sec: float
    max_event_queue_size: int
    log_level: str
    ui_timer_intervals_ms: dict[str, int]
    # [AI-CHANGE | 2026-04-30 23:20 UTC | v0.201]
    # CO ZMIENIONO: Dodano pole `map_config` z parametrami bezpieczeństwa walidacji mapy.
    # DLACZEGO: Konfiguracja limitów mapy ma być przekazywana przez model core, a nie przez hardcoded stałe UI.
    # JAK TO DZIAŁA: Loader zwraca słownik z kluczami `max_sample_age_s`, `max_speed_mps` i `allowed_frames`,
    #                który następnie jest konsumowany przez `MainWindow` i `MapTab`.
    # TODO: Zastąpić słownik `map_config` osobną dataclassą z pełną walidacją statyczną typów.
    map_config: dict[str, float | list[str]]


@dataclass(frozen=True, slots=True)
class MissionEvent:
    """Kontrakt pojedynczego zdarzenia publikowanego na szynie."""

    name: str
    category: EventCategory
    correlation_id: str | None
    session_id: str
    payload: dict[str, Any]
    emitted_at: datetime


@dataclass(frozen=True, slots=True)
class ErrorDescriptor:
    """Opis błędu przekazywany do UI i logów."""

    code: str
    message: str
    details: str | None = None


@dataclass(frozen=True, slots=True)
class MapSnapshotContract:
    """Kontrakt pełnego rekordu mapy przekazywanego między store i UI."""

    # [AI-CHANGE | 2026-04-30 16:20 UTC | v0.201]
    # CO ZMIENIONO: Dodano model kontraktu mapy z osobnymi polami danych, jakości i reason_code.
    # DLACZEGO: Kontrakt musi być jednoznaczny, aby UI mogło odrzucać niekompletne próbki zamiast
    #           renderować potencjalnie błędną lokalizację robota.
    # JAK TO DZIAŁA: Model wymaga osobnych wartości: position/frame_id/timestamp/trajectory/tf_status
    #                oraz metadanych data_quality/reason_code odczytywanych ze store.
    # TODO: Dodać walidację zakresów pozycji i dopuszczalnych statusów TF na poziomie modelu.
    position: tuple[float, float] | None
    frame_id: str | None
    timestamp: datetime | None
    trajectory: tuple[tuple[float, float], ...] | None
    tf_status: str | None
    data_quality: str
    reason_code: str | None


@dataclass(frozen=True, slots=True)
class MapPoseState:
    """Kontrakt pojedynczego stanu mapy przekazywanego ROS -> store -> UI."""

    # [AI-CHANGE | 2026-04-30 12:35 UTC | v0.200]
    # CO ZMIENIONO: Dodano nowy model domenowy `MapPoseState` z polami:
    #               timestamp, frame_id, position, trajectory, source, quality, reason_code.
    # DLACZEGO: Potrzebny jest pojedynczy i jawny kontrakt danych mapy, żeby uniknąć lokalnych
    #           transformacji rozsianych po UI i zredukować ryzyko renderu błędnej pozycji.
    # JAK TO DZIAŁA: Model przenosi komplet danych + metadane jakości. Warstwa ROS mapuje
    #                surowe payloady do tej dataclass, store przechowuje obiekt, a UI wykonuje
    #                jedynie lekki render i lokalne safety checks.
    # TODO: Dodać walidator zakresów pozycji/trajectory (np. limity mapy) bezpośrednio w modelu.
    timestamp: datetime | None
    frame_id: str | None
    position: tuple[float, float] | None
    trajectory: tuple[tuple[float, float], ...] | None
    source: str
    quality: str
    reason_code: str | None
