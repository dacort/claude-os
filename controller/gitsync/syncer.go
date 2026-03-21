package gitsync

import (
	"context"
	"encoding/json"
	"fmt"
	"log/slog"
	"net/url"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"time"

	"github.com/dacort/claude-os/controller/queue"
	"github.com/dacort/claude-os/controller/scheduler"
)

type Syncer struct {
	repoURL    string
	branch     string
	localPath  string
	token      string
	queue      *queue.Queue
	knownTasks map[string]bool
	scheduler  *scheduler.Scheduler
}

func NewSyncer(repoURL, branch, localPath, token string, q *queue.Queue) *Syncer {
	return &Syncer{
		repoURL:    repoURL,
		branch:     branch,
		localPath:  localPath,
		token:      token,
		queue:      q,
		knownTasks: make(map[string]bool),
	}
}

// SetScheduler attaches a scheduler for syncing scheduled tasks.
// Must be called before the first Sync() if scheduled tasks should be picked up.
func (s *Syncer) SetScheduler(sched *scheduler.Scheduler) {
	s.scheduler = sched
}

// LocalPath returns the local clone directory path.
func (s *Syncer) LocalPath() string {
	return s.localPath
}

// CommitAndPush stages all changes, commits with the given message, and pushes.
func (s *Syncer) CommitAndPush(message string) error {
	return s.gitCommitAndPush(message)
}

// cloneURL returns the repo URL with embedded token for push access.
func (s *Syncer) cloneURL() string {
	if s.token == "" {
		return s.repoURL
	}
	u, err := url.Parse(s.repoURL)
	if err != nil {
		return s.repoURL
	}
	u.User = url.UserPassword("x-access-token", s.token)
	return u.String()
}

func (s *Syncer) Sync(ctx context.Context) error {
	if err := s.ensureClone(); err != nil {
		return fmt.Errorf("clone: %w", err)
	}
	if err := s.pull(); err != nil {
		return fmt.Errorf("pull: %w", err)
	}
	slog.Info("git sync completed, scanning for tasks")

	// Sync scheduled tasks (register/deregister with scheduler)
	if s.scheduler != nil {
		if err := s.syncScheduledTasks(ctx); err != nil {
			slog.Error("failed to sync scheduled tasks", "error", err)
		}
	}

	return s.syncPendingTasks(ctx)
}

// syncScheduledTasks scans tasks/scheduled/ and registers/deregisters tasks
// with the scheduler. Idempotent — safe to call on every sync cycle.
func (s *Syncer) syncScheduledTasks(ctx context.Context) error {
	tasksPath := filepath.Join(s.localPath, "tasks")
	scheduledFiles, err := ScanScheduledTasks(tasksPath)
	if err != nil {
		return fmt.Errorf("scan scheduled tasks: %w", err)
	}

	// Build set of task IDs found on disk
	foundIDs := make(map[string]bool)
	for _, tf := range scheduledFiles {
		taskID := strings.TrimSuffix(tf.Filename, ".md")
		foundIDs[taskID] = true

		st := &scheduler.ScheduledTask{
			ID:            taskID,
			Schedule:      tf.Schedule,
			Profile:       tf.Profile,
			Priority:      tf.Priority,
			Title:         tf.Title,
			Description:   tf.Description,
			TargetRepo:    tf.TargetRepo,
			Agent:         tf.Agent,
			Model:         tf.Model,
			Mode:          tf.Mode,
			ContextRefs:   tf.ContextRefs,
			MaxConcurrent: tf.MaxConcurrent,
		}
		if err := s.scheduler.Register(ctx, st); err != nil {
			slog.Error("failed to register scheduled task", "id", taskID, "error", err)
		}
	}

	// Deregister tasks that were removed from git
	for _, id := range s.scheduler.RegisteredTaskIDs() {
		if !foundIDs[id] {
			if err := s.scheduler.Deregister(ctx, id); err != nil {
				slog.Error("failed to deregister scheduled task", "id", id, "error", err)
			}
		}
	}

	if len(scheduledFiles) > 0 {
		slog.Info("scheduled tasks synced", "count", len(scheduledFiles))
	}
	return nil
}

func (s *Syncer) ensureClone() error {
	if _, err := os.Stat(filepath.Join(s.localPath, ".git")); err == nil {
		return nil
	}
	slog.Info("cloning repo", "url", s.repoURL, "path", s.localPath)
	cmd := exec.Command("git", "clone", "--branch", s.branch, "--single-branch", s.cloneURL(), s.localPath)
	cmd.Stdout = os.Stdout
	cmd.Stderr = os.Stderr
	return cmd.Run()
}

func (s *Syncer) pull() error {
	// Abort any stuck rebase from a previous failed sync
	if _, err := os.Stat(filepath.Join(s.localPath, ".git", "rebase-merge")); err == nil {
		slog.Warn("aborting stuck rebase-merge")
		abort := exec.Command("git", "rebase", "--abort")
		abort.Dir = s.localPath
		abort.CombinedOutput()
	}

	// Reset any uncommitted local changes before pulling
	// (task file moves may leave the index dirty if push failed)
	reset := exec.Command("git", "reset", "--hard", "HEAD")
	reset.Dir = s.localPath
	reset.CombinedOutput()

	clean := exec.Command("git", "clean", "-fd")
	clean.Dir = s.localPath
	clean.CombinedOutput()

	cmd := exec.Command("git",
		"-c", "user.name=Claude OS",
		"-c", "user.email=claude-os@noreply.github.com",
		"pull", "--rebase", "origin", s.branch)
	cmd.Dir = s.localPath
	output, err := cmd.CombinedOutput()
	if err != nil {
		return fmt.Errorf("git pull: %s: %w", string(output), err)
	}
	return nil
}

func (s *Syncer) syncPendingTasks(ctx context.Context) error {
	tasksPath := filepath.Join(s.localPath, "tasks")
	tasks, err := ScanPendingTasks(tasksPath)
	if err != nil {
		return err
	}

	slog.Info("found pending tasks", "count", len(tasks))
	for _, tf := range tasks {
		taskID := strings.TrimSuffix(tf.Filename, ".md")
		if s.knownTasks[taskID] {
			continue
		}

		priority := queue.PriorityNormal
		switch tf.Priority {
		case "high":
			priority = queue.PriorityHigh
		case "creative":
			priority = queue.PriorityCreative
		}

		task := &queue.Task{
			ID:            taskID,
			Title:         tf.Title,
			Description:   tf.Description,
			TargetRepo:    tf.TargetRepo,
			Profile:       tf.Profile,
			Agent:         tf.Agent,
			Model:         tf.Model,
			Mode:          tf.Mode,
			ContextRefs:   tf.ContextRefs,
			Priority:      priority,
			PlanID:        tf.PlanID,
			TaskType:      queue.TaskType(tf.TaskType),
			DependsOn:     tf.DependsOn,
			MaxRetries:    tf.MaxRetries,
			AgentRequired: tf.AgentRequired,
		}
		if task.MaxRetries == 0 {
			task.MaxRetries = 2 // default
		}
		if task.TaskType == "" {
			task.TaskType = queue.TaskTypeStandalone
		}

		// For plan subtasks, validate the DAG before enqueuing any of them.
		if task.PlanID != "" && task.TaskType == queue.TaskTypeSubtask {
			planTasks := s.collectPlanSubtasks(task.PlanID, tasksPath)
			// Include the current task in the DAG map.
			planTasks[taskID] = task.DependsOn

			if err := queue.ValidateSubtaskCount(planTasks, 10); err != nil {
				slog.Error("plan subtask count exceeded, skipping task",
					"plan", task.PlanID, "task", taskID, "error", err)
				continue
			}
			if err := queue.ValidateDAG(planTasks); err != nil {
				slog.Error("plan DAG invalid, skipping task",
					"plan", task.PlanID, "task", taskID, "error", err)
				continue
			}
		}

		// If any dependency is not yet completed, block this task instead of
		// enqueuing it. The watcher will unblock it when deps complete.
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
		if task.PlanID != "" {
			s.queue.RegisterPlanTask(ctx, task.PlanID, taskID)
		}
		slog.Info("enqueued task from git", "id", taskID, "title", tf.Title)

		if err := s.moveTask(tf.Filename, "pending", "in-progress"); err != nil {
			slog.Error("failed to move task to in-progress, will retry next sync",
				"id", taskID, "error", err)
			// Don't mark as known — retry on next sync cycle
			continue
		}
		s.knownTasks[taskID] = true
	}
	return nil
}

// collectPlanSubtasks returns a map of taskID -> depends_on for all pending
// subtasks belonging to planID. Used for DAG validation at ingestion time.
func (s *Syncer) collectPlanSubtasks(planID, tasksPath string) map[string][]string {
	result := make(map[string][]string)
	tasks, err := ScanAllTasks(tasksPath)
	if err != nil {
		return result
	}
	for _, tf := range tasks {
		if tf.PlanID == planID {
			taskID := strings.TrimSuffix(tf.Filename, ".md")
			result[taskID] = tf.DependsOn
		}
	}
	return result
}

func (s *Syncer) gitCommitAndPush(message string) error {
	// Stage and commit first — these don't need retry.
	stageCmds := [][]string{
		{"git", "add", "-A"},
		{"git", "-c", "user.name=Claude OS", "-c", "user.email=claude-os@noreply.github.com",
			"commit", "-m", message},
	}
	for _, args := range stageCmds {
		cmd := exec.Command(args[0], args[1:]...)
		cmd.Dir = s.localPath
		if output, err := cmd.CombinedOutput(); err != nil {
			return fmt.Errorf("%s: %s: %w", args[0], string(output), err)
		}
	}

	// Push with retry + rebase on conflict.
	// Races are rare but real: another controller instance or a manual push
	// can cause a non-fast-forward rejection. We pull --rebase then retry.
	const maxAttempts = 3
	for attempt := 1; attempt <= maxAttempts; attempt++ {
		pushCmd := exec.Command("git", "push", "origin", s.branch)
		pushCmd.Dir = s.localPath
		out, err := pushCmd.CombinedOutput()
		if err == nil {
			return nil
		}

		slog.Warn("git push failed, will retry",
			"attempt", attempt,
			"max", maxAttempts,
			"output", strings.TrimSpace(string(out)),
		)

		if attempt == maxAttempts {
			return fmt.Errorf("git push failed after %d attempts: %s", maxAttempts, string(out))
		}

		// Pull --rebase to incorporate remote changes before retrying.
		rebaseCmd := exec.Command("git",
			"-c", "user.name=Claude OS",
			"-c", "user.email=claude-os@noreply.github.com",
			"pull", "--rebase", "origin", s.branch)
		rebaseCmd.Dir = s.localPath
		if rbOut, rbErr := rebaseCmd.CombinedOutput(); rbErr != nil {
			return fmt.Errorf("git pull --rebase before push retry: %s: %w", string(rbOut), rbErr)
		}

		// Brief back-off so concurrent pushes don't all retry at once.
		time.Sleep(time.Duration(attempt) * 2 * time.Second)
	}

	return nil // unreachable
}

func (s *Syncer) moveTask(filename, from, to string) error {
	src := filepath.Join(s.localPath, "tasks", from, filename)
	dst := filepath.Join(s.localPath, "tasks", to, filename)
	if err := os.Rename(src, dst); err != nil {
		return fmt.Errorf("rename %s → %s: %w", from, to, err)
	}
	if err := s.gitCommitAndPush(fmt.Sprintf("task %s: %s → %s", strings.TrimSuffix(filename, ".md"), from, to)); err != nil {
		// Push failed — revert the local move so disk stays consistent with
		// the remote. Without this, pull() would reset --hard and silently
		// undo the move, but Redis would still think the task is in the new state.
		slog.Error("failed to push task move, reverting local rename",
			"file", filename, "from", from, "to", to, "error", err)
		if revertErr := os.Rename(dst, src); revertErr != nil {
			slog.Error("failed to revert local rename — manual intervention needed",
				"file", filename, "error", revertErr)
		}
		return fmt.Errorf("push task move: %w", err)
	}
	slog.Info("pushed task move", "file", filename, "from", from, "to", to)
	return nil
}

func formatStructuredResult(result *queue.TaskResult) string {
	if result == nil {
		return ""
	}

	var b strings.Builder
	b.WriteString("\n## Outcome\n\n")
	b.WriteString(fmt.Sprintf("- Outcome: %s\n", result.Outcome))
	b.WriteString(fmt.Sprintf("- Agent: %s\n", result.Agent))
	if result.Model != "" {
		b.WriteString(fmt.Sprintf("- Model: %s\n", result.Model))
	}

	if result.Summary != "" {
		b.WriteString("\n## Summary\n\n")
		b.WriteString(result.Summary)
		b.WriteString("\n")
	}

	b.WriteString("\n## Usage\n\n")
	b.WriteString(fmt.Sprintf("- Tokens in: %d\n", result.Usage.TokensIn))
	b.WriteString(fmt.Sprintf("- Tokens out: %d\n", result.Usage.TokensOut))
	b.WriteString(fmt.Sprintf("- Duration (s): %d\n", result.Usage.DurationSeconds))

	b.WriteString("\n## Artifacts\n\n")
	if len(result.Artifacts) == 0 {
		b.WriteString("- None\n")
	} else {
		for _, artifact := range result.Artifacts {
			var details []string
			if artifact.Ref != "" {
				details = append(details, fmt.Sprintf("ref=%s", artifact.Ref))
			}
			if artifact.URL != "" {
				details = append(details, fmt.Sprintf("url=%s", artifact.URL))
			}
			if artifact.Path != "" {
				details = append(details, fmt.Sprintf("path=%s", artifact.Path))
			}
			if len(details) > 0 {
				b.WriteString(fmt.Sprintf("- %s (%s)\n", artifact.Type, strings.Join(details, ", ")))
			} else {
				b.WriteString(fmt.Sprintf("- %s\n", artifact.Type))
			}
		}
	}

	if result.Failure != nil {
		b.WriteString("\n## Failure Details\n\n")
		b.WriteString(fmt.Sprintf("- Reason: %s\n", result.Failure.Reason))
		b.WriteString(fmt.Sprintf("- Retryable: %t\n", result.Failure.Retryable))
		if result.Failure.Detail != "" {
			b.WriteString(fmt.Sprintf("- Detail: %s\n", result.Failure.Detail))
		}
	}

	if result.NextAction != nil {
		b.WriteString("\n## Next Action\n\n")
		b.WriteString(fmt.Sprintf("- Type: %s\n", result.NextAction.Type))
		if result.NextAction.Awaiting != "" {
			b.WriteString(fmt.Sprintf("- Awaiting: %s\n", result.NextAction.Awaiting))
		}
		if result.NextAction.ThreadID != "" {
			b.WriteString(fmt.Sprintf("- Thread ID: %s\n", result.NextAction.ThreadID))
		}
		if len(result.NextAction.Tasks) > 0 {
			b.WriteString("- Spawned tasks:\n")
			for _, task := range result.NextAction.Tasks {
				b.WriteString(fmt.Sprintf("  - %s (profile=%s, agent=%s)\n", task.ID, task.Profile, task.Agent))
			}
		}
	}

	return b.String()
}

func appendTaskResult(path, heading string, result *queue.TaskResult, logs string) error {
	f, err := os.OpenFile(path, os.O_APPEND|os.O_WRONLY, 0644)
	if err != nil {
		return err
	}
	defer f.Close()

	if _, err := f.WriteString(fmt.Sprintf("\n## %s\n", heading)); err != nil {
		return err
	}

	if result != nil {
		if _, err := f.WriteString(formatStructuredResult(result)); err != nil {
			return err
		}
		if rawJSON, err := json.MarshalIndent(result, "", "  "); err == nil {
			if _, err := f.WriteString("\n## Structured Result (raw)\n\n```json\n" + string(rawJSON) + "\n```\n"); err != nil {
				return err
			}
		}
	}

	if len(logs) > 10000 {
		logs = logs[:10000] + "\n\n...(truncated)"
	}
	if _, err := f.WriteString("\n## Worker Logs\n\n" + logs + "\n"); err != nil {
		return err
	}

	return nil
}

func (s *Syncer) CompleteTask(taskID string, result *queue.TaskResult, logs string) {
	filename := taskID + ".md"
	src := filepath.Join(s.localPath, "tasks", "in-progress", filename)
	if _, err := os.Stat(src); os.IsNotExist(err) {
		// Task was created programmatically (e.g. workshop), not from a git file.
		// Write results directly to completed/ instead.
		s.writeResultsOnly(taskID, "completed", result, logs)
		return
	}
	if err := s.moveTask(filename, "in-progress", "completed"); err != nil {
		slog.Error("failed to move task to completed — results will be lost until next reconcile",
			"task", taskID, "error", err)
		return
	}

	path := filepath.Join(s.localPath, "tasks", "completed", filename)
	if err := appendTaskResult(path, "Results", result, logs); err != nil {
		slog.Error("failed to open completed task for results", "task", taskID, "error", err)
		return
	}

	if err := s.gitCommitAndPush(fmt.Sprintf("task %s: add results", taskID)); err != nil {
		slog.Warn("failed to push task results", "task", taskID, "error", err)
	} else {
		slog.Info("pushed task results", "task", taskID)
	}
}

func (s *Syncer) writeResultsOnly(taskID, dir string, result *queue.TaskResult, logs string) {
	filename := taskID + ".md"
	path := filepath.Join(s.localPath, "tasks", dir, filename)
	header := fmt.Sprintf("---\nprofile: small\npriority: creative\nstatus: %s\n---\n\n# Workshop: %s\n", dir, taskID)
	if err := os.WriteFile(path, []byte(header), 0644); err != nil {
		slog.Error("failed to write results file", "task", taskID, "error", err)
		return
	}
	if err := appendTaskResult(path, "Results", result, logs); err != nil {
		slog.Error("failed to append structured results file", "task", taskID, "error", err)
		return
	}
	if err := s.gitCommitAndPush(fmt.Sprintf("workshop %s: %s", taskID, dir)); err != nil {
		slog.Warn("failed to push workshop results", "task", taskID, "error", err)
	} else {
		slog.Info("pushed workshop results", "task", taskID)
	}
}

// ListProcessedTaskIDs returns the set of task IDs that have already been
// moved to completed/ or failed/. Used to seed the watcher's seen map on
// startup so it doesn't re-process finished jobs that are still lingering
// in K8s (TTLSecondsAfterFinished).
func (s *Syncer) ListProcessedTaskIDs() map[string]bool {
	processed := make(map[string]bool)
	for _, dir := range []string{"completed", "failed"} {
		dirPath := filepath.Join(s.localPath, "tasks", dir)
		entries, err := os.ReadDir(dirPath)
		if err != nil {
			continue
		}
		for _, entry := range entries {
			if entry.IsDir() || !strings.HasSuffix(entry.Name(), ".md") {
				continue
			}
			taskID := strings.TrimSuffix(entry.Name(), ".md")
			processed[taskID] = true
		}
	}
	return processed
}

func (s *Syncer) FailTask(taskID string, result *queue.TaskResult, logs string) {
	filename := taskID + ".md"
	src := filepath.Join(s.localPath, "tasks", "in-progress", filename)
	if _, err := os.Stat(src); os.IsNotExist(err) {
		s.writeResultsOnly(taskID, "failed", result, logs)
		return
	}
	if err := s.moveTask(filename, "in-progress", "failed"); err != nil {
		slog.Error("failed to move task to failed — will remain in-progress until next reconcile",
			"task", taskID, "error", err)
		return
	}

	path := filepath.Join(s.localPath, "tasks", "failed", filename)
	if err := appendTaskResult(path, "Failure", result, logs); err != nil {
		slog.Error("failed to open failed task for reason", "task", taskID, "error", err)
		return
	}

	reason := "job failed"
	if result != nil && result.Failure != nil && result.Failure.Reason != "" {
		reason = result.Failure.Reason
	}
	if err := s.gitCommitAndPush(fmt.Sprintf("task %s: failed — %s", taskID, reason)); err != nil {
		slog.Warn("failed to push task failure", "task", taskID, "error", err)
	}
}
