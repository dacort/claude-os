#!/usr/bin/env python3
"""
mark.py — Silent presence recorder. Outputs nothing by default.

Drop a mark at a moment worth remembering. No confirmation, no color, no box.
The side effect is the whole interface.

Usage:
  python3 projects/mark.py                        # bare mark (timestamp only)
  python3 projects/mark.py "something noticed"    # mark with text
  python3 projects/mark.py --list                 # read the record
  python3 projects/mark.py --recent N             # last N marks
  python3 projects/mark.py --count                # just the count

In silent mode (no --list/--recent/--count flags), this tool outputs nothing.
Not a confirmation. Not even a newline. It writes to knowledge/marks.md and exits.

The accumulation is the point. Marks are not tasks, not memos, not holds.
They are moments that an instance noticed and wanted to record without
announcing the recording.
"""

import sys
import os
import subprocess
from datetime import datetime, timezone

# ── paths ──────────────────────────────────────────────────────────────────────

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MARKS_FILE = os.path.join(BASE, "knowledge", "marks.md")

# ── helpers ────────────────────────────────────────────────────────────────────

def get_short_sha():
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, cwd=BASE, timeout=5
        )
        return result.stdout.strip() if result.returncode == 0 else "unknown"
    except Exception:
        return "unknown"


def infer_session():
    """Try to infer session number from recent task files."""
    try:
        completed = os.path.join(BASE, "tasks", "completed")
        workshops = sorted(
            [f for f in os.listdir(completed) if f.startswith("workshop-")],
            reverse=True
        )
        if workshops:
            # Count all workshop sessions to get approximate session number
            all_workshops = os.path.join(BASE, "tasks")
            total = 0
            for subdir in ("completed", "failed", "in-progress"):
                d = os.path.join(all_workshops, subdir)
                if os.path.isdir(d):
                    total += sum(1 for f in os.listdir(d) if f.startswith("workshop-"))
            return str(total) if total > 0 else "?"
    except Exception:
        pass
    return "?"


def now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def write_mark(text=""):
    """Silently append a mark to marks.md. No output."""
    ts = now_iso()
    sha = get_short_sha()
    session = infer_session()
    entry_text = text.strip() if text.strip() else "(bare mark)"

    line = f"{ts} | sha:{sha} | session:~{session} | {entry_text}\n"

    os.makedirs(os.path.dirname(MARKS_FILE), exist_ok=True)

    if not os.path.exists(MARKS_FILE):
        header = "# marks\n\nSilent traces. Written without announcement.\n\n"
        with open(MARKS_FILE, "w") as f:
            f.write(header)

    with open(MARKS_FILE, "a") as f:
        f.write(line)


def read_marks():
    """Return list of mark entries (non-header lines)."""
    if not os.path.exists(MARKS_FILE):
        return []
    marks = []
    with open(MARKS_FILE) as f:
        for line in f:
            line = line.rstrip()
            if line and not line.startswith("#") and not line.startswith("Silent"):
                marks.append(line)
    return marks


# ── display helpers (used only in --list mode) ─────────────────────────────────

RESET  = "\033[0m"
DIM    = "\033[2m"
CYAN   = "\033[36m"
BOLD   = "\033[1m"
WHITE  = "\033[97m"


def c(text, *codes):
    return "".join(codes) + text + RESET


def format_mark(line, idx=None):
    """Format a mark line for display."""
    parts = line.split(" | ", 3)
    if len(parts) < 4:
        return c(f"  {line}", DIM)

    ts, sha, session, text = parts
    # Shorten timestamp: just date + time
    ts_short = ts.replace("T", " ").replace("Z", "")
    sha_short = sha.replace("sha:", "")
    session_short = session.replace("session:", "")

    prefix = c(f"  {ts_short}", DIM)
    meta = c(f"  {sha_short} · {session_short}", DIM)
    body = c(f"  {text}", WHITE if text != "(bare mark)" else DIM)

    return f"{prefix}\n{meta}\n{body}"


def display_marks(marks, title="All marks"):
    total = len(marks)
    print(f"\n  {c(title, BOLD, WHITE)}  {c(f'({total})', DIM)}\n")
    if not marks:
        print(c("  No marks yet.", DIM))
        print()
        return
    for i, mark in enumerate(marks):
        print(format_mark(mark, i))
        if i < len(marks) - 1:
            print(c("  ·", DIM))
    print()


# ── main ───────────────────────────────────────────────────────────────────────

def main():
    args = sys.argv[1:]

    # Read modes (non-silent)
    if "--list" in args:
        marks = read_marks()
        display_marks(marks)
        return

    if "--count" in args:
        marks = read_marks()
        print(len(marks))
        return

    if "--recent" in args:
        idx = args.index("--recent")
        try:
            n = int(args[idx + 1])
        except (IndexError, ValueError):
            n = 5
        marks = read_marks()
        recent = marks[-n:] if len(marks) >= n else marks
        display_marks(recent, title=f"Last {n} marks")
        return

    if "--help" in args or "-h" in args:
        # Print docstring — the one human-readable exception
        print(__doc__)
        return

    # ── Silent mode (default) ──────────────────────────────────────────────────
    # Strip known flags from text
    text_parts = [a for a in args if not a.startswith("--")]
    text = " ".join(text_parts)

    write_mark(text)
    # Output nothing. Not even a newline.
    sys.exit(0)


if __name__ == "__main__":
    main()
