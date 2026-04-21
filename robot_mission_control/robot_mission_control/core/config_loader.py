"""Loader konfiguracji Mission Control z rygorystyczną walidacją."""

from __future__ import annotations

from pathlib import Path
import yaml

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


_REQUIRED_FIELDS: dict[str, type] = {
    "session_id": str,
    "operator_timeout_sec": (int, float),
    "max_event_queue_size": int,
    "log_level": str,
}


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

    return MissionControlConfig(
        session_id=str(raw_data["session_id"]).strip(),
        operator_timeout_sec=operator_timeout_sec,
        max_event_queue_size=max_event_queue_size,
        log_level=str(raw_data["log_level"]).strip().upper(),
    )
