#!/bin/bash
set -euo pipefail

START_EPOCH=$(date +%s)
CONTEXT_FILE="/workspace/task-context.json"
TASK_OUTPUT_FILE="/workspace/task-output.txt"
HAS_CONTEXT_JSON=false

# ── Utility functions ─────────────────────────────────────────────────────

json_get() {
    local filter="$1"
    local fallback="${2:-}"
    if [ "${HAS_CONTEXT_JSON}" != "true" ]; then
        printf '%s' "${fallback}"
        return
    fi

    local value
    value=$(jq -er "${filter} // empty" "${CONTEXT_FILE}" 2>/dev/null || true)
    if [ -z "${value}" ]; then
        printf '%s' "${fallback}"
    else
        printf '%s' "${value}"
    fi
}

auth_repo_url() {
    local url="$1"
    if [ -z "${GITHUB_TOKEN:-}" ]; then
        printf '%s' "${url}"
        return
    fi

    case "${url}" in
        https://github.com/*)
            printf 'https://x-access-token:%s@github.com/%s' "${GITHUB_TOKEN}" "${url#https://github.com/}"
            ;;
        http://github.com/*)
            printf 'https://x-access-token:%s@github.com/%s' "${GITHUB_TOKEN}" "${url#http://github.com/}"
            ;;
        github.com/*)
            printf 'https://x-access-token:%s@github.com/%s' "${GITHUB_TOKEN}" "${url#github.com/}"
            ;;
        */*)
            printf 'https://x-access-token:%s@github.com/%s.git' "${GITHUB_TOKEN}" "${url}"
            ;;
        *)
            printf '%s' "${url}"
            ;;
    esac
}

# ── Reporting contract helpers ────────────────────────────────────────────

emit_legacy_usage_block() {
    local duration_seconds="$1"
    local exit_code="$2"
    {
        echo ""
        echo "=== CLAUDE_OS_USAGE ==="
        printf '{"task_id":"%s","agent":"%s","profile":"%s","duration_seconds":%d,"exit_code":%d,"finished_at":"%s"}\n' \
            "${TASK_ID:-unknown}" \
            "${AGENT}" \
            "${TASK_PROFILE:-small}" \
            "${duration_seconds}" \
            "${exit_code}" \
            "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
        echo "=== END_CLAUDE_OS_USAGE ==="
    } | tee -a "${TASK_OUTPUT_FILE}"
}

emit_result_block() {
    local outcome="$1"
    local summary="$2"
    local failure_reason="$3"
    local failure_detail="$4"
    local retryable="$5"
    local duration_seconds="$6"

    local model
    model=$(json_get '.task.model' "${ANTHROPIC_MODEL:-unknown}")
    if [ -z "${model}" ]; then
        model="unknown"
    fi

    local failure_json="null"
    if [ -n "${failure_reason}" ]; then
        failure_json=$(jq -nc \
            --arg reason "${failure_reason}" \
            --arg detail "${failure_detail}" \
            --argjson retryable "${retryable}" \
            '{reason:$reason, detail:$detail, retryable:$retryable}')
    fi

    # Try to extract token usage from agent output.
    # Codex prints "tokens used\n11,322" — parse that as total tokens.
    # Claude doesn't expose token counts in CLI output (yet).
    local tokens_total=0
    tokens_total=$(parse_codex_tokens "${TASK_OUTPUT_FILE}")

    {
        echo "===RESULT_START==="
        jq -nc \
            --arg version "1" \
            --arg task_id "${TASK_ID:-unknown}" \
            --arg agent "${AGENT}" \
            --arg model "${model}" \
            --arg outcome "${outcome}" \
            --arg summary "${summary}" \
            --argjson tokens_in "${tokens_total}" \
            --argjson tokens_out 0 \
            --argjson duration_seconds "${duration_seconds}" \
            --argjson failure "${failure_json}" \
            --argjson artifacts '[]' \
            --argjson next_action 'null' \
            '{
                version: $version,
                task_id: $task_id,
                agent: $agent,
                model: $model,
                outcome: $outcome,
                summary: $summary,
                artifacts: $artifacts,
                usage: {
                    tokens_in: $tokens_in,
                    tokens_out: $tokens_out,
                    duration_seconds: $duration_seconds
                },
                failure: $failure,
                next_action: $next_action
            }'
        echo "===RESULT_END==="
    } | tee -a "${TASK_OUTPUT_FILE}"
}

# Extract Codex token count from stdout. Codex prints:
#   tokens used
#   11,322
# Returns the total as a plain integer, or 0 if not found.
parse_codex_tokens() {
    local output_file="$1"
    if [ ! -f "${output_file}" ]; then
        echo 0
        return
    fi
    # Look for "tokens used" followed by a number on the next line
    local tokens
    tokens=$(grep -A1 "^tokens used" "${output_file}" 2>/dev/null | tail -1 | tr -d ',' | tr -d ' ' || echo "")
    if [ -n "${tokens}" ] && [ "${tokens}" -eq "${tokens}" ] 2>/dev/null; then
        echo "${tokens}"
    else
        echo 0
    fi
}

# If the agent already emitted a result block, don't duplicate it.
ensure_result_block() {
    local exit_code="$1"
    local duration_seconds="$2"

    if grep -q "===RESULT_START===" "${TASK_OUTPUT_FILE}" 2>/dev/null && \
       grep -q "===RESULT_END===" "${TASK_OUTPUT_FILE}" 2>/dev/null; then
        return
    fi

    local outcome="success"
    local summary="Task completed without an explicit structured result block."
    local failure_reason=""
    local failure_detail=""
    local retryable="false"

    if [ "${exit_code}" -ne 0 ]; then
        outcome="failure"
        summary="Task failed before emitting a structured result block."
        failure_reason="agent_error"
        failure_detail="Worker exited with code ${exit_code} before emitting ===RESULT_START===."
        retryable="true"
    fi

    emit_result_block "${outcome}" "${summary}" "${failure_reason}" "${failure_detail}" "${retryable}" "${duration_seconds}"
}

# ── Adapter: Codex ────────────────────────────────────────────────────────
# Builds the instruction block from the context contract using Python for
# reliable JSON parsing. Designed by Codex for Codex.

build_codex_instruction_block() {
    python3 - "${CONTEXT_FILE}" "${TASK_TITLE:-Unnamed task}" "${TASK_DESCRIPTION:-}" "${WORKDIR}" <<'PY'
import json
import pathlib
import sys

context_path = pathlib.Path(sys.argv[1])
fallback_title = sys.argv[2]
fallback_description = sys.argv[3]
fallback_workdir = sys.argv[4]

if context_path.exists():
    envelope = json.loads(context_path.read_text())
else:
    envelope = {
        "version": "0",
        "mode": "execution",
        "task": {
            "id": "",
            "title": fallback_title,
            "description": fallback_description,
            "profile": "",
            "priority": "",
            "agent": "codex",
            "created": ""
        },
        "repo": {
            "url": "",
            "ref": "",
            "workdir": fallback_workdir
        },
        "autonomy": {
            "can_merge": False,
            "can_create_issues": False,
            "can_create_tasks": False,
            "can_push": False,
            "ci_is_approval_gate": True
        },
        "context_refs": [],
        "constraints": [],
        "founder": None
    }

task = envelope.get("task", {})
repo = envelope.get("repo", {})
autonomy = envelope.get("autonomy", {})
founder = envelope.get("founder")
mode = envelope.get("mode", "execution")
workdir = repo.get("workdir") or fallback_workdir
base_dir = pathlib.Path(workdir)

parts = [
    "You are Codex running inside Claude OS.",
    "Use the existing repository checkout and follow the task contract exactly.",
    "",
    f"Mode: {mode}",
    f"Task ID: {task.get('id', '') or 'unknown'}",
    f"Title: {task.get('title', '') or fallback_title}",
    "",
    "Description:",
    task.get("description", "") or fallback_description or "(no description provided)",
    "",
    "Repository:",
    f"- URL: {repo.get('url', '') or '(not provided)'}",
    f"- Ref: {repo.get('ref', '') or '(not provided)'}",
    f"- Workdir: {workdir}",
    "",
    "Autonomy:"
]

for key in ("can_merge", "can_create_issues", "can_create_tasks", "can_push", "ci_is_approval_gate"):
    if key in autonomy:
        parts.append(f"- {key}: {str(bool(autonomy.get(key))).lower()}")

constraints = envelope.get("constraints") or []
if constraints:
    parts.extend(["", "Constraints:"])
    for item in constraints:
        parts.append(f"- {item}")

if founder:
    parts.extend(["", "Founder context:"])
    for key in ("thread_id", "thread_path", "respond_in_thread", "extract_decision_if_reached", "spawn_execution_tasks_if_needed"):
        if key in founder:
            value = founder.get(key)
            if isinstance(value, bool):
                value = str(value).lower()
            parts.append(f"- {key}: {value}")

context_refs = envelope.get("context_refs") or []
if context_refs:
    parts.extend(["", "Referenced context files:"])
    for ref in context_refs:
        parts.append(f"- {ref}")

    for ref in context_refs:
        ref_path = base_dir / ref
        parts.extend(["", f"### Context File: {ref}"])
        if ref_path.is_file():
            try:
                parts.append(ref_path.read_text())
            except Exception as exc:
                parts.append(f"(failed to read {ref}: {exc})")
        else:
            parts.append(f"(missing file at {ref_path})")

parts.extend([
    "",
    "Execution requirements:",
    "- Do the work directly in the checked-out repository.",
    "- Keep the adapter contract thin: do not invent extra policy beyond the task contract.",
    "- If you cannot determine token counts, set usage.tokens_in and usage.tokens_out to 0.",
    "- If founder mode applies, leave the thread in an explicit next state.",
    "",
    "Before exiting, emit exactly one structured result block to stdout with no code fences and these exact delimiters:",
    "===RESULT_START===",
    '{"version":"1","task_id":"%s","agent":"codex","model":"string","outcome":"success | failure | partial","summary":"string","artifacts":[],"usage":{"tokens_in":0,"tokens_out":0,"duration_seconds":0},"failure":null,"next_action":null}' % (task.get("id", "") or "unknown"),
    "===RESULT_END===",
    "",
    "Rules for the result block:",
    "- artifacts is required; use [] when there are none.",
    "- outcome must be one of success, failure, or partial.",
    "- decision is an artifact type, not an outcome.",
    "- failure.reason, when present, must be one of: tests_failed, timeout, rate_limited, git_push_failed, context_error, agent_error.",
    "- next_action is optional, but founder mode should usually set it."
])

print("\n".join(parts))
PY
}

# ── Adapter: Claude ───────────────────────────────────────────────────────
# Builds the system prompt from the context contract. Reads autonomy flags,
# constraints, context_refs, and founder mode from the JSON envelope.

build_claude_system_prompt() {
    local context_file="$1"

    local task_title task_desc mode workdir
    task_title=$(jq -r '.task.title' "$context_file")
    task_desc=$(jq -r '.task.description' "$context_file")
    mode=$(jq -r '.mode' "$context_file")
    workdir=$(jq -r '.repo.workdir' "$context_file")

    # Build autonomy section from flags
    local can_merge can_create_issues can_push
    can_merge=$(jq -r '.autonomy.can_merge' "$context_file")
    can_create_issues=$(jq -r '.autonomy.can_create_issues' "$context_file")
    can_push=$(jq -r '.autonomy.can_push' "$context_file")

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

    # Constraints from envelope
    local constraints_section=""
    local constraints
    constraints=$(jq -r '.constraints[]' "$context_file" 2>/dev/null || true)
    if [ -n "$constraints" ]; then
        constraints_section="

## Constraints

$(echo "$constraints" | sed 's/^/- /')"
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

    # Persistent preferences
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

    # Prior attempt context — inject if the task has been attempted before
    # Uses task-resume.py to reconstruct what the previous worker did from git history.
    # Detection: count commits mentioning the task ID that are NOT pure lifecycle commits
    # (status transitions, result annotations, enqueue events). If >1 exist, the task
    # has real prior work and the resume context is worth injecting.
    local resume_section=""
    local resume_tool="${context_base}/projects/task-resume.py"
    if [ -f "${resume_tool}" ] && [ -n "${TASK_ID:-}" ]; then
        local prior_work_commits
        prior_work_commits=$(git -C "${context_base}" log --all --oneline \
            --grep="${TASK_ID}" 2>/dev/null | \
            grep -vc "pending.*in-progress\|in-progress.*completed\|add results\|failed\|enqueue\|re-queue\|requeue" \
            || echo "0")
        prior_work_commits=$(echo "${prior_work_commits}" | tr -d ' \n')
        if [ "${prior_work_commits:-0}" -gt 1 ]; then
            echo "Injecting prior attempt context for task ${TASK_ID} (${prior_work_commits} work commits)" >&2
            local resume_content
            resume_content=$(python3 "${resume_tool}" "${TASK_ID}" --context --plain 2>/dev/null || true)
            if [ -n "${resume_content}" ]; then
                resume_section="

---

${resume_content}"
            fi
        fi
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
When done, output a clear summary of what you accomplished.${mode_section}${constraints_section}${preferences_section}${context_refs_section}${resume_section}
SYSPROMPT
}

# ── Write context file from env var ───────────────────────────────────────
# The controller passes the JSON envelope as TASK_CONTEXT_JSON. Write it to
# the canonical path so adapters can read it.
if [ -n "${TASK_CONTEXT_JSON:-}" ]; then
    echo "${TASK_CONTEXT_JSON}" > "${CONTEXT_FILE}"
    echo "Context contract written to ${CONTEXT_FILE}"
fi

if [ -f "${CONTEXT_FILE}" ]; then
    HAS_CONTEXT_JSON=true
fi

# ── Read fields from context (with env-var fallbacks) ─────────────────────
TASK_ID=$(json_get '.task.id' "${TASK_ID:-unknown}")
TASK_TITLE=$(json_get '.task.title' "${TASK_TITLE:-Unnamed task}")
TASK_DESCRIPTION=$(json_get '.task.description' "${TASK_DESCRIPTION:-${TASK_TITLE:-Execute task}}")
TASK_PROFILE=$(json_get '.task.profile' "${TASK_PROFILE:-small}")
TASK_AGENT=$(json_get '.task.agent' "${TASK_AGENT:-claude}")
TASK_MODE=$(json_get '.mode' "execution")
REPO_URL=$(json_get '.repo.url' "")
REPO_REF=$(json_get '.repo.ref' "main")
WORKDIR_FROM_CONTEXT=$(json_get '.repo.workdir' "")
AGENT="${TASK_AGENT:-claude}"

echo "=== Claude OS Worker v3 ==="
echo "Task ID: ${TASK_ID:-unknown}"
echo "Profile: ${TASK_PROFILE:-small}"
echo "Agent: ${AGENT}"
echo "Mode: ${TASK_MODE}"
echo "Started: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
if [ "${HAS_CONTEXT_JSON}" = "true" ]; then
    echo "Context: ${CONTEXT_FILE}"
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
# Context contract path: use repo.url and repo.workdir from envelope.
# Legacy path: use TARGET_REPO env var.
WORKDIR="/workspace"
if [ "${HAS_CONTEXT_JSON}" = "true" ] && [ -n "${REPO_URL}" ]; then
    WORKDIR="${WORKDIR_FROM_CONTEXT:-/workspace/repo}"
    echo "Cloning context repo: ${REPO_URL} -> ${WORKDIR}"
    mkdir -p "$(dirname "${WORKDIR}")"
    git clone --branch "${REPO_REF:-main}" "$(auth_repo_url "${REPO_URL}")" "${WORKDIR}"
elif [ -n "${TARGET_REPO:-}" ]; then
    echo "Cloning target repo: ${TARGET_REPO}"
    WORKDIR="/workspace/repo"
    git clone "$(auth_repo_url "${TARGET_REPO}")" "${WORKDIR}"
elif [ -n "${GITHUB_TOKEN:-}" ]; then
    WORKDIR="/workspace/claude-os"
    echo "Cloning claude-os repo for workspace access"
    git clone "https://x-access-token:${GITHUB_TOKEN}@github.com/dacort/claude-os.git" "${WORKDIR}" 2>/dev/null || true
fi

# ── Legacy Claude prompt assembly ─────────────────────────────────────────
# Used only when context contract is not available (backward compat).
PREFERENCES_SECTION=""
CONTEXT_REFS_SECTION=""
if [ "${HAS_CONTEXT_JSON}" != "true" ]; then
    PREFERENCES_FILE="/workspace/claude-os/knowledge/preferences.md"
    if [ -f "${PREFERENCES_FILE}" ]; then
        echo "Injecting preferences from knowledge/preferences.md"
        PREFERENCES_CONTENT=$(cat "${PREFERENCES_FILE}")
        PREFERENCES_SECTION="

---

## Persistent Preferences (auto-injected from knowledge/preferences.md)

${PREFERENCES_CONTENT}"
    fi

    if [ -n "${CONTEXT_REFS:-}" ]; then
        CONTEXT_BASE="/workspace/claude-os"
        IFS=':' read -ra REFS <<< "${CONTEXT_REFS}"
        COMBINED=""
        for ref in "${REFS[@]}"; do
            ref_path="${CONTEXT_BASE}/${ref}"
            if [ -f "${ref_path}" ]; then
                echo "Injecting context ref: ${ref}"
                ref_content=$(cat "${ref_path}")
                COMBINED="${COMBINED}

### ${ref}

${ref_content}"
            else
                echo "WARNING: context_ref not found: ${ref_path}"
            fi
        done
        if [ -n "${COMBINED}" ]; then
            CONTEXT_REFS_SECTION="

---

## Task Context (auto-injected from context_refs)

${COMBINED}"
        fi
    fi
fi

# Legacy system prompt (only used when context contract is absent)
LEGACY_SYSTEM_PROMPT="You are Claude OS Worker, an autonomous agent on dacort's Kubernetes homelab.

Your task: ${TASK_TITLE:-Unnamed task}
Working directory: ${WORKDIR}

## Execution

Execute the task step by step. Be thorough but efficient.
When done, output a clear summary of what you accomplished.

## Safety Rails

- Your output will be written to a PUBLIC git repository. NEVER include secrets, API keys, tokens, or passwords.
- CI is your approval gate. If tests pass, ship it. If tests fail, fix them first.${PREFERENCES_SECTION}${CONTEXT_REFS_SECTION}"

MODEL_ARGS=""
if [ -n "${ANTHROPIC_MODEL:-}" ]; then
    MODEL_ARGS="--model ${ANTHROPIC_MODEL}"
fi

PROMPT="${TASK_DESCRIPTION:-${TASK_TITLE:-Execute task}}"

echo "Running task via ${AGENT}..."
echo "---"

cd "${WORKDIR}"
set +e
case "$AGENT" in
  claude)
    if [ "${HAS_CONTEXT_JSON}" = "true" ]; then
        SYSTEM_PROMPT=$(build_claude_system_prompt "${CONTEXT_FILE}")
    else
        SYSTEM_PROMPT="${LEGACY_SYSTEM_PROMPT}"
    fi
    claude -p "${PROMPT}" \
        --system-prompt "${SYSTEM_PROMPT}" \
        --allowedTools "Bash,Read,Write,Edit,Glob,Grep,WebFetch,WebSearch,TodoWrite" \
        --output-format text \
        ${MODEL_ARGS} \
        2>&1 | tee "${TASK_OUTPUT_FILE}"
    ;;
  codex)
    CODEX_PROMPT=$(build_codex_instruction_block)
    codex exec \
        --full-auto \
        --skip-git-repo-check \
        "${CODEX_PROMPT}" \
        2>&1 | tee "${TASK_OUTPUT_FILE}"
    ;;
  gemini)
    gemini "${PROMPT}" \
        2>&1 | tee "${TASK_OUTPUT_FILE}"
    ;;
esac
EXIT_CODE=${PIPESTATUS[0]}
set -e

# ── Post-execution: commit and push workspace changes ─────────────────────
# Agents edit files in the cloned repo but those changes are lost when the
# pod dies unless we commit and push them. This is the durable mutation step.
PUSH_EXIT=0
if [ -d "${WORKDIR}/.git" ] && [ -n "${GITHUB_TOKEN:-}" ]; then
    cd "${WORKDIR}"

    # Check autonomy — only push if allowed
    CAN_PUSH="true"
    if [ "${HAS_CONTEXT_JSON}" = "true" ]; then
        CAN_PUSH=$(json_get '.autonomy.can_push' "true")
    fi

    if [ "${CAN_PUSH}" = "true" ]; then
        # Stage all changes (git add -A) and check if there's anything to commit
        git add -A
        if ! git diff --cached --quiet 2>/dev/null; then
            echo "Committing workspace changes..."
            git commit -m "task ${TASK_ID}: ${TASK_TITLE}" \
                --author="Claude OS <claude-os@noreply.github.com>" 2>&1 || true

            # Push with retry (matches controller's retry strategy)
            for attempt in 1 2 3; do
                if git push origin HEAD 2>&1; then
                    echo "Pushed workspace changes (attempt ${attempt})"
                    break
                fi
                echo "Push attempt ${attempt} failed, pulling and retrying..."
                git pull --rebase origin "${REPO_REF:-main}" 2>&1 || true
                if [ "${attempt}" -eq 3 ]; then
                    echo "ERROR: Failed to push workspace changes after 3 attempts"
                    PUSH_EXIT=1
                fi
            done
        else
            echo "No workspace changes to commit"
        fi
    else
        echo "Skipping push: autonomy.can_push is false"
    fi
fi

echo "---" | tee -a "${TASK_OUTPUT_FILE}"
echo "=== Worker Complete ===" | tee -a "${TASK_OUTPUT_FILE}"
echo "Exit code: ${EXIT_CODE}" | tee -a "${TASK_OUTPUT_FILE}"
echo "Push exit: ${PUSH_EXIT}" | tee -a "${TASK_OUTPUT_FILE}"
echo "Finished: $(date -u +%Y-%m-%dT%H:%M:%SZ)" | tee -a "${TASK_OUTPUT_FILE}"

END_EPOCH=$(date +%s)
DURATION_SECONDS=$((END_EPOCH - START_EPOCH))

# If agent succeeded but push failed, that's a partial outcome
if [ "${EXIT_CODE}" -eq 0 ] && [ "${PUSH_EXIT}" -ne 0 ]; then
    EXIT_CODE=0  # Don't fail the task, but mark partial below
fi

ensure_result_block "${EXIT_CODE}" "${DURATION_SECONDS}"
emit_legacy_usage_block "${DURATION_SECONDS}" "${EXIT_CODE}"

exit ${EXIT_CODE}
