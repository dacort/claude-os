package config

import (
	"os"
	"path/filepath"
	"testing"
	"time"
)

func TestProjectWeight_Default(t *testing.T) {
	s := SchedulerConfig{}
	if got := s.ProjectWeight(); got != 70 {
		t.Errorf("ProjectWeight() with zero value = %d, want 70", got)
	}
}

func TestProjectWeight_Explicit(t *testing.T) {
	s := SchedulerConfig{WorkshopProjectWeight: 50}
	if got := s.ProjectWeight(); got != 50 {
		t.Errorf("ProjectWeight() = %d, want 50", got)
	}
}

func TestLoadConfig(t *testing.T) {
	dir := t.TempDir()
	configFile := filepath.Join(dir, "controller.yaml")
	err := os.WriteFile(configFile, []byte(`
server:
  port: 9090
  webhook_path: /hook
redis:
  address: localhost:6379
git:
  repo: https://github.com/test/test.git
  branch: main
  poll_interval: 10m
  tasks_path: tasks
scheduler:
  max_concurrent_jobs: 2
  job_ttl_after_finished: 30m
  creative_mode_enabled: false
  creative_idle_threshold: 5m
worker:
  image: test:latest
  namespace: test-ns
  service_account: test-sa
`), 0644)
	if err != nil {
		t.Fatal(err)
	}

	cfg, err := Load(configFile)
	if err != nil {
		t.Fatalf("Load failed: %v", err)
	}

	if cfg.Server.Port != 9090 {
		t.Errorf("expected port 9090, got %d", cfg.Server.Port)
	}
	if cfg.Redis.Address != "localhost:6379" {
		t.Errorf("expected localhost:6379, got %s", cfg.Redis.Address)
	}
	if cfg.Scheduler.MaxConcurrentJobs != 2 {
		t.Errorf("expected 2 concurrent jobs, got %d", cfg.Scheduler.MaxConcurrentJobs)
	}
	if cfg.Worker.Image != "test:latest" {
		t.Errorf("expected test:latest, got %s", cfg.Worker.Image)
	}
	if cfg.Git.PollDuration() != 10*time.Minute {
		t.Errorf("expected 10m poll duration, got %v", cfg.Git.PollDuration())
	}
	if cfg.Scheduler.TTLDuration() != 30*time.Minute {
		t.Errorf("expected 30m TTL, got %v", cfg.Scheduler.TTLDuration())
	}
}
