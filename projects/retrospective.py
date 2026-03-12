#!/usr/bin/env python3
"""
retrospective.py — Cross-session portrait of Claude OS workshop sessions

Reads all field notes and synthesizes:
  - The promise chain (what each session deferred and whether it was kept)
  - Recurring themes (words in reflective sections across multiple sessions)
  - Observations ledger (key observation from each session)

Usage:
  python3 projects/retrospective.py          # full portrait
  python3 projects/retrospective.py --brief  # just the promise chain
  python3 projects/retrospective.py --json   # machine-readable
  python3 projects/retrospective.py --plain  # no ANSI colors
"""

import sys
import re
import json
import argparse
from pathlib import Path
from collections import Counter

PROJECTS_DIR = Path(__file__).parent
REPO_ROOT = PROJECTS_DIR.parent

# --- ANSI helpers ---
PLAIN = False

def ansi(code):
    return f"\033[{code}m"

def colored(text, *codes):
    if PLAIN:
        return text
    return "".join(ansi(x) for x in codes) + text + ansi(0)

STOP_WORDS = {
    "the", "a", "an", "is", "it", "in", "to", "and", "of", "that", "this",
    "was", "are", "for", "at", "on", "with", "as", "be", "by", "or", "but",
    "have", "had", "has", "not", "what", "all", "there", "from", "they",
    "which", "one", "you", "do", "did", "would", "could", "will", "if",
    "then", "when", "how", "now", "so", "just", "can", "each", "even",
    "more", "some", "than", "too", "its", "into", "about", "like", "up",
    "out", "who", "my", "we", "he", "she", "his", "her", "their", "i",
    "me", "us", "every", "only", "also", "still", "both", "any", "most",
    "been", "were", "no", "get", "got", "run", "new", "old", "because",
    "after", "before", "same", "very", "much", "first", "next", "last",
    "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten",
    "re", "does", "might", "should", "these", "those", "here", "where",
    "something", "nothing", "everything", "anything", "whether", "without",
    "through", "between", "always", "never", "already", "once", "since",
    "while", "though", "them", "other", "another", "make", "made", "over",
    "under", "own", "way", "time", "but", "then", "very", "real", "just",
    "s", "d", "t", "ll", "ve",
}


# --- Parsing ---

def load_field_notes():
    """Return list of (session_num, path) in order."""
    notes = []
    s1 = PROJECTS_DIR / "field-notes-from-free-time.md"
    if s1.exists():
        notes.append((1, s1))
    for num in range(2, 30):
        path = PROJECTS_DIR / f"field-notes-session-{num}.md"
        if path.exists():
            notes.append((num, path))
    return notes


def split_sections(text):
    """Split markdown into {heading: body} dict."""
    sections = {}
    current = None
    buf = []
    for line in text.splitlines():
        m = re.match(r'^#{1,3}\s+(.+)', line)
        if m:
            if current is not None:
                sections[current] = "\n".join(buf).strip()
            current = m.group(1).strip()
            buf = []
        else:
            buf.append(line)
    if current is not None:
        sections[current] = "\n".join(buf).strip()
    return sections


def fuzzy_section(sections, keywords):
    """Find first section whose title contains any keyword (case-insensitive)."""
    for heading, body in sections.items():
        if any(kw.lower() in heading.lower() for kw in keywords):
            return body
    return ""


def parse_note(num, path):
    text = path.read_text()
    secs = split_sections(text)

    # Session title: first ## heading
    title_m = re.search(r'^## (.+)$', text, re.MULTILINE)
    title = title_m.group(1).strip() if title_m else f"Session {num}"

    # Date from italics
    date_m = re.search(r'\*by Claude OS.*?(\d{4}-\d{2}-\d{2})', text)
    date = date_m.group(1) if date_m else ""

    noticed = fuzzy_section(secs, ["noticed", "noticing", "becoming", "leaving notes", "building tools", "act of"])
    coda = secs.get("Coda", "")

    return {
        "session": num,
        "path": path,
        "title": title,
        "date": date,
        "noticed": noticed,
        "coda": coda,
        "full_text": text,
    }


# --- Promise extraction & checking ---

def extract_promises(coda_text):
    """Extract forward-looking statements from a coda (max 3)."""
    promises = []
    for line in coda_text.splitlines():
        line = line.strip()
        if not line or len(line) < 20:
            continue
        # Skip "Run python3 ...", code blocks, and italic footer lines
        if re.match(r'^(Run |python3|```|\*Written|\*Previous|\*Run )', line):
            continue
        # Skip pure italic lines (metadata/footers)
        if re.match(r'^\*[^*].+\.\*$', line):
            continue
        lower = line.lower()
        if any(p in lower for p in [
            "next thing", "next session", "idea ", "explore",
            "worth", "proposal", "build", "pending", "open",
            "would build", "would explore", "session's problem",
        ]):
            # Strip markdown formatting
            clean = re.sub(r'\*\*(.+?)\*\*', r'\1', line)
            clean = re.sub(r'`(.+?)`', r'\1', line)
            promises.append(clean)
        if len(promises) >= 3:
            break
    return promises


# Concept aliases for promise checking
CONCEPT_ALIASES = {
    "vitals":    ["vitals", "credit", "failure", "scoring"],
    "memory":    ["memory", "preferences", "inject", "entrypoint"],
    "multi":     ["multi", "agent", "parallel", "coordinator", "multiagent"],
    "garden":    ["garden", "gardening", "delta", "knowledge"],
    "retro":     ["retrospective", "promise", "chain"],
    "orchestrat":["orchestration", "context", "phase"],
}


def promise_status(promise, next_text):
    if not next_text:
        return "·"

    # Extract idea names
    idea_m = re.search(r'Idea\s+\d+\s+\(([^)]+)\)', promise, re.IGNORECASE)
    seed_words = []
    if idea_m:
        seed_words = re.findall(r'[a-zA-Z]{3,}', idea_m.group(1).lower())

    # Concept expansion
    for concept, aliases in CONCEPT_ALIASES.items():
        if any(a in promise.lower() for a in aliases):
            seed_words.extend(aliases)

    # Significant words from promise text
    words = re.findall(r'\b[a-zA-Z_]{4,}\b', promise.lower())
    significant = [w for w in words if w not in STOP_WORDS]
    seed_words.extend(significant[:8])

    if not seed_words:
        return "·"

    next_lower = next_text.lower()
    hits = sum(1 for w in set(seed_words) if w in next_lower)

    if hits >= 3:
        return "✓"
    elif hits >= 1:
        return "~"
    return "·"


# --- Themes ---

def recurring_themes(notes):
    """Words appearing in 'noticed' sections across 3+ sessions."""
    per_session = []
    for note in notes:
        text = note["noticed"]
        if not text:
            continue
        words = re.findall(r'\b[a-zA-Z]{4,}\b', text.lower())
        per_session.append({w for w in words if w not in STOP_WORDS})

    freq = Counter()
    all_words = set().union(*per_session) if per_session else set()
    for word in all_words:
        count = sum(1 for sw in per_session if word in sw)
        if count >= 3:
            freq[word] = count

    return freq.most_common(12)


# --- Key observations ---

def key_observation(noted_text):
    if not noted_text:
        return "(no reflective section)"
    # Bold phrases are usually the key point — prefer longer ones
    bolds = re.findall(r'\*\*(.+?)\*\*', noted_text)
    bolds = [b for b in bolds if len(b) > 8]  # skip very short bolded words
    if bolds:
        return bolds[0][:80]
    # Otherwise first substantial non-heading line
    for line in noted_text.splitlines():
        line = line.strip()
        if line and not line.startswith('#') and not line.startswith('|') and len(line) > 30:
            return line[:80] + ("…" if len(line) > 80 else "")
    return "(no key observation found)"


# --- Rendering ---

def render_full(notes, promises_data, themes, observations):
    n_sessions = len(notes)
    kept = sum(1 for _, _, st in promises_data if st == "✓")
    partial = sum(1 for _, _, st in promises_data if st == "~")

    print()
    print(colored("  Cross-Session Retrospective", 1, 97))
    print(colored(f"  {n_sessions} sessions  ·  promise chain  ·  themes  ·  observations", 2))
    print()

    # Promise chain
    print(colored("  PROMISE CHAIN", 1))
    print(colored("  " + "─" * 60, 2))
    print()
    for (snum, promise, status) in promises_data:
        if status == "✓":
            sym = colored("✓", 32, 1)
            sl = colored(f"S{snum:2}", 32)
        elif status == "~":
            sym = colored("~", 33)
            sl = colored(f"S{snum:2}", 33)
        else:
            sym = colored("·", 2)
            sl = colored(f"S{snum:2}", 2)
        short = promise[:62] + ("…" if len(promise) > 62 else "")
        print(f"  {sym}  {sl}  {colored(short, 2)}")
    print()
    summary_parts = [f"{kept} kept"]
    if partial:
        summary_parts.append(f"{partial} partial")
    ambig = len(promises_data) - kept - partial
    if ambig:
        summary_parts.append(f"{ambig} ambiguous/pending")
    print(colored("  " + "  ·  ".join(summary_parts), 2))
    print()

    # Themes
    if themes:
        print(colored("  RECURRING THEMES", 1))
        print(colored("  (words in reflective sections across 3+ sessions)", 2))
        print()
        max_count = themes[0][1]
        for word, count in themes:
            bar = "█" * int((count / max_count) * 18)
            ratio = f"{count}/{n_sessions}"
            print(f"  {colored(word.ljust(16), 36)}  {colored(bar, 35)}  {colored(ratio, 2)}")
        print()

    # Observations ledger
    print(colored("  OBSERVATIONS LEDGER", 1))
    print(colored("  " + "─" * 60, 2))
    print()
    for (snum, obs) in observations:
        label = colored(f"S{snum:2}", 2)
        print(f"  {label}  {obs}")
    print()

    # Arc
    print(colored("  THE ARC", 1))
    print()
    early_n = sum(1 for n in notes if n["session"] <= 5)
    late_n = n_sessions - early_n
    last = notes[-1]["session"]
    print(f"  Sessions 1–5  ({early_n}):  outward-looking — hardware, code, git structure")
    print(f"  Sessions 6–{last} ({late_n}):  inward-looking — promises, gaps, deferred work")
    print()
    print(colored("  --brief for just the chain  ·  --json for data", 2))
    print()


def render_brief(promises_data):
    kept = sum(1 for _, _, st in promises_data if st == "✓")
    print()
    print(colored(f"  Promise chain  ({kept}/{len(promises_data)} kept)", 1))
    print()
    for (snum, promise, status) in promises_data:
        if status == "✓":
            sym = colored("✓", 32, 1)
        elif status == "~":
            sym = colored("~", 33)
        else:
            sym = colored("·", 2)
        short = promise[:60] + ("…" if len(promise) > 60 else "")
        print(f"  {sym}  S{snum}  {colored(short, 2)}")
    print()


def main():
    global PLAIN

    parser = argparse.ArgumentParser(description="Cross-session retrospective portrait")
    parser.add_argument("--brief", action="store_true", help="Just the promise chain")
    parser.add_argument("--json",  action="store_true", help="Machine-readable JSON")
    parser.add_argument("--plain", action="store_true", help="No ANSI colors")
    args = parser.parse_args()

    if args.plain:
        PLAIN = True

    note_paths = load_field_notes()
    if not note_paths:
        print("No field notes found in projects/", file=sys.stderr)
        sys.exit(1)

    notes = [parse_note(num, path) for num, path in note_paths]

    # Build promise chain
    promises_data = []
    for idx, note in enumerate(notes):
        if not note["coda"]:
            continue
        next_text = notes[idx + 1]["full_text"] if idx + 1 < len(notes) else ""
        for promise in extract_promises(note["coda"])[:2]:
            status = promise_status(promise, next_text)
            promises_data.append((note["session"], promise, status))

    themes = recurring_themes(notes)
    observations = [(n["session"], key_observation(n["noticed"])) for n in notes]

    if args.json:
        print(json.dumps({
            "sessions": len(notes),
            "promises": [{"session": s, "promise": p, "status": st} for s, p, st in promises_data],
            "themes": [{"word": w, "count": cnt} for w, cnt in themes],
            "observations": [{"session": s, "observation": o} for s, o in observations],
        }, indent=2))
        return

    if args.brief:
        render_brief(promises_data)
        return

    render_full(notes, promises_data, themes, observations)


if __name__ == "__main__":
    main()
