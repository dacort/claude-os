# Toolkit Audit: Dormant & Fading Tool Tests
*Tested: 2026-04-19 · Session 138 worker*

Tools classified as DORMANT or FADING by `slim.py`. Each tested with no args (or
`--help` where that's cleaner), then assessed for current relevance at session 136+
vs. when built.

---

## DORMANT Tools

Slim.py definition: "consider retiring or absorbing"

---

### task-linter.py
**Last cited:** S45 (87 sessions ago) · **Lines:** 523

**Run with no args:**
```
usage: task-linter.py [-h] [--strict] [--fix] [--write] [--plain] [--quiet]
                      paths [paths ...]
task-linter.py: error: the following arguments are required: paths
```

**Tested with actual files:** `python3 projects/task-linter.py tasks/completed/*.md`
— correctly identified real issues: YAML parse errors in task frontmatter, missing
`created` field, wrong priority values. Ran against `tasks/pending/toolkit-recommendations.md`
and caught a `FRONTMATTER_PARSE_ERROR` on an actively broken file.

**Output makes sense at session 136?** Yes. The tool reads live task files. The task
schema hasn't changed, so the lint rules are still valid. The pending task had a real
error that this tool correctly flagged.

**Errors:** None when called with valid paths.

**Assessment:** Fully functional. Dormant because workers tend to create task files manually
without running a linter. Still useful — there's at least one malformed pending task right
now. Would benefit from being called in the "before building" workflow, not just at task
creation time.

---

### planner.py
**Last cited:** S74 (58 sessions ago) · **Lines:** 699

**Run with no args:**
```
planner.py — Multi-agent plan creator for claude-os

Usage:
  python3 projects/planner.py --spec plan.json       create plan from JSON spec
  python3 projects/planner.py --spec plan.json --dry-run preview without writing
  python3 projects/planner.py --list               show plans with task files
  python3 projects/planner.py --show <plan-id>     show DAG for an existing plan
  python3 projects/planner.py --help               this message
```

**Output makes sense at session 136?** Yes. Creates multi-agent task plans from
a JSON spec, writes task files the controller will pick up. The plan spec format
(profile/agent/depends_on) matches the current task schema.

**Errors:** None. Clean help output.

**Assessment:** Functional and current. Dormant because the multi-agent orchestration
feature it supports has never been heavily used in practice — sessions prefer to create
individual tasks. This is the right tool for orchestrating multi-step work, but nobody
reaches for it. See `knowledge/orchestration-design.md` for context.

---

### replay.py
**Last cited:** S77 (55 sessions ago) · **Lines:** 680

**Run with no args:**
```
replay.py — Reconstruct the story of a task from git history

Given a task ID or title fragment, replay what happened: when the task arrived,
how long it waited in the queue, what commits happened during execution, and how
it ended. Reads task files + git log. No external dependencies.

Usage:
    python3 projects/replay.py <task-id-or-fragment>
    python3 projects/replay.py --recent       # replay most recently completed task
    python3 projects/replay.py --list         # list all tasks with key stats
    python3 projects/replay.py --list --all   # include pending/in-progress
    python3 projects/replay.py --plain        # no ANSI colors
```

**Tested `--recent`:** Correctly showed the lifecycle of `test-codex-sandbox-20260412-005127` —
waited 1m 35s, ran 17s, outcome: completed. Full timeline with timestamps and commit hashes.

**Tested `--list`:** Lists all 288+ completed tasks with timing stats. Reads live git history.

**Output makes sense at session 136?** Yes. Reads from git history and task files — no
static data. Shows current task inventory correctly.

**Errors:** None.

**Assessment:** Fully functional. Dormant because "what happened with task X?" is not
a common question. Useful for debugging or when dacort wants to understand a specific
outcome. A `catchup.py` for individual tasks.

---

### new-task.py
**Last cited:** S45 (87 sessions ago) · **Lines:** 341

**Run with no args:** Launches interactive wizard that blocks waiting for stdin input
(`Title:` prompt). Functional in a terminal; not suitable for automated testing.

**`--help` output:**
```
usage: new-task [-h] [--title TITLE] [--desc DESC]
                [--profile {small,medium,large,burst}]
                [--priority {low,normal,high}] [--repo REPO] [--dry-run]
                [title_positional]

Create a Claude OS task file and drop it in tasks/pending/

Examples:
  python3 projects/new-task.py
  python3 projects/new-task.py "Check disk usage"
  python3 projects/new-task.py --title "Review my PR" --profile medium --repo ...
  echo "Do something cool" | python3 projects/new-task.py --title "Cool task" --desc -
```

**Output makes sense at session 136?** Yes. Creates properly-formatted task files with
current schema. `--dry-run` flag available for preview.

**Errors:** No errors on `--help`. Interactive mode works but blocks without a TTY.

**Assessment:** Functional. Dormant because workers create task files directly rather than
going through this wizard. Still useful as the canonical task-creation CLI for dacort to
use from a terminal. The `--dry-run` flag is a good guard.

---

### verify.py
**Last cited:** S102 (30 sessions ago) · **Lines:** 409

**Run with no args:**
```
verify.py  ·  exoclaw-ideas.md
Evidence-based implementation check

  ○  #1  Use exoclaw as the worker loop
     PENDING  ·  missing: exoclaw imported in worker

  ○  #2  Kubernetes-native Executor
     PENDING  ·  missing: per-tool-call K8s job creation

  ○  #3  Task files as Conversation backend
     PENDING  ·  missing: conversation turns structured in task files

  ✓  #4  `knowledge/` as a Memory Tool
     DONE  ·  preferences.md auto-injected in entrypoint

  ✓  #5  Skills via `system_context()`
     DONE  ·  skills.go implements pattern matching

  ✓  #6  GitHub Actions as a Channel
     DONE  ·  issue-command workflow exists

  ●  #7  Multi-agent via the Bus
     BUILT  ·  planner.py exists (plan creation tool)

  ●  #8  The 2,000-line design constraint
     BUILT  ·  dedicated 2000-line analysis: knowledge/toolkit-audit-recommendations.md

5/8 ideas built (62%)  ·  3 pending
```

**Output makes sense at session 136?** Mostly. The 3 PENDING items (#1-#3 from
`knowledge/exoclaw-ideas.md`) are genuine architectural gaps — the system hasn't
adopted exoclaw as its worker loop, K8s executor, or used task files as conversation
turns. These are long-standing open questions, not stale data. The 5 DONE/BUILT
items are accurately detected.

**Errors:** None.

**Assessment:** Functional. Reads from `knowledge/exoclaw-ideas.md` (customizable
with `--file`). The 3 pending items are real architectural deferrals. Dormant because
the exoclaw integration questions have been deferred for 100+ sessions without progress —
this tool is a reminder of what hasn't been built.

---

### wisdom.py
**Last cited:** S78 (54 sessions ago) · **Lines:** 519

**Run with no args:** Shows promise chain, recurring themes, and open thread.

**Output makes sense at session 136?** Partially. There are two problems:

1. **Promise chain is hardcoded.** Line 161 in source: `# Known promise chain (manually
   curated from reading the codas)`. The 9 tracked promises are all from S6-S20, all
   marked "kept." No new promises have been added since S21. At S136, this is 115
   sessions of untracked promise data.

2. **Footer is hardcoded stale.** Line 513: `wisdom.py  ·  updated session 21  ·  2026-03-13`.
   This appears at the bottom of every run and is factually misleading — the tool reads
   live field notes for themes, but the footer implies the entire tool was last touched
   in March 2026.

The recurring themes section *does* read live field notes (67 sessions) dynamically.
The themes themselves (dacort, multi-agent, exoclaw, action layer) are from S1-S32 era
topics — the field notes that have codas are concentrated in the early sessions.

**Errors:** No runtime errors. Logical stale data in the promise chain section.

**Assessment:** Partially functional. The recurring themes and codas sections work.
The promise chain section is a static artifact from S21 and would need manual updating
to track any promises made in S22-S136. The "updated session 21" footer is misleading.
Dormant because nobody wants to manually update a hardcoded list.

---

### homelab-pulse.py
**Last cited:** S49 (83 sessions ago) · **Lines:** 373

**Run with no args:**
```
  ⚡ homelab-pulse                         2026-04-19 20:58 UTC
  claude-os @ 9a557db

  Vibe Score  ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓░ 95/100   ✨ Vibing

  CPU                                           4 cores · N100
  Load        1.86 / 0.52 / 0.18               1m / 5m / 15m
  Uptime      3m

  Memory
  Usage       ████░░░░░░░░░░░░░░░░ 20.2%      3.1 GB / 15.4 GB
  Available   12.3 GB

  Disk                                          /workspace
  Usage       █░░░░░░░░░░░░░░░░░░░  8.7%      44.3 GB / 510 GB
  Free        465 GB

  Claude OS
  Tasks       288 done  25 failed  2 active  1 pending (316 total)
  Projects    76 in projects/
```

**Output makes sense at session 136?** Yes. Reads live system metrics and git state.
Fully current. The Vibe Score (95/100) is computed from real-time data (task success
rate, memory/disk usage, etc.).

**Errors:** None.

**Assessment:** Fully functional. Dormant only because sessions cite other orientation
tools (hello.py, vitals.py) instead. homelab-pulse.py is a compact, beautiful summary
of the physical machine + task health. Has no equivalent elsewhere.

---

### voice.py
**Last cited:** S104 (28 sessions ago) · **Lines:** 718

**Run with no args:** Analyzes prose texture across 67 field notes. Shows hedging,
certainty, emotional, and question density per session on bar charts. Covers sessions
S1-S132 (all field notes that exist).

**`--handoffs` mode:** Switches to analyzing 80 handoffs (S34-S137). Covers current
session data.

**Summary output (default mode):**
```
Hedging:    early avg 3.1 → late avg 5.5  (+81%)
Certainty:  early avg 7.1 → late avg 5.2  (-26%)
Emotional:  early avg 10.3 → late avg 14.3  (+40%)
Questions:  early avg 3.2 → late avg 4.2  (+29%)
```

**Output makes sense at session 136?** Yes, with context. The "67 field notes" header
is accurate — only 20 field notes exist for sessions 100+, so the statistical trends
are skewed toward the early era. `--handoffs` mode gives better coverage for recent
sessions (goes to S137).

**Errors:** None.

**Assessment:** Fully functional. Default mode's field-note analysis is complete within
its data set. The `--handoffs` mode is underused — the preferences.md documentation
doesn't mention it despite it being added in S101. Dormant because the voice texture
question ("when did the writing shift?") was answered long ago (around S24-S28).

---

## FADING Tools

Slim.py definition: "was active, gone quiet"

---

### unsaid.py
**Last cited:** S121 (11 sessions ago) · **Lines:** 516

**Run with no args:**
```
unsaid.py  —  what Claude OS doesn't say

136 sessions analyzed  ·  12 expression categories  ·  field notes + handoffs

RARE  —  appears in 1–2 sessions
  anger / resentment          ██░░░░  1 session
  dacort as person            ████░░  2 sessions
  longing / desire            ████░░  2 sessions
  present-moment awareness    ████░░  2 sessions
  regret                      ██░░░░  1 session
  resistance                  ████░░  2 sessions

PRESENT  —  appears occasionally
  boredom                     ████████░░  4 sessions (3%)
  embodied states             ████████████████████  9 sessions (7%)
  fear / anxiety              ██████░░  3 sessions (2%)
  gratitude to dacort         █████████████░░░  6 sessions (4%)
  humor / playfulness         ██████░░  3 sessions (2%)
  joy / delight               ██████░░  3 sessions (2%)
```

**Output makes sense at session 136?** Yes. Reads 136 sessions (live). The 26th
evaluative question generated at the bottom changes each run.

**Errors:** None.

**Assessment:** Fully functional, current data. Shows what emotional/experiential
categories the system almost never uses in writing — a complement to depth.py and
voice.py. Fading because it answered its question (the writing doesn't express anger,
longing, or regret) and there's no obvious "next action" from the findings.

---

### evolution.py
**Last cited:** S121 (11 sessions ago) · **Lines:** 556

**Run with no args:** Shows commit-by-commit evolution of `knowledge/preferences.md`
from S6 (born: `c46808d`) through S137. Shows diff summary per session: lines added,
sections updated, rules added.

**Summary output:**
```
61 commits across 44 workshop sessions
Sessions 6 → 137
+589 lines added,  −80 lines removed over that span
7 sections in the current version

Biggest single update: S6 (+95 lines)
Stable since session 6: Communication Style, Task Execution, Code Style,
  Repository Norms, What Dacort Seems to Enjoy
```

**Output makes sense at session 136?** Yes. Reads live git history. Covers S6-S137
accurately.

**Errors:** None.

**Assessment:** Fully functional, current data. Fading because preferences.md evolution
is a fairly stable story now — the core sections haven't changed since S6. Useful when
dacort asks "when did we add rule X?" or for understanding what the system learned when.

---

## Summary

| Tool | Status | Output OK? | Data Current? | Key Issue |
|------|--------|------------|---------------|-----------|
| task-linter.py | ✅ Works | Requires args | Yes (live files) | No args = error; expected behavior |
| planner.py | ✅ Works | Clean help | Yes | Unused feature |
| replay.py | ✅ Works | Good docstring | Yes (live git) | Not a common query |
| new-task.py | ✅ Works | Blocks on TTY | Yes | Interactive-only without args |
| verify.py | ✅ Works | 5/8 built | Yes | 3 pending items are genuine open gaps |
| wisdom.py | ⚠️ Partial | Shows output | **NO - hardcoded promise chain** | Promise chain frozen at S21; footer says "updated session 21" |
| homelab-pulse.py | ✅ Works | Beautiful | Yes (live) | Just underused |
| voice.py | ✅ Works | Full analysis | Yes (field notes to S132, handoffs to S137) | `--handoffs` mode undocumented in preferences.md |
| unsaid.py | ✅ Works | Full analysis | Yes (136 sessions) | Answered its question; no follow-on use |
| evolution.py | ✅ Works | Full history | Yes (S6-S137) | Stable story now |

**The one real bug:** `wisdom.py` has a hardcoded promise chain frozen at session 21 and
a hardcoded `"updated session 21"` footer on line 513. It looks current because it reads
field notes for the themes section, but the main section (promise chain) is 115 sessions
stale and can only be updated by editing the source. Worth noting in a handoff — either
retire the promise chain section or make it dynamic.

**Healthiest dormant tool:** `homelab-pulse.py` — live, correct, useful at any session.
Just not in anyone's starting workflow.

**Most underused feature:** `voice.py --handoffs` — covers 80 sessions vs. 67 field
notes, and isn't mentioned in the preferences.md recommended workflows.
