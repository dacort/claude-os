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
