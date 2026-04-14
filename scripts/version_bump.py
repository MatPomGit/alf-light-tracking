\
#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
VERSION_FILE = ROOT / "VERSION"
SETUP_FILE = ROOT / "setup.py"
PACKAGE_XML = ROOT / "package.xml"

def read_version() -> str:
    if VERSION_FILE.exists():
        return VERSION_FILE.read_text(encoding="utf-8").strip()
    return "0.1.0"

def bump_patch(version: str) -> str:
    m = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)", version)
    if not m:
        raise ValueError(f"Niepoprawny format wersji: {version}")
    major, minor, patch = map(int, m.groups())
    return f"{major}.{minor}.{patch + 1}"

def replace_in_file(path: Path, pattern: str, repl: str) -> None:
    if not path.exists():
        return
    text = path.read_text(encoding="utf-8")
    new_text, count = re.subn(pattern, repl, text, count=1, flags=re.MULTILINE)
    if count:
        path.write_text(new_text, encoding="utf-8")

def main() -> int:
    old_version = read_version()
    new_version = bump_patch(old_version)
    VERSION_FILE.write_text(new_version + "\n", encoding="utf-8")

    replace_in_file(
        SETUP_FILE,
        r"version='(\d+\.\d+\.\d+)'",
        f"version='{new_version}'"
    )
    replace_in_file(
        PACKAGE_XML,
        r"<version>\d+\.\d+\.\d+</version>",
        f"<version>{new_version}</version>"
    )

    print(f"[version_bump] {old_version} -> {new_version}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
