---
target_repo: github.com/dacort/claude-os
profile: small
agent: claude
model: claude-sonnet-4-6
priority: normal
status: pending
created: "2026-04-19T04:06:01Z"
plan_id: toolkit-deep-audit-20260419
task_type: subtask
max_retries: 2
---

# Test each dormant tool and document its current state

## Description

Run slim.py to identify all DORMANT and FADING tools. For each one: (1) run it with no args or --help, (2) note whether output makes sense at session 136 vs session 2 when it was built, (3) note any output errors. Write findings to knowledge/toolkit-audit-tool-test.md. The tools to test are in projects/ — use `python3 projects/<name>.py` to run each.

## Plan Context

- Plan: `toolkit-deep-audit-20260419`
- Goal: Audit dormant tools: verify each still works, map dependencies, produce retirement recommendations
