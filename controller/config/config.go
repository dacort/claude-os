package config

import (
	"os"
	"time"

	"gopkg.in/yaml.v3"
)

type Config struct {
	Server    ServerConfig    `yaml:"server"`
	Redis     RedisConfig     `yaml:"redis"`
	Git       GitConfig       `yaml:"git"`
	Scheduler SchedulerConfig `yaml:"scheduler"`
	Worker    WorkerConfig    `yaml:"worker"`
}

type ServerConfig struct {
	Port        int    `yaml:"port"`
	WebhookPath string `yaml:"webhook_path"`
}

type RedisConfig struct {
	Address string `yaml:"address"`
}

type GitConfig struct {
	Repo         string `yaml:"repo"`
	Branch       string `yaml:"branch"`
	PollInterval string `yaml:"poll_interval"`
	TasksPath    string `yaml:"tasks_path"`
}

func (g GitConfig) PollDuration() time.Duration {
	d, _ := time.ParseDuration(g.PollInterval)
	if d == 0 {
		return 5 * time.Minute
	}
	return d
}

type SchedulerConfig struct {
	MaxConcurrentJobs     int    `yaml:"max_concurrent_jobs"`
	JobTTLAfterFinished   string `yaml:"job_ttl_after_finished"`
	TaskTimeout           string `yaml:"task_timeout"`
	CreativeModeEnabled   bool   `yaml:"creative_mode_enabled"`
	CreativeIdleThreshold string `yaml:"creative_idle_threshold"`

	// Project-aware Workshop (v2): scan this directory for project.md files.
	// Leave empty to disable project work selection.
	ProjectsDir string `yaml:"projects_dir"`
	// ProjectWeight is the 0-100 probability of picking project work vs
	// free-form creative time. Default 70 when unset (applied in NewWorkshop).
	ProjectWeight int `yaml:"project_weight"`
}

func (s SchedulerConfig) TTLDuration() time.Duration {
	d, _ := time.ParseDuration(s.JobTTLAfterFinished)
	if d == 0 {
		return time.Hour
	}
	return d
}

// TaskTimeoutDuration returns the max time a task job may run before being killed.
// Default is 2 hours — generous enough for long creative sessions, firm enough
// to prevent runaway jobs from consuming resources forever.
func (s SchedulerConfig) TaskTimeoutDuration() time.Duration {
	d, _ := time.ParseDuration(s.TaskTimeout)
	if d == 0 {
		return 2 * time.Hour
	}
	return d
}

func (s SchedulerConfig) IdleThreshold() time.Duration {
	d, _ := time.ParseDuration(s.CreativeIdleThreshold)
	if d == 0 {
		return 15 * time.Minute
	}
	return d
}

type WorkerConfig struct {
	Image          string `yaml:"image"`
	Namespace      string `yaml:"namespace"`
	ServiceAccount string `yaml:"service_account"`
}

func Load(path string) (*Config, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}
	var cfg Config
	if err := yaml.Unmarshal(data, &cfg); err != nil {
		return nil, err
	}
	return &cfg, nil
}
