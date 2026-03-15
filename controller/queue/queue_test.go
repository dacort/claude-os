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

func TestParseResult(t *testing.T) {
	sampleLogs := `
=== Worker Complete ===

===RESULT_START===
{"version":"1","task_id":"fix-logging","agent":"claude","model":"claude-sonnet-4-6","outcome":"success","summary":"Fixed pull() logging.","artifacts":[{"type":"commit","ref":"abc1234"}],"usage":{"tokens_in":12500,"tokens_out":3400,"duration_seconds":45},"failure":null,"next_action":null}
===RESULT_END===

=== CLAUDE_OS_USAGE ===
{"task_id":"fix-logging","agent":"claude","profile":"small","duration_seconds":45,"exit_code":0,"finished_at":"2026-03-14T22:00:00Z"}
=== END_CLAUDE_OS_USAGE ===
`
	result := ParseResult(sampleLogs)
	if result == nil {
		t.Fatal("expected ParseResult to return a result, got nil")
	}
	if result.Version != "1" {
		t.Errorf("version = %q, want %q", result.Version, "1")
	}
	if result.TaskID != "fix-logging" {
		t.Errorf("task_id = %q, want %q", result.TaskID, "fix-logging")
	}
	if result.Outcome != "success" {
		t.Errorf("outcome = %q, want %q", result.Outcome, "success")
	}
	if result.Usage.TokensIn != 12500 {
		t.Errorf("tokens_in = %d, want 12500", result.Usage.TokensIn)
	}
	if result.Usage.TokensOut != 3400 {
		t.Errorf("tokens_out = %d, want 3400", result.Usage.TokensOut)
	}
	if result.Usage.DurationSeconds != 45 {
		t.Errorf("duration_seconds = %d, want 45", result.Usage.DurationSeconds)
	}
	if len(result.Artifacts) != 1 || result.Artifacts[0].Type != "commit" {
		t.Errorf("artifacts = %v, want [{type:commit, ref:abc1234}]", result.Artifacts)
	}

	// Missing block returns nil
	if got := ParseResult("no result block here"); got != nil {
		t.Errorf("expected nil for logs without result block, got %+v", got)
	}

	// Malformed JSON returns nil
	malformed := "===RESULT_START===\n{broken\n===RESULT_END==="
	if got := ParseResult(malformed); got != nil {
		t.Errorf("expected nil for malformed JSON, got %+v", got)
	}
}

func TestParseResultFailure(t *testing.T) {
	logs := `
===RESULT_START===
{"version":"1","task_id":"broken-task","agent":"codex","model":"o4-mini","outcome":"failure","summary":"","artifacts":[],"usage":{"tokens_in":500,"tokens_out":100,"duration_seconds":10},"failure":{"reason":"tests_failed","detail":"TestFoo failed","retryable":true},"next_action":null}
===RESULT_END===
`
	result := ParseResult(logs)
	if result == nil {
		t.Fatal("expected ParseResult to return a result")
	}
	if result.Outcome != "failure" {
		t.Errorf("outcome = %q, want failure", result.Outcome)
	}
	if result.Failure == nil {
		t.Fatal("expected failure to be non-nil")
	}
	if result.Failure.Reason != "tests_failed" {
		t.Errorf("failure.reason = %q, want tests_failed", result.Failure.Reason)
	}
	if !result.Failure.Retryable {
		t.Error("expected failure to be retryable")
	}
}

func TestTaskWithPlanFields(t *testing.T) {
	rdb := setupTestRedis(t)
	q := New(rdb)
	ctx := context.Background()

	task := &Task{
		ID:          "subtask-001",
		Title:       "Implement API endpoint",
		Description: "Build the /chat endpoint",
		Profile:     "medium",
		Agent:       "codex",
		Model:       "claude-sonnet-4-6",
		Priority:    PriorityNormal,
		PlanID:      "cos-cli-build",
		TaskType:    TaskTypeSubtask,
		DependsOn:   []string{"subtask-design"},
		ContextRefs: []string{"knowledge/plans/cos-cli/design.md"},
		RetryCount:  0,
		MaxRetries:  2,
	}

	err := q.Enqueue(ctx, task)
	if err != nil {
		t.Fatalf("Enqueue failed: %v", err)
	}

	got, err := q.Dequeue(ctx)
	if err != nil {
		t.Fatalf("Dequeue failed: %v", err)
	}

	if got.PlanID != "cos-cli-build" {
		t.Errorf("expected PlanID cos-cli-build, got %s", got.PlanID)
	}
	if got.TaskType != TaskTypeSubtask {
		t.Errorf("expected TaskType subtask, got %s", got.TaskType)
	}
	if len(got.DependsOn) != 1 || got.DependsOn[0] != "subtask-design" {
		t.Errorf("expected DependsOn [subtask-design], got %v", got.DependsOn)
	}
	if got.MaxRetries != 2 {
		t.Errorf("expected MaxRetries 2, got %d", got.MaxRetries)
	}
}

func TestBlockAndUnblock(t *testing.T) {
	rdb := setupTestRedis(t)
	q := New(rdb)
	ctx := context.Background()

	// Block a task
	task := &Task{
		ID:        "impl-task",
		PlanID:    "my-plan",
		DependsOn: []string{"design-task"},
		Priority:  PriorityNormal,
	}
	err := q.Block(ctx, task)
	if err != nil {
		t.Fatalf("Block failed: %v", err)
	}

	// Should not be in the regular queue
	got, _ := q.Dequeue(ctx)
	if got != nil {
		t.Errorf("blocked task should not be dequeued, got %v", got)
	}

	// Get blocked tasks for this plan
	blocked, err := q.GetBlocked(ctx, "my-plan")
	if err != nil {
		t.Fatalf("GetBlocked failed: %v", err)
	}
	if len(blocked) != 1 || blocked[0].ID != "impl-task" {
		t.Errorf("expected 1 blocked task, got %v", blocked)
	}

	// Unblock it (move to regular queue)
	err = q.Unblock(ctx, task)
	if err != nil {
		t.Fatalf("Unblock failed: %v", err)
	}

	// Now it should be dequeue-able
	got, _ = q.Dequeue(ctx)
	if got == nil || got.ID != "impl-task" {
		t.Errorf("expected impl-task after unblock, got %v", got)
	}

	// Blocked set should be empty
	blocked, _ = q.GetBlocked(ctx, "my-plan")
	if len(blocked) != 0 {
		t.Errorf("expected 0 blocked tasks after unblock, got %d", len(blocked))
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
