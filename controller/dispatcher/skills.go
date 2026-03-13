package dispatcher

import (
	"fmt"
	"os"
	"path/filepath"
	"regexp"
	"sync"

	"gopkg.in/yaml.v3"
)

// Skill declares a context injection pattern. When a task description matches
// the Pattern, the file at Inject (relative to the claude-os repo root) is
// added to CONTEXT_REFS for that job.
type Skill struct {
	Name    string `yaml:"name"`
	Pattern string `yaml:"pattern"`
	Inject  string `yaml:"inject"`

	compiled *regexp.Regexp
}

var (
	skills   []*Skill
	skillsMu sync.RWMutex
)

// LoadSkills reads all skill.yaml files from dir and compiles their patterns.
// Call once at startup; safe to call again to reload.
func LoadSkills(dir string) error {
	entries, err := os.ReadDir(dir)
	if err != nil {
		if os.IsNotExist(err) {
			// No skills dir is fine — skills are optional
			return nil
		}
		return fmt.Errorf("read skills dir: %w", err)
	}

	var loaded []*Skill
	for _, entry := range entries {
		if !entry.IsDir() {
			continue
		}
		skillPath := filepath.Join(dir, entry.Name(), "skill.yaml")
		data, err := os.ReadFile(skillPath)
		if err != nil {
			if os.IsNotExist(err) {
				continue
			}
			return fmt.Errorf("read skill %s: %w", skillPath, err)
		}

		var s Skill
		if err := yaml.Unmarshal(data, &s); err != nil {
			return fmt.Errorf("parse skill %s: %w", skillPath, err)
		}
		if s.Pattern == "" || s.Inject == "" {
			return fmt.Errorf("skill %s missing pattern or inject field", skillPath)
		}
		compiled, err := regexp.Compile(`(?i)` + s.Pattern)
		if err != nil {
			return fmt.Errorf("compile pattern for skill %s: %w", s.Name, err)
		}
		s.compiled = compiled
		loaded = append(loaded, &s)
	}

	skillsMu.Lock()
	skills = loaded
	skillsMu.Unlock()
	return nil
}

// MatchSkills returns the inject paths for all skills whose pattern matches text.
// text is typically the task title + description.
func MatchSkills(text string) []string {
	skillsMu.RLock()
	defer skillsMu.RUnlock()

	var matches []string
	for _, s := range skills {
		if s.compiled.MatchString(text) {
			matches = append(matches, s.Inject)
		}
	}
	return matches
}
