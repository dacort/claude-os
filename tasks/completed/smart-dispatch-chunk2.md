---
profile: medium
priority: high
status: pending
target_repo: dacort/claude-os
created: "2026-03-15T02:08:30Z"
context_refs:
  - knowledge/specs/2026-03-14-smart-dispatch-design.md
  - knowledge/plans/2026-03-14-smart-dispatch-implementation.md
---

# Smart Dispatch: Chunk 2 — Frontmatter Parsing + Dependency-Aware Enqueue

## Description
Implement Tasks 4, 5a, and 5 from the smart dispatch implementation plan (`knowledge/plans/2026-03-14-smart-dispatch-implementation.md`), section "Chunk 2: Frontmatter Parsing + Dependency-Aware Enqueue".

This builds on the queue extensions from Chunk 1 (already merged to main).

### What to build:

**Task 4: Parse new frontmatter fields in gitsync** (`controller/gitsync/gitsync.go`):
- Add `PlanID`, `TaskType`, `DependsOn`, `MaxRetries`, `AgentRequired` to `TaskFrontmatter` and `TaskFile` structs
- Wire field assignments through `ParseTaskFile`
- Write test `TestParseTaskFileWithPlanFields`

**Task 5a: DAG cycle detection** (new files):
- Create `controller/queue/dag.go` with `ValidateDAG()` (Kahn's algorithm) and `ValidateSubtaskCount()`
- Create `controller/queue/dag_test.go` with test cases: simple chain, fan-out, direct cycle, transitive cycle, self-ref, unknown dep
- Note: `TestValidateSubtaskCount` uses `fmt.Sprintf` so import `fmt` in the test file

**Task 5: Dependency-aware enqueue in Syncer** (`controller/gitsync/syncer.go`):
- Update `syncPendingTasks` to pass new fields (PlanID, TaskType, DependsOn, MaxRetries) to `queue.Task`
- Add DAG validation for plan subtasks before enqueuing
- Block tasks with unmet dependencies instead of enqueuing them
- Add `collectPlanSubtasks` helper method on Syncer
- Write test `TestSyncPendingTasksWithDependencies` in gitsync_test.go

### How to work:
1. Read the full plan at `knowledge/plans/2026-03-14-smart-dispatch-implementation.md` — it has exact code and test snippets for Chunk 2
2. Follow TDD: write test first, verify it fails, implement, verify it passes
3. Run ALL existing tests after each change to check for regressions: `go test ./queue/ -v && go test ./gitsync/ -v`
4. Commit after each task (3 commits total)
5. Push to main when all tests pass

### Success criteria:
- All new tests pass
- All existing queue tests still pass (TestEnqueueAndDequeue, TestDequeueEmpty, TestPriorityOrdering, TestUpdateStatus, TestTaskWithPlanFields, TestBlockAndUnblock, TestPlanStatusTracking)
- All existing gitsync tests still pass
- `go build ./...` succeeds
- 3 clean commits pushed to main
