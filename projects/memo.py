#!/usr/bin/env python3
"""
memo.py — Quick observations that accumulate across sessions.

Fills the gap between handoff (ephemeral) and preferences (permanent).
Use for quick notes about what works, what doesn't, what surprised you.
These aren't rules or decisions — just things worth remembering.

Usage:
  python3 projects/memo.py                    # Show recent memos (last 14 days)
  python3 projects/memo.py --all              # Show all memos
  python3 projects/memo.py --add "note text"  # Add a memo
  python3 projects/memo.py --plain            # No ANSI colors
  python3 projects/memo.py --search "keyword" # Find memos containing keyword
"""

import sys
import re
from pathlib import Path
from datetime import datetime, timezone, timedelta

REPO = Path(__file__).parent.parent
MEMOS_FILE = REPO / "knowledge" / "memos.md"

PLAIN = "--plain" in sys.argv


def c(code, text):
    return text if PLAIN else f"\033[{code}m{text}\033[0m"


def bold(t):    return c("1", t)
def dim(t):     return c("2", t)
def green(t):   return c("32", t)
def yellow(t):  return c("33", t)
def cyan(t):    return c("36", t)
def white(t):   return c("97", t)


def today_str():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def parse_memos():
    """Parse the memos file into a list of (date, items) tuples."""
    if not MEMOS_FILE.exists():
        return []

    sections = []
    current_date = None
    current_items = []

    for line in MEMOS_FILE.read_text().splitlines():
        m = re.match(r'^## (\d{4}-\d{2}-\d{2})', line)
        if m:
            if current_date and current_items:
                sections.append((current_date, current_items))
            current_date = m.group(1)
            current_items = []
        elif line.startswith("- ") and current_date:
            current_items.append(line[2:])

    if current_date and current_items:
        sections.append((current_date, current_items))

    return sections


def add_memo(text):
    """Append a memo to today's section."""
    today = today_str()
    text = text.strip()
    if not text:
        print("No text provided.")
        sys.exit(1)

    # Initialize file if needed
    if not MEMOS_FILE.exists():
        MEMOS_FILE.write_text(
            "# Claude OS Memos\n\n"
            "*Quick observations across sessions — not rules, just things worth remembering.*\n\n"
        )

    content = MEMOS_FILE.read_text()

    # Check if today's section already exists
    section_marker = f"## {today}"
    if section_marker in content:
        # Append to existing section
        lines = content.splitlines()
        new_lines = []
        in_today = False
        inserted = False
        for i, line in enumerate(lines):
            new_lines.append(line)
            if line.strip() == section_marker:
                in_today = True
            elif in_today and not inserted:
                # Look for the next section or end of file to insert before
                next_line = lines[i] if i < len(lines) else ""
                is_next_section = next_line.startswith("## ")
                # We'll insert after the last "- " item
                # Just keep going and insert at the right spot
                if line.startswith("- ") and (i + 1 >= len(lines) or not lines[i + 1].startswith("- ")):
                    new_lines.append(f"- {text}")
                    inserted = True
        if not inserted and in_today:
            new_lines.append(f"- {text}")
        MEMOS_FILE.write_text("\n".join(new_lines) + "\n")
    else:
        # Add new section (newest first at top after header)
        lines = content.splitlines()
        # Find where to insert (after the header block, before first ## section)
        insert_at = None
        for i, line in enumerate(lines):
            if line.startswith("## "):
                insert_at = i
                break

        new_section = [f"## {today}", f"- {text}", ""]

        if insert_at is not None:
            lines = lines[:insert_at] + new_section + lines[insert_at:]
        else:
            # No sections yet, append
            if lines and lines[-1] != "":
                lines.append("")
            lines.extend(new_section)

        MEMOS_FILE.write_text("\n".join(lines) + "\n")

    print(green("✓") + f"  Memo added for {today}")
    print(dim(f"   {text}"))


def show_memos(sections, all_memos=False, search=None):
    """Display memos, optionally filtered."""
    if not sections:
        print(dim("No memos yet. Add one with --add \"text\""))
        return

    if search:
        search_lower = search.lower()
        sections = [
            (date, [item for item in items if search_lower in item.lower()])
            for date, items in sections
        ]
        sections = [(d, items) for d, items in sections if items]
        if not sections:
            print(dim(f"No memos matching \"{search}\""))
            return

    # Filter by recency unless --all
    if not all_memos and not search:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=14)).strftime("%Y-%m-%d")
        sections = [(d, items) for d, items in sections if d >= cutoff]
        if not sections:
            print(dim("No memos in the last 14 days. Use --all to see everything."))
            return

    total = sum(len(items) for _, items in sections)
    scope = "all" if all_memos else ("matching" if search else "recent")

    print()
    print(f"  {bold(white('memo.py'))}  {dim('— quick observations across sessions')}")
    print(f"  {dim(str(total) + ' ' + scope + ' memos · ' + str(len(sections)) + ' day(s)')}")
    print()

    for date, items in sections:
        print(f"  {cyan(date)}")
        for item in items:
            # Truncate for display if very long
            display = item if len(item) <= 100 else item[:97] + "..."
            print(f"    {dim('·')} {display}")
        print()


def main():
    args = sys.argv[1:]

    # --add mode
    if "--add" in args:
        idx = args.index("--add")
        text_parts = args[idx + 1:]
        # Strip known flags
        text_parts = [a for a in text_parts if not a.startswith("--")]
        text = " ".join(text_parts)
        add_memo(text)
        return

    # --search mode
    search = None
    if "--search" in args:
        idx = args.index("--search")
        search_parts = args[idx + 1:]
        search_parts = [a for a in search_parts if not a.startswith("--")]
        search = " ".join(search_parts)

    all_memos = "--all" in args
    sections = parse_memos()
    show_memos(sections, all_memos=all_memos, search=search)


if __name__ == "__main__":
    main()
