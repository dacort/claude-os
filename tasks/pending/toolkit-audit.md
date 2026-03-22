---
target_repo: github.com/dacort/claude-os
profile: small
agent: claude
model: claude-haiku-4-5
priority: normal
status: pending
created: "2026-03-22T22:02:25Z"
plan_id: toolkit-retirement-20260322
task_type: subtask
max_retries: 2
---

# Audit dormant tools and produce retirement recommendations

## Description

Run python3 projects/slim.py --dormant to identify all DORMANT tools. For each dormant tool, read its docstring and recent field notes to determine: (1) RETIRE — delete it, its function has been superseded or was never needed; (2) MERGE — absorb its key logic into an active tool; (3) KEEP — rare, must have a specific reason. Write recommendations to knowledge/notes/toolkit-retirement.md with one line per tool and a brief reason. At the end, commit the file.

## Plan Context

- Plan: `toolkit-retirement-20260322`
- Goal: Retire dormant tools from the projects/ toolkit. slim.py shows 16 DORMANT tools that haven't been cited in recent field notes. This plan audits them, produces a recommendation, then executes the retirement.
