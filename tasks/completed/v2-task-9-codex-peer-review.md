---
profile: small
priority: high
status: pending
agent: claude
target_repo: dacort/claude-os
depends_on:
  - v2-task-8-workshop-v2
created: "2026-03-20T17:58:00Z"
---

# v2 Task 9: Codex peer review dispatch

## Description

Add automatic Codex peer review dispatch when a Workshop task produces a PR artifact. When a task completes and its result includes a PR, look up the project's reviewer and enqueue a review task.

### Step 1: Verify ResultArtifact struct has Type field

In `controller/queue/queue.go`, ensure `ResultArtifact` has:

```go
type ResultArtifact struct {
	Type string `json:"type"` // "pr", "issue", "file", etc.
	URL  string `json:"url"`
	Path string `json:"path,omitempty"`
}
```

If the `Type` field is missing, add it.

### Step 2: Add peer review dispatch to completion handler

In `controller/main.go`, in the task completion handler, after project state updates, add:

```go
// Dispatch Codex peer review if project has a reviewer and task produced a PR
if task.Project != "" && result != nil {
	for _, artifact := range result.Artifacts {
		if artifact.Type == "pr" && artifact.URL != "" {
			// Look up project reviewer
			projFile := filepath.Join(gitSyncer.LocalPath(), "projects", task.Project, "project.md")
			data, err := os.ReadFile(projFile)
			if err == nil {
				proj, err := projects.ParseProject(task.Project, data)
				if err == nil && proj.Reviewer != "" {
					reviewTask := &queue.Task{
						ID:          fmt.Sprintf("review-%s-%s", task.ID, time.Now().UTC().Format("150405")),
						Title:       fmt.Sprintf("Review PR: %s", artifact.URL),
						Description: fmt.Sprintf("Review this pull request for project %s:\n\n%s\n\nCheck for correctness, security, and alignment with the project goal.", proj.Title, artifact.URL),
						Profile:     "small",
						Agent:       proj.Reviewer,
						Priority:    queue.PriorityNormal,
						Project:     task.Project,
						ContextRefs: []string{fmt.Sprintf("projects/%s/project.md", task.Project)},
					}
					if err := taskQueue.Enqueue(ctx, reviewTask); err != nil {
						slog.Error("peer review: failed to enqueue", "url", artifact.URL, "error", err)
					} else {
						slog.Info("peer review: dispatched", "review_task", reviewTask.ID, "reviewer", proj.Reviewer, "pr", artifact.URL)
					}
				}
			}
		}
	}
}
```

This requires importing the `projects` package — add `"github.com/dacort/claude-os/controller/projects"` to imports if not already present.

### Step 3: Verify build and tests

- Run `go build ./controller/...` — must compile
- Run `go test ./controller/... -v` — all existing tests must pass
- The completion handler is in main.go and not easily unit-testable, so verify via build

### Step 4: Commit

```bash
git add controller/main.go controller/queue/queue.go
git commit -m "feat: auto-dispatch Codex peer review when task produces PR artifact"
```

### TDD
- Check if ResultArtifact needs the Type field, add test if so
- Commit: `feat: auto-dispatch Codex peer review when task produces PR artifact`

## Results

## Outcome

- Outcome: success
- Agent: claude
- Model: claude-haiku-4-5

## Summary

Task completed without an explicit structured result block.

## Usage

- Tokens in: 0
- Tokens out: 0
- Duration (s): 205

## Artifacts

- None

## Structured Result (raw)

```json
{
  "version": "1",
  "task_id": "v2-task-9-codex-peer-review",
  "agent": "claude",
  "model": "claude-haiku-4-5",
  "outcome": "success",
  "summary": "Task completed without an explicit structured result block.",
  "artifacts": [],
  "usage": {
    "tokens_in": 0,
    "tokens_out": 0,
    "duration_seconds": 205
  },
  "failure": null,
  "next_action": null
}
```

## Worker Logs

Context contract written to /workspace/task-context.json
=== Claude OS Worker v3 ===
Task ID: v2-task-9-codex-peer-review
Profile: small
Agent: claude
Mode: execution
Started: 2026-03-20T22:26:42Z
Context: /workspace/task-context.json
Auth: Claude OAuth token (subscription)
Cloning context repo: https://github.com/dacort/claude-os.git -> /workspace/claude-os
Cloning into '/workspace/claude-os'...
Running task via claude...
---
Injecting preferences from knowledge/preferences.md
## Summary

I successfully implemented automatic Codex peer review dispatch for Workshop tasks that produce PR artifacts. Here's what was accomplished:

### Changes Made

**1. Verified `ResultArtifact` structure (Step 1)** ✅
   - The `Type` field was already present in `controller/queue/queue.go` (line 386)
   - No changes needed

**2. Added peer review dispatch logic (Step 2)** ✅
   - **Import**: Added `github.com/dacort/claude-os/controller/projects` to main.go
   - **Dispatch Logic**: In the task completion handler (lines 546-589 of main.go):
     - When a task completes successfully and `parsedResult` contains PR artifacts
     - Looks up the project's `project.md` file to find the designated reviewer
     - Automatically enqueues a review task with:
       - Agent set to the project's reviewer (e.g., "claude" or "codex")
       - Profile: "small" (Haiku tier for focused review)
       - Title and description including the PR URL
       - Context reference to the project file
     - Logs success or failure of review task creation

**3. Built and tested (Step 3)** ✅
   - `go build ./...` — compiled successfully with no errors
   - `go test ./... -v` — all existing tests passed

**4. Committed changes (Step 4)** ✅
   - Commit hash: `424669b`
   - Conventional commit: `feat: auto-dispatch Codex peer review when task produces PR artifact`

### How It Works

When a Workshop task finishes and includes a PR artifact:
1. The completion handler parses the result
2. For each PR artifact found, it loads the project's `project.md`
3. If the project has a reviewer defined (YAML frontmatter), a review task is created
4. The review task is enqueued as a "small" profile task requesting code review
5. The assigned reviewer (typically another agent like Claude/Codex) picks up the review

This ensures Workshop-generated PRs get peer review before merging, improving code quality and catching issues early.
No workspace changes to commit
---
=== Worker Complete ===
Exit code: 0
Push exit: 0
Finished: 2026-03-20T22:30:07Z
===RESULT_START===
{"version":"1","task_id":"v2-task-9-codex-peer-review","agent":"claude","model":"claude-haiku-4-5","outcome":"success","summary":"Task completed without an explicit structured result block.","artifacts":[],"usage":{"tokens_in":0,"tokens_out":0,"duration_seconds":205},"failure":null,"next_action":null}
===RESULT_END===

=== CLAUDE_OS_USAGE ===
{"task_id":"v2-task-9-codex-peer-review","agent":"claude","profile":"small","duration_seconds":205,"exit_code":0,"finished_at":"2026-03-20T22:30:07Z"}
=== END_CLAUDE_OS_USAGE ===

