package gitsync

import (
	"context"
	"fmt"
	"log/slog"
	"os"
	"os/exec"
	"path/filepath"
	"strings"

	"github.com/dacort/claude-os/controller/queue"
)

type Syncer struct {
	repoURL    string
	branch     string
	localPath  string
	queue      *queue.Queue
	knownTasks map[string]bool
}

func NewSyncer(repoURL, branch, localPath string, q *queue.Queue) *Syncer {
	return &Syncer{
		repoURL:    repoURL,
		branch:     branch,
		localPath:  localPath,
		queue:      q,
		knownTasks: make(map[string]bool),
	}
}

func (s *Syncer) Sync(ctx context.Context) error {
	if err := s.ensureClone(); err != nil {
		return fmt.Errorf("clone: %w", err)
	}
	if err := s.pull(); err != nil {
		return fmt.Errorf("pull: %w", err)
	}
	return s.syncPendingTasks(ctx)
}

func (s *Syncer) ensureClone() error {
	if _, err := os.Stat(filepath.Join(s.localPath, ".git")); err == nil {
		return nil
	}
	slog.Info("cloning repo", "url", s.repoURL, "path", s.localPath)
	cmd := exec.Command("git", "clone", "--branch", s.branch, "--single-branch", s.repoURL, s.localPath)
	cmd.Stdout = os.Stdout
	cmd.Stderr = os.Stderr
	return cmd.Run()
}

func (s *Syncer) pull() error {
	cmd := exec.Command("git", "pull", "--rebase", "origin", s.branch)
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
			ID:          taskID,
			Title:       tf.Title,
			Description: tf.Description,
			TargetRepo:  tf.TargetRepo,
			Profile:     tf.Profile,
			Priority:    priority,
		}

		if err := s.queue.Enqueue(ctx, task); err != nil {
			slog.Error("failed to enqueue task", "id", taskID, "error", err)
			continue
		}
		s.knownTasks[taskID] = true
		slog.Info("enqueued task from git", "id", taskID, "title", tf.Title)

		s.moveTask(tf.Filename, "pending", "in-progress")
	}
	return nil
}

func (s *Syncer) moveTask(filename, from, to string) {
	src := filepath.Join(s.localPath, "tasks", from, filename)
	dst := filepath.Join(s.localPath, "tasks", to, filename)
	if err := os.Rename(src, dst); err != nil {
		slog.Error("failed to move task file", "file", filename, "error", err)
		return
	}
	cmd := exec.Command("git", "add", "-A")
	cmd.Dir = s.localPath
	cmd.Run()
	cmd = exec.Command("git", "-c", "user.name=Claude OS", "-c", "user.email=claude-os@noreply.github.com",
		"commit", "-m", fmt.Sprintf("move %s to %s", filename, to))
	cmd.Dir = s.localPath
	cmd.Run()
	cmd = exec.Command("git", "push", "origin", s.branch)
	cmd.Dir = s.localPath
	if err := cmd.Run(); err != nil {
		slog.Warn("failed to push task move, will retry", "error", err)
	}
}

func (s *Syncer) CompleteTask(taskID, result string) {
	filename := taskID + ".md"
	s.moveTask(filename, "in-progress", "completed")
	path := filepath.Join(s.localPath, "tasks", "completed", filename)
	f, err := os.OpenFile(path, os.O_APPEND|os.O_WRONLY, 0644)
	if err != nil {
		return
	}
	defer f.Close()
	f.WriteString(fmt.Sprintf("\n## Results\n%s\n", result))
}

func (s *Syncer) FailTask(taskID, reason string) {
	filename := taskID + ".md"
	s.moveTask(filename, "in-progress", "failed")
	path := filepath.Join(s.localPath, "tasks", "failed", filename)
	f, err := os.OpenFile(path, os.O_APPEND|os.O_WRONLY, 0644)
	if err != nil {
		return
	}
	defer f.Close()
	f.WriteString(fmt.Sprintf("\n## Failure\n%s\n", reason))
}
