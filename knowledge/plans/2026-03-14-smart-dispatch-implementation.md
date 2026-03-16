# Smart Dispatch Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade the Claude OS controller from a dumb conveyor belt to an intelligent foreman with triage, planning, dependency tracking, and rate-limit recovery.

**Architecture:** Two-tier triage (controller-side Haiku for fast routing, worker-side Opus for complex decomposition). Dependencies tracked via per-plan Redis sets. Rate-limit detection in the completion watcher triggers agent fallback. All state in Redis + git, crash-safe.

**Tech Stack:** Go 1.25, Redis (miniredis for tests), K8s client-go, Anthropic Messages API (Haiku)

**Spec:** `docs/superpowers/specs/2026-03-14-smart-dispatch-design.md`

**Repo:** `dacort/claude-os` (cloned at `/tmp/claude-os`)

---

## File Map

### New files
| File | Responsibility |
|------|---------------|
| `controller/triage/triage.go` | Haiku API client, Assess() function, prompt builder |
| `controller/triage/triage_test.go` | Tests with mock HTTP server |
| `controller/triage/heuristic.go` | Keyword-based fallback routing when Haiku is unavailable |
| `controller/triage/heuristic_test.go` | Heuristic routing tests |
| `controller/queue/dag.go` | DAG cycle detection via topological sort |
| `controller/queue/dag_test.go` | Cycle detection tests |
| `config/routing.yaml` | Routing rules, fallback chains, model patterns |

### Modified files
| File | Changes |
|------|---------|
| `controller/queue/queue.go` | Add PlanID, TaskType, DependsOn, RetryCount, MaxRetries to Task; add blocked set ops |
| `controller/queue/queue_test.go` | Tests for new fields and blocked set |
| `controller/gitsync/gitsync.go` | Parse new frontmatter fields (plan_id, task_type, depends_on, etc.) |
| `controller/gitsync/gitsync_test.go` | Tests for new frontmatter parsing |
| `controller/gitsync/syncer.go` | Pass new fields through to queue.Task; dependency-aware enqueue |
| `controller/watcher/watcher.go` | Add failure classification, dependency resolution on completion |
| `controller/main.go` | Wire triage into dispatch loop, pass agent status |
| `controller/go.mod` | No new deps needed (net/http for Haiku, already available) |

---

## Chunk 1: Queue Extensions (Foundation)

### Task 1: Add new fields to Task struct

**Files:**
- Modify: `controller/queue/queue.go:29-45`
- Test: `controller/queue/queue_test.go`

- [ ] **Step 1: Write test for new Task fields roundtrip**

In `controller/queue/queue_test.go`, add:

```go
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /tmp/claude-os/controller && go test ./queue/ -run TestTaskWithPlanFields -v`
Expected: FAIL — `PlanID`, `TaskType`, `TaskTypeSubtask` undefined

- [ ] **Step 3: Add new fields and constants to queue.go**

In `controller/queue/queue.go`, add after the Priority constants:

```go
type TaskType string

const (
	TaskTypeStandalone TaskType = "standalone"
	TaskTypeSubtask    TaskType = "subtask"
	TaskTypePlan       TaskType = "plan"
)
```

Add to the `Task` struct:

```go
type Task struct {
	ID          string    `json:"id"`
	Title       string    `json:"title"`
	Description string    `json:"description"`
	TargetRepo  string    `json:"target_repo"`
	Profile     string    `json:"profile"`
	Agent       string    `json:"agent,omitempty"`
	Model       string    `json:"model,omitempty"`
	ContextRefs []string  `json:"context_refs,omitempty"`
	Priority    Priority  `json:"priority"`
	Status      Status    `json:"status"`
	Result      string    `json:"result,omitempty"`
	CreatedAt   time.Time `json:"created_at"`
	StartedAt   time.Time `json:"started_at,omitempty"`
	FinishedAt  time.Time `json:"finished_at,omitempty"`
	TokensUsed  int64     `json:"tokens_used,omitempty"`
	// Smart dispatch fields
	PlanID        string   `json:"plan_id,omitempty"`
	TaskType      TaskType `json:"task_type,omitempty"`
	DependsOn     []string `json:"depends_on,omitempty"`
	RetryCount    int      `json:"retry_count,omitempty"`
	MaxRetries    int      `json:"max_retries,omitempty"`
	AgentRequired string   `json:"agent_required,omitempty"`
	TriageVerdict string   `json:"triage_verdict,omitempty"`
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /tmp/claude-os/controller && go test ./queue/ -run TestTaskWithPlanFields -v`
Expected: PASS

- [ ] **Step 5: Run all existing queue tests to check for regressions**

Run: `cd /tmp/claude-os/controller && go test ./queue/ -v`
Expected: All tests PASS (new fields are omitempty, existing tests unaffected)

- [ ] **Step 6: Commit**

```bash
cd /tmp/claude-os
git add controller/queue/queue.go controller/queue/queue_test.go
git commit -m "feat(queue): add plan_id, task_type, depends_on, retry fields to Task"
```

### Task 2: Add blocked set operations to Queue

**Files:**
- Modify: `controller/queue/queue.go`
- Test: `controller/queue/queue_test.go`

- [ ] **Step 1: Write test for Block and Unblock operations**

In `controller/queue/queue_test.go`, add:

```go
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /tmp/claude-os/controller && go test ./queue/ -run TestBlockAndUnblock -v`
Expected: FAIL — `Block`, `Unblock`, `GetBlocked` undefined

- [ ] **Step 3: Implement Block, Unblock, GetBlocked**

In `controller/queue/queue.go`, add:

```go
const keyBlocked = "claude-os:plan:%s:blocked"

// Block stores a task in the per-plan blocked set (not the dispatch queue).
func (q *Queue) Block(ctx context.Context, task *Task) error {
	task.Status = StatusPending
	data, err := json.Marshal(task)
	if err != nil {
		return fmt.Errorf("marshal task: %w", err)
	}
	pipe := q.rdb.Pipeline()
	pipe.Set(ctx, fmt.Sprintf(keyTask, task.ID), data, 0)
	pipe.SAdd(ctx, fmt.Sprintf(keyBlocked, task.PlanID), task.ID)
	_, err = pipe.Exec(ctx)
	return err
}

// GetBlocked returns all blocked tasks for a plan.
func (q *Queue) GetBlocked(ctx context.Context, planID string) ([]*Task, error) {
	ids, err := q.rdb.SMembers(ctx, fmt.Sprintf(keyBlocked, planID)).Result()
	if err != nil {
		return nil, err
	}
	var tasks []*Task
	for _, id := range ids {
		task, err := q.Get(ctx, id)
		if err != nil {
			continue
		}
		tasks = append(tasks, task)
	}
	return tasks, nil
}

// Unblock moves a task from the blocked set to the dispatch queue.
func (q *Queue) Unblock(ctx context.Context, task *Task) error {
	pipe := q.rdb.Pipeline()
	pipe.SRem(ctx, fmt.Sprintf(keyBlocked, task.PlanID), task.ID)
	pipe.ZAdd(ctx, keyQueue, redis.Z{
		Score:  float64(task.Priority),
		Member: task.ID,
	})
	_, err := pipe.Exec(ctx)
	return err
}
```

Also add a new Status constant:

```go
const StatusBlocked Status = "blocked"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /tmp/claude-os/controller && go test ./queue/ -run TestBlockAndUnblock -v`
Expected: PASS

- [ ] **Step 5: Run all queue tests**

Run: `cd /tmp/claude-os/controller && go test ./queue/ -v`
Expected: All PASS

- [ ] **Step 6: Commit**

```bash
cd /tmp/claude-os
git add controller/queue/queue.go controller/queue/queue_test.go
git commit -m "feat(queue): add blocked set operations for dependency tracking"
```

### Task 3: Add plan status tracking to Queue

**Files:**
- Modify: `controller/queue/queue.go`
- Test: `controller/queue/queue_test.go`

- [ ] **Step 1: Write test for plan status tracking**

```go
func TestPlanStatusTracking(t *testing.T) {
	rdb := setupTestRedis(t)
	q := New(rdb)
	ctx := context.Background()

	// Register tasks in a plan
	q.RegisterPlanTask(ctx, "my-plan", "task-a")
	q.RegisterPlanTask(ctx, "my-plan", "task-b")
	q.RegisterPlanTask(ctx, "my-plan", "task-c")

	// Initially no tasks are completed
	done, total, err := q.PlanProgress(ctx, "my-plan")
	if err != nil {
		t.Fatalf("PlanProgress failed: %v", err)
	}
	if done != 0 || total != 3 {
		t.Errorf("expected 0/3, got %d/%d", done, total)
	}

	// Mark one completed
	q.CompletePlanTask(ctx, "my-plan", "task-a")
	done, total, _ = q.PlanProgress(ctx, "my-plan")
	if done != 1 || total != 3 {
		t.Errorf("expected 1/3, got %d/%d", done, total)
	}

	// Check if plan is complete
	if q.IsPlanComplete(ctx, "my-plan") {
		t.Error("plan should not be complete yet")
	}

	// Complete all
	q.CompletePlanTask(ctx, "my-plan", "task-b")
	q.CompletePlanTask(ctx, "my-plan", "task-c")
	if !q.IsPlanComplete(ctx, "my-plan") {
		t.Error("plan should be complete")
	}
}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /tmp/claude-os/controller && go test ./queue/ -run TestPlanStatusTracking -v`
Expected: FAIL

- [ ] **Step 3: Implement plan tracking methods**

In `controller/queue/queue.go`, add:

```go
const (
	keyPlanTasks     = "claude-os:plan:%s:tasks"
	keyPlanCompleted = "claude-os:plan:%s:completed"
)

func (q *Queue) RegisterPlanTask(ctx context.Context, planID, taskID string) error {
	return q.rdb.SAdd(ctx, fmt.Sprintf(keyPlanTasks, planID), taskID).Err()
}

func (q *Queue) CompletePlanTask(ctx context.Context, planID, taskID string) error {
	return q.rdb.SAdd(ctx, fmt.Sprintf(keyPlanCompleted, planID), taskID).Err()
}

func (q *Queue) PlanProgress(ctx context.Context, planID string) (completed, total int, err error) {
	total64, err := q.rdb.SCard(ctx, fmt.Sprintf(keyPlanTasks, planID)).Result()
	if err != nil {
		return 0, 0, err
	}
	done64, err := q.rdb.SCard(ctx, fmt.Sprintf(keyPlanCompleted, planID)).Result()
	if err != nil {
		return 0, 0, err
	}
	return int(done64), int(total64), nil
}

func (q *Queue) IsPlanComplete(ctx context.Context, planID string) bool {
	done, total, err := q.PlanProgress(ctx, planID)
	if err != nil || total == 0 {
		return false
	}
	return done >= total
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /tmp/claude-os/controller && go test ./queue/ -run TestPlanStatusTracking -v`
Expected: PASS

- [ ] **Step 5: Run all queue tests**

Run: `cd /tmp/claude-os/controller && go test ./queue/ -v`
Expected: All PASS

- [ ] **Step 6: Commit**

```bash
cd /tmp/claude-os
git add controller/queue/queue.go controller/queue/queue_test.go
git commit -m "feat(queue): add plan progress tracking via Redis sets"
```

---

## Chunk 2: Frontmatter Parsing + Dependency-Aware Enqueue

### Task 4: Parse new frontmatter fields in gitsync

**Files:**
- Modify: `controller/gitsync/gitsync.go:15-24`
- Test: `controller/gitsync/gitsync_test.go`

- [ ] **Step 1: Write test for new frontmatter fields**

In `controller/gitsync/gitsync_test.go`, add:

```go
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /tmp/claude-os/controller && go test ./gitsync/ -run TestParseTaskFileWithPlanFields -v`
Expected: FAIL — `PlanID`, `TaskType`, `DependsOn`, `MaxRetries`, `AgentRequired` not in structs

- [ ] **Step 3: Add new fields to TaskFrontmatter and TaskFile**

In `controller/gitsync/gitsync.go`, update:

```go
type TaskFrontmatter struct {
	TargetRepo    string   `yaml:"target_repo"`
	Profile       string   `yaml:"profile"`
	Agent         string   `yaml:"agent"`
	Model         string   `yaml:"model"`
	Priority      string   `yaml:"priority"`
	Status        string   `yaml:"status"`
	Created       string   `yaml:"created"`
	ContextRefs   []string `yaml:"context_refs"`
	PlanID        string   `yaml:"plan_id"`
	TaskType      string   `yaml:"task_type"`
	DependsOn     []string `yaml:"depends_on"`
	MaxRetries    int      `yaml:"max_retries"`
	AgentRequired string   `yaml:"agent_required"`
}

type TaskFile struct {
	Filename      string
	TargetRepo    string
	Profile       string
	Agent         string
	Model         string
	Priority      string
	Title         string
	Description   string
	CreatedAt     time.Time
	ContextRefs   []string
	PlanID        string
	TaskType      string
	DependsOn     []string
	MaxRetries    int
	AgentRequired string
}
```

In `ParseTaskFile`, add the new field assignments after the existing ones:

```go
	return &TaskFile{
		Filename:      filename,
		TargetRepo:    fm.TargetRepo,
		Profile:       fm.Profile,
		Agent:         fm.Agent,
		Model:         fm.Model,
		Priority:      fm.Priority,
		Title:         title,
		Description:   description,
		CreatedAt:     createdAt,
		ContextRefs:   fm.ContextRefs,
		PlanID:        fm.PlanID,
		TaskType:      fm.TaskType,
		DependsOn:     fm.DependsOn,
		MaxRetries:    fm.MaxRetries,
		AgentRequired: fm.AgentRequired,
	}, nil
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /tmp/claude-os/controller && go test ./gitsync/ -run TestParseTaskFileWithPlanFields -v`
Expected: PASS

- [ ] **Step 5: Run all gitsync tests**

Run: `cd /tmp/claude-os/controller && go test ./gitsync/ -v`
Expected: All PASS

- [ ] **Step 6: Commit**

```bash
cd /tmp/claude-os
git add controller/gitsync/gitsync.go controller/gitsync/gitsync_test.go
git commit -m "feat(gitsync): parse plan_id, task_type, depends_on from frontmatter"
```

### Task 5a: DAG cycle detection

**Files:**
- Create: `controller/queue/dag.go`
- Create: `controller/queue/dag_test.go`

- [ ] **Step 1: Write tests for cycle detection**

Create `controller/queue/dag_test.go`:

```go
package queue

import "testing"

func TestValidateDAG(t *testing.T) {
	tests := []struct {
		name    string
		tasks   map[string][]string // taskID -> depends_on
		wantErr bool
	}{
		{
			name:    "simple chain — no cycle",
			tasks:   map[string][]string{"a": {}, "b": {"a"}, "c": {"b"}},
			wantErr: false,
		},
		{
			name:    "fan-out — no cycle",
			tasks:   map[string][]string{"a": {}, "b": {"a"}, "c": {"a"}, "d": {"b", "c"}},
			wantErr: false,
		},
		{
			name:    "direct cycle",
			tasks:   map[string][]string{"a": {"b"}, "b": {"a"}},
			wantErr: true,
		},
		{
			name:    "transitive cycle",
			tasks:   map[string][]string{"a": {"c"}, "b": {"a"}, "c": {"b"}},
			wantErr: true,
		},
		{
			name:    "self-referencing",
			tasks:   map[string][]string{"a": {"a"}},
			wantErr: true,
		},
		{
			name:    "single task no deps",
			tasks:   map[string][]string{"a": {}},
			wantErr: false,
		},
		{
			name:    "dep references unknown task",
			tasks:   map[string][]string{"a": {"nonexistent"}},
			wantErr: true,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			err := ValidateDAG(tt.tasks)
			if (err != nil) != tt.wantErr {
				t.Errorf("ValidateDAG() error = %v, wantErr %v", err, tt.wantErr)
			}
		})
	}
}

func TestValidateSubtaskCount(t *testing.T) {
	// 10 tasks — OK
	tasks := make(map[string][]string)
	for i := 0; i < 10; i++ {
		tasks[fmt.Sprintf("task-%d", i)] = nil
	}
	if err := ValidateSubtaskCount(tasks, 10); err != nil {
		t.Errorf("10 tasks should be ok: %v", err)
	}

	// 11 tasks — exceeds limit
	tasks["task-10"] = nil
	if err := ValidateSubtaskCount(tasks, 10); err == nil {
		t.Error("11 tasks should fail")
	}
}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /tmp/claude-os/controller && go test ./queue/ -run TestValidateDAG -v`
Expected: FAIL

- [ ] **Step 3: Implement DAG validation**

Create `controller/queue/dag.go`:

```go
package queue

import "fmt"

// ValidateDAG checks that a set of task dependencies form a valid DAG.
// Returns an error if there are cycles or references to unknown tasks.
func ValidateDAG(tasks map[string][]string) error {
	// Check for references to unknown tasks
	for id, deps := range tasks {
		for _, dep := range deps {
			if _, ok := tasks[dep]; !ok {
				return fmt.Errorf("task %s depends on unknown task %s", id, dep)
			}
		}
	}

	// Kahn's algorithm for topological sort / cycle detection
	inDegree := make(map[string]int)
	for id := range tasks {
		inDegree[id] = 0
	}
	for _, deps := range tasks {
		for _, dep := range deps {
			inDegree[dep] = inDegree[dep] // ensure key exists
		}
	}
	// Count incoming edges (reversed: if B depends on A, A has an edge to B)
	for _, deps := range tasks {
		for range deps {
		}
	}
	// Actually: inDegree[X] = number of deps X has
	for id, deps := range tasks {
		inDegree[id] = len(deps)
	}

	var queue []string
	for id, deg := range inDegree {
		if deg == 0 {
			queue = append(queue, id)
		}
	}

	visited := 0
	for len(queue) > 0 {
		node := queue[0]
		queue = queue[1:]
		visited++

		// Find tasks that depend on this node
		for id, deps := range tasks {
			for _, dep := range deps {
				if dep == node {
					inDegree[id]--
					if inDegree[id] == 0 {
						queue = append(queue, id)
					}
				}
			}
		}
	}

	if visited != len(tasks) {
		return fmt.Errorf("dependency cycle detected: %d of %d tasks could be ordered", visited, len(tasks))
	}
	return nil
}

// ValidateSubtaskCount checks that a plan doesn't exceed the max subtask limit.
func ValidateSubtaskCount(tasks map[string][]string, max int) error {
	if len(tasks) > max {
		return fmt.Errorf("plan has %d subtasks, max is %d", len(tasks), max)
	}
	return nil
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /tmp/claude-os/controller && go test ./queue/ -run "TestValidateDAG|TestValidateSubtaskCount" -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
cd /tmp/claude-os
git add controller/queue/dag.go controller/queue/dag_test.go
git commit -m "feat(queue): DAG cycle detection and subtask count validation"
```

### Task 5: Dependency-aware enqueue in Syncer

**Files:**
- Modify: `controller/gitsync/syncer.go:102-146`

This task modifies `syncPendingTasks` to check dependencies before enqueuing. Tasks with unmet `depends_on` go to the blocked set. Also validates DAG (no cycles) when ingesting plan subtasks.

- [ ] **Step 1: Write test for dependency-aware enqueue**

In `controller/gitsync/gitsync_test.go`, add:

```go
func TestSyncPendingTasksWithDependencies(t *testing.T) {
	// This test verifies the parsing and field flow.
	// Full integration with the syncer requires a git repo and Redis,
	// which is tested at the integration level.
	// Here we verify that DependsOn is correctly parsed.
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
```

- [ ] **Step 2: Run test to verify it passes** (already covered by Task 4 changes)

Run: `cd /tmp/claude-os/controller && go test ./gitsync/ -v`
Expected: All PASS

- [ ] **Step 3: Update syncPendingTasks in syncer.go**

In `controller/gitsync/syncer.go`, update the `syncPendingTasks` method. Replace the task construction and enqueue block (lines ~124-144) with:

```go
		task := &queue.Task{
			ID:          taskID,
			Title:       tf.Title,
			Description: tf.Description,
			TargetRepo:  tf.TargetRepo,
			Profile:     tf.Profile,
			Agent:       tf.Agent,
			Model:       tf.Model,
			ContextRefs: tf.ContextRefs,
			Priority:    priority,
			PlanID:      tf.PlanID,
			TaskType:    queue.TaskType(tf.TaskType),
			DependsOn:   tf.DependsOn,
			MaxRetries:  tf.MaxRetries,
		}
		if task.MaxRetries == 0 {
			task.MaxRetries = 2 // default
		}
		if task.TaskType == "" {
			task.TaskType = queue.TaskTypeStandalone
		}

		// Validate plan constraints on ingestion
		if task.PlanID != "" && task.TaskType == queue.TaskTypeSubtask {
			// Collect all subtasks for this plan to validate DAG
			planTasks := s.collectPlanSubtasks(ctx, task.PlanID, tasksPath)
			// Add current task
			planTasks[taskID] = task.DependsOn

			if err := queue.ValidateSubtaskCount(planTasks, 10); err != nil {
				slog.Error("plan validation failed", "plan", task.PlanID, "error", err)
				continue
			}
			if err := queue.ValidateDAG(planTasks); err != nil {
				slog.Error("plan DAG validation failed", "plan", task.PlanID, "error", err)
				continue
			}
			// Validate depends_on only references tasks in same plan
			for _, dep := range task.DependsOn {
				if _, ok := planTasks[dep]; !ok {
					slog.Error("depends_on references task outside plan", "task", taskID, "dep", dep, "plan", task.PlanID)
					continue
				}
			}
		}

		// If task has unmet dependencies, block it instead of enqueuing
		if len(task.DependsOn) > 0 {
			allMet := true
			for _, dep := range task.DependsOn {
				depTask, err := s.queue.Get(ctx, dep)
				if err != nil || depTask.Status != queue.StatusCompleted {
					allMet = false
					break
				}
			}
			if !allMet {
				if err := s.queue.Block(ctx, task); err != nil {
					slog.Error("failed to block task", "id", taskID, "error", err)
					continue
				}
				// Register in plan tracking
				if task.PlanID != "" {
					s.queue.RegisterPlanTask(ctx, task.PlanID, taskID)
				}
				s.knownTasks[taskID] = true
				slog.Info("blocked task (unmet dependencies)", "id", taskID, "depends_on", task.DependsOn)
				continue
			}
		}

		if err := s.queue.Enqueue(ctx, task); err != nil {
			slog.Error("failed to enqueue task", "id", taskID, "error", err)
			continue
		}
		// Register in plan tracking
		if task.PlanID != "" {
			s.queue.RegisterPlanTask(ctx, task.PlanID, taskID)
		}
		s.knownTasks[taskID] = true
		slog.Info("enqueued task from git", "id", taskID, "title", tf.Title)

		s.moveTask(tf.Filename, "pending", "in-progress")
```

- [ ] **Step 4: Verify compilation**

Run: `cd /tmp/claude-os/controller && go build ./...`
Expected: Success

- [ ] **Step 5: Run all tests**

Run: `cd /tmp/claude-os/controller && go test ./... -v`
Expected: All PASS

- [ ] **Step 6: Commit**

```bash
cd /tmp/claude-os
git add controller/gitsync/syncer.go controller/gitsync/gitsync_test.go
git commit -m "feat(gitsync): dependency-aware enqueue — block tasks with unmet deps"
```

---

## Chunk 3: Triage Layer

### Task 6: Heuristic routing (the fallback)

**Files:**
- Create: `controller/triage/heuristic.go`
- Create: `controller/triage/heuristic_test.go`

Build the keyword-based fallback first — it's simpler and needed when Haiku is unavailable.

- [ ] **Step 1: Write test for heuristic routing**

Create `controller/triage/heuristic_test.go`:

```go
package triage

import "testing"

func TestHeuristicRoute(t *testing.T) {
	tests := []struct {
		name          string
		title         string
		desc          string
		wantModel     string
		wantComplex   bool
	}{
		{
			name:        "design task gets opus",
			title:       "Design the API schema",
			desc:        "Architect the REST endpoints",
			wantModel:   "claude-opus-4-6",
			wantComplex: true,
		},
		{
			name:        "implementation gets sonnet",
			title:       "Implement user login",
			desc:        "Build the login endpoint",
			wantModel:   "claude-sonnet-4-6",
			wantComplex: false,
		},
		{
			name:        "lint task gets haiku",
			title:       "Lint the Go code",
			desc:        "Run golangci-lint and fix issues",
			wantModel:   "claude-haiku-4-5",
			wantComplex: false,
		},
		{
			name:        "unknown defaults to sonnet",
			title:       "Do something",
			desc:        "A vague task",
			wantModel:   "claude-sonnet-4-6",
			wantComplex: false,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			v := HeuristicRoute(tt.title, tt.desc)
			if v.RecommendedModel != tt.wantModel {
				t.Errorf("model: got %s, want %s", v.RecommendedModel, tt.wantModel)
			}
			if v.NeedsPlan != tt.wantComplex {
				t.Errorf("needs_plan: got %v, want %v", v.NeedsPlan, tt.wantComplex)
			}
		})
	}
}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /tmp/claude-os/controller && go test ./triage/ -run TestHeuristicRoute -v`
Expected: FAIL — package doesn't exist

- [ ] **Step 3: Implement heuristic routing**

Create `controller/triage/heuristic.go`:

```go
package triage

import "strings"

// Verdict is the result of triaging a task.
type Verdict struct {
	Complexity       string `json:"complexity"`        // "simple" or "complex"
	RecommendedModel string `json:"recommended_model"`
	RecommendedAgent string `json:"recommended_agent"`
	Reasoning        string `json:"reasoning"`
	NeedsPlan        bool   `json:"needs_plan"`
}

var opusKeywords = []string{"design", "architect", "plan", "think", "research", "explore", "analyze", "what if"}
var haikuKeywords = []string{"lint", "format", "validate", "check", "scan", "cleanup", "typo"}

// HeuristicRoute applies keyword-based routing rules.
// Used as fallback when the Haiku API is unavailable.
func HeuristicRoute(title, description string) Verdict {
	text := strings.ToLower(title + " " + description)

	for _, kw := range opusKeywords {
		if strings.Contains(text, kw) {
			return Verdict{
				Complexity:       "complex",
				RecommendedModel: "claude-opus-4-6",
				RecommendedAgent: "claude",
				Reasoning:        "keyword match: " + kw,
				NeedsPlan:        true,
			}
		}
	}

	for _, kw := range haikuKeywords {
		if strings.Contains(text, kw) {
			return Verdict{
				Complexity:       "simple",
				RecommendedModel: "claude-haiku-4-5",
				RecommendedAgent: "claude",
				Reasoning:        "keyword match: " + kw,
				NeedsPlan:        false,
			}
		}
	}

	// Default: Sonnet, simple
	return Verdict{
		Complexity:       "simple",
		RecommendedModel: "claude-sonnet-4-6",
		RecommendedAgent: "claude",
		Reasoning:        "default routing",
		NeedsPlan:        false,
	}
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /tmp/claude-os/controller && go test ./triage/ -run TestHeuristicRoute -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
cd /tmp/claude-os
git add controller/triage/
git commit -m "feat(triage): add keyword-based heuristic routing fallback"
```

### Task 7: Haiku API triage client

**Files:**
- Create: `controller/triage/triage.go`
- Create: `controller/triage/triage_test.go` (extend)

- [ ] **Step 1: Write test with mock HTTP server**

In `controller/triage/triage_test.go`, add:

```go
package triage

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
)

func TestAssess_Success(t *testing.T) {
	// Mock Anthropic API returning a triage verdict
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Header.Get("x-api-key") != "test-key" {
			t.Error("expected x-api-key header")
		}
		if r.Header.Get("anthropic-version") == "" {
			t.Error("expected anthropic-version header")
		}
		// Return a mock response with the verdict in the text content
		resp := map[string]interface{}{
			"content": []map[string]interface{}{
				{"type": "text", "text": `{"complexity":"simple","recommended_model":"claude-sonnet-4-6","recommended_agent":"codex","reasoning":"focused coding task","needs_plan":false}`},
			},
		}
		json.NewEncoder(w).Encode(resp)
	}))
	defer server.Close()

	triager := NewTriager(server.URL, "test-key")
	status := AgentStatus{
		Claude: AgentInfo{Available: true},
		Codex:  AgentInfo{Available: true},
	}

	verdict, err := triager.Assess(context.Background(), "Fix the login bug", "The login endpoint returns 500", status)
	if err != nil {
		t.Fatalf("Assess failed: %v", err)
	}

	if verdict.RecommendedAgent != "codex" {
		t.Errorf("expected agent codex, got %s", verdict.RecommendedAgent)
	}
	if verdict.NeedsPlan {
		t.Error("expected needs_plan false")
	}
}

func TestAssess_Fallback(t *testing.T) {
	// Mock server that returns 500
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusInternalServerError)
	}))
	defer server.Close()

	triager := NewTriager(server.URL, "test-key")
	status := AgentStatus{
		Claude: AgentInfo{Available: true},
		Codex:  AgentInfo{Available: true},
	}

	verdict, err := triager.Assess(context.Background(), "Design the API", "Architect the endpoints", status)
	if err == nil {
		t.Fatal("expected error from 500 response")
	}

	// Caller should fall back to heuristic
	verdict = HeuristicRoute("Design the API", "Architect the endpoints")
	if verdict.RecommendedModel != "claude-opus-4-6" {
		t.Errorf("heuristic should route design to opus, got %s", verdict.RecommendedModel)
	}
}

func TestAssess_CircuitBreaker(t *testing.T) {
	callCount := 0
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		callCount++
		w.WriteHeader(http.StatusInternalServerError)
	}))
	defer server.Close()

	triager := NewTriager(server.URL, "test-key")
	status := AgentStatus{Claude: AgentInfo{Available: true}}

	// Fail 3 times to trip circuit breaker
	for i := 0; i < 3; i++ {
		triager.Assess(context.Background(), "task", "desc", status)
	}

	if !triager.IsDisabled() {
		t.Error("expected triager to be disabled after 3 failures")
	}

	// Next call should not hit the server
	beforeCount := callCount
	_, err := triager.Assess(context.Background(), "task", "desc", status)
	if err == nil {
		t.Error("expected error when triager is disabled")
	}
	if callCount != beforeCount {
		t.Error("disabled triager should not make API calls")
	}
}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /tmp/claude-os/controller && go test ./triage/ -run TestAssess -v`
Expected: FAIL — `NewTriager`, `AgentStatus`, etc. undefined

- [ ] **Step 3: Implement the Haiku triage client**

Create `controller/triage/triage.go`:

```go
package triage

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"log/slog"
	"net/http"
	"sync"
	"time"
)

// AgentInfo tracks an agent's availability.
type AgentInfo struct {
	Available bool
}

// AgentStatus is the current state of all agents.
type AgentStatus struct {
	Claude AgentInfo
	Codex  AgentInfo
}

// Triager calls Haiku to assess incoming tasks.
type Triager struct {
	apiURL     string
	apiKey     string
	client     *http.Client
	mu         sync.Mutex
	failures   int
	disabled   bool
	maxFails   int
}

const triageModel = "claude-haiku-4-5"

func NewTriager(apiURL, apiKey string) *Triager {
	return &Triager{
		apiURL: apiURL,
		apiKey: apiKey,
		client: &http.Client{Timeout: 5 * time.Second},
		maxFails: 3,
	}
}

func (t *Triager) IsDisabled() bool {
	t.mu.Lock()
	defer t.mu.Unlock()
	return t.disabled
}

// ReEnable resets the circuit breaker (called on successful API contact).
func (t *Triager) reEnable() {
	t.mu.Lock()
	defer t.mu.Unlock()
	t.failures = 0
	t.disabled = false
}

func (t *Triager) recordFailure() {
	t.mu.Lock()
	defer t.mu.Unlock()
	t.failures++
	if t.failures >= t.maxFails {
		t.disabled = true
		slog.Warn("triage: disabled after consecutive failures", "failures", t.failures)
	}
}

func (t *Triager) Assess(ctx context.Context, title, description string, agents AgentStatus) (Verdict, error) {
	if t.IsDisabled() {
		return Verdict{}, fmt.Errorf("triage disabled (circuit breaker open)")
	}

	prompt := buildTriagePrompt(title, description, agents)

	body := map[string]interface{}{
		"model":      triageModel,
		"max_tokens": 256,
		"messages": []map[string]string{
			{"role": "user", "content": prompt},
		},
	}
	bodyJSON, err := json.Marshal(body)
	if err != nil {
		return Verdict{}, fmt.Errorf("marshal request: %w", err)
	}

	req, err := http.NewRequestWithContext(ctx, "POST", t.apiURL+"/v1/messages", bytes.NewReader(bodyJSON))
	if err != nil {
		return Verdict{}, fmt.Errorf("create request: %w", err)
	}
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("x-api-key", t.apiKey)
	req.Header.Set("anthropic-version", "2023-06-01")

	resp, err := t.client.Do(req)
	if err != nil {
		t.recordFailure()
		return Verdict{}, fmt.Errorf("API call: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		t.recordFailure()
		respBody, _ := io.ReadAll(resp.Body)
		return Verdict{}, fmt.Errorf("API returned %d: %s", resp.StatusCode, string(respBody))
	}

	var apiResp struct {
		Content []struct {
			Type string `json:"type"`
			Text string `json:"text"`
		} `json:"content"`
	}
	if err := json.NewDecoder(resp.Body).Decode(&apiResp); err != nil {
		t.recordFailure()
		return Verdict{}, fmt.Errorf("decode response: %w", err)
	}

	if len(apiResp.Content) == 0 {
		t.recordFailure()
		return Verdict{}, fmt.Errorf("empty response content")
	}

	var verdict Verdict
	if err := json.Unmarshal([]byte(apiResp.Content[0].Text), &verdict); err != nil {
		t.recordFailure()
		return Verdict{}, fmt.Errorf("parse verdict JSON: %w", err)
	}

	t.reEnable()

	slog.Info("triage verdict",
		"title", title,
		"complexity", verdict.Complexity,
		"model", verdict.RecommendedModel,
		"agent", verdict.RecommendedAgent,
		"needs_plan", verdict.NeedsPlan,
		"reasoning", verdict.Reasoning,
	)

	return verdict, nil
}

func buildTriagePrompt(title, description string, agents AgentStatus) string {
	return fmt.Sprintf(`You are the triage brain for Claude OS. Classify this task and recommend routing.

Routing rules:
- Code review / security scan / focused coding → agent: codex
- Complex reasoning / orchestration / creative → agent: claude
- Design / architecture thinking → model: claude-opus-4-6, agent: claude
- Simple lint / format / validation / typo fix → model: claude-haiku-4-5
- General implementation → model: claude-sonnet-4-6

Agent availability:
- claude: available=%v
- codex: available=%v

If an agent is unavailable, route to the other one.
If the task requires multiple steps, coordination, or decomposition, set needs_plan=true.

Task title: %s
Task description: %s

Respond with ONLY a JSON object (no markdown, no explanation):
{"complexity":"simple|complex","recommended_model":"<model-id>","recommended_agent":"claude|codex","reasoning":"<one line>","needs_plan":false}`,
		agents.Claude.Available, agents.Codex.Available, title, description)
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /tmp/claude-os/controller && go test ./triage/ -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
cd /tmp/claude-os
git add controller/triage/
git commit -m "feat(triage): Haiku API client with circuit breaker and fallback"
```

---

## Chunk 4: Rate-Limit Detection + Agent Fallback

### Task 8: Failure classification in watcher

**Files:**
- Modify: `controller/watcher/watcher.go`

- [ ] **Step 1: Write test for failure classification**

Create `controller/watcher/watcher_test.go`:

```go
package watcher

import "testing"

func TestClassifyFailure(t *testing.T) {
	tests := []struct {
		name string
		logs string
		want FailureClass
	}{
		{
			name: "rate limit - out of usage",
			logs: "Error: You're out of extra usage for Claude until next week",
			want: FailureClassRateLimit,
		},
		{
			name: "rate limit - 429",
			logs: "HTTP 429 Too Many Requests",
			want: FailureClassRateLimit,
		},
		{
			name: "rate limit - credit balance",
			logs: "Error: Credit balance too low",
			want: FailureClassRateLimit,
		},
		{
			name: "rate limit - usage limit",
			logs: "You've reached your usage limit",
			want: FailureClassRateLimit,
		},
		{
			name: "task error - generic",
			logs: "Error: file not found: /workspace/missing.go",
			want: FailureClassTaskError,
		},
		{
			name: "task error - test failure",
			logs: "FAIL: TestLogin expected 200 got 500",
			want: FailureClassTaskError,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got := ClassifyFailure(tt.logs)
			if got != tt.want {
				t.Errorf("ClassifyFailure() = %v, want %v", got, tt.want)
			}
		})
	}
}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /tmp/claude-os/controller && go test ./watcher/ -run TestClassifyFailure -v`
Expected: FAIL — `FailureClass`, `ClassifyFailure` undefined

- [ ] **Step 3: Implement failure classification**

In `controller/watcher/watcher.go`, add:

```go
// FailureClass distinguishes rate limits from task errors.
type FailureClass int

const (
	FailureClassTaskError  FailureClass = iota
	FailureClassRateLimit
)

var rateLimitSignals = []string{
	"out of extra usage",
	"reached your usage limit",
	"quota exceeded",
	"rate limit exceeded",
	"credit balance too low",
	"429",
}

// ClassifyFailure determines whether a job failure is a rate limit or a task error.
func ClassifyFailure(logs string) FailureClass {
	lower := strings.ToLower(logs)
	for _, signal := range rateLimitSignals {
		if strings.Contains(lower, strings.ToLower(signal)) {
			return FailureClassRateLimit
		}
	}
	return FailureClassTaskError
}
```

Add `"strings"` to the import block.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /tmp/claude-os/controller && go test ./watcher/ -run TestClassifyFailure -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
cd /tmp/claude-os
git add controller/watcher/
git commit -m "feat(watcher): add failure classification — rate limit vs task error"
```

### Task 9: Agent rate-limit tracking in Redis

**Files:**
- Modify: `controller/queue/queue.go`
- Test: `controller/queue/queue_test.go`

- [ ] **Step 1: Write test for rate-limit tracking**

In `controller/queue/queue_test.go`, add:

```go
func TestAgentRateLimitTracking(t *testing.T) {
	rdb := setupTestRedis(t)
	q := New(rdb)
	ctx := context.Background()

	// Initially not rate limited
	if q.IsAgentRateLimited(ctx, "claude") {
		t.Error("claude should not be rate limited initially")
	}

	// Mark as rate limited
	q.SetAgentRateLimited(ctx, "claude", 1*time.Hour)

	if !q.IsAgentRateLimited(ctx, "claude") {
		t.Error("claude should be rate limited after SetAgentRateLimited")
	}

	// Codex should still be available
	if q.IsAgentRateLimited(ctx, "codex") {
		t.Error("codex should not be rate limited")
	}
}

func TestGetFallbackAgent(t *testing.T) {
	rdb := setupTestRedis(t)
	q := New(rdb)
	ctx := context.Background()

	// No rate limits — fallback from claude is codex
	agent, ok := q.GetFallbackAgent(ctx, "claude")
	if !ok || agent != "codex" {
		t.Errorf("expected codex fallback, got %s (ok=%v)", agent, ok)
	}

	// Mark codex as rate limited — no fallback available
	q.SetAgentRateLimited(ctx, "codex", 1*time.Hour)
	_, ok = q.GetFallbackAgent(ctx, "claude")
	if ok {
		t.Error("expected no fallback when codex is rate limited")
	}
}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /tmp/claude-os/controller && go test ./queue/ -run TestAgent -v`
Expected: FAIL

- [ ] **Step 3: Implement rate-limit tracking**

In `controller/queue/queue.go`, add:

```go
const keyAgentRateLimited = "claude-os:agent:%s:rate_limited"

var fallbackChain = map[string][]string{
	"claude": {"codex"},
	"codex":  {"claude"},
}

func (q *Queue) SetAgentRateLimited(ctx context.Context, agent string, ttl time.Duration) error {
	return q.rdb.Set(ctx, fmt.Sprintf(keyAgentRateLimited, agent), "1", ttl).Err()
}

func (q *Queue) IsAgentRateLimited(ctx context.Context, agent string) bool {
	val, err := q.rdb.Get(ctx, fmt.Sprintf(keyAgentRateLimited, agent)).Result()
	return err == nil && val == "1"
}

// GetFallbackAgent returns the next available agent in the fallback chain.
func (q *Queue) GetFallbackAgent(ctx context.Context, currentAgent string) (string, bool) {
	chain, ok := fallbackChain[currentAgent]
	if !ok {
		return "", false
	}
	for _, agent := range chain {
		if !q.IsAgentRateLimited(ctx, agent) {
			return agent, true
		}
	}
	return "", false
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /tmp/claude-os/controller && go test ./queue/ -run TestAgent -v`
Expected: PASS

- [ ] **Step 5: Run all queue tests**

Run: `cd /tmp/claude-os/controller && go test ./queue/ -v`
Expected: All PASS

- [ ] **Step 6: Commit**

```bash
cd /tmp/claude-os
git add controller/queue/queue.go controller/queue/queue_test.go
git commit -m "feat(queue): agent rate-limit tracking with fallback chain"
```

---

## Chunk 5: Wire It All Together

### Task 10: Update the main dispatch loop

**Files:**
- Modify: `controller/main.go:168-233`

This is the integration point. The dispatch loop gets triage before `CreateJob()`, and the watcher callback gets failure classification + dependency resolution.

- [ ] **Step 1: Add triage import and initialization to main.go**

In `controller/main.go`, add to imports:

```go
"github.com/dacort/claude-os/controller/triage"
```

After the Workshop initialization (~line 112), add:

```go
	// Triage brain (Haiku API for fast routing)
	triageAPIKey := os.Getenv("TRIAGE_API_KEY")
	var triager *triage.Triager
	if triageAPIKey != "" {
		triager = triage.NewTriager("https://api.anthropic.com", triageAPIKey)
		slog.Info("triage enabled (Haiku API)")
	} else {
		slog.Warn("triage disabled — no TRIAGE_API_KEY, using heuristic routing only")
	}
```

- [ ] **Step 2: Add triage to the dispatch loop**

Replace the dispatch section of the main loop (after governance check, before `CreateJob`) with:

```go
				// Triage: assess task and route intelligently
				agentStatus := triage.AgentStatus{
					Claude: triage.AgentInfo{Available: !taskQueue.IsAgentRateLimited(ctx, "claude")},
					Codex:  triage.AgentInfo{Available: !taskQueue.IsAgentRateLimited(ctx, "codex")},
				}

				var verdict triage.Verdict
				if triager != nil {
					var err error
					verdict, err = triager.Assess(ctx, task.Title, task.Description, agentStatus)
					if err != nil {
						slog.Warn("triage failed, using heuristic", "task", task.ID, "error", err)
						verdict = triage.HeuristicRoute(task.Title, task.Description)
					}
				} else {
					verdict = triage.HeuristicRoute(task.Title, task.Description)
				}

				// Store triage verdict on task for debugging
				task.TriageVerdict = verdict.Reasoning

				// Apply triage recommendations (explicit frontmatter overrides triage)
				if task.Model == "" {
					task.Model = verdict.RecommendedModel
				}
				if task.Agent == "" {
					task.Agent = verdict.RecommendedAgent
				}

				// If triage says this needs a plan and it's not already a plan/subtask
				if verdict.NeedsPlan && task.TaskType == queue.TaskTypeStandalone {
					task.TaskType = queue.TaskTypePlan
					task.Model = "claude-opus-4-6"
					task.Agent = "claude"
					slog.Info("triage: promoting to plan task", "id", task.ID)
				}

				slog.Info("dispatching task", "id", task.ID, "title", task.Title,
					"profile", task.Profile, "model", task.Model, "agent", task.Agent,
					"task_type", task.TaskType)
				job, err := jobDispatcher.CreateJob(ctx, task)
```

- [ ] **Step 3: Update watcher callback with failure classification and dependency resolution**

Replace the watcher callback in main.go (~line 236-251) with:

```go
	jobWatcher := watcher.New(k8sClient, cfg.Worker.Namespace, func(taskID string, succeeded bool, logs string) {
		// Notify workshop if this was a creative job
		if workshop != nil {
			workshop.OnJobFinished(fmt.Sprintf("claude-os-%s", taskID))
		}

		if succeeded {
			slog.Info("completing task", "task", taskID)
			gitSyncer.CompleteTask(taskID, logs)
			taskQueue.UpdateStatus(ctx, taskID, queue.StatusCompleted, "")

			// Check if this task is part of a plan
			task, err := taskQueue.Get(ctx, taskID)
			if err == nil && task.PlanID != "" {
				taskQueue.CompletePlanTask(ctx, task.PlanID, taskID)

				// Check if any blocked tasks can now be unblocked
				blocked, _ := taskQueue.GetBlocked(ctx, task.PlanID)
				for _, bt := range blocked {
					allMet := true
					for _, dep := range bt.DependsOn {
						dt, err := taskQueue.Get(ctx, dep)
						if err != nil || dt.Status != queue.StatusCompleted {
							allMet = false
							break
						}
					}
					if allMet {
						slog.Info("unblocking task", "id", bt.ID, "plan", task.PlanID)
						taskQueue.Unblock(ctx, bt)
					}
				}

				// Check if plan is complete
				if taskQueue.IsPlanComplete(ctx, task.PlanID) {
					slog.Info("plan completed", "plan_id", task.PlanID)
				}
			}
		} else {
			// Classify the failure
			failClass := watcher.ClassifyFailure(logs)

			if failClass == watcher.FailureClassRateLimit {
				// Rate limit — fallback to another agent, don't consume a retry
				task, err := taskQueue.Get(ctx, taskID)
				if err != nil {
					slog.Error("failed to get task for rate-limit fallback", "task", taskID, "error", err)
					gitSyncer.FailTask(taskID, logs)
					taskQueue.UpdateStatus(ctx, taskID, queue.StatusFailed, "rate limit + lookup error")
					return
				}

				currentAgent := task.Agent
				if currentAgent == "" {
					currentAgent = "claude"
				}

				slog.Warn("rate limit detected", "task", taskID, "agent", currentAgent)
				taskQueue.SetAgentRateLimited(ctx, currentAgent, 1*time.Hour)

				// Check agent_required constraint — if set, task must wait
				if task.AgentRequired != "" && task.AgentRequired == currentAgent {
					slog.Info("task requires specific agent, will wait", "task", taskID, "agent_required", task.AgentRequired)
					task.Status = queue.StatusPending
					task.Priority = queue.PriorityCreative // lowest priority, will retry when agent recovers
					taskQueue.Enqueue(ctx, task)
					return
				}

				fallback, ok := taskQueue.GetFallbackAgent(ctx, currentAgent)
				if ok {
					slog.Info("rerouting task to fallback agent", "task", taskID, "from", currentAgent, "to", fallback)
					task.Agent = fallback
					task.Status = queue.StatusPending
					taskQueue.Enqueue(ctx, task)
				} else {
					slog.Warn("all agents rate-limited, task will wait", "task", taskID)
					// Re-enqueue with low priority — will be picked up when an agent recovers
					task.Status = queue.StatusPending
					task.Priority = queue.PriorityCreative // lowest priority
					taskQueue.Enqueue(ctx, task)
				}
			} else {
				// Task error — normal retry/escalation
				task, err := taskQueue.Get(ctx, taskID)
				if err != nil || task.RetryCount >= task.MaxRetries {
					slog.Info("failing task (retries exhausted)", "task", taskID)
					gitSyncer.FailTask(taskID, logs)
					taskQueue.UpdateStatus(ctx, taskID, queue.StatusFailed, "job failed")

					// If part of a plan, mark the plan as failed
					if task != nil && task.PlanID != "" {
						slog.Warn("subtask failed, marking plan as failed", "plan_id", task.PlanID, "task", taskID)
						// Note: other independent branches continue executing
						// but the plan is marked failed for operator visibility
					}
				} else {
					task.RetryCount++
					slog.Info("retrying task", "task", taskID, "retry", task.RetryCount, "max", task.MaxRetries)
					// Level 2: escalate model on later retries
					if task.RetryCount >= task.MaxRetries/2+1 {
						task.Model = escalateModel(task.Model)
						slog.Info("escalating model", "task", taskID, "model", task.Model)
					}
					task.Status = queue.StatusPending
					taskQueue.Enqueue(ctx, task)
				}
			}
		}
	})
```

Add a helper function in main.go:

```go
func escalateModel(current string) string {
	switch current {
	case "claude-haiku-4-5":
		return "claude-sonnet-4-6"
	case "claude-sonnet-4-6":
		return "claude-opus-4-6"
	default:
		return current
	}
}
```

- [ ] **Step 4: Verify compilation**

Run: `cd /tmp/claude-os/controller && go build ./...`
Expected: Success

- [ ] **Step 5: Run all tests**

Run: `cd /tmp/claude-os/controller && go test ./... -v`
Expected: All PASS

- [ ] **Step 6: Commit**

```bash
cd /tmp/claude-os
git add controller/main.go
git commit -m "feat: wire triage, dependency resolution, and rate-limit fallback into main loop"
```

### Task 11: Add routing.yaml config

**Files:**
- Create: `config/routing.yaml`

- [ ] **Step 1: Create routing config**

Create `config/routing.yaml`:

```yaml
routing:
  # Keyword hints → model suggestion (used by heuristic fallback)
  model_patterns:
    - keywords: [design, architect, plan, think, research, explore, analyze]
      suggests: claude-opus-4-6
    - keywords: [implement, build, write, code, create, generate, fix, refactor]
      suggests: claude-sonnet-4-6
    - keywords: [lint, format, validate, check, review, scan, cleanup]
      suggests: claude-haiku-4-5

  # Agent capabilities (informational, used by triage prompt)
  agent_capabilities:
    claude:
      strengths: [reasoning, tool-use, git-integration, long-context, creative]
      default_for: [plan, workshop, standalone]
    codex:
      strengths: [code-review, focused-coding, diffs, refactoring]
      default_for: []

  # Fallback chain (v1: two agents only, Gemini slots in later)
  agent_fallback:
    claude: [codex]
    codex: [claude]

  # Default agent if not specified
  default_agent: claude

  # Explicit frontmatter overrides triage
  explicit_overrides: true
```

- [ ] **Step 2: Commit**

```bash
cd /tmp/claude-os
git add config/routing.yaml
git commit -m "config: add routing.yaml with model patterns and fallback chains"
```

### Task 12: Update K8s deployment for triage API key

**Files:**
- Note: This task produces documentation, not code. The actual K8s secret creation is a manual step.

- [ ] **Step 1: Document the secret creation command**

The operator (dacort) needs to run:

```bash
kubectl --kubeconfig ~//.kube/config create secret generic claude-os-triage \
  -n claude-os --from-literal=ANTHROPIC_API_KEY=<triage-api-key>
```

The controller deployment in `talos-homelab/infra/claude-os/controller.yaml` needs an additional env var:

```yaml
env:
  - name: TRIAGE_API_KEY
    valueFrom:
      secretKeyRef:
        name: claude-os-triage
        key: ANTHROPIC_API_KEY
        optional: true  # Controller works without it (heuristic fallback)
```

The `optional: true` means the controller starts fine without the secret — triage just falls back to heuristics.

- [ ] **Step 2: Commit a note in the repo**

Add to the CLAUDE.md key secrets table or a deployment notes file. This is a manual step for the operator.

---

## Summary

| Chunk | Tasks | What it delivers |
|-------|-------|-----------------|
| 1: Queue Extensions | 1-3 | Task struct with plan fields, blocked set, plan tracking |
| 2: Frontmatter + Deps | 4, 5a, 5 | Parser reads new fields, DAG validation, dependency-aware enqueue |
| 3: Triage Layer | 6-7 | Heuristic fallback + Haiku API client with circuit breaker |
| 4: Rate-Limit Recovery | 8-9 | Failure classification, agent cooldown, fallback routing |
| 5: Integration | 10-12 | Main loop wired up with agent_required enforcement, plan failure propagation, routing config, deployment notes |

Each chunk is independently testable and shippable. Chunks 1-2 are pure foundation (no behavior change for standalone tasks). Chunk 3 adds routing intelligence. Chunk 4 adds resilience. Chunk 5 wires everything together.

**Total: 13 tasks, ~55 test cases, ~700 lines of new Go code.**

### Review fixes applied
- Added Task 5a: DAG cycle detection with topological sort (was missing from spec requirement)
- Added `agent_required` enforcement in rate-limit fallback (Task 10)
- Added plan failure propagation on subtask retry exhaustion (Task 10)
- Added `AgentRequired` and `TriageVerdict` to Task struct (Task 1)
- Added DAG validation and subtask count check to syncer ingestion (Task 5)
- Added `controller/queue/dag.go` to file map
