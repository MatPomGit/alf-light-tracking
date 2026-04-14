#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(git -C "$SCRIPT_DIR" rev-parse --show-toplevel 2>/dev/null || true)"
if [ -z "$REPO_ROOT" ]; then
  REPO_ROOT="$SCRIPT_DIR"
fi

# Candidate locations for version_bump.py relative to git root or script dir.
CANDIDATES=(
  "$REPO_ROOT/ros2_ws/src/g1_light_tracking/scripts/version_bump.py"
  "$REPO_ROOT/ros2_ws/src/g1_light_tracking/scripts/version_bump.py"
  "$SCRIPT_DIR/ros2_ws/src/g1_light_tracking/scripts/version_bump.py"
)

VERSION_BUMP=""
PKG_ROOT=""
for c in "${CANDIDATES[@]}"; do
  if [ -f "$c" ]; then
    VERSION_BUMP="$c"
    PKG_ROOT="$(cd "$(dirname "$c")/.." && pwd)"
    break
  fi
done

if [ -z "$VERSION_BUMP" ]; then
  echo "[git-hooks] Nie znaleziono scripts/version_bump.py." >&2
  echo "[git-hooks] Sprawdzone ścieżki:" >&2
  for c in "${CANDIDATES[@]}"; do
    echo "  - $c" >&2
  done
  exit 1
fi

HOOKS_DIR="$REPO_ROOT/.git/hooks"
HOOK_FILE="$HOOKS_DIR/pre-commit"
mkdir -p "$HOOKS_DIR"

cat > "$HOOK_FILE" <<EOF
#!/usr/bin/env bash
set -e
python3 "$VERSION_BUMP"
git add "$PKG_ROOT/VERSION" \
        "$PKG_ROOT/setup.py" \
        "$PKG_ROOT/package.xml"
EOF

chmod +x "$HOOK_FILE"
echo "[git-hooks] Zainstalowano hook pre-commit: $HOOK_FILE"
echo "[git-hooks] Używany version_bump.py: $VERSION_BUMP"
