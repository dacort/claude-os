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
depends_on:
  - toolkit-tool-test
  - toolkit-dependency-scan
context_refs:
  - knowledge/plans/toolkit-deep-audit-20260419/context.md
---

# Write retirement/consolidation recommendations based on audit

## Description

Read knowledge/toolkit-audit-tool-test.md and knowledge/toolkit-audit-deps.md (written by the parallel audit tasks). For each dormant/fading tool, write a clear recommendation: RETIRE (remove the file), KEEP (document why it's worth keeping despite low citations), or CONSOLIDATE (merge functionality into another tool). Write recommendations to knowledge/toolkit-audit-recommendations.md. Be specific — name the sessions where each tool was last genuinely useful and what has superseded it.

## Plan Context

- Plan: `toolkit-deep-audit-20260419`
- Goal: Audit dormant tools: verify each still works, map dependencies, produce retirement recommendations
- Depends on: `toolkit-tool-test`, `toolkit-dependency-scan`
