package creative

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"path/filepath"
	"strings"
	"testing"

	"github.com/dacort/claude-os/controller/backlog"
	"github.com/dacort/claude-os/controller/ledger"
	"github.com/dacort/claude-os/controller/queue"
)

// newTestWorkshop creates a minimal Workshop for unit tests that only
// exercise OnJobFinished and related logic (no K8s or dispatcher calls).
func newTestWorkshop(t *testing.T) *Workshop {
	t.Helper()
	return &Workshop{}
}

func TestMaintenancePromptContainsContract(t *testing.T) {
	issue := backlog.Issue{
		Number: 42,
		Title:  "Fix the git index corruption recovery",
		Body:   "The controller clone corrupted on June 9.",
		URL:    "https://github.com/dacort/claude-os/issues/42",
	}
	p := maintenancePrompt(issue)

	for _, want := range []string{
		"#42",
		"Fix the git index corruption recovery",
		"https://github.com/dacort/claude-os/issues/42",
		"inspection",         // inspection pass comes first
		"octo-approved",      // explains the approval gate for filed issues
		"never merge",        // talos-homelab PRs are dacort's to merge
		"===RESULT_START===", // structured result contract
		"artifacts",          // artifact list drives credit verification
	} {
		if !strings.Contains(strings.ToLower(p), strings.ToLower(want)) {
			t.Errorf("maintenancePrompt missing %q", want)
		}
	}
}

func TestMaintenanceTaskShape(t *testing.T) {
	issue := backlog.Issue{Number: 7, Title: "Tend the certs", URL: "https://github.com/dacort/claude-os/issues/7"}
	task := maintenanceTask(issue)

	if !strings.HasPrefix(task.ID, "workshop-maint-") {
		// The "workshop" ID prefix is what SyncState and IsCreativeJob key on —
		// breaking it would orphan sessions across controller restarts.
		t.Errorf("task ID %q must keep the workshop- prefix", task.ID)
	}
	if task.ServiceAccount != "claude-os-maintenance" {
		t.Errorf("ServiceAccount = %q, want claude-os-maintenance", task.ServiceAccount)
	}
	if task.Profile != "medium" {
		t.Errorf("Profile = %q, want medium", task.Profile)
	}
}

func TestMaintenanceCompletionGrantsCredit(t *testing.T) {
	// GitHub stub: PR 5 merged; anything else 404s.
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path == "/repos/dacort/claude-os/pulls/5" {
			json.NewEncoder(w).Encode(map[string]any{"merged": true, "state": "closed"})
			return
		}
		http.NotFound(w, r)
	}))
	defer srv.Close()

	w := newTestWorkshop(t)
	led := ledger.New(filepath.Join(t.TempDir(), "credits.json"), func(string) error { return nil })
	bc := backlog.NewClientForTest("dacort", "claude-os", "tok", srv.URL)
	w.EnableMaintenance(led, bc)

	// Simulate an active maintenance session.
	w.active = true
	w.activeJob = "claude-os-workshop-maint-x"
	w.activeType = SessionMaintenance

	result := &queue.TaskResult{
		Outcome: "success",
		Artifacts: []queue.ResultArtifact{
			{Type: "pr", URL: "https://github.com/dacort/claude-os/pull/5"},
			{Type: "pr", URL: "https://github.com/dacort/claude-os/pull/999"}, // 404s — ignored
		},
	}
	w.OnJobFinished("claude-os-workshop-maint-x", result)

	if got := led.Balance(); got != 1 {
		t.Errorf("Balance() after verified maintenance session = %d, want 1 (one credit per session, not per artifact)", got)
	}
}

func TestCreativeCompletionGrantsNothing(t *testing.T) {
	w := newTestWorkshop(t)
	led := ledger.New(filepath.Join(t.TempDir(), "credits.json"), func(string) error { return nil })
	bc := backlog.NewClientForTest("dacort", "claude-os", "tok", "http://127.0.0.1:0")
	w.EnableMaintenance(led, bc)

	w.active = true
	w.activeJob = "claude-os-workshop-x"
	w.activeType = SessionCreativeFree

	w.OnJobFinished("claude-os-workshop-x", &queue.TaskResult{
		Outcome:   "success",
		Artifacts: []queue.ResultArtifact{{Type: "pr", URL: "https://github.com/dacort/claude-os/pull/5"}},
	})

	if got := led.Balance(); got != 0 {
		t.Errorf("Balance() after creative session = %d, want 0", got)
	}
}
