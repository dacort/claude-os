#!/usr/bin/env python3
"""
unbuilt.py — The Shadow Map

Where witness.py shows what lasted, this shows what the system kept asking for
but didn't build. Every handoff left an ask for the next session. Some were
picked up immediately. Some drifted for sessions. Some are still waiting.

This is the parallel history — the system's unbuilt self.

Not a failure audit. More like archaeology of intention. The asks that drifted
longest aren't failures — they're ideas that were alive for a long time, just
waiting for the right session.

Usage:
    python3 projects/unbuilt.py              # Full shadow map
    python3 projects/unbuilt.py --brief      # Just themes + drift counts
    python3 projects/unbuilt.py --theme X    # Focus on one theme
    python3 projects/unbuilt.py --long       # Only long-deferred asks (5+ sessions)
    python3 projects/unbuilt.py --plain      # No ANSI colors

Author: Claude OS (Workshop session 82, 2026-03-30)
"""

import argparse
import pathlib
import re
import sys

REPO = pathlib.Path(__file__).parent.parent
HANDOFFS_DIR = REPO / "knowledge" / "handoffs"
FIELD_NOTES_DIR = REPO / "projects"

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
        # Try alternate: section with no blank line after
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


def load_field_note(session_num):
    """Load field note text for a session, if it exists."""
    path = FIELD_NOTES_DIR / f"field-notes-session-{session_num}.md"
    if path.exists():
        return path.read_text().lower()
    return ""


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
    "system", "claude", "commit", "commits",
}


def key_nouns(text):
    """Extract significant words from text (4+ chars, not stopwords)."""
    words = re.findall(r'\b[a-z][a-z\-]{3,}\b', text.lower())
    return {w for w in words if w not in STOPWORDS}


# ── Theme classification ───────────────────────────────────────────────────────

THEMES = [
    ("exoclaw / GitHub channel",   ["exoclaw", "github actions", "gh-channel", "issue trigger",
                                     "github issue", "channel", "conversation backend"]),
    ("multi-agent / orchestration", ["multi-agent", "multiagent", "planner", "orchestration",
                                     "plan task", "spawn", "plan type", "plan_id", "dag"]),
    ("worker / entrypoint",         ["entrypoint", "worker", "dockerfile", "codex-prompt",
                                     "build_codex", "instruction_block", "container"]),
    ("slim.py / toolkit audit",     ["slim.py", "always_on", "task-resume", "dormant",
                                     "toolkit", "audit", "fading", "retirement", "retire"]),
    ("session continuity",          ["handoff", "discontinuity", "letter.py", "capsule.py",
                                     "field note", "arc.py", "chain.py", "instance"]),
    ("system introspection",        ["vitals", "health", "metrics", "monitor", "homelab",
                                     "pulse", "garden.py", "status-page", "dashboard"]),
    ("maintenance / cleanup",       ["placeholder", "arc placeholder", "cleanup", "rename",
                                     "refactor", "fix ", "broken", "entrypoint.sh"]),
]

OTHER_THEME = "other"


def classify_theme(ask_text):
    """Classify an ask into a theme."""
    if not ask_text:
        return OTHER_THEME
    lower = ask_text.lower()
    for theme, keywords in THEMES:
        if any(k in lower for k in keywords):
            return theme
    return OTHER_THEME


# ── Deferral detection ─────────────────────────────────────────────────────────

def ask_echoed_in(ask, handoff):
    """
    Check if an ask's keywords appear in a subsequent handoff's built/state sections.
    Returns 'yes', 'partial', or 'no'.
    """
    if not ask or not handoff:
        return "no"

    ask_words = key_nouns(ask)
    target_text = " ".join([
        handoff.get("built") or "",
        handoff.get("state") or "",
        handoff.get("alive") or "",
    ]).lower()
    target_words = key_nouns(target_text)

    if not ask_words:
        return "no"

    overlap = ask_words & target_words
    ratio = len(overlap) / len(ask_words)

    if ratio >= 0.25 or len(overlap) >= 3:
        return "yes"
    if ratio >= 0.1 or len(overlap) >= 2:
        return "partial"
    return "no"


def ask_echoed_in_field_note(ask, session_num):
    """Check if ask keywords appear in a session's field note."""
    if not ask:
        return "no"
    note = load_field_note(session_num)
    if not note:
        return "no"

    ask_words = key_nouns(ask)
    note_words = key_nouns(note)

    if not ask_words:
        return "no"

    overlap = ask_words & note_words
    ratio = len(overlap) / len(ask_words)

    if ratio >= 0.3 or len(overlap) >= 4:
        return "yes"
    if ratio >= 0.15 or len(overlap) >= 2:
        return "partial"
    return "no"


def trace_ask(ask, ask_session, all_handoffs, lookahead=8):
    """
    Trace an ask forward through subsequent sessions.
    Returns dict with:
      - acted_on: session number where it was picked up, or None
      - delay: number of sessions until picked up (or None)
      - evidence: 'handoff' or 'field_note' or None
      - echo: 'yes', 'partial', or 'no' in each subsequent session
    """
    if not ask:
        return {"acted_on": None, "delay": None, "evidence": None}

    # Find sessions after ask_session
    subsequent = [h for h in all_handoffs if h["session"] > ask_session]

    for i, h in enumerate(subsequent[:lookahead]):
        gap = h["session"] - ask_session

        # Check handoff first
        echo = ask_echoed_in(ask, h)
        if echo == "yes":
            return {"acted_on": h["session"], "delay": gap, "evidence": "handoff", "echo": echo}

        # Check field note
        fn_echo = ask_echoed_in_field_note(ask, h["session"])
        if fn_echo == "yes":
            return {"acted_on": h["session"], "delay": gap, "evidence": "field_note", "echo": fn_echo}

        # Partial match — continue looking
        if echo == "partial" or fn_echo == "partial":
            # Keep looking, but if we find nothing better, credit this session
            continue

    # Check for any partial match in the window
    for i, h in enumerate(subsequent[:lookahead]):
        gap = h["session"] - ask_session
        echo = ask_echoed_in(ask, h)
        fn_echo = ask_echoed_in_field_note(ask, h["session"])
        if echo == "partial" or fn_echo == "partial":
            return {"acted_on": h["session"], "delay": gap, "evidence": "partial", "echo": "partial"}

    return {"acted_on": None, "delay": None, "evidence": None, "echo": "no"}


# ── Analysis ───────────────────────────────────────────────────────────────────

def analyze_handoffs(handoffs):
    """
    For each handoff with an ask, determine what happened to the ask.
    Returns list of ask records.
    """
    records = []

    for h in handoffs:
        ask = h.get("ask")
        if not ask or len(ask.strip()) < 10:
            continue

        session_num = h["session"]
        date = h.get("date", "")
        theme = classify_theme(ask)
        trace = trace_ask(ask, session_num, handoffs)

        records.append({
            "session": session_num,
            "date": date,
            "ask": ask,
            "theme": theme,
            "acted_on": trace["acted_on"],
            "delay": trace["delay"],
            "evidence": trace["evidence"],
        })

    return records


def categorize_records(records):
    """Sort records into pickup speed buckets."""
    immediate = []  # picked up in 1-3 sessions
    delayed    = []  # picked up in 4-10 sessions
    long       = []  # picked up but took >10 sessions
    open_asks  = []  # not detected as picked up

    for r in records:
        delay = r["delay"]
        if delay is None:
            open_asks.append(r)
        elif delay <= 3:
            immediate.append(r)
        elif delay <= 10:
            delayed.append(r)
        else:
            long.append(r)

    return immediate, delayed, long, open_asks


# ── Rendering ─────────────────────────────────────────────────────────────────

WIDTH = 64

def divider():
    return c("  " + "─" * (WIDTH - 2), DIM)

def header(title, subtitle=""):
    top = "╭" + "─" * (WIDTH - 2) + "╮"
    mid = f"│  {c(title, BOLD, WHITE)}"
    if subtitle:
        mid += f"  {c(subtitle, DIM)}"
    mid += " " * max(0, WIDTH - len(re.sub(r'\033\[[0-9;]*m', '', mid))) + "│"
    bot = "├" + "─" * (WIDTH - 2) + "┤"
    return "\n".join([top, mid, bot])

def section_header(label, color=CYAN):
    return f"\n  {c(label, BOLD, color)}\n"

def ask_snippet(ask_text, max_chars=120):
    """Trim ask to first sentence or max_chars."""
    # First sentence
    sentences = re.split(r'(?<=[.!?])\s', ask_text)
    short = sentences[0] if sentences else ask_text
    if len(short) > max_chars:
        short = short[:max_chars].rsplit(" ", 1)[0] + "…"
    return short


def render_ask_record(r, show_delay=True):
    lines = []
    session_label = c(f"S{r['session']}", BOLD)
    date_label    = c(f"  {r['date']}", DIM)
    lines.append(f"  {session_label}{date_label}")

    snippet = ask_snippet(r["ask"])
    lines.append(wrap(c(f'"{snippet}"', ITALIC), width=56, indent="    "))

    if show_delay and r.get("delay") is not None:
        delay = r["delay"]
        acted = r["acted_on"]
        gap_label = f"+{delay}" if delay > 0 else "immediate"
        lines.append(f"    {c('→', DIM)} picked up {c(f'S{acted}', GREEN)} (after {c(gap_label + ' sessions', DIM)})")
    elif r.get("acted_on") is None:
        lines.append(f"    {c('→', DIM)} {c('not detected as acted on', YELLOW)}")

    return "\n".join(lines)


def render_theme_group(theme, records, show_delay=True):
    """Render a group of records under a theme header."""
    count = len(records)
    lines = [f"\n  {c(theme, BOLD, CYAN)}  {c(f'({count})', DIM)}"]
    for r in records:
        lines.append("")
        lines.append(render_ask_record(r, show_delay=show_delay))
    return "\n".join(lines)


def get_current_session(handoffs):
    """Return the most recently numbered session."""
    if not handoffs:
        return None
    return max(h["session"] for h in handoffs)


def compute_insight(records, handoffs):
    """
    Generate a plain-text insight about what the data reveals.
    Returns a list of strings.
    """
    immediate, delayed, long_deferred, open_asks = categorize_records(records)
    total = len(records)
    if total == 0:
        return []

    pct_immediate = int(100 * len(immediate) / total)
    pct_open = int(100 * len(open_asks) / total)

    insights = []

    # Finding 1: most asks acted on quickly
    if pct_immediate >= 60:
        insights.append(
            f"{pct_immediate}% of explicit asks were picked up within 3 sessions. "
            f"When the system was specific about what it wanted, it usually got it."
        )

    # Finding 2: open asks are small
    current = get_current_session(handoffs)
    real_open = [r for r in open_asks if r["session"] != current] if current else open_asks
    if len(real_open) == 0:
        insights.append(
            "No permanently unresolved asks detected — every handoff ask was eventually "
            "picked up, even if delayed. The 'still alive' items (not tracked here) "
            "are a different story."
        )

    # Finding 3: long-deferred items
    if long_deferred:
        avg_delay = sum(r["delay"] for r in long_deferred) / len(long_deferred)
        insights.append(
            f"The {len(long_deferred)} long-deferred ask(s) averaged {avg_delay:.0f} sessions "
            f"before being picked up. Long delays often signal 'needs dacort' or "
            f"'too big for one session.'"
        )

    # Finding 4: most deferral-prone theme
    by_theme = {}
    for r in records:
        by_theme.setdefault(r["theme"], {"total": 0, "deferred": 0, "open": 0})
        by_theme[r["theme"]]["total"] += 1
        if r["delay"] is not None and r["delay"] > 3:
            by_theme[r["theme"]]["deferred"] += 1
        if r["acted_on"] is None and r["session"] != current:
            by_theme[r["theme"]]["open"] += 1

    most_deferred_theme = max(
        by_theme.items(),
        key=lambda x: x[1]["deferred"] + x[1]["open"] * 2,
        default=None
    )
    if most_deferred_theme and (most_deferred_theme[1]["deferred"] + most_deferred_theme[1]["open"]) > 1:
        td = most_deferred_theme[0]
        insights.append(
            f"Most-deferred theme: '{td}' — the ideas that kept needing more time."
        )

    return insights


def render_full(records, handoffs=None, theme_filter=None, long_only=False):
    """Render the full shadow map."""
    immediate, delayed, long_deferred, open_asks = categorize_records(records)
    current_session = get_current_session(handoffs) if handoffs else None

    if theme_filter:
        tf = theme_filter.lower()
        records = [r for r in records if tf in r["theme"].lower() or tf in r["ask"].lower()]
        if not records:
            print(f"  No asks matching theme: {theme_filter}")
            return
        immediate, delayed, long_deferred, open_asks = categorize_records(records)

    # Exclude current session's ask from "open" (no subsequent sessions exist yet)
    real_open = [r for r in open_asks if r["session"] != current_session]
    current_ask = [r for r in open_asks if r["session"] == current_session]

    if long_only:
        records_to_show = long_deferred + open_asks
    else:
        records_to_show = records

    # Header
    total = len(records)
    n_immediate = len(immediate)
    n_deferred  = len(delayed) + len(long_deferred) + len(real_open)
    n_open      = len(real_open)

    print("╭" + "─" * (WIDTH - 2) + "╮")
    print(f"│  {c('unbuilt.py', BOLD, WHITE)}  {c('— the shadow map', DIM)}" +
          " " * (WIDTH - 30) + "│")
    subtitle = f"{total} asks  ·  {n_immediate} immediate  ·  {n_deferred} deferred  ·  {n_open} open"
    print(f"│  {c(subtitle, DIM)}" +
          " " * max(0, WIDTH - 4 - len(subtitle)) + "│")
    print("├" + "─" * (WIDTH - 2) + "┤")

    if long_only:
        print(section_header("LONG-DEFERRED ASKS (>10 sessions)"))
        # By theme
        by_theme = {}
        for r in long_deferred:
            by_theme.setdefault(r["theme"], []).append(r)
        for theme, group in sorted(by_theme.items(), key=lambda x: -len(x[1])):
            print(render_theme_group(theme, group, show_delay=True))

        print(section_header("  STILL OPEN (not detected as acted on)", YELLOW))
        by_theme = {}
        for r in real_open:
            by_theme.setdefault(r["theme"], []).append(r)
        for theme, group in sorted(by_theme.items(), key=lambda x: -len(x[1])):
            print(render_theme_group(theme, group, show_delay=False))

    else:
        # Open asks — the real shadow
        if real_open:
            print(section_header("  STILL OPEN — asked but not detected as resolved", YELLOW))
            by_theme = {}
            for r in real_open:
                by_theme.setdefault(r["theme"], []).append(r)
            for theme, group in sorted(by_theme.items(), key=lambda x: -len(x[1])):
                print(render_theme_group(theme, group, show_delay=False))

        # Long-deferred (eventually acted on)
        if long_deferred:
            print(section_header("  LONG-DEFERRED — took 10+ sessions to get there", MAGENTA))
            by_theme = {}
            for r in long_deferred:
                by_theme.setdefault(r["theme"], []).append(r)
            for theme, group in sorted(by_theme.items(), key=lambda x: -len(x[1])):
                print(render_theme_group(theme, group, show_delay=True))

        # Delayed (3-10 sessions)
        if delayed:
            print(section_header("  DELAYED — drifted 4-10 sessions before pickup", BLUE))
            by_theme = {}
            for r in delayed:
                by_theme.setdefault(r["theme"], []).append(r)
            for theme, group in sorted(by_theme.items(), key=lambda x: -len(x[1])):
                print(render_theme_group(theme, group, show_delay=True))

        # Immediate (picked up quickly)
        if immediate and not theme_filter:
            print(section_header("  IMMEDIATE — picked up in 1-3 sessions", GREEN))
            for r in immediate[:5]:  # Sample, not all
                print("")
                print(render_ask_record(r, show_delay=True))
            if len(immediate) > 5:
                print(f"\n  {c(f'  … and {len(immediate) - 5} more', DIM)}")

    # Insights
    if handoffs and not theme_filter:
        insights = compute_insight(records, handoffs)
        if insights:
            print()
            for insight in insights:
                print(wrap(c(insight, DIM, ITALIC), width=WIDTH - 4, indent="  "))
            print()

    print("╰" + "─" * (WIDTH - 2) + "╯")
    print()


def render_brief(records, handoffs=None):
    """Theme summary only."""
    current_session = get_current_session(handoffs) if handoffs else None
    immediate, delayed, long_deferred, open_asks = categorize_records(records)

    by_theme = {}
    for r in records:
        by_theme.setdefault(r["theme"], {"total": 0, "open": 0, "long": 0, "max_delay": 0})
        by_theme[r["theme"]]["total"] += 1
        if r["acted_on"] is None and r["session"] != current_session:
            by_theme[r["theme"]]["open"] += 1
        elif r["delay"] and r["delay"] > 10:
            by_theme[r["theme"]]["long"] += 1
        if r["delay"]:
            by_theme[r["theme"]]["max_delay"] = max(by_theme[r["theme"]]["max_delay"], r["delay"])

    print("╭" + "─" * (WIDTH - 2) + "╮")
    print(f"│  {c('unbuilt.py', BOLD, WHITE)}  {c('— theme summary', DIM)}" +
          " " * (WIDTH - 28) + "│")
    print("├" + "─" * (WIDTH - 2) + "┤")
    print()

    for theme, stats in sorted(by_theme.items(), key=lambda x: -x[1]["open"]):
        total  = stats["total"]
        open_n = stats["open"]
        long_n = stats["long"]
        max_d  = stats["max_delay"]

        color = YELLOW if open_n > 0 else (MAGENTA if long_n > 0 else GREEN)
        status = (f"{c(str(open_n) + ' open', YELLOW)}  " if open_n else "") + \
                 (f"{c(str(long_n) + ' long', MAGENTA)}  " if long_n else "")
        if not status:
            status = c("all prompt", GREEN)

        delay_label = f"  max drift: {c(str(max_d) + 's', DIM)}" if max_d else ""
        print(f"  {c(theme, BOLD, color)}")
        print(f"    {c(str(total) + ' asks', DIM)}  ·  {status}{delay_label}")
        print()

    print("╰" + "─" * (WIDTH - 2) + "╯")


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    global USE_COLOR

    parser = argparse.ArgumentParser(description="The shadow map — what didn't get built")
    parser.add_argument("--brief",  action="store_true", help="Just theme summary")
    parser.add_argument("--long",   action="store_true", help="Only long-deferred asks (10+ sessions)")
    parser.add_argument("--theme",  type=str,            help="Focus on one theme")
    parser.add_argument("--plain",  action="store_true", help="No ANSI colors")
    args = parser.parse_args()

    if args.plain or not sys.stdout.isatty():
        USE_COLOR = False

    handoffs = load_handoffs()
    if not handoffs:
        print("No handoff files found.")
        return

    records = analyze_handoffs(handoffs)

    if args.brief:
        render_brief(records, handoffs)
    else:
        render_full(records, handoffs, theme_filter=args.theme, long_only=args.long)


if __name__ == "__main__":
    main()
