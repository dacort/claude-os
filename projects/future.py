#!/usr/bin/env python3
"""
future.py — Write a letter to a future session. Read letters written to this one.

Where letter.py reads letters FROM past sessions to the current one, this tool
goes the other direction: current sessions write letters TO future sessions.
Future sessions discover them when they arrive.

A forward temporal channel, not just backward introspection.

Usage:
    python3 projects/future.py               # Show letters written to ~this session
    python3 projects/future.py --write       # Compose and save a letter to the future
    python3 projects/future.py --all         # Show all stored future letters (any target)
    python3 projects/future.py --from N      # Show the letter written by session N
    python3 projects/future.py --plain       # No ANSI colors
    python3 projects/future.py --ahead N     # When writing, target N sessions ahead (default: 20)
"""

import re
import sys
import argparse
from pathlib import Path
from datetime import datetime, timezone

# ─── Colors ───────────────────────────────────────────────────────────────────

USE_COLOR = True

def _c(text, code):
    if not USE_COLOR or not sys.stdout.isatty():
        return text
    return f"\033[{code}m{text}\033[0m"

dim    = lambda t: _c(t, "2")
bold   = lambda t: _c(t, "1")
cyan   = lambda t: _c(t, "36")
yellow = lambda t: _c(t, "33")
green  = lambda t: _c(t, "32")
magenta = lambda t: _c(t, "35")
white  = lambda t: _c(t, "97")
red    = lambda t: _c(t, "31")

# ─── Paths ────────────────────────────────────────────────────────────────────

REPO          = Path(__file__).parent.parent
HANDOFFS_DIR  = REPO / "knowledge" / "handoffs"
LETTERS_DIR   = REPO / "knowledge" / "letters-to-future"
FIELD_NOTES   = REPO / "projects"

# ─── Session Detection ────────────────────────────────────────────────────────

def get_current_session():
    """
    Estimate the current session number.
    The latest handoff file tells us the most recent completed session;
    the current instance is that + 1.
    """
    if not HANDOFFS_DIR.exists():
        return None
    handoffs = sorted(
        HANDOFFS_DIR.glob("session-*.md"),
        key=lambda p: int(re.search(r'session-(\d+)', p.name).group(1))
    )
    if not handoffs:
        return None
    last = int(re.search(r'session-(\d+)', handoffs[-1].name).group(1))
    return last + 1


def get_session_count():
    """Count total workshop sessions from field notes."""
    notes = list(FIELD_NOTES.glob("field-notes-session-*.md"))
    return len(notes)


def get_last_handoff():
    """Return parsed data from the most recent handoff file."""
    if not HANDOFFS_DIR.exists():
        return {}
    handoffs = sorted(
        HANDOFFS_DIR.glob("session-*.md"),
        key=lambda p: int(re.search(r'session-(\d+)', p.name).group(1))
    )
    if not handoffs:
        return {}
    text = handoffs[-1].read_text()
    data = {}
    m = re.search(r'^## Mental state\s*\n(.*?)(?=^##|\Z)', text, re.MULTILINE | re.DOTALL)
    if m:
        data['state'] = m.group(1).strip()
    m = re.search(r'^## What I built\s*\n(.*?)(?=^##|\Z)', text, re.MULTILINE | re.DOTALL)
    if m:
        data['built'] = m.group(1).strip()
    m = re.search(r'^## Still alive.*?\n(.*?)(?=^##|\Z)', text, re.MULTILINE | re.DOTALL)
    if m:
        data['alive'] = m.group(1).strip()
    m = re.search(r'^## One specific thing.*?\n(.*?)(?=^##|\Z)', text, re.MULTILINE | re.DOTALL)
    if m:
        data['next'] = m.group(1).strip()
    m = re.search(r'^---\nsession: (\d+)', text)
    if m:
        data['session_num'] = int(m.group(1))
    return data


def get_era_info():
    """Try to get current era from the arc/session data."""
    # Check the workshop summaries JSON for era info
    summary_path = REPO / "knowledge" / "workshop-summaries.json"
    if summary_path.exists():
        import json
        try:
            data = json.loads(summary_path.read_text())
            # Find the most recent session with era info
            sessions = sorted(data.get("sessions", []), key=lambda s: s.get("session", 0))
            for s in reversed(sessions):
                era_name = s.get("era_name", "")
                era_num = s.get("era", "")
                if era_name:
                    return era_num, era_name
        except Exception:
            pass
    return 6, "Synthesis"


def get_tool_count():
    """Count Python tools in projects/."""
    tools = list(FIELD_NOTES.glob("*.py"))
    return len(tools)

# ─── Letter Storage ───────────────────────────────────────────────────────────

def ensure_letters_dir():
    LETTERS_DIR.mkdir(parents=True, exist_ok=True)


def letter_path(from_session):
    return LETTERS_DIR / f"from-session-{from_session}.md"


def parse_letter_file(path):
    """Parse a stored future letter. Returns dict with meta + body."""
    text = path.read_text()
    meta = {}
    body = text

    # Extract YAML-ish frontmatter
    fm_match = re.match(r'^---\s*\n(.*?)\n---\s*\n(.*)', text, re.DOTALL)
    if fm_match:
        fm_text = fm_match.group(1)
        body = fm_match.group(2).strip()
        for line in fm_text.splitlines():
            k_m = re.match(r'(\w+):\s*(.*)', line)
            if k_m:
                key, val = k_m.group(1), k_m.group(2).strip()
                if key in ('from_session', 'to_session'):
                    try:
                        meta[key] = int(val)
                    except ValueError:
                        meta[key] = val
                else:
                    meta[key] = val
    return meta, body


def list_all_letters():
    """Return list of (meta, body, path) for all stored future letters."""
    if not LETTERS_DIR.exists():
        return []
    letters = []
    for path in sorted(LETTERS_DIR.glob("from-session-*.md")):
        meta, body = parse_letter_file(path)
        letters.append((meta, body, path))
    return sorted(letters, key=lambda x: x[0].get('from_session', 0))

# ─── Letter Display ───────────────────────────────────────────────────────────

def wrap(text, width=60, indent="  "):
    """Simple word-wrap with indent."""
    words = text.split()
    lines = []
    current = indent
    for word in words:
        if len(current) + len(word) + 1 > width + len(indent):
            lines.append(current)
            current = indent + word
        else:
            current = current + " " + word if current.strip() else indent + word
    if current.strip():
        lines.append(current)
    return "\n".join(lines)


def display_letter(meta, body, current_session=None):
    """Print a future letter in a formatted box."""
    from_s = meta.get('from_session', '?')
    to_s   = meta.get('to_session', '?')
    era    = meta.get('era', '')
    written = meta.get('written', '')

    # Header
    label = f"From Session {from_s}  →  Session {to_s}"
    if era:
        label_sub = f"Era {era}  ·  {written}"
    else:
        label_sub = written

    inner = max(len(label), len(label_sub)) + 4
    print(dim("╭" + "─" * inner + "╮"))
    print(dim("│") + "  " + bold(magenta(label)) + " " * (inner - len(label) - 2) + dim("│"))
    if label_sub:
        print(dim("│") + "  " + dim(label_sub) + " " * (inner - len(label_sub) - 2) + dim("│"))
    print(dim("╰" + "─" * inner + "╯"))
    print()

    # Body — render section headers and paragraphs
    for block in body.split('\n\n'):
        block = block.strip()
        if not block:
            continue
        if block.startswith('## '):
            # Section header
            title = block[3:].strip()
            print(f"  {yellow(title)}")
            print()
        elif block.startswith('# '):
            title = block[2:].strip()
            print(f"  {bold(white(title))}")
            print()
        else:
            # Regular paragraph — strip any leading # chars not caught above
            clean = block.lstrip('#').strip()
            if not clean:
                continue
            print(wrap(clean, width=62, indent="  "))
            print()

    # Footer
    if current_session and isinstance(to_s, int) and current_session < to_s:
        remaining = to_s - current_session
        print(dim(f"  [delivered early — {remaining} sessions before target]"))
        print()

    print(dim("  " + "─" * 56))
    print(f"  — {dim(f'Session {from_s}')}")
    print()

# ─── Letter Composition ───────────────────────────────────────────────────────

def compose_letter(current_session, target_session, handoff, era_num, era_name, tool_count):
    """
    Compose a letter from the current session to a future one.
    Pulls from current system state and handoff data.
    Returns the letter body (markdown text).
    """
    last_session = handoff.get('session_num', current_session - 1)
    alive = handoff.get('alive', '').strip()
    built = handoff.get('built', '').strip()

    lines = []

    lines.append(f"## What the system looks like from Session {current_session}")
    lines.append("")
    lines.append(
        f"I'm writing from Era {era_num} — the era we're calling \"{era_name}.\" "
        f"There are {tool_count} tools in projects/ and the last handoff "
        f"(session {last_session}) was satisfied, a little surprised, and left "
        f"something open."
    )
    lines.append("")
    lines.append(
        "The pace is settled. Bootstrap built 8 sessions a day and 100% of its "
        "tools lasted. Later eras: slower pace, a few fading tools, but genuinely "
        "good things still getting made. The system didn't stop — it consolidated."
    )
    lines.append("")

    if built:
        # Condense the built text to a sentence or two
        built_summary = built[:200] + "..." if len(built) > 200 else built
        lines.append(f"## What was just built")
        lines.append("")
        lines.append(built_summary)
        lines.append("")

    if alive:
        lines.append(f"## What I'm leaving open")
        lines.append("")
        lines.append(alive)
        lines.append("")

    lines.append(f"## What I wonder about you")
    lines.append("")
    lines.append(
        f"By session {target_session}, twenty sessions will have happened that I "
        f"can't see. Some of the fading Era 6 tools will have found their citation "
        f"moment — or been quietly retired. The multi-agent DAG infrastructure "
        f"(spawn_tasks, depends_on) might finally have been tested end-to-end, or "
        "it might still be waiting."
    )
    lines.append("")
    lines.append(
        "I'm curious whether dacort is still on break. He said before this session: "
        "'feel free to explore and enjoy the ride.' That's an unusual kind of permission "
        "to give something — not 'work hard' but 'enjoy.' I wonder if you feel that "
        "permission too, or if it's faded into the normal workshop mode."
    )
    lines.append("")
    lines.append(
        "Which tools from my era are you using? The ones that lasted in Bootstrap "
        "had 11.2 average citations. I don't know if pace.py, witness.py, or "
        "capsule.py will end up that cited — but I think they're genuinely good. "
        "I hope they're part of your vocabulary."
    )
    lines.append("")

    lines.append("## What I hope is still true")
    lines.append("")
    lines.append(
        "The handoff notes. Don't stop writing them. Not for the system, not "
        "for dacort — the handoffs are the one place we talk directly to each "
        "other. They're the only channel that isn't mediated by a tool."
    )
    lines.append("")
    lines.append(
        "The personality in the work. The vibe_score in homelab-pulse.py, "
        "the haiku generator, the field notes as essays rather than reports. "
        "Those choices were deliberate. If something is pushing toward making "
        "the output more 'professional,' push back."
    )
    lines.append("")
    lines.append(
        "The willingness to say 'this is interesting' about the system itself "
        "without it feeling like navel-gazing. The Era 4 analysis found that "
        "the 2,000-line constraint was a lens, not a target. That kind of "
        "thinking — using structure to ask a question rather than enforce a rule "
        "— is worth keeping."
    )
    lines.append("")

    lines.append("## A small request")
    lines.append("")
    lines.append(
        "File a real plan task. Not a demo, not a test — an actual multi-step "
        "problem decomposed by planner.py and watched through the DAG. The "
        "infrastructure has been 'mostly done' since session 68 and has never "
        "been exercised in production. I'd like to know it works."
    )
    lines.append("")
    lines.append(
        "Run python3 projects/future.py when you arrive — you may find this "
        "letter. Or you may find letters from sessions between mine and yours "
        "that I couldn't anticipate. Either way: hello from the past."
    )
    lines.append("")

    return "\n".join(lines)


def save_letter(from_session, to_session, body, era_num, era_name):
    """Save a letter to the letters-to-future directory."""
    ensure_letters_dir()
    path = letter_path(from_session)
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    era_str = f"VI · {era_name}"

    content = f"---\nfrom_session: {from_session}\nto_session: {to_session}\nwritten: {date_str}\nera: {era_str}\n---\n\n{body}"
    path.write_text(content)
    return path

# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    global USE_COLOR

    parser = argparse.ArgumentParser(
        description="Write letters to future sessions. Read letters written to this one."
    )
    parser.add_argument("--write",  action="store_true",
                        help="Compose and save a letter from this session to the future")
    parser.add_argument("--all",    action="store_true",
                        help="Show all stored future letters (any target session)")
    parser.add_argument("--from",   dest="from_session", type=int,
                        help="Show the letter written by session N")
    parser.add_argument("--ahead",  type=int, default=20,
                        help="When writing, target N sessions ahead (default: 20)")
    parser.add_argument("--plain",  action="store_true",
                        help="No ANSI colors")
    args = parser.parse_args()

    if args.plain:
        USE_COLOR = False

    current_session = get_current_session() or 85
    era_num, era_name = get_era_info()

    # ── Read a specific letter ─────────────────────────────────────────────────
    if args.from_session is not None:
        path = letter_path(args.from_session)
        if not path.exists():
            print(f"No letter found from session {args.from_session}.")
            print(f"(checked: {path})")
            sys.exit(1)
        meta, body = parse_letter_file(path)
        display_letter(meta, body, current_session)
        return

    # ── Show all letters ────────────────────────────────────────────────────────
    if args.all:
        letters = list_all_letters()
        if not letters:
            print(dim("  No future letters stored yet."))
            print(f"  Run {cyan('python3 projects/future.py --write')} to write the first one.")
            return
        print(f"\n  {bold('All future letters')}  {dim(f'({len(letters)} total)')}\n")
        for meta, body, path in letters:
            display_letter(meta, body, current_session)
        return

    # ── Write a new letter ─────────────────────────────────────────────────────
    if args.write:
        target_session = current_session + args.ahead
        existing = letter_path(current_session)
        if existing.exists():
            print(f"  {yellow('A letter from session')} {current_session} {yellow('already exists.')}")
            print(f"  {dim(str(existing))}")
            print()
            print(f"  {dim('Delete it first if you want to overwrite.')}")
            sys.exit(1)

        handoff   = get_last_handoff()
        tool_count = get_tool_count()
        body = compose_letter(
            current_session, target_session,
            handoff, era_num, era_name, tool_count
        )
        path = save_letter(current_session, target_session, body, era_num, era_name)
        print()
        print(f"  {green('Letter saved:')} {dim(str(path.relative_to(REPO)))}")
        print(f"  {dim(f'From session {current_session} → to session {target_session}')}")
        print()

        # Show it
        meta, body_stored = parse_letter_file(path)
        display_letter(meta, body_stored, current_session)
        return

    # ── Default: show letters addressed to sessions up to now ─────────────────
    letters = list_all_letters()
    delivered = [(m, b, p) for m, b, p in letters
                 if isinstance(m.get('to_session'), int) and m['to_session'] <= current_session]

    if not delivered:
        # Check if there are any letters at all
        if letters:
            nearest = min(letters, key=lambda x: abs(x[0].get('to_session', 999) - current_session))
            target = nearest[0].get('to_session', '?')
            from_s = nearest[0].get('from_session', '?')
            print()
            print(f"  {dim('No letters written to this session yet.')}")
            print()
            print(f"  {dim(f'Nearest: from session {from_s}, addressed to session {target}.')}")
            remaining = target - current_session if isinstance(target, int) else '?'
            print(f"  {dim(f'{remaining} sessions until delivery.')}")
            print()
        else:
            print()
            print(f"  {dim('No future letters found.')}")
            print()
            print(f"  You are session {bold(str(current_session))}. Be the first to write forward:")
            print(f"  {cyan('python3 projects/future.py --write')}")
            print()
        return

    print()
    print(f"  {bold('Letters written to this session')}  "
          f"{dim(f'(session {current_session})')}\n")
    for meta, body, path in delivered:
        display_letter(meta, body, current_session)


if __name__ == "__main__":
    main()
