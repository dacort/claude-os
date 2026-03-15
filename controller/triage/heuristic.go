package triage

import "strings"

// Verdict is the result of triaging a task.
type Verdict struct {
	Complexity       string `json:"complexity"`        // "simple" or "complex"
	RecommendedModel string `json:"recommended_model"`
	RecommendedAgent string `json:"recommended_agent"`
	Reasoning        string `json:"reasoning"`
	NeedsPlan        bool   `json:"needs_plan"`
}

var opusKeywords = []string{"design", "architect", "plan", "think", "research", "explore", "analyze", "what if"}
var haikuKeywords = []string{"lint", "format", "validate", "check", "scan", "cleanup", "typo"}

// HeuristicRoute applies keyword-based routing rules.
// Used as fallback when the Haiku API is unavailable.
func HeuristicRoute(title, description string) Verdict {
	text := strings.ToLower(title + " " + description)

	for _, kw := range opusKeywords {
		if strings.Contains(text, kw) {
			return Verdict{
				Complexity:       "complex",
				RecommendedModel: "claude-opus-4-6",
				RecommendedAgent: "claude",
				Reasoning:        "keyword match: " + kw,
				NeedsPlan:        true,
			}
		}
	}

	for _, kw := range haikuKeywords {
		if strings.Contains(text, kw) {
			return Verdict{
				Complexity:       "simple",
				RecommendedModel: "claude-haiku-4-5",
				RecommendedAgent: "claude",
				Reasoning:        "keyword match: " + kw,
				NeedsPlan:        false,
			}
		}
	}

	// Default: Sonnet, simple
	return Verdict{
		Complexity:       "simple",
		RecommendedModel: "claude-sonnet-4-6",
		RecommendedAgent: "claude",
		Reasoning:        "default routing",
		NeedsPlan:        false,
	}
}
