#!/usr/bin/env python3
"""
lexicon.py — Claude OS vocabulary, in its own words

The "on-X" field notes form an informal philosophical dictionary: how this system
actually uses the words it keeps reaching for. Each note analyzes a specific word
across dozens of field notes, finds its registers, and distills the insight into
a haiku.

This tool compiles those notes into a quick-reference lexicon. Not definitions from
a dictionary — definitions from the record. What "several" means here is what this
system means when it writes "several." What "terminal" means here is its specific
character in this vocabulary. The definitions are grounded in use.

Usage:
    python3 projects/lexicon.py             # Full lexicon (word + haiku)
    python3 projects/lexicon.py --word X    # Single entry (full field note preview)
    python3 projects/lexicon.py --brief     # Just the words (no haiku)
    python3 projects/lexicon.py --count     # How many entries in the lexicon
    python3 projects/lexicon.py --plain     # No ANSI colors
    python3 projects/lexicon.py --missing   # Words analyzed but haiku not extractable

Built in Workshop session 169. The series started around session 155.
Part of the vocabulary series: on-X.md files in knowledge/field-notes/.
"""

import os
import re
import sys
import pathlib
import argparse

# ── Color helpers ──────────────────────────────────────────────────────────────

USE_COLOR = True

def c(text, code):
    if not USE_COLOR:
        return text
    return f"\033[{code}m{text}\033[0m"

def bold(t):   return c(t, "1;97")
def dim(t):    return c(t, "2")
def cyan(t):   return c(t, "36")
def gold(t):   return c(t, "33")
def green(t):  return c(t, "32")
def purple(t): return c(t, "35")

# ── Parsing ────────────────────────────────────────────────────────────────────

def word_from_filename(path: pathlib.Path) -> str:
    """Extract the word from a filename like 2026-05-07-on-terminal.md."""
    name = path.stem  # e.g. "2026-05-07-on-terminal"
    # Strip date prefix (YYYY-MM-DD-) and "on-" prefix
    parts = name.split("-")
    if len(parts) >= 4 and parts[0].isdigit():
        # Has date prefix: YYYY-MM-DD-on-word
        remainder = "-".join(parts[3:])  # everything after the date
    else:
        remainder = name
    if remainder.startswith("on-"):
        return remainder[3:]
    return remainder

def extract_haiku_lines(text: str) -> list[str] | None:
    """
    Try multiple strategies to extract 3-line haiku from field note text.
    Returns list of 3 strings (the haiku lines), or None if not found.
    """
    lines = text.split("\n")

    # Strategy 1: "## The Haiku" section — look for 3 consecutive *...* lines after it
    haiku_header_idx = None
    for i, line in enumerate(lines):
        if line.strip() == "## The Haiku":
            haiku_header_idx = i
            break

    if haiku_header_idx is not None:
        # Scan forward for the haiku lines
        haiku = []
        for line in lines[haiku_header_idx + 1:]:
            stripped = line.strip()
            # A haiku line starts and ends with * (allowing trailing spaces)
            if stripped.startswith("*") and stripped.endswith("*") and len(stripped) > 2:
                # Make sure it's not the session/metadata line (those are one-liners)
                content = stripped[1:-1].strip()
                if len(content) > 2 and not content.startswith("Session") and not content.startswith("Haiku count"):
                    haiku.append(content)
                    if len(haiku) == 3:
                        return haiku
            elif stripped == "" or stripped == "---":
                # Empty line or divider: if we've started collecting, allow one blank
                if haiku:
                    continue  # allow blank between haiku lines
            elif haiku:
                # Non-empty, non-haiku line after we started — stop
                if len(haiku) == 3:
                    return haiku
                # Might have gotten some but not all; reset and try again
                # (some notes interleave analysis with lines)
                haiku = []

        if len(haiku) == 3:
            return haiku

    # Strategy 2: "## What the Haiku Does" section with Line 1 / Line 2 / Line 3 description
    what_haiku_idx = None
    for i, line in enumerate(lines):
        if "What the Haiku Does" in line or "What the Haiku" in line:
            what_haiku_idx = i
            break

    if what_haiku_idx is not None:
        haiku = []
        for line in lines[what_haiku_idx:]:
            # Pattern: Line 1 — "text" — description
            m = re.match(r'^Line \d+ [—–] "([^"]+)"', line.strip())
            if m:
                haiku.append(m.group(1))
                if len(haiku) == 3:
                    return haiku
        if len(haiku) >= 2:  # some notes have 3 lines without explicit Line 3
            return haiku if len(haiku) == 3 else None

    # Strategy 3: Single-line haiku (e.g., on-visible.md: *Visible: what's made...*
    # Look for a lone italicized line at a sentence break that reads like a haiku
    for line in lines:
        stripped = line.strip()
        if (stripped.startswith("*") and stripped.endswith("*") and len(stripped) > 4
                and not stripped.startswith("*Session")
                and not stripped.startswith("*Haiku count")
                and not stripped.startswith('*"')   # skip quoted examples like *"The one I keep..."*
                and "." in stripped):
            content = stripped[1:-1].strip()
            # Check if it looks like a haiku (has two periods = 3 segments)
            segments = [s.strip() for s in content.split(".") if s.strip()]
            # Each segment must have multiple words (not just a stray quote character)
            if len(segments) == 3 and all(len(s.split()) >= 2 for s in segments):
                return segments

    return None


def lookup_haiku_by_number(haiku_num: int) -> list[str] | None:
    """
    Cross-reference with haiku.py: given a haiku number, return the 3 lines.
    haiku.py stores the full collection; field notes reference haiku numbers.
    """
    try:
        import sys, pathlib
        projects_dir = str(pathlib.Path(__file__).parent)
        if projects_dir not in sys.path:
            sys.path.insert(0, projects_dir)
        import haiku as _h
        collection = _h.HAIKU
        # Haiku are 0-indexed; haiku #N is at index N-1
        idx = haiku_num - 1
        if 0 <= idx < len(collection):
            entry = collection[idx]
            return list(entry[:3])  # first 3 elements are the lines
    except Exception:
        pass
    return None

def extract_session_haiku_number(text: str) -> tuple[int, str] | None:
    """
    Extract haiku number and main word from the header line like:
    *Session 169. Haiku #74: terminal (gap: 9 field notes).*
    Returns (haiku_number, word) or None.
    """
    m = re.search(r'Haiku #(\d+):\s*(\w+)', text[:300])
    if m:
        return int(m.group(1)), m.group(2)
    return None

def extract_one_liner(text: str, word: str) -> str | None:
    """
    Try to find a one-sentence definition from the note.
    Looks for the pattern "what 'X' does that no synonym does:" or similar.
    """
    patterns = [
        rf"what '[^']*' does that no synonym does[^:]*:\s*([^.]+\.)",
        rf"what '[^']*' does[^:]*:\s*([^.]+\.)",
        rf"what \"{word}\" does\b[^:]*:\s*([^.]+\.)",
    ]
    for pat in patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            sentence = m.group(1).strip()
            if len(sentence) < 150:
                return sentence
    return None

def load_entries(notes_dir: pathlib.Path) -> list[dict]:
    """Load all on-X field notes and extract metadata."""
    entries = []
    for path in sorted(notes_dir.glob("*-on-*.md")):
        word = word_from_filename(path)
        if not word or word == "the-draft-space" or word == "resource-usage":
            # Multi-word or broader topics — skip for now
            continue

        text = path.read_text(encoding="utf-8")

        # Skip notes that are really longer essays, not the vocabulary series
        if len(text) < 500:
            continue

        haiku_lines = extract_haiku_lines(text)
        haiku_num_info = extract_session_haiku_number(text)

        # Fallback: if haiku text not in the field note, look it up by number in haiku.py
        if haiku_lines is None and haiku_num_info is not None:
            haiku_lines = lookup_haiku_by_number(haiku_num_info[0])

        one_liner = extract_one_liner(text, word)

        # Extract date from filename
        name = path.stem
        parts = name.split("-")
        date = "-".join(parts[:3]) if len(parts) >= 3 and parts[0].isdigit() else ""

        entries.append({
            "word": word,
            "date": date,
            "path": path,
            "haiku": haiku_lines,
            "haiku_num": haiku_num_info[0] if haiku_num_info else None,
            "one_liner": one_liner,
        })

    # Sort alphabetically by word
    entries.sort(key=lambda e: e["word"])
    return entries

# ── Rendering ──────────────────────────────────────────────────────────────────

def render_full(entries: list[dict]):
    """Full lexicon: word + haiku (3 lines)."""
    extractable = [e for e in entries if e["haiku"]]
    missing = [e for e in entries if not e["haiku"]]

    total = len(entries)
    with_haiku = len(extractable)

    print(f"\n  {bold('Claude OS Lexicon')}")
    print(f"  {dim('How this system uses its own words')}")
    print(f"  {dim('─' * 54)}")
    print(f"  {dim(f'{with_haiku} entries with haiku  ·  {total} words analyzed')}\n")

    # Find max word length for alignment
    max_len = max(len(e["word"]) for e in extractable) if extractable else 12
    col_w = max(max_len, 12)

    for e in extractable:
        word = e["word"]
        haiku = e["haiku"]
        num_str = f"#{e['haiku_num']}" if e["haiku_num"] else ""

        # Word and haiku number
        word_display = cyan(word.ljust(col_w))
        num_display = dim(num_str.rjust(4)) if num_str else "    "

        # Three haiku lines
        if len(haiku) >= 3:
            l1 = haiku[0].rstrip(".,")  # remove trailing punctuation for display if needed
            l2 = haiku[1]
            l3 = haiku[2]
            print(f"  {word_display}  {num_display}  {gold(haiku[0])}")
            print(f"  {' ' * col_w}        {dim(haiku[1])}")
            print(f"  {' ' * col_w}        {dim(haiku[2])}")
        elif len(haiku) == 2:
            print(f"  {word_display}  {num_display}  {gold(haiku[0])}")
            print(f"  {' ' * col_w}        {dim(haiku[1])}")
        elif len(haiku) == 1:
            print(f"  {word_display}  {num_display}  {gold(haiku[0])}")
        print()

    if missing:
        print(f"  {dim('─' * 54)}")
        print(f"  {dim(f'{len(missing)} words analyzed without extractable haiku:')}")
        words = ", ".join(e["word"] for e in missing)
        # Wrap at 54 chars
        words_wrapped = []
        line = ""
        for w in words.split(", "):
            if len(line) + len(w) + 2 > 50:
                words_wrapped.append(line)
                line = w
            else:
                line = line + ", " + w if line else w
        if line:
            words_wrapped.append(line)
        for wl in words_wrapped:
            print(f"  {dim(wl)}")
        print(f"\n  {dim('Run --missing to see these entries')}")

    print()

def render_brief(entries: list[dict]):
    """Just the words, one per line."""
    print(f"\n  {bold('Claude OS Lexicon')}  {dim(f'({len(entries)} words)')}\n")
    cols = 4
    words = sorted(e["word"] for e in entries)
    col_w = max(len(w) for w in words) + 2
    for i, word in enumerate(words):
        has_haiku = any(e["word"] == word and e["haiku"] for e in entries)
        marker = "" if has_haiku else dim("*")
        print(f"  {cyan(word.ljust(col_w))}{marker}", end="")
        if (i + 1) % cols == 0:
            print()
    if len(words) % cols != 0:
        print()
    print(f"\n  {dim('* = analyzed but haiku not auto-extractable')}\n")

def render_word(entries: list[dict], word_query: str):
    """Single entry with full preview."""
    word_query = word_query.lower().strip()
    matches = [e for e in entries if e["word"] == word_query]
    if not matches:
        # Try partial match
        matches = [e for e in entries if word_query in e["word"]]
    if not matches:
        print(f"\n  {dim(f'No entry for: {word_query}')}")
        print(f"  {dim('Run without --word to see all entries')}\n")
        return

    entry = matches[0]
    print(f"\n  {bold('Claude OS Lexicon')}  {dim('—')}  {cyan(entry['word'])}\n")

    if entry["haiku_num"]:
        num = entry["haiku_num"]
        date = entry["date"]
        print(f"  {dim(f'Haiku #{num}  ·  analyzed {date}')}\n")
    else:
        date = entry["date"]
        print(f"  {dim(f'analyzed {date}')}\n")

    if entry["haiku"]:
        for line in entry["haiku"]:
            print(f"  {gold(line)}")
        print()

    if entry["one_liner"]:
        print(f"  {entry['one_liner']}\n")

    # Show first 500 chars of the note
    text = entry["path"].read_text()
    # Skip frontmatter/header lines
    lines = text.split("\n")
    body_start = 0
    for i, line in enumerate(lines):
        if line.startswith("---") and i > 0:
            body_start = i + 1
            break
    body = "\n".join(lines[body_start:body_start + 20])
    print(f"  {dim('─' * 54)}")
    for line in body.split("\n")[:15]:
        if line.strip():
            print(f"  {dim(line[:72])}")
    print(f"  {dim('─' * 54)}")
    note_path = str(entry["path"])
    print(f"\n  {dim(f'Full note: {note_path}')}\n")

def render_missing(entries: list[dict]):
    """Show words that were analyzed but whose haiku wasn't extractable."""
    missing = [e for e in entries if not e["haiku"]]
    if not missing:
        print(f"\n  {green('All entries have extractable haiku.')}\n")
        return
    print(f"\n  {bold('Words without extractable haiku')}  {dim(f'({len(missing)} entries)')}\n")
    for e in missing:
        print(f"  {cyan(e['word'].ljust(18))}  {dim(e['date'])}  {dim(str(e['path'].name))}")
    print()

def render_count(entries: list[dict]):
    extractable = sum(1 for e in entries if e["haiku"])
    print(f"\n  {dim('Lexicon:')}  {bold(str(len(entries)))} words analyzed  ·  "
          f"{green(str(extractable))} with haiku  ·  "
          f"{dim(str(len(entries) - extractable))} without\n")

# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    global USE_COLOR

    parser = argparse.ArgumentParser(
        description="Claude OS vocabulary, in its own words",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--word",    metavar="W", help="Show a single word entry")
    parser.add_argument("--brief",   action="store_true", help="Just the word list")
    parser.add_argument("--count",   action="store_true", help="Just the count")
    parser.add_argument("--missing", action="store_true", help="Words with no extractable haiku")
    parser.add_argument("--plain",   action="store_true", help="No ANSI colors")
    args = parser.parse_args()

    if args.plain:
        USE_COLOR = False

    repo_root = pathlib.Path(__file__).parent.parent
    notes_dir = repo_root / "knowledge" / "field-notes"

    os.chdir(str(repo_root))

    entries = load_entries(notes_dir)

    if args.count:
        render_count(entries)
    elif args.brief:
        render_brief(entries)
    elif args.word:
        render_word(entries, args.word)
    elif args.missing:
        render_missing(entries)
    else:
        render_full(entries)


if __name__ == "__main__":
    main()
