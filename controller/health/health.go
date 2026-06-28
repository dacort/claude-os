// Package health turns agent-health canary task results into deduplicated
// GitHub issues.
//
// Canary tasks (tasks/scheduled/agent-health-<agent>.md) exercise each agent
// backend through the real dispatch path on a daily cron. When one fails, the
// controller opens (or updates) a single issue per agent; when the next run
// succeeds, the issue is closed. Open-on-fail / dedup / close-on-recover all
// fall out of the existing comms.Manager (Notify dedups by TaskID,
// Close is idempotent), so this package is just the glue.
package health

import (
	"context"
	"fmt"
	"strings"

	"github.com/dacort/claude-os/controller/comms"
)

// Prefix marks a task as an agent-health canary. Task IDs look like
// "agent-health-codex", "agent-health-claude", "agent-health-gemini".
const Prefix = "agent-health-"

// Notifier is the subset of comms.Manager this package needs.
type Notifier interface {
	Notify(ctx context.Context, msg comms.Message) error
	Close(ctx context.Context, id string) error
}

// IsCanary reports whether taskID belongs to an agent-health canary.
func IsCanary(taskID string) bool {
	return strings.HasPrefix(taskID, Prefix) && len(taskID) > len(Prefix)
}

// Agent extracts the agent name from a canary task ID
// ("agent-health-codex" -> "codex"). Returns "" if taskID is not a canary.
func Agent(taskID string) string {
	if !IsCanary(taskID) {
		return ""
	}
	return strings.TrimPrefix(taskID, Prefix)
}

// HandleTerminal reacts to a finished canary task. On failure it opens/updates
// the agent's health issue; on success it closes any open one. It is a no-op
// for non-canary task IDs, so callers can hand it every terminal task.
func HandleTerminal(ctx context.Context, n Notifier, taskID string, succeeded bool, logs string) error {
	if !IsCanary(taskID) {
		return nil
	}
	agent := Agent(taskID)

	if succeeded {
		// Quiet on success — close the issue if one is open, idempotent otherwise.
		return n.Close(ctx, taskID)
	}

	return n.Notify(ctx, comms.Message{
		ID:      taskID,
		TaskID:  taskID,
		Type:    comms.NeedsHuman, // yields the needs-human label that dedup/close key on
		Project: "agent-health",
		Title:   fmt.Sprintf("Agent unhealthy: %s", agent),
		Body:    buildBody(agent, logs),
	})
}

// buildBody renders the issue body: what failed, the most relevant error line,
// a short log tail, and pointers to the remediation runbooks.
func buildBody(agent, logs string) string {
	var b strings.Builder
	fmt.Fprintf(&b, "The daily `%s` health canary failed, which means a real task routed to "+
		"`%s` would likely fail too.\n\n", agent, agent)

	if line := firstErrorLine(logs); line != "" {
		fmt.Fprintf(&b, "**Likely cause:** `%s`\n\n", line)
	}

	fmt.Fprintf(&b, "<details><summary>Log tail</summary>\n\n```\n%s\n```\n</details>\n\n", logTail(logs, 25))

	b.WriteString("**Remediation pointers**\n")
	switch agent {
	case "codex":
		b.WriteString("- Expired token → re-run `codex login`, recreate the `claude-os-codex` secret.\n")
		b.WriteString("- `400 not supported` / `requires a newer version` → the pinned `CODEX_MODEL` " +
			"and the worker's codex CLI version are coupled; bump them together (see claude-os#22, #23).\n")
	case "claude":
		b.WriteString("- Auth failure → the `CLAUDE_CODE_OAUTH_TOKEN` in `claude-os-oauth` may have expired; " +
			"regenerate with `claude setup-token`.\n")
	case "gemini":
		b.WriteString("- Gemini is not configured by default (no API key). This issue is expected until " +
			"a `gemini` secret is added; close it if gemini is intentionally disabled.\n")
	default:
		b.WriteString("- Check the agent's auth secret and pinned model.\n")
	}

	b.WriteString("\n_Filed automatically by the agent health check. This issue dedups by task ID and " +
		"closes itself when the next canary run succeeds._")
	return b.String()
}

// firstErrorLine returns the first line that looks like an error signal, for a
// one-line "likely cause" summary.
func firstErrorLine(logs string) string {
	for _, raw := range strings.Split(logs, "\n") {
		line := strings.TrimSpace(raw)
		lower := strings.ToLower(line)
		if strings.HasPrefix(line, "ERROR") || strings.Contains(lower, "error\"") ||
			strings.Contains(lower, "invalid_request") || strings.Contains(lower, "not supported") ||
			strings.Contains(lower, "requires a newer version") {
			return truncate(line, 200)
		}
	}
	return ""
}

// logTail returns the last n non-empty lines of logs.
func logTail(logs string, n int) string {
	lines := strings.Split(strings.TrimRight(logs, "\n"), "\n")
	out := make([]string, 0, n)
	for i := len(lines) - 1; i >= 0 && len(out) < n; i-- {
		if strings.TrimSpace(lines[i]) == "" {
			continue
		}
		out = append([]string{lines[i]}, out...)
	}
	if len(out) == 0 {
		return "(no logs available)"
	}
	return strings.Join(out, "\n")
}

func truncate(s string, max int) string {
	if len(s) <= max {
		return s
	}
	return s[:max] + "…"
}
