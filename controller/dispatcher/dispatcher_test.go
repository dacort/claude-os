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
	d := New(client, "claude-os", "ghcr.io/dacort/claude-os-worker:latest")

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

func TestBurstJobHasTolerations(t *testing.T) {
	writeTestProfiles(t)
	client := fake.NewSimpleClientset()
	d := New(client, "claude-os", "ghcr.io/dacort/claude-os-worker:latest")

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
