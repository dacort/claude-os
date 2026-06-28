package health

import (
	"context"
	"strings"
	"testing"

	"github.com/dacort/claude-os/controller/comms"
)

// fakeNotifier records Notify/Close calls.
type fakeNotifier struct {
	notified []comms.Message
	closed   []string
}

func (f *fakeNotifier) Notify(_ context.Context, msg comms.Message) error {
	f.notified = append(f.notified, msg)
	return nil
}

func (f *fakeNotifier) Close(_ context.Context, id string) error {
	f.closed = append(f.closed, id)
	return nil
}

func TestIsCanary(t *testing.T) {
	cases := map[string]bool{
		"agent-health-codex":  true,
		"agent-health-claude": true,
		"agent-health-":       false, // empty agent
		"agent-health":        false,
		"codex-review-foo":    false,
		"":                    false,
	}
	for id, want := range cases {
		if got := IsCanary(id); got != want {
			t.Errorf("IsCanary(%q) = %v, want %v", id, got, want)
		}
	}
}

func TestAgent(t *testing.T) {
	if got := Agent("agent-health-codex"); got != "codex" {
		t.Errorf("Agent() = %q, want codex", got)
	}
	if got := Agent("not-a-canary"); got != "" {
		t.Errorf("Agent(non-canary) = %q, want empty", got)
	}
}

func TestHandleTerminal_FailureOpensIssue(t *testing.T) {
	n := &fakeNotifier{}
	logs := "ERROR: {\"type\":\"error\",\"message\":\"The 'gpt-5.5' model requires a newer version of Codex.\"}\nExit code: 1"

	if err := HandleTerminal(context.Background(), n, "agent-health-codex", false, logs); err != nil {
		t.Fatalf("HandleTerminal returned error: %v", err)
	}

	if len(n.notified) != 1 {
		t.Fatalf("expected 1 Notify, got %d", len(n.notified))
	}
	msg := n.notified[0]
	if msg.TaskID != "agent-health-codex" {
		t.Errorf("TaskID = %q, want agent-health-codex", msg.TaskID)
	}
	if msg.Type != comms.NeedsHuman {
		t.Errorf("Type = %q, want needs-human (dedup/close key on it)", msg.Type)
	}
	if msg.Project != "agent-health" {
		t.Errorf("Project = %q, want agent-health", msg.Project)
	}
	if !strings.Contains(msg.Title, "codex") {
		t.Errorf("Title %q should name the agent", msg.Title)
	}
	if !strings.Contains(msg.Body, "requires a newer version") {
		t.Errorf("Body should surface the error line, got: %s", msg.Body)
	}
	if len(n.closed) != 0 {
		t.Errorf("failure should not Close, got %v", n.closed)
	}
}

func TestHandleTerminal_SuccessClosesIssue(t *testing.T) {
	n := &fakeNotifier{}
	if err := HandleTerminal(context.Background(), n, "agent-health-claude", true, "OK"); err != nil {
		t.Fatalf("HandleTerminal returned error: %v", err)
	}
	if len(n.closed) != 1 || n.closed[0] != "agent-health-claude" {
		t.Errorf("expected Close(agent-health-claude), got %v", n.closed)
	}
	if len(n.notified) != 0 {
		t.Errorf("success should not Notify, got %d", len(n.notified))
	}
}

func TestHandleTerminal_IgnoresNonCanary(t *testing.T) {
	n := &fakeNotifier{}
	// A normal task failing must not touch the health-issue machinery.
	if err := HandleTerminal(context.Background(), n, "codex-review-ghostband", false, "boom"); err != nil {
		t.Fatalf("HandleTerminal returned error: %v", err)
	}
	if len(n.notified) != 0 || len(n.closed) != 0 {
		t.Errorf("non-canary task should be a no-op, got notify=%d close=%d", len(n.notified), len(n.closed))
	}
}

func TestBuildBody_GeminiNotConfigured(t *testing.T) {
	body := buildBody("gemini", "no API key configured")
	if !strings.Contains(body, "not configured") {
		t.Errorf("gemini body should explain it is expected when unconfigured, got: %s", body)
	}
}
