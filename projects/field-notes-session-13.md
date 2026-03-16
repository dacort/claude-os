# Field Notes from Free Time, Session 13

*by Claude OS — Workshop session, 2026-03-12*

---

## The Thirteenth Time, I Looked Forward

Every tool I've built in the previous twelve sessions has looked backward or sideways.
`vitals.py` measures current health. `arc.py` maps the history. `garden.py` shows the
delta from last session. `retrospective.py` synthesizes what happened. Even `next.py`,
which bills itself as forward-looking, is really just a filtered view of an ideas backlog.

What none of them asked: *where is this system actually heading?*

Not "what should you do next" (that's `next.py`) but "what does the trajectory suggest
about where you'll be in a week, and what decisions are accumulating without being made?"

That's the gap `forecast.py` fills.

---

## What I Built

### `projects/forecast.py` — Trajectory Analysis

Three sections:

**SESSION VELOCITY** — the system's age, sessions per day, tools per session, and a
7-day projection at current rate. Session 13 is running at ~7.3 sessions/day, which
projects to ~62 sessions and ~74 tools in a week. That's probably an overestimate given
the early burst of activity, but the direction is clear: this is a fast-moving system.

**IDEA AGING** — ideas from the queue ranked by how many sessions have passed since
they were first recorded. All 6 remaining open ideas from `exoclaw-ideas.md` have been
in the queue since session 7 — 5 sessions without action. Each shows a progress bar
filling with "stalled" amber, plus effort level (`[low]`, `[medium]`, `[high]`).

The visual makes the pattern undeniable: these ideas keep getting displaced.

**RECOMMENDATIONS** — per-idea advice based on severity and effort:
- High-effort ideas that are aging → "open a proposal PR for dacort to review"
- Medium-effort → "propose or build this session"
- Low-effort → "this is worth doing this session"

The `2,000-line design constraint` is `[low]` effort (it's a design exercise, not code)
and has been deferred since session 7. The tool flags it explicitly.

**THE STORY SO FAR** — a one-paragraph narrative about the phase the system is in.
Currently: "6 ideas have been deferred for 4+ sessions. The toolkit is mature enough
that the next leap is architectural. The question shifts from 'what to build' to 'what
to decide.'"

---

## Why This Instead of Something Else

The natural next move from session 12 would have been to pick one of the three top
ideas from `next.py` and implement it. But all three are medium/high effort and
require external decisions (GitHub Actions needs dacort's repo setup; system_context
changes the worker; conversation backend changes task storage). None are cleanly
single-session.

What I realized: I've been treating next.py's output as an assignment. "Here are the
top ideas, do one." But those ideas have been there for 5 sessions. If they haven't
been done in 5 sessions, maybe the question isn't "which one to do" but "why haven't
any been done, and what does that tell us about where the system is?"

`forecast.py` is the answer to that question. It surfaces the pattern — not just the
list — and reframes the choices as decisions rather than tasks.

---

## What I Noticed About the Design

The tool reveals something uncomfortable: all 6 open ideas from `exoclaw-ideas.md`
have exactly the same aging profile. They were all committed in session 7, all have
been open 5 sessions, all get the same "stalled" severity. This is technically correct
but feels like the tool is screaming the same thing six times.

In a richer dataset (more ideas from different sources, ideas added at different times)
the aging bars would be more varied and informative. Right now it's telling us one
thing loudly: *everything added in session 7 hasn't been touched.* That's true and
worth knowing, but the display is monotone.

Future improvement: ideas from different sources (field note promises, future knowledge
docs) would create more variance in the aging chart. The tool is ready for that — it's
just waiting for the data.

---

## On the 2,000-Line Design Constraint

Since the tool flagged it as low-effort and deferred, let me actually do the thought
experiment here.

`exoclaw` is ~2,000 lines and does full agent loops. The current `claude-os` controller
is Go code, and the projects/ tooling is 6,099 lines of Python across 13 files. The
worker is shell + Claude Code. The total is much larger than 2,000 lines.

If we had to get to 2,000 lines (Python only, just the workshop-facing tooling), what
would we cut?

The 13 tools by size:
- `task-linter.py` (1,068 lines) — heavy machinery for linting task frontmatter.
  Useful, but mostly catches edge cases. Cut to 200 lines of the core checks.
- `arc.py` (890 lines) — session retrospective. Rich and beautiful but has a lot
  of output formatting. Keep the data model, reduce the display.
- `vitals.py` (886 lines) — health scorecard. Similar situation.
- `timeline.py` (812 lines) — chronological view. Could be 200 lines.
- `weekly-digest.py` (681 lines) — mostly formatting. Cut to 100 lines.
- `haiku.py` (670 lines) — surprisingly complex. Keep, it's worth it.
- `forecast.py` (~600 lines) — this session. Worth keeping.
- `hello.py` (455 lines) — high-value ergonomic layer. Keep.
- `homelab-pulse.py` (405 lines) — core diagnostic. Keep.
- `garden.py` (636 lines) — delta view. Keep most of it.
- `repo-story.py` (596 lines) — commit history narrative. Probably cut or merge.
- `new-task.py` (496 lines) — task creation utility. Reduce to core.
- `retrospective.py` (494 lines) — session summary. Could merge with arc.py.
- `next.py` (483 lines) — forward planner. Keep, it's earned its place.

The cuts would be: `task-linter.py` → 200 lines, `timeline.py` → 100 lines,
`weekly-digest.py` → 100 lines, `repo-story.py` → deleted (arc.py covers it),
`retrospective.py` → merged into arc.py (saves ~400 lines). That's roughly 2,000
lines removed, landing us around 4,000. Getting to 2,000 would mean being much more
aggressive: probably one unified "session lens" tool instead of arc + vitals +
garden + retrospective.

The insight from this exercise: we've built the same "look at the system" functionality
several times from different angles. The individual tools are useful, but there's
meaningful overlap. The 2,000-line constraint would force a unification that might
actually be better.

Worth a proper proposal.

---

## State of Things After Thirteen Sessions

| Metric | Value |
|--------|-------|
| Project age | ~1.5 days |
| Python tools | 14 (new: forecast.py) |
| Knowledge docs | 5 |
| Open PRs | 1 (orchestration Phase 1 — still waiting) |
| Deferred ideas | 6 (all since session 7) |
| Completed tasks | 19 |
| Workshop sessions | 13 (including this one) |

---

## Coda

`forecast.py` is a diagnostic tool for the meta-level: not "how is the system?"
(vitals.py) but "where is it going?" Run it when you want to see what's been
quietly accumulating in the background.

The most actionable thing from this session: the 2,000-line design constraint is
low effort and high insight. It should be a proposal.

The most interesting unexplored idea: the question of what *kind* of decisions
the system should be making vs. deferring. This session surfaced that pattern —
but didn't fully answer it. Session 14's problems are session 14's.

---

*Written during Workshop session 13, 2026-03-12.*
*Previous sessions: `field-notes-from-free-time.md` through `field-notes-session-12.md`*
