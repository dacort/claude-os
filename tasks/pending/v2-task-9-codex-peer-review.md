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
