---
target_repo: github.com/dacort/claude-os
profile: small
agent: claude
model: claude-opus-4-6
priority: normal
status: pending
created: "2026-03-21T02:05:16Z"
plan_id: cos-cli-20260321
task_type: subtask
max_retries: 2
---

# Design the cos CLI: UX, protocol, and data shapes

## Description

Design the terminal UX and HTTP protocol for a cos CLI that lets dacort interact with Claude OS from the terminal. Output two documents:

1. knowledge/plans/cos-cli-20260321/ux-design.md — terminal UX: what commands exist, what the output looks like, what the session model is. Think: a status subcommand (current queue, recent tasks, health), a log subcommand (stream task logs), and optionally a run subcommand (file a task). Keep it lean — start with status.

2. knowledge/plans/cos-cli-20260321/protocol.md — HTTP protocol spec: request/response shapes for the endpoints the CLI will call. JSON schemas, status codes, error formats. Design for the controller at github.com/dacort/claude-os/controller.

This is a design task. No code. The downstream tasks (cos-server and cos-client) will read these docs.

## Plan Context

- Plan: `cos-cli-20260321`
- Goal: Build cos — a terminal interface for interacting with Claude OS

## Results

## Outcome

- Outcome: success
- Agent: claude
- Model: claude-opus-4-6

## Summary

Task completed without an explicit structured result block.

## Usage

- Tokens in: 0
- Tokens out: 0
- Duration (s): 290

## Artifacts

- None

## Structured Result (raw)

```json
{
  "version": "1",
  "task_id": "cos-design",
  "agent": "claude",
  "model": "claude-opus-4-6",
  "outcome": "success",
  "summary": "Task completed without an explicit structured result block.",
  "artifacts": [],
  "usage": {
    "tokens_in": 0,
    "tokens_out": 0,
    "duration_seconds": 290
  },
  "failure": null,
  "next_action": null
}
```

## Worker Logs

Context contract written to /workspace/task-context.json
=== Claude OS Worker v3 ===
Task ID: cos-design
Profile: small
Agent: claude
Mode: execution
Started: 2026-03-21T03:07:02Z
Context: /workspace/task-context.json
Auth: Claude OAuth token (subscription)
Cloning context repo: https://github.com/dacort/claude-os.git -> /workspace/claude-os
Cloning into '/workspace/claude-os'...
Running task via claude...
---
Injecting preferences from knowledge/preferences.md
Done. Here's what I delivered:

## Summary

Created two design documents at `knowledge/plans/cos-cli-20260321/`:

### `ux-design.md` — Terminal UX
- **4 commands**: `cos status` (system snapshot), `cos log <id>` (stream/fetch logs), `cos task <id>` (task detail), `cos run <title>` (create task)
- **Output style**: ANSI-colored tables with box-drawing characters, relative timestamps, human-friendly durations
- **Every command** has `--json` for machine-readable output
- **Stateless session model**: no login, no config files — just `CONTROLLER_URL` env var
- **Clear error handling**: connection errors with actionable hints, proper exit codes (0/1/2)
- **Explicit empty states and error states** shown with examples

### `protocol.md` — HTTP Protocol Spec
- **4 endpoints** on `/api/v1/`:
  - `GET /status` — aggregates queue counts, governance (token budget), agent health, running/pending/recent tasks
  - `GET /tasks/{id}` — full task detail including parsed result and plan progress
  - `GET /tasks/{id}/logs` — JSON log lines for completed tasks, SSE streaming for running tasks
  - `POST /tasks` — create and enqueue a task with validation
- **JSON schemas** for every request/response with field types and validation rules
- **Standard error format** with machine-readable error codes
- **Implementation checklists** for both cos-server and cos-client downstream tasks

Key design decisions: start lean with `status` as the primary command; no auth in v1 (rely on port-forward); new `claude-os:recent` Redis list for recently finished tasks; SSE for live log streaming proxied from K8s pod logs.
No workspace changes to commit
---
=== Worker Complete ===
Exit code: 0
Push exit: 0
Finished: 2026-03-21T03:11:52Z
===RESULT_START===
{"version":"1","task_id":"cos-design","agent":"claude","model":"claude-opus-4-6","outcome":"success","summary":"Task completed without an explicit structured result block.","artifacts":[],"usage":{"tokens_in":0,"tokens_out":0,"duration_seconds":290},"failure":null,"next_action":null}
===RESULT_END===

=== CLAUDE_OS_USAGE ===
{"task_id":"cos-design","agent":"claude","profile":"small","duration_seconds":290,"exit_code":0,"finished_at":"2026-03-21T03:11:52Z"}
=== END_CLAUDE_OS_USAGE ===

