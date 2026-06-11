package backlog

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
)

func TestApprovedIssuesQueriesLabelAndSorts(t *testing.T) {
	var gotQuery string
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/repos/dacort/claude-os/issues" {
			t.Errorf("unexpected path %s", r.URL.Path)
		}
		gotQuery = r.URL.RawQuery
		// Out of order on purpose: normal-priority older issue, a PR (must be
		// skipped), a high-priority newer issue.
		json.NewEncoder(w).Encode([]map[string]any{
			{"number": 10, "title": "older normal", "html_url": "https://github.com/dacort/claude-os/issues/10",
				"created_at": "2026-06-01T00:00:00Z", "labels": []map[string]string{{"name": "octo-approved"}}},
			{"number": 11, "title": "a PR not an issue", "html_url": "https://github.com/dacort/claude-os/pull/11",
				"created_at": "2026-05-01T00:00:00Z", "labels": []map[string]string{{"name": "octo-approved"}},
				"pull_request": map[string]string{"url": "x"}},
			{"number": 12, "title": "newer but high", "html_url": "https://github.com/dacort/claude-os/issues/12",
				"created_at": "2026-06-08T00:00:00Z", "labels": []map[string]string{{"name": "octo-approved"}, {"name": "priority:high"}}},
		})
	}))
	defer srv.Close()

	c := NewClient("dacort", "claude-os", "test-token")
	c.baseURL = srv.URL

	issues, err := c.ApprovedIssues(context.Background())
	if err != nil {
		t.Fatalf("ApprovedIssues() error: %v", err)
	}

	for _, want := range []string{"labels=octo-approved", "state=open"} {
		if !contains(gotQuery, want) {
			t.Errorf("query %q missing %q", gotQuery, want)
		}
	}
	if len(issues) != 2 {
		t.Fatalf("got %d issues, want 2 (PR filtered out)", len(issues))
	}
	if issues[0].Number != 12 {
		t.Errorf("first issue = #%d, want #12 (priority:high beats age)", issues[0].Number)
	}
	if issues[1].Number != 10 {
		t.Errorf("second issue = #%d, want #10", issues[1].Number)
	}
}

func TestApprovedIssuesEmptyOnAPIError(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusForbidden)
	}))
	defer srv.Close()

	c := NewClient("dacort", "claude-os", "test-token")
	c.baseURL = srv.URL

	if _, err := c.ApprovedIssues(context.Background()); err == nil {
		t.Error("ApprovedIssues() on 403 = nil error, want error")
	}
}

func contains(s, sub string) bool {
	for i := 0; i+len(sub) <= len(s); i++ {
		if s[i:i+len(sub)] == sub {
			return true
		}
	}
	return false
}
