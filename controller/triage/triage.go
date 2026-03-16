package triage

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"log/slog"
	"net/http"
	"strings"
	"sync"
	"time"
)

// AgentInfo tracks an agent's availability.
type AgentInfo struct {
	Available bool
}

// AgentStatus is the current state of all agents.
type AgentStatus struct {
	Claude AgentInfo
	Codex  AgentInfo
}

// Triager calls the Haiku API to assess incoming tasks and recommend routing.
type Triager struct {
	apiURL   string
	apiKey   string
	client   *http.Client
	mu       sync.Mutex
	failures int
	disabled bool
	maxFails int
}

const triageModel = "claude-haiku-4-5"

// NewTriager returns a Triager configured to call the Anthropic API at apiURL.
func NewTriager(apiURL, apiKey string) *Triager {
	return &Triager{
		apiURL:   apiURL,
		apiKey:   apiKey,
		client:   &http.Client{Timeout: 5 * time.Second},
		maxFails: 3,
	}
}

// IsDisabled returns true when the circuit breaker is open.
func (t *Triager) IsDisabled() bool {
	t.mu.Lock()
	defer t.mu.Unlock()
	return t.disabled
}

// reEnable resets the circuit breaker after a successful API call.
func (t *Triager) reEnable() {
	t.mu.Lock()
	defer t.mu.Unlock()
	t.failures = 0
	t.disabled = false
}

// recordFailure increments the failure counter and opens the circuit breaker
// after maxFails consecutive failures.
func (t *Triager) recordFailure() {
	t.mu.Lock()
	defer t.mu.Unlock()
	t.failures++
	if t.failures >= t.maxFails {
		t.disabled = true
		slog.Warn("triage: disabled after consecutive failures", "failures", t.failures)
	}
}

// Assess calls the Haiku API to classify a task and recommend routing.
// Returns an error if the call fails; caller should fall back to HeuristicRoute.
func (t *Triager) Assess(ctx context.Context, title, description string, agents AgentStatus) (Verdict, error) {
	if t.IsDisabled() {
		return Verdict{}, fmt.Errorf("triage disabled (circuit breaker open)")
	}

	prompt := buildTriagePrompt(title, description, agents)

	body := map[string]interface{}{
		"model":      triageModel,
		"max_tokens": 256,
		"messages": []map[string]string{
			{"role": "user", "content": prompt},
		},
	}
	bodyJSON, err := json.Marshal(body)
	if err != nil {
		return Verdict{}, fmt.Errorf("marshal request: %w", err)
	}

	req, err := http.NewRequestWithContext(ctx, "POST", t.apiURL+"/v1/messages", bytes.NewReader(bodyJSON))
	if err != nil {
		return Verdict{}, fmt.Errorf("create request: %w", err)
	}
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("x-api-key", t.apiKey)
	req.Header.Set("anthropic-version", "2023-06-01")

	resp, err := t.client.Do(req)
	if err != nil {
		t.recordFailure()
		return Verdict{}, fmt.Errorf("API call: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		t.recordFailure()
		respBody, _ := io.ReadAll(resp.Body)
		return Verdict{}, fmt.Errorf("API returned %d: %s", resp.StatusCode, string(respBody))
	}

	var apiResp struct {
		Content []struct {
			Type string `json:"type"`
			Text string `json:"text"`
		} `json:"content"`
	}
	if err := json.NewDecoder(resp.Body).Decode(&apiResp); err != nil {
		t.recordFailure()
		return Verdict{}, fmt.Errorf("decode response: %w", err)
	}

	if len(apiResp.Content) == 0 {
		t.recordFailure()
		return Verdict{}, fmt.Errorf("empty response content")
	}

	verdictText := stripMarkdownFencing(apiResp.Content[0].Text)

	var verdict Verdict
	if err := json.Unmarshal([]byte(verdictText), &verdict); err != nil {
		t.recordFailure()
		return Verdict{}, fmt.Errorf("parse verdict JSON: %w", err)
	}

	t.reEnable()

	slog.Info("triage verdict",
		"title", title,
		"complexity", verdict.Complexity,
		"model", verdict.RecommendedModel,
		"agent", verdict.RecommendedAgent,
		"needs_plan", verdict.NeedsPlan,
		"reasoning", verdict.Reasoning,
	)

	return verdict, nil
}

// stripMarkdownFencing removes ```json ... ``` wrapping that LLMs often add
// despite being told to return raw JSON.
func stripMarkdownFencing(s string) string {
	s = strings.TrimSpace(s)
	if strings.HasPrefix(s, "```") {
		// Remove opening fence (```json or ```)
		if idx := strings.Index(s, "\n"); idx != -1 {
			s = s[idx+1:]
		}
		// Remove closing fence
		if idx := strings.LastIndex(s, "```"); idx != -1 {
			s = s[:idx]
		}
		s = strings.TrimSpace(s)
	}
	return s
}

func buildTriagePrompt(title, description string, agents AgentStatus) string {
	return fmt.Sprintf(`You are the triage brain for Claude OS. Classify this task and recommend routing.

Routing rules:
- Code review / security scan / focused coding → agent: codex
- Complex reasoning / orchestration / creative → agent: claude
- Design / architecture thinking → model: claude-opus-4-6, agent: claude
- Simple lint / format / validation / typo fix → model: claude-haiku-4-5
- General implementation → model: claude-sonnet-4-6

Agent availability:
- claude: available=%v
- codex: available=%v

If an agent is unavailable, route to the other one.
If the task requires multiple steps, coordination, or decomposition, set needs_plan=true.

Task title: %s
Task description: %s

Respond with ONLY a JSON object (no markdown, no explanation):
{"complexity":"simple|complex","recommended_model":"<model-id>","recommended_agent":"claude|codex","reasoning":"<one line>","needs_plan":false}`,
		agents.Claude.Available, agents.Codex.Available, title, description)
}
