package triage

import "testing"

func TestHeuristicRoute(t *testing.T) {
	tests := []struct {
		name        string
		title       string
		desc        string
		wantModel   string
		wantComplex bool
	}{
		{
			name:        "design task gets opus",
			title:       "Design the API schema",
			desc:        "Architect the REST endpoints",
			wantModel:   "claude-opus-4-6",
			wantComplex: true,
		},
		{
			name:        "implementation gets sonnet",
			title:       "Implement user login",
			desc:        "Build the login endpoint",
			wantModel:   "claude-sonnet-4-6",
			wantComplex: false,
		},
		{
			name:        "lint task gets haiku",
			title:       "Lint the Go code",
			desc:        "Run golangci-lint and fix issues",
			wantModel:   "claude-haiku-4-5",
			wantComplex: false,
		},
		{
			name:        "unknown defaults to sonnet",
			title:       "Do something",
			desc:        "A vague task",
			wantModel:   "claude-sonnet-4-6",
			wantComplex: false,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			v := HeuristicRoute(tt.title, tt.desc)
			if v.RecommendedModel != tt.wantModel {
				t.Errorf("model: got %s, want %s", v.RecommendedModel, tt.wantModel)
			}
			if v.NeedsPlan != tt.wantComplex {
				t.Errorf("needs_plan: got %v, want %v", v.NeedsPlan, tt.wantComplex)
			}
		})
	}
}
