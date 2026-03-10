package dispatcher

import (
	"fmt"
	"os"
	"sync"

	"gopkg.in/yaml.v3"
)

type Toleration struct {
	Key      string `yaml:"key"`
	Operator string `yaml:"operator"`
	Value    string `yaml:"value,omitempty"`
	Effect   string `yaml:"effect"`
}

type Profile struct {
	CPURequest    string       `yaml:"cpu_request"`
	MemoryRequest string       `yaml:"memory_request"`
	ScratchSize   string       `yaml:"scratch_size"`
	Target        string       `yaml:"target"`
	DefaultModel  string       `yaml:"default_model"`
	Tolerations   []Toleration `yaml:"tolerations,omitempty"`
}

var (
	profiles map[string]Profile
	mu       sync.RWMutex
)

func LoadProfiles(path string) error {
	data, err := os.ReadFile(path)
	if err != nil {
		return fmt.Errorf("read profiles: %w", err)
	}
	var raw struct {
		Profiles map[string]Profile `yaml:"profiles"`
	}
	if err := yaml.Unmarshal(data, &raw); err != nil {
		return fmt.Errorf("parse profiles: %w", err)
	}
	mu.Lock()
	profiles = raw.Profiles
	mu.Unlock()
	return nil
}

func GetProfile(name string) (*Profile, error) {
	mu.RLock()
	defer mu.RUnlock()
	p, ok := profiles[name]
	if !ok {
		return nil, fmt.Errorf("unknown profile: %s", name)
	}
	return &p, nil
}
