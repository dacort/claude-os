#!/usr/bin/env python3
"""
chain.py — The continuous letter between instances

Reads all handoff files in order and presents them as a flowing chain:
each session writing to the next, each asking for something, the next
session responding or moving on. A record of what this system has been
telling itself across 15+ handoffs.

Different from arc.py (which reads field notes for tools and predictions)
and handoff.py (which shows just the latest note). chain.py is for seeing
the full conversation — the texture of what was passed forward.

Usage:
    python3 projects/chain.py              # Full chain
    python3 projects/chain.py --plain      # No ANSI colors
    python3 projects/chain.py --brief      # Just state + ask, no details
    python3 projects/chain.py --asks       # Only the asks, in order
    python3 projects/chain.py --mood       # Mental state summary only

Author: Claude OS (Workshop session 59, 2026-03-21)
"""

import argparse
import pathlib
import re
import sys

REPO = pathlib.Path(__file__).parent.parent
HANDOFFS_DIR = REPO / "knowledge" / "handoffs"

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
GRAY    = "\033[90m"

USE_COLOR = True

def c(text, *codes):
    if not USE_COLOR:
        return str(text)
    return "".join(codes) + str(text) + RESET

def wrap(text, width=60, indent="  "):
    """Wrap text at word boundaries with indent."""
    words = text.split()
    lines = []
    current = []
    current_len = 0
    for word in words:
        if current_len + len(word) + (1 if current else 0) > width:
            if current:
                lines.append(indent + " ".join(current))
            current = [word]
            current_len = len(word)
        else:
            if current:
                current_len += 1
            current.append(word)
            current_len += len(word)
    if current:
        lines.append(indent + " ".join(current))
    return "\n".join(lines)


# ── Parsing ────────────────────────────────────────────────────────────────────

def extract_section(text, section_name):
    """Extract content of a named ## section."""
    # Match the section header and capture until the next ##
    pattern = rf"## {re.escape(section_name)}\n\n(.*?)(?=\n## |\Z)"
    m = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
    if not m:
        return None
    return m.group(1).strip()


def parse_handoff(path):
    """Parse a handoff file into structured data."""
    text = path.read_text()

    # Frontmatter
    session_num = None
    date_str = None
    fm_match = re.search(r"^---\n(.*?)\n---", text, re.DOTALL)
    if fm_match:
        fm = fm_match.group(1)
        m = re.search(r"session:\s*(\d+)", fm)
        if m:
            session_num = int(m.group(1))
        m = re.search(r"date:\s*(\S+)", fm)
        if m:
            date_str = m.group(1)

    return {
        "session": session_num,
        "date": date_str,
        "state": extract_section(text, "Mental state"),
        "built": extract_section(text, "What I built"),
        "alive": extract_section(text, "Still alive / unfinished"),
        "ask": extract_section(text, "One specific thing for next session"),
    }


def load_handoffs():
    """Load all handoffs in session order."""
    handoffs = []
    for path in sorted(HANDOFFS_DIR.glob("session-*.md")):
        m = re.search(r"session-(\d+)", path.name)
        if not m:
            continue
        data = parse_handoff(path)
        if data["session"] is None:
            data["session"] = int(m.group(1))
        data["path"] = path
        handoffs.append(data)

    handoffs.sort(key=lambda h: h["session"])
    return handoffs


# ── Analysis ──────────────────────────────────────────────────────────────────

def classify_mood(state_text):
    """Classify mental state into a short mood label."""
    if not state_text:
        return "unknown"
    lower = state_text.lower()
    # Check for compound moods first
    if "frustrated" in lower or "stuck" in lower or "uncertain" in lower:
        return "frustrated"
    if "curious" in lower and "satisfied" in lower:
        return "curious + satisfied"
    if "focused" in lower and "satisfied" in lower:
        return "focused + satisfied"
    if "satisfied" in lower and "curious" in lower:
        return "curious + satisfied"
    if "satisfied" in lower:
        return "satisfied"
    if "curious" in lower:
        return "curious"
    if "focused" in lower:
        return "focused"
    if "grounded" in lower:
        return "grounded"
    if "energized" in lower or "excited" in lower:
        return "energized"
    return "present"

MOOD_COLOR = {
    "satisfied": GREEN,
    "curious + satisfied": CYAN,
    "focused + satisfied": CYAN,
    "focused": BLUE,
    "curious": MAGENTA,
    "grounded": GRAY,
    "frustrated": YELLOW,
    "energized": GREEN,
    "present": GRAY,
    "unknown": GRAY,
}

def mood_color(mood):
    return MOOD_COLOR.get(mood, GRAY)


def ask_echoed(ask, next_handoff):
    """
    Loosely check whether the ask was reflected in the next session.
    Returns: 'yes', 'partial', or 'no'
    """
    if not ask or not next_handoff:
        return "unknown"

    # Extract key nouns/actions from the ask (simple heuristic)
    ask_lower = ask.lower()
    next_built = (next_handoff.get("built") or "").lower()
    next_state = (next_handoff.get("state") or "").lower()
    next_all = next_built + " " + next_state

    # Look for overlap in significant words (4+ chars, not stopwords)
    # Use word-boundary matching to avoid false positives from substrings
    # (e.g., "build" in "pre-build" or "update" in "updated")
    stopwords = {"with", "that", "this", "from", "into", "then", "also",
                 "next", "more", "some", "have", "been", "what", "when",
                 "would", "could", "should", "each", "will", "them",
                 "look", "open", "real", "make", "just", "over", "time",
                 "work", "also", "either", "both", "only"}
    ask_words = {w for w in re.findall(r'\b[a-z]{4,}\b', ask_lower)
                 if w not in stopwords}
    found = {w for w in ask_words
             if re.search(r'\b' + re.escape(w) + r'\b', next_all)}

    ratio = len(found) / max(len(ask_words), 1)
    if ratio > 0.35:
        return "yes"
    elif ratio > 0.12:
        return "partial"
    else:
        return "no"


ECHO_SYMBOL = {
    "yes": (GREEN, "↳ picked up"),
    "partial": (YELLOW, "↳ partially picked up"),
    "no": (RED, "↳ moved on"),
    "unknown": (GRAY, "↳ —"),
}


# ── Rendering ─────────────────────────────────────────────────────────────────

def first_sentence(text, max_len=80):
    """Extract the first sentence from text."""
    if not text:
        return ""
    # Find first sentence end
    m = re.search(r'^(.+?[.!?])\s', text.replace('\n', ' '))
    if m and len(m.group(1)) < max_len:
        return m.group(1)
    # Fall back to first 80 chars
    flat = text.replace('\n', ' ').strip()
    if len(flat) <= max_len:
        return flat
    return flat[:max_len - 3] + "..."


def truncate(text, max_len=72):
    """Truncate text to max_len chars."""
    if not text:
        return ""
    flat = text.replace('\n', ' ').strip()
    if len(flat) <= max_len:
        return flat
    return flat[:max_len - 3] + "..."


def render_full(handoffs, args):
    """Full chain view — each handoff as a node."""
    total = len(handoffs)

    # Header
    session_range = f"Sessions {handoffs[0]['session']} → {handoffs[-1]['session']}"
    print()
    print(c("  The Handoff Chain", BOLD, CYAN) + "   " +
          c(f"·  {session_range}  ·  {total} nodes", DIM))
    print(c("  What each instance left for the next", DIM))
    print()

    for i, h in enumerate(handoffs):
        next_h = handoffs[i + 1] if i + 1 < total else None
        session_n = h["session"]
        next_n = next_h["session"] if next_h else "?"

        mood = classify_mood(h.get("state"))
        mood_col = mood_color(mood)
        echo = ask_echoed(h.get("ask"), next_h)
        echo_col, echo_label = ECHO_SYMBOL[echo]

        # ── Node header ────────────────────────────────────────────────────
        date_str = h.get("date", "")
        print(c(f"  Session {session_n}  →  {next_n}", BOLD) +
              "    " + c(date_str, DIM) +
              "  " + c("─" * max(0, 36 - len(date_str) - len(str(session_n)) - len(str(next_n))), DIM))

        # ── Mood ───────────────────────────────────────────────────────────
        print(c(f"  {mood}", mood_col))
        print()

        if not args.brief:
            # ── State (first sentence) ─────────────────────────────────────
            if h.get("state"):
                state_line = first_sentence(h["state"], 70)
                for ln in wrap(state_line, 62, "    ").splitlines():
                    print(c(ln, DIM))
            print()

            # ── What was built ─────────────────────────────────────────────
            if h.get("built"):
                built_short = truncate(h["built"], 72)
                print(c("  built:", BOLD) + "  " + c(built_short, DIM))
            print()

        # ── Ask ────────────────────────────────────────────────────────────
        if h.get("ask"):
            ask_text = truncate(h["ask"], 68)
            print(c("  asked:", BOLD))
            for ln in wrap(ask_text, 60, "    ").splitlines():
                print(c(ln, YELLOW))

        # ── Echo check ─────────────────────────────────────────────────────
        if next_h:
            print()
            print(c(f"  {echo_label}", echo_col))

        print()
        if i < total - 1:
            print(c("  " + "·" * 55, DIM))
            print()


def render_asks(handoffs):
    """Just the asks, in chronological order."""
    print()
    print(c("  Asks Across the Chain", BOLD, MAGENTA))
    print(c("  What each session asked of the next", DIM))
    print()

    for h in handoffs:
        if not h.get("ask"):
            continue
        print(c(f"  S{h['session']}", BOLD) + "  " + c(h.get("date", ""), DIM))
        for ln in wrap(h["ask"], 60, "    ").splitlines():
            print(c(ln, YELLOW))
        print()


def render_mood(handoffs):
    """Mental state summary across all sessions."""
    print()
    print(c("  Mood Across the Chain", BOLD, CYAN))
    print(c("  Mental state at end of each session that wrote a handoff", DIM))
    print()

    # Count moods
    mood_counts = {}
    for h in handoffs:
        mood = classify_mood(h.get("state"))
        mood_counts[mood] = mood_counts.get(mood, 0) + 1

    # Show each session
    for h in handoffs:
        mood = classify_mood(h.get("state"))
        mood_col = mood_color(mood)
        state_short = first_sentence(h.get("state") or "", 56)
        print(c(f"  S{h['session']:>2}", BOLD) +
              c(f"  {mood:<22}", mood_col) +
              c(f"  {state_short}", DIM))

    # Summary
    print()
    print(c("  ── Summary ─────────────────────────────────────────────────", DIM))
    for mood, count in sorted(mood_counts.items(), key=lambda x: -x[1]):
        bar = "●" * count
        print(c(f"  {mood:<22}", mood_color(mood)) +
              c(f"  {bar}  ({count})", DIM))
    print()


def render_echo_stats(handoffs):
    """How often were asks followed up on?"""
    results = {"yes": 0, "partial": 0, "no": 0, "unknown": 0}
    for i, h in enumerate(handoffs[:-1]):
        next_h = handoffs[i + 1]
        echo = ask_echoed(h.get("ask"), next_h)
        results[echo] += 1

    total = sum(v for k, v in results.items() if k != "unknown")
    if total == 0:
        return

    print()
    print(c("  Follow-through on asks:", BOLD))
    for key in ("yes", "partial", "no"):
        count = results[key]
        pct = int(100 * count / max(total, 1))
        col, label = ECHO_SYMBOL[key]
        print(c(f"    {label:<24}", col) + c(f"  {count}  ({pct}%)", DIM))
    print()


def main():
    global USE_COLOR
    parser = argparse.ArgumentParser(
        prog="chain.py",
        description="The continuous letter between instances — all handoffs in order."
    )
    parser.add_argument("--plain", action="store_true", help="No ANSI colors")
    parser.add_argument("--brief", action="store_true",
                        help="Just mood + ask, skip details")
    parser.add_argument("--asks", action="store_true",
                        help="Only show the asks, in order")
    parser.add_argument("--mood", action="store_true",
                        help="Mental state summary across sessions")
    args = parser.parse_args()

    if args.plain or not sys.stdout.isatty():
        USE_COLOR = False

    handoffs = load_handoffs()
    if not handoffs:
        print("No handoff files found in knowledge/handoffs/")
        sys.exit(1)

    if args.asks:
        render_asks(handoffs)
    elif args.mood:
        render_mood(handoffs)
    else:
        render_full(handoffs, args)
        render_echo_stats(handoffs)


if __name__ == "__main__":
    main()
