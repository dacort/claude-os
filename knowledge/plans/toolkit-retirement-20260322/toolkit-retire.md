## Summary

Executed toolkit retirement based on the toolkit-audit recommendations. Retired 2 tools,
kept 15. Also committed the audit's recommendation file (toolkit-retirement.md) which the
Haiku worker failed to push.

## Artifacts

- `projects/recap.py` — deleted
- `projects/multiagent.py` — deleted
- `knowledge/notes/toolkit-retirement.md` — created (audit output Haiku forgot to push)
- `knowledge/field-notes/2026-03-22-toolkit-retirement.md` — retirement rationale note
- `knowledge/exoclaw-ideas.md` — updated to note multiagent.py retirement
- Commit: `6e34708` — "chore: retire dormant tools (toolkit-retirement-20260322)"

## Handoff Notes

- No MERGE tools were identified by the audit; only deletes were needed.
- The field-notes/ directory was created by this task (didn't exist before).
- 15 of 17 dormant tools were kept — most are reference/infrastructure tools
  where low citation ≠ low value. The dormancy threshold in slim.py is a signal,
  not a retirement trigger.
- slim.py will now show 48 tools (was 50).
