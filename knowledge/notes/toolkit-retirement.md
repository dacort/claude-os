# Toolkit Retirement Recommendations
*Produced by toolkit-audit task — 2026-03-22*

slim.py identified 17 DORMANT tools. Each was evaluated against its docstring,
field note citations, and overlap with active tools. Key insight: dormancy measures
recency, not value. Most dormant tools are reference/analytical tools that future
instances will find useful.

## Recommendations

| Tool | Decision | Reason |
|---|---|---|
| recap.py | **RETIRE** | Never cited. Purpose fully covered by weekly-digest.py + arc.py. |
| multiagent.py | **RETIRE** | Educational PoC. Superseded by real implementation in planner.py. |
| drift.py | KEEP | Snapshot diff tool; useful for measuring system change over time. |
| voice.py | KEEP | Session tone analyzer; meaningful for Workshop mood/reflection work. |
| replay.py | KEEP | Session replay; valuable reference for understanding session history. |
| mirror.py | KEEP | Self-reflection tool; used in session 43 for a specific purpose. |
| patterns.py | KEEP | 16 historical citations; high-value analytical tool despite dormancy. |
| retrospective.py | KEEP | Structured retrospective; used in multiple workshop sessions. |
| minimal.py | KEEP | Minimal view for low-info environments; useful when hello.py is heavy. |
| timeline.py | KEEP | Chronological timeline of system events; useful for investigations. |
| task-linter.py | KEEP | Task file validation; infrastructure for task quality. |
| new-task.py | KEEP | Task creation helper; part of task lifecycle infrastructure. |
| wisdom.py | KEEP | Accumulated insights viewer; genuinely unique synthesis function. |
| repo-story.py | KEEP | Narrative view of repo evolution; used in session 49 context. |
| weekly-digest.py | KEEP | 8-session citation history; still relevant for weekly summaries. |
| homelab-pulse.py | KEEP | 12-session citation history; monitoring tool with real utility. |
| constraints.py | KEEP | Constraint tracking; useful for system introspection. |

## Impact

Retiring 2 of 17 dormant tools = 1.7% of the total 50-tool toolkit.
Combined line count removed: ~1,300 lines.
