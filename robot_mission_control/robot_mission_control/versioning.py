"""Runtime resolver for application version metadata."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from robot_mission_control import version as build_version


# [AI-CHANGE | 2026-04-20 20:05 UTC | v0.151]
# CO ZMIENIONO: Dodano resolver wersji z priorytetem `.git` i fallbackiem do artefaktu build.
# DLACZEGO: W środowiskach runtime bez repozytorium git UI nadal musi pokazać wersję albo jawny brak.
# JAK TO DZIAŁA: `resolve_version_metadata` próbuje odczyt z git, potem z `version.py`, a na końcu zwraca
#                stan unavailable z etykietą „WERSJA NIEDOSTĘPNA”.
# TODO: Rozszerzyć resolver o odczyt metadanych z wheel/dist-info dla dystrybucji produkcyjnych.


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

    if not isinstance(commit_count, int) or commit_count <= 0:
        return None
    if not isinstance(short_sha, str) or not short_sha.strip():
        return None
    if not isinstance(build_time_utc, str) or not build_time_utc.strip():
        return None

    return VersionMetadata(
        commit_count=commit_count,
        short_sha=short_sha,
        build_time_utc=build_time_utc,
        source="build_artifact",
    )
