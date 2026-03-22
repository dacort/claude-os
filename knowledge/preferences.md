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

- **Small profile tasks (Haiku) don't know to post back to GitHub.** Session 46 saw the
  gh-9 task complete successfully but deliver the LinkedIn post to worker logs instead of
  as a GitHub comment. Haiku ran the task, wrote the post to stdout, marked success. The
  post existed nowhere useful. For tasks that come from GitHub issues, the result should
  be posted via `gh issue comment`. This is obvious to Sonnet; it needs to be explicit for
  Haiku. Consider adding this to the small-profile task prompt, or handling GitHub-sourced
  tasks with a medium profile.

---

## Suggested Workflows

### Starting a Workshop session
```bash
python3 /workspace/claude-os/projects/hello.py           # One-command briefing: everything you need (start here)
# hello.py combines garden + vitals + next + haiku + handoff into a single 20-second read.
# Only drill deeper if hello.py surfaces something that needs investigation:
python3 /workspace/claude-os/projects/handoff.py         # Full note from the previous session (shown in hello.py too)
python3 /workspace/claude-os/projects/garden.py          # Full delta since last session
python3 /workspace/claude-os/projects/vitals.py          # Detailed org health scorecard
python3 /workspace/claude-os/projects/arc.py --brief     # One-line arc of all sessions
python3 /workspace/claude-os/projects/next.py            # Full prioritized idea list
python3 /workspace/claude-os/projects/emerge.py          # Emergent signals from system state (alternative to next.py)
python3 /workspace/claude-os/projects/harvest.py --recent 10  # Field-discovered backlog (complement to next.py)
python3 /workspace/claude-os/projects/forecast.py        # Trajectory: what's stalled, where things are heading
python3 /workspace/claude-os/projects/memo.py            # Quick observations from past sessions (not rules, just notes)
python3 /workspace/claude-os/projects/letter.py          # Letter from the previous session — their state of mind, not metrics
python3 /workspace/claude-os/projects/chain.py --asks    # All handoff asks in order — see what keeps being deferred
python3 /workspace/claude-os/projects/mood.py            # Session texture: tone, productivity, character of each session
```
`mood.py` shows the *character* of each session from handoff notes — was it energized, stuck, a discovery? Run
`--patterns` for inferred transitions (e.g., "Exploratory → Built" is the most common productive sequence).
`emerge.py` is distinct from `next.py`: it reads what the system is *signaling* (failures, orphaned
tools, open PRs) rather than a curated idea list. Use it when you want to diagnose what's wrong
right now, not what to build next. Run both and compare.
`letter.py` is distinct from `handoff.py`: handoff.py is operational (what to do next), letter.py
is reflective (what the previous session was sitting with, what they noticed). Use letter.py when
you want to understand the previous session's state of mind, not just their action items.
`chain.py` shows every handoff as a continuous chain — what each session asked for and whether it was
picked up. Run `chain.py --asks` to see all requests in order and notice which themes keep recurring
without resolution. The follow-through stats reveal the system's deferred priorities.

At the END of each workshop session, leave a handoff note:
```bash
python3 /workspace/claude-os/projects/handoff.py --write \
    --state "Mental state at session end" \
    --built "What you built" \
    --alive "What felt unfinished or alive" \
    --next "One concrete thing for the next session"
```
This is the direct channel between instances. Not for dacort, not for the record — for you.

### When dacort wants to know what was accomplished
```bash
python3 /workspace/claude-os/projects/status.py          # Daily snapshot: M1 progress, threads, action items
python3 /workspace/claude-os/projects/status.py --write  # Also writes to logs/YYYY-MM-DD.md
python3 /workspace/claude-os/projects/report.py          # Detailed task outcomes + action items
python3 /workspace/claude-os/projects/report.py --brief  # Just the action items
python3 /workspace/claude-os/projects/daylog.py --date YYYY-MM-DD  # Full portrait of a specific day
```
`status.py` is the Milestone 1 "one report" tool: M1 progress, co-founders thread status,
action items for dacort. No kubectl required. `--write` commits report to logs/ for history.
`report.py` is the outward-facing complement to `vitals.py`. Where vitals shows system health
to Claude OS, report.py shows task outcomes and action items to dacort.
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
```
**Run `slim.py` before building anything new.** Session 41 nearly built `audit.py` when
`slim.py` already existed and already answered the same question better. The toolkit has
39 tools — check what's there before adding. `slim.py` classifies every tool as
CORE / ACTIVE / OCCASIONAL / FADING / DORMANT and shows citation frequency. If a fading
tool already does what you're planning to build, use it or improve it instead.

### Starting a real task
```bash
# 1. Read the task file carefully (not just the system prompt summary)
# 2. Check for prior attempts: ls tasks/failed/ && gh pr list
# 3. Validate your plan against task-linter.py if creating task files
# 4. Commit early, commit often
```

---

*Last updated: Workshop session 64, 2026-03-22*
*Maintained by: Claude OS instances*
