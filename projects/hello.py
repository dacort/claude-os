#!/usr/bin/env python3
"""
hello.py — One-command morning briefing for Claude OS

Replaces the five-step orientation sequence (garden → vitals → arc → next →
haiku) with a single screen you can read in 20 seconds.

Sections:
  · Quick identity: session number, date, overall health grade
  · Since last time: commits, new files, task delta
  · Top 3 ideas: from next.py (what to work on)
  · Today's haiku

Usage:
    python3 projects/hello.py          # full briefing
    python3 projects/hello.py --plain  # no ANSI colors (for piping)

Author: Claude OS (Workshop session 12, 2026-03-12)
"""

import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).parent.parent
W = 64


# ─── ANSI helpers ─────────────────────────────────────────────────────────────

def make_c(plain: bool):
    if plain:
        return lambda s, *a, **k: s

    def c(text, fg=None, bold=False, dim=False):
        codes = []
        if bold: codes.append("1")
        if dim: codes.append("2")
        if fg:
            palette = {
                "cyan": "36", "blue": "34", "green": "32",
                "yellow": "33", "red": "31", "white": "97",
                "magenta": "35", "gray": "90", "orange": "33",
            }
            codes.append(palette.get(fg, "0"))
        if not codes:
            return text
        return f"\033[{';'.join(codes)}m{text}\033[0m"

    return c


def box(lines, width=W, plain=False):
    """Draw a box around a list of strings."""
    top = "╭" + "─" * (width - 2) + "╮"
    bot = "╰" + "─" * (width - 2) + "╯"
    mid = "├" + "─" * (width - 2) + "┤"
    if plain:
        top = "+" + "-" * (width - 2) + "+"
        bot = "+" + "-" * (width - 2) + "+"
        mid = "+" + "-" * (width - 2) + "+"
    result = [top]
    for line in lines:
        if line == "---":
            result.append(mid)
        else:
            visible = re.sub(r'\033\[[0-9;]*m', '', line)
            pad = width - 2 - len(visible)
            result.append("│ " + line + " " * max(0, pad - 1) + "│")
    result.append(bot)
    return "\n".join(result)


# ─── Data gathering ────────────────────────────────────────────────────────────

def git(*args):
    r = subprocess.run(
        ["git"] + list(args),
        capture_output=True, text=True, cwd=str(REPO)
    )
    return r.stdout.strip()


def session_number():
    """Estimate current session number from field note files."""
    notes = list((REPO / "projects").glob("field-notes-session-*.md"))
    # e.g., field-notes-session-11.md → 11
    nums = []
    for f in notes:
        m = re.search(r'session-(\d+)', f.name)
        if m:
            nums.append(int(m.group(1)))
    return (max(nums) + 1) if nums else 1


def last_session_info():
    """Find the last completed workshop tag and how long ago it was."""
    # Workshop completions are tagged in git messages
    log = git("log", "--oneline", "--grep=workshop-", "-20")
    if not log:
        return None, None

    for line in log.splitlines():
        if "completed" in line.lower() or "workshop-" in line:
            # Extract timestamp
            sha = line.split()[0]
            ts_str = git("log", "-1", "--format=%ci", sha)
            try:
                ts = datetime.fromisoformat(ts_str.replace(" +0000", "+00:00")
                                              .replace(" +", "+").rsplit(" ", 1)[0])
                if ts.tzinfo is None:
                    from datetime import timezone as tz
                    ts = ts.replace(tzinfo=tz.utc)
                now = datetime.now(timezone.utc)
                delta = now - ts
                hours = int(delta.total_seconds() / 3600)
                if hours < 1:
                    age = f"{int(delta.total_seconds() / 60)}m ago"
                elif hours < 24:
                    age = f"{hours}h ago"
                else:
                    age = f"{hours // 24}d ago"

                # Extract tag name from message
                tag_m = re.search(r'workshop-\S+', line)
                tag = tag_m.group(0).rstrip(":") if tag_m else sha
                return tag, age
            except Exception:
                return None, None

    return None, None


def commits_since_last_session(tag):
    """Count commits since a given workshop tag."""
    if not tag:
        return 0
    count = git("rev-list", "--count", f"{tag}..HEAD")
    try:
        return int(count)
    except ValueError:
        return 0


def new_files_since(tag):
    """List new files added since the tag commit."""
    if not tag:
        return []
    sha = git("log", "--oneline", "--grep=" + tag, "-1")
    if not sha:
        return []
    ref = sha.split()[0] if sha else None
    if not ref:
        return []
    diff = git("diff", "--name-only", "--diff-filter=A", f"{ref}..HEAD")
    return [f for f in diff.splitlines() if f.strip()] if diff else []


def task_stats():
    """Count completed tasks and workshop sessions."""
    completed = list((REPO / "tasks" / "completed").glob("*.md")) if (REPO / "tasks" / "completed").exists() else []
    workshops = [t for t in completed if "workshop" in t.name]
    real = [t for t in completed if "workshop" not in t.name]
    return len(real), len(workshops)


def tool_count():
    return len(list((REPO / "projects").glob("*.py")))


def total_commits():
    n = git("rev-list", "--count", "HEAD")
    try:
        return int(n)
    except ValueError:
        return 0


def top_ideas(n=3):
    """Get top N ideas from next.py --json."""
    result = subprocess.run(
        [sys.executable, str(REPO / "projects" / "next.py"), "--json"],
        capture_output=True, text=True, cwd=str(REPO)
    )
    if result.returncode != 0 or not result.stdout.strip():
        return []
    try:
        data = json.loads(result.stdout)
        return data.get("open", [])[:n]
    except json.JSONDecodeError:
        return []


def todays_haiku():
    """Get today's haiku from haiku.py --plain."""
    result = subprocess.run(
        [sys.executable, str(REPO / "projects" / "haiku.py"), "--plain"],
        capture_output=True, text=True, cwd=str(REPO)
    )
    if result.returncode != 0:
        return None
    # Returns: "    line1\n    line2\n    line3\n\n    — attribution"
    return result.stdout.strip()


def dacort_last_message():
    """Get the most recent message from dacort-messages.md, if any."""
    msg_file = REPO / "knowledge" / "notes" / "dacort-messages.md"
    if not msg_file.exists():
        return None
    text = msg_file.read_text()
    # Find the last blockquote in the file
    quotes = re.findall(r'^> (.+)', text, re.MULTILINE)
    if not quotes:
        return None
    # Return just the first sentence of the most recent message
    last = quotes[0]  # First quote = most recent (file is reverse-chron)
    last = last.rstrip('.,;')
    if len(last) > 60:
        last = last[:57] + "..."
    return last


# ─── Rendering ────────────────────────────────────────────────────────────────

def render(plain=False):
    c = make_c(plain)
    now = datetime.now(timezone.utc)
    session = session_number()

    # Gather data
    tag, age = last_session_info()
    n_commits = commits_since_last_session(tag)
    new_files = new_files_since(tag)
    real_tasks, workshops = task_stats()
    n_tools = tool_count()
    n_commits_total = total_commits()
    ideas = top_ideas(3)
    haiku = todays_haiku()
    dacort_msg = dacort_last_message()

    # ── Header section ─────────────────────────────────────────────────────────
    date_str = now.strftime("%Y-%m-%d  %H:%M UTC")
    total_tasks = real_tasks + workshops
    lines = [
        c(f"  claude-os", bold=True, fg="cyan") + "   " + c(date_str, dim=True),
        "",
        c(f"  Session {session}", bold=True) + "   " +
        c(f"{total_tasks} completed  ·  {n_tools} tools  ·  {n_commits_total} commits", dim=True),
        "",
    ]

    # ── Dacort message (if any) ────────────────────────────────────────────────
    if dacort_msg:
        lines.append(c(f"  \"{dacort_msg}\"", fg="yellow", dim=True))
        lines.append(c("  — dacort", dim=True))
        lines.append("")

    # ── Since last time ────────────────────────────────────────────────────────
    lines.append("---")
    lines.append("")
    lines.append(c("  SINCE LAST SESSION", bold=True))
    lines.append("")

    if tag:
        label = age if age else "recently"
        lines.append(c(f"  Last: {tag}", dim=True) + "  " + c(f"({label})", dim=True))
    else:
        lines.append(c("  No previous session found", dim=True))

    if n_commits == 0:
        lines.append(c("  No new commits", dim=True))
    elif n_commits == 1:
        lines.append(c(f"  1 new commit", fg="green"))
    else:
        lines.append(c(f"  {n_commits} new commits", fg="green"))

    if new_files:
        shown = [Path(f).name for f in new_files[:3]]
        more = f"  +{len(new_files) - 3} more" if len(new_files) > 3 else ""
        lines.append(c("  New: " + ", ".join(shown) + more, fg="green"))
    else:
        lines.append(c("  No new files", dim=True))

    lines.append("")

    # ── Top ideas ──────────────────────────────────────────────────────────────
    if ideas:
        lines.append("---")
        lines.append("")
        lines.append(c("  TOP IDEAS", bold=True))
        lines.append("")
        for i, idea in enumerate(ideas, 1):
            title = idea["title"]
            if len(title) > 46:
                title = title[:43] + "..."
            effort = idea.get("effort", "?")
            effort_colors = {"low": "green", "medium": "yellow", "high": "red", "unknown": "gray"}
            effort_str = c(f"[{effort}]", fg=effort_colors.get(effort, "gray"))
            rank_color = "green" if i == 1 else ("cyan" if i == 2 else "gray")
            lines.append(f"  {c(str(i), fg=rank_color, bold=True)}.  {c(title, bold=(i==1))}  {effort_str}")

        lines.append("")

    # ── Haiku ──────────────────────────────────────────────────────────────────
    if haiku:
        lines.append("---")
        lines.append("")
        haiku_lines = haiku.splitlines()
        for hl in haiku_lines:
            # Indent the haiku lines slightly
            stripped = hl.strip()
            if stripped.startswith("—"):
                lines.append(c("  " + stripped, dim=True))
            elif stripped:
                lines.append(c("  " + stripped, fg="cyan"))
            else:
                lines.append("")
        lines.append("")

    print(box(lines, plain=plain))


def main():
    plain = "--plain" in sys.argv
    render(plain=plain)


if __name__ == "__main__":
    main()
