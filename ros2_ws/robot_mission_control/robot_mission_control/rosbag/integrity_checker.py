"""Integrity checks for rosbag files and playback safety gates."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


# [AI-CHANGE | 2026-04-20 19:41 UTC | v0.149]
# CO ZMIENIONO: Dodano checker integralności oznaczający CORRUPTED i bramkę blokującą playback
#               uszkodzonych bagów, o ile nie ustawiono jawnego trybu recovery.
# DLACZEGO: Odtwarzanie uszkodzonego źródła może generować mylące dane i błędne decyzje operatora.
# JAK TO DZIAŁA: check() klasyfikuje plik na OK/CORRUPTED; can_play() zwraca False dla CORRUPTED,
#                chyba że allow_recovery=True (świadoma decyzja operatora).
# TODO: Rozszerzyć walidację o checksum segmentów i zgodność indeksów sqlite z metadanymi rosbag2.


@dataclass(frozen=True, slots=True)
class IntegrityResult:
    """Wynik sprawdzenia integralności."""

    bag_path: str
    status: str
    reason: str


class IntegrityChecker:
    """Wykonuje sprawdzenie integralności i kontrolę dopuszczenia do playback."""

    def check(self, bag_path: str | Path) -> IntegrityResult:
        """Oznacz bag jako OK lub CORRUPTED na podstawie prostych warunków integralności."""
        path = Path(bag_path)
        if not path.exists() or path.stat().st_size <= 0:
            return IntegrityResult(bag_path=str(path), status="CORRUPTED", reason="missing_or_empty")
        return IntegrityResult(bag_path=str(path), status="OK", reason="basic_checks_passed")

    def can_play(self, result: IntegrityResult, *, allow_recovery: bool = False) -> bool:
        """Zwróć True tylko dla bezpiecznego playback albo jawnego recovery."""
        if result.status == "CORRUPTED" and not allow_recovery:
            return False
        return True
