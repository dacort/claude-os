// Package scheduler manages cron-based recurring tasks for Claude OS.
//
// Scheduled tasks live in tasks/scheduled/ with a "schedule" field in their
// YAML frontmatter (standard 5-field cron expression, UTC). The scheduler
// ticks every 60 seconds, checks which tasks are due, and enqueues copies
// into the normal task queue. It prevents stacking (no new run if the
// previous one is still going) and respects governance token budgets.
package scheduler

import (
	"context"
	"fmt"
	"log/slog"
	"strings"
	"sync"
	"time"

	"github.com/redis/go-redis/v9"
	"github.com/robfig/cron/v3"
)

// Redis key templates for scheduled task state.
const (
	keyNextRun = "claude-os:scheduled:%s:next_run"
	keyLastRun = "claude-os:scheduled:%s:last_run"
	keyRunning = "claude-os:scheduled:%s:running"
)

// ScheduledTask holds the parsed definition of a recurring task.
type ScheduledTask struct {
	ID            string
	Schedule      string // 5-field cron expression
	Profile       string
	Priority      string
	Title         string
	Description   string
	TargetRepo    string
	Agent         string
	Model         string
	Mode          string
	ContextRefs   []string
	MaxConcurrent int // don't stack if previous run still going (default 1)
}

// EnqueueFunc is called by the scheduler to enqueue a spawned task copy.
// The scheduler creates a unique task ID and passes the full task definition.
type EnqueueFunc func(ctx context.Context, task SpawnedTask) error

// GovernanceCheck returns (allowed, reason). If !allowed, the scheduler
// skips this run cycle.
type GovernanceCheck func(ctx context.Context, priority string) (bool, string)

// SpawnedTask is the task copy that gets enqueued for a single run.
type SpawnedTask struct {
	ID          string
	ParentID    string // the scheduled task ID
	Title       string
	Description string
	TargetRepo  string
	Profile     string
	Agent       string
	Model       string
	Mode        string
	Priority    string
	ContextRefs []string
}

// Scheduler manages cron-based recurring tasks.
type Scheduler struct {
	rdb        *redis.Client
	enqueue    EnqueueFunc
	governance GovernanceCheck
	parser     cron.Parser

	mu    sync.Mutex
	tasks map[string]*ScheduledTask // keyed by task ID
}

// New creates a scheduler. The enqueue function is called to dispatch task
// copies into the normal queue. The governance function checks token budgets.
func New(rdb *redis.Client, enqueue EnqueueFunc, governance GovernanceCheck) *Scheduler {
	return &Scheduler{
		rdb:        rdb,
		enqueue:    enqueue,
		governance: governance,
		parser:     cron.NewParser(cron.Minute | cron.Hour | cron.Dom | cron.Month | cron.Dow),
		tasks:      make(map[string]*ScheduledTask),
	}
}

// Register adds or updates a scheduled task. Idempotent — safe to call on
// every git sync. Calculates and stores the next run time if not already set.
func (s *Scheduler) Register(ctx context.Context, task *ScheduledTask) error {
	if task.MaxConcurrent <= 0 {
		task.MaxConcurrent = 1
	}

	// Validate the cron expression
	if _, err := s.parser.Parse(task.Schedule); err != nil {
		return fmt.Errorf("invalid cron expression %q for task %s: %w", task.Schedule, task.ID, err)
	}

	s.mu.Lock()
	s.tasks[task.ID] = task
	s.mu.Unlock()

	// Set next_run if not already present
	key := fmt.Sprintf(keyNextRun, task.ID)
	exists, err := s.rdb.Exists(ctx, key).Result()
	if err != nil {
		return fmt.Errorf("check next_run for %s: %w", task.ID, err)
	}
	if exists == 0 {
		next, err := s.NextRun(task.Schedule, time.Now().UTC())
		if err != nil {
			return err
		}
		if err := s.rdb.Set(ctx, key, next.Unix(), 0).Err(); err != nil {
			return fmt.Errorf("set next_run for %s: %w", task.ID, err)
		}
		slog.Info("scheduler: registered task", "id", task.ID, "schedule", task.Schedule, "next_run", next)
	} else {
		slog.Debug("scheduler: task already registered", "id", task.ID)
	}

	return nil
}

// Deregister removes a scheduled task and cleans up its Redis state.
func (s *Scheduler) Deregister(ctx context.Context, taskID string) error {
	s.mu.Lock()
	delete(s.tasks, taskID)
	s.mu.Unlock()

	pipe := s.rdb.Pipeline()
	pipe.Del(ctx, fmt.Sprintf(keyNextRun, taskID))
	pipe.Del(ctx, fmt.Sprintf(keyLastRun, taskID))
	pipe.Del(ctx, fmt.Sprintf(keyRunning, taskID))
	_, err := pipe.Exec(ctx)
	if err != nil {
		return fmt.Errorf("deregister %s: %w", taskID, err)
	}
	slog.Info("scheduler: deregistered task", "id", taskID)
	return nil
}

// Tick checks all registered tasks and enqueues any that are due.
// Called every 60 seconds from the main loop.
func (s *Scheduler) Tick(ctx context.Context) {
	s.mu.Lock()
	// Snapshot the task list so we don't hold the lock during enqueue.
	tasks := make([]*ScheduledTask, 0, len(s.tasks))
	for _, t := range s.tasks {
		tasks = append(tasks, t)
	}
	s.mu.Unlock()

	now := time.Now().UTC()

	for _, task := range tasks {
		if err := s.maybeEnqueue(ctx, task, now); err != nil {
			slog.Error("scheduler: tick error", "task", task.ID, "error", err)
		}
	}
}

func (s *Scheduler) maybeEnqueue(ctx context.Context, task *ScheduledTask, now time.Time) error {
	// Check if a previous run is still going
	running, err := s.IsRunning(ctx, task.ID)
	if err != nil {
		return fmt.Errorf("check running for %s: %w", task.ID, err)
	}
	if running {
		slog.Debug("scheduler: skipping (still running)", "task", task.ID)
		return nil
	}

	// Check next_run
	nextRunKey := fmt.Sprintf(keyNextRun, task.ID)
	nextUnix, err := s.rdb.Get(ctx, nextRunKey).Int64()
	if err != nil {
		return fmt.Errorf("get next_run for %s: %w", task.ID, err)
	}

	nextRun := time.Unix(nextUnix, 0).UTC()
	if now.Before(nextRun) {
		return nil // not due yet
	}

	// Governance check
	priority := task.Priority
	if priority == "" {
		priority = "normal"
	}
	if s.governance != nil {
		allowed, reason := s.governance(ctx, priority)
		if !allowed {
			slog.Info("scheduler: skipping (governance)", "task", task.ID, "reason", reason)
			return nil
		}
	}

	// Generate spawned task ID: <base-id>-<YYYYMMDD-HHMMSS>
	spawnedID := SpawnedTaskID(task.ID, now)

	spawned := SpawnedTask{
		ID:          spawnedID,
		ParentID:    task.ID,
		Title:       task.Title,
		Description: task.Description,
		TargetRepo:  task.TargetRepo,
		Profile:     task.Profile,
		Agent:       task.Agent,
		Model:       task.Model,
		Mode:        task.Mode,
		Priority:    priority,
		ContextRefs: task.ContextRefs,
	}

	if err := s.enqueue(ctx, spawned); err != nil {
		return fmt.Errorf("enqueue spawned task %s: %w", spawnedID, err)
	}

	// Mark as running and update timestamps
	pipe := s.rdb.Pipeline()
	pipe.Set(ctx, fmt.Sprintf(keyRunning, task.ID), "1", 0)
	pipe.Set(ctx, fmt.Sprintf(keyLastRun, task.ID), now.Unix(), 0)

	// Calculate next run from now (no backfill)
	next, err := s.NextRun(task.Schedule, now)
	if err != nil {
		slog.Error("scheduler: failed to calculate next run", "task", task.ID, "error", err)
	} else {
		pipe.Set(ctx, nextRunKey, next.Unix(), 0)
	}

	if _, err := pipe.Exec(ctx); err != nil {
		return fmt.Errorf("update state for %s: %w", task.ID, err)
	}

	slog.Info("scheduler: enqueued run",
		"task", task.ID, "spawned_id", spawnedID,
		"next_run", next,
	)
	return nil
}

// OnTaskCompleted is called by the watcher when a spawned task finishes.
// It clears the running flag so the next run can proceed.
func (s *Scheduler) OnTaskCompleted(ctx context.Context, taskID string) {
	parentID := ParentTaskID(taskID)
	if parentID == "" {
		return // not a spawned scheduled task
	}

	s.mu.Lock()
	_, isScheduled := s.tasks[parentID]
	s.mu.Unlock()

	if !isScheduled {
		return
	}

	key := fmt.Sprintf(keyRunning, parentID)
	if err := s.rdb.Del(ctx, key).Err(); err != nil {
		slog.Error("scheduler: failed to clear running flag", "parent", parentID, "task", taskID, "error", err)
		return
	}

	slog.Info("scheduler: cleared running flag", "parent", parentID, "completed_task", taskID)
}

// IsRunning returns true if a scheduled task has a run in progress.
func (s *Scheduler) IsRunning(ctx context.Context, taskID string) (bool, error) {
	val, err := s.rdb.Get(ctx, fmt.Sprintf(keyRunning, taskID)).Result()
	if err == redis.Nil {
		return false, nil
	}
	if err != nil {
		return false, err
	}
	return val == "1", nil
}

// NextRun calculates the next run time after `after` for the given cron expression.
// No backfill: always returns a future time.
func (s *Scheduler) NextRun(cronExpr string, after time.Time) (time.Time, error) {
	sched, err := s.parser.Parse(cronExpr)
	if err != nil {
		return time.Time{}, fmt.Errorf("parse cron %q: %w", cronExpr, err)
	}
	return sched.Next(after), nil
}

// RegisteredTaskIDs returns the IDs of all currently registered scheduled tasks.
func (s *Scheduler) RegisteredTaskIDs() []string {
	s.mu.Lock()
	defer s.mu.Unlock()
	ids := make([]string, 0, len(s.tasks))
	for id := range s.tasks {
		ids = append(ids, id)
	}
	return ids
}

// SpawnedTaskID generates a unique task ID for a scheduled run.
// Format: <base-id>-<YYYYMMDD-HHMMSS>
func SpawnedTaskID(baseID string, t time.Time) string {
	return fmt.Sprintf("%s-%s", baseID, t.UTC().Format("20060102-150405"))
}

// ParentTaskID extracts the parent scheduled task ID from a spawned task ID.
// Returns "" if the ID doesn't match the spawned format (8 digits, dash, 6 digits suffix).
func ParentTaskID(spawnedID string) string {
	// Spawned IDs end with -YYYYMMDD-HHMMSS (16 chars including the leading dash)
	// We need to find the pattern: -\d{8}-\d{6} at the end
	if len(spawnedID) < 16 {
		return ""
	}

	suffix := spawnedID[len(spawnedID)-15:] // YYYYMMDD-HHMMSS
	parts := strings.SplitN(suffix, "-", 2)
	if len(parts) != 2 || len(parts[0]) != 8 || len(parts[1]) != 6 {
		return ""
	}

	// Verify they're all digits
	for _, c := range parts[0] + parts[1] {
		if c < '0' || c > '9' {
			return ""
		}
	}

	// The parent ID is everything before the timestamp suffix
	// (minus the dash separator before the date)
	return spawnedID[:len(spawnedID)-16]
}
