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
