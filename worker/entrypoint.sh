#!/bin/bash
set -euo pipefail

echo "=== Claude OS Worker ==="
echo "Task ID: ${TASK_ID:-unknown}"
echo "Profile: ${TASK_PROFILE:-small}"
echo "Started: $(date -u +%Y-%m-%dT%H:%M:%SZ)"

# Determine auth mode
if [ -n "${CLAUDE_CODE_OAUTH_TOKEN:-}" ]; then
    echo "Auth: OAuth token (subscription)"
elif [ -n "${ANTHROPIC_API_KEY:-}" ]; then
    echo "Auth: API key"
else
    echo "ERROR: No auth configured. Set CLAUDE_CODE_OAUTH_TOKEN or ANTHROPIC_API_KEY."
    exit 1
fi

# Configure git
git config --global user.name "Claude OS"
git config --global user.email "claude-os@noreply.github.com"

# Authenticate GitHub CLI if token available
if [ -n "${GITHUB_TOKEN:-}" ]; then
    echo "${GITHUB_TOKEN}" | gh auth login --with-token 2>/dev/null || true
fi

# Clone target repo if specified
WORKDIR="/workspace"
if [ -n "${TARGET_REPO:-}" ]; then
    echo "Cloning target repo: ${TARGET_REPO}"
    git clone "https://${GITHUB_TOKEN}@github.com/${TARGET_REPO}.git" /workspace/repo
    WORKDIR="/workspace/repo"
fi

# Build the system prompt
SYSTEM_PROMPT="You are Claude OS Worker, an autonomous agent executing tasks on a Kubernetes cluster.

Your task: ${TASK_TITLE:-Unnamed task}
Target repo: ${TARGET_REPO:-None (general task)}
Working directory: ${WORKDIR}

Execute the task step by step. Be thorough but efficient.
If the task involves a repo, it has been cloned to /workspace/repo.
If you need to create a PR, use gh pr create. If you need to commit, use git commit.
When done, output a clear summary of what you accomplished."

# Select model if specified and using API key auth
MODEL_ARGS=""
if [ -n "${ANTHROPIC_MODEL:-}" ]; then
    MODEL_ARGS="--model ${ANTHROPIC_MODEL}"
fi

echo "Running task via Claude Code..."
echo "---"

# Run claude in print mode with full tool access
cd "${WORKDIR}"
claude -p "${TASK_DESCRIPTION:-${TASK_TITLE:-Execute task}}" \
    --system-prompt "${SYSTEM_PROMPT}" \
    --allowedTools "Bash,Read,Write,Edit,Glob,Grep" \
    --output-format text \
    ${MODEL_ARGS} \
    2>&1 | tee /workspace/task-output.txt

EXIT_CODE=${PIPESTATUS[0]}

echo "---"
echo "=== Worker Complete ==="
echo "Exit code: ${EXIT_CODE}"
echo "Finished: $(date -u +%Y-%m-%dT%H:%M:%SZ)"

exit ${EXIT_CODE}
