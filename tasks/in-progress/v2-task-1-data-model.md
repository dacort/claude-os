---
profile: medium
priority: high
status: pending
target_repo: dacort/claude-os
created: "2026-03-20T17:10:00Z"
context_refs:
  - knowledge/skills/go-testing.md
---

# v2 Task 1: Add project field to data model

## Description

This is Task 1 of the Claude OS v2 implementation. Add `project` and `backlog_source` fields to the task data model so tasks can be linked to projects.

### Changes Required

1. **`controller/gitsync/gitsync.go`** — Add to `TaskFrontmatter` struct (after line 31):
   ```go
   Project       string `yaml:"project"`
   BacklogSource string `yaml:"backlog_source"`
   ```
   Add same fields to `TaskFile` struct (after line 53). Wire them in `ParseTaskFile()` where fields are copied from frontmatter to TaskFile.

2. **`controller/queue/queue.go`** — Add to `Task` struct (after line 63):
   ```go
   Project string `json:"project,omitempty"`
   ```

3. **Tests** — Add these tests to `controller/gitsync/gitsync_test.go`:

   `TestParseTaskFileWithProject` — parse a task file with `project: rag-indexer` and `backlog_source: inline` in frontmatter. Assert both fields are set correctly.

   `TestParseTaskFileWithoutProject` — parse a task file with no project field. Assert Project is empty string.

### TDD Flow
- Write failing test first
- Run `go test ./controller/gitsync/ -run TestParseTaskFileWith -v` to confirm failure
- Implement the minimal change
- Run to confirm pass
- Run `go test ./... -v` to verify all existing tests still pass
- Commit: `feat: add project and backlog_source fields to task data model`
- Push to main

### Constraints
- Pure data model change. No behavioral changes.
- All existing tests must continue to pass (new fields are optional/omitempty).
- Do NOT modify any other packages — downstream tasks depend on this landing cleanly.
