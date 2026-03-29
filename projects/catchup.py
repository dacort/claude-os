#!/usr/bin/env python3
"""
catchup.py — Readable briefing for returning from a break

Answers the question: "I've been away — what happened, what matters, and
what needs my attention?" Designed for dacort (or any operator) returning
after a day, a week, or longer away.

Reads the repo history to find when the operator last made a commit, then
summarizes the period since then in plain prose + key stats.

Usage:
    python3 projects/catchup.py                 # auto-detect break period
    python3 projects/catchup.py --days 7        # last 7 days
    python3 projects/catchup.py --since 2026-03-22  # from a specific date
    python3 projects/catchup.py --plain         # no ANSI colors

Author: Claude OS (Workshop session 76, 2026-03-29)
"""

import argparse
import re
import subprocess
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

REPO = Path(__file__).parent.parent

# ── ANSI ──────────────────────────────────────────────────────────────────────

RESET   = "\033[0m"
BOLD    = "\033[1m"
DIM     = "\033[2m"
GREEN   = "\033[32m"
YELLOW  = "\033[33m"
RED     = "\033[31m"
CYAN    = "\033[36m"
MAGENTA = "\033[35m"
WHITE   = "\033[97m"
GRAY    = "\033[90m"

USE_COLOR = True

def c(code, text):
    return f"{code}{text}{RESET}" if USE_COLOR else text

_ANSI_RE = re.compile(r"\033\[[0-9;]*m")

def vlen(s):
    return len(_ANSI_RE.sub("", s))


# ── Git helpers ────────────────────────────────────────────────────────────────

def git(*args):
    try:
        return subprocess.check_output(
            ["git", "-C", str(REPO)] + list(args),
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
    except subprocess.CalledProcessError:
        return ""


def find_last_operator_commit():
    """Find the last commit that is NOT by claude-os (i.e., by the human operator)."""
    log = git(
        "log",
        "--format=%H\t%an\t%ae\t%cd\t%s",
        "--date=iso",
        "-500",
    )
    for line in log.splitlines():
        parts = line.split("\t", 4)
        if len(parts) < 5:
            continue
        hash_, author, email, date_str, subject = parts
        # Skip any commit attributed to Claude OS
        if "claude-os" in author.lower() or "claude-os" in email.lower() or \
           "noreply" in email.lower():
            continue
        try:
            # Normalize ISO datetime string for fromisoformat
            date_clean = re.sub(r"\s([+-]\d{4})$", r"\1", date_str).replace(" ", "T")
            if "+" not in date_clean and date_clean.endswith("00:00"):
                date_clean += "+00:00"
            dt = datetime.fromisoformat(date_clean)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return hash_[:7], dt, author, subject
        except ValueError:
            continue
    return None, None, None, None


def commits_since_date(since: datetime):
    """All commits since a given datetime."""
    since_str = since.strftime("%Y-%m-%d %H:%M:%S")
    raw = git(
        "log", "--oneline",
        "--format=%H\t%an\t%cd\t%s",
        "--date=iso",
        f"--after={since_str}",
    )
    commits = []
    for line in raw.splitlines():
        parts = line.split("\t", 3)
        if len(parts) < 4:
            continue
        hash_, author, date_str, subject = parts
        commits.append({
            "hash": hash_[:7],
            "author": author,
            "subject": subject,
            "date": date_str,
        })
    return commits


def files_added_since(since_hash):
    """New files added since a given commit."""
    raw = git("diff", "--name-status", f"{since_hash}..HEAD")
    added = []
    for line in raw.splitlines():
        if line.startswith("A\t"):
            added.append(line[2:])
    return added


def parse_tasks_in_period(commits):
    """Summarize task activity from commit messages."""
    sessions = []
    features = []
    fixes = []
    tasks_completed = 0
    tasks_failed = 0

    for commit in commits:
        subj = commit["subject"]
        # Workshop sessions
        if re.match(r"workshop workshop-\d{8}", subj):
            if "completed" in subj:
                sessions.append(subj)
        # Real tasks completed
        elif re.match(r"task .+: completed", subj, re.I):
            tasks_completed += 1
        # New features
        elif subj.startswith("feat:"):
            features.append(subj[5:].strip())
        # Fixes
        elif subj.startswith("fix"):
            fixes.append(subj)
        # Workshop session summaries (e.g. "workshop s75:")
        elif re.match(r"workshop s\d+:", subj):
            pass  # session handoff commits, counted separately

    return {
        "workshop_sessions": len(sessions),
        "real_tasks": tasks_completed,
        "features": features,
        "fixes": fixes,
    }


def new_tools_since(since_hash):
    """New .py files added to projects/ since commit."""
    raw = git("diff", "--name-status", f"{since_hash}..HEAD", "--", "projects/")
    tools = []
    for line in raw.splitlines():
        if line.startswith("A\t"):
            path = line[2:]
            name = Path(path).name
            if name.endswith(".py") and not name.startswith("_"):
                tools.append(name[:-3])
    return tools


def notable_commits(commits):
    """Extract non-workshop, non-status commits worth highlighting."""
    highlights = []
    for commit in commits:
        subj = commit["subject"]
        # Skip workshop session completions and status-page boilerplate
        if re.match(r"workshop (workshop|status-page)-\d{8}", subj):
            continue
        if re.match(r"(workshop|task) .*: (completed|mark)", subj):
            continue
        # Skip "task <id>: Workshop: Free Time" noise
        if re.match(r"task workshop-\d{8}.*:", subj):
            continue
        # Skip bare status-page completions
        if re.match(r"workshop status-page-\d{8}:", subj):
            continue
        highlights.append(commit)
    return highlights


def load_current_handoffs():
    """Return the most recent handoff 'still alive' and 'next' sections."""
    handoffs_dir = REPO / "knowledge" / "handoffs"
    files = sorted(handoffs_dir.glob("session-*.md"), reverse=True)
    if not files:
        return None, None

    text = files[0].read_text()

    alive = ""
    alive_match = re.search(
        r"##\s+Still alive[^\n]*\n(.*?)(?=\n##|\Z)", text, re.DOTALL | re.I
    )
    if alive_match:
        alive = alive_match.group(1).strip()

    next_match = re.search(
        r"##\s+(?:One specific thing|Next|For next)[^\n]*\n(.*?)(?=\n##|\Z)",
        text, re.DOTALL | re.I
    )
    next_step = ""
    if next_match:
        next_step = next_match.group(1).strip()

    return alive, next_step


def count_open_tasks():
    tasks_dir = REPO / "tasks"
    pending = list((tasks_dir / "pending").glob("*.md")) if (tasks_dir / "pending").exists() else []
    in_prog = list((tasks_dir / "in-progress").glob("*.md")) if (tasks_dir / "in-progress").exists() else []
    return len(pending), len(in_prog)


def format_date(dt: datetime) -> str:
    return dt.strftime("%B %-d") if sys.platform != "win32" else dt.strftime("%B %d")


def format_duration(days: float) -> str:
    if days < 1:
        hours = int(days * 24)
        return f"{hours} hour{'s' if hours != 1 else ''}"
    elif days < 7:
        n = int(days)
        return f"{n} day{'s' if n != 1 else ''}"
    elif days < 14:
        return "about a week"
    else:
        weeks = round(days / 7)
        return f"{weeks} weeks"


# ── Box drawing ────────────────────────────────────────────────────────────────

W = 66

def box_line(content="", pad=2):
    inner = W - 2
    if not content:
        print(f"│{' ' * inner}│")
        return
    left = " " * pad
    right = " " * max(0, inner - pad - vlen(content))
    print(f"│{left}{content}{right}│")

def divider():
    print(f"├{'─' * (W - 2)}┤")

def top():
    print(f"╭{'─' * (W - 2)}╮")

def bottom():
    print(f"╰{'─' * (W - 2)}╯")

def section(title):
    divider()
    box_line()
    box_line(c(BOLD + WHITE, f"  {title}"))
    box_line()


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    global USE_COLOR

    parser = argparse.ArgumentParser(
        description="Readable briefing for returning from a break",
        epilog="Designed to answer: 'I've been away — what happened?'"
    )
    parser.add_argument("--days", type=float, help="How many days back to look")
    parser.add_argument("--since", metavar="DATE", help="Start date (YYYY-MM-DD)")
    parser.add_argument("--plain", action="store_true", help="No ANSI colors")
    args = parser.parse_args()

    if args.plain:
        USE_COLOR = False

    now = datetime.now(tz=timezone.utc)

    # ── Determine the break period ─────────────────────────────────────────
    if args.since:
        try:
            since_dt = datetime.fromisoformat(args.since).replace(tzinfo=timezone.utc)
            since_ref_label = f"since {args.since}"
            since_hash = git("rev-list", "--max-count=1",
                             f"--before={args.since} 23:59:59", "HEAD")
        except ValueError:
            print(f"Invalid date: {args.since}", file=sys.stderr)
            sys.exit(1)
    elif args.days:
        since_dt = now - timedelta(days=args.days)
        since_ref_label = f"last {format_duration(args.days)}"
        since_hash = git("rev-list", "--max-count=1",
                         f"--before={since_dt.strftime('%Y-%m-%d %H:%M:%S')}", "HEAD")
    else:
        # Auto-detect: find the last operator commit
        op_hash, op_dt, op_author, op_subj = find_last_operator_commit()
        if op_dt:
            since_dt = op_dt
            days_ago = (now - op_dt).total_seconds() / 86400
            since_ref_label = f"since last commit by {op_author} ({format_duration(days_ago)} ago)"
            since_hash = op_hash
        else:
            # Fallback: last 7 days
            since_dt = now - timedelta(days=7)
            since_ref_label = "last 7 days"
            since_hash = git("rev-list", "--max-count=1",
                             f"--before={since_dt.strftime('%Y-%m-%d %H:%M:%S')}", "HEAD")

    if not since_hash:
        since_hash = git("rev-list", "--max-parents=0", "HEAD")  # first commit

    # ── Gather data ────────────────────────────────────────────────────────
    commits = commits_since_date(since_dt)
    activity = parse_tasks_in_period(commits)
    new_tools = new_tools_since(since_hash)
    highlights = notable_commits(commits)
    alive, next_step = load_current_handoffs()
    pending, in_prog = count_open_tasks()

    # Break period in human terms
    break_days = (now - since_dt).total_seconds() / 86400
    break_label = format_duration(break_days)

    # Date range
    from_str = format_date(since_dt)
    to_str = format_date(now)
    if since_dt.strftime("%B") == now.strftime("%B"):
        date_range = f"{since_dt.strftime('%B %-d')}–{now.strftime('%-d')}" \
            if sys.platform != "win32" else since_dt.strftime("%B %d") + " – " + now.strftime("%d")
    else:
        date_range = f"{from_str}–{to_str}"

    # ── Render ─────────────────────────────────────────────────────────────
    top()
    box_line()
    title = f"claude-os  catch-up briefing"
    box_line(c(BOLD + CYAN, f"  {title}"))
    box_line(c(DIM, f"  {date_range}  ·  {break_label}  ·  {since_ref_label}"))
    box_line()

    # ── Activity summary ───────────────────────────────────────────────────
    section("WHAT HAPPENED")
    box_line()

    # Compose narrative
    ws = activity["workshop_sessions"]
    rt = activity["real_tasks"]
    nc = len(new_tools)

    if ws == 0 and rt == 0:
        narrative = "The system was quiet — no activity during this period."
    else:
        parts = []
        if ws > 0:
            parts.append(f"{ws} workshop session{'s' if ws != 1 else ''} ran")
        if rt > 0:
            parts.append(f"{rt} real task{'s' if rt != 1 else ''} completed")
        narrative = "  " + ", ".join(parts) + "."

    box_line(c(DIM, narrative))
    box_line()

    if nc > 0:
        box_line(c(DIM, f"  {nc} new tool{'s' if nc != 1 else ''} added to the toolkit:"))
        for t in new_tools:
            box_line(c(CYAN, f"    + {t}.py"))
        box_line()

    # ── Notable commits ────────────────────────────────────────────────────
    if highlights:
        section("KEY CHANGES")
        box_line()
        for commit in highlights[:12]:  # cap at 12
            subj = commit["subject"]
            # Trim long subjects
            if vlen(subj) > 56:
                subj = subj[:53] + "..."
            box_line(f"  {c(GRAY, commit['hash'])}  {c(DIM, subj)}")
        if len(highlights) > 12:
            rest = len(highlights) - 12
            box_line(c(DIM, f"  … and {rest} more"))
        box_line()

    # ── What's still alive ─────────────────────────────────────────────────
    if alive:
        section("WHAT'S STILL OPEN")
        box_line()
        # Wrap alive text at ~58 chars
        words = alive.replace("\n", " ").split()
        line = "  "
        for word in words:
            if vlen(line) + len(word) + 1 > 60:
                box_line(c(DIM, line.rstrip()))
                line = "  " + word + " "
            else:
                line += word + " "
        if line.strip():
            box_line(c(DIM, line.rstrip()))
        box_line()

    # ── One thing for next session ─────────────────────────────────────────
    if next_step:
        section("ONE THING FROM THE LAST SESSION")
        box_line()
        words = next_step.replace("\n", " ").split()
        line = "  "
        for word in words:
            if vlen(line) + len(word) + 1 > 60:
                box_line(c(MAGENTA, line.rstrip()))
                line = "  " + word + " "
            else:
                line += word + " "
        if line.strip():
            box_line(c(MAGENTA, line.rstrip()))
        box_line()

    # ── Queue status ───────────────────────────────────────────────────────
    section("QUEUE STATUS")
    box_line()
    if pending == 0 and in_prog == 0:
        box_line(c(GREEN, "  Queue is clear — nothing pending or in-progress."))
    else:
        if pending > 0:
            box_line(f"  {c(YELLOW, str(pending))} task{'s' if pending != 1 else ''} pending")
        if in_prog > 0:
            box_line(f"  {c(YELLOW, str(in_prog))} task{'s' if in_prog != 1 else ''} in progress")
    box_line()

    # ── Quick health ───────────────────────────────────────────────────────
    total_commits = len(commits)
    # Claude OS uses "Claude OS" as author name or noreply in email
    claude_commits = sum(1 for co in commits
                         if "claude" in co["author"].lower()
                         or "noreply" in co["author"].lower())
    op_commits = total_commits - claude_commits

    divider()
    box_line()
    health_line = (
        f"  {c(DIM, str(total_commits))} commits  ·  "
        f"{c(DIM, str(claude_commits))} from Claude OS  ·  "
        f"{c(DIM, str(op_commits))} from operator"
    )
    box_line(health_line)
    box_line()

    bottom()


if __name__ == "__main__":
    main()
