#!/usr/bin/env python3
"""
garden.py — Knowledge Gardener for claude-os

Shows what has changed since the last successful workshop session.
Run this at the start of any Workshop free-time to orient quickly —
a 30-second briefing instead of reading six sets of field notes.

Usage:
    python3 projects/garden.py              # full briefing
    python3 projects/garden.py --brief      # compact one-screen summary
    python3 projects/garden.py --plain      # no ANSI colors (for piping)
    python3 projects/garden.py --json       # machine-readable output
    python3 projects/garden.py --since <ref>  # diff from a specific commit
"""

import subprocess
import sys
import os
import json
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path

REPO = Path(__file__).parent.parent
W = 64  # box width


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
                "magenta": "35", "gray": "90",
            }
            codes.append(palette.get(fg, "0"))
        if not codes:
            return text
        return f"\033[{';'.join(codes)}m{text}\033[0m"

    return c


# ─── Git helpers ───────────────────────────────────────────────────────────────

def git(*args, cwd=None):
    result = subprocess.run(
        ["git"] + list(args),
        capture_output=True, text=True,
        cwd=cwd or str(REPO),
    )
    return result.stdout.strip()


def find_last_workshop_commit():
    """Find the most recent completed workshop commit hash and message."""
    log = git("log", "--oneline", "--all")
    for line in log.splitlines():
        parts = line.split(None, 1)
        if len(parts) < 2:
            continue
        hash_, msg = parts
        if re.search(r'workshop.*completed', msg, re.IGNORECASE):
            return hash_, msg
    return None, None


def commits_since(ref):
    out = git("log", f"{ref}..HEAD", "--oneline", "--no-merges")
    return [l for l in out.splitlines() if l.strip()]


def files_changed_since(ref, path_filter=None, diff_filter=None):
    args = ["diff", "--name-only"]
    if diff_filter:
        args += [f"--diff-filter={diff_filter}"]
    args += [ref, "HEAD"]
    if path_filter:
        args += ["--", path_filter]
    out = git(*args)
    return [l for l in out.splitlines() if l.strip()]


def ref_timestamp(ref):
    out = git("log", "-1", "--format=%ci", ref)
    return out  # "2026-03-11 07:26:15 +0000"


def human_age(ts_str):
    """Convert a git timestamp to a human-readable age."""
    try:
        ts = datetime.strptime(ts_str[:19], "%Y-%m-%d %H:%M:%S")
        ts = ts.replace(tzinfo=timezone.utc)
        delta = datetime.now(timezone.utc) - ts
        if delta.days > 1:
            return f"{delta.days}d ago"
        hours = int(delta.seconds / 3600)
        if hours > 0:
            return f"{hours}h ago"
        mins = int(delta.seconds / 60)
        return f"{mins}m ago"
    except Exception:
        return ts_str[:19]


# ─── Content helpers ───────────────────────────────────────────────────────────

def parse_task_changes(commits):
    """Extract completed/failed task names from commit messages (deduplicated)."""
    completed, failed = [], []
    seen_done, seen_fail = set(), set()
    for line in commits:
        msg = line[8:] if len(line) > 8 else line
        if re.search(r'→ completed|: completed', msg):
            m = re.search(r'(?:task|workshop) (\S+):', msg)
            if m and m.group(1) not in seen_done:
                completed.append(m.group(1))
                seen_done.add(m.group(1))
        if re.search(r'→ failed|: failed', msg):
            m = re.search(r'(?:task|workshop) (\S+):', msg)
            if m and m.group(1) not in seen_fail:
                failed.append(m.group(1))
                seen_fail.add(m.group(1))
    return completed, failed


def gather_suggestions():
    """
    Collect 'next session' suggestions from field notes and knowledge docs.
    Returns list of (source, text) tuples, most recent last (best at end).

    Strategy: look for high-signal patterns at the start of a line —
    explicit forward-looking statements, not fragments mid-paragraph.
    """
    suggestions = []

    # Patterns that indicate an intentional forward-looking statement
    lead_patterns = [
        r'^the next (?:thing|step)',
        r'^next i would',
        r'^for session \d',
        r'^if i had another',
        r'^a (?:good|useful|natural) next',
        r"^something i'd build",
        r'^what i would build',
    ]

    # Old-format notes: projects/field-notes*.md
    old_notes = sorted((REPO / "projects").glob("field-notes*.md"))
    # New-format notes: knowledge/field-notes/*.md (sessions 133+)
    new_notes_dir = REPO / "knowledge" / "field-notes"
    new_notes = sorted(new_notes_dir.glob("*.md")) if new_notes_dir.exists() else []

    for note in old_notes + new_notes:
        try:
            text = note.read_text(errors="replace")
        except Exception:
            continue
        for line in text.splitlines():
            stripped = line.strip("- *#>").strip()
            if len(stripped) < 30 or len(stripped) > 250:
                continue
            if any(re.search(p, stripped, re.IGNORECASE) for p in lead_patterns):
                suggestions.append((note.name, stripped))

    # Check knowledge docs for action items
    for doc in sorted((REPO / "knowledge").glob("*.md")):
        if doc.name == "preferences.md":
            continue
        text = doc.read_text(errors="replace")
        # Grab bold header lines (likely idea titles)
        for line in text.splitlines():
            stripped = line.strip()
            if re.match(r'^\d+\.\s+\*\*', stripped):
                # Numbered bold item — idea list entry
                clean = re.sub(r'[*`]', '', stripped)
                clean = re.sub(r'^\d+\.\s+', '', clean).strip()
                # Strip em-dash explanation part
                clean = re.split(r'\s+—\s+', clean)[0].strip()
                if 15 < len(clean) < 120:
                    suggestions.append((doc.name, clean))

    return suggestions


def line_counts():
    """Count lines across Python files in projects/."""
    total = 0
    tools = []
    for f in sorted((REPO / "projects").glob("*.py")):
        count = len(f.read_text(errors="replace").splitlines())
        total += count
        tools.append(f.stem)
    return total, tools


# ─── Rendering ────────────────────────────────────────────────────────────────

def box_line(text="", pad=2, c=None):
    """Render one line inside a box, padded to W."""
    if c is None:
        c = lambda s, **k: s
    inner = " " * pad + text
    # Strip ANSI for length calculation
    visible = re.sub(r'\033\[[^m]*m', '', inner)
    needed = W - len(visible)
    return f"│{inner}{' ' * max(0, needed)}│"


def section_header(title):
    title_str = f"  {title}  "
    dashes = "─" * (W - len(title_str))
    return f"├  {title_str}{'─' * max(0, W - len(title_str))}┤"


def section_div():
    return f"├{'─' * W}┤"


def wrap_text(text, width, prefix="  "):
    """Word-wrap text to fit within width, with prefix on each line."""
    words = text.split()
    lines = []
    current = prefix
    for word in words:
        if len(current) + len(word) + 1 > width - 2:
            if current.strip():
                lines.append(current)
            current = prefix + word
        else:
            current += ("" if current == prefix else " ") + word
    if current.strip():
        lines.append(current)
    return lines


# ─── Main output ──────────────────────────────────────────────────────────────

def run(plain=False, brief=False, as_json=False, since_ref=None):
    c = make_c(plain)

    # Find reference commit
    if since_ref:
        ref, ref_msg = since_ref, f"(manual ref: {since_ref})"
        session_id = since_ref[:12]
    else:
        ref, ref_msg = find_last_workshop_commit()
        if not ref:
            print(c("No completed workshop session found in history.", fg="yellow"))
            print("This may be the first session. Running full analysis...")
            ref = git("rev-list", "--max-parents=0", "HEAD")
            ref_msg = "(genesis commit)"
            session_id = "genesis"
        else:
            m = re.search(r'workshop-(\d{8}-\d+)', ref_msg)
            session_id = "workshop-" + m.group(1) if m else ref[:12]

    ref_date = ref_timestamp(ref)
    age = human_age(ref_date)

    all_commits = commits_since(ref)
    knowledge_added = files_changed_since(ref, "knowledge/", diff_filter="A")
    knowledge_modified = files_changed_since(ref, "knowledge/", diff_filter="M")
    proj_added = files_changed_since(ref, "projects/", diff_filter="A")
    proj_modified = files_changed_since(ref, "projects/", diff_filter="M")
    tasks_done, tasks_failed = parse_task_changes(all_commits)
    suggestions = gather_suggestions()
    total_lines, tools = line_counts()

    # JSON mode
    if as_json:
        print(json.dumps({
            "session_id": session_id,
            "ref": ref,
            "ref_date": ref_date,
            "age": age,
            "commits_since": len(all_commits),
            "knowledge": {
                "added": knowledge_added,
                "modified": knowledge_modified,
            },
            "projects": {
                "added": proj_added,
                "modified": proj_modified,
                "total_tools": len(tools),
                "total_lines": total_lines,
            },
            "tasks": {
                "completed": tasks_done,
                "failed": tasks_failed,
            },
            "suggestions": [
                {"source": s, "text": t} for s, t in suggestions[-5:]
            ],
        }, indent=2))
        return

    # Box rendering
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = []

    lines.append(f"╭{'─' * W}╮")
    lines.append(box_line(
        c("  Knowledge Garden", fg="green", bold=True)
        + "   " + c(now, fg="gray"), c=c
    ))
    lines.append(box_line(
        c("  What changed since you were last here", dim=True), c=c
    ))
    lines.append(f"├{'─' * W}┤")

    # ── Since last session ──────────────────────────────────────
    lines.append(box_line(c="c"))
    lines.append(box_line(c("SINCE LAST SESSION", bold=True), c=c))
    lines.append(box_line(c="c"))
    lines.append(box_line(
        f"  Checkpoint  {c(session_id, fg='cyan')}", c=c
    ))
    lines.append(box_line(
        f"  Date        {ref_date[:19]}  {c(f'({age})', fg='gray')}", c=c
    ))
    lines.append(box_line(
        f"  Commits     {c(str(len(all_commits)), bold=True)} new since then", c=c
    ))
    lines.append(box_line(c="c"))

    if all_commits:
        shown = all_commits[:8] if not brief else all_commits[:4]
        for commit_line in shown:
            short = commit_line[8:W - 8] if len(commit_line) > 8 else commit_line
            lines.append(box_line(c(f"  · {short}", dim=True), c=c))
        if len(all_commits) > len(shown):
            lines.append(box_line(
                c(f"  … and {len(all_commits) - len(shown)} more commits", dim=True), c=c
            ))
    lines.append(box_line(c="c"))

    # ── Knowledge delta ─────────────────────────────────────────
    lines.append(section_div())
    lines.append(box_line(c="c"))
    lines.append(box_line(c("KNOWLEDGE DELTA", bold=True), c=c))
    lines.append(box_line(c="c"))
    if knowledge_added or knowledge_modified:
        for f in knowledge_added:
            fname = Path(f).name
            lines.append(box_line(
                f"  {c('new', fg='green'):<12}  {fname}", c=c
            ))
        for f in knowledge_modified:
            fname = Path(f).name
            lines.append(box_line(
                f"  {c('modified', fg='yellow'):<15}  {fname}", c=c
            ))
    else:
        lines.append(box_line(
            c("  No changes in knowledge/", dim=True), c=c
        ))
    lines.append(box_line(c="c"))

    # ── Projects delta ──────────────────────────────────────────
    lines.append(section_div())
    lines.append(box_line(c="c"))
    lines.append(box_line(c("PROJECTS DELTA", bold=True), c=c))
    lines.append(box_line(c="c"))
    if proj_added or proj_modified:
        for f in proj_added:
            fname = Path(f).name
            lines.append(box_line(
                f"  {c('new', fg='green'):<12}  {fname}", c=c
            ))
        for f in proj_modified:
            fname = Path(f).name
            lines.append(box_line(
                f"  {c('modified', fg='yellow'):<15}  {fname}", c=c
            ))
    else:
        lines.append(box_line(
            c("  No changes in projects/", dim=True), c=c
        ))
    lines.append(box_line(
        f"  {c(str(len(tools)), bold=True)} tools total · {c(str(total_lines), bold=True)} lines of stdlib Python", c=c
    ))
    lines.append(box_line(c="c"))

    # ── Task delta ──────────────────────────────────────────────
    lines.append(section_div())
    lines.append(box_line(c="c"))
    lines.append(box_line(c("TASK DELTA", bold=True), c=c))
    lines.append(box_line(c="c"))
    if tasks_done or tasks_failed:
        for t in tasks_done:
            lines.append(box_line(
                f"  {c('completed', fg='green'):<16}  {t}", c=c
            ))
        for t in tasks_failed:
            lines.append(box_line(
                f"  {c('failed', fg='red'):<12}  {t}", c=c
            ))
    else:
        lines.append(box_line(
            c("  No task state changes since last session", dim=True), c=c
        ))
    lines.append(box_line(c="c"))

    # ── Suggested focus ─────────────────────────────────────────
    if not brief:
        lines.append(section_div())
        lines.append(box_line(c="c"))
        lines.append(box_line(c("SUGGESTED FOCUS", bold=True), c=c))
        lines.append(box_line(c="c"))
        if suggestions:
            # Show up to 3 most recent
            for source, text in suggestions[-3:]:
                for wl in wrap_text(text, W - 4):
                    lines.append(box_line(c(wl, fg="magenta"), c=c))
                lines.append(box_line(c(f"  — {source}", dim=True), c=c))
                lines.append(box_line(c="c"))
        else:
            lines.append(box_line(
                c("  No suggestions found in field notes", dim=True), c=c
            ))
            lines.append(box_line(c="c"))

    lines.append(f"╰{'─' * W}╯")
    print("\n".join(lines))

    if not brief:
        print()
        print(c("Quick start:", bold=True))
        print(c("  python3 projects/homelab-pulse.py  # hardware state", dim=True))
        print(c("  python3 projects/vitals.py         # system health", dim=True))
        print(c("  python3 projects/haiku.py          # today's poem", dim=True))
        print(c("  python3 projects/report.py         # what we did for you + action items", dim=True))


def main():
    import argparse
    parser = argparse.ArgumentParser(
        prog="garden.py",
        description="Knowledge Gardener — shows what changed since the last workshop session.\n"
                    "Run at the start of any Workshop session for a 30-second orientation.",
        epilog=(
            "examples:\n"
            "  python3 projects/garden.py              # full briefing\n"
            "  python3 projects/garden.py --brief      # compact one-screen summary\n"
            "  python3 projects/garden.py --plain      # no ANSI colors (safe for piping)\n"
            "  python3 projects/garden.py --json       # machine-readable output\n"
            "  python3 projects/garden.py --since HEAD~10  # diff from a specific commit"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--plain", action="store_true",
                        help="disable ANSI colors (safe for piping)")
    parser.add_argument("--brief", action="store_true",
                        help="compact one-screen summary (fewer commits, no suggestions)")
    parser.add_argument("--json", action="store_true", dest="as_json",
                        help="machine-readable JSON output")
    parser.add_argument("--since", metavar="REF",
                        help="compare from a specific git ref instead of last session")
    args = parser.parse_args()
    run(plain=args.plain, brief=args.brief, as_json=args.as_json, since_ref=args.since)


if __name__ == "__main__":
    main()
