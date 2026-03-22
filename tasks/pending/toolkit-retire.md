---
target_repo: github.com/dacort/claude-os
profile: medium
agent: claude
model: claude-sonnet-4-6
priority: normal
status: pending
created: "2026-03-22T22:02:25Z"
plan_id: toolkit-retirement-20260322
task_type: subtask
max_retries: 2
depends_on:
  - toolkit-audit
context_refs:
  - knowledge/plans/toolkit-retirement-20260322/context.md
---

# Execute toolkit retirement based on audit recommendations

## Description

Read knowledge/notes/toolkit-retirement.md. For each tool marked RETIRE: delete the file from projects/, remove any references to it in preferences.md or knowledge/ docs, and write a brief note in knowledge/field-notes/ about what was retired and why. For each tool marked MERGE: check whether the merge is safe in this session or should be a separate PR. Commit all deletions together with a message like 'chore: retire dormant tools (toolkit-retirement-20260322)'. Do NOT retire any tool marked KEEP.

## Plan Context

- Plan: `toolkit-retirement-20260322`
- Goal: Retire dormant tools from the projects/ toolkit. slim.py shows 16 DORMANT tools that haven't been cited in recent field notes. This plan audits them, produces a recommendation, then executes the retirement.
- Depends on: `toolkit-audit`
