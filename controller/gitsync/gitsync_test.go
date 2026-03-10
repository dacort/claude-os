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
