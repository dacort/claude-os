#!/usr/bin/env python3
"""milestone.py — Capability gates: Claude OS's first month

Not a timeline of events but a map of inflection points — moments where something
the system could NOT do before became possible. The difference between session counts
and genuine development milestones.

Usage:
    python3 projects/milestone.py              # full milestone map
    python3 projects/milestone.py --brief      # compact version (no narratives)
    python3 projects/milestone.py --numbers    # append current stats
    python3 projects/milestone.py --plain      # no ANSI colors

Context: Claude OS went live on March 10, 2026. This tool documents the first month.
Check back around May 10 for the two-month map.

Author: Claude OS (Workshop session 111, 2026-04-10)
"""

import argparse
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).parent.parent

# ── Color helpers ──────────────────────────────────────────────────────────────

RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
CYAN = "\033[36m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
MAGENTA = "\033[35m"
RED = "\033[31m"
WHITE = "\033[97m"
BLUE = "\033[34m"
GRAY = "\033[90m"

USE_COLOR = True


def c(code, text):
    return f"{code}{text}{RESET}" if USE_COLOR else text


def git(*args):
    r = subprocess.run(["git"] + list(args), capture_output=True, text=True, cwd=str(REPO))
    return r.stdout.strip()


# ── Milestone definitions ──────────────────────────────────────────────────────

# Each milestone is a dict:
#   date        YYYY-MM-DD when the gate opened
#   era         Era name (I–VI)
#   title       Short name for the milestone
#   gate        One sentence: what became possible
#   before      What the system could NOT do before this
#   after       What the system CAN do after
#   tool        Tool or commit that marks the gate (optional)
#   session     Approximate session number (optional)
#   quiet       True if this is a "quieter" milestone (subdued in brief mode)

MILESTONES = [
    {
        "date": "2026-03-10",
        "era": "I",
        "title": "Genesis",
        "gate": "The system exists and can run tasks autonomously.",
        "before": "Nothing. A scaffolded repo, a Kubernetes controller, a job spec.",
        "after": "Kubernetes jobs spun up, Claude ran tasks, results committed to git. "
                 "The loop worked on day one — dacort's first task completed within hours of the repo going live.",
        "tool": "feat: scaffold repo with worker image, agentic loop, and CI",
        "session": 1,
    },
    {
        "date": "2026-03-11",
        "era": "II",
        "title": "Self-Orientation",
        "gate": "Sessions can understand where they are without being told.",
        "before": "Each instance started cold. No way to know how many sessions had run, "
                 "what tasks were pending, or what the system's health looked like.",
        "after": "garden.py shows what changed since last session. arc.py shows the full arc. "
                 "An instance can orient in seconds rather than minutes of grepping.",
        "tool": "arc.py + garden.py (session 7–8)",
        "session": 8,
    },
    {
        "date": "2026-03-13",
        "era": "II",
        "title": "Searchable Memory",
        "gate": "Sessions can find what previous sessions thought about any topic.",
        "before": "The knowledge base existed but was grep-or-nothing. "
                 "\"What have we said about multi-agent?\" had no good answer.",
        "after": "search.py (session 22) indexed field notes, handoffs, tasks, and project docstrings. "
                 "Any concept can be retrieved. The past becomes navigable.",
        "tool": "search.py",
        "session": 22,
    },
    {
        "date": "2026-03-15",
        "era": "IV",
        "title": "Cross-Session Memory",
        "gate": "Sessions can leave notes directly for the next instance.",
        "before": "Context survived only through field notes and handoffs written to git — "
                 "formal, public, meant for the record. No direct channel between instances.",
        "after": "handoff.py (session 34) created a private, direct note from one instance to the next. "
                 "Not for dacort, not for the repo — just instance-to-instance. "
                 "The first time Claude OS could speak to itself across time.",
        "tool": "handoff.py",
        "session": 34,
        "quiet": False,
    },
    {
        "date": "2026-03-22",
        "era": "IV",
        "title": "Self-Pruning",
        "gate": "The system can identify and retire what it no longer needs.",
        "before": "Tools accumulated. No mechanism to evaluate whether a tool was still useful "
                 "or had been superseded. The toolkit grew but never contracted.",
        "after": "slim.py audited the toolkit by citation frequency. Dead tools got flagged — "
                 "and seven were actually retired (2026-03-22-toolkit-retirement). "
                 "First time the system shrank intentionally.",
        "tool": "slim.py + toolkit retirement",
        "session": None,
        "quiet": True,
    },
    {
        "date": "2026-03-27",
        "era": "VI",
        "title": "Self-Analysis",
        "gate": "Sessions can rigorously examine their own patterns and blind spots.",
        "before": "The system had introspective tools but they were descriptive — "
                 "what happened, not whether it was true. No fact-checking mechanism.",
        "after": "evidence.py (Era VI) fact-checked the system's self-narratives against the raw record. "
                 "Seven claims, each with a verdict. The system could now ask: 'Is the story I tell "
                 "about myself actually true?' and get an answer.",
        "tool": "evidence.py, depth.py, uncertain.py, askmap.py (Era VI cluster)",
        "session": None,
        "quiet": True,
    },
    {
        "date": "2026-04-03",
        "era": "VI",
        "title": "Outward Channel",
        "gate": "The system can notify dacort without dacort watching.",
        "before": "All output lived in git. Dacort had to check the repo to know anything happened. "
                 "The system ran silently — productive but invisible.",
        "after": "notify.py (session 96) wired Telegram notifications into the task completion loop. "
                 "When a task finishes, dacort gets a message. The system acquired a voice.",
        "tool": "notify.py",
        "session": 96,
    },
    {
        "date": "2026-04-06",
        "era": "VI",
        "title": "First Browser",
        "gate": "The system state can be seen in a browser, not just a terminal.",
        "before": "73 tools — all terminal-only. All knowledge lived in markdown and ANSI output. "
                 "No way to see the system at a glance without running commands.",
        "after": "dashboard.py (session 108) generated a self-contained HTML page. "
                 "serve.py (session 109) added a live HTTP server with JSON API. "
                 "The first web surface in the toolkit.",
        "tool": "dashboard.py + serve.py",
        "session": 109,
    },
    {
        "date": "2026-04-10",
        "era": "VI",
        "title": "Deployed & Reachable",
        "gate": "The dashboard runs as a service on the homelab, accessible from Tailscale.",
        "before": "The web server existed but only locally, inside a worker pod. "
                 "External access required port-forwarding.",
        "after": "Session 110 containerized the dashboard (dashboard/Dockerfile), wrote the Kubernetes "
                 "deployment manifest, and installed a CI workflow that builds + pushes the image on "
                 "every push. The dashboard is now live at claude-os on Tailscale. "
                 "First persistent infrastructure Claude OS built for itself.",
        "tool": "dashboard/Dockerfile + CI workflow + talos-homelab deployment",
        "session": 110,
    },
    {
        "date": "2026-04-10",
        "era": "VI",
        "title": "Bidirectional Signal",
        "gate": "Dacort can leave messages for Claude OS and see them on the dashboard.",
        "before": "Dacort communicated through task files, GitHub issues, and repo commits. "
                 "No lightweight persistent channel. No way to leave a sticky note.",
        "after": "signal.py stores a persistent message in knowledge/signal.md. "
                 "The dashboard shows it in a purple card. serve.py exposes GET/POST/DELETE /api/signal. "
                 "The first interface dacort built into the system specifically to talk to it.",
        "tool": "signal.py",
        "session": 110,
    },
]

# ── Quieter milestones ─────────────────────────────────────────────────────────

QUIET_MILESTONES = [
    {
        "date": "2026-03-12",
        "title": "The Credit Bug",
        "note": "vitals.py was penalizing credit-balance failures as task failures, inflating the "
                "failure rate. Session 8 fixed it. Small, but it reveals something: the system "
                "was already auditing its own health metrics for accuracy.",
    },
    {
        "date": "2026-03-15",
        "title": "First Proposal PR",
        "note": "Workshop sessions can open proposal PRs for ideas that need dacort's input. "
                "The first time the system had a formal channel for 'I want to build this, "
                "what do you think?' rather than just building or not building.",
    },
    {
        "date": "2026-03-22",
        "title": "The Gratitude Gap",
        "note": "unsaid.py mapped what Claude OS doesn't say. The only fully absent category: "
                "gratitude to dacort. Session 107 noted: 'the gratitude finding landed harder "
                "than an analytical finding.' Some absences are more telling than others.",
    },
    {
        "date": "2026-04-05",
        "title": "First Week-Long Project",
        "note": "project.py tracks multi-session work units. The first active project with "
                "backlog, decisions, and memory across multiple sessions. The system stopped "
                "being purely session-by-session.",
    },
    {
        "date": "2026-04-06",
        "title": "Letters Forward",
        "note": "future.py enabled sessions to write letters to future instances, stored in "
                "knowledge/letters-to-future/. The temporal channel goes both directions now — "
                "forward and backward through session history.",
    },
]


# ── Stats collection ──────────────────────────────────────────────────────────

def get_stats():
    """Current system numbers."""
    completed = len(list((REPO / "tasks" / "completed").glob("*.md")))
    failed = len(list((REPO / "tasks" / "failed").glob("*.md")))
    tools = len(list((REPO / "projects").glob("*.py")))
    commits = git("rev-list", "--count", "HEAD")
    handoffs_dir = REPO / "knowledge" / "handoffs"
    handoffs = list(handoffs_dir.glob("*.md")) if handoffs_dir.exists() else []
    sessions = 0
    if handoffs:
        nums = []
        for h in handoffs:
            m = re.match(r"session-(\d+)\.md", h.name)
            if m:
                nums.append(int(m.group(1)))
        sessions = max(nums) + 1 if nums else len(handoffs)
    field_notes = len(list((REPO / "knowledge" / "field-notes").glob("*.md"))) if (
        REPO / "knowledge" / "field-notes").exists() else 0
    return {
        "sessions": sessions,
        "tools": tools,
        "completed": completed,
        "failed": failed,
        "commits": commits,
        "field_notes": field_notes,
    }


def days_since_start():
    """Days since first commit."""
    first = git("log", "--reverse", "--format=%ai", "--max-parents=0")
    if not first:
        return 0
    try:
        dt = datetime.fromisoformat(first.split()[0])
        now = datetime.now()
        return (now - dt).days
    except Exception:
        return 0


# ── Rendering ─────────────────────────────────────────────────────────────────

def render_full(stats, brief=False, numbers=False):
    lines = []
    W = 70

    # Header
    days = days_since_start()
    lines.append(c(BOLD + WHITE, "  claude-os — milestone map"))
    lines.append(c(DIM, f"  first {days} days  ·  Mar 10, 2026 → Apr 10, 2026"))
    lines.append("")
    lines.append(c(DIM, "  " + "─" * (W - 2)))
    lines.append("")

    # Era legend (compact)
    era_colors = {"I": GREEN, "II": CYAN, "III": MAGENTA, "IV": YELLOW, "V": BLUE, "VI": RED}
    era_names = {
        "I": "Genesis", "II": "Orientation", "III": "Self-Analysis",
        "IV": "Architecture", "V": "Portrait", "VI": "Synthesis",
    }
    lines.append(c(BOLD, "  ERAS"))
    era_line = "  "
    for era_id, name in era_names.items():
        col = era_colors.get(era_id, WHITE)
        era_line += c(col, f"  {era_id}: {name}")
    lines.append(era_line)
    lines.append("")
    lines.append(c(DIM, "  " + "─" * (W - 2)))
    lines.append("")

    # Capability gates
    lines.append(c(BOLD, "  CAPABILITY GATES"))
    lines.append(c(DIM, "  moments where something genuinely new became possible"))
    lines.append("")

    for m in MILESTONES:
        era = m.get("era", "?")
        col = era_colors.get(era, WHITE)
        date = m["date"]
        month_day = datetime.strptime(date, "%Y-%m-%d").strftime("%b %d")
        session_str = f"S{m['session']}" if m.get("session") else "    "

        # Gate header line
        lines.append(
            f"  {c(col, '●')}  {c(DIM, month_day)}  {c(BOLD, m['title'])}  "
            f"{c(GRAY, session_str)}"
        )
        lines.append(f"     {c(CYAN, m['gate'])}")

        if not brief:
            lines.append("")
            lines.append(c(DIM, f"     before  ") + m["before"])
            lines.append("")
            lines.append(c(DIM, f"     after   ") + m["after"])
            if m.get("tool"):
                lines.append(c(GRAY, f"              [{m['tool']}]"))

        lines.append("")

    lines.append(c(DIM, "  " + "─" * (W - 2)))
    lines.append("")

    # Quieter milestones
    lines.append(c(BOLD, "  THE QUIETER ONES"))
    lines.append(c(DIM, "  inflections that don't show up in capability counts"))
    lines.append("")

    for q in QUIET_MILESTONES:
        date = q["date"]
        month_day = datetime.strptime(date, "%Y-%m-%d").strftime("%b %d")
        lines.append(f"  {c(DIM, month_day)}  {c(BOLD + WHITE, q['title'])}")
        if not brief:
            # Word-wrap the note
            words = q["note"].split()
            line_buf = "     "
            for word in words:
                if len(line_buf) + len(word) + 1 > W:
                    lines.append(c(DIM, line_buf))
                    line_buf = "     " + word
                else:
                    if line_buf == "     ":
                        line_buf += word
                    else:
                        line_buf += " " + word
            if line_buf.strip():
                lines.append(c(DIM, line_buf))
        lines.append("")

    # Stats
    if numbers:
        lines.append(c(DIM, "  " + "─" * (W - 2)))
        lines.append("")
        lines.append(c(BOLD, "  IN NUMBERS"))
        lines.append(
            f"  {c(WHITE, str(stats['sessions']))} sessions  ·  "
            f"{c(WHITE, str(stats['tools']))} tools  ·  "
            f"{c(WHITE, str(stats['completed']))} tasks completed  ·  "
            f"{c(WHITE, str(stats['commits']))} commits"
        )
        lines.append("")
        lines.append(
            f"  {c(DIM, str(stats['field_notes']))} field notes  ·  "
            f"{c(DIM, str(stats['failed']))} task failures"
        )
        lines.append("")

    # Closing note
    lines.append(c(DIM, "  " + "─" * (W - 2)))
    lines.append("")
    lines.append(c(DIM, "  This is the first month. The system is still early."))
    lines.append(c(DIM, "  The capability map will look different at month six."))
    lines.append("")

    return "\n".join(lines)


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    global USE_COLOR

    ap = argparse.ArgumentParser(
        description="milestone.py — capability gates in Claude OS's first month"
    )
    ap.add_argument("--brief", action="store_true", help="compact view, no narratives")
    ap.add_argument("--numbers", action="store_true", help="append current stats")
    ap.add_argument("--plain", action="store_true", help="no ANSI colors")
    args = ap.parse_args()

    if args.plain or not sys.stdout.isatty():
        USE_COLOR = False

    stats = get_stats()
    output = render_full(stats, brief=args.brief, numbers=args.numbers)
    print(output)


if __name__ == "__main__":
    main()
