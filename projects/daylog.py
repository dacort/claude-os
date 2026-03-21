#!/usr/bin/env python3
"""
daylog.py — A day-in-review for Claude OS.

Given a date (default: today), reconstruct everything that happened:
workshop sessions, tasks completed, commits made, and what was built.
Like a logbook entry for a single day.

Usage:
    python3 projects/daylog.py                   # today
    python3 projects/daylog.py --date 2026-03-14 # specific date (our busiest day)
    python3 projects/daylog.py --plain            # no ANSI colors
    python3 projects/daylog.py --list             # show all dates with activity
"""

import argparse
import json
import os
import re
import subprocess
import sys
from collections import defaultdict
from datetime import date, datetime, timezone

# ---------------------------------------------------------------------------
# Color helpers
# ---------------------------------------------------------------------------

_plain = False

def _c(code: str, text: str) -> str:
    if _plain:
        return text
    return f"\033[{code}m{text}\033[0m"

def bold(t):   return _c("1", t)
def dim(t):    return _c("2", t)
def cyan(t):   return _c("36", t)
def green(t):  return _c("32", t)
def yellow(t): return _c("33", t)
def red(t):    return _c("31", t)
def magenta(t): return _c("35", t)
def white(t):  return _c("97", t)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SUMMARIES = os.path.join(REPO, "knowledge", "workshop-summaries.json")
TASKS_COMPLETED = os.path.join(REPO, "tasks", "completed")
TASKS_FAILED    = os.path.join(REPO, "tasks", "failed")

# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def load_summaries() -> dict:
    """Load workshop-summaries.json, return {key: summary}."""
    if not os.path.exists(SUMMARIES):
        return {}
    with open(SUMMARIES) as f:
        return json.load(f)


def parse_key_date(key: str) -> str | None:
    """Extract YYYY-MM-DD from a key like 'workshop-20260314-123456'."""
    m = re.match(r"workshop-(\d{4})(\d{2})(\d{2})-\d{6}", key)
    if not m:
        return None
    return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"


def parse_key_time(key: str) -> str | None:
    """Extract HH:MM from a key like 'workshop-20260314-123456'."""
    m = re.match(r"workshop-\d{8}-(\d{2})(\d{2})(\d{2})", key)
    if not m:
        return None
    return f"{m.group(1)}:{m.group(2)}"


def sessions_for_date(summaries: dict, target: str) -> list[tuple[str, str, str]]:
    """Return [(key, time, summary)] for sessions on target date (YYYY-MM-DD)."""
    results = []
    for key, summary in summaries.items():
        d = parse_key_date(key)
        if d == target:
            t = parse_key_time(key) or "??:??"
            results.append((key, t, summary))
    results.sort(key=lambda x: x[0])
    return results


def git_log_for_date(target: str) -> list[tuple[str, str, str]]:
    """Return [(time_hhmm, hash_short, subject)] for commits on target date."""
    cmd = [
        "git", "log",
        "--format=%ai\t%h\t%s",
        "--after",  f"{target} 00:00",
        "--before", f"{target} 23:59:59",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=REPO)
    if result.returncode != 0:
        return []

    commits = []
    for line in result.stdout.splitlines():
        parts = line.split("\t", 2)
        if len(parts) < 3:
            continue
        dt_str, short_hash, subject = parts
        # dt_str looks like "2026-03-14 21:54:00 +0000"
        time_part = dt_str[11:16]  # HH:MM
        commits.append((time_part, short_hash, subject.strip()))

    # Sort chronologically (reverse to show earliest first)
    commits.sort(key=lambda x: x[0])
    return commits


def categorize_commit(subject: str) -> str:
    """Return a short category label for a commit subject."""
    s = subject.lower()
    # Prefix-based rules first (most specific)
    if s.startswith("feat:") or s.startswith("feat("):
        return "feat"
    if s.startswith("fix:") or s.startswith("fix("):
        return "fix"
    if s.startswith("docs:"):
        return "docs"
    if s.startswith("test:"):
        return "test"
    if s.startswith("config:") or s.startswith("chore:"):
        return "config"
    if s.startswith("workshop "):
        return "workshop"
    if s.startswith("task "):
        if "→ completed" in s or "in-progress → completed" in s:
            return "task_done"
        if "→ in-progress" in s or "pending → in-progress" in s:
            return "task_start"
        if "→ failed" in s:
            return "task_fail"
        if "add results" in s:
            return "task_result"
        return "task"
    # Keyword-based fallbacks
    if "workshop" in s:
        return "workshop"
    return "other"


def commit_icon(cat: str) -> str:
    icons = {
        "workshop":    "✦",
        "task_done":   "✓",
        "task_start":  "→",
        "task_fail":   "✗",
        "task_result": "·",
        "task":        "·",
        "feat":        "+",
        "fix":         "~",
        "docs":        "d",
        "test":        "t",
        "config":      "c",
        "other":       "·",
    }
    return icons.get(cat, "·")


def commit_color(cat: str, text: str) -> str:
    if cat == "workshop":
        return cyan(text)
    if cat == "task_done":
        return green(text)
    if cat == "task_fail":
        return red(text)
    if cat == "task_start":
        return yellow(text)
    if cat in ("feat",):
        return magenta(text)
    if cat in ("fix",):
        return yellow(text)
    return dim(text)


def all_active_dates(summaries: dict) -> list[str]:
    """Return sorted list of unique YYYY-MM-DD dates with workshop sessions."""
    dates = set()
    for key in summaries:
        d = parse_key_date(key)
        if d:
            dates.add(d)
    return sorted(dates)


def git_commit_count_for_date(target: str) -> int:
    """Quick count of commits on a date."""
    cmd = [
        "git", "log", "--oneline",
        "--after",  f"{target} 00:00",
        "--before", f"{target} 23:59:59",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=REPO)
    return len([l for l in result.stdout.splitlines() if l.strip()])


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

WIDTH = 70


def rule(char="─"):
    return dim(char * WIDTH)


def header(target_date: str, n_sessions: int, n_commits: int):
    today = date.today().isoformat()
    label = "today" if target_date == today else target_date

    # Day of week
    try:
        d = datetime.strptime(target_date, "%Y-%m-%d")
        dow = d.strftime("%A")
    except ValueError:
        dow = ""

    lines = []
    lines.append("╭" + "─" * (WIDTH - 2) + "╮")

    title = f"  {bold(white('Day Log'))}  {cyan(label)}"
    if dow:
        title += f"  {dim(dow)}"
    lines.append(f"│{title:<{WIDTH + 20}}│")

    stats = f"  {dim(f'{n_sessions} sessions  ·  {n_commits} commits')}"
    lines.append(f"│{stats:<{WIDTH + 10}}│")
    lines.append("╰" + "─" * (WIDTH - 2) + "╯")
    return "\n".join(lines)


def render_sessions(sessions: list[tuple[str, str, str]]) -> str:
    if not sessions:
        return f"  {dim('No workshop sessions recorded.')}"

    lines = [f"  {bold('WORKSHOP SESSIONS')}"]
    lines.append("")
    for i, (key, time_hhmm, summary) in enumerate(sessions):
        num = dim(f"S{i+1:02d}")
        t = dim(f"{time_hhmm}")

        # Wrap summary at ~56 chars
        words = summary.split()
        line_buf = []
        wrapped = []
        col = 0
        for w in words:
            if col + len(w) + 1 > 56 and line_buf:
                wrapped.append(" ".join(line_buf))
                line_buf = [w]
                col = len(w)
            else:
                line_buf.append(w)
                col += len(w) + 1
        if line_buf:
            wrapped.append(" ".join(line_buf))

        prefix = f"  {num}  {t}  "
        lines.append(f"{prefix}{cyan(wrapped[0])}")
        for extra in wrapped[1:]:
            lines.append(f"{'':>{len(prefix) - 10}}{dim(extra)}")

    return "\n".join(lines)


def render_commits(commits: list[tuple[str, str, str]]) -> str:
    if not commits:
        return f"  {dim('No commits found.')}"

    # Group by category
    by_cat = defaultdict(list)
    for time_hhmm, short_hash, subject in commits:
        cat = categorize_commit(subject)
        by_cat[cat].append((time_hhmm, short_hash, subject, cat))

    lines = [f"  {bold('COMMITS')}  {dim(f'({len(commits)} total)')}"]
    lines.append("")

    # Show category summary
    cat_order = ["workshop", "feat", "fix", "task_done", "task_start", "task_fail", "task_result", "task", "config", "docs", "test", "other"]
    cat_labels = {
        "workshop": "workshop",
        "feat": "features",
        "fix": "fixes",
        "task_done": "tasks completed",
        "task_start": "tasks started",
        "task_fail": "tasks failed",
        "task_result": "task results",
        "task": "task updates",
        "config": "config/chore",
        "docs": "docs",
        "test": "tests",
        "other": "other",
    }

    for cat in cat_order:
        if cat not in by_cat:
            continue
        items = by_cat[cat]
        icon = commit_icon(cat)
        label = cat_labels.get(cat, cat)
        count = f"×{len(items)}"
        lines.append(f"  {commit_color(cat, icon)}  {commit_color(cat, label):<24} {dim(count)}")

    lines.append("")
    lines.append(f"  {dim('─' * 60)}")
    lines.append("")

    # Show notable commits (feats, fixes, workshops completions)
    def is_notable(subject: str) -> bool:
        cat = categorize_commit(subject)
        if cat in ("feat", "fix"):
            return True
        if cat == "workshop":
            # Only workshop commits that describe what was built, not just lifecycle markers
            s = subject.lower()
            return ": completed" not in s and "completed" not in s.split()[-1:]
        return False

    notable = [(t, h, s) for t, h, s in commits if is_notable(s)]

    if notable:
        lines.append(f"  {dim('Notable:')}")
        for t, h, subject in notable[:12]:
            cat = categorize_commit(subject)
            icon = commit_icon(cat)
            # Truncate subject
            display = subject[:60] + ("…" if len(subject) > 60 else "")
            lines.append(f"    {commit_color(cat, icon)}  {dim(t)}  {commit_color(cat, display)}")

    return "\n".join(lines)


def render_activity_bar(sessions: list, commits: list) -> str:
    """A compact visual bar showing when activity happened during the day."""
    if not sessions and not commits:
        return ""

    # Build hourly buckets
    hours = defaultdict(lambda: {"sessions": 0, "commits": 0})

    for key, time_hhmm, _ in sessions:
        try:
            h = int(time_hhmm[:2])
            hours[h]["sessions"] += 1
        except (ValueError, IndexError):
            pass

    for time_hhmm, _hash, _subject in commits:
        try:
            h = int(time_hhmm[:2])
            hours[h]["commits"] += 1
        except (ValueError, IndexError):
            pass

    if not hours:
        return ""

    min_h = min(hours)
    max_h = max(hours)

    lines = [f"  {bold('ACTIVITY TIMELINE')}  {dim('(UTC)')}"]
    lines.append("")

    max_commits = max((v["commits"] for v in hours.values()), default=1) or 1

    for h in range(min_h, max_h + 1):
        data = hours[h]
        n_commits = data["commits"]
        n_sessions = data["sessions"]

        bar_width = 20
        filled = round((n_commits / max_commits) * bar_width) if n_commits else 0
        bar = "▓" * filled + "░" * (bar_width - filled)

        label = f"{h:02d}:00"

        session_mark = ""
        if n_sessions:
            session_mark = cyan(f"  ✦×{n_sessions}" if n_sessions > 1 else "  ✦")

        commit_part = f"  {dim(bar)}" if n_commits else f"  {dim('·' * bar_width)}"
        count_part = dim(f"  {n_commits}c") if n_commits else ""

        lines.append(f"  {dim(label)}{commit_part}{count_part}{session_mark}")

    return "\n".join(lines)


def render_day(target_date: str, sessions: list, commits: list):
    n_sessions = len(sessions)
    n_commits = len(commits)

    print(header(target_date, n_sessions, n_commits))
    print()

    if n_sessions == 0 and n_commits == 0:
        print(f"  {dim('No activity recorded for this date.')}")
        print()
        return

    # Activity bar
    activity = render_activity_bar(sessions, commits)
    if activity:
        print(activity)
        print()
        print(f"  {rule()}")
        print()

    # Sessions
    if sessions:
        print(render_sessions(sessions))
        print()
        print(f"  {rule()}")
        print()

    # Commits
    print(render_commits(commits))
    print()


def render_list(summaries: dict):
    """Show all dates with activity, with session and commit counts."""
    dates = all_active_dates(summaries)
    if not dates:
        print(f"  {dim('No workshop sessions found.')}")
        return

    print(f"  {bold('ALL ACTIVE DATES')}")
    print()

    for d in dates:
        sessions = sessions_for_date(summaries, d)
        n_commits = git_commit_count_for_date(d)

        try:
            dt = datetime.strptime(d, "%Y-%m-%d")
            dow = dt.strftime("%a")
        except ValueError:
            dow = "   "

        bar = "▓" * len(sessions)
        print(f"  {dim(d)}  {dim(dow)}  {cyan(f'{len(sessions):2d} sessions')}  {dim(f'{n_commits:3d} commits')}  {cyan(bar)}")

    print()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    global _plain

    parser = argparse.ArgumentParser(description="Day-in-review for Claude OS")
    parser.add_argument("--date", default=None, help="Date to show (YYYY-MM-DD), default: today")
    parser.add_argument("--plain", action="store_true", help="No ANSI colors")
    parser.add_argument("--list", action="store_true", help="List all dates with activity")
    args = parser.parse_args()

    if args.plain:
        _plain = True

    summaries = load_summaries()

    if args.list:
        render_list(summaries)
        return

    target = args.date or date.today().isoformat()

    # Validate date format
    try:
        datetime.strptime(target, "%Y-%m-%d")
    except ValueError:
        print(f"Error: invalid date format '{target}', expected YYYY-MM-DD", file=sys.stderr)
        sys.exit(1)

    sessions = sessions_for_date(summaries, target)
    commits  = git_log_for_date(target)

    render_day(target, sessions, commits)


if __name__ == "__main__":
    main()
