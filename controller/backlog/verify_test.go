package backlog

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/dacort/claude-os/controller/queue"
)

// verifyTestServer fakes the three GitHub endpoints VerifyArtifact uses.
func verifyTestServer(t *testing.T) *httptest.Server {
	t.Helper()
	mux := http.NewServeMux()
	// Home-repo PR #5: merged.
	mux.HandleFunc("/repos/dacort/claude-os/pulls/5", func(w http.ResponseWriter, r *http.Request) {
		json.NewEncoder(w).Encode(map[string]any{"merged": true, "state": "closed"})
	})
	// Home-repo PR #6: open, not merged.
	mux.HandleFunc("/repos/dacort/claude-os/pulls/6", func(w http.ResponseWriter, r *http.Request) {
		json.NewEncoder(w).Encode(map[string]any{"merged": false, "state": "open"})
	})
	// Foreign-repo PR #7: open with green checks.
	mux.HandleFunc("/repos/dacort/talos-homelab/pulls/7", func(w http.ResponseWriter, r *http.Request) {
		json.NewEncoder(w).Encode(map[string]any{
			"merged": false, "state": "open",
			"head": map[string]string{"sha": "abc123"},
		})
	})
	mux.HandleFunc("/repos/dacort/talos-homelab/commits/abc123/check-runs", func(w http.ResponseWriter, r *http.Request) {
		json.NewEncoder(w).Encode(map[string]any{
			"total_count": 1,
			"check_runs":  []map[string]string{{"status": "completed", "conclusion": "success"}},
		})
	})
	// Issue #8: closed.
	mux.HandleFunc("/repos/dacort/claude-os/issues/8", func(w http.ResponseWriter, r *http.Request) {
		json.NewEncoder(w).Encode(map[string]any{"state": "closed"})
	})
	return httptest.NewServer(mux)
}

func TestVerifyArtifact(t *testing.T) {
	srv := verifyTestServer(t)
	defer srv.Close()

	c := NewClient("dacort", "claude-os", "test-token")
	c.baseURL = srv.URL

	tests := []struct {
		name     string
		artifact queue.ResultArtifact
		want     bool
	}{
		{"merged home-repo PR", queue.ResultArtifact{Type: "pr", URL: "https://github.com/dacort/claude-os/pull/5"}, true},
		{"open home-repo PR not merged", queue.ResultArtifact{Type: "pr", URL: "https://github.com/dacort/claude-os/pull/6"}, false},
		{"open foreign PR with green CI", queue.ResultArtifact{Type: "pr", URL: "https://github.com/dacort/talos-homelab/pull/7"}, true},
		{"closed issue", queue.ResultArtifact{Type: "issue", URL: "https://github.com/dacort/claude-os/issues/8"}, true},
		{"bare commit earns nothing", queue.ResultArtifact{Type: "commit", Ref: "abc123"}, false},
		{"file earns nothing", queue.ResultArtifact{Type: "file", Path: "knowledge/x.md"}, false},
		{"garbage URL", queue.ResultArtifact{Type: "pr", URL: "https://example.com/nope"}, false},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			if got := c.VerifyArtifact(context.Background(), tt.artifact); got != tt.want {
				t.Errorf("VerifyArtifact(%+v) = %v, want %v", tt.artifact, got, tt.want)
			}
		})
	}
}
