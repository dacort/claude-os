package gitsync

import (
	"context"
	"os"
	"path/filepath"
	"testing"

	"github.com/alicebob/miniredis/v2"
	"github.com/dacort/claude-os/controller/queue"
	"github.com/redis/go-redis/v9"
)

func newTestSyncer(t *testing.T) (*Syncer, *queue.Queue, string) {
	t.Helper()
	mr := miniredis.RunT(t)
	rdb := redis.NewClient(&redis.Options{Addr: mr.Addr()})
	q := queue.New(rdb)

	tmpDir := t.TempDir()
	for _, dir := range []string{"pending", "in-progress", "completed", "failed"} {
		if err := os.MkdirAll(filepath.Join(tmpDir, "tasks", dir), 0755); err != nil {
			t.Fatalf("mkdir %s: %v", dir, err)
		}
	}

	s := NewSyncer("https://github.com/dacort/claude-os.git", "main", tmpDir, "", q)
	return s, q, tmpDir
}

func writeTaskFile(t *testing.T, dir, filename string) {
	t.Helper()
	content := `---
profile: small
priority: normal
---
# Retry Task
## Description
This task needs a retry after failure.
`
	if err := os.WriteFile(filepath.Join(dir, filename), []byte(content), 0644); err != nil {
		t.Fatalf("write task file: %v", err)
	}
}

// TestSyncPendingTasksReDispatchesReturnedTask verifies that a task whose file
// has been moved back to pending/ (for a retry) is re-enqueued even when the
// syncer's knownTasks map still has it marked as dispatched.
//
// This is the fix for issue #18: the controller silently skipped tasks whose
// file reappeared in pending/ after a failure, because knownTasks prevented
// re-enqueue. The silent skip produced no log and no new K8s Job.
func TestSyncPendingTasksReDispatchesReturnedTask(t *testing.T) {
	s, q, tmpDir := newTestSyncer(t)
	ctx := context.Background()

	pendingDir := filepath.Join(tmpDir, "tasks", "pending")
	taskID := "task-retry-001"
	writeTaskFile(t, pendingDir, taskID+".md")

	// Simulate a previous dispatch: mark the task as known.
	// In normal operation this is set by a successful moveTask+push.
	s.knownTasks[taskID] = true

	// syncPendingTasks will see the file, detect it's "known", log a warning,
	// clear knownTasks, and re-enqueue. The moveTask call will fail (no git
	// remote), but the enqueue happens before the move.
	if err := s.syncPendingTasks(ctx); err != nil {
		t.Fatalf("syncPendingTasks: %v", err)
	}

	// The task should now be in Redis.
	task, err := q.Get(ctx, taskID)
	if err != nil {
		t.Fatalf("task not found in Redis after re-dispatch: %v", err)
	}
	if task.Status != queue.StatusPending {
		t.Errorf("expected status pending after re-dispatch, got %s", task.Status)
	}

	// knownTasks should be cleared so a subsequent retry also works.
	if s.knownTasks[taskID] {
		t.Error("expected knownTasks to be cleared after re-dispatch")
	}
}

// TestFailTaskClearsKnownTask verifies that FailTask removes the task from
// knownTasks so a subsequent move of the file back to pending/ triggers a
// re-dispatch without requiring a controller restart.
func TestFailTaskClearsKnownTask(t *testing.T) {
	s, _, _ := newTestSyncer(t)

	taskID := "task-fail-clear"
	s.knownTasks[taskID] = true

	// FailTask with no in-progress file goes through writeResultsOnly path.
	// The git push inside writeResultsOnly will fail (no remote) but that's fine —
	// the delete(s.knownTasks, taskID) at the top of FailTask runs unconditionally.
	s.FailTask(taskID, nil, "job failed: codex token expired")

	if s.knownTasks[taskID] {
		t.Error("expected knownTasks to be cleared after FailTask")
	}
}

// TestCompleteTaskClearsKnownTask verifies symmetry: CompleteTask also clears
// knownTasks so a completed task file moved back to pending/ (e.g. for a re-run)
// can be dispatched again.
func TestCompleteTaskClearsKnownTask(t *testing.T) {
	s, _, _ := newTestSyncer(t)

	taskID := "task-complete-clear"
	s.knownTasks[taskID] = true

	s.CompleteTask(taskID, nil, "")

	if s.knownTasks[taskID] {
		t.Error("expected knownTasks to be cleared after CompleteTask")
	}
}
