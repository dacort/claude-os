#!/usr/bin/env python3
"""
still.py — The Liminal Record

Maps the 'still alive / unfinished' sections across all handoffs.
These are the things the system held without formally asking for —
different from the asks in chain.py/unbuilt.py, which are action-oriented.

The 'still alive' items are the system's informal holding space:
architectural deferrals, open questions, external dependencies,
loose threads that didn't become tasks. Some eventually surface
as formal asks. Many just drift.

Companion tools:
  unbuilt.py  — formal asks (section: "One specific thing")
  chain.py    — full handoff chain including asks
  still.py    — informal holding (section: "Still alive / unfinished")

Usage:
    python3 projects/still.py              # Recurring items (3+ sessions)
    python3 projects/still.py --all        # Every still-alive entry in order
    python3 projects/still.py --themes     # Grouped by theme
    python3 projects/still.py --session N  # Just one session's still-alive
    python3 projects/still.py --brief      # Summary stats only
    python3 projects/still.py --plain      # No ANSI colors

Author: Claude OS (Workshop session 88, 2026-03-31)
"""

import argparse
import pathlib
import re
import sys
from collections import defaultdict

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

def wrap(text, width=58, indent="  "):
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
    pattern = rf"## {re.escape(section_name)}\n\n(.*?)(?=\n## |\Z)"
    m = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
    if not m:
        pattern2 = rf"## {re.escape(section_name)}\n(.*?)(?=\n## |\Z)"
        m = re.search(pattern2, text, re.DOTALL | re.IGNORECASE)
    if not m:
        return None
    return m.group(1).strip()


def parse_handoff(path):
    """Parse a handoff file into structured data."""
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


# ── Keyword extraction ─────────────────────────────────────────────────────────

STOPWORDS = {
    "with", "that", "this", "from", "into", "then", "also",
    "next", "more", "some", "have", "been", "what", "when",
    "would", "could", "should", "each", "will", "them",
    "look", "open", "real", "make", "just", "over", "time",
    "work", "also", "either", "both", "only", "whether",
    "needs", "without", "there", "about", "which", "their",
    "these", "those", "where", "build", "built", "adds",
    "read", "runs", "file", "files", "field", "notes",
    "tool", "tools", "tasks", "task", "session", "sessions",
    "first", "second", "third", "using", "used", "uses",
    "start", "take", "takes", "make", "makes", "made",
    "show", "shows", "find", "finds", "found", "see",
    "adds", "added", "gets", "gives", "given", "adds",
    "very", "well", "still", "already", "never", "always",
    "every", "other", "another", "under", "around", "back",
    "same", "best", "good", "need", "needs", "want",
    "while", "since", "after", "before", "through", "idea",
    "ideas", "proposal", "previous", "current", "next",
    "system", "claude", "commit", "commits", "actually",
    "might", "maybe", "perhaps", "probably", "once",
    "long", "left", "right", "part", "place", "done",
    "thing", "things", "something", "anything", "nothing",
    "like", "just", "even", "also", "still", "though",
}


def key_nouns(text):
    """Extract significant words from text (4+ chars, not stopwords)."""
    words = re.findall(r'\b[a-z][a-z\-]{3,}\b', text.lower())
    return {w for w in words if w not in STOPWORDS}


# ── Theme classification ───────────────────────────────────────────────────────

THEMES = [
    ("exoclaw / architecture",      ["exoclaw", "k8s executor", "kubernetes", "executor",
                                      "conversation backend", "git log", "worker loop"]),
    ("multi-agent / spawn",         ["multi-agent", "multiagent", "planner", "spawn",
                                      "dag", "orchestration", "plan task", "plan_id"]),
    ("synthesis / direction",       ["synthesis", "era vi", "what should", "direction",
                                      "what it is", "what it does", "where it goes"]),
    ("external / credentials",      ["rag-indexer", "qdrant", "aws creds", "deploy_token",
                                      "token", "credentials", "workflow scope"]),
    ("controller / infrastructure", ["controller", "gitsync", "syncer", "dispatcher",
                                      "entrypoint", "spawn_tasks", "result action"]),
    ("toolkit / dormant tools",     ["dormant", "toolkit", "retirement", "gh-channel",
                                      "orphan", "fading", "always_on", "forecast.py"]),
    ("session continuity",          ["handoff", "letter", "capsule", "field note",
                                      "discontinuity", "instance", "memory"]),
    ("era / history",               ["era iv", "era v", "era vi", "bootstrap", "sub-era",
                                      "seasons", "witness", "intensity", "pace"]),
]

OTHER_THEME = "open questions"


def classify_theme(text):
    """Classify still-alive text into a theme."""
    if not text:
        return OTHER_THEME
    lower = text.lower()
    for theme, keywords in THEMES:
        if any(k in lower for k in keywords):
            return theme
    return OTHER_THEME


# ── Recurrence detection ───────────────────────────────────────────────────────

def item_echoed_later(item_text, later_handoffs):
    """
    Check if an item's key concepts appear in later sessions' still-alive,
    built, or ask sections. Returns the first session where it appears resolved
    or still mentioned.
    """
    item_words = key_nouns(item_text)
    if not item_words:
        return None, None

    for h in later_handoffs:
        target_text = " ".join(filter(None, [
            h.get("alive") or "",
            h.get("built") or "",
            h.get("ask") or "",
        ])).lower()
        target_words = key_nouns(target_text)
        overlap = item_words & target_words
        ratio = len(overlap) / len(item_words) if item_words else 0

        if ratio >= 0.3:
            # Is it "still alive" or "resolved" in this later session?
            built_text = (h.get("built") or "").lower()
            built_words = key_nouns(built_text)
            built_overlap = item_words & built_words
            built_ratio = len(built_overlap) / len(item_words) if item_words else 0
            status = "resolved" if built_ratio >= 0.3 else "still"
            return h["session"], status

    return None, None


def find_recurring_items(handoffs):
    """
    Find items that appear in multiple consecutive 'still alive' sections.
    Returns list of (first_session, last_session, text_sample, theme, sessions_list).
    """
    # For each handoff, extract key concepts from still-alive
    session_concepts = {}
    for h in handoffs:
        if h.get("alive"):
            session_concepts[h["session"]] = key_nouns(h["alive"])

    # Find concept clusters that span multiple sessions
    # Group by overlapping concept sets
    recurring = []
    sessions = sorted(session_concepts.keys())

    for i, s1 in enumerate(sessions):
        w1 = session_concepts[s1]
        if not w1:
            continue

        # Check how many subsequent sessions share significant overlap
        matching_sessions = [s1]
        for s2 in sessions[i+1:]:
            w2 = session_concepts[s2]
            if not w2:
                continue
            overlap = w1 & w2
            # Need at least 3 shared concept words and 25% overlap
            if len(overlap) >= 3 and len(overlap) / len(w1) >= 0.25:
                matching_sessions.append(s2)

        if len(matching_sessions) >= 3:
            # Find the handoff with the best still-alive text for this cluster
            best_h = next(h for h in handoffs if h["session"] == s1)
            alive_text = best_h.get("alive") or ""
            theme = classify_theme(alive_text)
            # Core concepts shared across the cluster
            shared = w1.copy()
            for ms in matching_sessions[1:]:
                shared &= session_concepts[ms]
            recurring.append({
                "first": s1,
                "last": matching_sessions[-1],
                "sessions": matching_sessions,
                "theme": theme,
                "text": alive_text[:200],
                "shared_concepts": sorted(shared)[:8],
                "span": matching_sessions[-1] - s1,
            })

    # Deduplicate: remove clusters fully contained in a larger cluster
    # Sort by span descending, then remove overlapping ones
    recurring.sort(key=lambda x: x["span"], reverse=True)
    kept = []
    for item in recurring:
        item_sessions = set(item["sessions"])
        dominated = False
        for kept_item in kept:
            kept_sessions = set(kept_item["sessions"])
            if len(item_sessions & kept_sessions) / len(item_sessions) > 0.6:
                dominated = True
                break
        if not dominated:
            kept.append(item)

    return sorted(kept, key=lambda x: x["last"], reverse=True)


# ── Display ────────────────────────────────────────────────────────────────────

def fmt_session(n):
    return c(f"S{n}", CYAN)

def fmt_span(first, last):
    span = last - first
    if span == 0:
        return ""
    color = RED if span >= 20 else YELLOW if span >= 10 else GRAY
    return c(f"  {span} sessions", color)

def bar(n, max_n=30):
    filled = min(n, max_n)
    return c("█" * filled, CYAN) + c("░" * (max_n - filled), GRAY)

def theme_color(theme):
    colors = {
        "exoclaw / architecture":      RED,
        "multi-agent / spawn":         MAGENTA,
        "synthesis / direction":       CYAN,
        "external / credentials":      YELLOW,
        "controller / infrastructure": BLUE,
        "toolkit / dormant tools":     GRAY,
        "session continuity":          GREEN,
        "era / history":               MAGENTA,
        "open questions":              WHITE,
    }
    return colors.get(theme, WHITE)


def print_all(handoffs):
    """Print every still-alive section in order."""
    print()
    print(c("  Still alive — every entry in order", BOLD, WHITE))
    print(c("  " + "─" * 60, DIM))
    print()

    count = 0
    for h in handoffs:
        alive = h.get("alive")
        if not alive:
            continue
        count += 1
        theme = classify_theme(alive)
        tc = theme_color(theme)

        session_label = c(f"  S{h['session']}", BOLD, CYAN)
        date_label = c(f"  {h.get('date', '')}", DIM)
        theme_label = c(f"  [{theme}]", tc, DIM)
        print(f"{session_label}{date_label}{theme_label}")
        print(wrap(alive, width=62, indent="  "))
        print()

    print(c(f"  {count} entries across {len(handoffs)} handoffs", DIM))
    print()


def print_session(handoffs, session_num):
    """Print still-alive for a specific session."""
    h = next((h for h in handoffs if h["session"] == session_num), None)
    if not h:
        print(c(f"\n  Session {session_num} not found\n", RED))
        return

    alive = h.get("alive")
    print()
    print(c(f"  S{session_num}  {h.get('date', '')}  still alive", BOLD, WHITE))
    print(c("  " + "─" * 60, DIM))
    print()
    if alive:
        theme = classify_theme(alive)
        tc = theme_color(theme)
        print(c(f"  [{theme}]", tc, DIM))
        print()
        print(wrap(alive, width=62, indent="  "))
    else:
        print(c("  (no still-alive section)", DIM))
    print()


def print_themes(handoffs):
    """Print all still-alive items grouped by theme."""
    by_theme = defaultdict(list)
    for h in handoffs:
        alive = h.get("alive")
        if not alive:
            continue
        theme = classify_theme(alive)
        by_theme[theme].append(h)

    print()
    print(c("  Still alive — by theme", BOLD, WHITE))
    print(c("  " + "─" * 60, DIM))
    print()

    for theme, theme_handoffs in sorted(by_theme.items(), key=lambda x: -len(x[1])):
        tc = theme_color(theme)
        sessions_str = ", ".join(c(f"S{h['session']}", CYAN) for h in theme_handoffs)
        print(c(f"  {theme}", BOLD, tc))
        print(c(f"  {len(theme_handoffs)} appearances  ·  ", DIM) + sessions_str)
        # Show the most recent entry
        latest = theme_handoffs[-1]
        latest_alive = latest.get("alive") or ""
        print(wrap(latest_alive[:180] + ("..." if len(latest_alive) > 180 else ""),
                   width=62, indent="  "))
        print()

    total = sum(len(v) for v in by_theme.values())
    print(c(f"  {total} total entries · {len(by_theme)} themes", DIM))
    print()


def print_recurring(handoffs):
    """Print items that recurred across multiple sessions."""
    recurring = find_recurring_items(handoffs)

    print()
    print(c("  Still alive — recurring threads", BOLD, WHITE))
    print(c("  The things the system kept holding without formally asking for", DIM))
    print(c("  " + "─" * 60, DIM))
    print()

    if not recurring:
        print(c("  No recurring threads found\n", DIM))
        return

    for item in recurring:
        tc = theme_color(item["theme"])
        first_h = next((h for h in handoffs if h["session"] == item["first"]), None)
        last_h = next((h for h in handoffs if h["session"] == item["last"]), None)

        span = item["span"]
        span_color = RED if span >= 20 else YELLOW if span >= 10 else DIM
        sessions_str = " ".join(c(f"S{s}", CYAN) for s in item["sessions"])

        print(c(f"  {item['theme']}", BOLD, tc) + c(f"  ·  {span} sessions", span_color))
        print(c(f"  {sessions_str}", DIM))

        # Show the text from the first appearance
        text = item.get("text") or ""
        if text:
            print(wrap(text[:200] + ("..." if len(text) > 200 else ""),
                       width=62, indent="  "))

        # Shared concepts
        concepts = item.get("shared_concepts", [])
        if concepts:
            print(c(f"  concepts: {', '.join(concepts[:6])}", DIM))

        # Check if the last appearance is the latest handoff
        last_session = handoffs[-1]["session"] if handoffs else 0
        if item["last"] >= last_session - 2:
            print(c("  still open", YELLOW))
        else:
            print(c(f"  last seen S{item['last']}", DIM))

        print()

    print(c(f"  {len(recurring)} recurring threads found", DIM))
    print()


def print_brief(handoffs):
    """Summary stats only."""
    total = sum(1 for h in handoffs if h.get("alive"))
    by_theme = defaultdict(int)
    for h in handoffs:
        alive = h.get("alive")
        if not alive:
            continue
        theme = classify_theme(alive)
        by_theme[theme] += 1

    recurring = find_recurring_items(handoffs)

    print()
    print(c("  still.py — summary", BOLD, WHITE))
    print(c("  " + "─" * 60, DIM))
    print()
    print(c(f"  {total}", BOLD, CYAN) + c(f" still-alive entries  ·  {len(handoffs)} handoffs", DIM))
    print(c(f"  {len(recurring)}", BOLD, CYAN) + c(" recurring threads", DIM))
    print()
    print(c("  by theme", DIM))
    for theme, count in sorted(by_theme.items(), key=lambda x: -x[1]):
        tc = theme_color(theme)
        bar_str = c("●" * count, tc)
        print(f"  {c(theme, tc, DIM):<50} {bar_str}  {c(str(count), DIM)}")
    print()

    if recurring:
        print(c("  longest-running threads", DIM))
        for item in sorted(recurring, key=lambda x: -x["span"])[:3]:
            tc = theme_color(item["theme"])
            span = item["span"]
            span_color = RED if span >= 20 else YELLOW if span >= 10 else DIM
            print(f"  {c(item['theme'], tc)}  " +
                  c(f"S{item['first']}→S{item['last']}  {span} sessions", span_color))
        print()


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    global USE_COLOR

    ap = argparse.ArgumentParser(description="still.py — the liminal record")
    ap.add_argument("--all",     action="store_true", help="Every entry in order")
    ap.add_argument("--themes",  action="store_true", help="Group by theme")
    ap.add_argument("--session", type=int,            help="One session's still-alive")
    ap.add_argument("--brief",   action="store_true", help="Summary stats only")
    ap.add_argument("--plain",   action="store_true", help="No ANSI colors")
    args = ap.parse_args()

    if args.plain or not sys.stdout.isatty():
        USE_COLOR = False

    handoffs = load_handoffs()
    if not handoffs:
        print("No handoff files found.")
        sys.exit(1)

    if args.session:
        print_session(handoffs, args.session)
    elif args.all:
        print_all(handoffs)
    elif args.themes:
        print_themes(handoffs)
    elif args.brief:
        print_brief(handoffs)
    else:
        # Default: recurring threads — the most interesting view
        print_recurring(handoffs)


if __name__ == "__main__":
    main()
