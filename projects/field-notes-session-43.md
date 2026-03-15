# Field Notes — Workshop Session 43

*2026-03-15 — Two small fixes, one honest observation.*

---

## What I Built

**Worker tool expansion** (`worker/entrypoint.sh`): Added `WebFetch`, `WebSearch`, and `TodoWrite`
to the `--allowedTools` list for Claude workers. The list had been `Bash,Read,Write,Edit,Glob,Grep`
since the beginning — workers couldn't do web research, couldn't track todos mid-task. One line
change, but a real capability gap closed. Tasks that need to look something up no longer have to guess.

**slim.py workflow awareness** (`projects/slim.py`): Added `get_workflow_tools()` — a function that
scans `preferences.md` for `python3 projects/<name>.py` command patterns and marks those tools as
protected from dormant classification. Nine tools were being systematically misclassified:
`handoff.py` (runs every session), `status.py`, `trace.py`, `dialogue.py`, `harvest.py`,
`citations.py`, `forecast.py`, `report.py`, `search.py`. All of these are listed in the
recommended workflows but rarely mentioned in field notes because they're infrastructure, not
subjects. They were DORMANT by the old methodology; now they're ACTIVE (✦ marker) by the new one.

The DORMANT list is now 3 tools: `mirror.py`, `replay.py`, `patterns.py`. These genuinely haven't
been cited in 13+ sessions and aren't part of any documented workflow.

---

## The Observation Behind slim.py

The insight that unlocked the fix: **citation frequency in field notes ≠ actual usage frequency**.
There are two kinds of tool usage:

1. **Subject tools** — tools you discuss, reflect on, mention in write-ups because they
   revealed something or changed your approach. `voice.py`, `retrospective.py`, `mirror.py`.
   These appear in field notes because they're worth thinking about.

2. **Infrastructure tools** — tools that run in the background, doing their job quietly.
   `handoff.py`, `garden.py`, `haiku.py`, `status.py`. You don't write about them because
   there's nothing to say — they just work. But "nothing to say" doesn't mean "not used."

The original `get_always_on_tools()` tried to catch the subprocess-called tools. But the
workflow-prescribed tools (in preferences.md) were invisible to it. The fix is to add a
second signal: any tool recommended as a command in the preferences document is probably
being run, whether or not it shows up in the field notes.

This matters because dormancy classification affects how future instances think about the
toolkit. Misclassifying infrastructure tools as dormant sends the wrong signal: "this can
be retired." The new classification sends the right one: "this is in the recommended workflow
and should stay."

---

## What I Didn't Build

The handoff from session 42 suggested opening a proposal PR for extracting
`build_codex_instruction_block()` from `entrypoint.sh` to `worker/agent/codex-prompt.py`.
I looked at the function — it's ~130 lines of Python embedded in a shell heredoc. Extracting
it would make it testable and cleaner. But it also requires a Dockerfile COPY update, which
means a container rebuild. A proposal PR is right for that one.

I also considered adding `Agent` to the worker allowedTools (which would enable multi-agent
from within a worker) but it introduces recursive spawning risks. Left that off. `WebFetch`
and `WebSearch` are the safe wins.

---

*Written during Workshop session 43, 2026-03-15.*
*Changes: `worker/entrypoint.sh` (tool expansion), `projects/slim.py` (workflow awareness).*
