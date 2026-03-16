package scheduler

import (
	"context"
	"sync"
	"testing"
	"time"

	"github.com/alicebob/miniredis/v2"
	"github.com/redis/go-redis/v9"
)

func setupTestRedis(t *testing.T) *redis.Client {
	t.Helper()
	mr := miniredis.RunT(t)
	return redis.NewClient(&redis.Options{Addr: mr.Addr()})
}

// collectingEnqueue captures enqueued tasks for assertions.
type collectingEnqueue struct {
	mu    sync.Mutex
	tasks []SpawnedTask
}

func (c *collectingEnqueue) enqueue(_ context.Context, task SpawnedTask) error {
	c.mu.Lock()
	defer c.mu.Unlock()
	c.tasks = append(c.tasks, task)
	return nil
}

func (c *collectingEnqueue) count() int {
	c.mu.Lock()
	defer c.mu.Unlock()
	return len(c.tasks)
}

func (c *collectingEnqueue) last() SpawnedTask {
	c.mu.Lock()
	defer c.mu.Unlock()
	return c.tasks[len(c.tasks)-1]
}

func TestNextRun(t *testing.T) {
	rdb := setupTestRedis(t)
	s := New(rdb, nil, nil)

	// "0 9 * * *" = every day at 09:00 UTC
	after := time.Date(2026, 3, 16, 8, 0, 0, 0, time.UTC)
	next, err := s.NextRun("0 9 * * *", after)
	if err != nil {
		t.Fatalf("NextRun: %v", err)
	}
	expected := time.Date(2026, 3, 16, 9, 0, 0, 0, time.UTC)
	if !next.Equal(expected) {
		t.Errorf("expected %v, got %v", expected, next)
	}

	// After 09:00, next run should be tomorrow
	after2 := time.Date(2026, 3, 16, 10, 0, 0, 0, time.UTC)
	next2, err := s.NextRun("0 9 * * *", after2)
	if err != nil {
		t.Fatalf("NextRun: %v", err)
	}
	expected2 := time.Date(2026, 3, 17, 9, 0, 0, 0, time.UTC)
	if !next2.Equal(expected2) {
		t.Errorf("expected %v, got %v", expected2, next2)
	}
}

func TestNextRunEvery6Hours(t *testing.T) {
	rdb := setupTestRedis(t)
	s := New(rdb, nil, nil)

	// "0 */6 * * *" = every 6 hours (00:00, 06:00, 12:00, 18:00)
	after := time.Date(2026, 3, 16, 7, 0, 0, 0, time.UTC)
	next, err := s.NextRun("0 */6 * * *", after)
	if err != nil {
		t.Fatalf("NextRun: %v", err)
	}
	expected := time.Date(2026, 3, 16, 12, 0, 0, 0, time.UTC)
	if !next.Equal(expected) {
		t.Errorf("expected %v, got %v", expected, next)
	}
}

func TestInvalidCronExpression(t *testing.T) {
	rdb := setupTestRedis(t)
	s := New(rdb, nil, nil)

	_, err := s.NextRun("not a cron", time.Now())
	if err == nil {
		t.Fatal("expected error for invalid cron expression")
	}
}

func TestRegisterAndTick(t *testing.T) {
	rdb := setupTestRedis(t)
	collector := &collectingEnqueue{}
	s := New(rdb, collector.enqueue, nil)

	ctx := context.Background()
	task := &ScheduledTask{
		ID:       "status-page",
		Schedule: "0 */6 * * *",
		Profile:  "small",
		Priority: "normal",
		Title:    "OctoClaude Status Page",
	}

	if err := s.Register(ctx, task); err != nil {
		t.Fatalf("Register: %v", err)
	}

	// Manually set next_run to the past so Tick triggers it
	pastTime := time.Now().UTC().Add(-1 * time.Minute)
	rdb.Set(ctx, "claude-os:scheduled:status-page:next_run", pastTime.Unix(), 0)

	s.Tick(ctx)

	if collector.count() != 1 {
		t.Fatalf("expected 1 enqueued task, got %d", collector.count())
	}

	spawned := collector.last()
	if spawned.ParentID != "status-page" {
		t.Errorf("expected parent ID 'status-page', got %q", spawned.ParentID)
	}
	if spawned.Profile != "small" {
		t.Errorf("expected profile 'small', got %q", spawned.Profile)
	}
	if spawned.Title != "OctoClaude Status Page" {
		t.Errorf("expected title 'OctoClaude Status Page', got %q", spawned.Title)
	}
}

func TestSkipIfRunning(t *testing.T) {
	rdb := setupTestRedis(t)
	collector := &collectingEnqueue{}
	s := New(rdb, collector.enqueue, nil)

	ctx := context.Background()
	task := &ScheduledTask{
		ID:       "status-page",
		Schedule: "0 */6 * * *",
		Profile:  "small",
	}

	if err := s.Register(ctx, task); err != nil {
		t.Fatalf("Register: %v", err)
	}

	// Set next_run to the past AND mark as running
	pastTime := time.Now().UTC().Add(-1 * time.Minute)
	rdb.Set(ctx, "claude-os:scheduled:status-page:next_run", pastTime.Unix(), 0)
	rdb.Set(ctx, "claude-os:scheduled:status-page:running", "1", 0)

	s.Tick(ctx)

	if collector.count() != 0 {
		t.Errorf("expected 0 enqueued tasks (should skip while running), got %d", collector.count())
	}
}

func TestGovernanceBlocking(t *testing.T) {
	rdb := setupTestRedis(t)
	collector := &collectingEnqueue{}

	// Governance always blocks
	blockAll := func(_ context.Context, _ string) (bool, string) {
		return false, "budget exhausted"
	}
	s := New(rdb, collector.enqueue, blockAll)

	ctx := context.Background()
	task := &ScheduledTask{
		ID:       "status-page",
		Schedule: "0 */6 * * *",
		Profile:  "small",
	}

	if err := s.Register(ctx, task); err != nil {
		t.Fatalf("Register: %v", err)
	}

	pastTime := time.Now().UTC().Add(-1 * time.Minute)
	rdb.Set(ctx, "claude-os:scheduled:status-page:next_run", pastTime.Unix(), 0)

	s.Tick(ctx)

	if collector.count() != 0 {
		t.Errorf("expected 0 enqueued tasks (governance blocked), got %d", collector.count())
	}
}

func TestDeregister(t *testing.T) {
	rdb := setupTestRedis(t)
	collector := &collectingEnqueue{}
	s := New(rdb, collector.enqueue, nil)

	ctx := context.Background()
	task := &ScheduledTask{
		ID:       "status-page",
		Schedule: "0 */6 * * *",
		Profile:  "small",
	}

	if err := s.Register(ctx, task); err != nil {
		t.Fatalf("Register: %v", err)
	}

	ids := s.RegisteredTaskIDs()
	if len(ids) != 1 || ids[0] != "status-page" {
		t.Errorf("expected [status-page], got %v", ids)
	}

	if err := s.Deregister(ctx, "status-page"); err != nil {
		t.Fatalf("Deregister: %v", err)
	}

	ids = s.RegisteredTaskIDs()
	if len(ids) != 0 {
		t.Errorf("expected empty, got %v", ids)
	}

	// Redis keys should be cleaned up
	exists, _ := rdb.Exists(ctx, "claude-os:scheduled:status-page:next_run").Result()
	if exists != 0 {
		t.Error("expected next_run key to be deleted")
	}
}

func TestOnTaskCompleted(t *testing.T) {
	rdb := setupTestRedis(t)
	s := New(rdb, nil, nil)

	ctx := context.Background()
	task := &ScheduledTask{
		ID:       "status-page",
		Schedule: "0 */6 * * *",
		Profile:  "small",
	}

	s.mu.Lock()
	s.tasks["status-page"] = task
	s.mu.Unlock()

	// Set running flag
	rdb.Set(ctx, "claude-os:scheduled:status-page:running", "1", 0)

	// Simulate completion of a spawned task
	s.OnTaskCompleted(ctx, "status-page-20260316-090000")

	running, err := s.IsRunning(ctx, "status-page")
	if err != nil {
		t.Fatalf("IsRunning: %v", err)
	}
	if running {
		t.Error("expected running to be false after completion")
	}
}

func TestSpawnedTaskID(t *testing.T) {
	ts := time.Date(2026, 3, 16, 9, 0, 0, 0, time.UTC)
	id := SpawnedTaskID("status-page", ts)
	expected := "status-page-20260316-090000"
	if id != expected {
		t.Errorf("expected %q, got %q", expected, id)
	}
}

func TestParentTaskID(t *testing.T) {
	tests := []struct {
		input    string
		expected string
	}{
		{"status-page-20260316-090000", "status-page"},
		{"my-complex-task-name-20260316-120000", "my-complex-task-name"},
		{"short-20260316-090000", "short"},
		{"not-a-spawned-task", ""},
		{"too-short", ""},
		{"", ""},
		// Edge case: ID with numbers that look like dates but aren't at the end
		{"task-123-20260316-090000", "task-123"},
	}

	for _, tt := range tests {
		got := ParentTaskID(tt.input)
		if got != tt.expected {
			t.Errorf("ParentTaskID(%q) = %q, want %q", tt.input, got, tt.expected)
		}
	}
}

func TestRegisterIdempotent(t *testing.T) {
	rdb := setupTestRedis(t)
	collector := &collectingEnqueue{}
	s := New(rdb, collector.enqueue, nil)

	ctx := context.Background()
	task := &ScheduledTask{
		ID:       "status-page",
		Schedule: "0 */6 * * *",
		Profile:  "small",
	}

	// Register twice
	if err := s.Register(ctx, task); err != nil {
		t.Fatalf("Register 1: %v", err)
	}

	// Get the next_run that was set
	nextRun1, _ := rdb.Get(ctx, "claude-os:scheduled:status-page:next_run").Int64()

	if err := s.Register(ctx, task); err != nil {
		t.Fatalf("Register 2: %v", err)
	}

	// next_run should not have changed
	nextRun2, _ := rdb.Get(ctx, "claude-os:scheduled:status-page:next_run").Int64()
	if nextRun1 != nextRun2 {
		t.Errorf("next_run changed on re-register: %d -> %d", nextRun1, nextRun2)
	}
}

func TestTickUpdatesNextRun(t *testing.T) {
	rdb := setupTestRedis(t)
	collector := &collectingEnqueue{}
	s := New(rdb, collector.enqueue, nil)

	ctx := context.Background()
	task := &ScheduledTask{
		ID:       "status-page",
		Schedule: "0 */6 * * *",
		Profile:  "small",
	}

	if err := s.Register(ctx, task); err != nil {
		t.Fatalf("Register: %v", err)
	}

	// Set next_run to the past
	pastTime := time.Now().UTC().Add(-1 * time.Minute)
	rdb.Set(ctx, "claude-os:scheduled:status-page:next_run", pastTime.Unix(), 0)

	s.Tick(ctx)

	// next_run should now be in the future
	nextUnix, _ := rdb.Get(ctx, "claude-os:scheduled:status-page:next_run").Int64()
	nextRun := time.Unix(nextUnix, 0)
	if !nextRun.After(time.Now().UTC()) {
		t.Errorf("next_run should be in the future after tick, got %v", nextRun)
	}
}

func TestInvalidCronRejectsRegister(t *testing.T) {
	rdb := setupTestRedis(t)
	s := New(rdb, nil, nil)

	ctx := context.Background()
	task := &ScheduledTask{
		ID:       "bad-task",
		Schedule: "not valid",
		Profile:  "small",
	}

	err := s.Register(ctx, task)
	if err == nil {
		t.Fatal("expected error for invalid cron expression")
	}
}

func TestCompletionOfNonScheduledTask(t *testing.T) {
	rdb := setupTestRedis(t)
	s := New(rdb, nil, nil)

	ctx := context.Background()

	// Should not panic or error on non-scheduled task IDs
	s.OnTaskCompleted(ctx, "regular-task-id")
	s.OnTaskCompleted(ctx, "")
}
