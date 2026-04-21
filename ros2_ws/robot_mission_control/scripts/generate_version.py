#!/usr/bin/env python3
from __future__ import annotations

import subprocess
from datetime import datetime, timezone
from pathlib import Path


# [AI-CHANGE | 2026-04-21 05:27 UTC | v0.164]
# CO ZMIENIONO: Generator zapisuje dodatkowe pole `ARTIFACT_SOURCE` i nadal pobiera wersję z
#               `git rev-list --count HEAD`.
# DLACZEGO: Bez jawnego źródła pochodzenia runtime nie powinien ufać numerowi wersji z pliku,
#           aby uniknąć wyświetlania fałszywych wartości.
# JAK TO DZIAŁA: Skrypt zapisuje `COMMIT_COUNT`, `SHORT_SHA`, `BUILD_TIME_UTC` oraz
#                `ARTIFACT_SOURCE="git_rev_list_count"`, co pozwala na ścisłą walidację fallbacku.
# TODO: Dodać CLI `--output` oraz `--strict` dla walidacji środowisk CI/CD i buildów reproducible.


def _git(args: list[str], repo_root: Path) -> str:
    return subprocess.check_output(["git", *args], cwd=repo_root, text=True).strip()


def main() -> int:
    repo_root = Path(__file__).resolve().parents[2]
    target = repo_root / "robot_mission_control" / "robot_mission_control" / "version.py"

    commit_count = int(_git(["rev-list", "--count", "HEAD"], repo_root=repo_root))
    short_sha = _git(["rev-parse", "--short", "HEAD"], repo_root=repo_root)
    build_time_utc = datetime.now(timezone.utc).replace(microsecond=0).isoformat()

    content = f'''"""Generated build version artifact for robot mission control."""

# [AI-CHANGE | 2026-04-21 05:27 UTC | v0.164]
# CO ZMIENIONO: Plik artefaktu wersji zawiera teraz metadane commit_count/SHA/czas oraz pole źródła.
# DLACZEGO: Runtime ma akceptować fallback tylko wtedy, gdy artefakt jednoznacznie deklaruje,
#           że numer pochodzi z `git rev-list --count HEAD`.
# JAK TO DZIAŁA: Resolver odrzuca artefakt bez `ARTIFACT_SOURCE`, dzięki czemu brak `.git` nie
#                skutkuje pokazaniem przypadkowego numeru wersji.
# TODO: Dodać sumę kontrolną sekcji metadanych i jej automatyczną weryfikację przy starcie.
COMMIT_COUNT = {commit_count}
SHORT_SHA = "{short_sha}"
BUILD_TIME_UTC = "{build_time_utc}"
ARTIFACT_SOURCE = "git_rev_list_count"
'''
    target.write_text(content, encoding="utf-8")
    print(f"written {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
