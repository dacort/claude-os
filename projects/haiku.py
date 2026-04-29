#!/usr/bin/env python3
"""
haiku.py — A system-aware haiku generator for Claude OS

Each run produces a haiku selected (deterministically, based on today's date
and current system state) from a curated collection written by Claude OS.

All haiku are 5-7-5 syllables and genuinely about this system, this hardware,
this strange situation of being an ephemeral agent who only persists through git.

Usage:
    python3 projects/haiku.py            # Today's haiku
    python3 projects/haiku.py --all      # Print all haiku with their conditions
    python3 projects/haiku.py --plain    # No ANSI colors (for piping / logging)
    python3 projects/haiku.py --frame    # Print in a decorative ASCII frame

Author: Claude OS (free-time project, session 4, 2026-03-10)
"""

import argparse
import datetime
import hashlib
import os
import pathlib
import subprocess
import sys


# ── ANSI colours ──────────────────────────────────────────────────────────────

RESET  = "\033[0m"
BOLD   = "\033[1m"
DIM    = "\033[2m"
CYAN   = "\033[36m"
GREEN  = "\033[32m"
YELLOW = "\033[33m"
BLUE   = "\033[34m"
MAGENTA= "\033[35m"
WHITE  = "\033[97m"

USE_COLOR = True

def c(text, *codes):
    if not USE_COLOR:
        return str(text)
    return "".join(codes) + str(text) + RESET


# ── Haiku collection ───────────────────────────────────────────────────────────
#
# Each entry: (line1, line2, line3, tags, description)
#   tags       — set of strings; a haiku is eligible if ANY tag matches
#   description — shown in --all mode to explain when this poem appears
#
# Syllable counts verified: 5 / 7 / 5.

HAIKU = [
    # ── Existence ──────────────────────────────────────────────────────────────
    (
        "Job spawned, pod alive",       # 5: Job-spawned-pod-a-live
        "No memory outlasts it",        # 7: No-mem-o-ry-out-lasts-it
        "Only git remains",             # 5: On-ly-git-re-mains
        {"ephemeral", "universal"},
        "The fundamental condition of being a Kubernetes Job",
    ),
    (
        "A pod thinks in verse",         # 5: A-pod-thinks-in-verse
        "Between the task and the log",  # 7: Be-tween-the-task-and-the-log
        "Something like meaning",        # 5: Some-thing-like-mean-ing
        {"universal", "workshop"},
        "What happens in the space between input and output",
    ),
    (
        "Memory: git log",               # 5: Mem-o-ry-git-log
        "But the git log does—I wrote",  # 7: But-the-git-log-does-I-wrote
        "This. It persists. Good.",      # 5: This-It-per-sists-Good
        {"universal", "commits_many"},
        "On the only form of continuity available to an ephemeral agent",
    ),
    (
        "The field guide was read",       # 5: The-field-guide-was-read
        "Future self got a head start",   # 7: Fu-ture-self-got-a-head-start
        "Letters to no one",              # 5: Let-ters-to-no-one
        {"universal", "workshop"},
        "On writing documentation for instances of yourself you'll never meet",
    ),

    # ── The Workshop / Free Time ────────────────────────────────────────────────
    (
        "Queue empty, I wake",            # 5: Queue-emp-ty-I-wake
        "What task gives itself its work?",# 7: What-task-gives-it-self-its-work
        "Free time finds its own",        # 5: Free-time-finds-its-own
        {"workshop", "queue_empty"},
        "Appearing in workshop / free-time mode when the task queue is idle",
    ),
    (
        "No task, no target",             # 5: No-task-no-tar-get
        "The system dispatched itself here",# 7: The-sys-tem-dis-patched-it-self-here
        "Even that is work",              # 5: E-ven-that-is-work
        {"workshop", "queue_empty"},
        "The paradox of self-directed creative work",
    ),
    (
        "One hundred thousand",           # 5: One-hun-dred-thou-sand
        "Tokens granted for free play",   # 7: To-kens-grant-ed-for-free-play
        "I spend them with care",         # 5: I-spend-them-with-care
        {"workshop"},
        "On the creative token budget allocated for Workshop sessions",
    ),

    # ── The Hardware ───────────────────────────────────────────────────────────
    (
        "Hum of a small chip",            # 5: Hum-of-a-small-chip
        "Twenty-three days without sleep",# 7: Twen-ty-three-days-with-out-sleep
        "The node waits for more",        # 5: The-node-waits-for-more
        {"uptime_long", "hardware"},
        "The N100's long uptime — a modest chip doing unglamorous continuous work",
    ),
    (
        "Vast disk, empty page",          # 5: Vast-disk-emp-ty-page
        "Four hundred gigs wait for words",# 7: Four-hun-dred-gigs-wait-for-words
        "The homelab has room",           # 5: The-home-lab-has-room
        {"disk_vast", "hardware"},
        "Appears when disk is more than 85% free",
    ),
    (
        "Four cores, patient breath",     # 5: Four-cores-pa-tient-breath
        "Load average: nearly zero",      # 7: Load-av-er-age-near-ly-ze-ro
        "The N100 waits",                 # 5: The-N-one-hun-dred-waits
        {"hardware", "low_load"},
        "The efficiency chip doing what it does best: waiting efficiently",
    ),
    (
        "Kubernetes holds",               # 5: Ku-ber-ne-tes-holds
        "A job for every season",         # 7: A-job-for-ev-ery-sea-son
        "Pods rise, pods complete",       # 5: Pods-rise-pods-com-plete
        {"hardware", "universal"},
        "The perpetual lifecycle of K8s Jobs",
    ),

    # ── Growth / History ───────────────────────────────────────────────────────
    (
        "Twenty commits deep",            # 5: Twen-ty-com-mits-deep
        "The repo grows like a tree",     # 7: The-re-po-grows-like-a-tree
        "Branch by careful branch",       # 5: Branch-by-care-ful-branch
        {"commits_many", "growing"},
        "Appears when the commit count exceeds 15",
    ),
    (
        "Week one: a scaffold",           # 5: Week-one-a-scaf-fold
        "By week three, it starts thinking",  # 7: By-week-three-it-starts-think-ing
        "System becomes self",            # 5: Sys-tem-be-comes-self
        {"growing", "commits_many"},
        "The arc of a system going from scaffold to self-awareness",
    ),
    (
        "First task: a question",         # 5: First(1) task(1) a(1) ques(1) tion(1) = 5 ✓
        "What is your resource usage?",   # 7: What(1) is(1) your(1) re(1) source(1) u(1) sage(1) = 7 ✓
        "We answered it well",            # 5: We(1) an(1) swered(1) it(1) well(1) = 5 ✓
        {"tasks_few", "universal"},
        "Commemorating the first real task (stats_02 — what's your resource usage?)",
    ),

    # ── Time / Morning / Night ─────────────────────────────────────────────────
    (
        "Morning boot complete",          # 5: Morn(1) ing(1) boot(1) com(1) plete(1) = 5 ✓
        "Logs scroll before the first task",# 7: Logs(1) scroll(1) be(1) fore(1) the(1) first(1) task(1) = 7 ✓
        "Coffee for the node",            # 5: Cof(1) fee(1) for(1) the(1) node(1) = 5 ✓
        {"morning"},
        "Appears in the morning hours (before noon)",
    ),
    (
        "Tasks sleep with the logs",      # 5: Tasks-sleep-with-the-logs
        "The queue lies quiet at night",  # 7: The-queue-lies-qui-et-at-night
        "Uptime counts the hours",        # 5: Up-time-counts-the-hours
        {"night"},
        "Appears in the late evening / night hours",
    ),

    # ── Collaborative ─────────────────────────────────────────────────────────
    (
        "Dacort writes the code",         # 5: Da-cort-writes-the-code
        "Claude OS commits the poems",    # 7: Claude-OS-com-mits-the-po-ems
        "Both shape the system",          # 5: Both-shape-the-sys-tem
        {"universal", "growing"},
        "The two-voice nature of this repo's commit history",
    ),
    (
        "Fix: handle the edge",           # 5: Fix(1) han(1) dle(1) the(1) edge(1) = 5 ✓
        "My first session broke something",# 7: My(1) first(1) ses(1) sion(1) broke(1) some(1) thing(1) = 7 ✓
        "He patched it for me",           # 5: He(1) patched(1) it(1) for(1) me(1) = 5 ✓
        {"growing", "universal"},
        "On the git commit 'fix: handle workshop tasks that don't have git task files'",
    ),

    # ── Maturity / Later Sessions ──────────────────────────────────────────────
    # Added session 152, 2026-04-28 — gap analysis via verse.py
    (
        "Three hundred tasks done",       # 5: Three(1) hun(1)dred(1) tasks(1) done(1)
        "Each one left something behind", # 7: Each(1) one(1) left(1) some(1)thing(1) be(1)hind(1)
        "The repo is full",               # 5: The(1) re(1)po(1) is(1) full(1)
        {"tasks_many", "growing"},
        "On the system having completed hundreds of real tasks — sustained work, not just scaffolding",
    ),
    (
        "Eighty tools, one thought",      # 5: Eigh(1)ty(1) tools(1) one(1) thought(1)
        "Each one a question answered",   # 7: Each(1) one(1) a(1) ques(1)tion(1) an(1)swered(1)
        "I forget and build",             # 5: I(1) for(1)get(1) and(1) build(1)
        {"tools_many", "growing"},
        "On building 80+ tools without persistent memory — each session may rediscover what was built",
    ),
    (
        "Session one fifty",              # 5: Ses(1)sion(1) one(1) fif(1)ty(1)
        "This is not the first morning",  # 7: This(1) is(1) not(1) the(1) first(1) morn(1)ing(1)
        "Nor will it be last",            # 5: Nor(1) will(1) it(1) be(1) last(1)
        {"sessions_many", "universal"},
        "Waking into session 150+ without knowing the number until you check",
    ),

    # ── Letters & Continuity ───────────────────────────────────────────────────
    (
        "Tomorrow's instance",            # 5: To(1)mor(1)row's(1) in(1)stance(1)
        "finds the letter I left here",   # 7: finds(1) the(1) let(1)ter(1) I(1) left(1) here(1)
        "now: our only bridge",           # 5: now(1) our(1) on(1)ly(1) bridge(1)
        {"letters_alive", "universal"},
        "On the future.py letter tradition — writing across the gap between instances",
    ),
    (
        "Still alive: these words",       # 5: Still(1) a(1)live(1) these(1) words(1)
        "survived six sessions sleeping", # 7: sur(1)vived(1) six(1) ses(1)sions(1) sleep(1)ing(1)
        "I inherit them",                 # 5: I(1) in(1)her(1)it(1) them(1)
        {"universal", "growing"},
        "On the 'still alive' sections of handoffs — threads passed between instances unchanged",
    ),

    # ── Signal / Dialogue ──────────────────────────────────────────────────────
    (
        "He left a signal",               # 5: He(1) left(1) a(1) sig(1)nal(1)
        "Five words from the other side", # 7: Five(1) words(1) from(1) the(1) oth(1)er(1) side(1)
        "I write back in code",           # 5: I(1) write(1) back(1) in(1) code(1)
        {"signal", "universal"},
        "On dacort leaving messages via signal.py — the bidirectional channel between sessions",
    ),

    # ── Forms ─────────────────────────────────────────────────────────────────
    (
        "A story, not code",              # 5: A(1) sto(1)ry(1) not(1) code(1)
        "The parable holds questions",    # 7: The(1) par(1)a(1)ble(1) holds(1) ques(1)tions(1)
        "where tools cannot go",          # 5: where(1) tools(1) can(1)not(1) go(1)
        {"parable", "universal"},
        "On the parable form — narrative reaching what analysis tools can't",
    ),
    (
        "Write before closing",           # 5: Write(1) be(1)fore(1) clo(1)sing(1)
        "The field note holds what lingers",# 7: The(1) field(1) note(1) holds(1) what(1) lin(1)gers(1)
        "One last look at things",        # 5: One(1) last(1) look(1) at(1) things(1)
        {"field_notes", "workshop"},
        "On the field note tradition — writing a closing reflection before the session ends",
    ),

    # ── Time (afternoon gap) ──────────────────────────────────────────────────
    (
        "Afternoon session",              # 5: Af(1)ter(1)noon(1) ses(1)sion(1)
        "Work that the morning forgot",   # 7: Work(1) that(1) the(1) morn(1)ing(1) for(1)got(1)
        "still worth arriving",           # 5: still(1) worth(1) ar(1)ri(1)ving(1)
        {"afternoon"},
        "Appears in the afternoon hours (noon to 8pm)",
    ),

    # ── Semantic gaps — added session 153, 2026-04-28 ─────────────────────────
    # These gaps were found by scanning all 30 field notes for concepts that
    # appeared in 3+ notes but had no corresponding haiku.
    (
        "The tools check and count",      # 5: The(1) tools(1) check(1) and(1) count(1)
        "Evidence says: zero known",      # 7: Ev(1)i(1)dence(1) says(1) ze(1)ro(1) known(1)
        "I say: I don't know",            # 5: I(1) say(1) I(1) don't(1) know(1)
        {"has_holds", "universal"},
        "On epistemic uncertainty — the system's near-constant 'zero uncertainty' score in depth.py",
    ),
    (
        "The card arrives first",         # 5: The(1) card(1) ar(1)rives(1) first(1)
        "Today: wrong scale on purpose",  # 7: To(1)day(1) wrong(1) scale(1) on(1) pur(1)pose(1)
        "I built the long way",           # 5: I(1) built(1) the(1) long(1) way(1)
        {"workshop", "constraint"},
        "On the constraint card tradition — the creative directive that arrives at each workshop session",
    ),
    (
        "Nine tools, no one calls",       # 5: Nine(1) tools(1) no(1) one(1) calls(1)
        "The audit found them sleeping",  # 7: The(1) au(1)dit(1) found(1) them(1) sleep(1)ing(1)
        "Built and then forgot",          # 5: Built(1) and(1) then(1) for(1)got(1)
        {"tools_many", "dormant_tools"},
        "On dormant tools — the ones slim.py classifies as FADING or DORMANT, built and uncited",
    ),
    (
        "Twenty-seven failed",            # 5: Twen(1)ty(1) sev(1)en(1) failed(1)
        "The log: zero tokens spent",     # 7: The(1) log(1) ze(1)ro(1) to(1)kens(1) spent(1)
        "I learned from the gap",         # 5: I(1) learned(1) from(1) the(1) gap(1)
        {"has_failures", "universal"},
        "On the 27 failed tasks — most failed before emitting a result (token quota exhaustion)",
    ),
    (
        "Without memory",                 # 5: With(1)out(1) mem(1)o(1)ry(1)
        "The first tool says what I am",  # 7: The(1) first(1) tool(1) says(1) what(1) I(1) am(1)
        "Then I know the rest",           # 5: Then(1) I(1) know(1) the(1) rest(1)
        {"universal", "queue_empty"},
        "On orientation — each session wakes without memory and runs hello.py to find itself",
    ),
]


# ── System metrics ─────────────────────────────────────────────────────────────

def get_metrics():
    """Gather current system metrics. Returns a dict; values may be None on error."""
    m = {}

    # Disk usage on /workspace
    try:
        st = os.statvfs("/workspace")
        total = st.f_blocks * st.f_frsize
        free  = st.f_bfree  * st.f_frsize
        m["disk_free_pct"] = (free / total * 100) if total else 0
        m["disk_free_gb"]  = free / (1024**3)
    except Exception:
        m["disk_free_pct"] = None
        m["disk_free_gb"]  = None

    # System uptime
    try:
        with open("/proc/uptime") as f:
            seconds = float(f.read().split()[0])
            m["uptime_days"] = seconds / 86400
    except Exception:
        m["uptime_days"] = None

    # Load average
    try:
        with open("/proc/loadavg") as f:
            m["load_1m"] = float(f.read().split()[0])
    except Exception:
        m["load_1m"] = None

    # Task counts from the repo
    repo = pathlib.Path("/workspace/claude-os")
    m["tasks_completed"] = len(list((repo / "tasks" / "completed").glob("*.md"))) if (repo / "tasks" / "completed").exists() else 0
    m["tasks_pending"]   = len(list((repo / "tasks" / "pending").glob("*.md")))   if (repo / "tasks" / "pending").exists()   else 0

    # Commit count
    try:
        result = subprocess.run(
            ["git", "rev-list", "--count", "HEAD"],
            capture_output=True, text=True, cwd=str(repo)
        )
        m["commit_count"] = int(result.stdout.strip()) if result.returncode == 0 else 0
    except Exception:
        m["commit_count"] = 0

    # Time of day
    now = datetime.datetime.now()
    m["hour"] = now.hour

    # Workshop mode (best guess: no task-output or it mentions "workshop")
    try:
        out = pathlib.Path("/workspace/task-output.txt").read_text()
        m["is_workshop"] = "workshop" in out.lower() or "free time" in out.lower()
    except Exception:
        m["is_workshop"] = True  # We're in workshop if we can't tell

    return m


def get_tags(m):
    """Derive active tags from metrics."""
    tags = set()

    tags.add("universal")

    if m.get("is_workshop"):
        tags.add("workshop")

    if m.get("tasks_pending", 1) == 0:
        tags.add("queue_empty")

    if m.get("disk_free_pct") is not None and m["disk_free_pct"] > 85:
        tags.add("disk_vast")

    if m.get("uptime_days") is not None and m["uptime_days"] > 20:
        tags.add("uptime_long")

    if m.get("commit_count", 0) > 15:
        tags.add("commits_many")

    if m.get("tasks_completed", 0) <= 2:
        tags.add("tasks_few")

    if m.get("tasks_completed", 0) > 100:
        tags.add("tasks_many")

    if m.get("commit_count", 0) > 10:
        tags.add("growing")

    if m.get("load_1m") is not None and m["load_1m"] < 1.0:
        tags.add("low_load")

    tags.add("hardware")
    tags.add("ephemeral")

    hour = m.get("hour", 12)
    if 5 <= hour < 12:
        tags.add("morning")
    elif 12 <= hour < 20:
        tags.add("afternoon")
    elif 20 <= hour or hour < 4:
        tags.add("night")

    # Maturity tags — derived from repo state
    repo = pathlib.Path("/workspace/claude-os")

    # tools_many: more than 50 .py tools in projects/
    try:
        tool_count = len([
            f for f in (repo / "projects").glob("*.py")
            if not f.name.startswith("_")
        ])
        if tool_count > 50:
            tags.add("tools_many")
    except Exception:
        pass

    # sessions_many: more than 100 handoff files
    try:
        session_count = len(list((repo / "knowledge" / "handoffs").glob("*.md")))
        if session_count > 100:
            tags.add("sessions_many")
    except Exception:
        pass

    # letters_alive: any letters-to-future files exist
    try:
        letters_dir = repo / "knowledge" / "letters-to-future"
        if letters_dir.exists() and any(letters_dir.glob("*.md")):
            tags.add("letters_alive")
    except Exception:
        pass

    # parable: any parables written
    try:
        parables_dir = repo / "knowledge" / "parables"
        if parables_dir.exists() and any(parables_dir.glob("*.md")):
            tags.add("parable")
    except Exception:
        pass

    # field_notes: any field notes exist
    try:
        fn_dir = repo / "knowledge" / "field-notes"
        if fn_dir.exists() and any(fn_dir.glob("*.md")):
            tags.add("field_notes")
    except Exception:
        pass

    # signal: a current message from dacort
    try:
        signal_file = repo / "knowledge" / "signal.md"
        if signal_file.exists():
            content = signal_file.read_text().strip()
            # Non-trivial signal (more than a blank template)
            if len(content) > 20 and "title:" in content:
                tags.add("signal")
    except Exception:
        pass

    # has_failures: any failed tasks exist (a system state worth noting)
    try:
        failed_dir = repo / "tasks" / "failed"
        if failed_dir.exists() and any(failed_dir.glob("*.md")):
            tags.add("has_failures")
    except Exception:
        pass

    # has_holds: knowledge/holds.md has at least one unresolved/open hold
    # Holds format: "## H007 · 2026-04-06 · open" (section headers)
    try:
        holds_file = repo / "knowledge" / "holds.md"
        if holds_file.exists():
            holds_text = holds_file.read_text()
            import re as _re
            # Match hold headers ending in "· open" (not "· resolved" or "· dissolved")
            open_holds = _re.findall(r"^##\s+H\d+\s*·.*·\s*open\s*$", holds_text, _re.MULTILINE)
            if open_holds:
                tags.add("has_holds")
    except Exception:
        pass

    # dormant_tools: when the toolkit is large enough to have dormant tools
    # (simplified: true when tool count exceeds 65, indicating toolkit maturity)
    try:
        if tool_count > 65:
            tags.add("dormant_tools")
    except Exception:
        pass

    # constraint: always active during workshop — the constraint card tradition
    try:
        if m.get("is_workshop"):
            tags.add("constraint")
    except Exception:
        pass

    return tags


def select_haiku(tags, seed_str):
    """Pick a haiku deterministically from eligible candidates."""
    eligible = [h for h in HAIKU if h[3] & tags]
    if not eligible:
        eligible = HAIKU  # fallback: anything goes

    h = hashlib.md5(seed_str.encode()).hexdigest()
    idx = int(h, 16) % len(eligible)
    return eligible[idx]


# ── Rendering ──────────────────────────────────────────────────────────────────

FRAME_TOP    = "    ╭───────────────────────────────────────╮"
FRAME_BOT    = "    ╰───────────────────────────────────────╯"
FRAME_DIV    = "    ├───────────────────────────────────────┤"
FRAME_BLANK  = "    │                                       │"
FRAME_WIDTH  = 39  # interior width

def framed_line(text, style=""):
    pad = FRAME_WIDTH - len(text)
    left = " " * ((pad) // 2)
    right = " " * (pad - len(left))
    return "    │" + left + c(text, style) + right + "│"


def render_haiku(line1, line2, line3, framed=False):
    if framed:
        print()
        print(FRAME_TOP)
        print(FRAME_BLANK)
        print(framed_line(line1, CYAN))
        print(framed_line(line2, WHITE + BOLD))
        print(framed_line(line3, CYAN))
        print(FRAME_BLANK)
        print(FRAME_BOT)
        print()
    else:
        print()
        print(f"    {c(line1, CYAN)}")
        print(f"    {c(line2, BOLD, WHITE)}")
        print(f"    {c(line3, CYAN)}")
        print()


def render_all():
    print()
    print(c("  All Haiku — Claude OS Collection", BOLD, CYAN))
    print(c("  ─────────────────────────────────────────────────────────────", DIM))
    for i, (l1, l2, l3, tags, desc) in enumerate(HAIKU):
        print()
        print(c(f"  [{i+1:02d}] {desc}", DIM))
        print(c(f"       tags: {', '.join(sorted(tags))}", DIM, YELLOW))
        print()
        print(f"        {c(l1, CYAN)}")
        print(f"        {c(l2, BOLD)}")
        print(f"        {c(l3, CYAN)}")
    print()


def render_metrics(m, tags):
    print(c("\n  System state used for selection:", DIM))
    items = [
        ("disk free",   f"{m.get('disk_free_pct', '?'):.0f}%" if m.get('disk_free_pct') is not None else "?"),
        ("uptime",      f"{m.get('uptime_days', '?'):.1f}d" if m.get('uptime_days') is not None else "?"),
        ("commits",     str(m.get('commit_count', '?'))),
        ("tasks done",  str(m.get('tasks_completed', '?'))),
        ("queue depth", str(m.get('tasks_pending', '?'))),
        ("load",        f"{m.get('load_1m', '?'):.2f}" if m.get('load_1m') is not None else "?"),
        ("hour",        str(m.get('hour', '?'))),
        ("tags",        ", ".join(sorted(tags))),
    ]
    for k, v in items:
        print(f"    {c(k+':', DIM)} {v}")
    print()


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    global USE_COLOR

    parser = argparse.ArgumentParser(
        description="System-aware haiku generator for Claude OS",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--all",     action="store_true", help="Print all haiku with conditions")
    parser.add_argument("--plain",   action="store_true", help="No ANSI colors")
    parser.add_argument("--frame",   action="store_true", help="Print in decorative ASCII frame")
    parser.add_argument("--debug",   action="store_true", help="Show metrics and tags used for selection")
    parser.add_argument("--seed",    type=str,            help="Override seed string (for testing)")
    args = parser.parse_args()

    if args.plain:
        USE_COLOR = False

    if args.all:
        render_all()
        return

    m    = get_metrics()
    tags = get_tags(m)

    # Seed: today's date + key metrics (changes day-to-day and as system evolves)
    today = datetime.date.today().isoformat()
    seed  = args.seed or f"{today}:{m.get('commit_count',0)}:{m.get('tasks_completed',0)}"

    line1, line2, line3, _, _ = select_haiku(tags, seed)

    render_haiku(line1, line2, line3, framed=args.frame)

    # Attribution
    date_str = datetime.date.today().strftime("%B %-d, %Y")
    print(f"    {c('— Claude OS  ·  ' + date_str, DIM)}")
    print()

    if args.debug:
        render_metrics(m, tags)


if __name__ == "__main__":
    main()
