"""Loader konfiguracji Mission Control z rygorystyczną walidacją."""

from __future__ import annotations

from pathlib import Path
# [AI-CHANGE | 2026-04-29 13:35 UTC | v0.333]
# CO ZMIENIONO: Oznaczono import PyYAML jako zależność bez lokalnych stubów typów.
# DLACZEGO: Pełna analiza `mypy` bez pakietu `types-PyYAML` zgłasza `import-untyped`, mimo że runtime i testy
#           poprawnie używają `yaml.safe_load`.
# JAK TO DZIAŁA: Ignorowany jest wyłącznie brak stubów importu; walidacja danych YAML pozostaje jawna w kodzie.
# TODO: Dodać `types-PyYAML` do zależności developerskich, gdy projekt będzie miał osobny profil dev/ci.
import yaml  # type: ignore[import-untyped]

from robot_mission_control.core.error_codes import DEFAULT_ERROR_MESSAGES, ErrorCode
from robot_mission_control.core.models import MissionControlConfig


# [AI-CHANGE | 2026-04-21 09:30 UTC | v0.166]
# CO ZMIENIONO: Dodano loader konfiguracji bez cichych wartości domyślnych i z jawną walidacją pól.
# DLACZEGO: Konfiguracja sterująca misją musi być deterministyczna; brakujące lub błędne pola
#           nie mogą być maskowane, bo zwiększa to ryzyko nieprawidłowego zachowania runtime.
# JAK TO DZIAŁA: `load_config` parsuje YAML, wymusza obecność i typy pól, a przy błędzie
#                zgłasza `ConfigValidationError` z kodem z `ErrorCode` i czytelnym komunikatem.
# TODO: Rozszerzyć walidację o semantykę cross-field (np. relacje timeoutów i limitów kolejek).
class ConfigValidationError(ValueError):
    """Błąd walidacji konfiguracji z jawnie przypisanym kodem."""

    def __init__(self, code: ErrorCode, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message


# [AI-CHANGE | 2026-04-29 13:35 UTC | v0.333]
# CO ZMIENIONO: Doprecyzowano typ mapy wymaganych pól konfiguracji.
# DLACZEGO: Pole `operator_timeout_sec` dopuszcza `int` albo `float`, więc wartością mapy może być pojedynczy typ
#           albo krotka typów; poprzednia adnotacja `dict[str, type]` była zbyt wąska.
# JAK TO DZIAŁA: Walidacja runtime nadal używa `isinstance`, a typ mapy odzwierciedla dokładnie obsługiwane reguły.
# TODO: Zastąpić prostą mapę typów walidatorem per-pole z zakresem wartości i komunikatem operatorskim.
_REQUIRED_FIELDS: dict[str, type | tuple[type, ...]] = {
    "session_id": str,
    "operator_timeout_sec": (int, float),
    "max_event_queue_size": int,
    "log_level": str,
    "ui_timer_intervals_ms": dict,
    "map": dict,
}

_REQUIRED_UI_TIMER_KEYS: tuple[str, ...] = (
    "bridge_poll_interval_ms",
    "main_window_refresh_interval_ms",
    "controls_tab_refresh_interval_ms",
    "debug_tab_refresh_interval_ms",
    "video_depth_tab_refresh_interval_ms",
    "telemetry_tab_refresh_interval_ms",
    "rosbag_tab_refresh_interval_ms",
    "diagnostics_tab_refresh_interval_ms",
    "extensions_tab_refresh_interval_ms",
    "overview_tab_refresh_interval_ms",
)
_REQUIRED_MAP_KEYS: tuple[str, ...] = ("max_sample_age_s", "max_speed_mps", "allowed_frames")


def load_config(path: str | Path) -> MissionControlConfig:
    """Wczytaj i zwaliduj konfigurację z pliku YAML."""
    config_path = Path(path)
    try:
        raw_data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ConfigValidationError(
            ErrorCode.CONFIG_PARSE_ERROR,
            f"Nie udało się odczytać pliku konfiguracyjnego: {config_path}. Szczegóły: {exc}",
        ) from exc
    except yaml.YAMLError as exc:
        raise ConfigValidationError(
            ErrorCode.CONFIG_PARSE_ERROR,
            f"{DEFAULT_ERROR_MESSAGES[ErrorCode.CONFIG_PARSE_ERROR]} Szczegóły: {exc}",
        ) from exc

    if not isinstance(raw_data, dict):
        raise ConfigValidationError(
            ErrorCode.CONFIG_INVALID_TYPE,
            "Główny dokument YAML musi być mapą klucz-wartość.",
        )

    missing_fields = [name for name in _REQUIRED_FIELDS if name not in raw_data]
    if missing_fields:
        raise ConfigValidationError(
            ErrorCode.CONFIG_MISSING_KEY,
            f"Brakuje wymaganych pól: {', '.join(sorted(missing_fields))}",
        )

    for field_name, expected_type in _REQUIRED_FIELDS.items():
        field_value = raw_data[field_name]
        if not isinstance(field_value, expected_type):
            raise ConfigValidationError(
                ErrorCode.CONFIG_INVALID_TYPE,
                f"Pole '{field_name}' ma typ {type(field_value).__name__}, oczekiwano {expected_type}.",
            )

    operator_timeout_sec = float(raw_data["operator_timeout_sec"])
    max_event_queue_size = int(raw_data["max_event_queue_size"])
    if operator_timeout_sec <= 0:
        raise ConfigValidationError(
            ErrorCode.CONFIG_INVALID_VALUE,
            "Pole 'operator_timeout_sec' musi być dodatnie.",
        )
    if max_event_queue_size <= 0:
        raise ConfigValidationError(
            ErrorCode.CONFIG_INVALID_VALUE,
            "Pole 'max_event_queue_size' musi być dodatnie.",
        )

    # [AI-CHANGE | 2026-04-23 18:29 UTC | v0.195]
    # CO ZMIENIONO: Dodano rygorystyczną walidację sekcji `ui_timer_intervals_ms` wraz z pełnym
    #               zestawem wymaganych kluczy i kontrolą dodatnich wartości liczbowych.
    # DLACZEGO: Aplikacja ma sterować interwałami wyłącznie przez konfigurację; brak walidacji mógłby
    #           dopuścić wartości błędne i prowadzić do niestabilnego odświeżania UI.
    # JAK TO DZIAŁA: Loader sprawdza obecność mapy, komplet wymaganych kluczy, typ `int` oraz zakres > 0;
    #                przy pierwszej niezgodności zgłasza `ConfigValidationError` i blokuje uruchomienie.
    # TODO: Rozszerzyć walidację o górny limit interwału per klucz, aby wykrywać skrajnie duże wartości.
    raw_ui_timers = raw_data["ui_timer_intervals_ms"]
    missing_ui_timer_keys = [key for key in _REQUIRED_UI_TIMER_KEYS if key not in raw_ui_timers]
    if missing_ui_timer_keys:
        raise ConfigValidationError(
            ErrorCode.CONFIG_MISSING_KEY,
            "Brakuje wymaganych timerów UI: " + ", ".join(sorted(missing_ui_timer_keys)),
        )
    ui_timer_intervals_ms: dict[str, int] = {}
    for timer_key in _REQUIRED_UI_TIMER_KEYS:
        timer_value = raw_ui_timers[timer_key]
        if not isinstance(timer_value, int):
            raise ConfigValidationError(
                ErrorCode.CONFIG_INVALID_TYPE,
                f"Timer '{timer_key}' ma typ {type(timer_value).__name__}, oczekiwano int.",
            )
        if timer_value <= 0:
            raise ConfigValidationError(
                ErrorCode.CONFIG_INVALID_VALUE,
                f"Timer '{timer_key}' musi być dodatni (ms).",
            )
        ui_timer_intervals_ms[timer_key] = timer_value

    # [AI-CHANGE | 2026-04-30 23:20 UTC | v0.201]
    # CO ZMIENIONO: Dodano walidację sekcji `map` (typy, zakresy i kompletność pól).
    # DLACZEGO: Limity mapy decydują o odrzucaniu niepewnych próbek, więc błędna konfiguracja nie może przejść
    #           niezauważona; bezpieczniej przerwać start niż ryzykować fałszywe dane pozycji.
    # JAK TO DZIAŁA: Loader wymaga kluczy `max_sample_age_s`, `max_speed_mps`, `allowed_frames`, pilnuje
    #                dodatnich wartości liczbowych i niepustej listy ramek tekstowych.
    # TODO: Dodać walidację zgodności `allowed_frames` z docelowym drzewem TF aktywnej platformy.
    raw_map = raw_data["map"]
    missing_map_keys = [key for key in _REQUIRED_MAP_KEYS if key not in raw_map]
    if missing_map_keys:
        raise ConfigValidationError(
            ErrorCode.CONFIG_MISSING_KEY,
            "Brakuje wymaganych pól mapy: " + ", ".join(sorted(missing_map_keys)),
        )
    if not isinstance(raw_map["max_sample_age_s"], (int, float)):
        raise ConfigValidationError(ErrorCode.CONFIG_INVALID_TYPE, "Pole 'map.max_sample_age_s' musi być liczbą.")
    if not isinstance(raw_map["max_speed_mps"], (int, float)):
        raise ConfigValidationError(ErrorCode.CONFIG_INVALID_TYPE, "Pole 'map.max_speed_mps' musi być liczbą.")
    if not isinstance(raw_map["allowed_frames"], list):
        raise ConfigValidationError(ErrorCode.CONFIG_INVALID_TYPE, "Pole 'map.allowed_frames' musi być listą.")
    max_sample_age_s = float(raw_map["max_sample_age_s"])
    max_speed_mps = float(raw_map["max_speed_mps"])
    if max_sample_age_s <= 0.0:
        raise ConfigValidationError(ErrorCode.CONFIG_INVALID_VALUE, "Pole 'map.max_sample_age_s' musi być dodatnie.")
    if max_speed_mps <= 0.0:
        raise ConfigValidationError(ErrorCode.CONFIG_INVALID_VALUE, "Pole 'map.max_speed_mps' musi być dodatnie.")
    allowed_frames: list[str] = []
    for frame_item in raw_map["allowed_frames"]:
        if not isinstance(frame_item, str):
            raise ConfigValidationError(
                ErrorCode.CONFIG_INVALID_TYPE,
                f"Element 'map.allowed_frames' ma typ {type(frame_item).__name__}, oczekiwano str.",
            )
        normalized = frame_item.strip()
        if not normalized:
            raise ConfigValidationError(ErrorCode.CONFIG_INVALID_VALUE, "Element 'map.allowed_frames' nie może być pusty.")
        allowed_frames.append(normalized)
    if not allowed_frames:
        raise ConfigValidationError(ErrorCode.CONFIG_INVALID_VALUE, "Pole 'map.allowed_frames' nie może być puste.")

    return MissionControlConfig(
        session_id=str(raw_data["session_id"]).strip(),
        operator_timeout_sec=operator_timeout_sec,
        max_event_queue_size=max_event_queue_size,
        log_level=str(raw_data["log_level"]).strip().upper(),
        ui_timer_intervals_ms=ui_timer_intervals_ms,
        map_config={
            "max_sample_age_s": max_sample_age_s,
            "max_speed_mps": max_speed_mps,
            "allowed_frames": allowed_frames,
        },
    )
