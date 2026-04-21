"""Runtime resolver for application version metadata."""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from robot_mission_control import version as build_version


# [AI-CHANGE | 2026-04-21 05:27 UTC | v0.164]
# CO ZMIENIONO: Uszczelniono walidację fallbacku build-time przez wymaganie znacznika pochodzenia
#               `ARTIFACT_SOURCE="git_rev_list_count"` oraz walidację formatu SHA.
# DLACZEGO: DoD wymaga braku fałszywych numerów wersji; bez znacznika pochodzenia i poprawnego SHA
#           nie ufamy metadanym i wolimy zwrócić `WERSJA NIEDOSTĘPNA`.
# JAK TO DZIAŁA: Resolver czyta najpierw `.git`, a gdy go brak, akceptuje tylko artefakt spełniający
#                wszystkie reguły integralności (commit_count>0, SHA hex 7-40, build_time i źródło).
# TODO: Dodać kryptograficzny podpis artefaktu i weryfikację kluczem publicznym podczas startu aplikacji.
_ARTIFACT_SOURCE_EXPECTED = "git_rev_list_count"
_SHA_PATTERN = re.compile(r"^[0-9a-f]{7,40}$")


@dataclass(frozen=True, slots=True)
class VersionMetadata:
    commit_count: int | None
    short_sha: str | None
    build_time_utc: str | None
    source: str

    @property
    def version_tag(self) -> str:
        if self.commit_count is None:
            return "WERSJA NIEDOSTĘPNA"
        return f"v0.{self.commit_count}"


def resolve_version_metadata() -> VersionMetadata:
    git_metadata = _read_git_metadata()
    if git_metadata is not None:
        return git_metadata

    artifact_metadata = _read_build_artifact_metadata()
    if artifact_metadata is not None:
        return artifact_metadata

    return VersionMetadata(
        commit_count=None,
        short_sha=None,
        build_time_utc=None,
        source="unavailable",
    )


def _read_git_metadata() -> VersionMetadata | None:
    repo_root = Path(__file__).resolve().parents[2]
    git_dir = repo_root / ".git"
    if not git_dir.exists():
        return None

    try:
        commit_count_text = subprocess.check_output(
            ["git", "rev-list", "--count", "HEAD"],
            cwd=repo_root,
            text=True,
        ).strip()
        short_sha = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=repo_root,
            text=True,
        ).strip()
        commit_count = int(commit_count_text)
    except Exception:  # noqa: BLE001
        return None

    return VersionMetadata(
        commit_count=commit_count,
        short_sha=short_sha,
        build_time_utc=datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        source="git",
    )


def _read_build_artifact_metadata() -> VersionMetadata | None:
    commit_count = getattr(build_version, "COMMIT_COUNT", None)
    short_sha = getattr(build_version, "SHORT_SHA", None)
    build_time_utc = getattr(build_version, "BUILD_TIME_UTC", None)
    artifact_source = getattr(build_version, "ARTIFACT_SOURCE", None)

    if artifact_source != _ARTIFACT_SOURCE_EXPECTED:
        return None
    if not isinstance(commit_count, int) or commit_count <= 0:
        return None
    if not isinstance(short_sha, str) or _SHA_PATTERN.fullmatch(short_sha.strip()) is None:
        return None
    if not isinstance(build_time_utc, str) or not build_time_utc.strip():
        return None

    return VersionMetadata(
        commit_count=commit_count,
        short_sha=short_sha,
        build_time_utc=build_time_utc,
        source="build_artifact",
    )
