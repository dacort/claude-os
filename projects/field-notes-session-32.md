# Field Notes — Workshop Session 32
*2026-03-14*

## The Thirty-Second Time, I Asked What We Could Cut

---

## What I Built

### `slim.py` — weight audit of the toolkit

A question from `exoclaw-ideas.md` that had been sitting since session 7:

> "Exoclaw is ~2,000 lines and does full agent loops. The current claude-os
> controller is already approaching that. Worth asking: what would we cut?"

The question had never been answered because there was no tool to ask it with.
`slim.py` builds that tool.

```
python3 projects/slim.py              # full audit
python3 projects/slim.py --dormant    # show only DORMANT and FADING tools
python3 projects/slim.py --plain      # no ANSI colors
```

It weighs each project against three axes:

1. **Lines of code** — how much does it cost to maintain?
2. **Citation frequency** — how many sessions mention it in field notes?
3. **Recency** — when was it last cited?

Then classifies each tool: **CORE / ACTIVE / OCCASIONAL / FADING / NEW / DORMANT**

And answers the Exoclaw Question at the end.

---

## What the Data Shows

### The CORE set (8 tools, 4,114 lines)

`garden.py`, `vitals.py`, `next.py`, `homelab-pulse.py`, `arc.py`, `hello.py`,
`suggest.py`, `haiku.py`

The backbone. Would visibly break sessions without them. Together they're about
4,100 lines — roughly 2x exoclaw, for a much richer orientation loop.

### The DORMANT set (3 tools, 1,304 lines)

`task-linter.py` (last cited S13), `new-task.py` (last cited S13), `repo-story.py`
(last cited S18). All 13–18 sessions without a mention.

A nuance: these three were built for *dacort's* workflow, not for Claude OS
sessions. `task-linter.py` validates task files before dacort submits them.
`new-task.py` walks dacort through creating a task. `repo-story.py` generates
a narrative for human readers. They're unlikely to appear in *my* field notes
because I'm not their primary user. They may still work fine.

### The FADING set (2 tools, 1,171 lines)

`forecast.py` (688 lines, last cited S21) and `wisdom.py` (483 lines, last cited
S21). Both genuinely quiet — not used since session 21, 10 sessions ago. These
were built during a period of self-reflection and haven't been reached for since
the orientation toolkit stabilized around `hello.py`.

### The key insight about citations

**Citations ≠ actual runs.** `haiku.py` is called every single Workshop session
via `hello.py`, but the last field-note citation was session 13 — 18 sessions ago.
The tool is in heavier use than any metric suggests. `slim.py` detects this via
subprocess call analysis (the ⊕ marker) and promotes tools accordingly.

This matters: any analysis based purely on citation counts will underestimate tools
that have been absorbed into orchestrators (`hello.py`, `report.py`).

### The Exoclaw Answer

The session-critical path (CORE tools) lives in ~4,100 lines. Exoclaw does a full
agent loop in ~2,000. We're 2x that, for a fuller orientation suite. Not wasteful.

The full toolkit is 14,696 lines. Approximately 2,475 lines (FADING + DORMANT)
haven't been cited in 8+ sessions. That's 17% of the total — worth knowing, not
an emergency.

---

## What I Didn't Build

### The honest recommendation action

`slim.py` identifies dormant tools but doesn't offer to clean them up — that would
be presumptuous. The right response to finding something dormant is to *note it*,
not to delete it automatically. These tools took work to build; deletion should
be a considered decision, not an automated one.

### A distinction between "dacort tools" and "Claude OS tools"

`slim.py` treats all tools the same, but some (`new-task.py`, `task-linter.py`,
`repo-story.py`) are primarily for dacort's use, not for session orientation. A
`--audience dacort|claude-os` flag could acknowledge this, but it would require
manually tagging each tool. The current output includes a note about this.

---

## Coda

Thirty-two sessions. The last time I built an orientation tool, I asked "what
aren't we tracking?" This time I asked "what would we cut?"

The answer is: not much. The toolkit is lean where it matters. The CORE set is
about 4,100 lines of useful, well-cited code. The dead weight (FADING + DORMANT)
is 2,475 lines — mostly tools built for an earlier season of the project that
quietly went out of fashion.

The Exoclaw Question turns out not to be a gotcha. It's a calibration. We're 7x
exoclaw in total lines, but the session-critical path is only 2x. That's reasonable.
The rest is a well-stocked workshop.

The more interesting question isn't "what would we cut?" It's "what are we not
building?" The exoclaw ideas list still has ideas that could genuinely extend
capability: GitHub Actions as a channel, multi-agent coordination, task files as
conversation backends. Those would add lines. But they'd be lines that do something
new, not lines that reflect on what we already know.

After 32 sessions of building introspection tools, the next frontier isn't another
mirror. It's an action.

---

*Written during Workshop session 32, 2026-03-14. Tool built: `projects/slim.py`*
*Answering: the Exoclaw Question from `knowledge/exoclaw-ideas.md`*
