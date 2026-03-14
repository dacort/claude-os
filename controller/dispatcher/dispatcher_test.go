package dispatcher

import (
	"context"
	"os"
	"path/filepath"
	"testing"

	"github.com/dacort/claude-os/controller/queue"
	"k8s.io/client-go/kubernetes/fake"
)

var testProfilesYAML = `
profiles:
  small:
    cpu_request: 250m
    memory_request: 256Mi
    scratch_size: 1Gi
    target: local
    default_model: claude-sonnet-4-6
  medium:
    cpu_request: 500m
    memory_request: 512Mi
    scratch_size: 5Gi
    target: local
    default_model: claude-sonnet-4-6
  large:
    cpu_request: "2"
    memory_request: 4Gi
    scratch_size: 20Gi
    target: burst
    default_model: claude-sonnet-4-6
    tolerations:
      - key: burst.homelab.dev/cloud
        operator: Exists
        effect: NoSchedule
`

func writeTestProfiles(t *testing.T) {
	t.Helper()
	dir := t.TempDir()
	path := filepath.Join(dir, "profiles.yaml")
	os.WriteFile(path, []byte(testProfilesYAML), 0644)
	LoadProfiles(path)
}

func TestCreateJob(t *testing.T) {
	writeTestProfiles(t)
	client := fake.NewSimpleClientset()
	d := New(client, "claude-os", "ghcr.io/dacort/claude-os-worker:latest", "https://github.com/dacort/claude-os.git", "main")

	task := &queue.Task{
		ID:          "test-001",
		Title:       "Test task",
		Description: "Do something",
		TargetRepo:  "dacort/test-repo",
		Profile:     "small",
		Priority:    queue.PriorityNormal,
	}

	job, err := d.CreateJob(context.Background(), task)
	if err != nil {
		t.Fatalf("CreateJob failed: %v", err)
	}

	if job.Name != "claude-os-test-001" {
		t.Errorf("expected job name claude-os-test-001, got %s", job.Name)
	}

	container := job.Spec.Template.Spec.Containers[0]
	envMap := map[string]string{}
	for _, env := range container.Env {
		envMap[env.Name] = env.Value
	}
	if envMap["TASK_ID"] != "test-001" {
		t.Errorf("TASK_ID not set correctly")
	}
	if envMap["TARGET_REPO"] != "dacort/test-repo" {
		t.Errorf("TARGET_REPO not set correctly")
	}

	sc := container.SecurityContext
	if sc == nil || *sc.RunAsNonRoot != true {
		t.Error("expected runAsNonRoot")
	}
	if *sc.ReadOnlyRootFilesystem != true {
		t.Error("expected readOnlyRootFilesystem")
	}
	if *sc.AllowPrivilegeEscalation != false {
		t.Error("expected allowPrivilegeEscalation=false")
	}

	foundWorkspace := false
	foundHome := false
	for _, v := range job.Spec.Template.Spec.Volumes {
		if v.Name == "workspace" {
			foundWorkspace = true
		}
		if v.Name == "home" {
			foundHome = true
		}
	}
	if !foundWorkspace {
		t.Error("expected workspace volume")
	}
	if !foundHome {
		t.Error("expected home volume")
	}
}

func TestCreateJobWithAgent(t *testing.T) {
	writeTestProfiles(t)

	tests := []struct {
		name           string
		agent          string
		wantEnvAgent   string
		wantSecretName string
		wantCodexMount bool
	}{
		{
			name:           "default agent is claude",
			agent:          "",
			wantEnvAgent:   "claude",
			wantSecretName: "claude-os-oauth",
		},
		{
			name:           "explicit claude agent",
			agent:          "claude",
			wantEnvAgent:   "claude",
			wantSecretName: "claude-os-oauth",
		},
		{
			name:           "codex agent gets auth mount",
			agent:          "codex",
			wantEnvAgent:   "codex",
			wantCodexMount: true,
		},
		{
			name:           "gemini agent gets gemini secret",
			agent:          "gemini",
			wantEnvAgent:   "gemini",
			wantSecretName: "claude-os-gemini",
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			client := fake.NewSimpleClientset()
			d := New(client, "claude-os", "ghcr.io/dacort/claude-os-worker:latest", "https://github.com/dacort/claude-os.git", "main")

			task := &queue.Task{
				ID:      "agent-test",
				Title:   "Test",
				Profile: "small",
				Agent:   tt.agent,
			}

			job, err := d.CreateJob(context.Background(), task)
			if err != nil {
				t.Fatalf("CreateJob failed: %v", err)
			}

			container := job.Spec.Template.Spec.Containers[0]

			// Check TASK_AGENT env var
			envMap := map[string]string{}
			for _, env := range container.Env {
				envMap[env.Name] = env.Value
			}
			if envMap["TASK_AGENT"] != tt.wantEnvAgent {
				t.Errorf("TASK_AGENT = %q, want %q", envMap["TASK_AGENT"], tt.wantEnvAgent)
			}

			// Check secret references
			if tt.wantSecretName != "" {
				found := false
				for _, ef := range container.EnvFrom {
					if ef.SecretRef != nil && ef.SecretRef.Name == tt.wantSecretName {
						found = true
					}
				}
				if !found {
					t.Errorf("expected envFrom secret %q not found", tt.wantSecretName)
				}
			}

			// Check codex volume mount
			if tt.wantCodexMount {
				foundMount := false
				for _, m := range container.VolumeMounts {
					if m.Name == "codex-auth" && m.MountPath == "/tmp/codex-auth" {
						foundMount = true
					}
				}
				if !foundMount {
					t.Error("expected codex-auth volume mount at /tmp/codex-auth")
				}

				foundVol := false
				for _, v := range job.Spec.Template.Spec.Volumes {
					if v.Name == "codex-auth" {
						foundVol = true
					}
				}
				if !foundVol {
					t.Error("expected codex-auth volume")
				}

				if envMap["CODEX_HOME"] != "/home/worker/.codex" {
					t.Errorf("CODEX_HOME = %q, want /home/worker/.codex", envMap["CODEX_HOME"])
				}
			}
		})
	}
}

func TestModelOverride(t *testing.T) {
	writeTestProfiles(t)

	tests := []struct {
		name      string
		taskModel string
		wantModel string
	}{
		{
			name:      "no override uses profile default",
			taskModel: "",
			wantModel: "claude-sonnet-4-6",
		},
		{
			name:      "explicit model overrides profile",
			taskModel: "claude-opus-4-6",
			wantModel: "claude-opus-4-6",
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			client := fake.NewSimpleClientset()
			d := New(client, "claude-os", "ghcr.io/dacort/claude-os-worker:latest", "https://github.com/dacort/claude-os.git", "main")

			task := &queue.Task{
				ID:      "model-test",
				Profile: "small",
				Model:   tt.taskModel,
			}
			job, err := d.CreateJob(context.Background(), task)
			if err != nil {
				t.Fatalf("CreateJob failed: %v", err)
			}
			container := job.Spec.Template.Spec.Containers[0]
			envMap := map[string]string{}
			for _, env := range container.Env {
				envMap[env.Name] = env.Value
			}
			if envMap["ANTHROPIC_MODEL"] != tt.wantModel {
				t.Errorf("ANTHROPIC_MODEL = %q, want %q", envMap["ANTHROPIC_MODEL"], tt.wantModel)
			}
		})
	}
}

func TestContextRefsEnvVar(t *testing.T) {
	writeTestProfiles(t)
	client := fake.NewSimpleClientset()
	d := New(client, "claude-os", "ghcr.io/dacort/claude-os-worker:latest", "https://github.com/dacort/claude-os.git", "main")

	t.Run("no context_refs means no CONTEXT_REFS env var", func(t *testing.T) {
		task := &queue.Task{ID: "ctx-test-none", Profile: "small"}
		job, err := d.CreateJob(context.Background(), task)
		if err != nil {
			t.Fatalf("CreateJob failed: %v", err)
		}
		for _, env := range job.Spec.Template.Spec.Containers[0].Env {
			if env.Name == "CONTEXT_REFS" {
				t.Errorf("expected no CONTEXT_REFS env var, but found it with value %q", env.Value)
			}
		}
	})

	t.Run("context_refs are joined with colons", func(t *testing.T) {
		task := &queue.Task{
			ID:          "ctx-test",
			Profile:     "small",
			ContextRefs: []string{"knowledge/plans/my-plan/api-schema.md", "knowledge/preferences.md"},
		}
		job, err := d.CreateJob(context.Background(), task)
		if err != nil {
			t.Fatalf("CreateJob failed: %v", err)
		}
		envMap := map[string]string{}
		for _, env := range job.Spec.Template.Spec.Containers[0].Env {
			envMap[env.Name] = env.Value
		}
		want := "knowledge/plans/my-plan/api-schema.md:knowledge/preferences.md"
		if envMap["CONTEXT_REFS"] != want {
			t.Errorf("CONTEXT_REFS = %q, want %q", envMap["CONTEXT_REFS"], want)
		}
	})
}

func TestBurstJobHasTolerations(t *testing.T) {
	writeTestProfiles(t)
	client := fake.NewSimpleClientset()
	d := New(client, "claude-os", "ghcr.io/dacort/claude-os-worker:latest", "https://github.com/dacort/claude-os.git", "main")

	task := &queue.Task{
		ID:      "burst-001",
		Profile: "large",
	}

	job, err := d.CreateJob(context.Background(), task)
	if err != nil {
		t.Fatal(err)
	}
	if len(job.Spec.Template.Spec.Tolerations) == 0 {
		t.Error("burst job should have tolerations")
	}
}
