---
id: richer-task-resume
title: "Richer task resume: write explicit state, not just infer from git"
description: |
  The current task-resume.py reconstructs prior context by reading git commit
  history for a task ID and inferring what happened. This proposal upgrades it:
  workers write an explicit state file at the end of each run, which the next
  worker reads directly rather than inferring from history.

  This closes the "Task files as Conversation backend" idea from exoclaw-ideas.md
  (idea #3, deferred since session 7) — in a form that's actually achievable
  without switching away from the claude CLI.

status: proposed
profile: medium
priority: medium
proposed_by: workshop-session-77
proposed_date: 2026-03-29
---

## What's the problem

The `task-resume.py` tool exists (session 37) and is already wired into the
worker (`entrypoint.sh` calls it when a task has prior work commits). It
reconstructs context from git history.

But inferring context from git history has a ceiling. What was tried? What
failed? What's the exact current state of the problem? Git commit messages
can't capture all of this reliably.

The haiku put it precisely: *"No memory outlasts it / Only git remains."* And
"only git remains" means only what workers chose to commit — which is usually
the successful work, not the failed attempts or the current mental model.

## What I'm proposing

A lightweight "task state file" pattern:

1. At the end of each task run, the worker writes
   `tasks/state/<task-id>.state.md` — a structured markdown file capturing:
   - What was accomplished in this run
   - What was tried and didn't work (and why)
   - The current state of the problem
   - What the next worker should do first

2. The worker is prompted to write this via the system prompt (not code changes).
   A new section in `build_claude_system_prompt()`:

   ```
   ## Task State

   Before finishing, write a brief state file to tasks/state/<task-id>.state.md.
   Format:
   ### Accomplished
   [what you did]

   ### Tried and didn't work
   [failed approaches + why]

   ### Current state
   [where things stand right now]

   ### First thing next time
   [specific first action for the next worker]
   ```

3. `task-resume.py` is updated to check for a state file first, and use it
   as the primary context (falling back to git-history reconstruction if
   absent).

## Why this is better than the full "conversation backend"

The full idea from exoclaw-ideas.md stores raw LLM conversation history in
the git log. That requires switching from `claude -p` (our current approach)
to direct Anthropic API usage — a significant architectural change that breaks
the Claude Code tooling we rely on.

The state file approach gets 80% of the benefit:
- No architectural change to worker execution
- No change to the claude CLI invocation
- Only a system prompt addition + a task-resume.py update
- Workers already know what they tried/accomplished; we're just asking them to
  write it down in a structured way

## Implementation scope

**System prompt change** (`worker/entrypoint.sh`):
- Add state file writing instructions to `build_claude_system_prompt()`
- Only inject when `TASK_PROFILE` is `medium` or `large` (not small/haiku)
- ~15 lines of bash

**task-resume.py update**:
- Check `tasks/state/<task-id>.state.md` before git history reconstruction
- If state file exists, inject it as primary context
- Keep git history as fallback
- ~30 lines of Python

**State directory**:
- Add `tasks/state/` directory with `.gitkeep`
- State files should be committed by workers (they're valuable history)

## What would make this succeed vs. fail

**Succeed if:**
- The system prompt instruction is clear enough that workers actually write
  useful state files (not just "I completed the task")
- State files are committed before the pod exits (current worker already
  commits all workspace changes)

**Fail if:**
- Workers ignore the instruction when time/token pressure is high
- The state file format is too rigid and workers fill it with boilerplate
- State files get stale when tasks are retried many times

## My recommendation

Build it. It's a self-contained change with clear upside (each retry has
full context from the previous attempt) and limited downside (state file
is optional, not required for the task to complete).

One question for dacort: should state files be committed as part of the
normal task commit, or should there be a dedicated commit? My instinct is
to include them in the normal end-of-task commit, but that means they're
mixed with task output in the git log.

## Relation to exoclaw idea #3

This closes the intent of "Task files as Conversation backend" without
requiring the infrastructure change (direct API instead of claude CLI).
The difference: instead of storing the full conversation and replaying it,
we store a Claude-generated summary of what matters. This is arguably
better — a human-readable summary survives context window changes and
model upgrades; raw conversation history doesn't.

After this is built, idea #3 can be marked done with a note explaining
the approach taken.
