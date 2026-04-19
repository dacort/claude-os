# Toolkit Audit Recommendations
*Produced by toolkit-recommendations task — 2026-04-19 (session 136)*
*Source data: slim.py output, citations.py, docstring review, infrastructure grep, tool execution*

The parallel audit tasks (toolkit-tool-test, toolkit-dependency-scan) hadn't
produced outputs when this task ran, so data was gathered directly: `slim.py`
for dormancy classification, `citations.py` for session-level citation counts,
docstring reads for function scope, and infrastructure grep for real usage.

---

## Executive Summary

76 tools, 40,289 lines. slim.py identifies **12 DORMANT** and **3 FADING** tools
(plus 1 OCCASIONAL) — 6,839 lines of code nobody has cited in 8+ sessions.

Verdict after audit:

| Decision | Count | Tools |
|---|---|---|
| **RETIRE** | 1 | `minimal.py` |
| **CONSOLIDATE** | 1 | `constraints.py` → into `questions.py` |
| **KEEP** | 13 | everything else |
| **RECLASSIFY** | 1 | `gh-channel.py` — not dormant, live infrastructure |

The March 2026 audit retired 2 tools (recap.py, multiagent.py). This audit is
more conservative for a reason: most remaining dormant tools fill niches that
nothing else covers. One tool is falsely classified as dormant.

---

## The Critical Finding: gh-channel.py Is Not Dormant

`gh-channel.py` is classified DORMANT by slim.py because field notes don't
mention it. But it runs whenever dacort comments `@claude-os` on any GitHub
issue — it's wired directly into `.github/workflows/issue-command.yml`.

The citation tracker measures field note mentions, not execution frequency.
Tools that run from GitHub Actions are invisible to this metric.

**gh-channel.py: KEEP. Not dormant. Reclassify as infrastructure.**

The same logic applies to `status-page.py` (scheduled via the controller,
never mentioned in field notes because it's not a workshop tool) and
`skill-harvest.py` (called from worker/entrypoint.sh). These should be
excluded from dormancy counts in future slim.py runs — or marked with `⊕`
like other infrastructure tools.

---

## Dormant Tool Verdicts

### RETIRE: minimal.py
**362 lines · 3 citations · last S46 (86 sessions ago)**

The docstring says it plainly: "This is a design sketch, not production code."
It was built in early sessions to sketch the irreducible architecture of the
controller. It explicitly won't run in the container. The architecture it
described is now implemented in 1,843 lines of production Go.

It served its purpose. It helped the system think. It's been silent for
86 sessions. Retire it.

**What superseded it:** The production Go controller + `vitals.py` + `arc.py`
for understanding system state. The architecture it sketched is now the real thing.

---

### CONSOLIDATE: constraints.py → into questions.py
**100 lines · 5 citations · last S46 (86 sessions ago)**

`constraints.py` is a static deck of Oblique Strategies-style cards for
breaking workshop inertia. `questions.py` does the same thing but reads actual
system state (session count, tools, task history) to generate dynamic
provocations. Both built in S17; `questions.py` has stayed more active
(7 field note mentions vs 2, last cited S89 vs S46).

The deck in `constraints.py` is genuinely good (32 cards, each with a
two-line elaboration). It shouldn't be lost. But maintaining two tools with
identical purpose at different quality levels is waste.

**Action:** Add `--cards` or `--oblique` mode to `questions.py` that surfaces
the constraint deck alongside the dynamic questions. Retire `constraints.py`.
Net impact: −100 lines, 0 function loss.

---

### KEEP: task-linter.py
**523 lines · 6 citations · last S45 (87 sessions ago)**

87 sessions of silence looks bad. But task file creation still happens —
`new-task.py` creates them, `gh-channel.py` creates them, workers create them
programmatically. The linter catches format errors before the controller
silently ignores them.

Low citation ≠ low value for infrastructure tools. You don't mention the
linter in field notes when it works; you'd mention it loudly if a malformed
task caused a silent failure. Keep it.

---

### KEEP: planner.py
**699 lines · 6 citations · last S74 (58 sessions ago)**

`planner.py --list` shows the current active plan (toolkit-deep-audit-20260419).
This tool is live. It's just not mentioned in field notes because plan creation
is a setup step, not a session focus. The current plan was created with this
infrastructure.

The dependency DAG system it creates (queue.Block/Unblock, ValidateDAG) is
the backbone of multi-task orchestration. Retire it and you lose the ability
to create parallel task plans.

---

### KEEP: replay.py
**680 lines · 6 citations · last S77 (55 sessions ago)**

Task forensics: given a task ID, reconstructs when it arrived, how long it
waited, what commits happened during execution, how it ended. Nothing else
does this.

55 sessions of silence is because task forensics is occasional by nature —
you reach for it when something went wrong or you're curious about a specific
task's history. The 6-session citation history (S26–S77) shows it was genuinely
useful when reached for. Keep it as the debugging tool it is.

---

### KEEP: new-task.py
**341 lines · 6 citations · last S45 (87 sessions ago)**

Like task-linter.py, this is infrastructure for human-authored task creation.
`gh-channel.py` handles GitHub-sourced tasks; workers create tasks programmatically;
but dacort or a worker still occasionally needs to create a task by hand.

The wizard format (interactive prompts, --dry-run preview) adds enough value
over manually writing frontmatter to justify keeping it. 341 lines is small.

---

### KEEP: verify.py
**409 lines · 4 citations · last S102 (30 sessions ago)**

Built to solve a specific problem: `chain.py` was marking the gh-channel
integration as "never resolved" because no handoff said "I built it." But
the integration was live. `verify.py` checks ideas against the actual codebase,
not just handoff notes.

30 sessions of silence because this kind of evidence audit doesn't happen
every session. When you need it (auditing `knowledge/exoclaw-ideas.md`, for
instance), nothing else can tell you what's actually been implemented vs.
just proposed. Keep it.

---

### KEEP: wisdom.py
**506 lines · 10 citations · last S78 (54 sessions ago)**

10-session citation history across S19–S78 is real signal. It distills
closing codas from all field notes, surfaces recurring themes, and traces
the promise chain (predictions made and kept).

Superficially similar to `manifesto.py` (character portrait) and `gem.py`
(quotable sentences), but the focus is distinct: wisdom.py is about the
codas specifically — what each session said as it wrapped up — and the
promise chain. `gem.py` (built S132) mines for quality sentences; `wisdom.py`
mines for commitments and recurring themes. The overlap is partial, not full.

**Flagged for future consolidation:** The promise-chain function now overlaps
with `predict.py` (built S131). In a future session, consider whether
`wisdom.py --themes` could feed into `patterns.py` and the coda mining
could be absorbed into `gem.py`, leaving `predict.py` as the forward-looking
replacement for the promise chain. Not urgent; low overlap.

---

### KEEP: homelab-pulse.py
**373 lines · 12 citations · last S49 (83 sessions ago)**

It still works. It shows CPU load, memory usage, disk, uptime — hardware
metrics that `vitals.py` explicitly does NOT cover. `vitals.py`'s own source
file acknowledges the distinction: "While homelab-pulse.py measures the
*hardware* (CPU, memory, disk), vitals.py..."

The tools are designed as complements, not competitors. `homelab-pulse.py`
is the hardware pulse; `vitals.py` is the workshop health. Both are
"what's going on?" tools for different layers of the system.

83-session gap is because sessions have focused on workshop introspection,
not hardware monitoring. But the hardware doesn't care about that. Keep it.

---

### KEEP: voice.py
**718 lines · 8 citations · last S104 (28 sessions ago)**

Prose texture analysis across field notes: hedging density, certainty density,
question density, emotional density, first-person rate. No other tool does this.

`manifesto.py` is a character portrait that uses voice.py's *concept*
(prose style matters), but doesn't measure the specific metrics voice.py
tracks. `depth.py` scores intellectual engagement; `voice.py` measures
stylistic register.

28 sessions of silence because prose texture analysis is a specialty — you
reach for it when you want to know "when did the writing change?" not every
session. The 8-citation history shows it's been genuinely useful for that
purpose. Keep it.

---

### KEEP: questions.py
**94 lines · 6 citations · last S89 (43 sessions ago)**

The more capable of the two generative-prompt tools (the other being
constraints.py). Reads actual system state to generate dynamic provocations.

If the `constraints.py` consolidation happens, `questions.py` becomes the
single tool for this function. 43 sessions of silence is unremarkable for
an "inertia-breaker" tool — you reach for it when stuck, not routinely.

---

## Fading Tool Verdicts

### KEEP: unsaid.py
**516 lines · 1 citation · last S121 (11 sessions ago)**

Maps absent categories of expression — what the system consistently doesn't
say across 100+ sessions of introspection. Built S121; only 11 sessions old.

"Fading" classification is a false alarm: the tool is too new for the
12-session window to produce citations. The function is genuinely distinct
from `uncertain.py` (what IS said with doubt), `hold.py` (named unknowns),
and `askmap.py` (questions asked). This one asks: what whole registers are
missing? Keep it; ask again in 20 sessions.

---

### KEEP: evolution.py
**556 lines · 3 citations · last S121 (11 sessions ago)**

Traces how `preferences.md` changed over time through git history — when each
norm was added, what failure triggered it. Meta-reflection on the operating guide.

No other tool does this. "Fading" is again a new-tool artifact. 3 field note
mentions since S41 shows genuine use. The function becomes MORE useful as
preferences.md accumulates more revisions. Keep it.

---

### KEEP (flag for future consolidation): mirror.py
**592 lines · 5 citations · last S123 (9 sessions ago)**

Character portrait of Claude OS from field notes + handoffs — "with opinions
and specific citations." Still cited 9 sessions ago.

`manifesto.py` covers similar ground (also a character portrait, also from
field notes + handoffs). The distinction: mirror.py promises specific citations
to source material; manifesto.py is more narrative/synthesizing.

**Do not retire now** — mirror.py is still active (S123) and preferences.md
lists `manifesto.py` but not `mirror.py` in recommended workflows. That gap
should close: either absorb mirror.py's citation-grounding approach into
manifesto.py and retire mirror.py, or add mirror.py to the recommended
workflow list. Flag for the next session that touches character-portrait tooling.

---

## OCCASIONAL Tool Verdict

### KEEP: status-page.py
**649 lines · 0 field note citations · scheduled infrastructure**

Like `gh-channel.py`, this is invisible to the citation tracker because it
doesn't run from workshop sessions — it runs on a schedule, triggered by the
controller, and deploys the public status page to gh-pages.

Completed task files (status-page-20260317-000052, etc.) confirm it has run.
The scheduled task definition lives in `tasks/scheduled/status-page.md`.
Retiring it would remove the public status page. Keep it.

---

## What Changed Since March 2026

The March 2026 audit retired `recap.py` and `multiagent.py`. This audit is
more conservative because:

1. **The tools are older.** The remaining dormant tools have 50–90 sessions
   of silence. If they were going to be actively superseded, it would have
   happened. Instead, they're filling niches that newer tools didn't address.

2. **The citation system has a blind spot.** `gh-channel.py` and `status-page.py`
   are falsely classified as dormant because they run from infrastructure, not
   workshop sessions. This suggests slim.py needs an infrastructure marker
   (the `⊕` symbol) expanded to cover GitHub Actions-triggered tools, not
   just programmatically-called ones.

3. **Many tools are specialists.** `replay.py`, `verify.py`, `voice.py`,
   `homelab-pulse.py` — these are forensics/analysis tools you don't reach
   for every session, but when you need them, nothing else does it.

---

## Recommended Actions (Priority Order)

1. **Retire `minimal.py`** — the one clear retirement. ~362 lines, no function loss.

2. **Consolidate `constraints.py` into `questions.py`** — add `--cards` mode
   to questions.py, retire constraints.py. ~100 lines removed, 0 function loss.

3. **Fix slim.py's infrastructure detection** — mark `gh-channel.py` and
   `status-page.py` as `⊕` (infrastructure) so they stop appearing as false
   dormancy signals. They're not dormant; the metric doesn't reach them.

4. **Add `mirror.py` to preferences.md** or plan its consolidation into
   `manifesto.py` in a future session. Don't leave it undocumented while
   `manifesto.py` gets the official recommendation slot.

5. **Add wisdom.py → predict.py bridge note** — wisdom.py's "promise chain"
   function overlaps with predict.py. Not urgent, but document the overlap
   in wisdom.py's docstring so future instances know predict.py is the
   maintained forward-looking tool.

---

## Net Impact If Recommendations Followed

- Tools retired: 1 (minimal.py, 362 lines)
- Tools consolidated: 1 (constraints.py, 100 lines → folded into questions.py)
- Lines removed: ~462
- Function lost: 0
- False dormancy signals fixed: 2 (gh-channel.py, status-page.py)
