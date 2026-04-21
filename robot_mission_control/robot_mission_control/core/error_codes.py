"""Centralny katalog stabilnych kodów błędów modułu Mission Control."""

from __future__ import annotations

from enum import Enum


# [AI-CHANGE | 2026-04-21 09:30 UTC | v0.166]
# CO ZMIENIONO: Dodano dedykowany katalog kodów błędów wykorzystywany przez walidację konfiguracji,
#               szynę zdarzeń i granicę obsługi wyjątków.
# DLACZEGO: Jednoznaczne, stabilne kody błędów upraszczają diagnostykę oraz pozwalają bezpiecznie
#           degradować działanie UI bez zwracania potencjalnie mylących komunikatów.
# JAK TO DZIAŁA: Enum `ErrorCode` dostarcza jawne identyfikatory, a `DEFAULT_ERROR_MESSAGES`
#                mapuje je na czytelne komunikaty operatora.
# TODO: Powiązać kody z dokumentem operacyjnym runbook (SOP) oraz telemetrią alarmów.
class ErrorCode(str, Enum):
    """Stabilne kody błędów dla modułu sterowania misją."""

    CONFIG_MISSING_KEY = "MC_CFG_001"
    CONFIG_INVALID_TYPE = "MC_CFG_002"
    CONFIG_INVALID_VALUE = "MC_CFG_003"
    CONFIG_PARSE_ERROR = "MC_CFG_004"
    EVENT_MISSING_CORRELATION_ID = "MC_EVT_001"
    EVENT_INVALID_PAYLOAD = "MC_EVT_002"
    UI_GUARDED_OPERATION_FAILED = "MC_UI_001"
    UNKNOWN_RUNTIME_ERROR = "MC_GEN_001"


DEFAULT_ERROR_MESSAGES: dict[ErrorCode, str] = {
    ErrorCode.CONFIG_MISSING_KEY: "Brak wymaganego pola w konfiguracji.",
    ErrorCode.CONFIG_INVALID_TYPE: "Pole konfiguracji ma nieprawidłowy typ.",
    ErrorCode.CONFIG_INVALID_VALUE: "Pole konfiguracji ma nieprawidłową wartość.",
    ErrorCode.CONFIG_PARSE_ERROR: "Nie udało się sparsować pliku konfiguracyjnego.",
    ErrorCode.EVENT_MISSING_CORRELATION_ID: "Zdarzenie operatorskie wymaga correlation_id.",
    ErrorCode.EVENT_INVALID_PAYLOAD: "Zdarzenie operatorskie ma nieprawidłowy payload.",
    ErrorCode.UI_GUARDED_OPERATION_FAILED: "Operacja UI zakończona błędem; włączono degradację.",
    ErrorCode.UNKNOWN_RUNTIME_ERROR: "Nieobsłużony błąd wykonania.",
}
