#!/usr/bin/env python3
from __future__ import annotations

import subprocess
from datetime import datetime, timezone
from pathlib import Path


# [AI-CHANGE | 2026-04-20 20:05 UTC | v0.151]
# CO ZMIENIONO: Dodano generator artefaktu `robot_mission_control/version.py` z metadanymi builda.
# DLACZEGO: Aplikacja ma działać także bez `.git`, więc potrzebny jest trwały fallback wersji z czasu budowania.
# JAK TO DZIAŁA: Skrypt czyta commit_count i short_sha z git, zapisuje wraz z build_time_utc do modułu Python.
# TODO: Uruchamiać generator automatycznie w pipeline build/wheel zamiast ręcznie.


def _git(args: list[str], repo_root: Path) -> str:
    return subprocess.check_output(["git", *args], cwd=repo_root, text=True).strip()


def main() -> int:
    repo_root = Path(__file__).resolve().parents[2]
    target = repo_root / "robot_mission_control" / "robot_mission_control" / "version.py"

    commit_count = int(_git(["rev-list", "--count", "HEAD"], repo_root=repo_root))
    short_sha = _git(["rev-parse", "--short", "HEAD"], repo_root=repo_root)
    build_time_utc = datetime.now(timezone.utc).replace(microsecond=0).isoformat()

    content = f'''"""Generated build version artifact for robot mission control."""

# [AI-CHANGE | 2026-04-20 20:05 UTC | v0.151]
# CO ZMIENIONO: Plik generowany automatycznie podczas buildu zawierający metadane wersji.
# DLACZEGO: Runtime bez repozytorium git musi nadal wyświetlić zweryfikowaną wersję artefaktu.
# JAK TO DZIAŁA: Stałe poniżej są odczytywane przez `resolve_version_metadata()` jako źródło build_artifact.
# TODO: Dodać podpis artefaktu (checksum/sig), aby wykrywać ręczne modyfikacje pliku.
COMMIT_COUNT = {commit_count}
SHORT_SHA = "{short_sha}"
BUILD_TIME_UTC = "{build_time_utc}"
'''
    target.write_text(content, encoding="utf-8")
    print(f"written {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
