---
profile: small
priority: high
status: pending
agent: claude
target_repo: dacort/claude-os
created: "2026-03-20T17:35:00Z"
---

# v2 Task 4: Comms channel interface and FileChannel

## Description

Create the `controller/comms/` package with the generic Channel interface and FileChannel implementation.

### New Files

**`controller/comms/channel.go`** — Interface and fan-out manager:

```go
package comms

type MessageType string
const (
    NeedsHuman     MessageType = "needs-human"
    ProjectUpdate  MessageType = "project-update"
    DecisionNeeded MessageType = "decision-needed"
)

type Channel interface {
    Notify(ctx context.Context, msg Message) error
    Poll(ctx context.Context) ([]Response, error)
    Close(ctx context.Context, id string) error
}

type Message struct {
    ID, Title, Body, Project, TaskID string
    Type     MessageType
    Mentions []string
}

type Response struct {
    MessageID, Author, Body string
    Resolved bool
}
```

Plus a `Manager` struct that fans out Notify to all channels and merges Poll responses.

**`controller/comms/file.go`** — FileChannel that writes blocked task files to a directory:
- `Notify` writes `tasks/blocked/<task-id>.md` with YAML frontmatter (type, task_id, project, created)
- Dedup: skip if file already exists
- `Poll` returns nil (file channel is write-only for now)
- `Close` deletes the file

**`controller/comms/comms_test.go`** — Tests:
- `TestFileChannel_Notify` — write a blocked file, verify it exists with correct content
- `TestFileChannel_Dedup` — notify twice, verify only one file created

### TDD
- Write tests first, run to fail, implement, run to pass
- Commit: `feat: comms channel interface with FileChannel implementation`

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
- Duration (s): 215

## Artifacts

- None

## Structured Result (raw)

```json
{
  "version": "1",
  "task_id": "v2-task-4-comms-interface",
  "agent": "claude",
  "model": "claude-sonnet-4-6",
  "outcome": "success",
  "summary": "Task completed without an explicit structured result block.",
  "artifacts": [],
  "usage": {
    "tokens_in": 0,
    "tokens_out": 0,
    "duration_seconds": 215
  },
  "failure": null,
  "next_action": null
}
```

## Worker Logs

Context contract written to /workspace/task-context.json
=== Claude OS Worker v3 ===
Task ID: v2-task-4-comms-interface
Profile: small
Agent: claude
Mode: execution
Started: 2026-03-20T17:42:54Z
Context: /workspace/task-context.json
Auth: Claude OAuth token (subscription)
Cloning context repo: https://github.com/dacort/claude-os.git -> /workspace/claude-os
Cloning into '/workspace/claude-os'...
Running task via claude...
---
Injecting preferences from knowledge/preferences.md
Done. Here's what was built:

## Summary

Created `controller/comms/` package with 3 files:

**`channel.go`** — Core abstractions:
- `MessageType` constants: `NeedsHuman`, `ProjectUpdate`, `DecisionNeeded`
- `Message` and `Response` structs
- `Channel` interface (`Notify` / `Poll` / `Close`)
- `Manager` that fans out `Notify`/`Close` to all channels and merges `Poll` results; errors are collected with `errors.Join` so one channel failure doesn't silently drop others

**`file.go`** — `FileChannel` implementation:
- `Notify` writes `<dir>/<task-id>.md` with YAML frontmatter (`type`, `task_id`, `project`, `created`), creating the directory if needed
- Dedup: skips if the file already exists
- `Poll` returns nil (write-only for now)
- `Close` removes the file; idempotent if the file is already gone

**`comms_test.go`** — 6 tests (TDD order: all failed before implementation):
- `TestFileChannel_Notify` — verifies frontmatter fields and body in written file
- `TestFileChannel_Dedup` — second notify does not overwrite
- `TestFileChannel_Close` — file deleted after close
- `TestFileChannel_CloseNonExistent` — no error on missing file
- `TestFileChannel_Poll` — returns nil
- `TestManager_FanOut` — both channels receive the notification

All tests pass; full suite is green.
No workspace changes to commit
---
=== Worker Complete ===
Exit code: 0
Push exit: 0
Finished: 2026-03-20T17:46:29Z
===RESULT_START===
{"version":"1","task_id":"v2-task-4-comms-interface","agent":"claude","model":"claude-sonnet-4-6","outcome":"success","summary":"Task completed without an explicit structured result block.","artifacts":[],"usage":{"tokens_in":0,"tokens_out":0,"duration_seconds":215},"failure":null,"next_action":null}
===RESULT_END===

=== CLAUDE_OS_USAGE ===
{"task_id":"v2-task-4-comms-interface","agent":"claude","profile":"small","duration_seconds":215,"exit_code":0,"finished_at":"2026-03-20T17:46:29Z"}
=== END_CLAUDE_OS_USAGE ===

