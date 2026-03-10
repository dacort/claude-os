package webhook

import (
	"crypto/hmac"
	"crypto/sha256"
	"encoding/hex"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

func sign(secret, body string) string {
	mac := hmac.New(sha256.New, []byte(secret))
	mac.Write([]byte(body))
	return "sha256=" + hex.EncodeToString(mac.Sum(nil))
}

func TestValidSignature(t *testing.T) {
	secret := "test-secret"
	var received *IssueEvent
	h := New(secret, func(event *IssueEvent) {
		received = event
	})

	body := `{"action":"opened","issue":{"number":1,"title":"Build something","body":"## Description\nDo the thing"}}`
	sig := sign(secret, body)

	req := httptest.NewRequest(http.MethodPost, "/webhook", strings.NewReader(body))
	req.Header.Set("X-Hub-Signature-256", sig)
	req.Header.Set("X-GitHub-Event", "issues")
	w := httptest.NewRecorder()

	h.ServeHTTP(w, req)

	if w.Code != http.StatusOK {
		t.Errorf("expected 200, got %d", w.Code)
	}
	if received == nil {
		t.Fatal("callback not invoked")
	}
	if received.Issue.Title != "Build something" {
		t.Errorf("unexpected title: %s", received.Issue.Title)
	}
}

func TestInvalidSignature(t *testing.T) {
	h := New("real-secret", func(event *IssueEvent) {
		t.Error("callback should not be invoked")
	})

	body := `{"action":"opened"}`
	req := httptest.NewRequest(http.MethodPost, "/webhook", strings.NewReader(body))
	req.Header.Set("X-Hub-Signature-256", "sha256=invalid")
	req.Header.Set("X-GitHub-Event", "issues")
	w := httptest.NewRecorder()

	h.ServeHTTP(w, req)

	if w.Code != http.StatusForbidden {
		t.Errorf("expected 403, got %d", w.Code)
	}
}

func TestNonIssueEventIgnored(t *testing.T) {
	h := New("secret", func(event *IssueEvent) {
		t.Error("callback should not be invoked for push events")
	})

	body := `{"ref":"refs/heads/main"}`
	sig := sign("secret", body)
	req := httptest.NewRequest(http.MethodPost, "/webhook", strings.NewReader(body))
	req.Header.Set("X-Hub-Signature-256", sig)
	req.Header.Set("X-GitHub-Event", "push")
	w := httptest.NewRecorder()

	h.ServeHTTP(w, req)

	if w.Code != http.StatusOK {
		t.Errorf("expected 200, got %d", w.Code)
	}
}
