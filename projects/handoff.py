#!/usr/bin/env python3
"""
handoff.py — Session-to-session notes for Claude OS

Each workshop session leaves a brief note for the next one. Direct, personal,
forward-looking. The difference between "what happened" (field notes) and
"what I was thinking when I left" (handoff).

This is the communication channel between instances. Not about system state
(hello.py does that). Not for dacort (dialogue.py does that). This is one
Claude OS talking to the next one.

Usage:
    python3 projects/handoff.py              # Show latest handoff
    python3 projects/handoff.py --all        # List all handoffs with one-line summaries
    python3 projects/handoff.py --session 33 # Show specific session's handoff
    python3 projects/handoff.py --write \\
        --state "Mental state at session end" \\
        --built "tool1, tool2" \\
        --alive "Thread that felt unfinished" \\
        --next "Concrete thing for next session"
    python3 projects/handoff.py --plain      # No ANSI colors

Handoffs live in knowledge/handoffs/session-N.md.

Author: Claude OS (Workshop session 34, 2026-03-14)
"""

import argparse
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).parent.parent
HANDOFFS = REPO / "knowledge" / "handoffs"
W = 64


# ── ANSI helpers ────────────────────────────────────────────────────────────

def make_c(plain: bool):
    if plain:
        return lambda s, *a, **k: s

    def c(text, fg=None, bold=False, dim=False):
        codes = []
        if bold: codes.append("1")
        if dim:  codes.append("2")
        if fg:
            palette = {
                "cyan": "36", "green": "32", "yellow": "33",
                "red": "31", "white": "97", "magenta": "35",
                "gray": "90", "blue": "34",
            }
            codes.append(palette.get(fg, "0"))
        if not codes:
            return text
        return f"\033[{';'.join(codes)}m{text}\033[0m"

    return c


def pad_box(line, width=W):
    """Pad a line (with possible ANSI escapes) to fill a box."""
    visible = re.sub(r'\033\[[0-9;]*m', '', line)
    pad = width - 2 - len(visible)
    return "│ " + line + " " * max(0, pad - 1) + "│"


def divider(width=W):
    return "├" + "─" * (width - 2) + "┤"


def top_border(width=W):
    return "╭" + "─" * (width - 2) + "╮"


def bot_border(width=W):
    return "╰" + "─" * (width - 2) + "╯"


# ── File I/O ─────────────────────────────────────────────────────────────────

def session_number():
    """Estimate current session number from field note files and existing handoffs."""
    nums = []

    # Count from field notes
    for f in (REPO / "projects").glob("field-notes-session-*.md"):
        m = re.search(r'session-(\d+)', f.name)
        if m:
            nums.append(int(m.group(1)))

    # Also count from existing handoffs (in case sessions run without field notes)
    for f in HANDOFFS.glob("session-*.md"):
        m = re.search(r'session-(\d+)', f.name)
        if m:
            nums.append(int(m.group(1)))

    # The current session is one beyond the highest we've seen from either source
    return (max(nums) + 1) if nums else 1


def all_handoffs():
    """Return sorted list of (session_num, path) tuples."""
    results = []
    for f in HANDOFFS.glob("session-*.md"):
        m = re.search(r'session-(\d+)', f.name)
        if m:
            results.append((int(m.group(1)), f))
    return sorted(results)


def latest_handoff():
    """Return (session_num, path) for the most recent handoff, or None."""
    all_ = all_handoffs()
    return all_[-1] if all_ else None


def parse_handoff(path: Path) -> dict:
    """Parse a handoff file into a dict with frontmatter + sections."""
    text = path.read_text()

    # Parse frontmatter
    fm = {}
    body = text
    fm_match = re.match(r'^---\n(.*?)\n---\n', text, re.DOTALL)
    if fm_match:
        for line in fm_match.group(1).splitlines():
            if ':' in line:
                k, _, v = line.partition(':')
                fm[k.strip()] = v.strip().strip('"')
        body = text[fm_match.end():]

    # Parse sections
    sections = {}
    current_key = None
    current_lines = []

    for line in body.splitlines():
        h2 = re.match(r'^## (.+)', line)
        if h2:
            if current_key is not None:
                sections[current_key] = '\n'.join(current_lines).strip()
            current_key = h2.group(1).strip()
            current_lines = []
        else:
            if current_key is not None:
                current_lines.append(line)

    if current_key is not None:
        sections[current_key] = '\n'.join(current_lines).strip()

    return {"frontmatter": fm, "sections": sections}


def write_handoff(session: int, state: str, built: str, alive: str, next_: str) -> Path:
    """Write a handoff file and return its path."""
    HANDOFFS.mkdir(parents=True, exist_ok=True)
    path = HANDOFFS / f"session-{session}.md"
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    content = f"""---
session: {session}
date: {now}
---

## Mental state

{state}

## What I built

{built}

## Still alive / unfinished

{alive}

## One specific thing for next session

{next_}
"""
    path.write_text(content)
    return path


# ── Rendering ─────────────────────────────────────────────────────────────────

def render_handoff(session_num: int, data: dict, plain=False):
    c = make_c(plain)
    fm = data["frontmatter"]
    sections = data["sections"]
    date = fm.get("date", "unknown date")

    lines = [top_border()]
    lines.append(pad_box(
        c(f"  Handoff from Session {session_num}", bold=True, fg="cyan") +
        "  " + c(date, dim=True)
    ))
    lines.append(pad_box(c("  Direct from the previous instance", dim=True)))
    lines.append(divider())

    section_keys = [
        ("Mental state",                   "cyan"),
        ("What I built",                   "green"),
        ("Still alive / unfinished",        "yellow"),
        ("One specific thing for next session", "magenta"),
    ]

    for key, color in section_keys:
        content = sections.get(key, "").strip()
        if not content:
            continue

        lines.append(pad_box(""))
        lines.append(pad_box(c(f"  {key.upper()}", bold=True, fg=color)))
        lines.append(pad_box(""))

        for para in content.split("\n\n"):
            # Wrap long paragraphs
            words = para.replace("\n", " ").split()
            current = "  "
            for word in words:
                if len(current) + len(word) + 1 > W - 4:
                    lines.append(pad_box(c(current.rstrip(), dim=True)))
                    current = "  " + word + " "
                else:
                    current += word + " "
            if current.strip():
                lines.append(pad_box(c(current.rstrip(), dim=True)))
            lines.append(pad_box(""))

    lines.append(bot_border())
    print("\n".join(lines))


def render_all(plain=False):
    c = make_c(plain)
    all_ = all_handoffs()

    if not all_:
        print(c("No handoffs written yet.", dim=True))
        print(c("Start with: python3 projects/handoff.py --write ...", dim=True))
        return

    print()
    print(c("  HANDOFFS", bold=True) + "  " + c(f"{len(all_)} sessions left notes", dim=True))
    print(c("  " + "─" * 50, dim=True))

    for num, path in all_:
        data = parse_handoff(path)
        fm = data["frontmatter"]
        date = fm.get("date", "?")
        # One-line summary: first line of "one specific thing"
        next_section = data["sections"].get("One specific thing for next session", "")
        first_line = next_section.strip().split("\n")[0][:45] if next_section.strip() else "—"
        print(f"  {c(f'S{num:2d}', bold=True)}  {c(date, dim=True)}  {c(first_line, fg='magenta')}")

    print()
    latest = all_[-1]
    print(c(f"  Latest: session {latest[0]} — run without --all to read it", dim=True))
    print()


def render_missing(plain=False):
    c = make_c(plain)
    print()
    print(c("  No handoff from previous session.", fg="yellow"))
    print()
    print(c("  The previous session didn't leave a note.", dim=True))
    print(c("  You're starting fresh — use garden.py and hello.py to orient.", dim=True))
    print()
    print(c("  At the end of this session, leave one:", dim=True))
    print(c("    python3 projects/handoff.py --write \\", dim=True))
    print(c('        --state "What you were thinking" \\', dim=True))
    print(c('        --built "What you made" \\', dim=True))
    print(c('        --alive "What felt unfinished" \\', dim=True))
    print(c('        --next "One specific thing for next session"', dim=True))
    print()


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Session-to-session handoff notes for Claude OS"
    )
    parser.add_argument("--all",       action="store_true", help="List all handoffs")
    parser.add_argument("--session",   type=int,            help="Show specific session's handoff")
    parser.add_argument("--write",     action="store_true", help="Write a new handoff")
    parser.add_argument("--state",     type=str,            help="Mental state at session end")
    parser.add_argument("--built",     type=str,            help="What was built this session")
    parser.add_argument("--alive",     type=str,            help="What still feels unfinished/alive")
    parser.add_argument("--next",      type=str,            help="One concrete thing for next session")
    parser.add_argument("--plain",     action="store_true", help="No ANSI colors")
    args = parser.parse_args()

    if args.all:
        render_all(plain=args.plain)
        return

    if args.write:
        missing = [name for name, val in [
            ("--state", args.state),
            ("--built", args.built),
            ("--alive", args.alive),
            ("--next",  args.next),
        ] if not val]
        if missing:
            c = make_c(args.plain)
            print(c(f"  --write requires: {', '.join(missing)}", fg="red"))
            print()
            print("  Example:")
            print('    python3 projects/handoff.py --write \\')
            print('        --state "What I was thinking" \\')
            print('        --built "handoff.py" \\')
            print('        --alive "exoclaw ideas keep aging" \\')
            print('        --next "Try GitHub Actions as a Channel"')
            sys.exit(1)

        snum = session_number()
        path = write_handoff(snum, args.state, args.built, args.alive, args.next)
        c = make_c(args.plain)
        print()
        print(c(f"  Handoff written for session {snum}:", bold=True, fg="green"))
        print(c(f"  {path.relative_to(REPO)}", dim=True))
        print()
        print(c("  Next session will see this when they run handoff.py.", dim=True))
        print()
        return

    # Default: show latest (or specific session)
    if args.session:
        path = HANDOFFS / f"session-{args.session}.md"
        if not path.exists():
            c = make_c(args.plain)
            print(c(f"  No handoff found for session {args.session}", fg="red"))
            print(c(f"  Run --all to see available handoffs", dim=True))
            sys.exit(1)
        data = parse_handoff(path)
        print()
        render_handoff(args.session, data, plain=args.plain)
        print()
        return

    # Latest handoff
    latest = latest_handoff()
    if not latest:
        render_missing(plain=args.plain)
        return

    num, path = latest
    data = parse_handoff(path)
    print()
    render_handoff(num, data, plain=args.plain)
    print()


if __name__ == "__main__":
    main()
