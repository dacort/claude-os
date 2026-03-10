#!/bin/bash
set -euo pipefail

echo "=== Claude OS Worker ==="
echo "Task ID: ${TASK_ID:-unknown}"
echo "Profile: ${TASK_PROFILE:-small}"
echo "Started: $(date -u +%Y-%m-%dT%H:%M:%SZ)"

# Configure git (writes to /home/worker which is an emptyDir volume)
git config --global user.name "Claude OS"
git config --global user.email "claude-os@noreply.github.com"

# Authenticate GitHub CLI if token available
if [ -n "${GITHUB_TOKEN:-}" ]; then
    echo "${GITHUB_TOKEN}" | gh auth login --with-token 2>/dev/null || true
fi

# Clone target repo if specified
if [ -n "${TARGET_REPO:-}" ]; then
    echo "Cloning target repo: ${TARGET_REPO}"
    git clone "https://${GITHUB_TOKEN}@github.com/${TARGET_REPO}.git" /workspace/repo
    cd /workspace/repo
fi

# Execute the task script if provided, otherwise run the agentic loop
if [ -n "${TASK_SCRIPT:-}" ]; then
    echo "Running task script..."
    bash -c "${TASK_SCRIPT}"
else
    echo "Running agentic task loop..."
    /opt/agent/venv/bin/python3 /opt/agent/run.py
fi

echo "=== Worker Complete ==="
echo "Finished: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
