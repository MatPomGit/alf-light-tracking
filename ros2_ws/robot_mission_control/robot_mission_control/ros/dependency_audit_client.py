from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Callable

# [AI-CHANGE | 2026-04-29 13:35 UTC | v0.333]
# CO ZMIENIONO: Oznaczono import PyYAML jako import bez stubów typów.
# DLACZEGO: Klient audytu zależności parsuje YAML w runtime, ale środowisko statyczne nie ma `types-PyYAML`,
#           co generowało błąd niezwiązany z logiką bezpieczeństwa audytu.
# JAK TO DZIAŁA: `mypy` pomija tylko brak metadanych typów importu, a parser nadal zwraca UNKNOWN przy danych niepewnych.
# TODO: Dodać walidację schematu katalogu zależności przed wykonaniem zapytań audytu.
import yaml  # type: ignore[import-untyped]


# [AI-CHANGE | 2026-04-20 20:05 UTC | v0.151]
# CO ZMIENIONO: Rozszerzono moduł o kontrakt i klienta `system/dependency_status` z mapowaniem
#               statusów OK/MISSING/WRONG_VERSION/UNKNOWN oraz metadanych timestamp/source.
# DLACZEGO: UI i warstwa ROS potrzebują jednego, bezpiecznego źródła prawdy o stanie zależności,
#           z zachowaniem zasady: lepiej pokazać UNKNOWN niż błędnie potwierdzić poprawność.
# JAK TO DZIAŁA: DependencyStatusContract parsuje odpowiedź usługi, a DependencyStatusClient ładuje listę
#                bibliotek z YAML i zwraca raport z fallbackiem UNKNOWN, gdy dane są niepewne.
# TODO: Dodać walidację semver (`packaging.version`) i flagi kompatybilności ABI dla bibliotek natywnych.


@dataclass(frozen=True, slots=True)
class AuditRecord:
    """Pojedynczy rekord audytu dla operacji ROS."""

    timestamp: datetime
    component: str
    operation: str
    status: str
    correlation_id: str
    session_id: str
    details: dict[str, Any]


class DependencyAuditClient:
    """Prosty klient audytu dla krytycznych operacji mostu ROS."""

    def __init__(self, logger: logging.Logger | None = None) -> None:
        self._logger = logger or logging.getLogger("robot_mission_control.ros.audit")
        self._records: list[AuditRecord] = []

    def emit(
        self,
        *,
        component: str,
        operation: str,
        status: str,
        correlation_id: str,
        session_id: str,
        details: dict[str, Any] | None = None,
    ) -> AuditRecord:
        """Zapisuje rekord audytowy i loguje jego skrót."""
        payload = details or {}
        record = AuditRecord(
            timestamp=datetime.now(timezone.utc),
            component=component,
            operation=operation,
            status=status,
            correlation_id=correlation_id,
            session_id=session_id,
            details=payload,
        )
        self._records.append(record)
        self._logger.info(
            "audit component=%s operation=%s status=%s correlation_id=%s session_id=%s details=%s",
            component,
            operation,
            status,
            correlation_id,
            session_id,
            payload,
        )
        return record

    def snapshot(self) -> tuple[AuditRecord, ...]:
        """Zwraca niemodyfikowalny snapshot audytu."""
        return tuple(self._records)


class DependencyStatusCode(Enum):
    """Dozwolone statusy kontraktu dependency_status."""

    OK = "OK"
    MISSING = "MISSING"
    WRONG_VERSION = "WRONG_VERSION"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True, slots=True)
class DependencyRequirement:
    """Wymagana biblioteka po stronie robota."""

    name: str
    required_version: str | None = None


@dataclass(frozen=True, slots=True)
class DependencyStatusItem:
    """Stan pojedynczej zależności zwracany przez kontrakt."""

    name: str
    status: DependencyStatusCode
    required_version: str | None
    detected_version: str | None
    timestamp_utc: datetime
    source: str


@dataclass(frozen=True, slots=True)
class DependencyStatusReport:
    """Kompletny raport audytu zależności."""

    generated_at_utc: datetime
    source: str
    items: tuple[DependencyStatusItem, ...]


class DependencyStatusContract:
    """Parser odpowiedzi usługi `system/dependency_status`."""

    @staticmethod
    def parse_response(
        *,
        response: dict[str, Any] | None,
        requirements: tuple[DependencyRequirement, ...],
        fallback_source: str,
    ) -> DependencyStatusReport:
        now = datetime.now(timezone.utc)
        payload = response or {}
        raw_items = payload.get("dependencies")
        if not isinstance(raw_items, list):
            raw_items = []

        items_by_name: dict[str, dict[str, Any]] = {}
        for row in raw_items:
            if isinstance(row, dict) and isinstance(row.get("name"), str):
                items_by_name[row["name"]] = row

        parsed: list[DependencyStatusItem] = []
        for req in requirements:
            row = items_by_name.get(req.name, {})
            status_value = str(row.get("status", DependencyStatusCode.UNKNOWN.value)).upper()
            try:
                status = DependencyStatusCode(status_value)
            except ValueError:
                status = DependencyStatusCode.UNKNOWN

            timestamp_value = row.get("timestamp_utc")
            timestamp_utc = DependencyStatusContract._safe_parse_timestamp(timestamp_value, now)
            source = str(row.get("source") or fallback_source)

            parsed.append(
                DependencyStatusItem(
                    name=req.name,
                    status=status,
                    required_version=req.required_version,
                    detected_version=DependencyStatusContract._to_str_or_none(row.get("detected_version")),
                    timestamp_utc=timestamp_utc,
                    source=source,
                )
            )

        report_source = str(payload.get("source") or fallback_source)
        report_time = DependencyStatusContract._safe_parse_timestamp(payload.get("generated_at_utc"), now)
        return DependencyStatusReport(generated_at_utc=report_time, source=report_source, items=tuple(parsed))

    @staticmethod
    def _safe_parse_timestamp(value: Any, fallback: datetime) -> datetime:
        if not isinstance(value, str):
            return fallback
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return fallback
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)

    @staticmethod
    def _to_str_or_none(value: Any) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None


class DependencyStatusClient:
    """Klient kontraktu `system/dependency_status` z fallbackiem na bezpieczne UNKNOWN."""

    def __init__(
        self,
        *,
        request_fn: Callable[[dict[str, Any]], dict[str, Any] | None],
        dependencies_config_path: Path,
        logger: logging.Logger | None = None,
    ) -> None:
        self._request_fn = request_fn
        self._dependencies_config_path = dependencies_config_path
        self._logger = logger or logging.getLogger("robot_mission_control.ros.dependency_status")

    def load_requirements(self) -> tuple[DependencyRequirement, ...]:
        """Wczytuje listę zależności z YAML po stronie robota (bez hardcodu UI)."""
        if not self._dependencies_config_path.exists():
            self._logger.warning("dependencies config missing path=%s", self._dependencies_config_path)
            return tuple()

        data = yaml.safe_load(self._dependencies_config_path.read_text(encoding="utf-8")) or {}
        rows = data.get("dependencies", [])
        if not isinstance(rows, list):
            return tuple()

        requirements: list[DependencyRequirement] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            name = row.get("name")
            if not isinstance(name, str) or not name.strip():
                continue
            requirements.append(
                DependencyRequirement(
                    name=name.strip(),
                    required_version=DependencyStatusContract._to_str_or_none(row.get("required_version")),
                )
            )
        return tuple(requirements)

    def fetch_report(self) -> DependencyStatusReport:
        """Pobiera raport i nigdy nie podaje niezweryfikowanego sukcesu."""
        requirements = self.load_requirements()
        if not requirements:
            return DependencyStatusReport(
                generated_at_utc=datetime.now(timezone.utc),
                source="config_missing",
                items=tuple(),
            )

        request_payload = {
            "dependencies": [
                {"name": req.name, "required_version": req.required_version}
                for req in requirements
            ]
        }
        try:
            response = self._request_fn(request_payload)
        except Exception as exc:  # noqa: BLE001
            self._logger.error("dependency_status request failed err=%s", exc)
            response = None

        return DependencyStatusContract.parse_response(
            response=response,
            requirements=requirements,
            fallback_source="system/dependency_status",
        )
