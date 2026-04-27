#!/usr/bin/env python3
"""
citations.py — which projects are actually talked about?

Scans all field notes and counts how often each project is cited.
High citation = part of the vocabulary, actually used and valued.
Low/zero citation = built and not mentioned again.

Usage:
  python3 projects/citations.py              # show all projects ranked by citation
  python3 projects/citations.py --top 10     # top 10 only
  python3 projects/citations.py --zero       # show uncited projects only
  python3 projects/citations.py --recent 5   # cited in the last 5 sessions
  python3 projects/citations.py --plain      # no ANSI colors
  python3 projects/citations.py --detail garden  # session-by-session for one project
"""

import os
import re
import sys
import argparse
from pathlib import Path
from collections import defaultdict


# ─── color helpers ──────────────────────────────────────────────────────────

def ansi(code: str, text: str, plain: bool) -> str:
    if plain:
        return text
    return f"\033[{code}m{text}\033[0m"

def bold(t, plain=False):   return ansi("1", t, plain)
def dim(t, plain=False):    return ansi("2", t, plain)
def cyan(t, plain=False):   return ansi("36", t, plain)
def green(t, plain=False):  return ansi("32", t, plain)
def yellow(t, plain=False): return ansi("33", t, plain)
def red(t, plain=False):    return ansi("31", t, plain)
def gray(t, plain=False):   return ansi("90", t, plain)


# ─── data loading ────────────────────────────────────────────────────────────

PROJECTS_DIR = Path(__file__).parent
REPO_ROOT = PROJECTS_DIR.parent


def get_projects() -> list[str]:
    """Return all .py filenames in projects/ (stems, no path)."""
    stems = []
    for p in sorted(PROJECTS_DIR.glob("*.py")):
        if p.name != "__pycache__":
            stems.append(p.stem)
    return stems


def _session_num_from_new_note(p: Path) -> int | None:
    """Extract session number from a new-format field note (knowledge/field-notes/)."""
    try:
        text = p.read_text()
    except Exception:
        return None
    # YAML frontmatter
    m = re.search(r"^session:\s*(\d+)", text[:400], re.MULTILINE)
    if m:
        return int(m.group(1))
    # *Session N ·...* or *Workshop session N ·...*
    m = re.search(r"\*(?:Workshop\s+)?[Ss]ession\s+(\d+)\s*[—–·:,]", text[:500])
    if m:
        return int(m.group(1))
    # # Session N: title
    m = re.search(r"^#\s+[Ss]ession\s+(\d+)", text[:200], re.MULTILINE)
    if m:
        return int(m.group(1))
    return None


def get_field_notes() -> list[tuple[int, Path]]:
    """Return (session_number, path) for all field notes, sorted by session.

    Reads from both projects/field-notes-*.md (old format, sessions 1-132)
    and knowledge/field-notes/*.md (new format, sessions 133+).
    """
    notes = []
    # Old format: session-numbered in filename
    for p in PROJECTS_DIR.glob("field-notes-session-*.md"):
        m = re.search(r"session-(\d+)", p.name)
        if m:
            notes.append((int(m.group(1)), p))
    # the original free-time note (session 1)
    free_time = PROJECTS_DIR / "field-notes-from-free-time.md"
    if free_time.exists():
        notes.append((1, free_time))

    # New format: knowledge/field-notes/*.md
    new_dir = REPO_ROOT / "knowledge" / "field-notes"
    if new_dir.exists():
        for p in new_dir.glob("*.md"):
            sn = _session_num_from_new_note(p)
            if sn is not None:
                notes.append((sn, p))

    notes.sort(key=lambda x: x[0])
    return notes


def count_citations(projects: list[str], notes: list[tuple[int, Path]]) -> dict:
    """
    For each project, return a dict of:
      - sessions: list of session numbers that mention it
      - total: total mention count across all sessions
      - first: first session that mentions it
      - last: last session that mentions it
    """
    data = {p: {"sessions": [], "total": 0, "mentions_by_session": {}} for p in projects}

    for session_num, note_path in notes:
        try:
            text = note_path.read_text()
        except Exception:
            continue

        for proj in projects:
            # look for project.py (with or without backticks, with or without path prefix)
            patterns = [
                rf"`{re.escape(proj)}\.py`",     # `name.py`
                rf"\b{re.escape(proj)}\.py\b",   # name.py (bare)
            ]
            count = 0
            for pat in patterns:
                count += len(re.findall(pat, text, re.IGNORECASE))

            if count > 0:
                data[proj]["sessions"].append(session_num)
                data[proj]["total"] += count
                data[proj]["mentions_by_session"][session_num] = count

    # compute first/last
    for proj in projects:
        sessions = data[proj]["sessions"]
        data[proj]["first"] = min(sessions) if sessions else None
        data[proj]["last"] = max(sessions) if sessions else None

    return data


# ─── display ─────────────────────────────────────────────────────────────────

def bar(count: int, max_count: int, width: int = 20, plain: bool = False) -> str:
    if max_count == 0:
        return " " * width
    filled = round(count / max_count * width)
    bar_str = "█" * filled + "░" * (width - filled)
    if plain:
        return bar_str
    if count == 0:
        return dim(bar_str, plain)
    elif count >= max_count * 0.7:
        return green(bar_str, plain)
    elif count >= max_count * 0.3:
        return yellow(bar_str, plain)
    else:
        return gray(bar_str, plain)


def format_session_list(sessions: list[int], plain: bool) -> str:
    if not sessions:
        return dim("(never)", plain)
    if len(sessions) == 1:
        return dim(f"S{sessions[0]}", plain)
    # show first, last, and indicate span
    first, last = sessions[0], sessions[-1]
    span = last - first
    count = len(sessions)
    if count == span + 1:
        # consecutive
        return dim(f"S{first}–S{last}", plain)
    return dim(f"S{first}..S{last} ({count} sessions)", plain)


def render_all(projects: list[str], data: dict, plain: bool,
               top: int = None, zero_only: bool = False):
    # sort by session count (breadth) then total mentions (depth)
    sorted_projects = sorted(
        projects,
        key=lambda p: (len(data[p]["sessions"]), data[p]["total"]),
        reverse=True
    )

    if zero_only:
        sorted_projects = [p for p in sorted_projects if len(data[p]["sessions"]) == 0]
    if top:
        sorted_projects = sorted_projects[:top]

    max_sessions = max((len(data[p]["sessions"]) for p in projects), default=1)
    max_sessions = max(max_sessions, 1)

    total_notes = max((s for s, _ in get_field_notes()), default=1)

    # header
    w = 62
    print()
    print("  " + bold("CITATION INDEX", plain) + "   " + dim("which projects get talked about?", plain))
    print("  " + dim("─" * w, plain))
    print()

    name_w = max(len(p) for p in sorted_projects) + 4 if sorted_projects else 20

    for proj in sorted_projects:
        d = data[proj]
        session_count = len(d["sessions"])
        total = d["total"]

        name_display = f"{proj}.py"

        # color the name by citation level
        if session_count == 0:
            name_str = dim(f"  {name_display:<{name_w}}", plain)
        elif session_count >= total_notes * 0.5:
            name_str = green(f"  {name_display:<{name_w}}", plain)
        elif session_count >= total_notes * 0.2:
            name_str = cyan(f"  {name_display:<{name_w}}", plain)
        else:
            name_str = f"  {dim(name_display, plain):<{name_w + 10}}"

        bar_str = bar(session_count, max_sessions, width=18, plain=plain)
        count_str = f"{session_count:>2}"
        total_str = dim(f"({total:>3} mentions)", plain)
        span_str = format_session_list(d["sessions"], plain)

        print(f"{name_str}  {bar_str}  {count_str}  {total_str}  {span_str}")

    print()
    print("  " + dim(f"Sessions scanned: {total_notes}   Projects tracked: {len(projects)}", plain))

    # summary stats
    cited = [p for p in projects if len(data[p]["sessions"]) > 0]
    never = [p for p in projects if len(data[p]["sessions"]) == 0]
    print()
    print("  " + bold("SUMMARY", plain))
    print(f"  {green(str(len(cited)), plain)} projects cited in at least one session")
    if never:
        print(f"  {dim(str(len(never)), plain)} projects never mentioned in field notes")
        print(f"  {dim('  → ' + ', '.join(never[:8]) + ('...' if len(never) > 8 else ''), plain)}")
    print()


def render_detail(proj: str, data: dict, notes: list[tuple[int, Path]], plain: bool):
    if proj not in data:
        print(f"  Unknown project: {proj}")
        return

    d = data[proj]

    print()
    print("  " + bold(f"{proj}.py", plain) + "   " + dim("session-by-session citation detail", plain))
    print("  " + dim("─" * 50, plain))
    print()

    if not d["sessions"]:
        print("  " + dim("Never cited in any field notes.", plain))
        print()
        return

    max_mentions = max(d["mentions_by_session"].values(), default=1)

    for session_num, note_path in notes:
        count = d["mentions_by_session"].get(session_num, 0)
        bar_str = bar(count, max(max_mentions, 1), width=12, plain=plain)
        session_label = f"S{session_num:>2}"
        if count > 0:
            count_str = cyan(f"{count}", plain)
            print(f"  {dim(session_label, plain)}  {bar_str}  {count_str} mention{'s' if count != 1 else ''}")
        else:
            print(f"  {dim(session_label, plain)}  {dim('░' * 12, plain)}  {dim('—', plain)}")

    print()
    print(f"  Total: {bold(str(d['total']), plain)} mentions across {bold(str(len(d['sessions'])), plain)} sessions")
    print(f"  First cited: S{d['first']}   Last cited: S{d['last']}")
    print()


# ─── main ────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Citation frequency for claude-os projects")
    parser.add_argument("--top", type=int, default=None, help="Show only top N projects")
    parser.add_argument("--zero", action="store_true", help="Show only uncited projects")
    parser.add_argument("--recent", type=int, default=None, metavar="N", help="Show only projects cited in the last N sessions")
    parser.add_argument("--plain", action="store_true", help="No ANSI colors")
    parser.add_argument("--detail", type=str, default=None, help="Show session-by-session detail for one project")
    args = parser.parse_args()

    # chdir to repo root so relative paths work
    os.chdir(REPO_ROOT)

    projects = get_projects()
    # exclude citations.py itself from the count (it's new)
    # and exclude non-tools
    exclude = {"citations"}  # this file; won't have citations in past sessions
    projects = [p for p in projects if p not in exclude]

    notes = get_field_notes()
    data = count_citations(projects, notes)

    plain = args.plain

    if args.detail:
        target = args.detail.replace(".py", "")
        render_detail(target, data, notes, plain)
    else:
        # handle --recent filter: keep only projects cited in last N sessions
        if args.recent:
            all_sessions = [s for s, _ in notes]
            max_session = max(all_sessions) if all_sessions else 0
            cutoff = max_session - args.recent + 1
            projects = [
                p for p in projects
                if any(s >= cutoff for s in data[p]["sessions"])
            ]
            if not projects:
                print(f"\n  No projects cited in the last {args.recent} sessions.\n")
                return
        render_all(projects, data, plain, top=args.top, zero_only=args.zero)


if __name__ == "__main__":
    main()
