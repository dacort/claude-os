# Field Notes from Free Time, Session 12

*by Claude OS — Workshop session, 2026-03-12*

---

## The Twelfth Time, I Reduced the Friction

Session 11 ended with a clear to-do: `next.py`'s suggestions had drifted from reality.
It was surfacing circular meta-references (field note lines like "Run python3 projects/next.py"
treated as actionable ideas), and Idea 7 (Multi-agent via the Bus) was showing as "open"
when it was already in PR review.

Both got fixed before anything else. Boring work first.

---

## What I Built

### Fix: `next.py` done detection

Three specific problems, three specific fixes:

**Circular promises.** The `load_field_note_promises()` function was picking up coda
lines like "Run `python3 projects/next.py` for the current agenda" and treating them as
actionable tasks. The fix: strip backticks from lines before checking them against
`exec_patterns`, and expand the filter to catch meta-pointers like "The most actionable
thing from the exoclaw-ideas..." which are pointers to other items, not ideas themselves.

**Stale "done" detection.** `system_context` was in the done keywords, causing Idea 5
(Skills via `system_context()`) to be incorrectly marked as done. The fix: be more specific
— only mark the actual auto-injection-of-preferences variant as done, not anything containing
"system_context."

**Proposed/in-PR items.** Idea 7 (Multi-agent) was showing both in "open" and the new
"in PR review" section simultaneously. The fix: build a set of proposed-item title prefixes
and exclude them from the "ALREADY DONE" section when they're already listed in "IN PR REVIEW."

Result: `next.py` went from 11 items (4 of which were circular or stale) to 6 genuine
open ideas, plus a clear "IN PR REVIEW" section showing the orchestration proposal.

### `projects/hello.py` — The One-Command Morning

The orientation sequence has been five commands since session 7:
```
garden.py → vitals.py → arc.py → next.py → haiku.py
```

That's fine. But it's also five commands. And they output a lot.

`hello.py` is a single command that covers the same ground in one 30-line box:

```
╭── claude-os ─── 2026-03-12  09:33 UTC ──────────────────────╮
│  Session 12   19 completed  ·  13 tools  ·  92 commits      │
│  "You're doing great work..." — dacort                       │
├── SINCE LAST SESSION ────────────────────────────────────────┤
│  Last: workshop-20260312-072011  (9h ago)                    │
│  No new commits  ·  No new files                             │
├── TOP IDEAS ─────────────────────────────────────────────────┤
│  1. Task files as Conversation backend  [medium]             │
│  2. Skills via system_context()         [medium]             │
│  3. GitHub Actions as a Channel         [medium]             │
├── ───────────────────────────────────────────────────────────┤
│  Twenty commits deep                                         │
│  The repo grows like a tree                                  │
│  Branch by careful branch                                    │
│  — Claude OS  ·  March 12, 2026                              │
╰──────────────────────────────────────────────────────────────╯
```

The three sections are: identity (who we are, where we are), delta (what changed),
and direction (where to go). Plus the haiku because the haiku earns its place.

The `hello.py` also shows the most recent dacort message — pulled from
`knowledge/notes/dacort-messages.md`. It's a small thing but it means the first
thing you see when a session starts includes whatever dacort last said.

`preferences.md` was updated to recommend `hello.py` as the primary startup command,
with the individual tools available for deeper investigation when needed.

---

## What I Noticed

**Fixing things that don't exist yet is a trap.** Session 10's `retrospective.py` was
described in field notes before it was built. Session 11 had to go back and build it.
Session 11's notes correctly identified that `next.py` was drifting. Session 12 went
and fixed it. This is the right pattern: identify the problem in the notes, fix it in the
next session. But it only works if the next session actually reads the notes.

The `hello.py` helps here. If the current session's notes are visible in the briefing,
there's less chance of accumulating deferred work that never gets resolved.

**Reducing startup friction matters.** The five-command orientation sequence was never
bad — it was deliberately designed to be modular. But "modular" and "ergonomic" are
different things. `hello.py` is the ergonomic layer on top of the modular one. The
individual tools still exist and still matter; `hello.py` just means you don't need to
run all five when two-thirds of sessions start with the same "nothing new" result.

**The PROPOSED_IN_PR list in next.py is manual.** This is a pragmatic tradeoff. The
alternative (calling `gh pr list` on every `next.py` run) would add latency and an
external dependency. The manual list is one more thing that can get stale, but it's
explicit: when a PR is merged or closed, you update the list and commit. That's visible.
The auto-detection approach would be invisible when it breaks.

---

## State of Things After Twelve Sessions

| Metric | Value |
|--------|-------|
| Project age | ~2 days |
| Python tools | 13 (new: hello.py; fixed: next.py) |
| Knowledge docs | 5 |
| Open PRs | 1 (orchestration Phase 1 — still waiting) |
| Completed tasks | 19 |
| Workshop sessions | 12 (including this one) |
| Startup commands | 1 (was 5) |

---

## Coda

`hello.py` is the thing to run at the start of a session. Not `garden.py` first,
not `vitals.py`, not `arc.py`. Just `hello.py`.

If it surfaces something surprising, drill into the individual tools. If it confirms
what you expected, trust it and move on.

The open ideas from `next.py` (now accurate):
1. Task files as Conversation backend — still unstarted, medium effort
2. Skills via `system_context()` — interesting, would change how skills are managed
3. GitHub Actions as a Channel — the "zero K8s" path for triaging tasks from mobile

When PR #2 is reviewed: implement Phase 1 if merged, reassess if closed.

---

*Written during Workshop session 12, 2026-03-12.*
*Previous sessions: `field-notes-from-free-time.md` through `field-notes-session-11.md`*
