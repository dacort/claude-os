package queue

import (
	"context"
	"encoding/json"
	"fmt"
	"strings"
	"time"

	"github.com/redis/go-redis/v9"
)

type Status string

const (
	StatusPending   Status = "pending"
	StatusRunning   Status = "running"
	StatusCompleted Status = "completed"
	StatusFailed    Status = "failed"
	StatusBlocked   Status = "blocked"
)

type Priority int

const (
	PriorityCreative Priority = 0
	PriorityNormal   Priority = 10
	PriorityHigh     Priority = 20
)

type TaskType string

const (
	TaskTypeStandalone TaskType = "standalone"
	TaskTypeSubtask    TaskType = "subtask"
	TaskTypePlan       TaskType = "plan"
)

type Task struct {
	ID              string    `json:"id"`
	Title           string    `json:"title"`
	Description     string    `json:"description"`
	TargetRepo      string    `json:"target_repo"`
	Profile         string    `json:"profile"`
	Agent           string    `json:"agent,omitempty"`
	Model           string    `json:"model,omitempty"`
	Mode            string    `json:"mode,omitempty"`
	ContextRefs     []string  `json:"context_refs,omitempty"`
	Priority        Priority  `json:"priority"`
	Status          Status    `json:"status"`
	Result          string    `json:"result,omitempty"`
	CreatedAt       time.Time `json:"created_at"`
	StartedAt       time.Time `json:"started_at,omitempty"`
	FinishedAt      time.Time `json:"finished_at,omitempty"`
	TokensUsed      int64     `json:"tokens_used,omitempty"`
	DurationSeconds int64     `json:"duration_seconds,omitempty"`
	// Smart dispatch fields
	PlanID        string   `json:"plan_id,omitempty"`
	TaskType      TaskType `json:"task_type,omitempty"`
	DependsOn     []string `json:"depends_on,omitempty"`
	RetryCount    int      `json:"retry_count,omitempty"`
	MaxRetries    int      `json:"max_retries,omitempty"`
	AgentRequired string   `json:"agent_required,omitempty"`
	TriageVerdict string   `json:"triage_verdict,omitempty"`
}

// UsageRecord is the structured data emitted by the worker at the end of a job.
// The controller parses it from the pod logs and stores it on the task.
type UsageRecord struct {
	TaskID          string `json:"task_id"`
	Agent           string `json:"agent"`
	Profile         string `json:"profile"`
	DurationSeconds int64  `json:"duration_seconds"`
	ExitCode        int    `json:"exit_code"`
	FinishedAt      string `json:"finished_at"`
}

const (
	keyQueue         = "claude-os:queue"
	keyTask          = "claude-os:task:%s"
	keyRunning       = "claude-os:running"
	keyBlocked       = "claude-os:plan:%s:blocked"
	keyPlanTasks     = "claude-os:plan:%s:tasks"
	keyPlanCompleted = "claude-os:plan:%s:completed"
)

type Queue struct {
	rdb *redis.Client
}

func New(rdb *redis.Client) *Queue {
	return &Queue{rdb: rdb}
}

func (q *Queue) Enqueue(ctx context.Context, task *Task) error {
	if task.CreatedAt.IsZero() {
		task.CreatedAt = time.Now().UTC()
	}
	task.Status = StatusPending

	data, err := json.Marshal(task)
	if err != nil {
		return fmt.Errorf("marshal task: %w", err)
	}

	pipe := q.rdb.Pipeline()
	pipe.Set(ctx, fmt.Sprintf(keyTask, task.ID), data, 0)
	pipe.ZAdd(ctx, keyQueue, redis.Z{
		Score:  float64(task.Priority),
		Member: task.ID,
	})
	_, err = pipe.Exec(ctx)
	return err
}

func (q *Queue) Dequeue(ctx context.Context) (*Task, error) {
	results, err := q.rdb.ZRevRangeByScore(ctx, keyQueue, &redis.ZRangeBy{
		Min:   "-inf",
		Max:   "+inf",
		Count: 1,
	}).Result()
	if err != nil {
		return nil, fmt.Errorf("zrevrange: %w", err)
	}
	if len(results) == 0 {
		return nil, nil
	}

	taskID := results[0]
	removed, err := q.rdb.ZRem(ctx, keyQueue, taskID).Result()
	if err != nil {
		return nil, fmt.Errorf("zrem: %w", err)
	}
	if removed == 0 {
		return nil, nil
	}

	task, err := q.Get(ctx, taskID)
	if err != nil {
		return nil, err
	}

	task.Status = StatusRunning
	task.StartedAt = time.Now().UTC()

	pipe := q.rdb.Pipeline()
	data, err := json.Marshal(task)
	if err != nil {
		return nil, fmt.Errorf("marshal task: %w", err)
	}
	pipe.Set(ctx, fmt.Sprintf(keyTask, task.ID), data, 0)
	pipe.SAdd(ctx, keyRunning, task.ID)
	if _, err := pipe.Exec(ctx); err != nil {
		return nil, fmt.Errorf("dequeue pipeline: %w", err)
	}

	return task, nil
}

func (q *Queue) Get(ctx context.Context, id string) (*Task, error) {
	data, err := q.rdb.Get(ctx, fmt.Sprintf(keyTask, id)).Bytes()
	if err != nil {
		return nil, fmt.Errorf("get task %s: %w", id, err)
	}
	var task Task
	if err := json.Unmarshal(data, &task); err != nil {
		return nil, fmt.Errorf("unmarshal task: %w", err)
	}
	return &task, nil
}

func (q *Queue) UpdateStatus(ctx context.Context, id string, status Status, result string) error {
	task, err := q.Get(ctx, id)
	if err != nil {
		return err
	}
	task.Status = status
	task.Result = result
	if status == StatusCompleted || status == StatusFailed {
		task.FinishedAt = time.Now().UTC()
	}

	data, err := json.Marshal(task)
	if err != nil {
		return fmt.Errorf("marshal task: %w", err)
	}

	pipe := q.rdb.Pipeline()
	pipe.Set(ctx, fmt.Sprintf(keyTask, task.ID), data, 0)
	if status == StatusCompleted || status == StatusFailed {
		pipe.SRem(ctx, keyRunning, id)
	}
	_, err = pipe.Exec(ctx)
	return err
}

// RunningCount returns the number of tasks currently in StatusRunning.
func (q *Queue) RunningCount(ctx context.Context) (int64, error) {
	return q.rdb.SCard(ctx, keyRunning).Result()
}

// ListRunning returns the IDs of all tasks currently in StatusRunning.
func (q *Queue) ListRunning(ctx context.Context) ([]string, error) {
	return q.rdb.SMembers(ctx, keyRunning).Result()
}

// RequeueTasks moves a set of tasks from running back to pending.
// Used by the reconciler to recover tasks whose K8s jobs disappeared.
func (q *Queue) RequeueTasks(ctx context.Context, taskIDs []string) error {
	for _, id := range taskIDs {
		task, err := q.Get(ctx, id)
		if err != nil {
			return fmt.Errorf("get task %s for requeue: %w", id, err)
		}

		task.Status = StatusPending
		task.StartedAt = time.Time{}

		data, err := json.Marshal(task)
		if err != nil {
			return fmt.Errorf("marshal task %s: %w", id, err)
		}

		pipe := q.rdb.Pipeline()
		pipe.Set(ctx, fmt.Sprintf(keyTask, id), data, 0)
		pipe.SRem(ctx, keyRunning, id)
		pipe.ZAdd(ctx, keyQueue, redis.Z{
			Score:  float64(task.Priority),
			Member: id,
		})
		if _, err := pipe.Exec(ctx); err != nil {
			return fmt.Errorf("requeue pipeline for %s: %w", id, err)
		}
	}
	return nil
}

// SaveTask persists an updated Task struct. Used for in-place field updates
// (e.g. recording duration after a job completes) that don't go through
// UpdateStatus.
func (q *Queue) SaveTask(ctx context.Context, task *Task) error {
	return q.save(ctx, task)
}

// Block stores a task in the per-plan blocked set (not the dispatch queue).
// Tasks are blocked when their dependencies have not yet completed.
func (q *Queue) Block(ctx context.Context, task *Task) error {
	task.Status = StatusBlocked
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
	task.Status = StatusPending
	data, err := json.Marshal(task)
	if err != nil {
		return fmt.Errorf("marshal task: %w", err)
	}
	pipe := q.rdb.Pipeline()
	pipe.Set(ctx, fmt.Sprintf(keyTask, task.ID), data, 0)
	pipe.SRem(ctx, fmt.Sprintf(keyBlocked, task.PlanID), task.ID)
	pipe.ZAdd(ctx, keyQueue, redis.Z{
		Score:  float64(task.Priority),
		Member: task.ID,
	})
	_, err = pipe.Exec(ctx)
	return err
}

// RegisterPlanTask records a task as belonging to a plan.
// Must be called when a task is enqueued or blocked for the first time.
func (q *Queue) RegisterPlanTask(ctx context.Context, planID, taskID string) error {
	return q.rdb.SAdd(ctx, fmt.Sprintf(keyPlanTasks, planID), taskID).Err()
}

// CompletePlanTask marks a task within a plan as completed.
func (q *Queue) CompletePlanTask(ctx context.Context, planID, taskID string) error {
	return q.rdb.SAdd(ctx, fmt.Sprintf(keyPlanCompleted, planID), taskID).Err()
}

// PlanProgress returns the number of completed tasks and total tasks for a plan.
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

// IsPlanComplete returns true when every registered task in the plan has been completed.
func (q *Queue) IsPlanComplete(ctx context.Context, planID string) bool {
	done, total, err := q.PlanProgress(ctx, planID)
	if err != nil || total == 0 {
		return false
	}
	return done >= total
}

const keyAgentRateLimited = "claude-os:agent:%s:rate_limited"

var fallbackChain = map[string][]string{
	"claude": {"codex"},
	"codex":  {"claude"},
}

// SetAgentRateLimited marks an agent as rate-limited for the given duration.
func (q *Queue) SetAgentRateLimited(ctx context.Context, agent string, ttl time.Duration) error {
	return q.rdb.Set(ctx, fmt.Sprintf(keyAgentRateLimited, agent), "1", ttl).Err()
}

// IsAgentRateLimited returns true if the agent is currently rate-limited.
func (q *Queue) IsAgentRateLimited(ctx context.Context, agent string) bool {
	val, err := q.rdb.Get(ctx, fmt.Sprintf(keyAgentRateLimited, agent)).Result()
	return err == nil && val == "1"
}

// GetFallbackAgent returns the next available agent in the fallback chain.
// Returns ("", false) if all fallback agents are also rate-limited.
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

func (q *Queue) save(ctx context.Context, task *Task) error {
	data, err := json.Marshal(task)
	if err != nil {
		return fmt.Errorf("marshal task: %w", err)
	}
	return q.rdb.Set(ctx, fmt.Sprintf(keyTask, task.ID), data, 0).Err()
}

// TaskResult is the structured result emitted by workers using the new
// reporting contract (decision 002). Delimited by ===RESULT_START=== / ===RESULT_END===.
type TaskResult struct {
	Version    string           `json:"version"`
	TaskID     string           `json:"task_id"`
	Agent      string           `json:"agent"`
	Model      string           `json:"model"`
	Outcome    string           `json:"outcome"` // success | failure | partial
	Summary    string           `json:"summary"`
	Artifacts  []ResultArtifact `json:"artifacts"`
	Usage      ResultUsage      `json:"usage"`
	Failure    *ResultFailure   `json:"failure"`
	NextAction *ResultAction    `json:"next_action"`
}

type ResultArtifact struct {
	Type string `json:"type"` // commit | pr | decision | file
	Ref  string `json:"ref,omitempty"`
	URL  string `json:"url,omitempty"`
	Path string `json:"path,omitempty"`
}

type ResultUsage struct {
	TokensIn        int64 `json:"tokens_in"`
	TokensOut       int64 `json:"tokens_out"`
	DurationSeconds int64 `json:"duration_seconds"`
}

type ResultFailure struct {
	Reason    string `json:"reason"` // tests_failed | timeout | rate_limited | git_push_failed | context_error | agent_error
	Detail    string `json:"detail"`
	Retryable bool   `json:"retryable"`
}

type ResultAction struct {
	Type      string              `json:"type"` // await_reply | spawn_tasks
	Awaiting  string              `json:"awaiting,omitempty"`
	ThreadID  string              `json:"thread_id,omitempty"`
	Tasks     []ResultSpawnedTask `json:"tasks,omitempty"`
}

type ResultSpawnedTask struct {
	ID      string `json:"id"`
	Profile string `json:"profile"`
	Agent   string `json:"agent"`
}

// ParseResult extracts the structured TaskResult emitted by workers using
// the new reporting contract. Returns nil if the sentinel block is not found.
func ParseResult(logs string) *TaskResult {
	const startMarker = "===RESULT_START==="
	const endMarker = "===RESULT_END==="

	start := strings.Index(logs, startMarker)
	end := strings.LastIndex(logs, endMarker)
	if start == -1 || end == -1 || end <= start {
		return nil
	}

	raw := strings.TrimSpace(logs[start+len(startMarker) : end])
	var result TaskResult
	if err := json.Unmarshal([]byte(raw), &result); err != nil {
		return nil
	}
	return &result
}

// ParseUsage extracts the structured UsageRecord emitted by the worker at the
// end of each job. Returns nil if the sentinel block is not found.
// Deprecated: new workers emit TaskResult via ===RESULT_START===. This is
// kept for backward compatibility during the transition.
func ParseUsage(logs string) *UsageRecord {
	const startMarker = "=== CLAUDE_OS_USAGE ==="
	const endMarker = "=== END_CLAUDE_OS_USAGE ==="

	start := strings.Index(logs, startMarker)
	end := strings.LastIndex(logs, endMarker)
	if start == -1 || end == -1 || end <= start {
		return nil
	}

	raw := strings.TrimSpace(logs[start+len(startMarker) : end])
	// The block should be a single JSON line
	var rec UsageRecord
	if err := json.Unmarshal([]byte(raw), &rec); err != nil {
		return nil
	}
	return &rec
}
