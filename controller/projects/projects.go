// Package projects parses project.md files and provides helpers for backlog
// selection and state updates. A project.md has YAML frontmatter followed by
// markdown sections: Goal, Current State, Backlog, Memory, Decisions.
package projects

import (
	"bytes"
	"fmt"
	"os"
	"path/filepath"
	"strings"

	"gopkg.in/yaml.v3"
)

// ProjectBudget describes token and model constraints for a project.
type ProjectBudget struct {
	DailyTokens int    `yaml:"daily_tokens"`
	Model       string `yaml:"model"`
}

// ProjectFrontmatter holds the YAML header fields of a project.md.
type ProjectFrontmatter struct {
	Name          string        `yaml:"name"`
	Title         string        `yaml:"title"`
	Status        string        `yaml:"status"`
	Owner         string        `yaml:"owner"`
	Reviewer      string        `yaml:"reviewer"`
	Created       string        `yaml:"created"`
	Secret        bool          `yaml:"secret"`
	BacklogSource string        `yaml:"backlog_source"`
	Budget        ProjectBudget `yaml:"budget"`
}

// BacklogItem represents a single checkbox line in the Backlog section.
type BacklogItem struct {
	Text    string // display text (trimmed)
	Done    bool   // true if [x]
	Index   int    // zero-based index among all backlog items
	RawLine string // original line as it appeared in the file
}

// Project is a parsed project.md file.
type Project struct {
	ProjectFrontmatter
	RawContent string
	Goal       string
	State      string
	Backlog    []BacklogItem
	Memory     string
	Decisions  string
}

// ParseProject parses a project.md given its name and raw bytes.
func ParseProject(name string, data []byte) (*Project, error) {
	parts := bytes.SplitN(data, []byte("---"), 3)
	// parts[0] is empty (before first ---), parts[1] is YAML, parts[2] is body
	if len(parts) < 3 {
		return nil, fmt.Errorf("project %s: missing YAML frontmatter", name)
	}

	var fm ProjectFrontmatter
	if err := yaml.Unmarshal(parts[1], &fm); err != nil {
		return nil, fmt.Errorf("project %s: parse frontmatter: %w", name, err)
	}
	// If name not set in frontmatter, use the argument
	if fm.Name == "" {
		fm.Name = name
	}

	body := string(parts[2])

	goal := extractSection(body, "Goal")
	state := extractSection(body, "Current State")
	backlogRaw := extractSection(body, "Backlog")
	memory := extractSection(body, "Memory")
	decisions := extractSection(body, "Decisions")

	backlog := parseBacklog(backlogRaw)

	return &Project{
		ProjectFrontmatter: fm,
		RawContent:         string(data),
		Goal:               goal,
		State:              state,
		Backlog:            backlog,
		Memory:             memory,
		Decisions:          decisions,
	}, nil
}

// NextBacklogItem returns the first unchecked backlog item, or nil if all are done.
func (p *Project) NextBacklogItem() *BacklogItem {
	for i := range p.Backlog {
		if !p.Backlog[i].Done {
			return &p.Backlog[i]
		}
	}
	return nil
}

// RemainingItems returns the count of unchecked backlog items.
func (p *Project) RemainingItems() int {
	count := 0
	for _, item := range p.Backlog {
		if !item.Done {
			count++
		}
	}
	return count
}

// CheckOffItem replaces the `- [ ]` marker with `- [x]` for the given item
// and returns the updated file content.
func CheckOffItem(content string, item BacklogItem) (string, error) {
	// Match the exact raw line — use the first occurrence to be safe.
	if item.RawLine == "" {
		return "", fmt.Errorf("backlog item has empty RawLine")
	}
	checked := strings.Replace(item.RawLine, "- [ ]", "- [x]", 1)
	if checked == item.RawLine {
		return "", fmt.Errorf("item %q does not contain unchecked marker", item.RawLine)
	}
	updated := strings.Replace(content, item.RawLine, checked, 1)
	if updated == content {
		return "", fmt.Errorf("raw line %q not found in content", item.RawLine)
	}
	return updated, nil
}

// UpdateCurrentState replaces the body of the "Current State" section with newState.
func UpdateCurrentState(content, newState string) (string, error) {
	return replaceSection(content, "Current State", newState)
}

// AppendMemory prepends a new dated session entry to the Memory section.
// The entry is formatted as:
//
//	### <date>
//
//	<summary>
func AppendMemory(content, date, summary string) (string, error) {
	existing := extractSection(content, "Memory")
	newEntry := fmt.Sprintf("### %s\n\n%s", date, summary)
	var newBody string
	if strings.TrimSpace(existing) == "" {
		newBody = newEntry
	} else {
		newBody = newEntry + "\n\n" + strings.TrimSpace(existing)
	}
	return replaceSection(content, "Memory", newBody)
}

// ScanProjects reads all projects/*/project.md files under projectsDir
// and returns parsed Project entries.
func ScanProjects(projectsDir string) ([]*Project, error) {
	entries, err := os.ReadDir(projectsDir)
	if err != nil {
		if os.IsNotExist(err) {
			return nil, nil
		}
		return nil, fmt.Errorf("read projects dir: %w", err)
	}

	var projects []*Project
	for _, entry := range entries {
		if !entry.IsDir() {
			continue
		}
		mdPath := filepath.Join(projectsDir, entry.Name(), "project.md")
		data, err := os.ReadFile(mdPath)
		if err != nil {
			if os.IsNotExist(err) {
				continue
			}
			return nil, fmt.Errorf("read %s: %w", mdPath, err)
		}
		p, err := ParseProject(entry.Name(), data)
		if err != nil {
			// Log and skip; don't abort the whole scan for one bad file.
			continue
		}
		projects = append(projects, p)
	}
	return projects, nil
}

// extractSection returns the trimmed content between ## heading and the next ## heading.
func extractSection(body, heading string) string {
	marker := "## " + heading
	lines := strings.Split(body, "\n")
	inside := false
	var result []string
	for _, line := range lines {
		if strings.TrimSpace(line) == marker {
			inside = true
			continue
		}
		if inside {
			if strings.HasPrefix(strings.TrimSpace(line), "## ") {
				break
			}
			result = append(result, line)
		}
	}
	return strings.TrimSpace(strings.Join(result, "\n"))
}

// replaceSection replaces the body of a ## heading section with newBody.
// It preserves surrounding sections and returns the updated full content.
func replaceSection(content, heading, newBody string) (string, error) {
	marker := "## " + heading
	lines := strings.Split(content, "\n")

	startIdx := -1
	endIdx := len(lines)

	for i, line := range lines {
		if strings.TrimSpace(line) == marker {
			startIdx = i
			continue
		}
		if startIdx >= 0 && i > startIdx && strings.HasPrefix(strings.TrimSpace(line), "## ") {
			endIdx = i
			break
		}
	}

	if startIdx == -1 {
		return "", fmt.Errorf("section %q not found", heading)
	}

	var out []string
	out = append(out, lines[:startIdx+1]...)
	out = append(out, "")
	out = append(out, newBody)
	out = append(out, "")
	// Append remaining sections (from endIdx onward), skipping leading blank lines
	remaining := lines[endIdx:]
	// Trim leading blank lines from the remaining block so we don't double-blank
	for len(remaining) > 0 && strings.TrimSpace(remaining[0]) == "" {
		remaining = remaining[1:]
	}
	if len(remaining) > 0 {
		out = append(out, remaining...)
	}

	return strings.Join(out, "\n"), nil
}

// parseBacklog converts the raw text of the Backlog section into BacklogItems.
func parseBacklog(raw string) []BacklogItem {
	var items []BacklogItem
	idx := 0
	for _, line := range strings.Split(raw, "\n") {
		trimmed := strings.TrimSpace(line)
		if strings.HasPrefix(trimmed, "- [ ]") {
			items = append(items, BacklogItem{
				Text:    strings.TrimSpace(strings.TrimPrefix(trimmed, "- [ ]")),
				Done:    false,
				Index:   idx,
				RawLine: line,
			})
			idx++
		} else if strings.HasPrefix(trimmed, "- [x]") || strings.HasPrefix(trimmed, "- [X]") {
			items = append(items, BacklogItem{
				Text:    strings.TrimSpace(trimmed[5:]),
				Done:    true,
				Index:   idx,
				RawLine: line,
			})
			idx++
		}
	}
	return items
}
