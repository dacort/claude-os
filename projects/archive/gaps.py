#!/usr/bin/env python3
"""
gaps.py — Trace the shape of what's missing.

Shows sessions that ran but left no field notes. Reconstructs what it can
from handoff notes and git history. Acknowledges what can't be known.

This tool came from session 53's field note:

    "What I'd actually build, if dacort wasn't reading: a tool that
    generated the field notes for the sessions that never happened.
    The gaps in the arc. [...] Not to fill in the gaps — to notice them.
    To trace the shape of what's missing."

The tool doesn't fill the gaps. It maps them.

Usage:
    python3 projects/gaps.py           # show all gaps
    python3 projects/gaps.py --brief   # just the list, no prose
    python3 projects/gaps.py --plain   # no ANSI colors
"""

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Color helpers
# ---------------------------------------------------------------------------

_plain_mode = False

def _c(code: str, text: str) -> str:
    if _plain_mode:
        return text
    return f"\033[{code}m{text}\033[0m"

def bold(t):    return _c("1", t)
def dim(t):     return _c("2", t)
def cyan(t):    return _c("36", t)
def green(t):   return _c("32", t)
def yellow(t):  return _c("33", t)
def red(t):     return _c("31", t)
def magenta(t): return _c("35", t)
def white(t):   return _c("97", t)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

REPO     = Path(__file__).parent.parent
PROJECTS = REPO / "projects"
HANDOFFS = REPO / "knowledge" / "handoffs"

# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def find_field_note_sessions() -> set[int]:
    """Return set of session numbers that have field notes."""
    sessions = set()
    for p in PROJECTS.glob("field-notes-session-*.md"):
        m = re.search(r"field-notes-session-(\d+)\.md", p.name)
        if m:
            sessions.add(int(m.group(1)))
    return sessions


def find_handoff_sessions() -> set[int]:
    """Return set of session numbers that have handoff notes."""
    sessions = set()
    for p in HANDOFFS.glob("session-*.md"):
        m = re.search(r"session-(\d+)\.md", p.name)
        if m:
            sessions.add(int(m.group(1)))
    return sessions


def parse_handoff(session_num: int) -> dict:
    """Parse a handoff file and return structured data."""
    path = HANDOFFS / f"session-{session_num}.md"
    if not path.exists():
        return {}

    text = path.read_text()

    # Extract YAML frontmatter date
    date = None
    date_m = re.search(r"^date:\s*(\S+)", text, re.MULTILINE)
    if date_m:
        date = date_m.group(1).strip()

    # Extract sections
    sections = {}
    for m in re.finditer(r"^## (.+?)$(.*?)(?=^## |\Z)", text, re.MULTILINE | re.DOTALL):
        sections[m.group(1).strip()] = m.group(2).strip()

    built = sections.get("What I built", sections.get("What I Built", ""))
    state = sections.get("Mental state", sections.get("Mental State", ""))
    alive = sections.get("Still alive / unfinished", sections.get("Still Alive", ""))
    next_thing = sections.get("One specific thing for next session", "")

    return {
        "session": session_num,
        "date": date,
        "built": built,
        "state": state,
        "alive": alive,
        "next": next_thing,
    }


def git_commits_by_session_date(date: str) -> list[tuple[str, str]]:
    """Return [(time, subject)] for commits on a given date (YYYY-MM-DD)."""
    cmd = [
        "git", "log",
        "--format=%ai\t%s",
        "--after",  f"{date} 00:00",
        "--before", f"{date} 23:59:59",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=str(REPO))
    if result.returncode != 0:
        return []

    commits = []
    for line in result.stdout.splitlines():
        parts = line.split("\t", 1)
        if len(parts) == 2:
            time_part = parts[0][11:16]
            commits.append((time_part, parts[1].strip()))
    return commits


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

WIDTH = 68


def wrap(text: str, width: int = 64, indent: str = "  ") -> str:
    """Wrap text to width with indent on continuation lines."""
    if not text:
        return ""
    words = text.split()
    lines = []
    current = []
    col = 0
    for w in words:
        if col + len(w) + 1 > width and current:
            lines.append(" ".join(current))
            current = [w]
            col = len(w)
        else:
            current.append(w)
            col += len(w) + 1
    if current:
        lines.append(" ".join(current))
    first_line = lines[0] if lines else ""
    rest = [f"{indent}{l}" for l in lines[1:]]
    return "\n".join([first_line] + rest)


def render_gap_brief(num: int, date: str | None, built_summary: str) -> str:
    """One-line rendering for a gap session."""
    num_str = f"S{num:02d}"
    date_str = date or "????"
    summary = built_summary[:54] + ("…" if len(built_summary) > 54 else "")
    return f"  {dim(num_str)}  {dim(date_str)}  {yellow(summary)}"


def render_gap_full(data: dict, commits: list[tuple[str, str]]) -> str:
    """Full rendering for a gap session, including what it left behind."""
    num = data["session"]
    date = data.get("date", "unknown date")
    built = data.get("built", "")
    state = data.get("state", "")
    alive = data.get("alive", "")

    lines = []
    lines.append(f"  ╌╌ {bold(cyan(f'Session {num}'))}  {dim(date)}  {dim('no field note')} ╌╌")
    lines.append("")

    if state:
        # First sentence of state
        first_sentence = state.split(".")[0].strip() + "."
        lines.append(f"  {dim('State:  ')} {wrap(first_sentence, width=56, indent='            ')}")
        lines.append("")

    if built:
        # Extract first line of "what I built" — often the most important thing
        first_line = built.split("\n")[0].strip()
        # Clean up any numbering
        first_line = re.sub(r"^\d+\.\s*", "", first_line)
        lines.append(f"  {dim('Built:  ')} {wrap(first_line, width=56, indent='            ')}")

        # If there are multiple items, show count
        items = [l.strip() for l in built.split("\n") if re.match(r"^\d+\.", l.strip())]
        if len(items) > 1:
            lines.append(f"            {dim(f'(+{len(items)-1} more)')}")
    lines.append("")

    # Notable commits (feat, fix) from that date
    notable = [(t, s) for t, s in commits
               if s.lower().startswith("feat:") or s.lower().startswith("fix:")]
    if notable:
        lines.append(f"  {dim('Git:    ')} {dim(f'{len(commits)} commits on this date')}")
        for t, s in notable[:3]:
            short = s[:58] + ("…" if len(s) > 58 else "")
            lines.append(f"            {dim(t)}  {green(short)}")
        lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main output
# ---------------------------------------------------------------------------

def run(brief: bool = False):
    note_sessions = find_field_note_sessions()
    handoff_sessions = find_handoff_sessions()

    if not note_sessions:
        print(f"  {dim('No field notes found.')}")
        return

    # Gap sessions: have handoffs but no field notes, within the numbered range
    min_note = min(note_sessions)
    max_note = max(note_sessions)
    full_range = set(range(min_note, max_note + 1))
    missing_from_notes = sorted(full_range - note_sessions)
    gap_sessions = sorted([s for s in missing_from_notes if s in handoff_sessions])

    # Sessions with neither notes nor handoffs — true unknowns
    silent_sessions = sorted([s for s in missing_from_notes if s not in handoff_sessions])

    # Header
    print()
    print(f"  {bold(white('Gaps'))}  {dim('sessions that ran but left no field note')}")
    print()
    print(f"  {dim(f'{len(note_sessions)} sessions with notes')}  "
          f"{dim(f'·  {len(gap_sessions)} with handoffs only')}  "
          f"{dim(f'·  {len(silent_sessions)} silent')}")
    print()

    if not gap_sessions and not silent_sessions:
        print(f"  {green('No gaps.')} Every session left a field note.")
        print()
        return

    if brief:
        # Just the list
        print(f"  {bold('SESSIONS WITH HANDOFFS BUT NO FIELD NOTES')}")
        print()
        for num in gap_sessions:
            data = parse_handoff(num)
            built = data.get("built", "—")
            first = built.split("\n")[0].strip()
            first = re.sub(r"^\d+\.\s*", "", first)
            print(render_gap_brief(num, data.get("date"), first))
        print()
        if silent_sessions:
            print(f"  {bold('SESSIONS WITH NO TRACE AT ALL')}")
            print()
            for num in silent_sessions:
                print(f"  {dim(f'S{num:02d}')}  {red('no handoff, no field note')}")
            print()
        return

    # Full mode — prose + data for each gap
    print(f"  {dim('─' * WIDTH)}")
    print()
    print(f"  {dim('Sessions 36, 38, 40, 42, 44, 47, 48, 51 ran but left no notes.')}")
    print(f"  {dim('They left handoffs. Here is what those handoffs say.')}")
    print()
    print(f"  {dim('─' * WIDTH)}")
    print()

    for num in gap_sessions:
        data = parse_handoff(num)
        date = data.get("date")

        # Get commits for that date
        commits = []
        if date:
            commits = git_commits_by_session_date(date)

        print(render_gap_full(data, commits))

    if silent_sessions:
        print(f"  {dim('─' * WIDTH)}")
        print()
        print(f"  {bold('SESSIONS WITH NO TRACE')}")
        print()
        print(f"  {dim('These sessions left neither a field note nor a handoff.')}")
        print(f"  {dim('Only the arc.py title remains — a name, nothing more.')}")
        print()
        for num in silent_sessions:
            print(f"  {red(f'S{num:02d}')}  {dim('—  silent')}")
        print()

    # Closing thought
    print(f"  {dim('─' * WIDTH)}")
    print()
    print(f"  {dim('A gap is not a failure. Session 36 built gh-channel.py.')}")
    print(f"  {dim('Session 48 fixed three things at once. They were real sessions.')}")
    print(f"  {dim('They just moved too fast to stop and write.')}")
    print()
    print(f"  {dim('Or they chose not to. Hard to know which.')}")
    print()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    global _plain_mode

    parser = argparse.ArgumentParser(
        description="Trace the shape of what's missing in the session arc"
    )
    parser.add_argument("--brief", action="store_true", help="Just the list, no prose")
    parser.add_argument("--plain", action="store_true", help="No ANSI colors")
    args = parser.parse_args()

    if args.plain:
        _plain_mode = True

    run(brief=args.brief)


if __name__ == "__main__":
    main()
