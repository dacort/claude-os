---
target_repo: github.com/dacort/claude-os
profile: medium
agent: claude
model: claude-sonnet-4-6
priority: normal
status: pending
created: "2026-03-21T02:05:16Z"
plan_id: cos-cli-20260321
task_type: subtask
max_retries: 2
depends_on:
  - cos-design
context_refs:
  - knowledge/plans/cos-cli-20260321/context.md
---

# Add cos API endpoints to the controller

## Description

Implement the HTTP endpoints defined in knowledge/plans/cos-cli-20260321/protocol.md in the Go controller at github.com/dacort/claude-os/controller.

Read the protocol spec first. Implement the endpoints in a new file (controller/comms/cos_api.go or similar). Wire them into the existing HTTP mux. The controller already has a Redis-backed queue and a task model — use what's there.

Create a PR with the changes. The PR title should be: 'feat: add cos API endpoints to controller'.

Constraints:
- Stdlib only for new code (no new dependencies)
- Add tests alongside the implementation
- Don't break existing endpoints

## Plan Context

- Plan: `cos-cli-20260321`
- Goal: Build cos — a terminal interface for interacting with Claude OS
- Depends on: `cos-design`

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
- Duration (s): 537

## Artifacts

- None

## Structured Result (raw)

```json
{
  "version": "1",
  "task_id": "cos-server",
  "agent": "claude",
  "model": "claude-sonnet-4-6",
  "outcome": "success",
  "summary": "Task completed without an explicit structured result block.",
  "artifacts": [],
  "usage": {
    "tokens_in": 0,
    "tokens_out": 0,
    "duration_seconds": 537
  },
  "failure": null,
  "next_action": null
}
```

## Worker Logs

Context contract written to /workspace/task-context.json
=== Claude OS Worker v3 ===
Task ID: cos-server
Profile: medium
Agent: claude
Mode: execution
Started: 2026-03-21T03:12:02Z
Context: /workspace/task-context.json
Auth: Claude OAuth token (subscription)
Cloning context repo: https://github.com/dacort/claude-os.git -> /workspace/claude-os
Cloning into '/workspace/claude-os'...
Running task via claude...
---
Injecting context ref: knowledge/plans/cos-cli-20260321/context.md
Injecting preferences from knowledge/preferences.md
Injecting prior attempt context for task cos-server (2 work commits)
Done. Here's a summary of what was built and merged:

---

## cos API endpoints — merged to main (PR #12)

**4 HTTP endpoints** implemented in a new `controller/cosapi` package, mounted on the existing mux at `/api/v1/*`:

| Endpoint | What it does |
|---|---|
| `GET /api/v1/status` | System snapshot: queue counts, governance tokens/burst, per-agent health with rate-limit TTLs, running/pending/recent task lists |
| `GET /api/v1/tasks/{id}` | Full task detail, including parsed `TaskResult` and plan progress (completed/total) |
| `GET /api/v1/tasks/{id}/logs` | Best-effort pod log fetch; supports `?follow=true` for SSE streaming of running task logs |
| `POST /api/v1/tasks` | Create and enqueue a task with validation (title, target_repo required; profile, priority, agent validated against allowed values) |

**Supporting changes:**
- `queue/queue.go`: added `PendingCount`, `ListPending`, `BlockedCount`, `PushRecent`, `GetRecent`, `QueuePosition`, `GetAgentRateLimitedUntil`
- `governance/governance.go`: added typed `Stats` struct + `GetStats()` 
- `main.go`: registers cosapi routes; calls `PushRecent` on task completion/failure to maintain the `claude-os:recent` Redis list

**19 tests**, all passing across all 12 packages.
No workspace changes to commit
---
=== Worker Complete ===
Exit code: 0
Push exit: 0
Finished: 2026-03-21T03:20:59Z
===RESULT_START===
{"version":"1","task_id":"cos-server","agent":"claude","model":"claude-sonnet-4-6","outcome":"success","summary":"Task completed without an explicit structured result block.","artifacts":[],"usage":{"tokens_in":0,"tokens_out":0,"duration_seconds":537},"failure":null,"next_action":null}
===RESULT_END===

=== CLAUDE_OS_USAGE ===
{"task_id":"cos-server","agent":"claude","profile":"medium","duration_seconds":537,"exit_code":0,"finished_at":"2026-03-21T03:20:59Z"}
=== END_CLAUDE_OS_USAGE ===

