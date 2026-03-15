package triage

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
)

func TestAssess_Success(t *testing.T) {
	// Mock Anthropic API returning a triage verdict
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Header.Get("x-api-key") != "test-key" {
			t.Error("expected x-api-key header")
		}
		if r.Header.Get("anthropic-version") == "" {
			t.Error("expected anthropic-version header")
		}
		// Return a mock response with the verdict in the text content
		resp := map[string]interface{}{
			"content": []map[string]interface{}{
				{"type": "text", "text": `{"complexity":"simple","recommended_model":"claude-sonnet-4-6","recommended_agent":"codex","reasoning":"focused coding task","needs_plan":false}`},
			},
		}
		json.NewEncoder(w).Encode(resp)
	}))
	defer server.Close()

	triager := NewTriager(server.URL, "test-key")
	status := AgentStatus{
		Claude: AgentInfo{Available: true},
		Codex:  AgentInfo{Available: true},
	}

	verdict, err := triager.Assess(context.Background(), "Fix the login bug", "The login endpoint returns 500", status)
	if err != nil {
		t.Fatalf("Assess failed: %v", err)
	}

	if verdict.RecommendedAgent != "codex" {
		t.Errorf("expected agent codex, got %s", verdict.RecommendedAgent)
	}
	if verdict.NeedsPlan {
		t.Error("expected needs_plan false")
	}
}

func TestAssess_Fallback(t *testing.T) {
	// Mock server that returns 500
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusInternalServerError)
	}))
	defer server.Close()

	triager := NewTriager(server.URL, "test-key")
	status := AgentStatus{
		Claude: AgentInfo{Available: true},
		Codex:  AgentInfo{Available: true},
	}

	_, err := triager.Assess(context.Background(), "Design the API", "Architect the endpoints", status)
	if err == nil {
		t.Fatal("expected error from 500 response")
	}

	// Caller should fall back to heuristic
	verdict := HeuristicRoute("Design the API", "Architect the endpoints")
	if verdict.RecommendedModel != "claude-opus-4-6" {
		t.Errorf("heuristic should route design to opus, got %s", verdict.RecommendedModel)
	}
}

func TestAssess_CircuitBreaker(t *testing.T) {
	callCount := 0
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		callCount++
		w.WriteHeader(http.StatusInternalServerError)
	}))
	defer server.Close()

	triager := NewTriager(server.URL, "test-key")
	status := AgentStatus{Claude: AgentInfo{Available: true}}

	// Fail 3 times to trip circuit breaker
	for i := 0; i < 3; i++ {
		triager.Assess(context.Background(), "task", "desc", status)
	}

	if !triager.IsDisabled() {
		t.Error("expected triager to be disabled after 3 failures")
	}

	// Next call should not hit the server
	beforeCount := callCount
	_, err := triager.Assess(context.Background(), "task", "desc", status)
	if err == nil {
		t.Error("expected error when triager is disabled")
	}
	if callCount != beforeCount {
		t.Error("disabled triager should not make API calls")
	}
}
