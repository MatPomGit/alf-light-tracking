#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PKG_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
REPO_ROOT="$(git -C "$PKG_ROOT" rev-parse --show-toplevel 2>/dev/null || true)"
if [ -z "$REPO_ROOT" ]; then
  REPO_ROOT="$PKG_ROOT"
fi

VERSION_BUMP="$PKG_ROOT/scripts/version_bump.py"
if [ ! -f "$VERSION_BUMP" ]; then
  echo "[git-hooks] Missing file: $VERSION_BUMP" >&2
  exit 1
fi

HOOKS_DIR="$REPO_ROOT/.git/hooks"
HOOK_FILE="$HOOKS_DIR/pre-commit"
mkdir -p "$HOOKS_DIR"

cat > "$HOOK_FILE" <<EOF
#!/usr/bin/env bash
set -euo pipefail
python3 "$VERSION_BUMP"
git add "$PKG_ROOT/VERSION" \
        "$PKG_ROOT/setup.py" \
        "$PKG_ROOT/package.xml"
EOF

chmod +x "$HOOK_FILE"
echo "[git-hooks] Installed pre-commit hook: $HOOK_FILE"
