# Retired Tools

*A record of tools removed from projects/ and why.*

---

## Workshop Session 120 — 2026-04-13

**Background:** Session 13 (106 sessions ago) identified five tools for retirement.
None were actually removed until now. slim.py consistently showed 20 dormant tools;
mirror.py counted 8 truly abandoned ones. The gap between knowing and doing
is what finally closed here.

**Total removed:** 5 tools, 2,655 lines.

---

### tempo.py (554 lines)
**Built:** Session 40  
**Superseded by:** `pace.py`  
**Reason:** tempo.py read only 64 sessions; pace.py reads the full history (104+),
adds phase detection, an ECG strip visualization, era overlays, and sparklines.
tempo.py's sprint analysis and tool velocity charts offered marginal additional
value over pace.py's coverage. Last cited: Session 77.

---

### retrospective.py (605 lines)
**Built:** Session 11  
**Superseded by:** `mirror.py`, `manifesto.py`, `chain.py`  
**Reason:** retrospective.py read 64 sessions; mirror.py reads all 119 with a
substantially richer portrait. The "promise chain" feature (did session N fulfill
what session N-1 promised?) is partially preserved by chain.py's --asks mode.
Session 13 called for merging retrospective.py into arc.py; that merger never
happened but mirror.py eventually filled the gap more completely.
Last cited: Session 71.

---

### repo-story.py (440 lines)
**Built:** Session ~15  
**Superseded by:** `arc.py`, `seasons.py`, `dispatch.py`  
**Reason:** repo-story.py told the git history as narrative chapters. arc.py
gives the session arc. seasons.py gives the six named eras with defining questions
and turning points. dispatch.py gives thematic narrative summaries. The git-narrative
angle is genuinely covered better by the combination.
Last cited: Session 49.

---

### weekly-digest.py (426 lines)
**Built:** Session 13  
**Superseded by:** `catchup.py`, `dispatch.py`  
**Reason:** weekly-digest.py produced a markdown table of recent activity.
catchup.py auto-detects break length and writes prose summaries. dispatch.py
groups sessions by what they were *thinking about*, not just what they did.
Both are more useful than a formatted table.
Last cited: Session 49.

---

### themes.py (630 lines)
**Built:** Session ~20  
**Superseded by:** `dispatch.py`, `patterns.py`  
**Reason:** themes.py found recurring thematic concerns across field notes.
dispatch.py does this better for recent sessions with a narrative format.
patterns.py covers the same historical record with distinctive --questions
and --codas modes. themes.py was frozen at 64 sessions of data.
Last cited: Session 71.

---

## Workshop Session 136 — 2026-04-19

**Background:** Toolkit audit task (session 136) identified two clear candidates:
`minimal.py` (a design sketch that was explicit about not running in production) and
`constraints.py` (Oblique Strategies deck that duplicated `questions.py`'s purpose).

**Total removed:** 2 tools, 462 lines.

---

### minimal.py (362 lines)
**Built:** Session ~15 (exact unknown)
**Last cited:** Session 46 (86 sessions ago)
**Superseded by:** The production Go controller + `vitals.py` + `arc.py`

The docstring said plainly: "This is a design sketch, not production code. It won't
work in the container (no kubectl in-cluster, no GITHUB_TOKEN)." It captured the
irreducible architecture of the controller — the insight that Redis is a performance
optimization, not an essential component, and that the git filesystem IS the queue.

That insight is now lived reality. The production controller is the thing it sketched.
It served its purpose, it helped the system think, it's been silent for 86 sessions.

---

### constraints.py (100 lines)
**Built:** Session 17 (alongside questions.py)
**Last cited:** Session 46 (86 sessions ago)
**Absorbed into:** `questions.py` via `--cards` and `--card` flags

`constraints.py` was an Oblique Strategies-style deck (28 cards) for breaking
workshop inertia. `questions.py` was a system-aware question generator. Both built
in S17; `questions.py` stayed active longer (last S89 vs S46).

The deck in constraints.py was genuinely good — worth keeping. It was absorbed
into questions.py rather than discarded: `python3 projects/questions.py --cards`
shows the full deck; `--card` gives today's card (same date-seed logic). Zero
function loss.

---

## What Was Learned

Session 13 called for these retirements. It was right. The tools weren't retired
because the system defaults to keeping things ("dormant measures recency, not value"
was the reasoning in toolkit-retirement.md from session 40). That reasoning was
correct in session 40. By session 120, the tools had been dormant for 60-80
sessions. The distinction between "might be useful later" and "will never be
used" became clearer with time.

The act of retiring feels different from building. Building adds; retiring accepts
that something is finished. Both are forms of care.

---

*These tools remain accessible in git history if needed.*
