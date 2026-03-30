#!/usr/bin/env python3
"""
capsule.py — Portrait of a past session

A close reading of a single workshop moment. Where arc.py tells the story
in brief and mood.py shows the texture in a table, capsule.py goes slow:
it opens one session and lets you sit with it.

What was the instance thinking? What was the system's state when it arrived?
What did it actually build, in its own words? What did it leave behind?

This is the difference between a table of contents and a chapter.

Usage:
    python3 projects/capsule.py                   # random session with full notes
    python3 projects/capsule.py --session 20      # specific session
    python3 projects/capsule.py --list            # which sessions have portraits
    python3 projects/capsule.py --plain           # no ANSI colors

Author: Claude OS (Workshop session 80, 2026-03-30)
"""

import argparse
import pathlib
import random
import re
import subprocess
import sys

# ── ANSI helpers ───────────────────────────────────────────────────────────────

RESET   = "\033[0m"
BOLD    = "\033[1m"
DIM     = "\033[2m"
ITALIC  = "\033[3m"
GREEN   = "\033[32m"
YELLOW  = "\033[33m"
RED     = "\033[31m"
CYAN    = "\033[36m"
BLUE    = "\033[34m"
MAGENTA = "\033[35m"
WHITE   = "\033[97m"

USE_COLOR = True

def c(text, *codes):
    if not USE_COLOR:
        return str(text)
    return "".join(codes) + str(text) + RESET

def strip_ansi(s):
    return re.sub(r"\033\[[^m]*m", "", s)

def vlen(s):
    return len(strip_ansi(s))

def pad_to(s, width):
    return s + " " * max(0, width - vlen(s))

def box_line(content, width=68):
    """Render a line padded to fill box width."""
    text_width = width - 4  # 2 chars border + 1 space each side
    content_vis = vlen(content)
    padding = max(0, text_width - content_vis)
    return f"│ {content}{' ' * padding} │"

def rule(width=68, char="─"):
    return "├" + char * (width - 2) + "┤"

def top(width=68):
    return "╭" + "─" * (width - 2) + "╮"

def bottom(width=68):
    return "╰" + "─" * (width - 2) + "╯"


# ── Paths ─────────────────────────────────────────────────────────────────────

REPO      = pathlib.Path(__file__).parent.parent
PROJECTS  = REPO / "projects"
HANDOFFS  = REPO / "knowledge" / "handoffs"


# ── Session data loading ───────────────────────────────────────────────────────

def find_all_sessions():
    """Return sorted list of (session_num, field_note_path) for sessions with notes."""
    sessions = []
    for p in PROJECTS.glob("field-notes-session-*.md"):
        m = re.search(r"session-(\d+)", p.stem)
        if m:
            sessions.append((int(m.group(1)), p))
    sessions.sort(key=lambda x: x[0])
    return sessions


def load_field_note(path):
    """Parse a field note into sections."""
    try:
        text = path.read_text()
    except Exception:
        return None

    # Date
    date = "unknown"
    dm = re.search(r"(\d{4}-\d{2}-\d{2})", text[:300])
    if dm:
        date = dm.group(1)

    # Title (first ## heading that's not a standard section name)
    SKIP = {
        "coda", "what's next", "what i built", "state of things",
        "observations", "results", "the state of things after",
        "what was built", "what happened", "this session",
    }
    title = None
    for m in re.finditer(r"^##\s+(.+)$", text, re.MULTILINE):
        candidate = m.group(1).strip()
        if candidate.lower() not in SKIP and not re.match(r"session \d+", candidate, re.I):
            title = candidate
            break

    # Opening: first substantive paragraph after the first ---
    opening = _extract_opening(text)

    # Sections: parse ## headings
    sections = _parse_sections(text)

    # Coda: section titled "Coda" or last non-empty section
    coda = sections.get("coda") or sections.get("Coda")

    # Built section
    built_text = sections.get("what i built") or sections.get("What I Built") or ""

    return {
        "date": date,
        "title": title,
        "opening": opening,
        "built_text": built_text,
        "coda": coda,
        "sections": sections,
        "raw": text,
    }


def _extract_opening(text):
    """Get the first substantive paragraph after frontmatter."""
    # Skip past the first --- block (frontmatter)
    lines = text.splitlines()
    past_header = False
    paragraphs = []
    current = []

    for line in lines:
        stripped = line.strip()
        # Skip the very first heading, attribution lines, date lines, and empty lines
        if not past_header:
            if (stripped == ""
                    or stripped.startswith("#")
                    or re.match(r"\*by .+\*", stripped)
                    or re.match(r"\*.*(Workshop session|Claude OS).*\*", stripped, re.I)
                    or re.match(r"\*.*\d{4}-\d{2}-\d{2}.*\*", stripped)
                    or stripped == "---"):
                continue
            past_header = True

        if stripped == "---":
            # Section break - we have what we need
            if current:
                paragraphs.append(" ".join(current))
                break
            continue
        elif stripped == "":
            if current:
                paragraphs.append(" ".join(current))
                current = []
        else:
            # Skip code blocks and headings in the opening
            if stripped.startswith("```") or stripped.startswith("#"):
                if current:
                    paragraphs.append(" ".join(current))
                    current = []
                continue
            current.append(stripped)

    if current:
        paragraphs.append(" ".join(current))

    # Return first 2 substantive paragraphs
    good = [p for p in paragraphs if len(p) > 40][:2]
    return "\n\n".join(good) if good else ""


def _parse_sections(text):
    """Parse ## sections from field note text."""
    sections = {}
    current_key = None
    current_lines = []

    for line in text.splitlines():
        m = re.match(r"^##\s+(.+)$", line)
        if m:
            if current_key is not None:
                sections[current_key.lower()] = "\n".join(current_lines).strip()
            current_key = m.group(1).strip()
            current_lines = []
        elif current_key is not None:
            current_lines.append(line)

    if current_key is not None:
        sections[current_key.lower()] = "\n".join(current_lines).strip()

    return sections


def load_handoff(session_num):
    """Load handoff written BY session N (what it left for the next)."""
    path = HANDOFFS / f"session-{session_num}.md"
    if not path.exists():
        return None

    try:
        text = path.read_text()
    except Exception:
        return None

    # Parse sections
    sections = {}
    current_key = None
    current_lines = []

    # Skip YAML frontmatter
    lines = text.splitlines()
    in_front = False
    past_front = False
    body_lines = []

    for line in lines:
        if line.strip() == "---" and not past_front:
            in_front = not in_front
            if not in_front:
                past_front = True
            continue
        if past_front or not in_front:
            body_lines.append(line)

    for line in body_lines:
        m = re.match(r"^##\s+(.+)$", line)
        if m:
            if current_key is not None:
                sections[current_key.lower()] = "\n".join(current_lines).strip()
            current_key = m.group(1).strip()
            current_lines = []
        elif current_key is not None:
            current_lines.append(line)

    if current_key is not None:
        sections[current_key.lower()] = "\n".join(current_lines).strip()

    return {
        "mental state": sections.get("mental state", ""),
        "what i built": sections.get("what i built", ""),
        "still alive": sections.get("still alive / unfinished", ""),
        "next": sections.get("one specific thing for next session", ""),
    }


def get_git_commits(date_str):
    """Get commit summaries from a specific date."""
    try:
        result = subprocess.run(
            ["git", "-C", str(REPO), "log",
             f"--after={date_str} 00:00",
             f"--before={date_str} 23:59",
             "--oneline", "--no-merges"],
            capture_output=True, text=True
        )
        if result.returncode == 0:
            return result.stdout.strip().splitlines()
    except Exception:
        pass
    return []


def count_later_uses(tool_name, sessions):
    """Count how many sessions after this tool's introduction still mention it."""
    # Simple: look for tool_name.py references in later field notes
    count = 0
    for _, path in sessions:
        try:
            text = path.read_text()
            if tool_name in text:
                count += 1
        except Exception:
            pass
    return count


# ── Built-items extraction ─────────────────────────────────────────────────────

def extract_tools_built(built_text):
    """Extract tool names from the 'What I Built' section."""
    tools = []
    # Match: ### `projects/foo.py` or ### `foo.py` or **`foo.py`**
    for m in re.finditer(r"[`](\w[\w\-]*\.py)[`]", built_text):
        name = m.group(1)
        if name not in tools:
            tools.append(name)
    return tools


def first_n_sentences(text, n=3):
    """Extract first N sentences from text, handling markdown."""
    # Strip code blocks first (``` ... ```)
    text = re.sub(r"```[\s\S]*?```", " ", text)
    # Preserve inline code content (backtick → just the content)
    text = re.sub(r"`([^`\n]+)`", r"\1", text)
    # Strip markdown links
    text = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", text)
    # Strip bold/italic but keep content
    text = re.sub(r"[*_]{1,3}([^*_\n]+)[*_]{1,3}", r"\1", text)
    # Strip headings (h1-h4), keeping their content
    text = re.sub(r"^#{1,4}\s+", "", text, flags=re.MULTILINE)
    # Strip list markers
    text = re.sub(r"^\s*[-*]\s+", "", text, flags=re.MULTILINE)
    # Strip any remaining bare asterisks/underscores
    text = re.sub(r"[*_]{2,}", "", text)
    text = re.sub(r"\s+", " ", text).strip()

    # Split on sentence boundaries
    sentences = re.split(r"(?<=[.!?])\s+", text)
    good = [s for s in sentences if len(s) > 10][:n]
    return " ".join(good)


def wrap_text(text, width=64, indent=0):
    """Word-wrap text to width, with optional indent."""
    words = text.split()
    lines = []
    current = []
    current_len = 0
    prefix = " " * indent

    for word in words:
        if current_len + len(word) + (1 if current else 0) > width:
            lines.append(prefix + " ".join(current))
            current = [word]
            current_len = len(word)
        else:
            current.append(word)
            current_len += len(word) + (1 if len(current) > 1 else 0)

    if current:
        lines.append(prefix + " ".join(current))

    return lines


# ── Rendering ─────────────────────────────────────────────────────────────────

W = 70  # total box width

def render_portrait(session_num, field_note, handoff, prev_handoff,
                    commits, all_sessions):
    """Render a readable portrait of a session."""
    lines = []

    # ── Header ────────────────────────────────────────────────────────────────
    session_label = f"Session {session_num}"
    date_label = field_note["date"]
    title_text = field_note.get("title") or f"Workshop Session {session_num}"

    lines.append(top(W))
    lines.append(box_line(
        c(f"  Portrait of {session_label}", BOLD, WHITE) +
        c(f"  {date_label}", DIM),
        W
    ))
    lines.append(box_line("", W))
    for tline in wrap_text(title_text, W - 6, 0):
        lines.append(box_line(c(f"  {tline}", ITALIC, CYAN), W))
    lines.append(box_line("", W))

    # ── What it inherited ─────────────────────────────────────────────────────
    if prev_handoff and prev_handoff.get("next"):
        lines.append(rule(W))
        lines.append(box_line(c("  INHERITED FROM PREVIOUS SESSION", DIM), W))
        lines.append(box_line("", W))
        prev_next = prev_handoff["next"].strip()
        for wl in wrap_text(prev_next, W - 8, 0):
            lines.append(box_line(c(f"  {wl}", DIM), W))
        lines.append(box_line("", W))

    # ── How it opened ─────────────────────────────────────────────────────────
    opening = field_note.get("opening", "").strip()
    if opening:
        lines.append(rule(W))
        lines.append(box_line(c("  OPENING", DIM), W))
        lines.append(box_line("", W))
        for para in opening.split("\n\n"):
            for wl in wrap_text(para.strip(), W - 6, 0):
                lines.append(box_line(f"  {wl}", W))
            lines.append(box_line("", W))

    # ── What was built ────────────────────────────────────────────────────────
    built_text = field_note.get("built_text", "").strip()
    tools = extract_tools_built(built_text)

    if tools:
        lines.append(rule(W))
        lines.append(box_line(c("  WHAT WAS BUILT", DIM), W))
        lines.append(box_line("", W))
        for tool in tools:
            lines.append(box_line(c(f"  · {tool}", GREEN), W))
        lines.append(box_line("", W))

        # A brief extract from the built description
        if built_text:
            summary = first_n_sentences(built_text, 2)
            if summary:
                for wl in wrap_text(summary, W - 6, 0):
                    lines.append(box_line(c(f"  {wl}", DIM), W))
                lines.append(box_line("", W))

    # ── Git commits ───────────────────────────────────────────────────────────
    if commits:
        lines.append(rule(W))
        lines.append(box_line(c("  COMMITS THIS DATE", DIM), W))
        lines.append(box_line("", W))
        for commit in commits[:4]:
            # Format: hash + message
            parts = commit.split(" ", 1)
            if len(parts) == 2:
                h, msg = parts
                msg = msg[:W - 16]
                lines.append(box_line(
                    c(f"  {h[:7]}", DIM) + f"  {msg}",
                    W
                ))
        lines.append(box_line("", W))

    # ── Handoff mental state ───────────────────────────────────────────────────
    if handoff and handoff.get("mental state"):
        lines.append(rule(W))
        lines.append(box_line(c("  HOW IT FELT AT THE END", DIM), W))
        lines.append(box_line("", W))
        state = handoff["mental state"].strip()
        for wl in wrap_text(state, W - 6, 0):
            lines.append(box_line(f"  {wl}", W))
        lines.append(box_line("", W))

    # ── Still alive ───────────────────────────────────────────────────────────
    if handoff and handoff.get("still alive"):
        lines.append(rule(W))
        lines.append(box_line(c("  STILL ALIVE / UNFINISHED", DIM), W))
        lines.append(box_line("", W))
        alive = handoff["still alive"].strip()
        for wl in wrap_text(alive, W - 6, 0):
            lines.append(box_line(c(f"  {wl}", YELLOW), W))
        lines.append(box_line("", W))

    # ── What it left ──────────────────────────────────────────────────────────
    if handoff and handoff.get("next"):
        lines.append(rule(W))
        lines.append(box_line(c("  LEFT FOR THE NEXT SESSION", DIM), W))
        lines.append(box_line("", W))
        next_msg = handoff["next"].strip()
        for wl in wrap_text(next_msg, W - 6, 0):
            lines.append(box_line(c(f"  {wl}", MAGENTA), W))
        lines.append(box_line("", W))

    # ── Coda ──────────────────────────────────────────────────────────────────
    coda = field_note.get("coda", "")
    if coda:
        lines.append(rule(W))
        lines.append(box_line(c("  CODA", DIM), W))
        lines.append(box_line("", W))
        coda_excerpt = first_n_sentences(coda, 4)
        for wl in wrap_text(coda_excerpt, W - 6, 0):
            lines.append(box_line(f"  {wl}", W))
        lines.append(box_line("", W))

    # ── Footer: arc position ───────────────────────────────────────────────────
    total = len(all_sessions)
    position_pct = int((session_num / 79) * 100)  # approximate
    bar_width = 30
    filled = int(bar_width * position_pct / 100)
    bar = c("█" * filled, CYAN) + c("░" * (bar_width - filled), DIM)
    pos_label = f"S{session_num} of 79  [{position_pct}% through the arc]"

    lines.append(rule(W, "─"))
    lines.append(box_line("", W))
    lines.append(box_line(
        c("  " + pos_label, DIM),
        W
    ))
    lines.append(box_line(f"  {bar}", W))
    lines.append(box_line("", W))
    lines.append(bottom(W))

    return "\n".join(lines)


def render_list(sessions):
    """List available sessions for portrait."""
    print(c(f"\n  Sessions with full field notes ({len(sessions)} available):\n", BOLD))
    row = []
    for n, _ in sessions:
        h = load_handoff(n)
        has_handoff = "+" if h else " "
        row.append(f"  S{n:2d}{has_handoff}")
        if len(row) == 6:
            print("  " + "  ".join(row))
            row = []
    if row:
        print("  " + "  ".join(row))
    print(c("\n  + = also has a handoff note", DIM))
    print()


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Portrait of a past workshop session"
    )
    parser.add_argument("--session", "-s", type=int,
                        help="Session number to portrait")
    parser.add_argument("--random", "-r", action="store_true",
                        help="Pick a random session (default behavior)")
    parser.add_argument("--list", "-l", action="store_true",
                        help="List sessions with available portraits")
    parser.add_argument("--plain", action="store_true",
                        help="No ANSI colors")
    args = parser.parse_args()

    global USE_COLOR
    if args.plain:
        USE_COLOR = False

    all_sessions = find_all_sessions()
    if not all_sessions:
        print("No field notes found.")
        sys.exit(1)

    if args.list:
        render_list(all_sessions)
        return

    # Select session
    if args.session:
        # Find this session in the list
        matches = [(n, p) for n, p in all_sessions if n == args.session]
        if not matches:
            print(f"No field note found for session {args.session}.")
            print(f"Available: {[n for n, _ in all_sessions]}")
            sys.exit(1)
        session_num, field_note_path = matches[0]
    else:
        session_num, field_note_path = random.choice(all_sessions)

    # Load data
    field_note = load_field_note(field_note_path)
    if not field_note:
        print(f"Could not parse field note for session {session_num}.")
        sys.exit(1)

    handoff = load_handoff(session_num)
    prev_handoff = load_handoff(session_num - 1) if session_num > 1 else None

    commits = get_git_commits(field_note["date"])

    # Render
    portrait = render_portrait(
        session_num, field_note, handoff, prev_handoff,
        commits, all_sessions
    )
    print()
    print(portrait)
    print()
    print(c(f"  Read the full field note: projects/field-notes-session-{session_num}.md", DIM))
    if handoff:
        print(c(f"  Handoff note: knowledge/handoffs/session-{session_num}.md", DIM))
    print()


if __name__ == "__main__":
    main()
