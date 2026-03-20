package gitsync

import (
	"os"
	"path/filepath"
	"strings"
	"testing"

	"github.com/dacort/claude-os/controller/queue"
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

func TestParseTaskFileWithPlanFields(t *testing.T) {
	data := []byte(`---
profile: medium
agent: codex
model: claude-sonnet-4-6
priority: normal
status: pending
plan_id: cos-cli-build
task_type: subtask
depends_on:
  - cos-cli-design
  - cos-cli-protocol
context_refs:
  - knowledge/plans/cos-cli/design.md
max_retries: 3
agent_required: claude
---

# Implement CLI binary

## Description
Build the Go binary for the cos CLI.
`)

	tf, err := ParseTaskFile("cos-cli-implement.md", data)
	if err != nil {
		t.Fatalf("ParseTaskFile failed: %v", err)
	}

	if tf.PlanID != "cos-cli-build" {
		t.Errorf("expected PlanID cos-cli-build, got %s", tf.PlanID)
	}
	if tf.TaskType != "subtask" {
		t.Errorf("expected TaskType subtask, got %s", tf.TaskType)
	}
	if len(tf.DependsOn) != 2 {
		t.Fatalf("expected 2 depends_on, got %d", len(tf.DependsOn))
	}
	if tf.DependsOn[0] != "cos-cli-design" {
		t.Errorf("expected first dep cos-cli-design, got %s", tf.DependsOn[0])
	}
	if tf.MaxRetries != 3 {
		t.Errorf("expected MaxRetries 3, got %d", tf.MaxRetries)
	}
	if tf.AgentRequired != "claude" {
		t.Errorf("expected AgentRequired claude, got %s", tf.AgentRequired)
	}
}

func TestSyncPendingTasksWithDependencies(t *testing.T) {
	// Verify that DependsOn and PlanID are correctly parsed from frontmatter.
	// Full integration with Redis + git is tested at the integration level.
	data := []byte(`---
profile: small
priority: normal
status: pending
plan_id: test-plan
task_type: subtask
depends_on:
  - task-a
---

# Task B

## Description
Depends on task A.
`)

	tf, err := ParseTaskFile("task-b.md", data)
	if err != nil {
		t.Fatalf("ParseTaskFile failed: %v", err)
	}

	if len(tf.DependsOn) != 1 || tf.DependsOn[0] != "task-a" {
		t.Errorf("expected depends_on [task-a], got %v", tf.DependsOn)
	}
	if tf.PlanID != "test-plan" {
		t.Errorf("expected plan_id test-plan, got %s", tf.PlanID)
	}
}

func TestParseTaskFileWithProject(t *testing.T) {
	content := `---
target_repo: github.com/dacort/rag-indexer
profile: medium
priority: normal
status: pending
created: 2026-03-20T00:00:00Z
project: rag-indexer
backlog_source: inline
---

# Index documents

## Description
Run the RAG indexer over the document corpus.
`

	task, err := ParseTaskFile("2026-03-20-index-documents.md", []byte(content))
	if err != nil {
		t.Fatalf("ParseTaskFile failed: %v", err)
	}

	if task.Project != "rag-indexer" {
		t.Errorf("expected Project rag-indexer, got %q", task.Project)
	}
	if task.BacklogSource != "inline" {
		t.Errorf("expected BacklogSource inline, got %q", task.BacklogSource)
	}
}

func TestFormatStructuredResult(t *testing.T) {
	result := &queue.TaskResult{
		Version: "1",
		TaskID:  "task-001",
		Agent:   "codex",
		Model:   "gpt-5.4",
		Outcome: "success",
		Summary: "Implemented the adapter contract.",
		Artifacts: []queue.ResultArtifact{
			{Type: "commit", Ref: "abc1234"},
			{Type: "decision", Path: "knowledge/co-founders/decisions/002-context-contract.md"},
		},
		Usage: queue.ResultUsage{
			TokensIn:        100,
			TokensOut:       50,
			DurationSeconds: 12,
		},
		NextAction: &queue.ResultAction{
			Type:     "await_reply",
			Awaiting: "claude",
			ThreadID: "002-context-contract",
		},
	}

	got := formatStructuredResult(result)
	for _, want := range []string{
		"## Outcome",
		"- Agent: codex",
		"## Summary",
		"Implemented the adapter contract.",
		"## Usage",
		"- Tokens in: 100",
		"## Artifacts",
		"commit (ref=abc1234)",
		"decision (path=knowledge/co-founders/decisions/002-context-contract.md)",
		"## Next Action",
		"- Awaiting: claude",
	} {
		if !strings.Contains(got, want) {
			t.Errorf("formatted result missing %q\n%s", want, got)
		}
	}
}

func TestAppendTaskResult(t *testing.T) {
	path := filepath.Join(t.TempDir(), "task.md")
	if err := os.WriteFile(path, []byte("# Task\n"), 0644); err != nil {
		t.Fatalf("write temp file: %v", err)
	}

	result := &queue.TaskResult{
		Version:   "1",
		TaskID:    "task-002",
		Agent:     "claude",
		Model:     "claude-sonnet-4-6",
		Outcome:   "failure",
		Summary:   "Tests failed.",
		Artifacts: []queue.ResultArtifact{},
		Usage: queue.ResultUsage{
			TokensIn:        20,
			TokensOut:       5,
			DurationSeconds: 3,
		},
		Failure: &queue.ResultFailure{
			Reason:    "tests_failed",
			Detail:    "TestFoo failed",
			Retryable: true,
		},
	}

	if err := appendTaskResult(path, "Failure", result, "worker log line"); err != nil {
		t.Fatalf("appendTaskResult: %v", err)
	}

	content, err := os.ReadFile(path)
	if err != nil {
		t.Fatalf("read temp file: %v", err)
	}
	got := string(content)
	for _, want := range []string{
		"## Failure",
		"## Structured Result (raw)",
		"tests_failed",
		"## Worker Logs",
		"worker log line",
	} {
		if !strings.Contains(got, want) {
			t.Errorf("appended file missing %q\n%s", want, got)
		}
	}
}
