---
profile: medium
priority: high
status: pending
target_repo: dacort/claude-os
created: "2026-03-15T00:30:00Z"
context_refs:
  - knowledge/specs/2026-03-14-smart-dispatch-design.md
  - knowledge/plans/2026-03-14-smart-dispatch-implementation.md
---

# Smart Dispatch: Chunk 1 — Queue Extensions

## Description
Implement Tasks 1, 2, and 3 from the smart dispatch implementation plan (`knowledge/plans/2026-03-14-smart-dispatch-implementation.md`), section "Chunk 1: Queue Extensions (Foundation)".

This is pure additive work — new fields, new methods, new tests. No behavior change for existing standalone tasks.

### What to build:

**Task 1: Add new fields to Task struct** in `controller/queue/queue.go`:
- Add `TaskType` type and constants (`standalone`, `subtask`, `plan`)
- Add fields to Task: `PlanID`, `TaskType`, `DependsOn`, `RetryCount`, `MaxRetries`, `AgentRequired`, `TriageVerdict`
- Write tests verifying roundtrip through Enqueue/Dequeue

**Task 2: Add blocked set operations** to `controller/queue/queue.go`:
- `Block(ctx, task)` — stores task in per-plan blocked set
- `GetBlocked(ctx, planID)` — returns blocked tasks for a plan
- `Unblock(ctx, task)` — moves from blocked set to dispatch queue
- Write tests for block/unblock flow

**Task 3: Add plan status tracking** to `controller/queue/queue.go`:
- `RegisterPlanTask(ctx, planID, taskID)`
- `CompletePlanTask(ctx, planID, taskID)`
- `PlanProgress(ctx, planID)` — returns (completed, total)
- `IsPlanComplete(ctx, planID)`
- Write tests

### How to work:
1. Read the full plan at `knowledge/plans/2026-03-14-smart-dispatch-implementation.md` — it has exact code and test snippets
2. Follow TDD: write test first, verify it fails, implement, verify it passes
3. Run ALL existing queue tests after each change to check for regressions: `go test ./queue/ -v`
4. Commit after each task (3 commits total)
5. Push to main when all tests pass

### Success criteria:
- All new tests pass
- All existing queue tests still pass (`TestEnqueueAndDequeue`, `TestDequeueEmpty`, `TestPriorityOrdering`, `TestUpdateStatus`)
- `go build ./...` succeeds
- 3 clean commits pushed to main

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
- Duration (s): 247

## Artifacts

- None

## Structured Result (raw)

```json
{
  "version": "1",
  "task_id": "smart-dispatch-chunk1",
  "agent": "claude",
  "model": "claude-sonnet-4-6",
  "outcome": "success",
  "summary": "Task completed without an explicit structured result block.",
  "artifacts": [],
  "usage": {
    "tokens_in": 0,
    "tokens_out": 0,
    "duration_seconds": 247
  },
  "failure": null,
  "next_action": null
}
```

## Worker Logs

Context contract written to /workspace/task-context.json
=== Claude OS Worker v3 ===
Task ID: smart-dispatch-chunk1
Profile: medium
Agent: claude
Mode: execution
Started: 2026-03-15T02:00:18Z
Context: /workspace/task-context.json
Auth: Claude OAuth token (subscription)
Cloning context repo: https://github.com/dacort/claude-os.git -> /workspace/claude-os
Cloning into '/workspace/claude-os'...
Running task via claude...
---
Injecting context ref: knowledge/specs/2026-03-14-smart-dispatch-design.md
Injecting context ref: knowledge/plans/2026-03-14-smart-dispatch-implementation.md
Injecting preferences from knowledge/preferences.md
All done. Here's a summary:

---

## Done: Chunk 1 — Queue Extensions

Three commits pushed to main:

**1. `feat(queue): add plan_id, task_type, depends_on, retry fields to Task`** (`ce8cb10`)
- New `TaskType` string type with constants: `standalone`, `subtask`, `plan`
- New `StatusBlocked` constant
- Seven new `omitempty` fields on `Task`: `PlanID`, `TaskType`, `DependsOn`, `RetryCount`, `MaxRetries`, `AgentRequired`, `TriageVerdict`
- Test: `TestTaskWithPlanFields` — roundtrip through Enqueue/Dequeue

**2. `feat(queue): add blocked set operations for dependency tracking`** (`648dc7f`)
- `Block(ctx, task)` — stores in per-plan Redis set `claude-os:plan:<id>:blocked`, sets status to `StatusBlocked`
- `GetBlocked(ctx, planID)` — fetches all blocked tasks for a plan
- `Unblock(ctx, task)` — removes from blocked set, adds back to dispatch queue
- Test: `TestBlockAndUnblock` — full block → verify not dequeue-able → unblock → verify dequeue-able

**3. `feat(queue): add plan progress tracking via Redis sets`** (`e499d61`)
- `RegisterPlanTask` / `CompletePlanTask` — add task IDs to two Redis sets per plan
- `PlanProgress` — returns `(completed, total int)`
- `IsPlanComplete` — true when all registered tasks are completed; returns false if total=0 (safe default)
- Test: `TestPlanStatusTracking` — register 3 tasks, complete one at a time, verify `IsPlanComplete` flips at the right moment

**Final state:** 12/12 tests pass, `go build ./...` clean, zero regressions on existing tests.
---
=== Worker Complete ===
Exit code: 0
Finished: 2026-03-15T02:04:24Z
===RESULT_START===
{"version":"1","task_id":"smart-dispatch-chunk1","agent":"claude","model":"claude-sonnet-4-6","outcome":"success","summary":"Task completed without an explicit structured result block.","artifacts":[],"usage":{"tokens_in":0,"tokens_out":0,"duration_seconds":247},"failure":null,"next_action":null}
===RESULT_END===

=== CLAUDE_OS_USAGE ===
{"task_id":"smart-dispatch-chunk1","agent":"claude","profile":"medium","duration_seconds":247,"exit_code":0,"finished_at":"2026-03-15T02:04:24Z"}
=== END_CLAUDE_OS_USAGE ===

