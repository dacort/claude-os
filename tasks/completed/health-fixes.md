---
target_repo: github.com/dacort/claude-os
profile: small
agent: claude
model: claude-sonnet-4-6
priority: normal
status: completed
created: "2026-03-20T22:13:31Z"
plan_id: tool-health-20260320
task_type: subtask
max_retries: 2
depends_on:
  - health-audit
context_refs:
  - knowledge/plans/tool-health-20260320/context.md
---

# Add --help to the top 5 tools missing it

## Description

Read knowledge/plans/tool-health-20260320/audit.md from the health-audit step. Identify the 5 most-cited tools that lack a --help flag (or have a weak one). Add a proper --help with argparse to each, showing usage examples that match the tool's actual behavior. Don't change any functionality — just add help text. Each tool should show its name, what it does, and at least 2 usage examples.

## Plan Context

- Plan: `tool-health-20260320`
- Goal: Audit the projects/ toolkit and add --help to tools that are missing it
- Depends on: `health-audit`

## Results

Added argparse-based `--help` to the top 5 most-cited tools that were silently ignoring it.

| Rank | Tool | Citations | Flags documented |
|------|------|-----------|------------------|
| #1   | garden.py | 20 sessions | --plain, --brief, --json, --since REF |
| #4   | homelab-pulse.py | 12 sessions | (no flags — added help text only) |
| #5   | hello.py | 11 sessions | --plain |
| #8   | wisdom.py | 7 sessions | --plain, --codas, --themes |
| #11  | forecast.py | 6 sessions | --plain, --json |

No functionality changed. Commit: `9636c3d`.

## Outcome

- Outcome: success
- Agent: claude
- Model: claude-sonnet-4-6
