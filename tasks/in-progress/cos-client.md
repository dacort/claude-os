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

# Build the cos CLI binary

## Description

Build a Go CLI binary at cmd/cos/main.go in the github.com/dacort/claude-os/controller module.

Read knowledge/plans/cos-cli-20260321/ux-design.md and knowledge/plans/cos-cli-20260321/protocol.md first. Implement the commands defined there. Start with: cos status (show queue state, recent tasks, system health).

The binary should:
- Read CONTROLLER_URL from env (default: http://localhost:8080)
- Output clean terminal-formatted text (ANSI colors welcome)
- Have a --json flag for machine-readable output
- Handle connection errors gracefully

Create a PR with the changes. The PR title should be: 'feat: add cos CLI binary'.

Constraints:
- Stdlib only (no cobra, no viper — just os.Args and flag)
- Must compile with: go build ./cmd/cos/

## Plan Context

- Plan: `cos-cli-20260321`
- Goal: Build cos — a terminal interface for interacting with Claude OS
- Depends on: `cos-design`
