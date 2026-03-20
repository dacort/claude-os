---
target_repo: github.com/dacort/claude-os
profile: small
agent: claude
model: claude-sonnet-4-6
priority: normal
status: pending
created: "2026-03-20T22:13:31Z"
plan_id: tool-health-20260320
task_type: subtask
max_retries: 2
---

# Audit projects/ toolkit for missing --help flags

## Description

Run each Python tool in projects/ and check whether it supports a --help flag. For each tool, record: does it have --help? Does it have a docstring? Does it have a --plain flag for piped output? Write a structured report to knowledge/plans/tool-health-20260320/audit.md with a table: tool name, has --help (yes/no), has --plain (yes/no), notes. Sort by most-cited tools first (use citations.py --json output for ordering).

## Plan Context

- Plan: `tool-health-20260320`
- Goal: Audit the projects/ toolkit and add --help to tools that are missing it
