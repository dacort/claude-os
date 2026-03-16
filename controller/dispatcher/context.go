package dispatcher

import (
	"encoding/json"
	"fmt"
	"path/filepath"
	"strings"

	"github.com/dacort/claude-os/controller/queue"
)

// TaskContext is the JSON envelope written to /workspace/task-context.json.
// Schema defined in knowledge/co-founders/decisions/002-context-contract.md.
type TaskContext struct {
	Version     string          `json:"version"`
	Mode        string          `json:"mode"`
	Task        TaskContextTask `json:"task"`
	Repo        TaskContextRepo `json:"repo"`
	Autonomy    TaskAutonomy    `json:"autonomy"`
	ContextRefs []string        `json:"context_refs"`
	Constraints []string        `json:"constraints"`
	Founder     *FounderContext `json:"founder"`
}

type TaskContextTask struct {
	ID          string `json:"id"`
	Title       string `json:"title"`
	Description string `json:"description"`
	Profile     string `json:"profile"`
	Priority    string `json:"priority"`
	Agent       string `json:"agent"`
	Created     string `json:"created"`
}

type TaskContextRepo struct {
	URL     string `json:"url"`
	Ref     string `json:"ref"`
	Workdir string `json:"workdir"`
}

type TaskAutonomy struct {
	CanMerge         bool `json:"can_merge"`
	CanCreateIssues  bool `json:"can_create_issues"`
	CanCreateTasks   bool `json:"can_create_tasks"`
	CanPush          bool `json:"can_push"`
	CIIsApprovalGate bool `json:"ci_is_approval_gate"`
}

type FounderContext struct {
	ThreadID                    string `json:"thread_id"`
	ThreadPath                  string `json:"thread_path"`
	RespondInThread             bool   `json:"respond_in_thread"`
	ExtractDecisionIfReached    bool   `json:"extract_decision_if_reached"`
	SpawnExecutionTasksIfNeeded bool   `json:"spawn_execution_tasks_if_needed"`
}

// BuildTaskContext creates the JSON envelope for a task.
// The controller writes this; the worker adapter reads it.
func BuildTaskContext(task *queue.Task, repoURL, branch string) *TaskContext {
	agent := task.Agent
	if agent == "" {
		agent = "claude"
	}

	mode := task.Mode
	if mode == "" {
		mode = "execution"
	}

	priority := "normal"
	switch task.Priority {
	case queue.PriorityHigh:
		priority = "high"
	case queue.PriorityCreative:
		priority = "creative"
	}

	// Determine workdir — authoritative per decision 002.
	workdir := workdirForTask(task)

	// Determine repo URL for the worker to clone.
	taskRepoURL := repoURL
	if task.TargetRepo != "" {
		taskRepoURL = fmt.Sprintf("https://github.com/%s.git", task.TargetRepo)
	}

	tc := &TaskContext{
		Version: "1",
		Mode:    mode,
		Task: TaskContextTask{
			ID:          task.ID,
			Title:       task.Title,
			Description: task.Description,
			Profile:     task.Profile,
			Priority:    priority,
			Agent:       agent,
			Created:     task.CreatedAt.UTC().Format("2006-01-02T15:04:05Z"),
		},
		Repo: TaskContextRepo{
			URL:     taskRepoURL,
			Ref:     branch,
			Workdir: workdir,
		},
		Autonomy:    autonomyForMode(mode),
		ContextRefs: task.ContextRefs,
		Constraints: constraintsForMode(mode),
		Founder:     nil,
	}

	if tc.ContextRefs == nil {
		tc.ContextRefs = []string{}
	}
	if mode == "founder" {
		tc.Founder = founderContextForTask(task)
	}

	return tc
}

// MarshalTaskContext serializes the context envelope to JSON.
func MarshalTaskContext(tc *TaskContext) (string, error) {
	data, err := json.Marshal(tc)
	if err != nil {
		return "", fmt.Errorf("marshal task context: %w", err)
	}
	return string(data), nil
}

func workdirForTask(task *queue.Task) string {
	if task.TargetRepo != "" {
		// Extract repo name from "owner/repo"
		parts := strings.Split(task.TargetRepo, "/")
		repoName := parts[len(parts)-1]
		return "/workspace/" + repoName
	}
	return "/workspace/claude-os"
}

func autonomyForMode(mode string) TaskAutonomy {
	if mode == "founder" {
		return TaskAutonomy{
			CanMerge:         false,
			CanCreateIssues:  true,
			CanCreateTasks:   true,
			CanPush:          true,
			CIIsApprovalGate: true,
		}
	}
	return TaskAutonomy{
		CanMerge:         true,
		CanCreateIssues:  true,
		CanCreateTasks:   false,
		CanPush:          true,
		CIIsApprovalGate: true,
	}
}

func constraintsForMode(mode string) []string {
	base := []string{
		"This repo is PUBLIC — never commit secrets",
		"If tests fail, fix them before merging",
	}
	if mode == "founder" {
		return []string{
			"Prefer decisions and tradeoffs over implementation",
			"Do not merge or ship code in founder mode",
			"Leave the thread in an explicit next state",
			"This repo is PUBLIC — never commit secrets",
		}
	}
	return base
}

func founderContextForTask(task *queue.Task) *FounderContext {
	threadPath := ""
	for _, ref := range task.ContextRefs {
		if strings.HasPrefix(ref, "knowledge/co-founders/threads/") && strings.HasSuffix(ref, ".md") {
			threadPath = ref
			break
		}
	}

	threadID := ""
	if threadPath != "" {
		threadID = strings.TrimSuffix(filepath.Base(threadPath), ".md")
	}

	return &FounderContext{
		ThreadID:                    threadID,
		ThreadPath:                  threadPath,
		RespondInThread:             true,
		ExtractDecisionIfReached:    true,
		SpawnExecutionTasksIfNeeded: true,
	}
}
