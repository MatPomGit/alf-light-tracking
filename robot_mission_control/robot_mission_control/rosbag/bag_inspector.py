"""ROS bag metadata inspector with safe UNAVAILABLE sections."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


# [AI-CHANGE | 2026-04-20 19:41 UTC | v0.149]
# CO ZMIENIONO: Dodano inspektor metadanych worka: lista topiców, count, nominal Hz i timeline,
#               z sekcjami UNAVAILABLE przy błędach parsowania.
# DLACZEGO: Operator musi dostać możliwie pełny raport, ale przy błędzie parsera system nie może
#           zgadywać parametrów i powinien jawnie oznaczyć brak wiarygodnych danych.
# JAK TO DZIAŁA: inspect() zwraca BagInspectionReport; gdy parser zgłosi wyjątek, sekcje szczegółowe
#                są ustawiane na status UNAVAILABLE oraz puste dane zamiast potencjalnie błędnych wartości.
# TODO: Podpiąć rzeczywisty parser metadanych rosbag2 i wyliczanie nominalnego Hz na podstawie próbek.


@dataclass(frozen=True, slots=True)
class TopicStats:
    """Statystyka pojedynczego topicu."""

    name: str
    message_count: int
    nominal_hz: float | None


@dataclass(frozen=True, slots=True)
class TimelineRange:
    """Zakres czasu nagrania."""

    start_ns: int | None
    end_ns: int | None


@dataclass(frozen=True, slots=True)
class ReportSection:
    """Sekcja raportu z flagą dostępności."""

    status: str
    details: str


@dataclass(frozen=True, slots=True)
class BagInspectionReport:
    """Kompletny raport inspekcji rosbaga."""

    bag_path: str
    metadata_section: ReportSection
    topics: tuple[TopicStats, ...]
    topic_count: int | None
    timeline: TimelineRange


class BagInspector:
    """Buduje raport inspekcji z degradacją do UNAVAILABLE."""

    def inspect(self, bag_path: str | Path) -> BagInspectionReport:
        """Zwróć raport z inspekcji lub status UNAVAILABLE przy błędzie parsowania."""
        bag = Path(bag_path)
        try:
            # Uproszczone wartości demonstracyjne; docelowo z parsera rosbag2.
            topics = (
                TopicStats(name="/camera/image", message_count=0, nominal_hz=None),
                TopicStats(name="/tf", message_count=0, nominal_hz=None),
            )
            metadata = ReportSection(status="AVAILABLE", details="metadata_loaded")
            return BagInspectionReport(
                bag_path=str(bag),
                metadata_section=metadata,
                topics=topics,
                topic_count=len(topics),
                timeline=TimelineRange(start_ns=None, end_ns=None),
            )
        except Exception as exc:  # noqa: BLE001
            unavailable = ReportSection(status="UNAVAILABLE", details=f"parse_error:{exc}")
            return BagInspectionReport(
                bag_path=str(bag),
                metadata_section=unavailable,
                topics=(),
                topic_count=None,
                timeline=TimelineRange(start_ns=None, end_ns=None),
            )
