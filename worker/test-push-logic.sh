#!/bin/bash
# Exercises the fixed push logic from worker/entrypoint.sh against the three
# ways an agent can leave a workspace. Case B is the regression: it is what
# lost the favicon work.
set -u

SANDBOX=$(mktemp -d)
trap 'rm -rf "${SANDBOX}"' EXIT
PASS=0; FAIL=0

# The block under test, lifted from worker/entrypoint.sh.
run_push_block() {
    local WORKDIR="$1" REPO_REF="main" TASK_ID="t1" TASK_TITLE="test task"
    cd "${WORKDIR}" || return 1
    PUSH_EXIT=0

    git add -A
    if ! git diff --cached --quiet 2>/dev/null; then
        echo "Committing workspace changes..."
        git commit -m "task ${TASK_ID}: ${TASK_TITLE}" \
            --author="Claude OS <claude-os@noreply.github.com>" >/dev/null 2>&1 || true
    else
        echo "Nothing left to stage — the agent may have committed its own work"
    fi

    UPSTREAM_REF="origin/${REPO_REF:-main}"
    if git rev-parse --verify --quiet "${UPSTREAM_REF}" >/dev/null 2>&1; then
        AHEAD=$(git rev-list --count "${UPSTREAM_REF}..HEAD" 2>/dev/null || echo 1)
    else
        echo "WARNING: cannot resolve ${UPSTREAM_REF}; attempting push regardless"
        AHEAD=1
    fi

    if [ "${AHEAD}" -gt 0 ]; then
        echo "Pushing ${AHEAD} commit(s) ahead of ${UPSTREAM_REF}..."
        git push origin HEAD >/dev/null 2>&1 && echo "Pushed workspace changes"
    else
        echo "No workspace changes to push — HEAD matches ${UPSTREAM_REF}"
    fi
}

new_repo() {
    local name="$1"
    git init -q --bare "${SANDBOX}/${name}.git"
    git clone -q "${SANDBOX}/${name}.git" "${SANDBOX}/${name}"
    cd "${SANDBOX}/${name}"
    git config user.email t@t; git config user.name t
    echo seed > seed.txt; git add -A
    git commit -qm seed; git push -q origin HEAD:main 2>/dev/null
    git branch -q -M main 2>/dev/null || true
    git fetch -q origin 2>/dev/null
}

check() {
    local label="$1" repo="$2" want="$3"
    local got
    got=$(git --git-dir="${SANDBOX}/${repo}.git" log --oneline 2>/dev/null | grep -c "$want")
    if [ "${got}" -ge 1 ]; then
        echo "  PASS: ${label}"; PASS=$((PASS+1))
    else
        echo "  FAIL: ${label} — '${want}' never reached the remote"; FAIL=$((FAIL+1))
    fi
}

echo "=== Case A: agent leaves changes UNCOMMITTED (worked before too) ==="
new_repo caseA
echo "favicon" > favicon.svg
run_push_block "${SANDBOX}/caseA" | sed 's/^/  /'
check "uncommitted work reaches remote" caseA "test task"

echo
echo "=== Case B: agent COMMITS its own work (the regression) ==="
new_repo caseB
echo "favicon" > favicon.svg
git add -A && git commit -qm "feat: add favicon (agent's own commit)"
run_push_block "${SANDBOX}/caseB" | sed 's/^/  /'
check "agent's own commit reaches remote" caseB "agent's own commit"

echo
echo "=== Case C: agent changes NOTHING (must stay quiet, push nothing) ==="
new_repo caseC
out=$(run_push_block "${SANDBOX}/caseC")
echo "${out}" | sed 's/^/  /'
if echo "${out}" | grep -q "No workspace changes to push"; then
    echo "  PASS: correctly reports nothing to push"; PASS=$((PASS+1))
else
    echo "  FAIL: did not report an empty run"; FAIL=$((FAIL+1))
fi

echo
echo "=== ${PASS} passed, ${FAIL} failed ==="
[ "${FAIL}" -eq 0 ]
