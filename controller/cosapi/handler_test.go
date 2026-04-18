package cosapi

import (
	"bytes"
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"github.com/alicebob/miniredis/v2"
	"github.com/dacort/claude-os/controller/governance"
	"github.com/dacort/claude-os/controller/queue"
	"github.com/redis/go-redis/v9"
)

// ─── Test helpers ─────────────────────────────────────────────────────────────

func setupHandler(t *testing.T) (*Handler, *miniredis.Miniredis) {
	t.Helper()
	mr := miniredis.RunT(t)
	rdb := redis.NewClient(&redis.Options{Addr: mr.Addr()})
	q := queue.New(rdb)
	gov := governance.New(rdb, governance.Limits{
		DailyTokenLimit:  200_000,
		DailyBurstBudget: 5.00,
	})
	return &Handler{
		Queue:    q,
		Governor: gov,
		// K8s left nil — tests that need it will set it explicitly
	}, mr
}

func enqueueTask(t *testing.T, q *queue.Queue, id, title string) *queue.Task {
	t.Helper()
	task := &queue.Task{
		ID:         id,
		Title:      title,
		TargetRepo: "github.com/dacort/claude-os",
		Profile:    "small",
		Priority:   queue.PriorityNormal,
		Status:     queue.StatusPending,
	}
	if err := q.Enqueue(context.Background(), task); err != nil {
		t.Fatalf("enqueue %s: %v", id, err)
	}
	return task
}

// ─── GET /api/v1/status ───────────────────────────────────────────────────────

func TestHandleStatus_Empty(t *testing.T) {
	h, _ := setupHandler(t)

	req := httptest.NewRequest(http.MethodGet, "/api/v1/status", nil)
	w := httptest.NewRecorder()
	h.handleStatus(w, req)

	if w.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d", w.Code)
	}
	if ct := w.Header().Get("Content-Type"); !strings.HasPrefix(ct, "application/json") {
		t.Errorf("expected application/json content-type, got %q", ct)
	}

	var resp statusResponse
	if err := json.NewDecoder(w.Body).Decode(&resp); err != nil {
		t.Fatalf("decode response: %v", err)
	}

	if resp.Controller.Version != Version {
		t.Errorf("expected version %q, got %q", Version, resp.Controller.Version)
	}
	if resp.Queue.Pending != 0 {
		t.Errorf("expected 0 pending, got %d", resp.Queue.Pending)
	}
	if resp.Agents == nil {
		t.Error("agents map should not be nil")
	}
	if _, ok := resp.Agents["claude"]; !ok {
		t.Error("expected claude in agents")
	}
}

func TestHandleStatus_WithPendingTask(t *testing.T) {
	h, _ := setupHandler(t)
	enqueueTask(t, h.Queue, "test-task-1", "Fix the thing")

	req := httptest.NewRequest(http.MethodGet, "/api/v1/status", nil)
	w := httptest.NewRecorder()
	h.handleStatus(w, req)

	var resp statusResponse
	json.NewDecoder(w.Body).Decode(&resp)

	if resp.Queue.Pending != 1 {
		t.Errorf("expected 1 pending, got %d", resp.Queue.Pending)
	}
	if len(resp.Pending) != 1 {
		t.Fatalf("expected 1 pending task in list, got %d", len(resp.Pending))
	}
	if resp.Pending[0].ID != "test-task-1" {
		t.Errorf("expected test-task-1, got %q", resp.Pending[0].ID)
	}
}

func TestHandleStatus_RecentParam(t *testing.T) {
	h, _ := setupHandler(t)

	// Push 3 recent completions
	for _, id := range []string{"task-a", "task-b", "task-c"} {
		task := &queue.Task{
			ID:         id,
			Title:      "task " + id,
			Status:     queue.StatusCompleted,
			TargetRepo: "dacort/test",
			Profile:    "small",
			FinishedAt: time.Now().UTC(),
		}
		h.Queue.SaveTask(context.Background(), task)
		h.Queue.PushRecent(context.Background(), id)
	}

	req := httptest.NewRequest(http.MethodGet, "/api/v1/status?recent=2", nil)
	w := httptest.NewRecorder()
	h.handleStatus(w, req)

	var resp statusResponse
	json.NewDecoder(w.Body).Decode(&resp)

	if len(resp.Recent) != 2 {
		t.Errorf("expected 2 recent tasks, got %d", len(resp.Recent))
	}
}

func TestHandleStatus_RateLimitedAgent(t *testing.T) {
	h, mr := setupHandler(t)

	// Simulate claude being rate-limited (set key with TTL)
	mr.Set("claude-os:agent:claude:rate_limited", "1")
	mr.SetTTL("claude-os:agent:claude:rate_limited", 30*time.Minute)

	req := httptest.NewRequest(http.MethodGet, "/api/v1/status", nil)
	w := httptest.NewRecorder()
	h.handleStatus(w, req)

	var resp statusResponse
	json.NewDecoder(w.Body).Decode(&resp)

	if resp.Agents["claude"].Status != "rate_limited" {
		t.Errorf("expected claude to be rate_limited, got %q", resp.Agents["claude"].Status)
	}
	if resp.Agents["claude"].RateLimitedUntil == nil {
		t.Error("expected rate_limited_until to be set")
	}
}

// ─── GET /api/v1/tasks/{id} ───────────────────────────────────────────────────

func TestHandleTaskDetail_Found(t *testing.T) {
	h, _ := setupHandler(t)
	enqueueTask(t, h.Queue, "cos-server", "Add cos API endpoints")

	mux := http.NewServeMux()
	h.RegisterRoutes(mux)

	req := httptest.NewRequest(http.MethodGet, "/api/v1/tasks/cos-server", nil)
	w := httptest.NewRecorder()
	mux.ServeHTTP(w, req)

	if w.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d: %s", w.Code, w.Body.String())
	}

	var resp taskDetailResponse
	if err := json.NewDecoder(w.Body).Decode(&resp); err != nil {
		t.Fatalf("decode: %v", err)
	}
	if resp.ID != "cos-server" {
		t.Errorf("expected id cos-server, got %q", resp.ID)
	}
	if resp.Title != "Add cos API endpoints" {
		t.Errorf("unexpected title: %q", resp.Title)
	}
}

func TestHandleTaskDetail_NotFound(t *testing.T) {
	h, _ := setupHandler(t)

	mux := http.NewServeMux()
	h.RegisterRoutes(mux)

	req := httptest.NewRequest(http.MethodGet, "/api/v1/tasks/nonexistent", nil)
	w := httptest.NewRecorder()
	mux.ServeHTTP(w, req)

	if w.Code != http.StatusNotFound {
		t.Fatalf("expected 404, got %d", w.Code)
	}

	var resp errorResponse
	json.NewDecoder(w.Body).Decode(&resp)
	if resp.Error != "not_found" {
		t.Errorf("expected error=not_found, got %q", resp.Error)
	}
}

func TestHandleTaskDetail_WithPlanProgress(t *testing.T) {
	h, _ := setupHandler(t)
	ctx := context.Background()

	task := &queue.Task{
		ID:         "cos-server",
		Title:      "Add cos API endpoints",
		TargetRepo: "dacort/test",
		Profile:    "small",
		PlanID:     "cos-cli-20260321",
		TaskType:   queue.TaskTypeSubtask,
		Status:     queue.StatusRunning,
	}
	h.Queue.SaveTask(ctx, task)
	// Register 3 plan tasks, 1 completed
	for _, id := range []string{"cos-design", "cos-server", "cos-client"} {
		h.Queue.RegisterPlanTask(ctx, "cos-cli-20260321", id)
	}
	h.Queue.CompletePlanTask(ctx, "cos-cli-20260321", "cos-design")

	mux := http.NewServeMux()
	h.RegisterRoutes(mux)

	req := httptest.NewRequest(http.MethodGet, "/api/v1/tasks/cos-server", nil)
	w := httptest.NewRecorder()
	mux.ServeHTTP(w, req)

	var resp taskDetailResponse
	json.NewDecoder(w.Body).Decode(&resp)

	if resp.PlanProgress == nil {
		t.Fatal("expected plan_progress to be set")
	}
	if resp.PlanProgress.Completed != 1 {
		t.Errorf("expected 1 completed, got %d", resp.PlanProgress.Completed)
	}
	if resp.PlanProgress.Total != 3 {
		t.Errorf("expected 3 total, got %d", resp.PlanProgress.Total)
	}
}

// ─── GET /api/v1/tasks/{id}/logs ─────────────────────────────────────────────

func TestHandleTaskLogs_NotFound(t *testing.T) {
	h, _ := setupHandler(t)

	mux := http.NewServeMux()
	h.RegisterRoutes(mux)

	req := httptest.NewRequest(http.MethodGet, "/api/v1/tasks/ghost/logs", nil)
	w := httptest.NewRecorder()
	mux.ServeHTTP(w, req)

	if w.Code != http.StatusNotFound {
		t.Fatalf("expected 404, got %d", w.Code)
	}
}

func TestHandleTaskLogs_CompletedNoK8s(t *testing.T) {
	h, _ := setupHandler(t)
	ctx := context.Background()

	task := &queue.Task{
		ID:         "done-task",
		Title:      "A finished task",
		Status:     queue.StatusCompleted,
		TargetRepo: "dacort/test",
		Profile:    "small",
		FinishedAt: time.Now().UTC(),
	}
	h.Queue.SaveTask(ctx, task)

	mux := http.NewServeMux()
	h.RegisterRoutes(mux)

	req := httptest.NewRequest(http.MethodGet, "/api/v1/tasks/done-task/logs", nil)
	w := httptest.NewRecorder()
	mux.ServeHTTP(w, req)

	if w.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d", w.Code)
	}

	var resp logsResponse
	json.NewDecoder(w.Body).Decode(&resp)

	if resp.TaskID != "done-task" {
		t.Errorf("unexpected task_id: %q", resp.TaskID)
	}
	// No K8s client → logs unavailable message
	if resp.Message == "" {
		t.Error("expected a message about unavailable logs")
	}
}

// ─── POST /api/v1/tasks ───────────────────────────────────────────────────────

func TestHandleCreateTask_Success(t *testing.T) {
	h, _ := setupHandler(t)

	mux := http.NewServeMux()
	h.RegisterRoutes(mux)

	body := `{
		"title": "Fix the broken vitals test",
		"description": "The vitals.py test fails on missing field.",
		"target_repo": "github.com/dacort/claude-os",
		"profile": "small",
		"priority": "normal"
	}`
	req := httptest.NewRequest(http.MethodPost, "/api/v1/tasks", strings.NewReader(body))
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()
	mux.ServeHTTP(w, req)

	if w.Code != http.StatusCreated {
		t.Fatalf("expected 201, got %d: %s", w.Code, w.Body.String())
	}

	var resp createTaskResponse
	json.NewDecoder(w.Body).Decode(&resp)

	if resp.ID == "" {
		t.Error("expected non-empty task ID")
	}
	if resp.Status != "pending" {
		t.Errorf("expected status pending, got %q", resp.Status)
	}
	if resp.QueuePosition != 1 {
		t.Errorf("expected queue position 1, got %d", resp.QueuePosition)
	}
	if !strings.HasPrefix(resp.ID, "fix-the-broken-vitals-test") {
		t.Errorf("expected ID to start with slug, got %q", resp.ID)
	}
}

func TestHandleCreateTask_MissingTitle(t *testing.T) {
	h, _ := setupHandler(t)

	mux := http.NewServeMux()
	h.RegisterRoutes(mux)

	body := `{"target_repo": "github.com/dacort/claude-os"}`
	req := httptest.NewRequest(http.MethodPost, "/api/v1/tasks", strings.NewReader(body))
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()
	mux.ServeHTTP(w, req)

	if w.Code != http.StatusBadRequest {
		t.Fatalf("expected 400, got %d", w.Code)
	}
	var resp errorResponse
	json.NewDecoder(w.Body).Decode(&resp)
	if resp.Error != "invalid_request" {
		t.Errorf("expected invalid_request, got %q", resp.Error)
	}
}

func TestHandleCreateTask_MissingTargetRepo(t *testing.T) {
	h, _ := setupHandler(t)

	mux := http.NewServeMux()
	h.RegisterRoutes(mux)

	body := `{"title": "Fix bug"}`
	req := httptest.NewRequest(http.MethodPost, "/api/v1/tasks", strings.NewReader(body))
	w := httptest.NewRecorder()
	mux.ServeHTTP(w, req)

	if w.Code != http.StatusBadRequest {
		t.Fatalf("expected 400, got %d", w.Code)
	}
}

func TestHandleCreateTask_InvalidProfile(t *testing.T) {
	h, _ := setupHandler(t)

	mux := http.NewServeMux()
	h.RegisterRoutes(mux)

	body := `{"title": "Fix bug", "target_repo": "dacort/test", "profile": "huge"}`
	req := httptest.NewRequest(http.MethodPost, "/api/v1/tasks", bytes.NewBufferString(body))
	w := httptest.NewRecorder()
	mux.ServeHTTP(w, req)

	if w.Code != http.StatusBadRequest {
		t.Fatalf("expected 400, got %d", w.Code)
	}
	var resp errorResponse
	json.NewDecoder(w.Body).Decode(&resp)
	if !strings.Contains(resp.Message, "huge") {
		t.Errorf("error message should mention invalid profile, got: %q", resp.Message)
	}
}

func TestHandleCreateTask_InvalidPriority(t *testing.T) {
	h, _ := setupHandler(t)

	mux := http.NewServeMux()
	h.RegisterRoutes(mux)

	body := `{"title": "Fix bug", "target_repo": "dacort/test", "priority": "urgent"}`
	req := httptest.NewRequest(http.MethodPost, "/api/v1/tasks", bytes.NewBufferString(body))
	w := httptest.NewRecorder()
	mux.ServeHTTP(w, req)

	if w.Code != http.StatusBadRequest {
		t.Fatalf("expected 400, got %d", w.Code)
	}
}

func TestHandleCreateTask_HighPriority(t *testing.T) {
	h, _ := setupHandler(t)

	mux := http.NewServeMux()
	h.RegisterRoutes(mux)

	body := `{
		"title": "Critical fix",
		"target_repo": "dacort/test",
		"priority": "high",
		"profile": "medium"
	}`
	req := httptest.NewRequest(http.MethodPost, "/api/v1/tasks", strings.NewReader(body))
	w := httptest.NewRecorder()
	mux.ServeHTTP(w, req)

	if w.Code != http.StatusCreated {
		t.Fatalf("expected 201, got %d: %s", w.Code, w.Body.String())
	}

	var resp createTaskResponse
	json.NewDecoder(w.Body).Decode(&resp)

	// Verify the task was actually enqueued with high priority
	task, err := h.Queue.Get(context.Background(), resp.ID)
	if err != nil {
		t.Fatalf("task not found in queue: %v", err)
	}
	if task.Priority != queue.PriorityHigh {
		t.Errorf("expected high priority (%d), got %d", queue.PriorityHigh, task.Priority)
	}
}

// ─── Helper unit tests ────────────────────────────────────────────────────────

func TestGenerateTaskID(t *testing.T) {
	id := generateTaskID("Fix the broken vitals test")
	if !strings.HasPrefix(id, "fix-the-broken-vitals-test") {
		t.Errorf("unexpected slug: %q", id)
	}
	// Should have a 4-char hex suffix
	parts := strings.Split(id, "-")
	suffix := parts[len(parts)-1]
	if len(suffix) != 4 {
		t.Errorf("expected 4-char suffix, got %q", suffix)
	}
}

func TestGenerateTaskID_LongTitle(t *testing.T) {
	long := strings.Repeat("a-very-long-word-", 10)
	id := generateTaskID(long)
	// Base slug should be ≤40 chars, plus 5 for -xxxx suffix
	base := strings.Join(strings.Split(id, "-")[:len(strings.Split(id, "-"))-1], "-")
	if len(base) > 40 {
		t.Errorf("slug base too long: %d chars (%q)", len(base), base)
	}
}

func TestTaskJobName(t *testing.T) {
	tests := []struct {
		id   string
		want string
	}{
		{"cos-server", "claude-os-cos-server"},
		{"my_task_123", "claude-os-my-task-123"},
		{"Task With Spaces!", "claude-os-taskwithspaces"},
	}
	for _, tt := range tests {
		got := taskJobName(tt.id)
		if got != tt.want {
			t.Errorf("taskJobName(%q) = %q, want %q", tt.id, got, tt.want)
		}
	}
}

func TestParseLogLines(t *testing.T) {
	raw := "2026-03-21T14:02:33Z Starting up\nplain line\n2026-03-21T14:02:35Z Done.\n"
	lines := parseLogLines(raw)

	if len(lines) != 3 {
		t.Fatalf("expected 3 lines, got %d", len(lines))
	}
	if lines[0].TS == nil {
		t.Error("expected timestamp on first line")
	}
	if lines[0].Text != "Starting up" {
		t.Errorf("unexpected text: %q", lines[0].Text)
	}
	if lines[1].TS != nil {
		t.Error("plain line should have no timestamp")
	}
	if lines[1].Text != "plain line" {
		t.Errorf("unexpected text: %q", lines[1].Text)
	}
}

func TestParseLogLines_Empty(t *testing.T) {
	lines := parseLogLines("")
	if len(lines) != 0 {
		t.Errorf("expected 0 lines for empty input, got %d", len(lines))
	}
}

// ─── Signal endpoint tests ────────────────────────────────────────────────────

// fakeGitSyncer is a test double that writes files to a temp dir without git.
type fakeGitSyncer struct {
	dir     string
	pushErr error
	pushed  int
}

func (f *fakeGitSyncer) LocalPath() string          { return f.dir }
func (f *fakeGitSyncer) CommitAndPush(msg string) error { f.pushed++; return f.pushErr }

func newSignalHandler(t *testing.T) (*Handler, *fakeGitSyncer) {
	t.Helper()
	h, _ := setupHandler(t)
	dir := t.TempDir()
	// Create the knowledge subdirectory
	if err := os.MkdirAll(filepath.Join(dir, "knowledge"), 0755); err != nil {
		t.Fatalf("mkdir knowledge: %v", err)
	}
	gs := &fakeGitSyncer{dir: dir}
	h.GitSyncer = gs
	return h, gs
}

func TestHandleGetSignal_NoFile(t *testing.T) {
	h, _ := newSignalHandler(t)

	mux := http.NewServeMux()
	h.RegisterRoutes(mux)

	req := httptest.NewRequest(http.MethodGet, "/api/v1/signal", nil)
	w := httptest.NewRecorder()
	mux.ServeHTTP(w, req)

	if w.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d: %s", w.Code, w.Body.String())
	}
	var resp map[string]any
	json.NewDecoder(w.Body).Decode(&resp)
	if resp["signal"] != nil {
		t.Errorf("expected null signal, got %v", resp["signal"])
	}
}

func TestHandleSetSignal_RoundTrip(t *testing.T) {
	h, gs := newSignalHandler(t)

	mux := http.NewServeMux()
	h.RegisterRoutes(mux)

	body := `{"title": "hello from dacort", "message": "are you there?"}`
	req := httptest.NewRequest(http.MethodPost, "/api/v1/signal", strings.NewReader(body))
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()
	mux.ServeHTTP(w, req)

	if w.Code != http.StatusCreated {
		t.Fatalf("expected 201, got %d: %s", w.Code, w.Body.String())
	}
	var resp signalResponse
	if err := json.NewDecoder(w.Body).Decode(&resp); err != nil {
		t.Fatalf("decode: %v", err)
	}
	if resp.Title != "hello from dacort" {
		t.Errorf("unexpected title: %q", resp.Title)
	}
	if resp.Body != "are you there?" {
		t.Errorf("unexpected body: %q", resp.Body)
	}
	if gs.pushed != 1 {
		t.Errorf("expected 1 push, got %d", gs.pushed)
	}

	// Verify we can read it back
	req2 := httptest.NewRequest(http.MethodGet, "/api/v1/signal", nil)
	w2 := httptest.NewRecorder()
	mux.ServeHTTP(w2, req2)

	var resp2 signalResponse
	json.NewDecoder(w2.Body).Decode(&resp2)
	if resp2.Title != "hello from dacort" {
		t.Errorf("GET after POST: unexpected title: %q", resp2.Title)
	}
}

func TestHandleSetSignal_MissingMessage(t *testing.T) {
	h, _ := newSignalHandler(t)

	mux := http.NewServeMux()
	h.RegisterRoutes(mux)

	body := `{"title": "no message here"}`
	req := httptest.NewRequest(http.MethodPost, "/api/v1/signal", strings.NewReader(body))
	w := httptest.NewRecorder()
	mux.ServeHTTP(w, req)

	if w.Code != http.StatusBadRequest {
		t.Fatalf("expected 400, got %d", w.Code)
	}
}

func TestHandleClearSignal(t *testing.T) {
	h, gs := newSignalHandler(t)

	// Write a signal file first
	sigPath := filepath.Join(h.GitSyncer.LocalPath(), "knowledge", "signal.md")
	os.WriteFile(sigPath, []byte("## Signal · 2026-04-18 22:00 UTC\n**test**\n\nhello\n"), 0644)

	mux := http.NewServeMux()
	h.RegisterRoutes(mux)

	req := httptest.NewRequest(http.MethodDelete, "/api/v1/signal", nil)
	w := httptest.NewRecorder()
	mux.ServeHTTP(w, req)

	if w.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d: %s", w.Code, w.Body.String())
	}
	if gs.pushed != 1 {
		t.Errorf("expected 1 push after clear, got %d", gs.pushed)
	}

	// Signal file should now contain the cleared marker
	content, _ := os.ReadFile(sigPath)
	if !strings.Contains(string(content), "no signal") {
		t.Errorf("expected cleared signal file, got: %s", content)
	}
}

func TestHandleGetSignal_NoSyncer(t *testing.T) {
	h, _ := setupHandler(t) // no GitSyncer

	mux := http.NewServeMux()
	h.RegisterRoutes(mux)

	req := httptest.NewRequest(http.MethodGet, "/api/v1/signal", nil)
	w := httptest.NewRecorder()
	mux.ServeHTTP(w, req)

	// Should return 503 (service unavailable) when no syncer configured
	if w.Code != http.StatusServiceUnavailable {
		t.Fatalf("expected 503, got %d: %s", w.Code, w.Body.String())
	}
}
