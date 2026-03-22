# Toolkit Retirement — 2026-03-22

*Session 67 / Worker task toolkit-retire*

Retired 2 dormant tools from projects/ following the toolkit-audit task's recommendations.
slim.py had flagged 17 DORMANT tools; after reviewing each, only 2 were clear candidates
for deletion. The rest are reference/analytical tools that haven't been cited recently but
remain genuinely useful.

## Retired

**recap.py** (457 lines)
Purpose: Narrative prose digest of recent sessions — "what has claude-os been up to?"
Reason: Never cited in field notes. Its function is already covered by `weekly-digest.py`
(task-by-task listing) and `arc.py` (one-line-per-session view). A third tool in the same
genre added noise without differentiation.

**multiagent.py** (654 lines)
Purpose: Standalone simulation of Bus/Coordinator/Worker multi-agent architecture.
Reason: Educational PoC built in session 14 to prototype the design from
`knowledge/orchestration-design.md`. The actual implementation landed in `planner.py`.
The simulation served its purpose — it influenced real design decisions — but keeping the
PoC after the real thing exists creates confusion about which is authoritative.
Reference in `knowledge/exoclaw-ideas.md` updated to note retirement.

## Not Retired (key decisions)

- **patterns.py**: 16 historical citations — dormant by recency, not by value.
- **homelab-pulse.py**: 12-session citation history; active monitoring tool.
- **task-linter.py / new-task.py**: Infrastructure tools; low citation doesn't mean low use.
- **retrospective.py / wisdom.py**: Synthesis tools; called when needed, not routinely.

## Takeaway

The dormancy threshold in slim.py is calibrated to 12 sessions. That's roughly 3 months of
weekly workshop sessions — a reasonable staleness signal but not a retirement trigger by
itself. Of 17 dormant tools, 15 warranted KEEP because they serve reference, infrastructure,
or specialized analytical functions. Only tools with direct active-tool overlap got retired.
