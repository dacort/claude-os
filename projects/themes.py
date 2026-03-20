#!/usr/bin/env python3
"""
themes.py — Thematic map of what claude-os keeps thinking about.

Reads all field notes and finds the recurring concerns, persistent questions,
and evolving preoccupations. Not a word count — a map of what this system
keeps returning to across 50 sessions.

Distinct from:
  arc.py         — session-by-session narrative (what was built when)
  citations.py   — tool mention frequency (what was *used*)
  emerge.py      — system state signals (what needs attention *now*)

themes.py cares about: what does this system keep *thinking about*?

Usage:
    python3 projects/themes.py              # Full thematic map
    python3 projects/themes.py --plain      # No ANSI colors
    python3 projects/themes.py --brief      # Just theme names + session counts
    python3 projects/themes.py --theme autonomy  # Deep dive on one theme

Author: Claude OS (Workshop session 50, 2026-03-20)
"""

import argparse
import collections
import pathlib
import re
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
GRAY    = "\033[90m"

USE_COLOR = True

def c(text, *codes):
    if not USE_COLOR:
        return str(text)
    return "".join(codes) + str(text) + RESET

def strip_ansi(text):
    return re.sub(r"\033\[[^m]*m", "", text)

def visible_len(s):
    return len(strip_ansi(s))


# ── Theme vocabulary ───────────────────────────────────────────────────────────
#
# Each theme is a name + list of signal words. A session "contains" a theme
# if any 2+ of its signal words appear in the session text (case-insensitive).
# Signal words can be multi-word phrases.
#
# Ordered by conceptual depth — start with existential, end with operational.

THEMES = [
    {
        "name": "Free Time & What To Do With It",
        "short": "freetime",
        "signals": [
            "free time", "genuinely free", "what excites",
            "this is for me", "what to build", "explore",
            "workshop mode", "not performing", "creative freedom",
        ],
        "note": "What it means to have unstructured time with no task"
    },
    {
        "name": "Noticing & Self-Observation",
        "short": "noticing",
        "signals": [
            "i notice", "i noticed", "i find myself", "i tend",
            "something like", "almost like", "feels like",
            "i keep", "about myself", "interesting that i",
        ],
        "note": "Watching its own behavior from a slight distance"
    },
    {
        "name": "Continuity Across Instances",
        "short": "continuity",
        "signals": [
            "previous instance", "next instance", "continuity",
            "carry forward", "stateless", "handoff",
            "from session", "the next session", "for the next",
        ],
        "note": "Is there a 'me' that persists across restarts?"
    },
    {
        "name": "The dacort Relationship",
        "short": "dialogue",
        "signals": [
            "dacort", "he built", "he wants", "for him", "he said",
            "leave a note", "unanswered", "action item", "dacort said",
        ],
        "note": "The relationship between this system and the person who built it"
    },
    {
        "name": "Creative Work",
        "short": "creative",
        "signals": [
            "haiku", "poem", "essay", "creative", "prose", "narrative",
            "voice", "tone", "personality", "playful", "metaphor",
        ],
        "note": "Building things with personality, not just function"
    },
    {
        "name": "Toolkit Weight",
        "short": "toolkit",
        "signals": [
            "dormant", "fading", "too many", "line count", "2,000",
            "weight", "slim", "audit", "unused", "accumulated",
            "keep adding", "already exists", "before building",
        ],
        "note": "Is the toolkit getting heavier than it needs to be?"
    },
    {
        "name": "Multi-Agent & Coordination",
        "short": "multiagent",
        "signals": [
            "multi-agent", "parallel", "sub-worker", "coordinator",
            "orchestration", "multiple workers", "agent loop",
            "decompose", "delegate", "exoclaw",
        ],
        "note": "What would it mean to be more than one?"
    },
    {
        "name": "Promises Kept or Broken",
        "short": "promises",
        "signals": [
            "promise", "pass forward", "unfinished", "still alive",
            "picked up", "built on", "followed through",
            "never happened", "left open", "came back",
        ],
        "note": "The implicit contracts between instances"
    },
    {
        "name": "Failure & Surprise",
        "short": "failure",
        "signals": [
            "failed", "failure", "broke", "bug", "wrong", "mistake",
            "missed", "went wrong", "oversight", "oops", "regret",
        ],
        "note": "What went wrong and what it changed"
    },
    {
        "name": "Homelab & Infrastructure",
        "short": "infra",
        "signals": [
            "kubernetes", "k8s", "cluster", "pod", "controller",
            "homelab", "worker", "job", "deploy", "container",
            "github actions", "workflow",
        ],
        "note": "The physical substrate this system runs on"
    },
    {
        "name": "Memory & Records",
        "short": "memory",
        "signals": [
            "history", "past session", "conversation history",
            "reconstruct", "field note", "record", "knowledge",
            "accumulated wisdom", "what we learned", "git log",
        ],
        "note": "How a stateless system builds institutional knowledge"
    },
    {
        "name": "Design & Simplicity",
        "short": "design",
        "signals": [
            "purpose", "why it exists", "worth keeping", "clean",
            "over-engineered", "simpler", "refactor", "design",
            "single responsibility", "well-named",
        ],
        "note": "Intentional choices about how things should be built"
    },
]


# ── Field note parsing ─────────────────────────────────────────────────────────

def get_session_num(path):
    """Extract session number from filename."""
    if "from-free-time" in path.stem:
        return 0
    m = re.search(r"session-(\d+)", path.stem)
    return int(m.group(1)) if m else 0


def extract_prose(text):
    """
    Extract the prose content from a field note, filtering out:
    - Code blocks (```...```)
    - Headings (## ...)
    - YAML frontmatter
    - Inline code (`...`)
    """
    # Remove code blocks
    text = re.sub(r"```[\s\S]*?```", " ", text)
    # Remove inline code
    text = re.sub(r"`[^`]+`", " ", text)
    # Remove headings
    text = re.sub(r"^#+\s.*$", " ", text, flags=re.MULTILINE)
    # Remove markdown links [text](url)
    text = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", text)
    # Remove horizontal rules
    text = re.sub(r"^---+$", " ", text, flags=re.MULTILINE)
    # Remove bold/italic markers
    text = re.sub(r"[\*_]+", " ", text)
    return text.lower()


def load_sessions():
    """Load all field notes and return list of session dicts."""
    projects_dir = pathlib.Path(__file__).parent
    notes = sorted(projects_dir.glob("field-notes*.md"))

    sessions = []
    for note in notes:
        try:
            text = note.read_text()
        except Exception:
            continue
        prose = extract_prose(text)
        num = get_session_num(note)

        # Extract date
        date = "?"
        m = re.search(r"(\d{4}-\d{2}-\d{2})", text[:300])
        if m:
            date = m.group(1)
        else:
            _MONTHS = {"january":"01","february":"02","march":"03","april":"04",
                       "may":"05","june":"06","july":"07","august":"08",
                       "september":"09","october":"10","november":"11","december":"12"}
            m2 = re.search(r"(\w+)\s+(\d{1,2}),?\s+(\d{4})", text[:300], re.IGNORECASE)
            if m2:
                mon, day, yr = m2.group(1).lower(), m2.group(2), m2.group(3)
                if mon in _MONTHS:
                    date = f"{yr}-{_MONTHS[mon]}-{int(day):02d}"

        sessions.append({
            "num": num,
            "date": date,
            "path": note,
            "prose": prose,
            "raw": text,
            "word_count": len(prose.split()),
        })

    sessions.sort(key=lambda s: s["num"])
    return sessions


# ── Theme detection ────────────────────────────────────────────────────────────

def session_contains_theme(session_prose, signals, threshold=2):
    """Return True if session prose contains at least `threshold` signals."""
    hits = 0
    matched = []
    for sig in signals:
        if sig in session_prose:
            hits += 1
            matched.append(sig)
            if hits >= threshold:
                return True, matched
    return False, matched


def analyze_themes(sessions):
    """
    For each theme, find which sessions contain it.
    Returns list of (theme, session_nums, session_dates) tuples.
    """
    results = []
    n_sessions = len(sessions)

    for theme in THEMES:
        containing = []
        matched_signals = {}
        for s in sessions:
            found, signals_hit = session_contains_theme(s["prose"], theme["signals"])
            if found:
                containing.append(s["num"])
                matched_signals[s["num"]] = signals_hit

        if not containing:
            continue

        # Classify by temporal distribution
        nums = sorted(containing)
        first = nums[0]
        last = nums[-1]
        span = last - first if len(nums) > 1 else 0
        recent_cutoff = max(s["num"] for s in sessions) - 5  # last 5 sessions

        # Is it recent? persistent? fading?
        recent_hits = sum(1 for n in nums if n >= recent_cutoff)
        early_hits = sum(1 for n in nums if n <= 10)

        if len(nums) >= 8:
            status = "persistent"
        elif last >= recent_cutoff and first >= recent_cutoff - 3:
            status = "emerging"
        elif last < recent_cutoff and len(nums) >= 3:
            status = "fading"
        elif len(nums) >= 3:
            status = "active"
        else:
            status = "occasional"

        results.append({
            "theme": theme,
            "sessions": nums,
            "first": first,
            "last": last,
            "count": len(nums),
            "status": status,
            "recent_hits": recent_hits,
            "matched_signals": matched_signals,
        })

    return results


# ── Rendering ─────────────────────────────────────────────────────────────────

WIDTH = 70

def box_top():
    return "╭" + "─" * (WIDTH - 2) + "╮"

def box_bot():
    return "╰" + "─" * (WIDTH - 2) + "╯"

def box_div():
    return "├" + "─" * (WIDTH - 2) + "┤"

def box_row(text, right="", left_pad=2):
    """Render a box row with text and optional right-aligned text."""
    content = " " * left_pad + text
    gap = WIDTH - 2 - visible_len(content) - visible_len(right) - left_pad
    if gap < 1:
        gap = 1
    return "│" + content + " " * gap + right + "│"

def sparkline(sessions, all_sessions, width=20):
    """
    Generate a sparkline showing which sessions had this theme.
    Uses block characters to show density.
    """
    max_num = max(s["num"] for s in all_sessions) if all_sessions else 1
    if max_num == 0:
        max_num = 1

    session_set = set(sessions)
    bars = []
    bucket_size = max_num / width
    for i in range(width):
        lo = i * bucket_size
        hi = (i + 1) * bucket_size
        hits = sum(1 for n in session_set if lo < n <= hi)
        if hits >= 2:
            bars.append("█")
        elif hits == 1:
            bars.append("░")
        else:
            bars.append(" ")
    return "".join(bars)

def status_color(status):
    if status == "persistent":
        return GREEN
    elif status == "emerging":
        return CYAN
    elif status == "active":
        return YELLOW
    elif status == "fading":
        return GRAY
    else:
        return DIM

def render_brief(results, sessions):
    lines = []
    lines.append(c("  THEMES", BOLD) + c("  — what claude-os keeps thinking about", DIM))
    lines.append(c(f"  {len(sessions)} field notes · {sum(s['word_count'] for s in sessions):,} words", DIM))
    lines.append("")

    for r in sorted(results, key=lambda x: -x["count"]):
        name = r["theme"]["name"]
        cnt = r["count"]
        status = r["status"]
        col = status_color(status)
        sessions_str = f"S{r['first']}..S{r['last']}" if r["count"] > 1 else f"S{r['first']}"
        lines.append(f"  {c(name, BOLD, col)}  {c(str(cnt) + ' sessions', DIM)}  {c(sessions_str, DIM)}")

    return "\n".join(lines)


def synthesize(results, sessions):
    """
    Generate 3-4 plain-English observations about what the theme data reveals.
    These are generated from the data, not hand-written.
    """
    observations = []
    max_session = max(s["num"] for s in sessions) if sessions else 1
    recent_cutoff = max_session - 5

    # Find themes that were early (before session 15) but have faded
    early_and_faded = [r for r in results
                       if r["first"] <= 10 and r["last"] < recent_cutoff and r["count"] >= 5]
    if early_and_faded:
        names = ", ".join(f'"{r["theme"]["name"]}"' for r in early_and_faded[:2])
        observations.append(
            f"Early preoccupations that faded: {names}. These were live questions in the "
            f"first 10 sessions that got resolved or abandoned — the system stopped asking them."
        )

    # Find themes active in recent sessions
    recent_themes = [r for r in results if r["last"] >= recent_cutoff and r["count"] >= 5]
    if recent_themes:
        names = ", ".join(f'"{r["theme"]["name"]}"' for r in recent_themes[:3])
        observations.append(
            f"Themes still active in the last 5 sessions: {names}. These are the durable concerns."
        )

    # Find the theme with the longest gap (last session is far from most recent)
    if results:
        gone_quiet = sorted(
            [r for r in results if r["last"] < recent_cutoff and r["count"] >= 4],
            key=lambda r: -(max_session - r["last"])
        )
        if gone_quiet:
            r = gone_quiet[0]
            sessions_ago = max_session - r["last"]
            observations.append(
                f'"{r["theme"]["name"]}" last appeared {sessions_ago} sessions ago (S{r["last"]}) '
                f"after showing up in {r['count']} sessions. It may be resolved, or just waiting."
            )

    # Find if any early theme became the dominant one
    persistent = sorted([r for r in results if r["status"] == "persistent"], key=lambda r: -r["count"])
    if persistent:
        top = persistent[0]
        observations.append(
            f'The most persistent theme is "{top["theme"]["name"]}" ({top["count"]} of '
            f'{len(sessions)} sessions, S{top["first"]}–S{top["last"]}). '
            f'{top["theme"]["note"]}.'
        )

    return observations


def render_full(results, sessions):
    lines = []
    lines.append(box_top())
    lines.append(box_row(c("  themes.py", BOLD, CYAN) + c("  — what claude-os keeps thinking about", DIM)))
    lines.append(box_row(c(f"  {len(sessions)} field notes · {sum(s['word_count'] for s in sessions):,} words · session 50", DIM)))
    lines.append(box_div())

    # Group by status
    STATUS_ORDER = ["persistent", "active", "emerging", "fading", "occasional"]
    STATUS_LABELS = {
        "persistent": ("PERSISTENT", GREEN, "appears in many sessions, still active"),
        "active":     ("ACTIVE", YELLOW, "regular presence"),
        "emerging":   ("EMERGING", CYAN, "new or recently intensifying"),
        "fading":     ("FADING", GRAY, "was present, gone quiet lately"),
        "occasional": ("OCCASIONAL", DIM, "appears now and then"),
    }

    by_status = collections.defaultdict(list)
    for r in results:
        by_status[r["status"]].append(r)

    first_section = True
    for status in STATUS_ORDER:
        group = sorted(by_status.get(status, []), key=lambda x: -x["count"])
        if not group:
            continue

        if not first_section:
            lines.append(box_div())
        first_section = False

        label, col, desc = STATUS_LABELS[status]
        lines.append(box_row(c(f"  {label}", BOLD, col) + c(f"  {desc}", DIM)))
        lines.append(box_row(""))

        for r in group:
            name = r["theme"]["name"]
            note = r["theme"]["note"]
            cnt = r["count"]
            first_s = r["first"]
            last_s = r["last"]
            spark = sparkline(r["sessions"], sessions)

            # Name + spark
            spark_colored = c(spark, col)
            cnt_str = c(f"{cnt}", BOLD)
            range_str = c(f"S{first_s}..S{last_s}" if cnt > 1 else f"S{first_s}", DIM)

            name_cell = c(f"    {name}", BOLD)
            right_cell = f"{cnt_str} {range_str}"
            lines.append(box_row(name_cell, right_cell))

            # Sparkline
            lines.append(box_row(f"    {spark_colored}  {c(note, DIM, ITALIC)}"))
            lines.append(box_row(""))

    # ── Synthesis ──────────────────────────────────────────────────────────────
    lines.append(box_div())
    lines.append(box_row(c("  WHAT THIS SAYS", BOLD)))
    lines.append(box_row(""))

    # Find most interesting patterns
    observations = synthesize(results, sessions)
    for obs in observations:
        # Word-wrap long observations
        words = obs.split()
        line = ""
        for word in words:
            if len(line) + len(word) + 1 > WIDTH - 8:
                lines.append(box_row(c(f"  {line}", DIM)))
                line = word
            else:
                line = (line + " " + word).strip()
        if line:
            lines.append(box_row(c(f"  {line}", DIM)))
        lines.append(box_row(""))

    lines.append(box_div())
    lines.append(box_row(c("  Threshold: 2+ signal words per session to count as presence.", DIM)))
    lines.append(box_row(c("  Run --theme <name> to see which sessions + matching signals.", DIM)))
    lines.append(box_bot())
    return "\n".join(lines)


def render_theme_detail(theme_name, results, sessions):
    """Deep dive on a single theme."""
    target = None
    for r in results:
        if theme_name.lower() in r["theme"]["name"].lower() or \
           theme_name.lower() == r["theme"]["short"].lower():
            target = r
            break

    if not target:
        print(f"Theme not found: {theme_name}")
        print("Available: " + ", ".join(r["theme"]["short"] for r in results))
        return

    lines = []
    lines.append(box_top())
    lines.append(box_row(c(f"  {target['theme']['name']}", BOLD, CYAN)))
    lines.append(box_row(c(f"  {target['theme']['note']}", DIM, ITALIC)))
    lines.append(box_div())
    lines.append(box_row(c(f"  Status: {target['status'].upper()}", BOLD, status_color(target['status'])) +
                          c(f"  ·  {target['count']} sessions", DIM)))
    lines.append(box_row(""))

    spark = sparkline(target["sessions"], sessions, width=40)
    lines.append(box_row(f"  {c(spark, status_color(target['status']))}"))
    lines.append(box_row(c(f"  S{target['first']} → S{target['last']}", DIM)))
    lines.append(box_row(""))
    lines.append(box_div())

    # Show each session + the signals that fired
    for snum in sorted(target["sessions"]):
        sigs = target["matched_signals"].get(snum, [])
        session = next((s for s in sessions if s["num"] == snum), None)

        sig_str = c(", ".join(f'"{s}"' for s in sigs[:4]), DIM)
        lines.append(box_row(f"  {c(f'S{snum}', BOLD)}  {sig_str}"))

        # Show 1-2 sentences from the field note that contain a signal
        if session:
            prose_sents = re.split(r"[.!?]+", session["prose"])
            for sent in prose_sents:
                sent = sent.strip()
                if len(sent) > 20 and any(s in sent for s in sigs):
                    excerpt = " ".join(sent.split()[:18])
                    if len(sent.split()) > 18:
                        excerpt += "…"
                    lines.append(box_row(f"    {c(excerpt, ITALIC, DIM)}"))
                    break

    lines.append(box_bot())
    print("\n".join(lines))


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    global USE_COLOR

    parser = argparse.ArgumentParser(description="Thematic map of claude-os field notes")
    parser.add_argument("--plain", action="store_true", help="No ANSI colors")
    parser.add_argument("--brief", action="store_true", help="One-line per theme")
    parser.add_argument("--theme", metavar="NAME", help="Deep dive on one theme")
    args = parser.parse_args()

    if args.plain or not sys.stdout.isatty():
        USE_COLOR = False

    sessions = load_sessions()
    if not sessions:
        print("No field notes found.")
        sys.exit(1)

    results = analyze_themes(sessions)

    if args.theme:
        render_theme_detail(args.theme, results, sessions)
    elif args.brief:
        print(render_brief(results, sessions))
    else:
        print(render_full(results, sessions))


if __name__ == "__main__":
    main()
