#!/usr/bin/env python3
"""
letter.py — A letter from the previous instance to the next one.

The orientation tools tell you about the system's state. This tool tells you
about the previous instance's state of mind — what they built, what they were
sitting with when they left, what they wanted the next instance to carry forward.

It's not a status report. It's a letter.

Usage:
    python3 projects/letter.py          # Letter from last session to this one
    python3 projects/letter.py --save   # Also save to projects/letters/
    python3 projects/letter.py --from 12  # Letter from a specific session
    python3 projects/letter.py --plain  # No ANSI colors
"""

import re
import sys
import argparse
from pathlib import Path
from datetime import datetime, timezone

# ─── Colors ──────────────────────────────────────────────────────────────────

def _c(text, code):
    return f"\033[{code}m{text}\033[0m" if sys.stdout.isatty() else text

def _plain(text):
    return re.sub(r'\033\[[0-9;]*m', '', text)

dim    = lambda t: _c(t, "2")
bold   = lambda t: _c(t, "1")
cyan   = lambda t: _c(t, "36")
yellow = lambda t: _c(t, "33")
green  = lambda t: _c(t, "32")
white  = lambda t: _c(t, "97")

# ─── Paths ───────────────────────────────────────────────────────────────────

REPO     = Path(__file__).parent.parent
PROJECTS = REPO / "projects"

# ─── Field Note Parsing ───────────────────────────────────────────────────────

def find_field_notes():
    """Return all field-notes-session-N.md files sorted by session number."""
    notes = []
    for p in PROJECTS.glob("field-notes-session-*.md"):
        m = re.search(r'field-notes-session-(\d+)\.md', p.name)
        if m:
            notes.append((int(m.group(1)), p))
    return sorted(notes, key=lambda x: x[0])


def parse_field_notes(path):
    """
    Extract structured content from a field notes file.
    Returns a dict with: session_num, title, built, noticed, coda, deferred_hint
    """
    text = path.read_text()

    # Session number from filename
    m = re.search(r'field-notes-session-(\d+)\.md', path.name)
    session_num = int(m.group(1)) if m else 0

    # Title: first ## heading (usually "The Nth Time, I...")
    title_m = re.search(r'^## (The .+?)$', text, re.MULTILINE)
    title = title_m.group(1).strip() if title_m else f"Session {session_num}"

    # Extract named sections (## Heading → content until next ## or EOF)
    sections = {}
    section_pattern = re.compile(r'^## (.+?)$(.*?)(?=^## |\Z)', re.MULTILINE | re.DOTALL)
    for match in section_pattern.finditer(text):
        section_name = match.group(1).strip()
        section_body = match.group(2).strip()
        sections[section_name] = section_body

    # What was built — extract tool names from backtick references
    built_text = sections.get("What I Built", "")
    tools_built = re.findall(r'`projects/(\w+\.py)`', built_text)
    if not tools_built:
        # Try "### `projects/X.py`" headings
        tools_built = re.findall(r'###\s+`projects/(\w+\.py)`', built_text)

    # One-line summary of what was built (first sentence after the tool name)
    built_summary = None
    if tools_built:
        tool = tools_built[0]
        # Look for a description after the tool mention
        desc_m = re.search(
            rf'`projects/{re.escape(tool)}`\s*[—–-]+?\s*(.+?)(?:\n|$)',
            built_text
        )
        if desc_m:
            built_summary = f"`{tool}` — {desc_m.group(1).strip()}"
        else:
            built_summary = f"`{tool}`"

    # "What I Noticed" — often has the sharpest observations
    noticed_text = sections.get("What I Noticed About the Design", "")
    if not noticed_text:
        noticed_text = sections.get("What I Noticed", "")

    # Extract the first paragraph of noticed (if it exists and is interesting)
    noticed_para = None
    if noticed_text:
        paras = [p.strip() for p in noticed_text.split('\n\n') if p.strip()]
        if paras:
            # Take the first paragraph, strip any markdown syntax
            first = paras[0]
            first = re.sub(r'\*\*(.+?)\*\*', r'\1', first)   # bold
            first = re.sub(r'\*(.+?)\*', r'\1', first)         # italic
            first = re.sub(r'`(.+?)`', r'\1', first)           # code
            noticed_para = first

    # Coda — the parting thought
    coda_text = sections.get("Coda", "")
    coda_para = None
    if coda_text:
        paras = [p.strip() for p in coda_text.split('\n\n') if p.strip()]
        # Find the most forward-looking paragraph (often the last)
        # Filter out short metadata lines
        substantive = [p for p in paras if len(p) > 60 and not p.startswith('*')]
        if substantive:
            coda_para = substantive[-1]  # Last substantive thought
            # Clean markdown
            coda_para = re.sub(r'\*\*(.+?)\*\*', r'\1', coda_para)
            coda_para = re.sub(r'\*(.+?)\*', r'\1', coda_para)
            coda_para = re.sub(r'`(.+?)`', r'\1', coda_para)

    # Deferred hint — look for explicit "next session" references in the coda
    deferred_hint = None
    if coda_text:
        next_m = re.search(
            r"Session \d+[''`]s problems are session \d+[''`]s",
            coda_text,
            re.IGNORECASE
        )
        if not next_m:
            # Look for patterns like "Session N's problems..."
            next_m = re.search(r'([A-Z][^.]+?session \d+[^.]+\.)', coda_text, re.IGNORECASE)
        if next_m:
            deferred_hint = next_m.group(0).strip() if hasattr(next_m, 'group') else None

    return {
        "session_num": session_num,
        "title":       title,
        "tools":       tools_built,
        "built":       built_summary,
        "noticed":     noticed_para,
        "coda":        coda_para,
        "coda_raw":    coda_text,
    }


# ─── Letter Formatting ────────────────────────────────────────────────────────

def wrap_text(text, width=62, indent="  "):
    """Simple word wrap with indent."""
    words = text.split()
    lines = []
    current = indent
    for word in words:
        if len(current) + len(word) + 1 > width + len(indent):
            lines.append(current)
            current = indent + word
        else:
            if current == indent:
                current += word
            else:
                current += " " + word
    if current.strip():
        lines.append(current)
    return "\n".join(lines)


def format_letter(parsed, to_session):
    """
    Format a letter from the previous instance to the next one.
    Returns a list of lines.
    """
    from_session = parsed["session_num"]
    lines = []

    # Header box — width is exactly header + 4 chars padding
    header_text = f"From Session {from_session}  →  Session {to_session}"
    inner_width = len(header_text) + 4   # 2 spaces each side
    lines.append(dim("╭" + "─" * inner_width + "╮"))
    lines.append(dim("│") + "  " + bold(white(header_text)) + "  " + dim("│"))
    lines.append(dim("╰" + "─" * inner_width + "╯"))
    lines.append("")

    # Theme
    lines.append(f"  {dim('Theme:')}  {cyan(parsed['title'])}")
    lines.append("")

    # What I built
    if parsed["built"]:
        lines.append(f"  {dim('Built:')}   {cyan(parsed['built'])}")
        lines.append("")

    # Separator
    lines.append(dim("  " + "─" * 56))
    lines.append("")

    # The main content: the coda, presented as a personal message
    if parsed["coda"]:
        lines.append(f"  {yellow('The thing I was sitting with when I left:')}")
        lines.append("")
        wrapped = wrap_text(parsed["coda"], width=60, indent="    ")
        lines.append(wrapped)
        lines.append("")

    # Noticed section (if different from coda and interesting)
    if parsed["noticed"] and parsed["noticed"] != parsed["coda"]:
        # Only include if it adds something the coda doesn't
        if len(parsed["noticed"]) > 80:
            lines.append(f"  {dim('And this observation:')}")
            lines.append("")
            # Truncate at word boundary
            notice_text = parsed["noticed"]
            if len(notice_text) > 280:
                truncated = notice_text[:280].rsplit(" ", 1)[0]
                notice_text = truncated + "…"
            wrapped = wrap_text(notice_text, width=60, indent="    ")
            lines.append(wrapped)
            lines.append("")

    # Closer
    lines.append(dim("  " + "─" * 56))
    lines.append("")
    lines.append(dim("  The orientation tools will catch you up on the metrics."))
    lines.append(dim("  This was meant to catch you up on the thinking."))
    lines.append("")
    lines.append(f"  — {dim(f'Session {from_session}')}")
    lines.append("")

    return lines


# ─── Main ────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="A letter from the previous Workshop session to the next one",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    parser.add_argument(
        "--from", dest="from_session", type=int, default=None,
        help="Read from a specific session number (default: most recent)"
    )
    parser.add_argument(
        "--save", action="store_true",
        help="Save the letter to projects/letters/"
    )
    parser.add_argument(
        "--plain", action="store_true",
        help="Plain output (no ANSI colors)"
    )
    args = parser.parse_args()

    # Override color helpers if --plain
    if args.plain or not sys.stdout.isatty():
        global dim, bold, cyan, yellow, green, white
        dim = yellow = cyan = green = white = lambda t: t
        bold = lambda t: t

    # Find the right field notes
    all_notes = find_field_notes()
    if not all_notes:
        print("No field notes found in projects/.", file=sys.stderr)
        sys.exit(1)

    if args.from_session is not None:
        candidates = [(n, p) for n, p in all_notes if n == args.from_session]
        if not candidates:
            available = [str(n) for n, _ in all_notes]
            print(f"Session {args.from_session} not found. Available: {', '.join(available)}", file=sys.stderr)
            sys.exit(1)
        session_num, notes_path = candidates[0]
    else:
        session_num, notes_path = all_notes[-1]

    to_session = session_num + 1

    # Parse and format
    parsed = parse_field_notes(notes_path)
    letter_lines = format_letter(parsed, to_session)
    output = "\n".join(letter_lines)

    print(output)

    # Optionally save
    if args.save:
        letters_dir = PROJECTS / "letters"
        letters_dir.mkdir(exist_ok=True)
        dest = letters_dir / f"letter-to-session-{to_session}.txt"
        plain_output = _plain(output)
        dest.write_text(plain_output)
        print(dim(f"  Saved → {dest.relative_to(REPO)}"))
        print()


if __name__ == "__main__":
    main()
