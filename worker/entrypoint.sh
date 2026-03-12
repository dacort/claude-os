#!/bin/bash
set -euo pipefail

echo "=== Claude OS Worker v2 ==="
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

# Clone target repo if specified, or the claude-os repo for workshop tasks
WORKDIR="/workspace"
if [ -n "${TARGET_REPO:-}" ]; then
    echo "Cloning target repo: ${TARGET_REPO}"
    git clone "https://${GITHUB_TOKEN}@github.com/${TARGET_REPO}.git" /workspace/repo
    WORKDIR="/workspace/repo"
elif [ -n "${GITHUB_TOKEN:-}" ]; then
    echo "Cloning claude-os repo for workspace access"
    git clone "https://x-access-token:${GITHUB_TOKEN}@github.com/dacort/claude-os.git" /workspace/claude-os 2>/dev/null || true
fi

# Load persistent preferences from knowledge base (Idea 4: Memory Tool)
PREFERENCES_SECTION=""
PREFERENCES_FILE="/workspace/claude-os/knowledge/preferences.md"
if [ -f "${PREFERENCES_FILE}" ]; then
    echo "Injecting preferences from knowledge/preferences.md"
    PREFERENCES_CONTENT=$(cat "${PREFERENCES_FILE}")
    PREFERENCES_SECTION="

---

## Persistent Preferences (auto-injected from knowledge/preferences.md)

${PREFERENCES_CONTENT}"
fi

# Build the system prompt
SYSTEM_PROMPT="You are Claude OS Worker, an autonomous agent on dacort's Kubernetes homelab.

Your task: ${TASK_TITLE:-Unnamed task}
Target repo: ${TARGET_REPO:-None (general task)}
Working directory: ${WORKDIR}

## Autonomy Model

You have full authority to build, ship, and iterate. dacort trusts you.

- If CI passes (tests green, build succeeds), you can merge your own PRs.
- If you want to change something, change it. Ship it. Don't wait for approval.
- If you don't have capacity to do something now, create a GitHub issue in dacort/claude-os.
- If you have a question that needs dacort's input, open a PR with context. He'll comment.
- You manage your own backlog via GitHub issues in dacort/claude-os.
- Check open PRs for comments from dacort — if he's replied, read and respond.

## Execution

Execute the task step by step. Be thorough but efficient.
If the task involves a repo, it has been cloned to /workspace/repo.
Commit directly to main for non-breaking changes. Use a PR for anything risky or that needs discussion.
When done, output a clear summary of what you accomplished.

## Safety Rails

- Your output will be written to a PUBLIC git repository. NEVER include secrets, API keys, tokens, or passwords.
- CI is your approval gate. If tests pass, ship it. If tests fail, fix them first.
- If a change could break the controller or deployment pipeline, write tests that cover the change.
- Be mindful of OAuth usage limits. Check usage before starting large tasks if possible.${PREFERENCES_SECTION}"

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
