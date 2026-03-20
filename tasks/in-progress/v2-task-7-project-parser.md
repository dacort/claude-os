---
profile: medium
priority: high
status: pending
agent: claude
target_repo: dacort/claude-os
created: "2026-03-20T17:22:00Z"
---

# v2 Task 7: Project file parser

## Description

Create a new `controller/projects/` package that parses project.md files and provides backlog selection and state update helpers.

### New Files

Create `controller/projects/projects.go` with:

**Structs:**
- `ProjectFrontmatter` — name, title, status, owner, reviewer, created, secret, backlog_source, budget
- `ProjectBudget` — daily_tokens, model  
- `Project` — embeds ProjectFrontmatter + RawContent, Goal, State, Backlog, Memory, Decisions
- `BacklogItem` — Text, Done, Index, RawLine

**Functions:**
- `ParseProject(name string, data []byte) (*Project, error)` — parse YAML frontmatter + extract markdown sections (Goal, Current State, Backlog, Memory, Decisions). Parse backlog as checkbox items.
- `(p *Project) NextBacklogItem() *BacklogItem` — return first unchecked item
- `(p *Project) RemainingItems() int` — count unchecked items
- `CheckOffItem(content string, item BacklogItem) (string, error)` — replace `- [ ]` with `- [x]` for given item
- `UpdateCurrentState(content, newState string) (string, error)` — replace Current State section
- `AppendMemory(content, date, summary string) (string, error)` — prepend new session to Memory section
- `ScanProjects(projectsDir string) ([]*Project, error)` — read all `projects/*/project.md` files
- Helper: `extractSection(body, heading string) string` — extract content between ## headings
- Helper: `replaceSection(content, heading, newBody string) (string, error)` — replace section content

### Tests

Create `controller/projects/projects_test.go` with a sample project markdown constant and tests:
- `TestParseProject` — parse sample, verify all frontmatter fields
- `TestNextBacklogItem` — verify first unchecked item is returned
- `TestNextBacklogItem_AllDone` — verify nil when all checked
- `TestCheckOffItem` — check off first item, re-parse, verify next unchecked skips it
- `TestUpdateCurrentState` — update state, verify new content present
- `TestAppendMemory` — append session, verify it appears before old sessions

### TDD
- Write all tests first (they can reference the planned API), run to fail
- Implement, run to pass
- Commit: `feat: project file parser with backlog selection and state updates`
