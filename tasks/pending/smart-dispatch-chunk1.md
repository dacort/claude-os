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
