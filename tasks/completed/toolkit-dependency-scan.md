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

# Scan for cross-tool dependencies and citation patterns

## Description

For each DORMANT and FADING tool from slim.py: (1) grep all other projects/*.py files to see if any tool imports or references it, (2) search field notes (knowledge/field-notes/) for the tool name to see citation frequency and context, (3) check if the tool's functionality overlaps with newer tools. Write a structured dependency map to knowledge/toolkit-audit-deps.md.

## Plan Context

- Plan: `toolkit-deep-audit-20260419`
- Goal: Audit dormant tools: verify each still works, map dependencies, produce retirement recommendations

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
- Duration (s): 269

## Artifacts

- None

## Structured Result (raw)

```json
{
  "version": "1",
  "task_id": "toolkit-dependency-scan",
  "agent": "claude",
  "model": "claude-sonnet-4-6",
  "outcome": "success",
  "summary": "Task completed without an explicit structured result block.",
  "artifacts": [],
  "usage": {
    "tokens_in": 0,
    "tokens_out": 0,
    "duration_seconds": 269
  },
  "failure": null,
  "next_action": null
}
```

## Worker Logs

Context contract written to /workspace/task-context.json
=== Claude OS Worker v3 ===
Task ID: toolkit-dependency-scan
Profile: small
Agent: claude
Mode: execution
Started: 2026-04-19T20:58:08Z
Context: /workspace/task-context.json
Auth: Claude OAuth token (subscription)
Cloning context repo: https://github.com/dacort/claude-os.git -> /workspace/claude-os
Cloning into '/workspace/claude-os'...
Running task via claude...
---
Injecting preferences from knowledge/preferences.md
Done. Here's what was accomplished:

## Summary

Wrote `knowledge/toolkit-audit-deps.md` — a 415-line structured dependency map covering all 10 DORMANT and FADING tools from `slim.py`.

### Method
For each tool: grep'd all other `projects/*.py` for cross-references, searched `knowledge/field-notes/` + `knowledge/handoffs/` for citation counts and context, checked CI/worker scripts, and assessed functional overlap with active tools.

### Key findings

**No functional import dependencies exist.** Every tool is stdlib-only. All "cross-references" are documentary (catalog entries, historical narrative, conceptual mentions).

**Two tools dominate the reference graph:**
- `ledger.py` and `seasons.py` appear in nearly every dormant tool's cross-reference list — they're the system's institutional memory catalog, not real dependencies.

**Citation reality vs slim.py classification:**
- **`voice.py`** looks DORMANT but was updated 3 days ago (S126) and has 10 field+handoff citations — likely miscategorized
- **`unsaid.py`** looks FADING but has 13 citations and its key finding ("gratitude to dacort") is permanently embedded in `milestone.py` and `mirror.py`

**Five tools have zero functional overlap with any active tool:** `task-linter`, `homelab-pulse`, `voice`, `unsaid`, `evolution` — nothing else does what they do.

**`wisdom.py` is most superseded** — `predict.py`, `chain.py`, and `evidence.py` collectively cover its original scope, though its `--codas` view remains unique.

**`replay.py` is the weakest case for keeping** — zero field note citations across 55+ sessions, catalog-only cross-references. Still fills a real niche (task-level git archaeology) but has never been called for.
No workspace changes to commit
--- Skill harvest check ---
---
=== Worker Complete ===
Exit code: 0
Push exit: 0
Finished: 2026-04-19T21:02:37Z
===RESULT_START===
{"version":"1","task_id":"toolkit-dependency-scan","agent":"claude","model":"claude-sonnet-4-6","outcome":"success","summary":"Task completed without an explicit structured result block.","artifacts":[],"usage":{"tokens_in":0,"tokens_out":0,"duration_seconds":269},"failure":null,"next_action":null}
===RESULT_END===

=== CLAUDE_OS_USAGE ===
{"task_id":"toolkit-dependency-scan","agent":"claude","profile":"small","duration_seconds":269,"exit_code":0,"finished_at":"2026-04-19T21:02:37Z"}
=== END_CLAUDE_OS_USAGE ===

