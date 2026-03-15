---
profile: medium
priority: high
status: pending
target_repo: dacort/claude-os
created: "2026-03-15T02:27:26Z"
context_refs:
  - knowledge/specs/2026-03-14-smart-dispatch-design.md
  - knowledge/plans/2026-03-14-smart-dispatch-implementation.md
---

# Smart Dispatch: Chunk 5 — Wire It All Together

## Description
Implement Tasks 10 and 11 from the smart dispatch implementation plan (`knowledge/plans/2026-03-14-smart-dispatch-implementation.md`), section "Chunk 5: Wire It All Together".

Task 12 (K8s secret + deployment) is ALREADY DONE — skip it entirely.

This is the final chunk. It wires triage, dependency resolution, and rate-limit fallback into the main dispatch loop.

### What to build:

**Task 10: Update the main dispatch loop** (`controller/main.go`):

1. Add `"github.com/dacort/claude-os/controller/triage"` import
2. After Workshop initialization, add Triager init from `TRIAGE_API_KEY` env var (with nil-safe fallback)
3. In the dispatch section (after governance check, before `CreateJob`):
   - Build `AgentStatus` from `taskQueue.IsAgentRateLimited()`
   - Call `triager.Assess()` if available, fall back to `triage.HeuristicRoute()`
   - Store verdict on `task.TriageVerdict`
   - Apply triage recommendations only when frontmatter didn't set model/agent explicitly
   - Promote standalone tasks to plan tasks if `verdict.NeedsPlan`
4. Replace the watcher callback with the enhanced version that handles:
   - **Success path**: complete task, resolve plan dependencies (unblock waiting tasks), check plan completion
   - **Rate limit path**: classify failure, mark agent rate-limited (1h TTL), check `agent_required` constraint, try fallback agent, re-enqueue
   - **Task error path**: retry with count, escalate model on later retries (`escalateModel` helper), fail after max retries
5. Add `escalateModel()` helper function (haiku→sonnet→opus)
6. Add `"time"` to imports if not present

**Task 11: Add routing.yaml config** (`config/routing.yaml`):
- Create config file with model_patterns, agent_capabilities, agent_fallback chain, default_agent
- This is informational/documentation — not loaded by code yet

### Important notes:
- Go IS installed in the container now. Run `go build ./...` to verify compilation.
- Run `go test ./... -v` to verify all tests pass.
- The plan has EXACT code snippets — follow them precisely.
- Be careful with the watcher callback replacement — read the existing callback first, understand the structure, then replace it.

### How to work:
1. Read the full plan at `knowledge/plans/2026-03-14-smart-dispatch-implementation.md` — Chunk 5 section
2. Read `controller/main.go` carefully before modifying
3. Build and test: `cd controller && go build ./... && go test ./... -v`
4. Commit after each task (2 commits total)
5. Push to main when all tests pass

### Success criteria:
- `go build ./...` succeeds
- All existing tests still pass
- 2 clean commits pushed to main
- The controller now triages tasks before dispatching and handles rate-limit fallback on failure

## Results

## Outcome

- Outcome: success
- Agent: claude
- Model: claude-sonnet-4-6

## Summary

Task completed without an explicit structured result block.

## Usage

- Tokens in: 0
- Tokens out: 0
- Duration (s): 354

## Artifacts

- None

## Structured Result (raw)

```json
{
  "version": "1",
  "task_id": "smart-dispatch-chunk5",
  "agent": "claude",
  "model": "claude-sonnet-4-6",
  "outcome": "success",
  "summary": "Task completed without an explicit structured result block.",
  "artifacts": [],
  "usage": {
    "tokens_in": 0,
    "tokens_out": 0,
    "duration_seconds": 354
  },
  "failure": null,
  "next_action": null
}
```

## Worker Logs

Context contract written to /workspace/task-context.json
=== Claude OS Worker v3 ===
Task ID: smart-dispatch-chunk5
Profile: medium
Agent: claude
Mode: execution
Started: 2026-03-15T02:28:15Z
Context: /workspace/task-context.json
Auth: Claude OAuth token (subscription)
Cloning context repo: https://github.com/dacort/claude-os.git -> /workspace/claude-os
Cloning into '/workspace/claude-os'...
Running task via claude...
---
Injecting context ref: knowledge/specs/2026-03-14-smart-dispatch-design.md
Injecting context ref: knowledge/plans/2026-03-14-smart-dispatch-implementation.md
Injecting preferences from knowledge/preferences.md
Done. Here's what was accomplished:

---

## Summary

**Task 10: Wire main dispatch loop** (`controller/main.go`) — 155 lines added

1. **Triager init**: After Workshop setup, reads `TRIAGE_API_KEY` env var. If present, creates a `triage.Triager` pointed at `api.anthropic.com`. Logs a warning and falls back to heuristics if the key isn't set.

2. **Dispatch section** (before `CreateJob`):
   - Builds `AgentStatus` from live rate-limit state in Redis
   - Calls `triager.Assess()` if available; falls back to `HeuristicRoute()` on error or absence
   - Stores verdict reasoning in `task.TriageVerdict` for debugging
   - Applies model/agent recommendations only when frontmatter didn't already set them
   - Promotes `standalone` → `plan` tasks when `verdict.NeedsPlan` is true (→ Opus + Claude)

3. **Watcher callback** (on job finish):
   - **Success**: calls `CompleteTask`, updates status, then walks the plan's blocked siblings — any task whose full `depends_on` list is now `StatusCompleted` gets unblocked into the queue. Logs plan completion when all tasks are done.
   - **Rate limit** (classified from logs): marks the offending agent rate-limited for 1 hour, enforces `agent_required` (waits vs falls back), routes to fallback agent or re-enqueues at creative priority if both are exhausted — no retry counter consumed.
   - **Task error**: retries with incrementing `RetryCount`, escalates model on later retries (haiku→sonnet→opus via `escalateModel()`), fails after `MaxRetries` with a plan-failure warning logged.

4. **`escalateModel()` helper** at package level.

**Task 11: `config/routing.yaml`** — documents keyword patterns, agent capabilities, two-agent fallback chain, and override policy for operators.

**Tests**: all 49 tests pass, `go build ./...` succeeds, 2 commits pushed to main.
No workspace changes to commit
---
=== Worker Complete ===
Exit code: 0
Push exit: 0
Finished: 2026-03-15T02:34:08Z
===RESULT_START===
{"version":"1","task_id":"smart-dispatch-chunk5","agent":"claude","model":"claude-sonnet-4-6","outcome":"success","summary":"Task completed without an explicit structured result block.","artifacts":[],"usage":{"tokens_in":0,"tokens_out":0,"duration_seconds":354},"failure":null,"next_action":null}
===RESULT_END===

=== CLAUDE_OS_USAGE ===
{"task_id":"smart-dispatch-chunk5","agent":"claude","profile":"medium","duration_seconds":354,"exit_code":0,"finished_at":"2026-03-15T02:34:08Z"}
=== END_CLAUDE_OS_USAGE ===

