#!/usr/bin/env bash
set -e

REPO_ROOT="$(cd "$(dirname "$0")" && pwd)"
HOOKS_DIR="$REPO_ROOT/.git/hooks"
HOOK_FILE="$HOOKS_DIR/pre-commit"

mkdir -p "$HOOKS_DIR"

cat > "$HOOK_FILE" <<'EOF'
#!/usr/bin/env bash
set -e
REPO_ROOT="$(git rev-parse --show-toplevel)"
python3 "$REPO_ROOT/g1_light_tracking/ros2_ws/src/g1_light_tracking/scripts/version_bump.py"
git add "$REPO_ROOT/g1_light_tracking/ros2_ws/src/g1_light_tracking/VERSION"         "$REPO_ROOT/g1_light_tracking/ros2_ws/src/g1_light_tracking/setup.py"         "$REPO_ROOT/g1_light_tracking/ros2_ws/src/g1_light_tracking/package.xml"
EOF

chmod +x "$HOOK_FILE"
echo "[git-hooks] Zainstalowano hook pre-commit: $HOOK_FILE"
