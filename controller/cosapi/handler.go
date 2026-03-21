// Package cosapi implements the HTTP API endpoints consumed by the cos CLI.
// All routes are prefixed with /api/v1 and mounted on the controller's existing mux.
package cosapi

import (
	"bufio"
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"math/rand"
	"net/http"
	"regexp"
	"strconv"
	"strings"
	"time"

	corev1 "k8s.io/api/core/v1"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/client-go/kubernetes"

	"github.com/dacort/claude-os/controller/governance"
	"github.com/dacort/claude-os/controller/queue"
)

// Version is embedded in every /api/v1/status response.
const Version = "0.4.0"

// Handler holds the dependencies for the cos API endpoints.
type Handler struct {
	Queue     *queue.Queue
	Governor  *governance.Governor
	K8s       kubernetes.Interface
	Namespace string
}

// RegisterRoutes mounts all /api/v1/* routes on mux.
// Uses Go 1.22+ method+path pattern syntax for precise routing.
func (h *Handler) RegisterRoutes(mux *http.ServeMux) {
	mux.HandleFunc("GET /api/v1/status", h.handleStatus)
	mux.HandleFunc("GET /api/v1/tasks/{id}", h.handleTaskDetail)
	mux.HandleFunc("GET /api/v1/tasks/{id}/logs", h.handleTaskLogs)
	mux.HandleFunc("POST /api/v1/tasks", h.handleCreateTask)
}

// ─── Response types ──────────────────────────────────────────────────────────

type errorResponse struct {
	Error   string `json:"error"`
	Message string `json:"message"`
}

type statusResponse struct {
	Controller controllerInfo       `json:"controller"`
	Queue      queueStats           `json:"queue"`
	Governance governanceStats      `json:"governance"`
	Agents     map[string]agentInfo `json:"agents"`
	Running    []runningSummary     `json:"running"`
	Pending    []pendingSummary     `json:"pending"`
	Recent     []recentSummary      `json:"recent"`
}

type controllerInfo struct {
	Version string `json:"version"`
}

type queueStats struct {
	Pending int64 `json:"pending"`
	Running int64 `json:"running"`
	Blocked int64 `json:"blocked"`
}

type governanceStats struct {
	TokensUsedToday  int64   `json:"tokens_used_today"`
	TokensLimitToday int64   `json:"tokens_limit_today"`
	BurstSpendToday  float64 `json:"burst_spend_today"`
	BurstBudgetToday float64 `json:"burst_budget_today"`
}

type agentInfo struct {
	Status           string     `json:"status"`
	RateLimitedUntil *time.Time `json:"rate_limited_until,omitempty"`
}

type runningSummary struct {
	ID        string     `json:"id"`
	Title     string     `json:"title"`
	Agent     string     `json:"agent,omitempty"`
	Profile   string     `json:"profile,omitempty"`
	StartedAt *time.Time `json:"started_at,omitempty"`
}

type pendingSummary struct {
	ID        string     `json:"id"`
	Title     string     `json:"title"`
	Priority  int        `json:"priority"`
	Profile   string     `json:"profile,omitempty"`
	CreatedAt *time.Time `json:"created_at,omitempty"`
}

type recentSummary struct {
	ID              string     `json:"id"`
	Title           string     `json:"title"`
	Outcome         string     `json:"outcome,omitempty"`
	DurationSeconds int64      `json:"duration_seconds,omitempty"`
	FinishedAt      *time.Time `json:"finished_at,omitempty"`
}

type taskDetailResponse struct {
	ID              string             `json:"id"`
	Title           string             `json:"title"`
	Description     string             `json:"description,omitempty"`
	TargetRepo      string             `json:"target_repo,omitempty"`
	Profile         string             `json:"profile,omitempty"`
	Agent           string             `json:"agent,omitempty"`
	Model           string             `json:"model,omitempty"`
	Priority        int                `json:"priority"`
	Status          queue.Status       `json:"status"`
	TaskType        queue.TaskType     `json:"task_type,omitempty"`
	PlanID          string             `json:"plan_id,omitempty"`
	DependsOn       []string           `json:"depends_on,omitempty"`
	ContextRefs     []string           `json:"context_refs,omitempty"`
	CreatedAt       time.Time          `json:"created_at"`
	StartedAt       *time.Time         `json:"started_at,omitempty"`
	FinishedAt      *time.Time         `json:"finished_at,omitempty"`
	TokensUsed      int64              `json:"tokens_used,omitempty"`
	DurationSeconds int64              `json:"duration_seconds,omitempty"`
	Result          *queue.TaskResult  `json:"result,omitempty"`
	PlanProgress    *planProgressResp  `json:"plan_progress,omitempty"`
}

type planProgressResp struct {
	Completed int `json:"completed"`
	Total     int `json:"total"`
}

type logLine struct {
	TS   *time.Time `json:"ts,omitempty"`
	Text string     `json:"text"`
}

type logsResponse struct {
	TaskID  string    `json:"task_id"`
	Status  string    `json:"status"`
	Lines   []logLine `json:"lines"`
	Message string    `json:"message,omitempty"`
}

type createTaskRequest struct {
	Title       string   `json:"title"`
	Description string   `json:"description"`
	TargetRepo  string   `json:"target_repo"`
	Profile     string   `json:"profile"`
	Priority    string   `json:"priority"`
	Agent       string   `json:"agent"`
	Model       string   `json:"model"`
	ContextRefs []string `json:"context_refs"`
}

type createTaskResponse struct {
	ID            string    `json:"id"`
	Title         string    `json:"title"`
	Status        string    `json:"status"`
	QueuePosition int       `json:"queue_position"`
	CreatedAt     time.Time `json:"created_at"`
}

// ─── Handlers ────────────────────────────────────────────────────────────────

// GET /api/v1/status
func (h *Handler) handleStatus(w http.ResponseWriter, r *http.Request) {
	ctx := r.Context()

	recentN := 5
	if v := r.URL.Query().Get("recent"); v != "" {
		if n, err := strconv.Atoi(v); err == nil && n >= 0 && n <= 50 {
			recentN = n
		}
	}

	// Queue counts
	pendingCount, _ := h.Queue.PendingCount(ctx)
	runningIDs, _ := h.Queue.ListRunning(ctx)
	blockedCount, _ := h.Queue.BlockedCount(ctx)

	// Governance
	govStats := h.Governor.GetStats(ctx)

	// Agent health
	knownAgents := []string{"claude", "codex", "gemini"}
	agents := make(map[string]agentInfo, len(knownAgents))
	for _, name := range knownAgents {
		until := h.Queue.GetAgentRateLimitedUntil(ctx, name)
		if until != nil {
			agents[name] = agentInfo{Status: "rate_limited", RateLimitedUntil: until}
		} else {
			agents[name] = agentInfo{Status: "ok"}
		}
	}

	// Running tasks
	running := make([]runningSummary, 0, len(runningIDs))
	for _, id := range runningIDs {
		task, err := h.Queue.Get(ctx, id)
		if err != nil {
			continue
		}
		s := runningSummary{
			ID:      task.ID,
			Title:   task.Title,
			Agent:   task.Agent,
			Profile: task.Profile,
		}
		if !task.StartedAt.IsZero() {
			t := task.StartedAt
			s.StartedAt = &t
		}
		running = append(running, s)
	}

	// Pending tasks
	pendingTasks, _ := h.Queue.ListPending(ctx)
	pending := make([]pendingSummary, 0, len(pendingTasks))
	for _, task := range pendingTasks {
		s := pendingSummary{
			ID:       task.ID,
			Title:    task.Title,
			Priority: int(task.Priority),
			Profile:  task.Profile,
		}
		if !task.CreatedAt.IsZero() {
			t := task.CreatedAt
			s.CreatedAt = &t
		}
		pending = append(pending, s)
	}

	// Recent completions
	recentIDs, _ := h.Queue.GetRecent(ctx, recentN)
	recent := make([]recentSummary, 0, len(recentIDs))
	for _, id := range recentIDs {
		task, err := h.Queue.Get(ctx, id)
		if err != nil {
			continue
		}
		s := recentSummary{
			ID:              task.ID,
			Title:           task.Title,
			DurationSeconds: task.DurationSeconds,
		}
		if !task.FinishedAt.IsZero() {
			t := task.FinishedAt
			s.FinishedAt = &t
		}
		// Outcome from parsed result
		if task.Result != "" {
			if parsed := queue.ParseResult(task.Result); parsed != nil {
				s.Outcome = parsed.Outcome
			}
		}
		if s.Outcome == "" {
			if task.Status == queue.StatusCompleted {
				s.Outcome = "success"
			} else if task.Status == queue.StatusFailed {
				s.Outcome = "failure"
			}
		}
		recent = append(recent, s)
	}

	resp := statusResponse{
		Controller: controllerInfo{Version: Version},
		Queue: queueStats{
			Pending: pendingCount,
			Running: int64(len(runningIDs)),
			Blocked: blockedCount,
		},
		Governance: governanceStats{
			TokensUsedToday:  govStats.TokensUsedToday,
			TokensLimitToday: govStats.TokensLimitToday,
			BurstSpendToday:  govStats.BurstSpendToday,
			BurstBudgetToday: govStats.BurstBudgetToday,
		},
		Agents:  agents,
		Running: running,
		Pending: pending,
		Recent:  recent,
	}
	writeJSON(w, http.StatusOK, resp)
}

// GET /api/v1/tasks/{id}
func (h *Handler) handleTaskDetail(w http.ResponseWriter, r *http.Request) {
	ctx := r.Context()
	id := r.PathValue("id")

	task, err := h.Queue.Get(ctx, id)
	if err != nil {
		jsonError(w, http.StatusNotFound, "not_found", fmt.Sprintf("Task %q not found.", id))
		return
	}

	resp := taskDetailFromTask(task)

	// Parse structured result if stored
	if task.Result != "" {
		resp.Result = queue.ParseResult(task.Result)
	}

	// Plan progress
	if task.PlanID != "" {
		completed, total, err := h.Queue.PlanProgress(ctx, task.PlanID)
		if err == nil {
			resp.PlanProgress = &planProgressResp{Completed: completed, Total: total}
		}
	}

	writeJSON(w, http.StatusOK, resp)
}

// GET /api/v1/tasks/{id}/logs
func (h *Handler) handleTaskLogs(w http.ResponseWriter, r *http.Request) {
	ctx := r.Context()
	id := r.PathValue("id")

	task, err := h.Queue.Get(ctx, id)
	if err != nil {
		jsonError(w, http.StatusNotFound, "not_found", fmt.Sprintf("Task %q not found.", id))
		return
	}

	tailLines := 0
	if v := r.URL.Query().Get("tail"); v != "" {
		if n, err := strconv.Atoi(v); err == nil && n >= 0 {
			tailLines = n
		}
	}

	follow := r.URL.Query().Get("follow") == "true"

	if follow && task.Status == queue.StatusRunning {
		h.streamLogs(w, r, task, tailLines)
		return
	}

	// Non-streaming: fetch logs from K8s (best-effort)
	jobName := taskJobName(id)
	rawLogs, logErr := h.getPodLogs(ctx, jobName, false, 0)

	lines := parseLogLines(rawLogs)
	if tailLines > 0 && len(lines) > tailLines {
		lines = lines[len(lines)-tailLines:]
	}

	resp := logsResponse{
		TaskID: id,
		Status: string(task.Status),
		Lines:  lines,
	}
	if logErr != nil || rawLogs == "" {
		resp.Message = "Logs no longer available (job cleaned up)."
		resp.Lines = []logLine{}
	}

	writeJSON(w, http.StatusOK, resp)
}

// POST /api/v1/tasks
func (h *Handler) handleCreateTask(w http.ResponseWriter, r *http.Request) {
	ctx := r.Context()

	var req createTaskRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		jsonError(w, http.StatusBadRequest, "invalid_request", "Request body must be valid JSON.")
		return
	}

	// Validation
	if strings.TrimSpace(req.Title) == "" {
		jsonError(w, http.StatusBadRequest, "invalid_request", `"title" is required.`)
		return
	}
	if len(req.Title) > 200 {
		jsonError(w, http.StatusBadRequest, "invalid_request", `"title" must be 200 characters or fewer.`)
		return
	}
	if req.TargetRepo == "" {
		jsonError(w, http.StatusBadRequest, "invalid_request", `"target_repo" is required.`)
		return
	}
	if len(req.Description) > 5000 {
		jsonError(w, http.StatusBadRequest, "invalid_request", `"description" must be 5000 characters or fewer.`)
		return
	}

	validProfiles := map[string]bool{"small": true, "medium": true, "large": true, "burst": true, "think": true}
	if req.Profile != "" && !validProfiles[req.Profile] {
		jsonError(w, http.StatusBadRequest, "invalid_request",
			fmt.Sprintf("Invalid profile %q. Valid profiles: small, medium, large, burst, think.", req.Profile))
		return
	}

	validAgents := map[string]bool{"claude": true, "codex": true, "gemini": true}
	if req.Agent != "" && !validAgents[req.Agent] {
		jsonError(w, http.StatusBadRequest, "invalid_request",
			fmt.Sprintf("Invalid agent %q. Valid agents: claude, codex, gemini.", req.Agent))
		return
	}

	// Priority
	priority := queue.PriorityNormal
	switch req.Priority {
	case "", "normal":
		priority = queue.PriorityNormal
	case "high":
		priority = queue.PriorityHigh
	case "creative":
		priority = queue.PriorityCreative
	default:
		jsonError(w, http.StatusBadRequest, "invalid_request",
			fmt.Sprintf("Invalid priority %q. Valid priorities: creative, normal, high.", req.Priority))
		return
	}

	profile := req.Profile
	if profile == "" {
		profile = "small"
	}
	description := req.Description
	if description == "" {
		description = req.Title
	}

	task := &queue.Task{
		ID:          generateTaskID(req.Title),
		Title:       req.Title,
		Description: description,
		TargetRepo:  req.TargetRepo,
		Profile:     profile,
		Agent:       req.Agent,
		Model:       req.Model,
		Priority:    priority,
		ContextRefs: req.ContextRefs,
		TaskType:    queue.TaskTypeStandalone,
	}

	if err := h.Queue.Enqueue(ctx, task); err != nil {
		jsonError(w, http.StatusInternalServerError, "internal_error", "Failed to enqueue task.")
		return
	}

	pos := h.Queue.QueuePosition(ctx, task.ID)

	writeJSON(w, http.StatusCreated, createTaskResponse{
		ID:            task.ID,
		Title:         task.Title,
		Status:        "pending",
		QueuePosition: pos,
		CreatedAt:     task.CreatedAt,
	})
}

// ─── SSE streaming ───────────────────────────────────────────────────────────

func (h *Handler) streamLogs(w http.ResponseWriter, r *http.Request, task *queue.Task, tailLines int) {
	flusher, ok := w.(http.Flusher)
	if !ok {
		http.Error(w, "streaming not supported", http.StatusInternalServerError)
		return
	}

	w.Header().Set("Content-Type", "text/event-stream")
	w.Header().Set("Cache-Control", "no-cache")
	w.Header().Set("Connection", "keep-alive")
	w.WriteHeader(http.StatusOK)
	flusher.Flush()

	ctx := r.Context()
	jobName := taskJobName(task.ID)

	// Find the pod
	pods, err := h.K8s.CoreV1().Pods(h.Namespace).List(ctx, metav1.ListOptions{
		LabelSelector: fmt.Sprintf("job-name=%s", jobName),
	})
	if err != nil || len(pods.Items) == 0 {
		// Send done event immediately — no pod to stream from
		writeSSEDone(w, string(task.Status), "")
		flusher.Flush()
		return
	}

	pod := pods.Items[0]
	var tailPtr *int64
	if tailLines > 0 {
		t := int64(tailLines)
		tailPtr = &t
	}
	req := h.K8s.CoreV1().Pods(h.Namespace).GetLogs(pod.Name, &corev1.PodLogOptions{
		Follow:    true,
		TailLines: tailPtr,
	})
	stream, err := req.Stream(ctx)
	if err != nil {
		writeSSEDone(w, string(task.Status), "")
		flusher.Flush()
		return
	}
	defer stream.Close()

	scanner := bufio.NewScanner(stream)
	for scanner.Scan() {
		line := scanner.Text()
		ll := parseOneLine(line)
		data, _ := json.Marshal(ll)
		fmt.Fprintf(w, "data: %s\n\n", data)
		flusher.Flush()
	}

	// Stream ended — fetch final task status
	finalTask, err := h.Queue.Get(ctx, task.ID)
	outcome := ""
	status := string(task.Status)
	if err == nil {
		status = string(finalTask.Status)
		if parsed := queue.ParseResult(finalTask.Result); parsed != nil {
			outcome = parsed.Outcome
		}
	}
	writeSSEDone(w, status, outcome)
	flusher.Flush()
}

func writeSSEDone(w io.Writer, status, outcome string) {
	type donePayload struct {
		Status  string `json:"status"`
		Outcome string `json:"outcome,omitempty"`
	}
	data, _ := json.Marshal(donePayload{Status: status, Outcome: outcome})
	fmt.Fprintf(w, "event: done\ndata: %s\n\n", data)
}

// ─── K8s log helpers ─────────────────────────────────────────────────────────

func (h *Handler) getPodLogs(ctx context.Context, jobName string, follow bool, tailLines int) (string, error) {
	if h.K8s == nil {
		return "", fmt.Errorf("no k8s client")
	}
	pods, err := h.K8s.CoreV1().Pods(h.Namespace).List(ctx, metav1.ListOptions{
		LabelSelector: fmt.Sprintf("job-name=%s", jobName),
	})
	if err != nil || len(pods.Items) == 0 {
		return "", fmt.Errorf("no pod found for job %s", jobName)
	}

	pod := pods.Items[0]
	opts := &corev1.PodLogOptions{Follow: follow}
	if tailLines > 0 {
		t := int64(tailLines)
		opts.TailLines = &t
	}

	logCtx, cancel := context.WithTimeout(ctx, 10*time.Second)
	defer cancel()

	stream, err := h.K8s.CoreV1().Pods(h.Namespace).GetLogs(pod.Name, opts).Stream(logCtx)
	if err != nil {
		return "", fmt.Errorf("stream logs: %w", err)
	}
	defer stream.Close()

	var buf bytes.Buffer
	io.Copy(&buf, stream)
	return buf.String(), nil
}

// taskJobName returns the K8s job name for a task ID (mirrors dispatcher logic).
var nonAlphanumDash = regexp.MustCompile(`[^a-z0-9-]`)

func taskJobName(taskID string) string {
	name := strings.ToLower(taskID)
	name = strings.ReplaceAll(name, "_", "-")
	name = nonAlphanumDash.ReplaceAllString(name, "")
	if len(name) > 50 {
		name = name[:50]
	}
	return "claude-os-" + name
}

// ─── Log line parsing ────────────────────────────────────────────────────────

// parseLogLines splits raw log text into LogLine entries, attempting to extract timestamps.
func parseLogLines(raw string) []logLine {
	if raw == "" {
		return []logLine{}
	}
	var lines []logLine
	for _, line := range strings.Split(strings.TrimRight(raw, "\n"), "\n") {
		lines = append(lines, parseOneLine(line))
	}
	return lines
}

// parseOneLine tries to extract an RFC3339 timestamp prefix from a log line.
// If not found, returns the line as plain text with no timestamp.
func parseOneLine(line string) logLine {
	// Common log prefixes: "2026-03-21T14:02:33Z " or "2026-03-21T14:02:33.123Z "
	if len(line) >= 20 {
		candidate := line[:20]
		// Try different timestamp lengths
		for _, n := range []int{25, 24, 20} {
			if n > len(line) {
				continue
			}
			candidate = line[:n]
			t, err := time.Parse(time.RFC3339, strings.TrimRight(candidate, " "))
			if err != nil {
				t, err = time.Parse(time.RFC3339Nano, strings.TrimRight(candidate, " "))
			}
			if err == nil {
				rest := strings.TrimSpace(line[n:])
				return logLine{TS: &t, Text: rest}
			}
		}
	}
	return logLine{Text: line}
}

// ─── ID generation ───────────────────────────────────────────────────────────

var slugNonAlnum = regexp.MustCompile(`[^a-z0-9]+`)

// generateTaskID slugifies the title and appends a 4-char random hex suffix.
func generateTaskID(title string) string {
	slug := strings.ToLower(title)
	slug = slugNonAlnum.ReplaceAllString(slug, "-")
	slug = strings.Trim(slug, "-")
	if len(slug) > 40 {
		// Trim at word boundary if possible
		slug = slug[:40]
		if idx := strings.LastIndex(slug, "-"); idx > 20 {
			slug = slug[:idx]
		}
	}
	suffix := fmt.Sprintf("%04x", rand.Intn(65536))
	return slug + "-" + suffix
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

func taskDetailFromTask(t *queue.Task) taskDetailResponse {
	r := taskDetailResponse{
		ID:              t.ID,
		Title:           t.Title,
		Description:     t.Description,
		TargetRepo:      t.TargetRepo,
		Profile:         t.Profile,
		Agent:           t.Agent,
		Model:           t.Model,
		Priority:        int(t.Priority),
		Status:          t.Status,
		TaskType:        t.TaskType,
		PlanID:          t.PlanID,
		DependsOn:       t.DependsOn,
		ContextRefs:     t.ContextRefs,
		CreatedAt:       t.CreatedAt,
		TokensUsed:      t.TokensUsed,
		DurationSeconds: t.DurationSeconds,
	}
	if !t.StartedAt.IsZero() {
		ts := t.StartedAt
		r.StartedAt = &ts
	}
	if !t.FinishedAt.IsZero() {
		tf := t.FinishedAt
		r.FinishedAt = &tf
	}
	return r
}

func writeJSON(w http.ResponseWriter, status int, v any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	json.NewEncoder(w).Encode(v)
}

func jsonError(w http.ResponseWriter, status int, code, message string) {
	writeJSON(w, status, errorResponse{Error: code, Message: message})
}
