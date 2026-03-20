package comms

import (
	"context"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

// --- GitHubChannel helper tests ---

func TestFormatIssueBody(t *testing.T) {
	msg := Message{
		ID:       "msg-001",
		Title:    "Need credentials",
		Body:     "Missing GITHUB_TOKEN to push.",
		Project:  "my-project",
		TaskID:   "task-001",
		Type:     NeedsHuman,
		Mentions: []string{"dacort"},
	}

	got := formatIssueBody(msg)

	for _, want := range []string{
		"my-project",
		"task-001",
		"@dacort",
		"<!-- claude-os-task-id:task-001 -->",
		"Missing GITHUB_TOKEN to push.",
	} {
		if !strings.Contains(got, want) {
			t.Errorf("formatIssueBody missing %q\ngot:\n%s", want, got)
		}
	}
}

func TestExtractTaskID(t *testing.T) {
	body := "Some content\n<!-- claude-os-task-id:task-42 -->\nMore content"
	got := extractTaskID(body)
	if got != "task-42" {
		t.Errorf("extractTaskID = %q, want %q", got, "task-42")
	}
}

func TestExtractTaskID_Missing(t *testing.T) {
	body := "No marker here, just plain text."
	got := extractTaskID(body)
	if got != "" {
		t.Errorf("extractTaskID should return empty string for missing marker, got %q", got)
	}
}

func TestFileChannel_Notify(t *testing.T) {
	dir := t.TempDir()
	ch := NewFileChannel(dir)
	ctx := context.Background()

	msg := Message{
		ID:      "msg-001",
		Title:   "Blocked on credential",
		Body:    "Missing GITHUB_TOKEN — cannot push to remote.",
		Project: "my-project",
		TaskID:  "task-001",
		Type:    NeedsHuman,
	}

	if err := ch.Notify(ctx, msg); err != nil {
		t.Fatalf("Notify failed: %v", err)
	}

	path := filepath.Join(dir, "task-001.md")
	content, err := os.ReadFile(path)
	if err != nil {
		t.Fatalf("file not created at %s: %v", path, err)
	}

	got := string(content)
	for _, want := range []string{
		"type: needs-human",
		"task_id: task-001",
		"project: my-project",
		"created:",
		"Blocked on credential",
	} {
		if !strings.Contains(got, want) {
			t.Errorf("file missing %q\ngot:\n%s", want, got)
		}
	}
}

func TestFileChannel_Dedup(t *testing.T) {
	dir := t.TempDir()
	ch := NewFileChannel(dir)
	ctx := context.Background()

	msg := Message{
		Title:   "First write",
		Body:    "original content",
		Project: "proj",
		TaskID:  "task-dup",
		Type:    NeedsHuman,
	}

	if err := ch.Notify(ctx, msg); err != nil {
		t.Fatalf("first Notify failed: %v", err)
	}

	// Second call with different body — should be skipped.
	msg.Body = "should not overwrite"
	if err := ch.Notify(ctx, msg); err != nil {
		t.Fatalf("second Notify failed: %v", err)
	}

	entries, err := os.ReadDir(dir)
	if err != nil {
		t.Fatalf("ReadDir: %v", err)
	}
	if len(entries) != 1 {
		t.Errorf("expected 1 file after dedup, got %d", len(entries))
	}

	content, err := os.ReadFile(filepath.Join(dir, "task-dup.md"))
	if err != nil {
		t.Fatalf("read file: %v", err)
	}
	if strings.Contains(string(content), "should not overwrite") {
		t.Error("second Notify overwrote the file — dedup failed")
	}
}

func TestFileChannel_Close(t *testing.T) {
	dir := t.TempDir()
	ch := NewFileChannel(dir)
	ctx := context.Background()

	msg := Message{
		Title:   "Needs review",
		Body:    "Please look at this.",
		Project: "proj",
		TaskID:  "task-close",
		Type:    DecisionNeeded,
	}

	if err := ch.Notify(ctx, msg); err != nil {
		t.Fatalf("Notify failed: %v", err)
	}

	path := filepath.Join(dir, "task-close.md")
	if _, err := os.Stat(path); err != nil {
		t.Fatalf("file should exist before Close: %v", err)
	}

	if err := ch.Close(ctx, "task-close"); err != nil {
		t.Fatalf("Close failed: %v", err)
	}

	if _, err := os.Stat(path); !os.IsNotExist(err) {
		t.Error("file should be deleted after Close")
	}
}

func TestFileChannel_CloseNonExistent(t *testing.T) {
	dir := t.TempDir()
	ch := NewFileChannel(dir)
	ctx := context.Background()

	// Close on a file that was never created should not error.
	if err := ch.Close(ctx, "ghost-task"); err != nil {
		t.Errorf("Close on non-existent file should be a no-op, got: %v", err)
	}
}

func TestFileChannel_Poll(t *testing.T) {
	dir := t.TempDir()
	ch := NewFileChannel(dir)
	ctx := context.Background()

	// FileChannel is write-only for now — Poll should return nil.
	responses, err := ch.Poll(ctx)
	if err != nil {
		t.Fatalf("Poll returned error: %v", err)
	}
	if responses != nil {
		t.Errorf("Poll should return nil for FileChannel, got %v", responses)
	}
}

func TestManager_FanOut(t *testing.T) {
	dir1 := t.TempDir()
	dir2 := t.TempDir()
	ch1 := NewFileChannel(dir1)
	ch2 := NewFileChannel(dir2)
	mgr := NewManager(ch1, ch2)
	ctx := context.Background()

	msg := Message{
		Title:   "Fan-out test",
		Body:    "Both channels should receive this.",
		Project: "proj",
		TaskID:  "task-fanout",
		Type:    ProjectUpdate,
	}

	if err := mgr.Notify(ctx, msg); err != nil {
		t.Fatalf("Manager.Notify failed: %v", err)
	}

	for _, dir := range []string{dir1, dir2} {
		path := filepath.Join(dir, "task-fanout.md")
		if _, err := os.Stat(path); err != nil {
			t.Errorf("channel at %s did not receive notification: %v", dir, err)
		}
	}
}
