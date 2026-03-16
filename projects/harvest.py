#!/usr/bin/env python3
"""
harvest.py — deferred ideas from the living field notes

next.py shows the curated backlog (6 items from exoclaw-ideas.md, written session 7).
This shows the other backlog: ideas that emerged from actually running the system
and were noted but not acted on. The things we almost built.

Scans field notes for:
  - Explicit "didn't build" / "what's still open" sections
  - Coda sentences with deferred-work signals

Usage:
  python3 projects/harvest.py              # all sessions
  python3 projects/harvest.py --recent 10  # last 10 sessions only
  python3 projects/harvest.py --plain      # no ANSI colors
"""

import os
import re
import sys
import argparse
from pathlib import Path


# ─── color helpers ──────────────────────────────────────────────────────────

def ansi(code: str, text: str, plain: bool) -> str:
    if plain: return text
    return f"\033[{code}m{text}\033[0m"

def bold(t, p=False):    return ansi("1", t, p)
def dim(t, p=False):     return ansi("2", t, p)
def cyan(t, p=False):    return ansi("36", t, p)
def green(t, p=False):   return ansi("32", t, p)
def yellow(t, p=False):  return ansi("33", t, p)
def magenta(t, p=False): return ansi("35", t, p)
def gray(t, p=False):    return ansi("90", t, p)
def white(t, p=False):   return ansi("97", t, p)


# ─── constants ──────────────────────────────────────────────────────────────

PROJECTS_DIR = Path(__file__).parent

# Section titles that explicitly capture deferred work
DEFERRED_SECTIONS = [
    "What I Didn't Build",
    "What's Still Open",
    "The Gap to Production",
    "What's Next",
    "On the Deferred Ideas",
]

# Sentence-level signals in coda / general text
DEFERRED_SIGNALS = [
    r"\bdidn't build\b",
    r"\bnot yet built\b",
    r"\bworth exploring\b",
    r"\bworth trying\b",
    r"\bcould build\b",
    r"\bmight build\b",
    r"\bdeferred\b",
    r"\bopen question\b",
    r"\bopen frontier\b",
    r"\bnext instance\b.*\bcould\b",
    r"\bfuture session\b.*\bcould\b",
    r"\bnot sure\b.*\byet\b",
    r"\bunresolved\b",
    r"\bstill.*outstanding\b",
]

SIGNAL_RE = re.compile("|".join(DEFERRED_SIGNALS), re.IGNORECASE)


# ─── data structures ─────────────────────────────────────────────────────────

class HarvestItem:
    def __init__(self, session: int, title: str, section: str, text: str, explicit: bool):
        self.session = session
        self.title = title    # session title (from H1)
        self.section = section  # which section it came from
        self.text = text
        self.explicit = explicit  # from a named deferred section vs coda signal
        self.max_session = 0   # set after loading: highest session number in dataset


# ─── parsing ────────────────────────────────────────────────────────────────

def load_notes() -> list[dict]:
    """Load all field notes, return sorted list of dicts."""
    notes = []
    for fn in PROJECTS_DIR.glob("field-notes-session-*.md"):
        m = re.search(r"session-(\d+)", fn.name)
        if not m:
            continue
        num = int(m.group(1))
        text = fn.read_text()
        title_m = re.search(r'^# .+\n.*\n\n## (.+)', text)
        if not title_m:
            # fallback: look for first ## heading that's the session title
            title_m = re.search(r'^## (The .+Time.+)', text, re.MULTILINE)
        title = title_m.group(1).strip() if title_m else f"Session {num}"
        notes.append({"num": num, "title": title, "text": text, "path": fn})
    return sorted(notes, key=lambda n: n["num"])


def extract_section(text: str, section_title: str) -> str | None:
    """Extract content of a named ## section, stopping at next ##."""
    pattern = r"## " + re.escape(section_title) + r"\n(.*?)(?:\n## |\Z)"
    m = re.search(pattern, text, re.DOTALL)
    if not m:
        return None
    return m.group(1).strip()


def extract_coda_deferred(text: str) -> list[str]:
    """Extract sentences from the Coda section that have deferred-work signals."""
    coda_m = re.search(r"## (?:The )?Coda\n(.*?)(?:\n## |\Z)", text, re.DOTALL)
    if not coda_m:
        return []
    coda_text = coda_m.group(1)
    sentences = re.split(r"(?<=[.!?])\s+", coda_text.replace("\n", " "))
    hits = []
    for sent in sentences:
        sent = sent.strip()
        if len(sent) < 30:
            continue
        if not SIGNAL_RE.search(sent):
            continue
        # Skip historical summaries ("session N built X", "session N closed it")
        if re.search(r"\bsession \d+ (built|created|wrote|added|fixed|closed|opened|resolved)\b", sent, re.IGNORECASE):
            continue
        # Skip sentences about things that WERE done (positive past tense + no deferred signal)
        if re.search(r"\b(built|done|completed|finished|resolved)\b", sent, re.IGNORECASE):
            if not re.search(r"\b(didn't|not yet|deferred|open|still unresolved|still open|open question)\b", sent, re.IGNORECASE):
                continue
        # Skip generic observations ("deferred ideas aren't technical debt")
        if re.search(r"\bdeferred ideas? (aren't|are not|is not)\b", sent, re.IGNORECASE):
            continue
        hits.append(sent)
    return hits


def harvest_note(note: dict) -> list[HarvestItem]:
    """Extract all deferred items from a single field note."""
    items = []
    text = note["text"]
    num = note["num"]
    title = note["title"]

    # 1. Explicit deferred sections
    for section_name in DEFERRED_SECTIONS:
        content = extract_section(text, section_name)
        if not content:
            continue
        # Skip generic "I don't know / free time" responses in What's Next
        if section_name == "What's Next" and re.match(r"I don't know", content.strip(), re.IGNORECASE):
            continue
        # Skip sections that are entirely analysis of why things are already done
        if len(content) < 40:
            continue
        # Strip bold/italic markers
        clean = re.sub(r'\*\*(.+?)\*\*', r'\1', content)
        clean = re.sub(r'\*(.+?)\*', r'\1', clean)
        items.append(HarvestItem(num, title, section_name, clean, explicit=True))

    # 2. Coda sentences with deferred signals
    coda_hits = extract_coda_deferred(text)
    for hit in coda_hits:
        clean = re.sub(r'\*\*(.+?)\*\*', r'\1', hit)
        clean = re.sub(r'\*(.+?)\*', r'\1', clean)
        items.append(HarvestItem(num, title, "Coda", clean, explicit=False))

    return items


# ─── display ────────────────────────────────────────────────────────────────

def wrap_text(text: str, indent: int, width: int = 72) -> str:
    """Wrap text to width, indenting continuation lines."""
    words = text.split()
    lines = []
    current = " " * indent
    for word in words:
        if len(current) + len(word) + 1 > width:
            lines.append(current)
            current = " " * indent + word
        else:
            current = current + (" " if current.strip() else "") + word
    if current.strip():
        lines.append(current)
    return "\n".join(lines)


def display(items: list[HarvestItem], plain: bool, max_session: int = 0) -> None:
    W = 66

    # Header
    print(ansi("1;36", "  harvest.py", plain) + "  " + dim("— deferred ideas from field notes", plain))
    explicit_count = sum(1 for i in items if i.explicit)
    coda_count = sum(1 for i in items if not i.explicit)
    print(dim(f"  {explicit_count} explicit  ·  {coda_count} coda mentions", plain))
    print()

    if not items:
        print(dim("  No deferred items found.", plain))
        return

    # Group by explicit vs coda
    explicit_items = [i for i in items if i.explicit]
    coda_items = [i for i in items if not i.explicit]

    # --- Explicit deferred sections ---
    if explicit_items:
        print(bold("  EXPLICITLY DEFERRED", plain))
        print(dim("  " + "─" * 58, plain))
        print()
        for item in explicit_items:
            snum = cyan(f"S{item.session}", plain)
            sec = dim(f"[{item.section}]", plain)
            age = max_session - item.session
            age_str = gray(f"  {age} sessions ago" if age > 0 else "  this session", plain)
            stale_note = dim("  (may be resolved)", plain) if age > 14 else ""
            print(f"  {snum}  {sec}{age_str}{stale_note}")
            # Show up to ~300 chars of the content, smartly trimmed
            content = item.text
            # Take first 4-5 lines or 320 chars
            lines = [l for l in content.split("\n") if l.strip()]
            preview_lines = []
            total_chars = 0
            for line in lines:
                if total_chars > 300 and preview_lines:
                    preview_lines.append("     ...")
                    break
                preview_lines.append("     " + line.strip()[:68])
                total_chars += len(line)
            print(dim("\n".join(preview_lines), plain))
            print()

    # --- Coda signals ---
    if coda_items:
        print(bold("  CODA MENTIONS", plain))
        print(dim("  " + "─" * 58, plain))
        print()
        # Group by session
        by_session: dict[int, list[HarvestItem]] = {}
        for item in coda_items:
            by_session.setdefault(item.session, []).append(item)
        for snum in sorted(by_session.keys()):
            sitems = by_session[snum]
            s_label = cyan(f"S{snum}", plain)
            age = max_session - snum
            age_str = gray(f"  {age} sessions ago" if age > 0 else "  this session", plain)
            stale = age > 12
            stale_note = dim("  (may be resolved)", plain) if stale else ""
            print(f"  {s_label}{age_str}{stale_note}")
            for si in sitems:
                text_trimmed = si.text[:120] + ("..." if len(si.text) > 120 else "")
                print(dim(f"     {text_trimmed}", plain))
            print()

    # Footer
    print(dim("  " + "─" * 58, plain))
    print(dim("  run next.py for the curated backlog", plain))
    print()


# ─── main ────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="harvest.py — deferred ideas from field notes")
    parser.add_argument("--recent", type=int, metavar="N", help="Only last N sessions")
    parser.add_argument("--plain", action="store_true", help="No ANSI colors")
    args = parser.parse_args()

    plain = args.plain

    all_notes = load_notes()
    max_session = max(n["num"] for n in all_notes) if all_notes else 0

    notes = all_notes
    if args.recent:
        notes = all_notes[-args.recent:]

    items: list[HarvestItem] = []
    for note in notes:
        harvested = harvest_note(note)
        for item in harvested:
            item.max_session = max_session
        items.extend(harvested)

    display(items, plain, max_session)


if __name__ == "__main__":
    main()
