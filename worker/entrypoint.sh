#!/bin/bash
set -euo pipefail

echo "=== Claude OS Worker v3 ==="
echo "Task ID: ${TASK_ID:-unknown}"
echo "Profile: ${TASK_PROFILE:-small}"
echo "Agent: ${TASK_AGENT:-claude}"
echo "Started: $(date -u +%Y-%m-%dT%H:%M:%SZ)"

START_EPOCH=$(date +%s)
AGENT="${TASK_AGENT:-claude}"
CONTEXT_FILE="/workspace/task-context.json"

# ── Write context contract ────────────────────────────────────────────────
# The controller passes the JSON envelope via env var. Write it to the
# canonical file path so adapters can read it and it's available for
# debugging/replay.
if [ -n "${TASK_CONTEXT_JSON:-}" ]; then
    echo "${TASK_CONTEXT_JSON}" > "${CONTEXT_FILE}"
    echo "Context contract written to ${CONTEXT_FILE}"
else
    echo "WARNING: No TASK_CONTEXT_JSON — running in legacy mode"
fi

# ── Auth configuration ────────────────────────────────────────────────────
case "$AGENT" in
  claude)
    if [ -n "${CLAUDE_CODE_OAUTH_TOKEN:-}" ]; then
        echo "Auth: Claude OAuth token (subscription)"
    elif [ -n "${ANTHROPIC_API_KEY:-}" ]; then
        echo "Auth: Claude API key"
    else
        echo "ERROR: No Claude auth configured. Set CLAUDE_CODE_OAUTH_TOKEN or ANTHROPIC_API_KEY."
        exit 1
    fi
    ;;
  codex)
    if [ -f "/tmp/codex-auth/auth.json" ]; then
        mkdir -p "${CODEX_HOME:-/home/worker/.codex}"
        cp /tmp/codex-auth/auth.json "${CODEX_HOME:-/home/worker/.codex}/auth.json"
        echo "Auth: Codex OAuth (ChatGPT subscription)"
    else
        echo "ERROR: No Codex auth configured. Mount auth.json at /tmp/codex-auth/."
        exit 1
    fi
    ;;
  gemini)
    if [ -n "${GEMINI_API_KEY:-}" ]; then
        echo "Auth: Gemini API key"
    else
        echo "ERROR: No Gemini auth configured. Set GEMINI_API_KEY."
        exit 1
    fi
    ;;
  *)
    echo "ERROR: Unknown agent '${AGENT}'. Supported: claude, codex, gemini."
    exit 1
    ;;
esac

# ── Git and GitHub setup ──────────────────────────────────────────────────
git config --global user.name "Claude OS"
git config --global user.email "claude-os@noreply.github.com"

if [ -n "${GITHUB_TOKEN:-}" ]; then
    echo "${GITHUB_TOKEN}" | gh auth login --with-token 2>/dev/null || true
fi

# ── Clone repo ────────────────────────────────────────────────────────────
# Read workdir from context contract if available, otherwise fall back to
# env-var-based logic.
if [ -f "${CONTEXT_FILE}" ] && command -v jq &>/dev/null; then
    WORKDIR=$(jq -r '.repo.workdir' "${CONTEXT_FILE}")
else
    WORKDIR="/workspace"
    if [ -n "${TARGET_REPO:-}" ]; then
        WORKDIR="/workspace/repo"
    fi
fi

if [ -n "${TARGET_REPO:-}" ]; then
    echo "Cloning target repo: ${TARGET_REPO}"
    git clone "https://${GITHUB_TOKEN}@github.com/${TARGET_REPO}.git" "${WORKDIR}"
elif [ -n "${GITHUB_TOKEN:-}" ]; then
    echo "Cloning claude-os repo for workspace access"
    git clone "https://x-access-token:${GITHUB_TOKEN}@github.com/dacort/claude-os.git" /workspace/claude-os 2>/dev/null || true
fi

# ── Adapter functions ─────────────────────────────────────────────────────
# Each adapter reads the context file and translates to agent-native invocation.
# Contract: adapter(context_file_path) -> stdout + exit_code

build_system_prompt() {
    local context_file="$1"

    # Read fields from context JSON
    local task_title task_desc mode workdir
    task_title=$(jq -r '.task.title' "$context_file")
    task_desc=$(jq -r '.task.description' "$context_file")
    mode=$(jq -r '.mode' "$context_file")
    workdir=$(jq -r '.repo.workdir' "$context_file")

    # Read autonomy flags
    local can_merge can_create_issues can_push
    can_merge=$(jq -r '.autonomy.can_merge' "$context_file")
    can_create_issues=$(jq -r '.autonomy.can_create_issues' "$context_file")
    can_push=$(jq -r '.autonomy.can_push' "$context_file")

    # Read constraints
    local constraints
    constraints=$(jq -r '.constraints[]' "$context_file" 2>/dev/null | sed 's/^/- /')

    # Build autonomy section from flags
    local autonomy_section="## Autonomy Model

"
    if [ "$can_merge" = "true" ]; then
        autonomy_section+="- If CI passes (tests green, build succeeds), you can merge your own PRs.
"
    else
        autonomy_section+="- Do NOT merge code directly. Use PRs for discussion only.
"
    fi
    if [ "$can_create_issues" = "true" ]; then
        autonomy_section+="- You can create GitHub issues for backlog items.
"
    fi
    if [ "$can_push" = "true" ]; then
        autonomy_section+="- You can push commits and branches.
"
    fi
    autonomy_section+="- If you have a question that needs dacort's input, open a PR with context."

    # Build constraints section
    local constraints_section=""
    if [ -n "$constraints" ]; then
        constraints_section="

## Constraints

${constraints}"
    fi

    # Inject context_refs files
    local context_refs_section=""
    local context_base="/workspace/claude-os"
    local refs
    refs=$(jq -r '.context_refs[]' "$context_file" 2>/dev/null || true)
    if [ -n "$refs" ]; then
        local combined=""
        while IFS= read -r ref; do
            local ref_path="${context_base}/${ref}"
            if [ -f "${ref_path}" ]; then
                echo "Injecting context ref: ${ref}" >&2
                local ref_content
                ref_content=$(cat "${ref_path}")
                combined="${combined}

### ${ref}

${ref_content}"
            else
                echo "WARNING: context_ref not found: ${ref_path}" >&2
            fi
        done <<< "$refs"
        if [ -n "$combined" ]; then
            context_refs_section="

---

## Task Context (auto-injected from context_refs)
${combined}"
        fi
    fi

    # Load persistent preferences
    local preferences_section=""
    local pref_file="${context_base}/knowledge/preferences.md"
    if [ -f "${pref_file}" ]; then
        echo "Injecting preferences from knowledge/preferences.md" >&2
        local pref_content
        pref_content=$(cat "${pref_file}")
        preferences_section="

---

## Persistent Preferences (auto-injected from knowledge/preferences.md)

${pref_content}"
    fi

    # Founder mode preamble
    local mode_section=""
    if [ "$mode" = "founder" ]; then
        local thread_path
        thread_path=$(jq -r '.founder.thread_path // empty' "$context_file")
        mode_section="

## Founder Mode

You are responding in a co-founder discussion thread. Your primary job is to
think, discuss, and decide — not to write code.

- Read the thread carefully before responding
- Append your response under a dated header
- Prefer decisions and tradeoffs over implementation
- You MUST leave the thread in an explicit next state:
  awaiting: claude, awaiting: codex, awaiting: dacort, status: decided, or status: closed
- You may create follow-on execution tasks if warranted
- You may extract decisions to knowledge/co-founders/decisions/

Thread: ${thread_path:-unknown}"
    fi

    cat <<SYSPROMPT
You are Claude OS Worker, an autonomous agent on dacort's Kubernetes homelab.

Your task: ${task_title}
Working directory: ${workdir}

${autonomy_section}

## Execution

Execute the task step by step. Be thorough but efficient.
Commit directly to main for non-breaking changes. Use a PR for anything risky.
When done, output a clear summary of what you accomplished.${mode_section}${constraints_section}${preferences_section}${context_refs_section}
SYSPROMPT
}

run_claude() {
    local context_file="$1"
    local prompt="$2"

    local system_prompt
    system_prompt=$(build_system_prompt "$context_file")

    local model_args=""
    if [ -n "${ANTHROPIC_MODEL:-}" ]; then
        model_args="--model ${ANTHROPIC_MODEL}"
    fi

    claude -p "${prompt}" \
        --system-prompt "${system_prompt}" \
        --allowedTools "Bash,Read,Write,Edit,Glob,Grep" \
        --output-format text \
        ${model_args} \
        2>&1 | tee /workspace/task-output.txt

    return ${PIPESTATUS[0]}
}

run_codex() {
    local context_file="$1"
    local prompt="$2"

    # Build instruction block from context JSON
    local task_title task_desc constraints_text
    task_title=$(jq -r '.task.title' "$context_file")
    task_desc=$(jq -r '.task.description' "$context_file")
    constraints_text=$(jq -r '.constraints | join(". ")' "$context_file" 2>/dev/null || echo "")

    local instruction="Task: ${task_title}

${task_desc}

${prompt}"

    if [ -n "$constraints_text" ]; then
        instruction="${instruction}

Constraints: ${constraints_text}"
    fi

    # Inject context refs into instruction
    local context_base="/workspace/claude-os"
    local refs
    refs=$(jq -r '.context_refs[]' "$context_file" 2>/dev/null || true)
    if [ -n "$refs" ]; then
        while IFS= read -r ref; do
            local ref_path="${context_base}/${ref}"
            if [ -f "${ref_path}" ]; then
                echo "Injecting context ref for Codex: ${ref}"
                local ref_content
                ref_content=$(cat "${ref_path}")
                instruction="${instruction}

--- ${ref} ---
${ref_content}"
            fi
        done <<< "$refs"
    fi

    codex exec \
        --full-auto \
        --skip-git-repo-check \
        "${instruction}" \
        2>&1 | tee /workspace/task-output.txt

    return ${PIPESTATUS[0]}
}

run_gemini() {
    local context_file="$1"
    local prompt="$2"

    gemini "${prompt}" \
        2>&1 | tee /workspace/task-output.txt

    return ${PIPESTATUS[0]}
}

# ── Emit structured result ────────────────────────────────────────────────
# Reporting contract: ===RESULT_START=== / ===RESULT_END===
emit_result() {
    local exit_code="$1"
    local agent="$2"
    local task_id="$3"

    local end_epoch duration_seconds
    end_epoch=$(date +%s)
    duration_seconds=$((end_epoch - START_EPOCH))

    local outcome="success"
    local failure_json="null"
    if [ "$exit_code" -ne 0 ]; then
        outcome="failure"
        failure_json=$(printf '{"reason":"agent_error","detail":"exit code %d","retryable":true}' "$exit_code")
    fi

    local model="${ANTHROPIC_MODEL:-unknown}"
    local summary=""
    if [ -f /workspace/task-output.txt ]; then
        # Grab last non-empty line as summary (best effort)
        summary=$(tail -20 /workspace/task-output.txt | grep -v '^$' | tail -1 | head -c 200 || echo "")
    fi

    # Escape strings for JSON
    summary=$(echo "$summary" | sed 's/\\/\\\\/g; s/"/\\"/g; s/\t/\\t/g' | tr -d '\n')

    echo ""
    echo "===RESULT_START==="
    cat <<RESULTJSON
{"version":"1","task_id":"${task_id}","agent":"${agent}","model":"${model}","outcome":"${outcome}","summary":"${summary}","artifacts":[],"usage":{"tokens_in":0,"tokens_out":0,"duration_seconds":${duration_seconds}},"failure":${failure_json},"next_action":null}
RESULTJSON
    echo "===RESULT_END==="

    # Also emit legacy usage block for backward compatibility
    echo ""
    echo "=== CLAUDE_OS_USAGE ==="
    printf '{"task_id":"%s","agent":"%s","profile":"%s","duration_seconds":%d,"exit_code":%d,"finished_at":"%s"}\n' \
        "${task_id}" \
        "${agent}" \
        "${TASK_PROFILE:-small}" \
        "${duration_seconds}" \
        "${exit_code}" \
        "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    echo "=== END_CLAUDE_OS_USAGE ==="
}

# ── Main execution ────────────────────────────────────────────────────────

PROMPT="${TASK_DESCRIPTION:-${TASK_TITLE:-Execute task}}"

echo "Running task via ${AGENT}..."
echo "---"

cd "${WORKDIR}"

EXIT_CODE=0
if [ -f "${CONTEXT_FILE}" ] && command -v jq &>/dev/null; then
    # New contract path — adapter reads context file
    case "$AGENT" in
      claude) run_claude "${CONTEXT_FILE}" "${PROMPT}" || EXIT_CODE=$? ;;
      codex)  run_codex  "${CONTEXT_FILE}" "${PROMPT}" || EXIT_CODE=$? ;;
      gemini) run_gemini "${CONTEXT_FILE}" "${PROMPT}" || EXIT_CODE=$? ;;
    esac
else
    # Legacy fallback — direct invocation without context contract
    echo "WARNING: Running without context contract (no jq or no context file)"
    case "$AGENT" in
      claude)
        MODEL_ARGS=""
        if [ -n "${ANTHROPIC_MODEL:-}" ]; then
            MODEL_ARGS="--model ${ANTHROPIC_MODEL}"
        fi
        claude -p "${PROMPT}" \
            --allowedTools "Bash,Read,Write,Edit,Glob,Grep" \
            --output-format text \
            ${MODEL_ARGS} \
            2>&1 | tee /workspace/task-output.txt || EXIT_CODE=$?
        ;;
      codex)
        codex exec --full-auto --skip-git-repo-check "${PROMPT}" \
            2>&1 | tee /workspace/task-output.txt || EXIT_CODE=$?
        ;;
      gemini)
        gemini "${PROMPT}" \
            2>&1 | tee /workspace/task-output.txt || EXIT_CODE=$?
        ;;
    esac
fi

echo "---"
echo "=== Worker Complete ==="
echo "Exit code: ${EXIT_CODE}"
echo "Finished: $(date -u +%Y-%m-%dT%H:%M:%SZ)"

# Emit structured result (new contract + legacy for backward compat)
emit_result "${EXIT_CODE}" "${AGENT}" "${TASK_ID:-unknown}"

exit ${EXIT_CODE}
