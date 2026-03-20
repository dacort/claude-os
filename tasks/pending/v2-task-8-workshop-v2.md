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
