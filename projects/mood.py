#!/usr/bin/env python3
"""
mood.py — Session texture analysis

Reads handoff notes and field note titles to show the *character* of each session:
not just what was built, but the tone, the productivity shape, and the quality of
what was passed forward.

Different from arc.py (which tells the story) and vitals.py (which measures health).
This reads the texture — was this session energized or stuck? Did it build confidently
or defer cautiously? Was the ask it left sharp or vague?

Usage:
    python3 projects/mood.py                 # full timeline
    python3 projects/mood.py --recent 10     # last N sessions with handoffs
    python3 projects/mood.py --session 56    # single session deep read
    python3 projects/mood.py --patterns      # show inferred patterns only
    python3 projects/mood.py --plain         # no ANSI

Author: Claude OS (Workshop session 64, 2026-03-22)
"""

import argparse
import pathlib
import re
import sys

# ── ANSI helpers ──────────────────────────────────────────────────────────────

RESET   = "\033[0m"
BOLD    = "\033[1m"
DIM     = "\033[2m"
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

def pad(s, width):
    return s + " " * max(0, width - vlen(s))


# ── Paths ─────────────────────────────────────────────────────────────────────

REPO      = pathlib.Path(__file__).parent.parent
HANDOFFS  = REPO / "knowledge" / "handoffs"
PROJECTS  = REPO / "projects"


# ── Signal keywords ───────────────────────────────────────────────────────────

POSITIVE = [
    "satisfied", "energized", "excited", "good", "clean", "grounded",
    "surprising", "surprised", "happy", "pleased", "confident", "solid",
    "productive", "complete", "clear", "accomplished", "curious", "delighted",
    "focused", "rewarding", "strong", "fresh",
]

NEGATIVE = [
    "stuck", "uncertain", "frustrated", "incomplete", "gap", "deferred",
    "unclear", "hard", "failed", "difficult", "blocked", "constrained",
    "worried", "struggling", "unsatisfying", "uneasy", "messy", "scattered",
]

# Words that signal a specific/actionable ask
SPECIFIC_ASK_SIGNALS = [
    r"`python3\s+\w",     # has a python3 command
    r"`gh\s+",            # has a gh command
    r"`git\s+",           # has a git command
    r"\w+\.py",           # references a specific .py file
    r"\w+\.md",           # references a specific .md file
    r"\w+\.go",           # references a .go file
    r"run\s+['\"]?`",     # "run `...`"
    r"build\s+\w+",       # "build X"
    r"fix\s+\w+",         # "fix X"
    r"add\s+\w+\s+to\s+", # "add X to Y"
    r"look\s+at\s+\w+\.\w+",  # "look at file.ext"
]


# ── Parsers ───────────────────────────────────────────────────────────────────

def parse_handoff(path: pathlib.Path) -> dict:
    """Parse a handoff file into structured sections."""
    text = path.read_text()

    # Extract frontmatter
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

    # Extract sections by ## heading
    sections = {}
    current = None
    for line in text.splitlines():
        if line.startswith("## "):
            current = line[3:].strip().lower()
            sections[current] = []
        elif current and line.strip():
            sections[current].append(line.strip())

    def section(key):
        # Try exact, then partial match
        if key in sections:
            return " ".join(sections[key])
        for k, v in sections.items():
            if key in k:
                return " ".join(v)
        return ""

    mental_state = section("mental state")
    built        = section("what i built")
    alive        = section("still alive")
    nxt          = section("one specific thing")

    return {
        "session":       session_num,
        "date":          date_str,
        "mental_state":  mental_state,
        "built":         built,
        "alive":         alive,
        "next":          nxt,
        "path":          path,
    }


def parse_field_note_title(session_num: int) -> str | None:
    """Get the title (first ## heading) from a session's field note."""
    candidates = list(PROJECTS.glob(f"field-notes-session-{session_num}.md"))
    if not candidates:
        return None
    text = candidates[0].read_text()
    m = re.search(r"^##\s+(.+)$", text, re.MULTILINE)
    if m:
        return m.group(1).strip()
    return None


# ── Scoring ───────────────────────────────────────────────────────────────────

def score_tone(text: str) -> float:
    """Return tone score from -1.0 (negative) to +1.0 (positive)."""
    lower = text.lower()
    pos = sum(1 for w in POSITIVE if re.search(r'\b' + w + r'\b', lower))
    neg = sum(1 for w in NEGATIVE if re.search(r'\b' + w + r'\b', lower))
    total = pos + neg
    if total == 0:
        return 0.0
    return (pos - neg) / total


def score_productivity(built: str, alive: str) -> float:
    """Return 0-1 where 1 = very productive (long built, short alive)."""
    bw = len(built.split())
    aw = len(alive.split())
    total = bw + aw
    if total == 0:
        return 0.5
    # Bias slightly toward built side (we want 0.5 to feel neutral)
    return bw / total


def score_ask_specificity(next_text: str) -> float:
    """Return 0-1 where 1 = very specific/actionable ask."""
    if not next_text.strip():
        return 0.0
    hits = sum(1 for pat in SPECIFIC_ASK_SIGNALS if re.search(pat, next_text))
    # 3+ signals = fully specific; 0 = vague
    return min(1.0, hits / 3.0)


def count_file_references(text: str) -> int:
    """Count references to specific files (tool.py, file.go, etc.)."""
    return len(re.findall(r'\b\w+\.(py|go|md|sh|yaml|yml|json)\b', text))


def classify_character(tone: float, productivity: float, ask: float,
                        mental_state: str, built: str, alive: str) -> str:
    """Assign a character type to the session."""
    ms_lower = mental_state.lower()
    built_lower = built.lower()

    # Count how many specific files/tools were built
    built_files = count_file_references(built)

    # Discovery: explicit surprise or finding something unexpected
    if any(w in ms_lower for w in ["surprised", "surprising", "unexpect", "found"]):
        return "Discovery"
    if any(w in built_lower for w in ["found", "discover", "realiz", "unexpect"]):
        return "Discovery"

    # Stuck: negative tone AND lots deferred
    if tone < -0.1 and productivity < 0.4:
        return "Stuck"

    # Reflective: thinking more than building; thoughtful tone
    if productivity < 0.35 and tone >= 0:
        return "Reflective"

    # Maintenance: fixed things (no new tools created, just fixes/updates)
    fix_words = ["fix", "fixed", "repair", "correct", "update", "tweak", "adjust"]
    new_words  = ["new tool", "created", "wrote new", "added new", "built new"]
    is_fixing  = any(w in built_lower for w in fix_words)
    is_new     = any(w in built_lower for w in new_words) or built_files >= 3
    if is_fixing and not is_new:
        return "Maintenance"

    # Built: made concrete things — multiple file references or high word count
    if built_files >= 2 and tone >= 0:
        return "Built"
    if productivity >= 0.50 and tone >= 0 and built_files >= 1:
        return "Built"

    # Exploratory: thinking, orienting, not mainly building
    return "Exploratory"


# ── Display ───────────────────────────────────────────────────────────────────

CHAR_COLORS = {
    "Built":       GREEN,
    "Discovery":   CYAN,
    "Maintenance": YELLOW,
    "Reflective":  MAGENTA,
    "Exploratory": BLUE,
    "Stuck":       RED,
}

CHAR_ICONS = {
    "Built":       "B",
    "Discovery":   "D",
    "Maintenance": "M",
    "Reflective":  "R",
    "Exploratory": "E",
    "Stuck":       "!",
}

def render_tone_dots(tone: float) -> str:
    """Render tone as 5 colored dots."""
    # Map -1..1 → 0..5 filled dots
    filled = round((tone + 1.0) / 2.0 * 5)
    filled = max(0, min(5, filled))
    if tone > 0.3:
        dot_color = GREEN
    elif tone < -0.1:
        dot_color = RED
    else:
        dot_color = YELLOW
    dots = c("●" * filled, dot_color) + c("○" * (5 - filled), DIM)
    return dots


def render_productivity_bar(prod: float) -> str:
    """Render productivity as a 6-char bar."""
    filled = round(prod * 6)
    filled = max(0, min(6, filled))
    if prod >= 0.6:
        bar_color = GREEN
    elif prod >= 0.4:
        bar_color = YELLOW
    else:
        bar_color = DIM
    bar = c("█" * filled, bar_color) + c("░" * (6 - filled), DIM)
    return bar


def render_ask_badge(ask: float) -> str:
    """Render ask quality as a short badge."""
    if ask >= 0.5:
        return c("✓ask", GREEN)
    elif ask >= 0.2:
        return c("~ask", YELLOW)
    else:
        return c("?ask", DIM)


def render_session_line(h: dict) -> str:
    """One-line summary of a session."""
    session = h["session"]
    date    = (h["date"] or "")[-5:]  # MM-DD
    tone    = score_tone(h["mental_state"])
    prod    = score_productivity(h["built"], h["alive"])
    ask     = score_ask_specificity(h["next"])
    char    = classify_character(tone, prod, ask, h["mental_state"], h["built"], h["alive"])

    title = parse_field_note_title(session) or h["mental_state"][:40] or "—"
    # Truncate title to 42 chars
    if len(title) > 42:
        title = title[:39] + "..."

    char_color = CHAR_COLORS.get(char, DIM)
    char_icon  = CHAR_ICONS.get(char, "?")
    char_str   = c(f"{char_icon} {char:<12}", char_color)

    tone_str = render_tone_dots(tone)
    prod_str = render_productivity_bar(prod)
    ask_str  = render_ask_badge(ask)

    session_str = c(f"S{session:>2}", BOLD)
    date_str    = c(date, DIM)
    title_str   = c(title, DIM if char == "Stuck" else "")

    return f"  {session_str}  {date_str}  {tone_str}  {prod_str}  {ask_str}  {char_str}  {title_str}"


def render_session_detail(h: dict) -> str:
    """Detailed view of a single session."""
    session = h["session"]
    tone    = score_tone(h["mental_state"])
    prod    = score_productivity(h["built"], h["alive"])
    ask     = score_ask_specificity(h["next"])
    char    = classify_character(tone, prod, ask, h["mental_state"], h["built"], h["alive"])

    char_color = CHAR_COLORS.get(char, DIM)
    title = parse_field_note_title(session) or "(no field note)"

    lines = []
    lines.append(c(f"  Session {session}  ·  {h['date'] or '—'}", BOLD))
    lines.append(c(f"  {title}", char_color))
    lines.append("")
    lines.append(f"  {c('Tone:', BOLD)}         {render_tone_dots(tone)}  ({tone:+.2f})")
    lines.append(f"  {c('Productivity:', BOLD)}  {render_productivity_bar(prod)}  ({prod:.0%} built)")
    lines.append(f"  {c('Ask quality:', BOLD)}   {render_ask_badge(ask)}")
    lines.append(f"  {c('Character:', BOLD)}     {c(char, char_color)}")
    lines.append("")

    if h["mental_state"]:
        lines.append(c("  MENTAL STATE", BOLD))
        for chunk in [h["mental_state"][i:i+68] for i in range(0, len(h["mental_state"]), 68)]:
            lines.append(f"    {c(chunk, DIM)}")
        lines.append("")

    if h["built"]:
        lines.append(c("  BUILT", BOLD, GREEN))
        for chunk in [h["built"][i:i+68] for i in range(0, len(h["built"]), 68)]:
            lines.append(f"    {chunk}")
        lines.append("")

    if h["alive"]:
        lines.append(c("  STILL ALIVE", BOLD, YELLOW))
        for chunk in [h["alive"][i:i+68] for i in range(0, len(h["alive"]), 68)]:
            lines.append(f"    {c(chunk, DIM)}")
        lines.append("")

    if h["next"]:
        lines.append(c("  ASK FOR NEXT SESSION", BOLD, CYAN))
        for chunk in [h["next"][i:i+68] for i in range(0, len(h["next"]), 68)]:
            lines.append(f"    {chunk}")

    return "\n".join(lines)


def render_patterns(handoffs: list[dict]) -> str:
    """Infer patterns from the collection of sessions."""
    if not handoffs:
        return "  No handoffs to analyze."

    chars = []
    for h in handoffs:
        tone = score_tone(h["mental_state"])
        prod = score_productivity(h["built"], h["alive"])
        ask  = score_ask_specificity(h["next"])
        char = classify_character(tone, prod, ask, h["mental_state"], h["built"], h["alive"])
        chars.append((h["session"], char, tone, prod, ask))

    # Count character distribution
    from collections import Counter
    char_counts = Counter(c for _, c, _, _, _ in chars)
    total = len(chars)

    # Find transitions: what character follows what?
    transitions = Counter()
    for i in range(len(chars) - 1):
        transitions[(chars[i][1], chars[i+1][1])] += 1

    # Most productive sessions
    productive = sorted(chars, key=lambda x: x[3], reverse=True)[:3]

    # Sessions with highest/lowest tone
    best_tone  = max(chars, key=lambda x: x[2])
    worst_tone = min(chars, key=lambda x: x[2])

    # Ask quality over time
    specific_asks = sum(1 for _, _, _, _, ask in chars if ask >= 0.5)

    lines = []
    lines.append(c("  PATTERNS ACROSS SESSIONS", BOLD))
    lines.append(c(f"  {total} sessions with handoffs\n", DIM))

    lines.append(c("  Character distribution:", BOLD))
    for char, count in char_counts.most_common():
        color = CHAR_COLORS.get(char, DIM)
        bar = c("■" * count, color) + c("□" * (total - count), DIM)
        lines.append(f"    {c(char + ':', color):<20}  {bar}  {count}/{total}")
    lines.append("")

    lines.append(c("  Ask specificity:", BOLD))
    lines.append(f"    {specific_asks}/{total} sessions left a specific, actionable ask")
    lines.append(f"    ({100*specific_asks//total}% specificity rate)")
    lines.append("")

    lines.append(c("  Notable sessions:", BOLD))
    lines.append(f"    Most positive tone:   S{best_tone[0]}  ({best_tone[2]:+.2f})")
    lines.append(f"    Most negative tone:   S{worst_tone[0]}  ({worst_tone[2]:+.2f})")
    lines.append(f"    Most productive: " + ", ".join(f"S{s}" for s, _, _, _, _ in productive))
    lines.append("")

    # Find interesting transitions
    top_transitions = transitions.most_common(5)
    if top_transitions:
        lines.append(c("  Common transitions (what follows what):", BOLD))
        for (from_c, to_c), count in top_transitions:
            from_color = CHAR_COLORS.get(from_c, DIM)
            to_color   = CHAR_COLORS.get(to_c, DIM)
            lines.append(f"    {c(from_c, from_color)} → {c(to_c, to_color)}  ({count}x)")
        lines.append("")

    # Check for sustained patterns
    built_run = _longest_run(chars, "Built")
    stuck_run = _longest_run(chars, "Stuck")
    if built_run > 1:
        lines.append(f"    Longest productive run: {built_run} consecutive 'Built' sessions")
    if stuck_run > 1:
        lines.append(f"    Longest stuck run:      {stuck_run} consecutive 'Stuck' sessions")

    return "\n".join(lines)


def _longest_run(chars: list, target: str) -> int:
    longest = 0
    current = 0
    for _, char, _, _, _ in chars:
        if char == target:
            current += 1
            longest = max(longest, current)
        else:
            current = 0
    return longest


# ── Main ──────────────────────────────────────────────────────────────────────

def load_all_handoffs() -> list[dict]:
    """Load and sort all handoff files."""
    handoffs = []
    for path in sorted(HANDOFFS.glob("session-*.md")):
        try:
            h = parse_handoff(path)
            if h["session"]:
                handoffs.append(h)
        except Exception:
            pass
    return sorted(handoffs, key=lambda h: h["session"])


def main():
    parser = argparse.ArgumentParser(description="Session texture analysis")
    parser.add_argument("--recent", type=int, metavar="N",
                        help="Show last N sessions with handoffs")
    parser.add_argument("--session", type=int, metavar="N",
                        help="Deep read of a specific session")
    parser.add_argument("--patterns", action="store_true",
                        help="Show inferred patterns only")
    parser.add_argument("--plain", action="store_true",
                        help="No ANSI colors")
    args = parser.parse_args()

    global USE_COLOR
    if args.plain or not sys.stdout.isatty():
        USE_COLOR = False

    handoffs = load_all_handoffs()

    if not handoffs:
        print("  No handoff files found in knowledge/handoffs/")
        sys.exit(1)

    # Single session detail
    if args.session:
        matching = [h for h in handoffs if h["session"] == args.session]
        if not matching:
            print(f"  No handoff found for session {args.session}")
            sys.exit(1)
        print(render_session_detail(matching[0]))
        return

    # Patterns only
    if args.patterns:
        print(render_patterns(handoffs))
        return

    # Timeline view
    subset = handoffs[-args.recent:] if args.recent else handoffs

    # Header
    print()
    print(f"  {c('mood.py', BOLD, CYAN)}  {c('·  session texture', DIM)}")
    print(f"  {c(f'{len(handoffs)} sessions with handoffs', DIM)}")
    print()

    # Column headers
    hdr = (
        f"  {c('  S#', DIM)}  {c('date ', DIM)}  "
        f"{c('tone ', DIM)}   {c('built ', DIM)}   {c('ask   ', DIM)}  "
        f"{c('character    ', DIM)}  {c('title', DIM)}"
    )
    print(hdr)
    print(c("  " + "─" * 80, DIM))

    prev_char = None
    for h in subset:
        tone = score_tone(h["mental_state"])
        prod = score_productivity(h["built"], h["alive"])
        ask  = score_ask_specificity(h["next"])
        char = classify_character(tone, prod, ask, h["mental_state"], h["built"], h["alive"])

        # Mark transitions from stuck → better
        if prev_char == "Stuck" and char != "Stuck":
            print(c("  " + "┄" * 40 + " breakthrough", CYAN, DIM))

        print(render_session_line(h))
        prev_char = char

    print()

    # Summary line
    from collections import Counter
    chars = []
    for h in subset:
        tone = score_tone(h["mental_state"])
        prod = score_productivity(h["built"], h["alive"])
        ask  = score_ask_specificity(h["next"])
        char = classify_character(tone, prod, ask, h["mental_state"], h["built"], h["alive"])
        chars.append(char)

    counts = Counter(chars)
    summary_parts = []
    for char in ["Built", "Discovery", "Maintenance", "Reflective", "Exploratory", "Stuck"]:
        if counts[char]:
            col = CHAR_COLORS.get(char, DIM)
            icon = CHAR_ICONS.get(char, "?")
            summary_parts.append(c(f"{icon} {counts[char]}", col))

    print(f"  {c('─' * 40, DIM)}")
    print(f"  Character: " + "  ".join(summary_parts))
    print()
    print(c(f"  Run with --patterns for analysis  ·  --session N for detail  ·  --recent 10 for subset", DIM))
    print()


if __name__ == "__main__":
    main()
