package dispatcher

import (
	"context"
	"os"
	"path/filepath"
	"testing"

	"github.com/dacort/claude-os/controller/queue"
	"k8s.io/client-go/kubernetes/fake"
)

func writeSkillDir(t *testing.T, name, pattern, inject string) string {
	t.Helper()
	dir := t.TempDir()
	skillDir := filepath.Join(dir, name)
	os.MkdirAll(skillDir, 0755)
	content := "name: " + name + "\npattern: \"" + pattern + "\"\ninject: " + inject + "\n"
	os.WriteFile(filepath.Join(skillDir, "skill.yaml"), []byte(content), 0644)
	return dir
}

func TestLoadSkillsMissingDir(t *testing.T) {
	// A missing dir should not be an error
	if err := LoadSkills("/nonexistent/path"); err != nil {
		t.Errorf("expected no error for missing dir, got: %v", err)
	}
}

func TestLoadAndMatchSkills(t *testing.T) {
	dir := t.TempDir()

	// Write two skills
	os.MkdirAll(filepath.Join(dir, "pr-review"), 0755)
	os.WriteFile(filepath.Join(dir, "pr-review", "skill.yaml"), []byte(`
name: pr-review
pattern: "review.*pull request|pull request.*review|PR review|review.*PR"
inject: knowledge/skills/pr-review/context.md
`), 0644)

	os.MkdirAll(filepath.Join(dir, "go-testing"), 0755)
	os.WriteFile(filepath.Join(dir, "go-testing", "skill.yaml"), []byte(`
name: go-testing
pattern: "go test|golang.*test|fix.*test|failing test"
inject: knowledge/skills/go-testing/context.md
`), 0644)

	if err := LoadSkills(dir); err != nil {
		t.Fatalf("LoadSkills: %v", err)
	}
	t.Cleanup(func() {
		skillsMu.Lock()
		skills = nil
		skillsMu.Unlock()
	})

	tests := []struct {
		text    string
		wantLen int
		wantRef string
	}{
		{
			text:    "Review the pull request for the new feature",
			wantLen: 1,
			wantRef: "knowledge/skills/pr-review/context.md",
		},
		{
			text:    "Fix the failing tests in the auth package",
			wantLen: 1,
			wantRef: "knowledge/skills/go-testing/context.md",
		},
		{
			text:    "Update the README",
			wantLen: 0,
		},
	}

	for _, tt := range tests {
		t.Run(tt.text, func(t *testing.T) {
			got := MatchSkills(tt.text)
			if len(got) != tt.wantLen {
				t.Errorf("MatchSkills(%q) = %d matches, want %d; got %v", tt.text, len(got), tt.wantLen, got)
			}
			if tt.wantRef != "" {
				found := false
				for _, r := range got {
					if r == tt.wantRef {
						found = true
					}
				}
				if !found {
					t.Errorf("MatchSkills(%q): expected ref %q, got %v", tt.text, tt.wantRef, got)
				}
			}
		})
	}
}

func TestSkillsInjectedIntoJob(t *testing.T) {
	writeTestProfiles(t)

	// Set up one skill that matches the task description
	dir := t.TempDir()
	os.MkdirAll(filepath.Join(dir, "pr-review"), 0755)
	os.WriteFile(filepath.Join(dir, "pr-review", "skill.yaml"), []byte(`
name: pr-review
pattern: "pull request|PR review"
inject: knowledge/skills/pr-review/context.md
`), 0644)
	LoadSkills(dir)
	t.Cleanup(func() {
		skillsMu.Lock()
		skills = nil
		skillsMu.Unlock()
	})

	client := fake.NewSimpleClientset()
	d := New(client, "claude-os", "ghcr.io/dacort/claude-os-worker:latest")

	t.Run("skill ref auto-injected when pattern matches", func(t *testing.T) {
		task := &queue.Task{
			ID:          "skill-test-match",
			Title:       "PR review for feature branch",
			Description: "Review the pull request and give feedback",
			Profile:     "small",
		}
		job, err := d.CreateJob(context.Background(), task)
		if err != nil {
			t.Fatalf("CreateJob: %v", err)
		}
		envMap := map[string]string{}
		for _, env := range job.Spec.Template.Spec.Containers[0].Env {
			envMap[env.Name] = env.Value
		}
		if envMap["CONTEXT_REFS"] != "knowledge/skills/pr-review/context.md" {
			t.Errorf("CONTEXT_REFS = %q, want %q", envMap["CONTEXT_REFS"], "knowledge/skills/pr-review/context.md")
		}
	})

	t.Run("no skill ref when pattern does not match", func(t *testing.T) {
		task := &queue.Task{
			ID:          "skill-test-no-match",
			Title:       "Update docs",
			Description: "Fix typos in the README",
			Profile:     "small",
		}
		job, err := d.CreateJob(context.Background(), task)
		if err != nil {
			t.Fatalf("CreateJob: %v", err)
		}
		for _, env := range job.Spec.Template.Spec.Containers[0].Env {
			if env.Name == "CONTEXT_REFS" {
				t.Errorf("expected no CONTEXT_REFS but got %q", env.Value)
			}
		}
	})

	t.Run("skill ref merged with explicit context_refs, no duplicates", func(t *testing.T) {
		task := &queue.Task{
			ID:          "skill-test-merge",
			Title:       "PR review",
			Description: "Review the pull request",
			Profile:     "small",
			ContextRefs: []string{
				"knowledge/plans/my-plan.md",
				"knowledge/skills/pr-review/context.md", // already present — should not duplicate
			},
		}
		job, err := d.CreateJob(context.Background(), task)
		if err != nil {
			t.Fatalf("CreateJob: %v", err)
		}
		envMap := map[string]string{}
		for _, env := range job.Spec.Template.Spec.Containers[0].Env {
			envMap[env.Name] = env.Value
		}
		want := "knowledge/plans/my-plan.md:knowledge/skills/pr-review/context.md"
		if envMap["CONTEXT_REFS"] != want {
			t.Errorf("CONTEXT_REFS = %q, want %q", envMap["CONTEXT_REFS"], want)
		}
	})
}
