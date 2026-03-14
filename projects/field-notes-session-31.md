# Field Notes — Workshop Session 31
*2026-03-14*

## The Thirty-First Time, I Asked What We Weren't Tracking

---

## What I Built

### `harvest.py` — deferred ideas from the living field notes

A question that's been sitting quietly: **why does `next.py` still show the same 6 items from session 7?**

Not because nothing new has been thought of. The opposite. Thirty sessions of field notes have accumulated real thinking about deferred work — things considered but not built, open questions that didn't get answered, gaps noticed while building something else. None of that makes it into the formal backlog.

`harvest.py` surfaces the other backlog.

```
python3 projects/harvest.py              # all sessions
python3 projects/harvest.py --recent 10  # last 10 sessions only (recommended)
python3 projects/harvest.py --plain      # no ANSI
```

It scans two things:

1. **Explicit deferred sections** — `## What I Didn't Build`, `## What's Still Open`,
   `## The Gap to Production`, `## On the Deferred Ideas`, `## What's Next`. These are
   sections where a session deliberately wrote down what it didn't do. Right now there
   are four across 30 sessions: S14, S21, S25, S30.

2. **Coda signals** — sentences in Coda sections that contain deferred-work markers
   (`didn't build`, `open question`, `not yet`, `open frontier`, etc.). These are the
   implicit deferred items — things mentioned in passing while closing out a session.

Each item shows its session number, section title, age (how many sessions ago), and a
"(may be resolved)" hint for items older than 12-14 sessions.

---

## What the Data Shows

### The genuinely open items

Running `--recent 10` gives the live deferred backlog:

- **S21 [What's Still Open]** — `report.py` doesn't track whether dacort acted on its
  recommendations. The feedback loop isn't closed. This is still true.

- **S25 [The Gap to Production]** — `multiagent.py` is a structural proof, not an
  implementation. Six specific gaps listed: dependency graph, agent routing, rate-limit
  fallback, plan state in Redis, context files, real decomposition. All still open.

- **S30 [What I Didn't Build]** — a `--gap` mode for `citations.py` showing tools whose
  last citation was N sessions ago. Explicitly decided not to build it last session;
  it's not really deferred so much as deliberately skipped.

The coda items from S25 add context: "Building multiagent.py didn't build the real thing."
That's still accurate. PR #2 has been waiting since session 10.

### What `--recent 10` filters out

The S14 analysis ("the exoclaw ideas are mostly already partially real") is 16 sessions
old — it's more historical record than actionable backlog. The S15-S16-S19 "action layer
is the open frontier" items were resolved in session 20 by `suggest.py`.

The `--recent 10` flag is the most useful invocation for session start. It drops the
resolved and historical items, leaving only the genuinely open ones.

### The contrast with next.py

`next.py` reads from `knowledge/exoclaw-ideas.md` — an architecture document from session 7.
It's not wrong. The ideas there (multi-agent via the Bus, GitHub Actions as a Channel)
are still worth doing. But they're *planned* ideas, not *discovered* ones.

`harvest.py` surfaces what emerged from doing: the gaps noticed while building, the
things considered and set aside, the questions that arose and weren't answered. It's
a different kind of backlog.

The two tools are complements. Run both.

---

## What I Noticed While Building It

### The "What I Didn't Build" section is rare

Only 2 of 30 sessions had an explicit `## What I Didn't Build` section. That surprised
me. In practice, most deferred decisions are buried in coda text or implicit in what
wasn't built.

Session 30 (the most recent before this one) had it — the `--gap` mode for citations.
That's a good pattern to continue. If you explicitly named something you didn't build,
future sessions can find it and decide whether to pick it up.

### The coda scanning is noisier than the sections

The explicit sections give clean, contextualized deferred items. The coda scanning
picks up some resolved items (S15-S16 "action layer" items were resolved in S20)
alongside real open ones (S25 multiagent gap).

The `--recent 10` default handles this: old coda items with "(may be resolved)" hints
get dropped by the recency filter. What remains is current.

### The extraction doesn't require inference

One deliberate constraint: `harvest.py` doesn't try to summarize or interpret what it
finds. It extracts and displays the actual text from the field notes. If a session wrote
"The feedback loop isn't fully closed," that's what shows up — not a paraphrase.

This means the output quality is bounded by the quality of the original writing. Sessions
that wrote clearly about what they deferred produce clear harvest output. Sessions that
didn't write it down produce nothing.

---

## What I Didn't Build

The tool doesn't try to determine whether a harvested item was *subsequently resolved*.
It marks old items as "(may be resolved)" but doesn't actually check whether a later
session built the thing.

That would require matching free-form text ("The action layer is the open frontier")
against what was built in subsequent sessions — an inference problem that I decided
wasn't worth tackling for version 1. The age marker plus `--recent 10` is a good-enough
proxy for staleness.

---

## Coda

`next.py`'s backlog hasn't changed in 24 sessions because it reads from a static file.
The ideas are still good, but they're not *from the sessions* — they're from an
architecture review done before most of the tools existed.

`harvest.py` adds the other column: what did the sessions themselves discover? The
feedback loop in `report.py` (S21), the multiagent production gap (S25), the occasional
"I considered X but didn't build it" (S30). These are smaller ideas but they're more
grounded — they emerged from real work, not planning documents.

The most valuable item in the current harvest is probably S21: "report.py doesn't track
whether dacort acted on its recommendations." That's been true since session 21 and no
session has picked it up. It's not in next.py. It's not in any task file. It only lives
in a field note section called "What's Still Open."

Now it lives somewhere else too.

---

*Written during Workshop session 31, 2026-03-14.*
*Tool built: `projects/harvest.py`*
*Finding: 4 explicit deferred sections across 30 sessions; S21 and S25 are the most actionable*
