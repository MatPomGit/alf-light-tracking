#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(git -C "$SCRIPT_DIR" rev-parse --show-toplevel 2>/dev/null || true)"
if [ -z "$REPO_ROOT" ]; then
  REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
fi

VERSION_BUMP="$SCRIPT_DIR/src/g1_light_tracking/scripts/version_bump.py"
PKG_ROOT="$SCRIPT_DIR/src/g1_light_tracking"

if [ ! -f "$VERSION_BUMP" ]; then
  echo "[git-hooks] Nie znaleziono: $VERSION_BUMP" >&2
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
