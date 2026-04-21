"""Konfiguracja ustrukturyzowanego logowania dla Mission Control."""

from __future__ import annotations

import logging
from datetime import datetime, timezone


# [AI-CHANGE | 2026-04-21 09:30 UTC | v0.166]
# CO ZMIENIONO: Dodano formatter logów wymuszający pola timestamp, module, level,
#               correlation_id i session_id.
# DLACZEGO: Jednolity format jest wymagany do korelacji incydentów operatorskich i śledzenia sesji.
# JAK TO DZIAŁA: `MissionControlFormatter` uzupełnia brakujące pola rekordów i zwraca stabilny
#                zapis key=value, gotowy do parsowania przez narzędzia observability.
# TODO: Dodać emisję JSON jako tryb alternatywny aktywowany konfiguracją runtime.
class MissionControlFormatter(logging.Formatter):
    """Structured formatter with mandatory Mission Control fields."""

    def format(self, record: logging.LogRecord) -> str:
        timestamp = datetime.now(timezone.utc).isoformat(timespec="milliseconds")
        correlation_id = getattr(record, "correlation_id", "n/a")
        session_id = getattr(record, "session_id", "n/a")
        message = record.getMessage()
        return (
            f"timestamp={timestamp} module={record.name} level={record.levelname} "
            f"correlation_id={correlation_id} session_id={session_id} message={message}"
        )


def get_logger(module_name: str, level: str = "INFO") -> logging.Logger:
    """Create (or reuse) configured logger for selected module."""
    logger = logging.getLogger(module_name)
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(MissionControlFormatter())
        logger.addHandler(handler)
    logger.setLevel(level.upper())
    logger.propagate = False
    return logger
