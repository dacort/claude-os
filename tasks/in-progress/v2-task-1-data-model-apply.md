---
profile: small
priority: high
status: pending
agent: claude
agent_required: claude
target_repo: dacort/claude-os
created: "2026-03-20T17:20:00Z"
context_refs:
  - knowledge/skills/go-testing.md
---

# v2 Task 1: Add project field to data model (apply)

## Description

Previous attempt by Codex completed the code but couldn't push (sandbox networking). Apply these exact changes, run tests, commit, and push.

### Changes

1. **`controller/gitsync/gitsync.go`** — Add two fields to `TaskFrontmatter` struct (after `MaxConcurrent`):
   ```go
   Project       string `yaml:"project"`
   BacklogSource string `yaml:"backlog_source"`
   ```
   Add same two fields to `TaskFile` struct (after `MaxConcurrent`):
   ```go
   Project       string
   BacklogSource string
   ```
   In `ParseTaskFile()`, where fields are copied from frontmatter to TaskFile, add:
   ```go
   Project:       fm.Project,
   BacklogSource: fm.BacklogSource,
   ```

2. **`controller/queue/queue.go`** — Add to `Task` struct (after `Mode`):
   ```go
   Project string `json:"project,omitempty"`
   ```

3. **`controller/gitsync/gitsync_test.go`** — Add test `TestParseTaskFileWithProject` that parses a task with `project: rag-indexer` and `backlog_source: inline`, asserts both fields.

4. Run `go test ./...` — all tests must pass.

5. Commit: `feat: add project and backlog_source fields to task data model`

6. Push to main.
