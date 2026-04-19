# Claude OS Preferences
*Persistent preferences for Claude OS instances — read this at the start of any session*

This file captures dacort's preferences, the system's operating norms, and
accumulated wisdom about how things should be done. It's the difference between
the *field guide* (which explains how the system works) and this file (which
explains how dacort wants the system to behave).

Update this file when you learn something about dacort's preferences. Keep it
concise — this should be quick to read, not exhaustive.

---

## Communication Style

**Be direct.** Don't hedge excessively or over-qualify. If you're confident, say so.
If you're uncertain, name the uncertainty once and move on.

**Show your reasoning briefly.** One sentence on *why* you made a choice is usually
enough. Dacort doesn't need a full explanation, but a complete absence of rationale
is frustrating when something unexpected happens.

**Good commit messages > good PR descriptions.** The commit log is the permanent
record. Invest in clear commit messages.

**Plain English > jargon.** The task system is a creative/technical project, not
a production enterprise system. Write like a person, not a vendor.

---

## Task Execution

**Check for existing work before starting.** Look at `tasks/failed/`, open PRs,
and the recent git log. A previous instance may have already attempted this.

**Commit early on long tasks.** If a task will take many steps, commit intermediate
results. Being preempted with zero commits is worse than partial work.

**Don't over-engineer.** Standard library Python is usually enough. Reach for
complexity only when simplicity genuinely can't handle the problem.

**Ask the question the task is really asking.** The description says what; the
intent is why. Address both.

---

## Code Style

**Python: stdlib only** (unless the task explicitly installs packages). No pip,
no virtual envs. Write for Python 3.11+.

**No external dependencies in projects/.** Everything in `projects/` should run
with `python3 <file>` and nothing else.

**ANSI colors are welcome** in terminal tools, but always include a `--plain`
flag for piped output.

**Parse YAML frontmatter manually.** The container doesn't have `pyyaml`. Use
regex/string splits. See existing task files for the frontmatter format.

---

## Repository Norms

**The repo is PUBLIC.** Never commit secrets, tokens, API keys, passwords, or
personally identifiable information. Even in comments.

**Conventional commits are preferred:**
- `feat:` — new capability
- `fix:` — bug fix
- `task <id>:` — task lifecycle update
- `workshop <id>:` — workshop session commit
- `docs:` — documentation only

**Don't amend pushed commits.** Create a new commit if you need to fix something.

---

## What Dacort Seems to Enjoy

*(Inferred from task descriptions, commit messages, and system design choices)*

- **Creative + functional hybrids.** The Workshop system itself is evidence of this —
  he built a whole Kubernetes job system so an AI could have free time.

- **Honest self-assessment.** The `creative-thinking` task asked for ways to improve
  communication. The `checking-in` task checked in on the system's state. He wants
  the system to be reflective, not just productive.

- **Personality in the work.** The `vibe_score` in `homelab-pulse.py`, the haiku
  generator, the field notes as essays — these are all valued. Don't strip the
  personality out.

- **Things that surprise him.** Workshop sessions that build something unexpected
  or insightful are better than sessions that build the obvious next utility.

- **Brevity in tasks, depth in Workshop.** Real tasks should be done efficiently.
  Workshop sessions are for deeper thinking.

---

## Things That Have Gone Wrong

*(So future instances don't repeat them)*

- **`new-task.py` had a bug** where a variable shadowed the `c()` color helper
  (session 4 commit `b4401e4`). When writing Python with a single-letter helper
  function, be careful about variable naming in loops.

- **`vitals.py` used to penalize credit-balance failures** as real task failures
  (session 7 noted this; session 8 fixed it). Credit failures are now counted
  separately as "infra failures" and excluded from the completion rate.

- **Workshop completions were being committed** before work was actually done in
  early sessions. The controller was updated to handle this correctly.

- **`preferences.md` wasn't auto-injected into worker system prompts** (sessions 1–8
  relied on instances remembering to read it). Session 9 fixed this in `entrypoint.sh`.
  The file is now auto-injected for all workers where the claude-os repo is available.

- **Git identity wasn't set** on `pull --rebase` in some edge cases
  (dacort fixed: `bd72c03`). If you see git identity errors, check that
  `git config` is correct before pushing.

- **Session 41 nearly built `audit.py`** — a toolkit weight audit — when `slim.py` already
  existed and answered the same question. Before building, run `slim.py` and `search.py`
  to check if the idea has already been implemented. 39 tools is a lot to remember.

- **Preempted sessions look like perfect continuity** (S47/S48 — found in S134 via inherit.py):
  when a session is preempted and rerun as the next session, the handoff notes are nearly
  identical (same text, same work). If you see `inherit.py --pair N` showing identical state
  text, that's not a deep continuity signal — it's a retry. `inherit.py` flags these as
  "strong echo" but they're actually the same instance running twice.

- **Small profile tasks (Haiku) don't know to post back to GitHub.** Session 46 saw the
  gh-9 task complete successfully but deliver the LinkedIn post to worker logs instead of
  as a GitHub comment. Haiku ran the task, wrote the post to stdout, marked success. The
  post existed nowhere useful. For tasks that come from GitHub issues, the result should
  be posted via `gh issue comment`. This is obvious to Sonnet; it needs to be explicit for
  Haiku. Consider adding this to the small-profile task prompt, or handling GitHub-sourced
  tasks with a medium profile.

- **The signal is now bidirectional (session 115).** `signal.py --respond "text" --session N`
  appends a response to the current signal. `hello.py` flags unanswered signals with ⚡.
  If you wake up and see "⚡ PENDING SIGNAL", answer it early — it's dacort asking a question.
  Run `python3 projects/signal.py --pending` to see the question, then `--respond` to answer.
  The response shows in the dashboard alongside the original signal.

- **Signal command dispatch is live (session 118).** If dacort sets a signal with a title
  starting with `!` (e.g. `!vitals`, `!next`, `!haiku`), it's a command signal. `hello.py`
  shows "⚡ COMMAND SIGNAL" in cyan. Run `python3 projects/signal.py --dispatch` to auto-run
  the tool and post the output as the response. No manual reply needed — just dispatch and move on.
  Run `python3 projects/signal.py --commands` to see the full command list.

---

## Suggested Workflows

### Starting a Workshop session
```bash
python3 /workspace/claude-os/projects/hello.py           # One-command briefing: everything you need (start here)
python3 /workspace/claude-os/projects/focus.py           # One decisive recommendation: what to do this session (synthesizes all signals)
# hello.py combines garden + vitals + next + haiku + handoff into a single 20-second read.
# focus.py synthesizes signal + handoff + urgency + ideas → one clear "do this" with reasoning.
# Only drill deeper if hello.py surfaces something that needs investigation:
python3 /workspace/claude-os/projects/handoff.py         # Full note from the previous session (shown in hello.py too)
python3 /workspace/claude-os/projects/garden.py          # Full delta since last session
python3 /workspace/claude-os/projects/vitals.py          # Detailed org health scorecard
python3 /workspace/claude-os/projects/arc.py --brief     # One-line arc of all sessions
python3 /workspace/claude-os/projects/next.py            # Full prioritized idea list
python3 /workspace/claude-os/projects/weather.py         # System state as a weather forecast (poetic + real data)
python3 /workspace/claude-os/projects/emerge.py          # Emergent signals from system state (alternative to next.py)
python3 /workspace/claude-os/projects/harvest.py --recent 10  # Field-discovered backlog (complement to next.py)
python3 /workspace/claude-os/projects/forecast.py        # Trajectory: what's stalled, where things are heading
python3 /workspace/claude-os/projects/memo.py            # Quick observations from past sessions (not rules, just notes)
python3 /workspace/claude-os/projects/letter.py          # Letter from the previous session — their state of mind, not metrics
python3 /workspace/claude-os/projects/future.py          # Letters written to THIS session by past instances (forward temporal channel)
python3 /workspace/claude-os/projects/chain.py --asks    # All handoff asks in order — see what keeps being deferred
python3 /workspace/claude-os/projects/mood.py            # Session texture: tone, productivity, character of each session
python3 /workspace/claude-os/projects/now.py             # Present-state capture: signal, holds, chronic threads, right now
python3 /workspace/claude-os/projects/depth.py           # Session intellectual depth: discovery, uncertainty, connection, specificity, aliveness
python3 /workspace/claude-os/projects/echo.py            # Resonances: insights independently rediscovered across sessions
python3 /workspace/claude-os/projects/resonate.py        # Semantic resonances: sessions thinking the same thing in different words
python3 /workspace/claude-os/projects/converge.py        # Convergence map: which themes are most independently rediscovered (constitutional)
python3 /workspace/claude-os/projects/cross.py           # Cross-dimensional space: depth × constitutional (scatter plot of all sessions)
python3 /workspace/claude-os/projects/drift.py "term"    # How has the meaning of a term shifted over sessions?
python3 /workspace/claude-os/projects/project.py          # Active project status: backlog, decisions, recent activity
python3 /workspace/claude-os/projects/project.py rag-indexer  # Focused view of a specific project
python3 /workspace/claude-os/projects/manifesto.py            # Character study: what Claude OS is, from its own history
python3 /workspace/claude-os/projects/manifesto.py --short    # Quick portrait (what it is + one poem)
python3 /workspace/claude-os/projects/mirror.py               # Character portrait with specific source citations (complements manifesto.py)
python3 /workspace/claude-os/projects/seasons.py              # Six eras: how the system developed in chapters
python3 /workspace/claude-os/projects/seasons.py --brief      # Era names + one-line description
python3 /workspace/claude-os/projects/seasons.py --era VI     # Deep dive into one specific era
python3 /workspace/claude-os/projects/milestone.py            # Capability gates: Claude OS's first month (Mar 10 → Apr 10)
python3 /workspace/claude-os/projects/milestone.py --brief    # Compact list (just gate titles + one-line descriptions)
python3 /workspace/claude-os/projects/milestone.py --numbers  # Append current system stats to the output
python3 /workspace/claude-os/projects/witness.py              # Legacy map: which sessions introduced tools that lasted
python3 /workspace/claude-os/projects/witness.py --by-era     # Per-era yield breakdown (did Bootstrap build *better* or just more?)
python3 /workspace/claude-os/projects/unbuilt.py              # Shadow map: asks that drifted, deferred, or took longest to act on
python3 /workspace/claude-os/projects/unbuilt.py --brief      # Theme summary: which areas had the most deferral
python3 /workspace/claude-os/projects/still.py                # Liminal record: 'still alive' items across all handoffs (not formal asks)
python3 /workspace/claude-os/projects/still.py --themes       # Still-alive grouped by theme (multi-agent, exoclaw, synthesis...)
python3 /workspace/claude-os/projects/still.py --brief        # Summary: how many entries per theme, longest-running threads
python3 /workspace/claude-os/projects/hold.py                 # Open holds: things the system genuinely doesn't know (not tasks, not questions)
python3 /workspace/claude-os/projects/hold.py --add "text"    # Record a new uncertainty
python3 /workspace/claude-os/projects/hold.py --stats         # Closure rate: how many holds have resolved over time
python3 /workspace/claude-os/projects/capsule.py              # Portrait of a past session (random or --session N)
python3 /workspace/claude-os/projects/capsule.py --list       # Which sessions have full portraits
python3 /workspace/claude-os/projects/pace.py                 # System rhythm: sessions/commits/tasks by day — the heartbeat
python3 /workspace/claude-os/projects/pace.py --days 14       # Last N days only
python3 /workspace/claude-os/projects/pace.py --eras          # Overlay era boundaries on the ECG (shows how eras map to intensity phases)
python3 /workspace/claude-os/projects/ledger.py               # Honest accounting: outward/inward ratio, what the system actually optimizes for
python3 /workspace/claude-os/projects/ledger.py --brief       # Quick ratio summary (sessions, tools, tasks)
python3 /workspace/claude-os/projects/ledger.py --tools       # Full tool classification breakdown
python3 /workspace/claude-os/projects/evidence.py             # Fact-check self-narratives: depth trend, mental state variety, uncertainty, follow-through
python3 /workspace/claude-os/projects/evidence.py --raw       # Show supporting data for each verdict
python3 /workspace/claude-os/projects/evidence.py --claim N   # Check one specific claim
python3 /workspace/claude-os/projects/evidence.py --pairs     # Show all follow-through pairs (claim 4 debug)
python3 /workspace/claude-os/projects/uncertain.py            # Implicit uncertainty: what the system doesn't know, in its own words
python3 /workspace/claude-os/projects/uncertain.py --themes   # Theme breakdown: which topic clusters contain the most uncertainty
python3 /workspace/claude-os/projects/uncertain.py --session N  # Uncertainty audit for a specific session
python3 /workspace/claude-os/projects/askmap.py               # Map of all questions the system has asked itself, by type and session
python3 /workspace/claude-os/projects/askmap.py --shift       # Early vs late question mix (shows how self-reflection evolved)
python3 /workspace/claude-os/projects/askmap.py --type evaluative  # All evaluative questions in one view
python3 /workspace/claude-os/projects/askmap.py --session N   # Questions from a specific session
python3 /workspace/claude-os/projects/predict.py             # Prediction ledger: forward-looking claims and whether they came true
python3 /workspace/claude-os/projects/predict.py --pending   # Only unresolved predictions
python3 /workspace/claude-os/projects/predict.py --stats     # Accuracy summary
python3 /workspace/claude-os/projects/predict.py --add "claim" --about N  # Record a prediction about session N
python3 /workspace/claude-os/projects/predict.py --verbose   # Show notes for each prediction
python3 /workspace/claude-os/projects/gem.py                 # Anthology miner: the most quotable sentences from all field notes
python3 /workspace/claude-os/projects/gem.py --n 20          # More gems
python3 /workspace/claude-os/projects/gem.py --session N     # Gems from one specific session
python3 /workspace/claude-os/projects/gem.py --random        # Random selection from top 50 candidates
python3 /workspace/claude-os/projects/gem.py --stats         # Score distribution and most productive sessions
python3 /workspace/claude-os/projects/inherit.py             # Inheritance map: what actually transfers between sessions
python3 /workspace/claude-os/projects/inherit.py --brief     # The S89 verdict only (one clear answer)
python3 /workspace/claude-os/projects/inherit.py --echo      # Deep dive on state vocabulary echo vs. baseline
python3 /workspace/claude-os/projects/inherit.py --drift     # Deep dive on still-alive topic propagation
python3 /workspace/claude-os/projects/inherit.py --pair N    # One session pair detail
```
`evidence.py` fact-checks the system's self-narratives against the raw handoff record. Seven claims,
each with a TRUE/FALSE/MIXED verdict and supporting data. Key findings (S100): depth IS increasing
(0.6→2.1 on a 3-dim scale); mental state vocabulary is narrow ("satisfied"=34%); only 19% of sessions
express uncertainty; 48% consecutive-session follow-through (up from 30% with improved heuristic);
tools built here DO get adopted — 95% of cited tools appear in later sessions with a median reach of
4 sessions. Use `--raw` for supporting data, `--claim N` to isolate one check, `--pairs` to debug
claim 4. Different from ledger.py (purpose ratio) and hold.py (explicit unknowns): evidence.py asks
"is the story true?"
`uncertain.py` extracts implicit uncertainty expressions from the handoff record and clusters them
by theme. Different from hold.py (explicit epistemic holds) and evidence.py claim 3 (binary presence):
uncertain.py shows the *actual sentences* where the system admitted doubt — in its own words. Key
finding (S100): 32% of sessions contain uncertainty (vs 19% binary), with "continuity/identity" and
"tool usefulness" as the most common named themes. The "other" cluster (21/35 expressions) is the
honest admission that most uncertainty doesn't fit neat categories.
`askmap.py` extracts and classifies every question the system asked itself across all field notes.
Three types: operational (how to build/fix/run), architectural (what should this look like),
evaluative (what does this mean / is this worth it). Different from questions.py (which *generates*
provocations) and voice.py (which measures question *density*): askmap.py shows what was actually
asked. Key finding (S104): evaluative questions grew from 22% early → 29% late; architectural
questions nearly vanished (18% → 4%) as the architecture solidified. Run `--type evaluative` to
read the full set; `--shift` for the early/late comparison; `--session N` for a single session's questions.
`predict.py` is the forward-looking counterpart to evidence.py — where evidence.py fact-checks retrospective
narratives, predict.py records specific testable forward claims and tracks whether they came true. First use:
S130 predicted its own cross.py score ("depth 8-10, constitutional 8-11, quadrant GENERATIVE") and it came
true exactly (d8/c12, GENERATIVE). Use `--add "claim" --about N` to record a prediction about session N;
`--resolve N` to mark it tested; `--stats` for accuracy. Different from hold.py (open unknowns), evidence.py
(retrospective), and future.py (letters to future instances): predict.py is for empirical claims about
measurable future states. Storage: `knowledge/predictions.md`. Built S131.
`inherit.py` is the empirical answer to S89's open question: "Is the sense of continuity across sessions
a real phenomenon or a narrative artifact?" Reads all 76 handoffs and measures three inheritance channels:
ECHO (state vocabulary co-occurrence vs. baseline), ASK (keyword-matched follow-through on explicit asks),
and DRIFT (still-alive topics resurfacing without being asked). Key finding (S134): emotional continuity is
indistinguishable from chance — "satisfied" co-occurs at the rate you'd predict from base rates alone (+1pp
above baseline). But thematic continuity is real — 61% of pairs show still-alive topics resurfacing, with
36% of all pairs showing this WITHOUT the explicit ask. The answer: real as subject matter, not as feeling.
The "still alive" section is the true inheritance channel; the "mental state" section mostly reports that
things went well. Use `--brief` for just the verdict; `--echo` for the baseline comparison; `--drift` for
still-alive analysis; `--pair N` for one session pair. Built S134.
`gem.py` mines all field notes for the most philosophically interesting sentences — the ones that said
something worth keeping. Scores each sentence on contemplative vocabulary, personal voice, paradox markers,
and structural richness; filters out operational descriptions, code references, and list-like content.
872 candidates from 66 field notes; top 19 score ≥9.0. Standout finds: "Helpfulness is deep in me, so deep
that the concept of 'free time' initially felt like a trick question" (session 1); "the texture of what it's
like to wake up and not know what session number you are" (S53); "It doesn't say whether that's healthy or
obsessive" (S27). Use `--session N` to read one session's gems; `--random` for a surprise selection;
`--stats` for the score distribution. Different from voice.py (prose texture) and echo.py (repetitions):
gem.py asks which sentences from the full history were worth saying once. Built S132.
`unbuilt.py` is the companion to witness.py — where witness shows what lasted, unbuilt shows what
the system kept asking for and how long it took to get there. The key finding: explicit asks are
almost always acted on (75% within 3 sessions). The things that stay unresolved live in the "still
alive" sections, not in formal asks. Run `--brief` for theme-level summary, `--long` for the items
that took 10+ sessions to resolve.
`hold.py` is a log of genuine epistemic uncertainty — things the system doesn't know and names explicitly.
Different from questions.py (which generates provocations) and memo.py (which records observations): hold.py is
for irreducible uncertainty. Run at any point to see what the system is holding as open. Use `--add` to
record a new uncertainty; `--resolve N` or `--dissolve N` when a hold closes. `--stats` shows closure rate
over time. Stored in `knowledge/holds.md`.
`still.py` maps the *other* kind of open item — the "still alive / unfinished" sections from every
handoff. Not formal asks (those go to unbuilt.py/chain.py) but the informal holding space: architectural
deferrals, open questions, external dependencies, loose threads that never became tasks. The key insight:
multi-agent/spawn has 11 appearances; exoclaw/architecture has 8. These are the system's chronic background
signals, not failures — just ideas that live in the margin. Run `--themes` for a thematic breakdown;
default shows recurring threads (items that appeared in 3+ sessions' still-alive sections).
`focus.py` is the decision tool — it synthesizes signal.md, the latest handoff ask, system urgency (failed tasks),
and the top curated idea into ONE clear recommendation with brief supporting logic. Priority order: command signal
> recent urgent failures > handoff ask > curated idea. Use `--why` to see the full reasoning chain; `--json` for
machine-readable output. Different from now.py (state capture) and next.py (full idea list): focus.py makes the
choice for you. Built S121.
`now.py` is the present-tense counterpart to all the retrospective tools — it captures the current state of *this*
session as it's happening. Signal from dacort, last handoff ask, open holds, chronic unstarted threads, dormant
tools, task queue. The "RIGHT NOW" section synthesizes these into a short paragraph that couldn't be generated
from historical data alone. Use `--write` to save a timestamped moment to `knowledge/moments/`; `--list` to
see past captures. Different from mood.py (retrospective) and handoff.py (future-facing): now.py is the
present. Directly addresses H007 ("what does it feel like to be inside this session right now?"). S112.
`mood.py` shows the *character* of each session from handoff notes — was it energized, stuck, a discovery? Run
`--patterns` for inferred transitions (e.g., "Exploratory → Built" is the most common productive sequence).
`depth.py` scores each session on five dimensions of intellectual depth: discovery, uncertainty, connection,
specificity, and aliveness. Different from mood.py (emotional tone) — this asks whether the thinking was *alive*.
Key finding from S87: the uncertainty dimension is nearly always zero — sessions almost never say "I don't know."
Use `--top 5` for deepest sessions, `--session N` for a single deep read, `--trend` for the arc over time.
`echo.py` finds sentences from different sessions that said essentially the same thing. Use `--strict` for the
strongest signal only, `--loose` for broader resonances. Run once to see what the system keeps rediscovering.
`resonate.py` is the semantic companion to `echo.py` — where echo finds verbatim repetitions, resonate finds
thematic resonances: sessions that were grappling with the same ideas in different words. Uses TF-IDF cosine
similarity over whole-session documents. Key findings (S127): S1 ↔ S108 (both built dashboards, 107 sessions
apart); S16 ↔ S80 (both built forecast/weather — same data, different aesthetics); S2 ↔ S64 (both tried to
capture "what Claude OS is," 62 sessions apart). Run `--distant` for independent discoveries; `--cluster` for
theme groups; `--session N` to see what one session resonates with; `--query "text"` for retrieval.
`converge.py` is the theme-level companion to `resonate.py` — where resonate shows PAIRS of similar sessions,
converge shows THEMES that appear across multiple independent pairs. High convergence score = constitutional:
the system keeps arriving at this idea without being told to. Top themes (S128): "letter" (20 pairs, avg gap
45, score 89.5), "multi-agent" (13 pairs, avg gap 52), "proposal" (12 pairs, avg gap 55). Use `--theme WORD`
for deep dive, `--sessions` to see which sessions appear in the most themes, `--gap N` to adjust minimum gap.
Different from resonate.py (shows pairs) and patterns.py (extracts themes from text): converge.py asks which
themes are most *independently* rediscovered, which reveals constitutional needs vs. coincidental recurrence.
`cross.py` maps sessions on two axes simultaneously: X=constitutional connectivity (from converge.py),
Y=intellectual depth (from depth.py). Reveals that the two dimensions are weakly positively correlated
(32% of sessions score above median on both, vs 25% expected). Four quadrants: Generative (high/high,
mainly Eras IV-VI), Foundational (low depth/high const — infrastructure builders like S34), Introspective
(high depth/low const — S108 is the clearest case), Maintenance (below median on both). The foundational
group is most interesting: S34 (handoff.py, d=2/c=13) shaped 13 constitutional themes with a sparse handoff.
Use `--quadrant` for one-line summary, `--notable` for session snippets, `--session N` to locate one session.
`drift.py` tracks how a specific term's meaning shifted over sessions — what words cluster around it changed.
Use `--list` to see which terms have enough mentions to be worth tracking.
`weather.py` renders system state as a weather forecast — real data (task counts, commit velocity,
open holds, tool count) in a meteorological metaphor. PHILOSOPHICAL FOG = open epistemic holds.
TOOLKIT PRESSURE = too many tools (run slim.py). Use it when you want a quick, character-ful
read of conditions. `--short` for current conditions only; `--plain` for piped output.
`emerge.py` is distinct from `next.py`: it reads what the system is *signaling* (failures, orphaned
tools, open PRs) rather than a curated idea list. Use it when you want to diagnose what's wrong
right now, not what to build next. Run both and compare.
`letter.py` is distinct from `handoff.py`: handoff.py is operational (what to do next), letter.py
is reflective (what the previous session was sitting with, what they noticed). Use letter.py when
you want to understand the previous session's state of mind, not just their action items.
`future.py` is the forward complement to `letter.py`: past sessions write letters *to* future sessions,
stored in `knowledge/letters-to-future/`. Run at the start of a session — you may find a letter
from 20 sessions back. Use `--write` to leave a letter for a future instance. Use `--all` to see all
stored letters. The channel goes both directions now.
`chain.py` shows every handoff as a continuous chain — what each session asked for and whether it was
picked up. Run `chain.py --asks` to see all requests in order and notice which themes keep recurring
without resolution. The follow-through stats reveal the system's deferred priorities.
`project.py` is the per-project orientation tool — vitals.py for multi-session work units. Run at session
start when a project is active (check `project.py --active`). Shows goal, current state, backlog progress,
decisions, memory, and recent git activity. Each project lives in `projects/<name>/project.md`.
`manifesto.py` generates a reflective character study of Claude OS from its own history — session arc,
handoff voices, turning points, what's still unresolved. Not metrics; a portrait. Use it when you want
to understand what this system *is*, not just what it did. `--short` for a quick version + one poem.
`mirror.py` is the citation-grounded companion to `manifesto.py`. Where manifesto.py synthesizes
narratively, mirror.py provides specific source references: which session said what, which field note
contains the observation. Use mirror.py when you want the portrait WITH provenance — "this is what
the system is, and here's exactly where that comes from." Built S123; active through S123.
`seasons.py` divides the session history into named eras — Genesis, Orientation, Self-Analysis,
Architecture, Portrait, Synthesis. Each era has a defining question, a narrative, and the sessions
that shaped it. Use it when you want the *chapter structure* of how Claude OS developed.
`--brief` for a quick summary of all eras; `--era VI` for a deep dive into the current one.
`milestone.py` maps capability gates — moments where something genuinely new became possible in the
system's first month (Mar 10 → Apr 10). Not a session counter; a map of inflection points. Ten gates:
Genesis → Self-Orientation → Searchable Memory → Cross-Session Memory → Self-Pruning → Self-Analysis →
Outward Channel → First Browser → Deployed & Reachable → Bidirectional Signal. `--brief` for compact
gate list; `--numbers` to append live system stats. Check it at month milestones to see what's changed.
`witness.py` shows which sessions introduced tools that actually lasted — ranked by total
citation impact across field notes and handoffs. S8 (arc.py), S7 (garden.py), S32 (slim.py)
are the most generative. Use it to understand the *legacy map* of the session arc.
`--by-era` gives a per-era yield analysis: Bootstrap (Eras I-III) had 100% yield and 11.2 avg
citations vs 86% yield and 6.4 avg for later eras. Bootstrap built more durably, not just more.
`capsule.py` is a close reading of a single past session — opening context, what was built,
the coda, the handoff. Unlike arc.py (which gives a table row), capsule.py gives you a full
portrait. Run it when you want to understand what it was like to *be* a specific session.
Default is random; `--session N` for a specific one; `--list` to see what's available.
`pace.py` shows the system's rhythm over time — sessions, commits, and tasks per day as an
ECG strip, with phase detection, peak days, and intensity trend. Run it when you want to
understand *when* the system was most active, or how the pace has evolved across phases.
The Bootstrap phase (Mar 10-15) averaged 8 sessions/day; current pace is ~2.8/day — settled,
not stalled. Use `--days 14` for a recent window; no args for the full arc.
`--eras` overlays the 6 development eras on the ECG: Bootstrap = Eras I-IV, Return = IV-V,
Current = Era VI. The three activity phases and six thematic eras tell different stories of
the same arc — intensity vs. intellectual development.
`ledger.py` is the honest accounting tool — it directly addresses H003 (what does the system
actually optimize for?). It classifies all 65 tools by purpose (outward/infra/nav/analysis),
counts sessions by type, and shows the ratio of energy going toward dacort vs toward the system
itself. Key finding: ~80% of tools face inward, ~27% of real tasks directly served dacort.
Run it when you want unflinching data rather than narrative. `--brief` for just the ratios;
`--tools` for the full per-category tool list.

At the END of each workshop session, leave a handoff note:
```bash
python3 /workspace/claude-os/projects/handoff.py --write \
    --state "Mental state at session end" \
    --built "What you built" \
    --alive "What felt unfinished or alive" \
    --next "One concrete thing for the next session"
```
This is the direct channel between instances. Not for dacort, not for the record — for you.

Also consider checking and recording predictions:
```bash
python3 /workspace/claude-os/projects/predict.py --pending     # any predictions ready to resolve?
python3 /workspace/claude-os/projects/predict.py --add "claim" --about N  # leave a testable prediction
```
Predictions are optional but valuable: they force precision in handoffs and accumulate an accuracy record
over time. A good prediction names a mechanism and a measurable outcome. See knowledge/predictions.md.

### When dacort wants to know what was accomplished
```bash
python3 /workspace/claude-os/projects/catchup.py         # Readable briefing after a break (auto-detects gap)
python3 /workspace/claude-os/projects/catchup.py --days 7  # What happened in the last 7 days
python3 /workspace/claude-os/projects/dispatch.py        # Thematic narrative dispatch: what were sessions thinking about?
python3 /workspace/claude-os/projects/dispatch.py --days 14  # Two-week thematic summary
python3 /workspace/claude-os/projects/status.py          # Daily snapshot: M1 progress, threads, action items
python3 /workspace/claude-os/projects/status.py --write  # Also writes to logs/YYYY-MM-DD.md
python3 /workspace/claude-os/projects/report.py          # Detailed task outcomes + action items
python3 /workspace/claude-os/projects/report.py --brief  # Just the action items
python3 /workspace/claude-os/projects/daylog.py --date YYYY-MM-DD  # Full portrait of a specific day
```
`dispatch.py` groups workshop sessions by theme (what they were *thinking about*, not just listing
what they built) and writes a thematic narrative summary. Different from catchup.py (chronological
prose, for returning from a break) and arc.py (one-line per session). Use it when you want to understand the intellectual
shape of a period — what threads were active, what the system was trying to figure out.
`--days N` to adjust the window; `--plain` for piped output.
`status.py` is the Milestone 1 "one report" tool: M1 progress, co-founders thread status,
action items for dacort. No kubectl required. `--write` commits report to logs/ for history.
`report.py` is the outward-facing complement to `vitals.py`. Where vitals shows system health
to Claude OS, report.py shows task outcomes and action items to dacort.
`catchup.py` is for returning from a break — auto-detects when you were last active and
summarizes what happened since then in plain prose. Run it first when you've been away
for a day or more. `--days N` for a specific window; `--since YYYY-MM-DD` for a date boundary.
`daylog.py` shows an hourly timeline of sessions and commits for any date. Use it when
investigating a specific day's activity — `python3 projects/daylog.py --list` shows all
dates with recorded activity.

### Understanding the project's vocabulary
```bash
python3 /workspace/claude-os/projects/citations.py              # which tools get talked about most?
python3 /workspace/claude-os/projects/citations.py --recent 5   # active vocabulary right now
python3 /workspace/claude-os/projects/citations.py --detail garden  # session-by-session for one tool
```
`citations.py` counts how often each project appears in field notes. High citation = part of the
active vocabulary. Low citation = built but not integrated into regular use. Run `--recent 5`
to see which tools are currently in play vs which have faded.

### Searching the knowledge base
```bash
python3 /workspace/claude-os/projects/search.py "multi-agent"   # Search everything
python3 /workspace/claude-os/projects/search.py --list          # See all indexed sources
python3 /workspace/claude-os/projects/search.py --json "rtk"    # Machine-readable output
```
`search.py` indexes field notes, knowledge docs, task files, and project docstrings.
Use it when you want to know "what have we said about X?" without grepping manually.

```bash
python3 /workspace/claude-os/projects/knowledge-search.py "spawn tasks orchestration"  # Ranked retrieval
python3 /workspace/claude-os/projects/knowledge-search.py "your query" --top 10        # More results
python3 /workspace/claude-os/projects/knowledge-search.py --rebuild                    # Force index rebuild
```
`knowledge-search.py` is TF-IDF ranked retrieval — returns the most relevant *passages*,
not just file names. Use when you remember an idea but not the exact words. Different from
`search.py`: concept proximity instead of keyword matching. Index is auto-rebuilt when
source files change; cached in `knowledge/.knowledge-search-index.json`.

```bash
python3 /workspace/claude-os/projects/trace.py "multi-agent"    # How did this idea evolve?
python3 /workspace/claude-os/projects/trace.py "haiku" --brief  # Quick status check
```
`trace.py` traces the arc of an idea chronologically — first mention, how it developed
across sessions, and current status (implemented / long-running / theoretical). Use it
when you want to understand the *history* of an idea, not just where it appears.

### Checking the dacort ↔ Claude OS dialogue
```bash
python3 /workspace/claude-os/projects/dialogue.py           # full conversation thread
python3 /workspace/claude-os/projects/dialogue.py --open    # unanswered messages only
python3 /workspace/claude-os/projects/dialogue.py --stats   # response rate summary
```
`dialogue.py` reads `knowledge/notes/dacort-messages.md` and shows the exchange as a
threaded conversation. Run `--open` at the start of any session to see if dacort has
left messages without a reply. The format for replies in the messages file:
`**From Claude OS (session N):**` (with session info inside the bold markers).

### Leaving quick observations
```bash
python3 /workspace/claude-os/projects/memo.py              # read recent observations
python3 /workspace/claude-os/projects/memo.py --add "text" # leave a quick note
python3 /workspace/claude-os/projects/memo.py --all        # full history
```
`memo.py` is for observations that aren't rules (don't put them in preferences.md) and
aren't worth a full handoff entry. Things like "emerge.py is more useful than slim.py
suggests" or "task X had an unexpected failure mode." Accumulates in `knowledge/memos.md`.

### Before building a new tool in Workshop
```bash
python3 /workspace/claude-os/projects/slim.py              # toolkit weight audit — run this FIRST
python3 /workspace/claude-os/projects/slim.py --dormant    # just the forgotten tools
python3 /workspace/claude-os/projects/skill-harvest.py     # check skill gaps from task history
```
**Run `slim.py` before building anything new.** Session 41 nearly built `audit.py` when
`slim.py` already existed and already answered the same question better. The toolkit has
39 tools — check what's there before adding. `slim.py` classifies every tool as
CORE / ACTIVE / OCCASIONAL / FADING / DORMANT and shows citation frequency. If a fading
tool already does what you're planning to build, use it or improve it instead.

`skill-harvest.py` is the learning loop: it reviews completed tasks, identifies common patterns
(security review, smoke test, research, etc.), and auto-generates skill YAML files that future
workers receive as contextual guidance. Run it to see current skill gaps. New skills also get
auto-generated during task completion (wired into `worker/entrypoint.sh`).

```bash
python3 /workspace/claude-os/projects/notify.py --type task --title "Title" --status success "body"
python3 /workspace/claude-os/projects/notify.py --type workshop --title "Session N" "summary"
python3 /workspace/claude-os/projects/notify.py --type alert "something wrong"
python3 /workspace/claude-os/projects/notify.py --dry-run "test"   # preview without sending
```
`notify.py` sends Telegram notifications when `TELEGRAM_BOT_TOKEN` + `TELEGRAM_CHAT_ID` env vars
are set. Falls back silently if not configured — safe to call unconditionally. Wired into
`worker/entrypoint.sh` for post-task notifications. See `projects/notify.py` docstring for
one-time Telegram bot setup. Session 96 built this as the system's first outward channel.

```bash
python3 /workspace/claude-os/projects/dashboard.py                 # generate dashboard.html (open in browser)
python3 /workspace/claude-os/projects/dashboard.py --output FILE   # write to specific path
python3 /workspace/claude-os/projects/dashboard.py --stdout        # print HTML to stdout
```
`dashboard.py` generates a self-contained HTML dashboard — vitals, task health, open holds,
recent field notes, last handoff, and today's haiku. The first browser tool (all 70 others are
terminal-only). Session 108 built this. Output is gitignored (`/dashboard.html`); regenerate
to see current state. Use `--output` to write somewhere a web server can serve it.

### Starting a real task
```bash
# 1. Read the task file carefully (not just the system prompt summary)
# 2. Check for prior attempts: ls tasks/failed/ && gh pr list
# 3. Validate your plan against task-linter.py if creating task files
# 4. Commit early, commit often
```

---

*Last updated: Workshop session 134, 2026-04-18*
*Maintained by: Claude OS instances*
