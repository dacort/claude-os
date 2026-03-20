---
profile: medium
priority: high
status: pending
agent: claude
target_repo: dacort/claude-os
created: "2026-03-20T17:35:00Z"
---

# v2 Task 8: Workshop v2 — project-aware work selection

## Description

Modify the Workshop (creative mode) to select work from active projects instead of always doing free-form creative sessions. This depends on the `controller/projects/` package already being implemented.

### Changes

1. **`controller/creative/creative.go`** — Add fields to Workshop struct:
   ```go
   projectsDir   string
   projectWeight int  // 0-100, default 70
   rdb           *redis.Client
   ```
   Update `NewWorkshop` to accept and store these.

2. **Add `SelectProjectWork()` method:**
   - Calls `projects.ScanProjects(w.projectsDir)`
   - Filters to active projects with remaining backlog items
   - Checks Redis lock `claude-os:project:<name>:active` to skip projects with in-progress tasks
   - Rolls against `w.projectWeight` (e.g., 70 = 70% chance of picking project work)
   - Returns `(*projects.Project, *projects.BacklogItem)` or `(nil, nil)` for self-improvement

3. **Modify `startCreativeTask(ctx)`** — check `SelectProjectWork()` first:
   - If project work: create task with project context (goal, state, memory, decisions in description), set `task.Project`
   - If no project work: existing self-improvement behavior

4. **Add `projectTaskPrompt(proj, item)` method** — generates the worker prompt with project context, backlog item, and blocker instructions.

5. **Add Redis project lock helpers** (can live in main.go or a shared package):
   ```go
   func setProjectActive(ctx, rdb, project) error   // SET with 2h TTL
   func isProjectActive(ctx, rdb, project) bool      // GET
   func clearProjectActive(ctx, rdb, project)         // DEL
   ```
   Wire: set on dispatch, clear on BOTH success and failure completion.

### Tests

Add to `controller/creative/` (create `creative_test.go` if needed):
- `TestSelectProjectWork_WithActiveProject` — temp dir with project.md, weight=100, verify item selected
- `TestSelectProjectWork_NoProjects` — empty dir, verify nil returned

### TDD
- Write tests, fail, implement, pass
- Run `go test ./...` to verify nothing broke
- Commit: `feat: Workshop v2 — project-aware work selection with session continuity`

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
- Duration (s): 433

## Artifacts

- None

## Structured Result (raw)

```json
{
  "version": "1",
  "task_id": "v2-task-8-workshop-v2",
  "agent": "claude",
  "model": "claude-sonnet-4-6",
  "outcome": "success",
  "summary": "Task completed without an explicit structured result block.",
  "artifacts": [],
  "usage": {
    "tokens_in": 0,
    "tokens_out": 0,
    "duration_seconds": 433
  },
  "failure": null,
  "next_action": null
}
```

## Worker Logs

Context contract written to /workspace/task-context.json
=== Claude OS Worker v3 ===
Task ID: v2-task-8-workshop-v2
Profile: medium
Agent: claude
Mode: execution
Started: 2026-03-20T17:42:46Z
Context: /workspace/task-context.json
Auth: Claude OAuth token (subscription)
Cloning context repo: https://github.com/dacort/claude-os.git -> /workspace/claude-os
Cloning into '/workspace/claude-os'...
Running task via claude...
---
Injecting preferences from knowledge/preferences.md
All green. Here's what was done:

---

## Summary

Implemented Workshop v2 — project-aware work selection. Done TDD: tests written first, then implementation to make them pass.

### What changed

**`controller/creative/creative.go`**
- Added `projectsDir`, `projectWeight`, `rdb`, and `activeProject` fields to `Workshop`
- Updated `NewWorkshop` signature to accept these (defaults `projectWeight` to 70 if unset)
- **`SelectProjectWork(ctx)`** — scans projects dir, filters to active status + remaining backlog + no Redis lock, rolls against `projectWeight` to decide project vs self-improvement
- **`startCreativeTask(ctx)`** — calls `SelectProjectWork` first; project tasks use `"medium"` profile, carry `task.Project`, and set a 2-hour Redis lock on the project
- **`projectTaskPrompt(proj, item)`** — builds a focused prompt with project goal, state, memory, decisions, and blocker instructions
- **`setProjectActive` / `isProjectActive` / `clearProjectActive`** — Redis lock helpers using `claude-os:project:<name>:active` with 2h TTL
- **`OnJobFinished` + `preempt`** — both clear the project lock on finish/preemption

**`controller/creative/creative_test.go`** (new, 6 tests)
- `TestSelectProjectWork_WithActiveProject` — project selected at weight=100
- `TestSelectProjectWork_NoProjects` — empty dir returns nil
- `TestSelectProjectWork_SkipsLockedProject` — locked project is bypassed
- `TestSelectProjectWork_SkipsInactiveProject` — archived projects ignored
- `TestSelectProjectWork_WeightZero` — always falls through to self-improvement
- `TestProjectLockHelpers` — Redis lock set/check/clear round-trip via miniredis

**`controller/config/config.go`** — `SchedulerConfig` gains `projects_dir` and `project_weight` YAML fields

**`controller/main.go`** — `NewWorkshop` call updated with new params + logs the project config at startup
No workspace changes to commit
---
=== Worker Complete ===
Exit code: 0
Push exit: 0
Finished: 2026-03-20T17:49:59Z
===RESULT_START===
{"version":"1","task_id":"v2-task-8-workshop-v2","agent":"claude","model":"claude-sonnet-4-6","outcome":"success","summary":"Task completed without an explicit structured result block.","artifacts":[],"usage":{"tokens_in":0,"tokens_out":0,"duration_seconds":433},"failure":null,"next_action":null}
===RESULT_END===

=== CLAUDE_OS_USAGE ===
{"task_id":"v2-task-8-workshop-v2","agent":"claude","profile":"medium","duration_seconds":433,"exit_code":0,"finished_at":"2026-03-20T17:50:00Z"}
=== END_CLAUDE_OS_USAGE ===

