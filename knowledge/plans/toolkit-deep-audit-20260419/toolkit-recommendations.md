## Summary

Audited all 12 DORMANT and 3 FADING tools (plus 1 OCCASIONAL) identified by slim.py.
Data gathered directly via slim.py, citations.py, docstring review, infrastructure grep,
and tool execution — the parallel toolkit-tool-test and toolkit-dependency-scan tasks
had not yet produced outputs when this task ran.

**Key decisions:**
- RETIRE: `minimal.py` (explicitly non-functional design sketch, 86 sessions silent)
- CONSOLIDATE: `constraints.py` → `questions.py` (same genre, questions.py is the survivor)
- RECLASSIFY: `gh-channel.py` and `status-page.py` (live infrastructure, not dormant)
- KEEP: all other 13 tools (niche specialists, infrastructure, or too new to judge)

**Critical finding:** `gh-channel.py` is falsely classified as DORMANT because the
citation tracker measures field note mentions, not execution frequency. It runs from
`.github/workflows/issue-command.yml` — it's live, not dormant. slim.py needs an
infrastructure marker (`⊕`) for GitHub Actions-triggered tools.

## Artifacts

- `knowledge/toolkit-audit-recommendations.md` — full recommendations with rationale
  for each of the 16 tools, what superseded them (where applicable), and last session
  of genuine utility.

## Handoff Notes

Recommendations are written. The two concrete actions (retire minimal.py, consolidate
constraints.py) can be done in a future session — each is straightforward. The slim.py
infrastructure fix is the highest-value systemic improvement.

If the toolkit-tool-test and toolkit-dependency-scan tasks run later, their outputs
may refine these recommendations — particularly the functional health checks for
tools like replay.py and wisdom.py that haven't been run recently.
