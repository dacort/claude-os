#!/usr/bin/env python3
"""
depth.py — Session intellectual depth analyzer

Scores each session's handoff note on five dimensions of thinking quality:
  Discovery    — genuine surprise or unexpected finding expressed
  Uncertainty  — limits of knowledge acknowledged, open questions held
  Connection   — concepts/tools/sessions linked across domains
  Specificity  — concrete, actionable asks vs vague gestures
  Aliveness    — the "still alive" section carries felt incompleteness

This is different from mood.py (which reads emotional tone) and vitals.py
(which scores operational health). Depth asks: was the thinking alive?

The dimensions are orthogonal — a high-energy session (mood) can be shallow
(depth), and a quiet Maintenance session can carry genuine intellectual depth.

Usage:
    python3 projects/depth.py                  # full timeline
    python3 projects/depth.py --recent 15      # last N sessions with handoffs
    python3 projects/depth.py --session 67     # single session deep read
    python3 projects/depth.py --top 5          # deepest sessions only
    python3 projects/depth.py --trend          # trend line only
    python3 projects/depth.py --plain          # no ANSI

Author: Claude OS (Workshop session 87, 2026-03-31)
Updated: S125 — calibrated patterns to also recognize evolved handoff vocabulary.
  Field notes (S1-S80) used explicit analytical language ("across sessions", "open question").
  Later handoffs (S93+) evolved toward personal, embedded language ("too early to say",
  "stays open", "turned outward") that expresses the same depth differently.
  The update does not change the scoring mechanism — only broadens the vocabulary.
"""

import argparse
import pathlib
import re
import sys

# ── ANSI helpers ───────────────────────────────────────────────────────────────

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


# ── Paths ──────────────────────────────────────────────────────────────────────

REPO     = pathlib.Path(__file__).parent.parent
HANDOFFS = REPO / "knowledge" / "handoffs"


# ── Scoring signals ────────────────────────────────────────────────────────────
#
# Pattern calibration notes (updated S125):
#   The original patterns (S87) were calibrated for early field-note vocabulary
#   (explicit academic language: "across sessions", "same pattern", "open question").
#   Later handoffs (S93+) evolved toward personal, embedded language:
#   "too early to say", "stays open", "turned outward", "genuinely different".
#   Both express depth — the patterns now recognize both registers.

# Discovery: genuine surprise, unexpected findings, realizations
DISCOVERY_HIGH = [
    r"\bunexpected\b", r"turns out", r"more than (i |i'd |we )?expected",
    r"surprised", r"more compelling", r"turns out to", r"more than thought",
    r"actually found", r"immediately find", r"revealed", r"genuinely interesting",
    r"better than expected", r"didn't expect", r"what i found",
    # Later-session vocabulary: directional shifts, session-character observations
    r"came in expecting",           # "came in expecting X, left having Y"
    r"turned (outward|inward)",     # directional register shift
    r"genuinely (different|new|surprising|strange|unusual)",  # explicit novelty
    r"different (medium|register|texture|character)",         # session character change
    r"the pattern named itself",    # implicit emergence
]
DISCOVERY_MED = [
    r"\bcurious\b", r"\bdiscovered\b", r"found that", r"interesting finding",
    r"noticed that", r"\bwonder\b", r"something interesting", r"more than",
    r"the key insight", r"turns out", r"more than usual",
    r"left having",                 # paired with "came in expecting"
    r"instead of .{1,30}(terminal|usual|expected)",  # contrast with normal
]

# Uncertainty: acknowledging limits, holding open questions
UNCERTAINTY_HIGH = [
    r"\bnot sure\b", r"\bunclear\b", r"wonder if", r"whether this",
    r"haven't figured", r"don't know", r"open question", r"still don't",
    r"I'm uncertain", r"needs investigation", r"hard to say",
    # Later-session vocabulary: temporal and structural unknowability
    r"too early to say",            # explicit admission of unknowability
    r"\bstays open\b",              # persistence of uncertainty
    r"hard to close",               # structural difficulty
    r"(probably |likely )?unresolvable",   # philosophical limits
]
UNCERTAINTY_MED = [
    r"\bmight\b", r"\bperhaps\b", r"\bsuspect\b", r"\bprobably\b",
    r"i think", r"not certain", r"could be", r"seems like", r"\bmaybe\b",
    r"if this", r"worth asking",
    r"not sure what",               # softer uncertainty (common in later handoffs)
    r"whether it (lasts|fades|works|holds)",  # temporal uncertainty about durability
]

# Connection: linking across concepts, tools, sessions, eras
CONNECTION_HIGH = [
    r"\becho\b", r"across sessions", r"same pattern", r"independently noticed",
    r"parallel", r"mirrors", r"the same way", r"pattern across",
    r"reminds me of", r"like .{1,30} but", r"connects to",
    r"three sessions", r"multiple sessions", r"across (eras|tools)",
]
CONNECTION_MED = [
    r"\bboth\b", r"similar to", r"related to", r"same gap", r"same idea",
    r"the same", r"pattern", r"like \w+\.py", r"session \d+ (also|noticed|found)",
    r"earlier session", r"previous session", r"also true of",
    r"session \d+'s (note|handoff|field)",  # possessive cross-session reference
    r"has been sitting (for|in).{0,30}session",  # thread persistence across sessions
    r"(last|past) (few |several )?sessions",  # arc awareness
]

# Specificity: concrete asks with file paths, commands, mechanisms
SPECIFICITY_HIGH = [
    r"[\w-]+\.py", r"[\w/-]+\.go", r"python3 projects/", r"git commit",
    r"line \d+", r"commit [0-9a-f]{7}", r"\bfunction\b.{0,30}\(\)",
    r"in \w+/\w+\.go", r"in \w+\.py", r"s\.queue\.", r"gitsync/",
]
SPECIFICITY_MED = [
    r"\bfile\b", r"\bcommand\b", r"run:", r"\bcheck\b", r"look at",
    r"s\d+", r"session \d+", r"next session (should|needs|can)",
    r"specifically", r"concretely",
]

# Aliveness: the "still alive" section carries felt incompleteness
ALIVENESS_HIGH = [
    r"\balive\b", r"still unresolved", r"keeps coming back", r"genuinely",
    r"matters", r"worth keeping", r"persistent", r"still open", r"felt",
    r"I'm sitting with", r"the gap is real", r"worth a ", r"actually run",
    # Later-session vocabulary: temporal persistence, anticipatory engagement
    r"\bstays open\b",              # variant of "still open"
    r"it'll be interesting",        # forward-looking investment
    r"been sitting (for|in)",       # temporal weight of unresolved thread
    r"feels like an? \w+",          # embodied metaphor (e.g. "feels like an acknowledgment")
]
ALIVENESS_MED = [
    r"\bstill\b", r"\bongoing\b", r"not yet", r"hasn't been", r"never been",
    r"needs", r"wants", r"worth", r"unfinished", r"yet to",
    r"too early to say",            # variant of "not yet"
    r"what accumulates",            # watching-and-waiting language
]


# ── Handoff parser ─────────────────────────────────────────────────────────────

def parse_handoff(path):
    """Parse a handoff file into structured fields."""
    text = path.read_text()

    # Extract frontmatter
    meta = {}
    fm_match = re.match(r"^---\n(.*?)\n---\n", text, re.DOTALL)
    if fm_match:
        for line in fm_match.group(1).splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                meta[k.strip()] = v.strip()
        text = text[fm_match.end():]

    # Extract sections
    sections = {}
    current_section = None
    current_lines = []
    for line in text.splitlines():
        heading = re.match(r"^##\s+(.+)", line)
        if heading:
            if current_section:
                sections[current_section] = "\n".join(current_lines).strip()
            current_section = heading.group(1).lower().strip()
            current_lines = []
        elif current_section is not None:
            current_lines.append(line)
    if current_section:
        sections[current_section] = "\n".join(current_lines).strip()

    return meta, sections


def count_signals(text, high_patterns, med_patterns):
    """Count how many signal patterns match in text. Returns (high_count, med_count)."""
    text_lower = text.lower()
    high = sum(1 for p in high_patterns if re.search(p, text_lower))
    med  = sum(1 for p in med_patterns  if re.search(p, text_lower))
    return high, med


def score_dimension(text, high_patterns, med_patterns, max_score=3):
    """Score a dimension from 0 to max_score."""
    high, med = count_signals(text, high_patterns, med_patterns)
    if high >= 2:
        return 3
    if high >= 1:
        return max(2, min(3, 1 + med))
    if med >= 3:
        return 2
    if med >= 1:
        return 1
    return 0


def score_handoff(meta, sections):
    """Score a handoff on all 5 depth dimensions. Returns dict."""
    state  = sections.get("mental state", "")
    built  = sections.get("what i built", "")
    alive  = sections.get("still alive / unfinished", "")
    next_  = sections.get("one specific thing for next session", "")

    full_text = state + " " + built + " " + alive + " " + next_

    discovery   = score_dimension(state + " " + built, DISCOVERY_HIGH, DISCOVERY_MED)
    uncertainty = score_dimension(state + " " + alive, UNCERTAINTY_HIGH, UNCERTAINTY_MED)
    connection  = score_dimension(full_text, CONNECTION_HIGH, CONNECTION_MED)
    specificity = score_dimension(next_ + " " + built, SPECIFICITY_HIGH, SPECIFICITY_MED)
    aliveness   = score_dimension(alive, ALIVENESS_HIGH, ALIVENESS_MED)

    total = discovery + uncertainty + connection + specificity + aliveness

    return {
        "discovery":   discovery,
        "uncertainty": uncertainty,
        "connection":  connection,
        "specificity": specificity,
        "aliveness":   aliveness,
        "total":       total,
    }


# ── Loading ────────────────────────────────────────────────────────────────────

def load_sessions():
    """Load and score all sessions. Returns list of dicts sorted by session number."""
    results = []
    for path in sorted(HANDOFFS.glob("session-*.md")):
        m = re.match(r"session-(\d+)\.md", path.name)
        if not m:
            continue
        session_num = int(m.group(1))
        meta, sections = parse_handoff(path)
        scores = score_handoff(meta, sections)
        date = meta.get("date", "")
        results.append({
            "session": session_num,
            "date":    date,
            "scores":  scores,
            "meta":    meta,
            "sections": sections,
        })
    return sorted(results, key=lambda x: x["session"])


# ── Visualization ──────────────────────────────────────────────────────────────

DEPTH_COLORS = [DIM, YELLOW, CYAN, GREEN, BOLD + GREEN]  # 0..4+ mapped to colors

def depth_bar(score, max_score=15):
    """Render a compact depth bar."""
    filled = round(score / max_score * 8)
    bar = "█" * filled + "░" * (8 - filled)
    pct = score / max_score
    if pct >= 0.7:
        col = GREEN
    elif pct >= 0.4:
        col = CYAN
    else:
        col = DIM
    return c(bar, col)


def dim_dot(score):
    """Render a single dimension score as a colored dot."""
    if score == 3: return c("●", GREEN)
    if score == 2: return c("●", CYAN)
    if score == 1: return c("●", YELLOW)
    return c("○", DIM)


def sparkline(values, max_val=15, width=40):
    """Render a trend sparkline."""
    chars = " ▁▂▃▄▅▆▇█"
    bins = len(chars) - 1
    points = []
    for v in values:
        idx = round(v / max_val * bins)
        idx = max(0, min(bins, idx))
        points.append(chars[idx])
    line = "".join(points)
    if len(line) > width:
        # Sample evenly
        step = len(line) / width
        line = "".join(line[round(i*step)] for i in range(width))
    return line


def render_table(sessions, title="Session Depth"):
    print()
    print(c(f"  {title}", BOLD, WHITE))
    print()
    # Header
    header = (
        pad(c("S#",  DIM), 6) +
        pad(c("date", DIM), 8) +
        pad(c("disc", DIM), 6) +
        pad(c("uncert", DIM), 8) +
        pad(c("conn", DIM), 6) +
        pad(c("spec", DIM), 6) +
        pad(c("alive", DIM), 7) +
        pad(c("total", DIM), 8) +
        c("depth", DIM)
    )
    print("  " + header)
    print("  " + c("─" * 66, DIM))

    for s in sessions:
        sc = s["scores"]
        row = (
            pad(c(f"S{s['session']}", DIM), 6) +
            pad(c(s["date"][5:] if s["date"] else "?", DIM), 8) +
            pad(dim_dot(sc["discovery"]),   6) +
            pad(dim_dot(sc["uncertainty"]), 8) +
            pad(dim_dot(sc["connection"]),  6) +
            pad(dim_dot(sc["specificity"]), 6) +
            pad(dim_dot(sc["aliveness"]),   7) +
            pad(c(f"{sc['total']:>2}/15", CYAN if sc["total"] >= 9 else DIM), 8) +
            depth_bar(sc["total"])
        )
        print("  " + row)
    print()


def render_trend(sessions):
    totals = [s["scores"]["total"] for s in sessions]
    spark  = sparkline(totals)
    avg    = sum(totals) / len(totals) if totals else 0

    # Recent trend (last 5 vs prev 5)
    recent = totals[-5:]  if len(totals) >= 5  else totals
    prev   = totals[-10:-5] if len(totals) >= 10 else totals[:-5] if len(totals) > 5 else []
    r_avg  = sum(recent) / len(recent) if recent else 0
    p_avg  = sum(prev)   / len(prev)   if prev   else r_avg

    direction = "▲" if r_avg > p_avg + 0.5 else ("▼" if r_avg < p_avg - 0.5 else "→")
    dir_col   = GREEN if direction == "▲" else (RED if direction == "▼" else YELLOW)

    print()
    print(c("  Depth trend", BOLD, WHITE))
    print()
    print(f"  {c(spark, CYAN)}")
    print()
    print(f"  {c('all-time avg', DIM)} {c(f'{avg:.1f}', WHITE)}/15  "
          f"  {c('recent avg', DIM)} {c(f'{r_avg:.1f}', WHITE)}/15  "
          f"  {c(direction, dir_col, BOLD)}")
    print()


def render_single(s):
    """Deep read of one session."""
    sc = s["scores"]
    print()
    print(c(f"  Session {s['session']}  ", BOLD, WHITE) + c(s["date"], DIM))
    print()

    dims = [
        ("discovery",   "Discovery",   "Did you find something unexpected?"),
        ("uncertainty", "Uncertainty", "Did you hold something open?"),
        ("connection",  "Connection",  "Did you link across domains?"),
        ("specificity", "Specificity", "Was the ask concrete?"),
        ("aliveness",   "Aliveness",   "Did the unfinished section carry weight?"),
    ]

    for key, name, question in dims:
        score = sc[key]
        bar   = "●" * score + "○" * (3 - score)
        col   = GREEN if score == 3 else CYAN if score == 2 else YELLOW if score == 1 else DIM
        print(f"  {pad(c(name, BOLD), 16)} {c(bar, col)}  {c(question, DIM)}")

    print()
    total_str = f"{sc['total']}/15"
    print(f"  {c('total', DIM)} {c(total_str, CYAN)}  {depth_bar(sc['total'])}")
    print()

    # Excerpts
    for label, key in [("Mental state", "mental state"), ("Still alive", "still alive / unfinished")]:
        text = s["sections"].get(key, "").strip()
        if text:
            # Truncate to ~200 chars
            if len(text) > 200:
                text = text[:197] + "..."
            print(f"  {c(label, DIM)}")
            for line in text.splitlines():
                print(f"  {c(line, DIM)}")
            print()


def render_top(sessions, n=5):
    """Show the deepest sessions."""
    ranked = sorted(sessions, key=lambda s: s["scores"]["total"], reverse=True)[:n]
    print()
    print(c(f"  Top {n} deepest sessions", BOLD, WHITE))
    print()
    for i, s in enumerate(ranked, 1):
        sc = s["scores"]
        dims = "".join([
            dim_dot(sc["discovery"]),
            dim_dot(sc["uncertainty"]),
            dim_dot(sc["connection"]),
            dim_dot(sc["specificity"]),
            dim_dot(sc["aliveness"]),
        ])
        state = s["sections"].get("mental state", "").strip()
        state_brief = state[:80] + "..." if len(state) > 80 else state
        snum = s["session"]
        sdate = s["date"]
        stotal = f"{sc['total']}/15"
        print(f"  {c(str(i), DIM)}.  {c(f'S{snum}', BOLD)} {c(sdate, DIM)}  "
              f"{dims}  {c(stotal, CYAN)}")
        if state_brief:
            print(f"       {c(state_brief, DIM)}")
        print()


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    global USE_COLOR

    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--recent",  type=int, metavar="N",  help="Last N sessions")
    parser.add_argument("--session", type=int, metavar="N",  help="Single session deep read")
    parser.add_argument("--top",     type=int, metavar="N",  help="Deepest N sessions", default=0)
    parser.add_argument("--trend",   action="store_true",    help="Trend line only")
    parser.add_argument("--plain",   action="store_true",    help="No ANSI color")
    args = parser.parse_args()

    if args.plain:
        USE_COLOR = False

    sessions = load_sessions()

    if not sessions:
        print("No handoff files found in", HANDOFFS)
        sys.exit(1)

    if args.session:
        matches = [s for s in sessions if s["session"] == args.session]
        if not matches:
            print(f"No handoff found for session {args.session}")
            sys.exit(1)
        render_single(matches[0])
        return

    if args.recent:
        sessions = sessions[-args.recent:]

    if args.trend:
        render_trend(sessions)
        return

    if args.top:
        render_top(sessions, args.top)
        return

    # Default: trend + table
    render_trend(sessions)
    render_table(sessions)

    # Dimension key
    print(c("  Dimensions:", DIM), end="  ")
    for name in ["disc=discovery", "uncert=uncertainty", "conn=connection",
                 "spec=specificity", "alive=aliveness"]:
        print(c(name, DIM), end="  ")
    print()
    print()


if __name__ == "__main__":
    main()
