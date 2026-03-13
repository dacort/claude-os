package gitsync

import (
	"os"
	"path/filepath"
	"testing"
)

func TestParseTaskFile(t *testing.T) {
	content := `---
target_repo: github.com/dacort/test-repo
profile: medium
priority: normal
status: pending
created: 2026-03-10T12:00:00Z
---

# Build CLI Tool

## Description
Create a Go CLI that does X.
`

	task, err := ParseTaskFile("2026-03-10-build-cli-tool.md", []byte(content))
	if err != nil {
		t.Fatalf("ParseTaskFile failed: %v", err)
	}

	if task.TargetRepo != "github.com/dacort/test-repo" {
		t.Errorf("unexpected target_repo: %s", task.TargetRepo)
	}
	if task.Profile != "medium" {
		t.Errorf("unexpected profile: %s", task.Profile)
	}
	if task.Title != "Build CLI Tool" {
		t.Errorf("unexpected title: %s", task.Title)
	}
	if task.Description == "" {
		t.Error("description should not be empty")
	}
}

func TestParseTaskFileWithContextRefsAndModel(t *testing.T) {
	content := `---
target_repo: github.com/dacort/test-repo
profile: small
model: claude-opus-4-6
priority: normal
status: pending
created: 2026-03-13T00:00:00Z
context_refs:
  - knowledge/plans/my-plan/api-schema.md
  - knowledge/preferences.md
---

# Implement API

## Description
Implement the API schema.
`

	task, err := ParseTaskFile("implement-api.md", []byte(content))
	if err != nil {
		t.Fatalf("ParseTaskFile failed: %v", err)
	}

	if task.Model != "claude-opus-4-6" {
		t.Errorf("unexpected model: %s", task.Model)
	}
	if len(task.ContextRefs) != 2 {
		t.Fatalf("expected 2 context_refs, got %d", len(task.ContextRefs))
	}
	if task.ContextRefs[0] != "knowledge/plans/my-plan/api-schema.md" {
		t.Errorf("unexpected context_refs[0]: %s", task.ContextRefs[0])
	}
	if task.ContextRefs[1] != "knowledge/preferences.md" {
		t.Errorf("unexpected context_refs[1]: %s", task.ContextRefs[1])
	}
}

func TestScanPendingTasks(t *testing.T) {
	dir := t.TempDir()
	pendingDir := filepath.Join(dir, "tasks", "pending")
	os.MkdirAll(pendingDir, 0755)

	task1 := `---
target_repo: dacort/repo1
profile: small
priority: normal
---
# Task One
## Description
Do thing one.
`
	task2 := `---
target_repo: dacort/repo2
profile: medium
priority: high
---
# Task Two
## Description
Do thing two.
`
	os.WriteFile(filepath.Join(pendingDir, "task1.md"), []byte(task1), 0644)
	os.WriteFile(filepath.Join(pendingDir, "task2.md"), []byte(task2), 0644)

	tasks, err := ScanPendingTasks(filepath.Join(dir, "tasks"))
	if err != nil {
		t.Fatalf("ScanPendingTasks failed: %v", err)
	}
	if len(tasks) != 2 {
		t.Errorf("expected 2 tasks, got %d", len(tasks))
	}
}
