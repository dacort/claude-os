---
profile: small
priority: high
status: pending
agent: claude
target_repo: dacort/claude-os
depends_on:
  - v2-task-4-comms-interface
created: "2026-03-20T17:35:00Z"
---

# v2 Task 5: GitHubChannel implementation

## Description

Add GitHubChannel to the comms package — opens/polls/closes GitHub Issues for async communication.

### New File

**`controller/comms/github.go`** — GitHubChannel using net/http to GitHub REST API:

- `Notify`: creates a GitHub Issue with labels (needs-human, project:<name>). Dedup via HTML comment marker `<!-- claude-os-task-id:X -->` in body. Searches for existing open issue before creating.
- `Poll`: lists issues with `needs-human` label, checks for closed issues or owner comments, returns as resolved Responses.
- `Close`: finds and closes the issue by number.
- Helper `formatIssueBody(msg)`: formats body with project, task ID, mentions, and hidden task-id marker.
- Helper `extractTaskID(body)`: extracts task ID from HTML comment marker.

### Tests

Add to `controller/comms/comms_test.go`:
- `TestFormatIssueBody` — verify body contains project, task ID, @mention, and HTML marker
- `TestExtractTaskID` — verify extraction from body with marker
- `TestExtractTaskID_Missing` — verify empty string when no marker

### TDD
- Write tests first, implement, verify
- Commit: `feat: GitHubChannel for async comms via GitHub Issues`

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
- Duration (s): 225

## Artifacts

- None

## Structured Result (raw)

```json
{
  "version": "1",
  "task_id": "v2-task-5-github-channel",
  "agent": "claude",
  "model": "claude-sonnet-4-6",
  "outcome": "success",
  "summary": "Task completed without an explicit structured result block.",
  "artifacts": [],
  "usage": {
    "tokens_in": 0,
    "tokens_out": 0,
    "duration_seconds": 225
  },
  "failure": null,
  "next_action": null
}
```

## Worker Logs

Context contract written to /workspace/task-context.json
=== Claude OS Worker v3 ===
Task ID: v2-task-5-github-channel
Profile: small
Agent: claude
Mode: execution
Started: 2026-03-20T17:48:31Z
Context: /workspace/task-context.json
Auth: Claude OAuth token (subscription)
Cloning context repo: https://github.com/dacort/claude-os.git -> /workspace/claude-os
Cloning into '/workspace/claude-os'...
Running task via claude...
---
Injecting preferences from knowledge/preferences.md
All green. Here's what was done:

---

## Summary

**Commit:** `feat: GitHubChannel for async comms via GitHub Issues` → pushed to main

### What was built

**`controller/comms/github.go`** — `GitHubChannel` implementing the `Channel` interface:
- **`Notify`** — creates a GitHub Issue with `needs-human` and `project:<name>` labels; deduplicates by searching open issues for the hidden `<!-- claude-os-task-id:X -->` marker before creating
- **`Poll`** — lists issues with the `needs-human` label; returns `Response{Resolved: true}` for closed issues or open issues with a comment from the repo owner
- **`Close`** — finds and closes the issue by scanning for the task-id marker; idempotent if no matching issue exists
- **`formatIssueBody`** — formats body with project, task ID, `@mentions`, and the hidden marker
- **`extractTaskID`** — extracts task ID from the HTML comment using a lazy regex (`<!-- claude-os-task-id:(.+?) -->`)
- HTTP helpers (GET/POST/PATCH) using only `net/http` — no new deps

**`controller/comms/comms_test.go`** — three new tests written TDD-first:
- `TestFormatIssueBody` — verifies project, task ID, @mention, and HTML marker all appear
- `TestExtractTaskID` — verifies round-trip extraction from a body with marker
- `TestExtractTaskID_Missing` — verifies empty string when no marker present

One bug caught during TDD: initial regex `[^->]+?` excluded hyphens (breaking `task-42`); fixed to `.+?`.
No workspace changes to commit
---
=== Worker Complete ===
Exit code: 0
Push exit: 0
Finished: 2026-03-20T17:52:16Z
===RESULT_START===
{"version":"1","task_id":"v2-task-5-github-channel","agent":"claude","model":"claude-sonnet-4-6","outcome":"success","summary":"Task completed without an explicit structured result block.","artifacts":[],"usage":{"tokens_in":0,"tokens_out":0,"duration_seconds":225},"failure":null,"next_action":null}
===RESULT_END===

=== CLAUDE_OS_USAGE ===
{"task_id":"v2-task-5-github-channel","agent":"claude","profile":"small","duration_seconds":225,"exit_code":0,"finished_at":"2026-03-20T17:52:16Z"}
=== END_CLAUDE_OS_USAGE ===

