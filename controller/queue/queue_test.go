package queue

import (
	"context"
	"testing"

	"github.com/alicebob/miniredis/v2"
	"github.com/redis/go-redis/v9"
)

func setupTestRedis(t *testing.T) *redis.Client {
	t.Helper()
	mr := miniredis.RunT(t)
	return redis.NewClient(&redis.Options{Addr: mr.Addr()})
}

func TestEnqueueAndDequeue(t *testing.T) {
	rdb := setupTestRedis(t)
	q := New(rdb)
	ctx := context.Background()

	task := &Task{
		ID:          "task-001",
		Title:       "Build CLI tool",
		Description: "Create a Go CLI that does X",
		TargetRepo:  "dacort/some-repo",
		Profile:     "medium",
		Priority:    PriorityNormal,
		Status:      StatusPending,
	}

	err := q.Enqueue(ctx, task)
	if err != nil {
		t.Fatalf("Enqueue failed: %v", err)
	}

	got, err := q.Dequeue(ctx)
	if err != nil {
		t.Fatalf("Dequeue failed: %v", err)
	}

	if got.ID != "task-001" {
		t.Errorf("expected task-001, got %s", got.ID)
	}
	if got.Status != StatusRunning {
		t.Errorf("expected status running, got %s", got.Status)
	}
}

func TestDequeueEmpty(t *testing.T) {
	rdb := setupTestRedis(t)
	q := New(rdb)
	ctx := context.Background()

	got, err := q.Dequeue(ctx)
	if err != nil {
		t.Fatalf("Dequeue failed: %v", err)
	}
	if got != nil {
		t.Errorf("expected nil task from empty queue, got %v", got)
	}
}

func TestPriorityOrdering(t *testing.T) {
	rdb := setupTestRedis(t)
	q := New(rdb)
	ctx := context.Background()

	q.Enqueue(ctx, &Task{ID: "low", Priority: PriorityCreative, Status: StatusPending})
	q.Enqueue(ctx, &Task{ID: "high", Priority: PriorityHigh, Status: StatusPending})
	q.Enqueue(ctx, &Task{ID: "normal", Priority: PriorityNormal, Status: StatusPending})

	first, _ := q.Dequeue(ctx)
	if first.ID != "high" {
		t.Errorf("expected high priority first, got %s", first.ID)
	}
}

func TestUpdateStatus(t *testing.T) {
	rdb := setupTestRedis(t)
	q := New(rdb)
	ctx := context.Background()

	q.Enqueue(ctx, &Task{ID: "task-002", Priority: PriorityNormal, Status: StatusPending})
	q.Dequeue(ctx)

	err := q.UpdateStatus(ctx, "task-002", StatusCompleted, "PR opened: #42")
	if err != nil {
		t.Fatalf("UpdateStatus failed: %v", err)
	}

	task, err := q.Get(ctx, "task-002")
	if err != nil {
		t.Fatalf("Get failed: %v", err)
	}
	if task.Status != StatusCompleted {
		t.Errorf("expected completed, got %s", task.Status)
	}
	if task.Result != "PR opened: #42" {
		t.Errorf("expected result 'PR opened: #42', got %s", task.Result)
	}
}

func TestRunningSet(t *testing.T) {
	rdb := setupTestRedis(t)
	q := New(rdb)
	ctx := context.Background()

	// Queue two tasks
	for _, id := range []string{"t1", "t2"} {
		q.Enqueue(ctx, &Task{ID: id, Priority: PriorityNormal})
	}

	// Nothing running yet
	count, err := q.RunningCount(ctx)
	if err != nil {
		t.Fatalf("RunningCount: %v", err)
	}
	if count != 0 {
		t.Errorf("expected 0 running, got %d", count)
	}

	// Dequeue first task — should appear in running set
	first, _ := q.Dequeue(ctx)
	count, _ = q.RunningCount(ctx)
	if count != 1 {
		t.Errorf("expected 1 running after dequeue, got %d", count)
	}

	running, _ := q.ListRunning(ctx)
	if len(running) != 1 || running[0] != first.ID {
		t.Errorf("expected [%s] in running set, got %v", first.ID, running)
	}

	// Dequeue second task
	second, _ := q.Dequeue(ctx)
	count, _ = q.RunningCount(ctx)
	if count != 2 {
		t.Errorf("expected 2 running, got %d", count)
	}

	// Complete first task — should be removed from running set
	q.UpdateStatus(ctx, first.ID, StatusCompleted, "done")
	count, _ = q.RunningCount(ctx)
	if count != 1 {
		t.Errorf("expected 1 running after completion, got %d", count)
	}

	// Fail second task — should also be removed
	q.UpdateStatus(ctx, second.ID, StatusFailed, "oops")
	count, _ = q.RunningCount(ctx)
	if count != 0 {
		t.Errorf("expected 0 running after failure, got %d", count)
	}
}

func TestParseUsage(t *testing.T) {
	sampleLogs := `
=== Worker Complete ===
Exit code: 0
Finished: 2026-03-14T20:00:00Z

=== CLAUDE_OS_USAGE ===
{"task_id":"task-001","agent":"claude","profile":"small","duration_seconds":42,"exit_code":0,"finished_at":"2026-03-14T20:00:00Z"}
=== END_CLAUDE_OS_USAGE ===
`
	rec := ParseUsage(sampleLogs)
	if rec == nil {
		t.Fatal("expected ParseUsage to return a record, got nil")
	}
	if rec.TaskID != "task-001" {
		t.Errorf("expected task_id task-001, got %s", rec.TaskID)
	}
	if rec.DurationSeconds != 42 {
		t.Errorf("expected 42 seconds, got %d", rec.DurationSeconds)
	}
	if rec.Agent != "claude" {
		t.Errorf("expected agent claude, got %s", rec.Agent)
	}

	// Missing block returns nil
	if got := ParseUsage("no usage block here"); got != nil {
		t.Errorf("expected nil for logs without usage block, got %+v", got)
	}

	// Malformed JSON returns nil
	malformed := "=== CLAUDE_OS_USAGE ===\n{broken\n=== END_CLAUDE_OS_USAGE ==="
	if got := ParseUsage(malformed); got != nil {
		t.Errorf("expected nil for malformed JSON, got %+v", got)
	}
}

func TestRequeueTasks(t *testing.T) {
	rdb := setupTestRedis(t)
	q := New(rdb)
	ctx := context.Background()

	q.Enqueue(ctx, &Task{ID: "orphan", Priority: PriorityNormal})
	q.Dequeue(ctx) // now in running set

	// Simulate controller restart: requeue the orphaned task
	err := q.RequeueTasks(ctx, []string{"orphan"})
	if err != nil {
		t.Fatalf("RequeueTasks: %v", err)
	}

	// Should no longer be in running set
	count, _ := q.RunningCount(ctx)
	if count != 0 {
		t.Errorf("expected 0 running after requeue, got %d", count)
	}

	// Should be dequeue-able again
	task, err := q.Dequeue(ctx)
	if err != nil {
		t.Fatalf("Dequeue after requeue: %v", err)
	}
	if task == nil || task.ID != "orphan" {
		t.Errorf("expected orphan task back in queue, got %v", task)
	}
}
