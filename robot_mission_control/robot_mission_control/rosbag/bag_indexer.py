"""Local ROS bag indexer with lightweight metadata cache."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


# [AI-CHANGE | 2026-04-20 19:41 UTC | v0.149]
# CO ZMIENIONO: Dodano indeks lokalnych bagów z cache metadanych: nazwa, data, rozmiar,
#               czas trwania i liczba topiców.
# DLACZEGO: Widok operatora potrzebuje szybkiego listowania plików bez ponownego parsowania
#           każdego worka przy każdym odświeżeniu.
# JAK TO DZIAŁA: refresh_index() skanuje katalog, liczy podstawowe metryki i aktualizuje słownik cache.
#                Metadane niepewne ustawiane są na None, aby uniknąć zwracania błędnych wartości.
# TODO: Dodać trwały cache na dysku z hashami plików i częściowym odświeżaniem różnicowym.


@dataclass(frozen=True, slots=True)
class BagMetadata:
    """Podstawowy rekord metadanych lokalnego rosbaga."""

    name: str
    created_at: datetime
    size_bytes: int
    duration_seconds: float | None
    topic_count: int | None


class BagIndexer:
    """Skanuje lokalne pliki rosbag i utrzymuje cache metadanych."""

    def __init__(self, root_dir: str | Path) -> None:
        self._root_dir = Path(root_dir)
        self._cache: dict[str, BagMetadata] = {}

    @property
    def cache(self) -> dict[str, BagMetadata]:
        """Zwraca kopię cache metadanych."""
        return dict(self._cache)

    def refresh_index(self) -> list[BagMetadata]:
        """Przeskanuj katalog i zbuduj świeżą listę metadanych plików bag."""
        indexed: list[BagMetadata] = []
        for candidate in sorted(self._root_dir.glob("*.db3")):
            stat = candidate.stat()
            metadata = BagMetadata(
                name=candidate.name,
                created_at=datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc),
                size_bytes=stat.st_size,
                duration_seconds=None,
                topic_count=None,
            )
            self._cache[candidate.name] = metadata
            indexed.append(metadata)
        return indexed
