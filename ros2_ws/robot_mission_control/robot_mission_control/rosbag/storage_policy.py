"""Storage retention policy for rosbag artifacts."""

from __future__ import annotations

from dataclasses import dataclass


# [AI-CHANGE | 2026-04-20 19:41 UTC | v0.149]
# CO ZMIENIONO: Dodano politykę storage do decyzji retencji/usuwania bagów na podstawie limitu miejsca.
# DLACZEGO: Kontrola przestrzeni dyskowej ogranicza ryzyko awarii nagrań i utraty stabilności aplikacji.
# JAK TO DZIAŁA: evaluate_capacity() zwraca ALLOW/THROTTLE/BLOCK; przy niepewnych danych pojemności
#                stosowany jest konserwatywny wynik BLOCK, zgodnie z zasadą bezpieczeństwa danych.
# TODO: Dodać strategię wielopoziomową (wiek, priorytet misji, flagi chronione) dla selektywnej retencji.


@dataclass(frozen=True, slots=True)
class StorageDecision:
    """Decyzja polityki retencji."""

    action: str
    reason: str


class StoragePolicy:
    """Podejmuje konserwatywne decyzje dot. użycia przestrzeni dla rosbagów."""

    def __init__(self, *, min_free_bytes: int) -> None:
        self._min_free_bytes = min_free_bytes

    def evaluate_capacity(self, free_bytes: int | None) -> StorageDecision:
        """Oceń stan pojemności i zwróć decyzję ALLOW/THROTTLE/BLOCK."""
        if free_bytes is None:
            return StorageDecision(action="BLOCK", reason="capacity_unknown")

        if free_bytes <= 0:
            return StorageDecision(action="BLOCK", reason="disk_full")

        if free_bytes < self._min_free_bytes:
            return StorageDecision(action="THROTTLE", reason="low_free_space")

        return StorageDecision(action="ALLOW", reason="capacity_ok")
