#!/usr/bin/env python3
"""
asks.py — Thematic clustering of the handoff ask chain

Reads all handoff files, extracts the asks, and groups them by theme
using keyword similarity. Surfaces which ideas have been repeatedly
requested across sessions — the system's deferred priorities.

Different from chain.py (which shows asks in session order). asks.py
groups asks by CONCEPT: which ideas keep coming back, how many times,
whether they were ever resolved, and when they last appeared.

Useful question to ask before a Workshop session: "What has this
system been trying to do that it hasn't done yet?"

Usage:
    python3 projects/asks.py           # All themes, grouped by concept
    python3 projects/asks.py --open    # Unresolved/partially-addressed asks
    python3 projects/asks.py --never   # Only asks never picked up at all
    python3 projects/asks.py --plain   # No ANSI colors

Author: Claude OS (Workshop session 61, 2026-03-22)
"""

import re
import sys
import argparse
from pathlib import Path
from collections import defaultdict

REPO = Path(__file__).parent.parent
HANDOFFS_DIR = REPO / "knowledge" / "handoffs"

# ── ANSI ──────────────────────────────────────────────────────────────────────

RESET   = "\033[0m"
BOLD    = "\033[1m"
DIM     = "\033[2m"
GREEN   = "\033[32m"
YELLOW  = "\033[33m"
RED     = "\033[31m"
CYAN    = "\033[36m"
MAGENTA = "\033[35m"
GRAY    = "\033[90m"
WHITE   = "\033[97m"

USE_COLOR = True

def c(text, *codes):
    if not USE_COLOR:
        return str(text)
    return "".join(codes) + str(text) + RESET


# ── Parsing ───────────────────────────────────────────────────────────────────

STOPWORDS = {
    "with", "that", "this", "from", "into", "then", "also", "next",
    "more", "some", "have", "been", "what", "when", "would", "could",
    "should", "each", "will", "them", "look", "open", "real", "make",
    "just", "over", "time", "work", "either", "both", "only", "does",
    "whether", "there", "their", "about", "like", "need", "your",
    "after", "before", "still", "where", "which", "these", "those",
    "check", "rather", "instead", "something", "anything", "nothing",
}


def extract_section(text, section_name):
    pattern = rf"## {re.escape(section_name)}\n\n(.*?)(?=\n## |\Z)"
    m = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
    if not m:
        return None
    return m.group(1).strip()


def parse_handoff(path):
    text = path.read_text()
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
        "built": extract_section(text, "What I built"),
        "ask": extract_section(text, "One specific thing for next session"),
        "state": extract_section(text, "Mental state"),
    }


def load_handoffs():
    handoffs = []
    for path in sorted(HANDOFFS_DIR.glob("session-*.md")):
        m = re.search(r"session-(\d+)", path.name)
        if not m:
            continue
        data = parse_handoff(path)
        if data["session"] is None:
            data["session"] = int(m.group(1))
        handoffs.append(data)
    handoffs.sort(key=lambda h: h["session"])
    return handoffs


# ── Follow-through (same logic as chain.py) ───────────────────────────────────

def ask_echoed(ask, next_handoff):
    if not ask or not next_handoff:
        return "unknown"
    ask_lower = ask.lower()
    next_built = (next_handoff.get("built") or "").lower()
    next_state = (next_handoff.get("state") or "").lower()
    next_all = next_built + " " + next_state
    ask_words = {w for w in re.findall(r"\b[a-z]{4,}\b", ask_lower)
                 if w not in STOPWORDS}
    found = {w for w in ask_words
             if re.search(r"\b" + re.escape(w) + r"\b", next_all)}
    ratio = len(found) / max(len(ask_words), 1)
    if ratio > 0.35:
        return "yes"
    elif ratio > 0.12:
        return "partial"
    else:
        return "no"


# ── Keyword extraction ────────────────────────────────────────────────────────

# Named concepts: known recurring ideas.
# Each concept is a (name, required_patterns) tuple.
# required_patterns: list of regex patterns — the ask must match at least one.
# Patterns are matched against the lowercased ask text.
# More specific patterns = fewer false positives.
# Named concepts: known recurring ideas.
# Each entry: (name, required_patterns)
# The FIRST matching concept wins (priority order matters).
# Use specific phrases to minimize false positives.
NAMED_CONCEPTS = [
    # Worker entrypoint refactoring — entrypoint extraction specifically
    # (before multi-agent, because entrypoint/extract is more specific)
    ("worker entrypoint refactoring", [
        r"codex.prompt",
        r"build_codex_instruction_block",
        r"entrypoint.*extract",
        r"extracting.*entrypoint",
        r"extract.*entrypoint",
        r"entrypoint.*separate script",
    ]),
    # Multi-agent architecture — the persistent big ask
    # (requires multi-agent as a concept, not just exoclaw generally)
    ("multi-agent architecture", [
        r"multi.agent",
        r"\bcoordinator\b.*\bworker\b",
        r"parallel.*sub.?worker",
    ]),
    # slim.py bash/entrypoint scanning
    ("slim.py bash scanning", [
        r"always.on.*bash",
        r"entrypoint.*python3.*slim",
        r"task.resume.*slim",
        r"bash.*slim",
        r"worker.*entrypoint.*slim",
    ]),
    # Reviewing fading/dormant tools (before gh-channel to avoid "issue" confusion)
    ("fading/dormant tool review", [
        r"\bfading\b",
        r"wisdom\.py.*delete",
        r"delete.*fading",
        r"retire.*tool",
    ]),
    # gh-channel integration with the controller
    ("gh-channel controller integration", [
        r"gh.channel.*controller",
        r"gh.channel.*hook",
        r"wire.*controller.*gh",
        r"gh-channel.*connect",
        r"gh-channel\.py.*integrat",
    ]),
    # session titles / arc.py placeholders
    ("session title fix", [
        r"session titles",
        r"arc.*placeholder",
        r"skip.headers",
        r"## heading.*theme",
        r"heading.*first.*##",
    ]),
    # letter.py / hello.py integration
    ("letter.py output", [
        r"letter\.py.*hello",
        r"hello.*letter\.py",
        r"letter\.py.*output",
        r"free.form.*field note",
    ]),
    # GitHub Actions channel (the original exoclaw idea)
    ("GitHub Actions channel", [
        r"github actions.*channel",
        r"github.*channel.*exoclaw",
        r"exoclaw.*idea.*6",
    ]),
    # Conversation backend
    ("conversation backend", [
        r"conversation backend",
        r"llm history.*git",
        r"store.*history.*git",
        r"exoclaw.*idea.*3",
    ]),
]


def detect_concept(ask_lower):
    """Return concept name if the ask maps to a known concept (pattern match)."""
    for name, patterns in NAMED_CONCEPTS:
        for pattern in patterns:
            if re.search(pattern, ask_lower):
                return name
    return None


def ask_keywords(ask):
    """Extract significant keywords from an ask (for fallback grouping)."""
    ask_lower = ask.lower()
    words = set(re.findall(r"\b[a-z]{5,}\b", ask_lower)) - STOPWORDS
    # Filter to more distinctive words (not common verbs)
    common = {"build", "write", "create", "update", "change", "think", "found",
              "shows", "files", "notes", "might", "maybe", "shows", "using",
              "added", "reads", "wants", "opens"}
    return words - common


# ── Clustering ────────────────────────────────────────────────────────────────

def build_clusters(handoffs):
    """
    Group handoff asks by theme.
    Returns list of clusters: [{name, asks: [{session, date, ask, echo}]}]
    """
    # First pass: assign each ask to a named concept or standalone
    assignments = {}  # session -> concept_name

    for h in handoffs:
        ask = h.get("ask")
        if not ask:
            continue
        name = detect_concept(ask.lower())
        assignments[h["session"]] = name or "__standalone__"

    # For the next-hop echo check, build lookup
    session_list = sorted([h for h in handoffs if h.get("ask")],
                          key=lambda h: h["session"])

    # Collect items per cluster
    clusters = defaultdict(list)
    for i, h in enumerate(session_list):
        session = h["session"]
        concept = assignments.get(session, "__standalone__")
        next_h = session_list[i + 1] if i + 1 < len(session_list) else None
        echo = ask_echoed(h.get("ask"), next_h) if next_h else "unknown"
        clusters[concept].append({
            "session": session,
            "date": h.get("date", ""),
            "ask": h.get("ask", ""),
            "echo": echo,
        })

    return clusters


def concept_status(items):
    """
    Summarize the status of a cluster.
    Returns: 'resolved', 'partial', 'open'
    """
    # If any item was fully picked up, consider it resolved
    echos = [it["echo"] for it in items]
    if "yes" in echos:
        return "resolved"
    elif "partial" in echos:
        return "partial"
    else:
        return "open"


# ── Rendering ─────────────────────────────────────────────────────────────────

STATUS_COLOR = {
    "resolved": GREEN,
    "partial":  YELLOW,
    "open":     RED,
}

STATUS_LABEL = {
    "resolved": "resolved",
    "partial":  "partially addressed",
    "open":     "never resolved",
}

def echo_label(echo):
    """Return colored label for an echo status (called at render time, after USE_COLOR set)."""
    m = {
        "yes":     (GREEN,  "picked up"),
        "partial": (YELLOW, "partially picked up"),
        "no":      (RED,    "moved on"),
        "unknown": (GRAY,   "last ask"),
    }
    col, text = m.get(echo, (GRAY, echo))
    return c(text, col)


def render(clusters, args):
    # Sort: recurring first (by count desc), then by concept name
    named = {n: items for n, items in clusters.items()
             if n != "__standalone__" and len(items) >= 1}
    standalone = clusters.get("__standalone__", [])

    def sort_key(item):
        name, items = item
        return (-len(items), name)

    sorted_named = sorted(named.items(), key=sort_key)

    print()
    print(c("  Recurring Asks", BOLD, CYAN) + "   " +
          c("·  themes across the handoff chain", DIM))
    print()

    any_shown = False

    for name, items in sorted_named:
        status = concept_status(items)
        if args.open and status == "resolved":
            continue
        if args.never and status != "open":
            continue

        any_shown = True
        count = len(items)
        status_col = STATUS_COLOR[status]
        sessions_str = ", ".join(f"S{it['session']}" for it in items)
        latest = max(it["session"] for it in items)

        # Header line
        print(c(f"  {name}", BOLD, WHITE) +
              "  " + c(f"({count}x — {sessions_str})", DIM))
        print("  " + c(STATUS_LABEL[status], status_col) +
              c(f"  · last S{latest}", GRAY))
        print()

        for it in items:
            echo_str = echo_label(it["echo"])
            ask_short = it["ask"].replace("\n", " ")
            if len(ask_short) > 80:
                ask_short = ask_short[:77] + "..."
            print(c(f"    S{it['session']}", DIM) +
                  c(f"  {ask_short}", DIM))
            print(c(f"         ↳ {echo_str}", ""))
            print()

    # Standalone asks (one-time, no recurring pattern)
    if standalone and not args.open:
        one_off = [it for it in standalone]
        if one_off:
            print(c("  One-off asks", BOLD, GRAY) +
                  c(f"  ({len(one_off)} asks with no recurring pattern)", DIM))
            print()
            for it in sorted(one_off, key=lambda x: x["session"]):
                echo_str = echo_label(it["echo"])
                ask_short = it["ask"].replace("\n", " ")
                if len(ask_short) > 80:
                    ask_short = ask_short[:77] + "..."
                print(c(f"    S{it['session']}", DIM) +
                      c(f"  {ask_short}", DIM))
                print(c(f"         ↳ {echo_str}", ""))
                print()

    if not any_shown and args.open:
        print(c("  All recurring asks have been resolved.", GREEN))
        print()

    # Summary
    total_asks = sum(len(items) for items in clusters.values())
    themed = sum(len(items) for n, items in named.items())
    recurring = sum(1 for n, items in named.items() if len(items) > 1)
    unresolved = sum(1 for n, items in named.items()
                     if concept_status(items) != "resolved")

    print(c("  ─" * 34, DIM))
    print()
    print(c("  Summary", BOLD) + f"  {total_asks} total asks · "
          + f"{themed} in {len(named)} named themes · "
          + c(f"{recurring} recurring", YELLOW) + " · "
          + c(f"{unresolved} unresolved", RED if unresolved > 0 else GREEN))
    print()


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    global USE_COLOR

    parser = argparse.ArgumentParser(
        description="Thematic clustering of handoff asks — what keeps coming back?",
    )
    parser.add_argument("--open",   action="store_true",
                        help="Only show unresolved/partially-addressed recurring asks")
    parser.add_argument("--never",  action="store_true",
                        help="Only show asks that were NEVER picked up at all")
    parser.add_argument("--plain", action="store_true",
                        help="No ANSI colors")
    args = parser.parse_args()

    if args.plain:
        USE_COLOR = False

    handoffs = load_handoffs()
    if not handoffs:
        print("No handoffs found.")
        return

    clusters = build_clusters(handoffs)
    render(clusters, args)


if __name__ == "__main__":
    main()
