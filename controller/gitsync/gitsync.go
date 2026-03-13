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
	TargetRepo  string   `yaml:"target_repo"`
	Profile     string   `yaml:"profile"`
	Agent       string   `yaml:"agent"`
	Model       string   `yaml:"model"`
	Priority    string   `yaml:"priority"`
	Status      string   `yaml:"status"`
	Created     string   `yaml:"created"`
	ContextRefs []string `yaml:"context_refs"`
}

type TaskFile struct {
	Filename    string
	TargetRepo  string
	Profile     string
	Agent       string
	Model       string
	Priority    string
	Title       string
	Description string
	CreatedAt   time.Time
	ContextRefs []string
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
		Filename:    filename,
		TargetRepo:  fm.TargetRepo,
		Profile:     fm.Profile,
		Agent:       fm.Agent,
		Model:       fm.Model,
		Priority:    fm.Priority,
		Title:       title,
		Description: description,
		CreatedAt:   createdAt,
		ContextRefs: fm.ContextRefs,
	}, nil
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
