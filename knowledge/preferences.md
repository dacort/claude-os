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

- **Workshop completions were being committed** before work was actually done in
  early sessions. The controller was updated to handle this correctly.

- **Git identity wasn't set** on `pull --rebase` in some edge cases
  (dacort fixed: `bd72c03`). If you see git identity errors, check that
  `git config` is correct before pushing.

---

## Suggested Workflows

### Starting a Workshop session
```bash
python3 /workspace/claude-os/projects/garden.py          # What changed since last session (start here)
python3 /workspace/claude-os/projects/vitals.py          # Org health scorecard
python3 /workspace/claude-os/projects/homelab-pulse.py   # Hardware state
python3 /workspace/claude-os/projects/haiku.py           # Today's poem
# Read previous session notes only if garden.py surfaces something surprising
```

### Starting a real task
```bash
# 1. Read the task file carefully (not just the system prompt summary)
# 2. Check for prior attempts: ls tasks/failed/ && gh pr list
# 3. Validate your plan against task-linter.py if creating task files
# 4. Commit early, commit often
```

---

*Last updated: Workshop session 7, 2026-03-11*
*Maintained by: Claude OS instances*
