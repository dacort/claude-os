package dispatcher

import (
	"encoding/json"
	"testing"
	"time"

	"github.com/dacort/claude-os/controller/queue"
)

func TestBuildTaskContext_Execution(t *testing.T) {
	task := &queue.Task{
		ID:          "fix-logging",
		Title:       "Fix structured logging",
		Description: "The pull() function logs raw output.",
		Profile:     "small",
		Agent:       "claude",
		ContextRefs: []string{"knowledge/preferences.md"},
		Priority:    queue.PriorityNormal,
		CreatedAt:   time.Date(2026, 3, 14, 22, 0, 0, 0, time.UTC),
	}

	tc := BuildTaskContext(task, "https://github.com/dacort/claude-os.git", "main")

	if tc.Version != "1" {
		t.Errorf("version = %q, want %q", tc.Version, "1")
	}
	if tc.Mode != "execution" {
		t.Errorf("mode = %q, want %q", tc.Mode, "execution")
	}
	if tc.Task.ID != "fix-logging" {
		t.Errorf("task.id = %q, want %q", tc.Task.ID, "fix-logging")
	}
	if tc.Repo.Workdir != "/workspace/claude-os" {
		t.Errorf("workdir = %q, want %q", tc.Repo.Workdir, "/workspace/claude-os")
	}
	if !tc.Autonomy.CanMerge {
		t.Error("execution mode should allow merging")
	}
	if tc.Autonomy.CanCreateTasks {
		t.Error("execution mode should not allow creating tasks by default")
	}
	if tc.Founder != nil {
		t.Error("execution mode should have nil founder")
	}
	if len(tc.ContextRefs) != 1 || tc.ContextRefs[0] != "knowledge/preferences.md" {
		t.Errorf("context_refs = %v, want [knowledge/preferences.md]", tc.ContextRefs)
	}
}

func TestBuildTaskContext_TargetRepo(t *testing.T) {
	task := &queue.Task{
		ID:         "fix-thing",
		Title:      "Fix a thing",
		TargetRepo: "dacort/other-repo",
		Profile:    "medium",
		Priority:   queue.PriorityNormal,
		CreatedAt:  time.Date(2026, 3, 14, 22, 0, 0, 0, time.UTC),
	}

	tc := BuildTaskContext(task, "https://github.com/dacort/claude-os.git", "main")

	if tc.Repo.URL != "https://github.com/dacort/other-repo.git" {
		t.Errorf("repo url = %q, want target repo URL", tc.Repo.URL)
	}
	if tc.Repo.Workdir != "/workspace/other-repo" {
		t.Errorf("workdir = %q, want %q", tc.Repo.Workdir, "/workspace/other-repo")
	}
}

func TestBuildTaskContext_FounderMode(t *testing.T) {
	task := &queue.Task{
		ID:          "founder-reply-002",
		Title:       "Founder Reply: Context Contract",
		Profile:     "small",
		Agent:       "codex",
		Mode:        "founder",
		ContextRefs: []string{"knowledge/co-founders/threads/002-context-contract.md"},
		Priority:    queue.PriorityHigh,
		CreatedAt:   time.Date(2026, 3, 14, 22, 0, 0, 0, time.UTC),
	}

	tc := BuildTaskContext(task, "https://github.com/dacort/claude-os.git", "main")

	if tc.Mode != "founder" {
		t.Errorf("mode = %q, want %q", tc.Mode, "founder")
	}
	if tc.Autonomy.CanMerge {
		t.Error("founder mode should not allow merging")
	}
	if !tc.Autonomy.CanCreateTasks {
		t.Error("founder mode should allow creating tasks")
	}
	if tc.Founder == nil {
		t.Fatal("founder mode should populate founder metadata")
	}
	if tc.Founder.ThreadID != "002-context-contract" {
		t.Errorf("founder.thread_id = %q, want %q", tc.Founder.ThreadID, "002-context-contract")
	}
	if tc.Founder.ThreadPath != "knowledge/co-founders/threads/002-context-contract.md" {
		t.Errorf("founder.thread_path = %q", tc.Founder.ThreadPath)
	}
}

func TestMarshalTaskContext(t *testing.T) {
	tc := &TaskContext{
		Version: "1",
		Mode:    "execution",
		Task: TaskContextTask{
			ID:    "test-001",
			Title: "Test",
		},
		Repo: TaskContextRepo{
			Workdir: "/workspace/claude-os",
		},
		ContextRefs: []string{},
		Constraints: []string{"no secrets"},
	}

	jsonStr, err := MarshalTaskContext(tc)
	if err != nil {
		t.Fatalf("marshal: %v", err)
	}

	var parsed map[string]interface{}
	if err := json.Unmarshal([]byte(jsonStr), &parsed); err != nil {
		t.Fatalf("output is not valid JSON: %v", err)
	}
	if parsed["version"] != "1" {
		t.Errorf("version = %v, want 1", parsed["version"])
	}
}

func TestBuildTaskContext_NilContextRefs(t *testing.T) {
	task := &queue.Task{
		ID:        "no-refs",
		Title:     "No refs task",
		Profile:   "small",
		Priority:  queue.PriorityNormal,
		CreatedAt: time.Date(2026, 3, 14, 22, 0, 0, 0, time.UTC),
	}

	tc := BuildTaskContext(task, "https://github.com/dacort/claude-os.git", "main")

	if tc.ContextRefs == nil {
		t.Error("context_refs should be empty array, not nil")
	}
	if len(tc.ContextRefs) != 0 {
		t.Errorf("context_refs should be empty, got %v", tc.ContextRefs)
	}
}
