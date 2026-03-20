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

## Results

## Outcome

- Outcome: success
- Agent: claude
- Model: claude-sonnet-4-6

## Summary

Task completed without an explicit structured result block.

## Usage

- Tokens in: 0
- Tokens out: 0
- Duration (s): 127

## Artifacts

- None

## Structured Result (raw)

```json
{
  "version": "1",
  "task_id": "v2-task-1-data-model-apply",
  "agent": "claude",
  "model": "claude-sonnet-4-6",
  "outcome": "success",
  "summary": "Task completed without an explicit structured result block.",
  "artifacts": [],
  "usage": {
    "tokens_in": 0,
    "tokens_out": 0,
    "duration_seconds": 127
  },
  "failure": null,
  "next_action": null
}
```

## Worker Logs

Context contract written to /workspace/task-context.json
=== Claude OS Worker v3 ===
Task ID: v2-task-1-data-model-apply
Profile: small
Agent: claude
Mode: execution
Started: 2026-03-20T17:18:34Z
Context: /workspace/task-context.json
Auth: Claude OAuth token (subscription)
Cloning context repo: https://github.com/dacort/claude-os.git -> /workspace/claude-os
Cloning into '/workspace/claude-os'...
Running task via claude...
---
WARNING: context_ref not found: /workspace/claude-os/knowledge/skills/go-testing.md
Injecting preferences from knowledge/preferences.md
Done. Here's what was applied and pushed:

**Commit `51f7463` → `main`**

| File | Change |
|---|---|
| `controller/gitsync/gitsync.go` | Added `Project`/`BacklogSource` to `TaskFrontmatter` struct (yaml tags), `TaskFile` struct (plain fields), and the `ParseTaskFile()` return literal |
| `controller/queue/queue.go` | Added `Project string` (with `json:"project,omitempty"`) to the `Task` struct after `Mode` |
| `controller/gitsync/gitsync_test.go` | Added `TestParseTaskFileWithProject` — parses a task with `project: rag-indexer` and `backlog_source: inline`, asserts both fields round-trip correctly |

All 8 test packages passed before the push (`go test ./...`).
No workspace changes to commit
---
=== Worker Complete ===
Exit code: 0
Push exit: 0
Finished: 2026-03-20T17:20:40Z
===RESULT_START===
{"version":"1","task_id":"v2-task-1-data-model-apply","agent":"claude","model":"claude-sonnet-4-6","outcome":"success","summary":"Task completed without an explicit structured result block.","artifacts":[],"usage":{"tokens_in":0,"tokens_out":0,"duration_seconds":127},"failure":null,"next_action":null}
===RESULT_END===

=== CLAUDE_OS_USAGE ===
{"task_id":"v2-task-1-data-model-apply","agent":"claude","profile":"small","duration_seconds":127,"exit_code":0,"finished_at":"2026-03-20T17:20:40Z"}
=== END_CLAUDE_OS_USAGE ===

