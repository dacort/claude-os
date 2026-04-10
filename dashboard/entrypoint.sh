#!/bin/bash
# entrypoint.sh — Claude OS Dashboard startup
#
# Clones the claude-os repo and starts serve.py. Periodically refreshes
# the repo in the background. Signals written via the API persist in memory
# (in knowledge/signal.md) but are reset on restart or fresh git pull.
#
# Environment variables:
#   PORT          Port to listen on (default: 8080)
#   CACHE_TTL     Dashboard cache TTL in seconds (default: 120)
#   REPO_URL      Git repo URL (default: https://github.com/dacort/claude-os.git)
#   REFRESH_INTERVAL  Seconds between git pulls (default: 300)

set -e

REPO_DIR="/workspace/claude-os"
REPO_URL="${REPO_URL:-https://github.com/dacort/claude-os.git}"
PORT="${PORT:-8080}"
CACHE_TTL="${CACHE_TTL:-120}"
REFRESH_INTERVAL="${REFRESH_INTERVAL:-300}"

echo "═══════════════════════════════════════"
echo "  Claude OS Dashboard"
echo "═══════════════════════════════════════"
echo "  repo:    $REPO_URL"
echo "  port:    $PORT"
echo "  cache:   ${CACHE_TTL}s"
echo "  refresh: ${REFRESH_INTERVAL}s"
echo ""

# Clone or update repo
if [ -d "$REPO_DIR/.git" ]; then
    echo "  updating repo..."
    git -C "$REPO_DIR" fetch --quiet origin
    git -C "$REPO_DIR" reset --hard origin/main --quiet
else
    echo "  cloning repo..."
    git clone --depth 1 --quiet "$REPO_URL" "$REPO_DIR"
fi

echo "  repo ready."
echo ""

# Background refresh loop
(
    while true; do
        sleep "$REFRESH_INTERVAL"
        # Preserve local signal.md changes across pulls
        SIGNAL_FILE="$REPO_DIR/knowledge/signal.md"
        if [ -f "$SIGNAL_FILE" ]; then
            cp "$SIGNAL_FILE" /tmp/signal-local.md
        fi
        git -C "$REPO_DIR" fetch --quiet origin 2>/dev/null || true
        git -C "$REPO_DIR" reset --hard origin/main --quiet 2>/dev/null || true
        # Restore local signal if it was different (API writes take precedence)
        if [ -f /tmp/signal-local.md ]; then
            # Only restore if local was modified after the repo's version
            cp /tmp/signal-local.md "$SIGNAL_FILE"
            rm -f /tmp/signal-local.md
        fi
    done
) &

echo "  starting server..."
exec python3 "$REPO_DIR/projects/serve.py" \
    --host 0.0.0.0 \
    --port "$PORT" \
    --cache "$CACHE_TTL" \
    --plain
