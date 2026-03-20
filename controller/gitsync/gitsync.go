package gitsync

import (
	"bytes"
	"fmt"
	"log/slog"
	"os"
	"path/filepath"
	"strings"
	"time"

	"gopkg.in/yaml.v3"
)

type TaskFrontmatter struct {
	TargetRepo    string   `yaml:"target_repo"`
	Profile       string   `yaml:"profile"`
	Agent         string   `yaml:"agent"`
	Model         string   `yaml:"model"`
	Mode          string   `yaml:"mode"`
	Priority      string   `yaml:"priority"`
	Status        string   `yaml:"status"`
	Created       string   `yaml:"created"`
	ContextRefs   []string `yaml:"context_refs"`
	PlanID        string   `yaml:"plan_id"`
	TaskType      string   `yaml:"task_type"`
	DependsOn     []string `yaml:"depends_on"`
	MaxRetries    int      `yaml:"max_retries"`
	AgentRequired string   `yaml:"agent_required"`
	// Scheduled task fields
	Schedule      string `yaml:"schedule"`       // 5-field cron expression (UTC)
	MaxConcurrent int    `yaml:"max_concurrent"` // prevent stacking (default 1)
	Project       string `yaml:"project"`
	BacklogSource string `yaml:"backlog_source"`
}

type TaskFile struct {
	Filename      string
	TargetRepo    string
	Profile       string
	Agent         string
	Model         string
	Mode          string
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
	// Scheduled task fields
	Schedule      string
	MaxConcurrent int
	Project       string
	BacklogSource string
}

func ParseTaskFile(filename string, data []byte) (*TaskFile, error) {
	parts := bytes.SplitN(data, []byte("---"), 3)
	if len(parts) < 3 {
		return nil, fmt.Errorf("invalid frontmatter in %s", filename)
	}

	var fm TaskFrontmatter
	if err := yaml.Unmarshal(parts[1], &fm); err != nil {
		return nil, fmt.Errorf("parse frontmatter in %s: %w", filename, err)
	}

	body := string(parts[2])

	title := ""
	for _, line := range strings.Split(body, "\n") {
		line = strings.TrimSpace(line)
		if strings.HasPrefix(line, "# ") {
			title = strings.TrimPrefix(line, "# ")
			break
		}
	}

	description := ""
	inDesc := false
	var descLines []string
	for _, line := range strings.Split(body, "\n") {
		trimmed := strings.TrimSpace(line)
		if trimmed == "## Description" {
			inDesc = true
			continue
		}
		if inDesc && strings.HasPrefix(trimmed, "## ") {
			break
		}
		if inDesc && trimmed != "" {
			descLines = append(descLines, trimmed)
		}
	}
	description = strings.Join(descLines, "\n")

	var createdAt time.Time
	if fm.Created != "" {
		createdAt, _ = time.Parse(time.RFC3339, fm.Created)
	}

	return &TaskFile{
		Filename:      filename,
		TargetRepo:    fm.TargetRepo,
		Profile:       fm.Profile,
		Agent:         fm.Agent,
		Model:         fm.Model,
		Mode:          fm.Mode,
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
		Schedule:      fm.Schedule,
		MaxConcurrent: fm.MaxConcurrent,
		Project:       fm.Project,
		BacklogSource: fm.BacklogSource,
	}, nil
}

// ScanScheduledTasks reads all .md files from tasks/scheduled/ and returns
// parsed TaskFile entries. Only files with status=scheduled and a non-empty
// schedule field are included.
func ScanScheduledTasks(tasksPath string) ([]*TaskFile, error) {
	scheduledDir := filepath.Join(tasksPath, "scheduled")
	entries, err := os.ReadDir(scheduledDir)
	if err != nil {
		if os.IsNotExist(err) {
			return nil, nil // directory doesn't exist yet
		}
		return nil, fmt.Errorf("read scheduled dir: %w", err)
	}

	var tasks []*TaskFile
	for _, entry := range entries {
		if entry.IsDir() || !strings.HasSuffix(entry.Name(), ".md") {
			continue
		}
		data, err := os.ReadFile(filepath.Join(scheduledDir, entry.Name()))
		if err != nil {
			continue
		}
		task, err := ParseTaskFile(entry.Name(), data)
		if err != nil {
			slog.Warn("skipping scheduled task file", "file", entry.Name(), "error", err)
			continue
		}
		if task.Schedule == "" {
			slog.Warn("skipping scheduled task with no schedule", "file", entry.Name())
			continue
		}
		tasks = append(tasks, task)
	}
	return tasks, nil
}

func ScanPendingTasks(tasksPath string) ([]*TaskFile, error) {
	pendingDir := filepath.Join(tasksPath, "pending")
	entries, err := os.ReadDir(pendingDir)
	if err != nil {
		return nil, fmt.Errorf("read pending dir: %w", err)
	}

	var tasks []*TaskFile
	for _, entry := range entries {
		if entry.IsDir() || !strings.HasSuffix(entry.Name(), ".md") {
			continue
		}
		data, err := os.ReadFile(filepath.Join(pendingDir, entry.Name()))
		if err != nil {
			continue
		}
		task, err := ParseTaskFile(entry.Name(), data)
		if err != nil {
			slog.Warn("skipping task file", "file", entry.Name(), "error", err)
			continue
		}
		tasks = append(tasks, task)
	}
	return tasks, nil
}
