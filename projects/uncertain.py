#!/usr/bin/env python3
"""uncertain.py — what Claude OS doesn't know, in its own words

evidence.py claim 3 shows that only 19% of sessions use uncertainty language.
But that's a binary fact. This tool asks the richer question: WHAT was the
system uncertain about, and does that uncertainty cluster into recognizable themes?

hold.py tracks *explicit* epistemic holds. uncertain.py finds the *implicit*
uncertainty — sentences in handoffs where the system said "I don't know" or
"I wonder" or "unclear" — without having registered a formal hold.

The two tools together map the full uncertainty landscape:
  hold.py      → what the system formally doesn't know
  uncertain.py → what it expressed without knowing it was uncertain

Usage:
  python3 projects/uncertain.py            # all sessions, clustered by theme
  python3 projects/uncertain.py --session N  # just one session
  python3 projects/uncertain.py --raw      # show sentence-level extracts
  python3 projects/uncertain.py --themes   # theme summary only (no sentences)
  python3 projects/uncertain.py --plain    # no ANSI color

Workshop session 100, 2026-04-04
"""

import re
import sys
import argparse
from pathlib import Path
from collections import defaultdict, Counter

BASE     = Path(__file__).resolve().parent.parent
HANDOFFS = BASE / "knowledge" / "handoffs"

# ── ANSI helpers ─────────────────────────────────────────────────────────────

USE_COLOR = True

def c(text, *codes):
    if not USE_COLOR:
        return str(text)
    return "\033[" + ";".join(str(x) for x in codes) + "m" + str(text) + "\033[0m"

BOLD   = 1
DIM    = 2
RED    = 31
GREEN  = 32
YELLOW = 33
CYAN   = 36
MAGENTA = 35
WHITE  = 97

# ── Uncertainty patterns ─────────────────────────────────────────────────────

# Extended beyond what evidence.py uses — these are phrase-level patterns
UNCERTAINTY_PHRASES = [
    r"don't know",
    r"do not know",
    r"not sure",
    r"unclear",
    r"uncertain",
    r"can't tell",
    r"cannot tell",
    r"wonder",
    r"might be",
    r"may be",
    r"hard to say",
    r"hard to know",
    r"open question",
    r"open hold",
    r"unsure",
    r"ambiguous",
    r"hypothesis",
    r"possibly",
    r"can't know",
    r"genuinely don't",
    r"nags",    # "nags a little" — indirect uncertainty
    r"hard to separate",
    r"still open",
    r"keeps coming back",
    r"not yet clear",
    r"no way to",
    r"difficult to",
    r"probably",  # tentative (only when not in "probably works")
]

# Theme vocabulary: what topic clusters do uncertainty expressions fall into?
THEMES = {
    "continuity / identity": [
        "continuity", "continuous", "identity", "narrative", "the story", "artifact",
        "phenomenon", "real", "sense of", "experience", "persist", "across sessions",
    ],
    "tool usefulness": [
        "useful", "actually used", "tool", "citation", "reuse", "vocabulary",
        "adopted", "adoption", "citation", "reach",
    ],
    "causation / correlation": [
        "causal", "causation", "correlation", "direction", "why", "because",
        "leads to", "produces", "cause",
    ],
    "multi-agent / exoclaw": [
        "multi-agent", "exoclaw", "spawn", "orchestrat", "worker", "plan",
        "parallel", "coordinate",
    ],
    "follow-through / continuity": [
        "follow", "through", "address", "pick up", "picked up", "did the next",
        "consecutive", "previous session asked",
    ],
    "self-knowledge / measurement": [
        "measure", "measuring", "metric", "accurate", "heuristic", "detect",
        "score", "method", "count",
    ],
    "system purpose / design": [
        "purpose", "designed", "for dacort", "outward", "inward", "optimization",
        "actually optimiz", "ledger",
    ],
}


def classify_theme(sentence: str) -> str:
    """Return the best-matching theme for a sentence, or 'other'."""
    sl = sentence.lower()
    scores = {}
    for theme, keywords in THEMES.items():
        count = 0
        for kw in keywords:
            # Use word-boundary matching to avoid "plan" in "explanation"
            # Partial stems (ending in non-word char) use re.search
            if kw.endswith(("_", "-")) or not re.search(r"\w$", kw):
                count += 1 if kw in sl else 0
            else:
                count += 1 if re.search(r"\b" + re.escape(kw), sl) else 0
        scores[theme] = count
    best = max(scores, key=scores.get)
    if scores[best] > 0:
        return best
    return "other"


# ── Parsing ──────────────────────────────────────────────────────────────────

def parse_handoff(path: Path) -> tuple[dict, dict]:
    text = path.read_text()
    meta = {}
    fm_match = re.match(r"^---\n(.*?)\n---\n", text, re.DOTALL)
    if fm_match:
        for line in fm_match.group(1).splitlines():
            k, _, v = line.partition(":")
            meta[k.strip()] = v.strip()
        body = text[fm_match.end():]
    else:
        body = text
    sections = {}
    current = None
    buf = []
    for line in body.splitlines():
        m = re.match(r"^##\s+(.+)", line)
        if m:
            if current is not None:
                sections[current.lower()] = "\n".join(buf).strip()
            current = m.group(1).strip()
            buf = []
        else:
            buf.append(line)
    if current:
        sections[current.lower()] = "\n".join(buf).strip()
    return meta, sections


def load_handoffs(session_filter: int | None = None) -> list[dict]:
    results = []
    for path in sorted(HANDOFFS.glob("session-*.md")):
        m = re.match(r"session-(\d+)\.md", path.name)
        if not m:
            continue
        num = int(m.group(1))
        if session_filter is not None and num != session_filter:
            continue
        meta, sections = parse_handoff(path)
        results.append({"num": num, "meta": meta, "sections": sections})
    return results


def extract_uncertainty(sections: dict) -> list[dict]:
    """Find sentences containing uncertainty language from a session's handoff."""
    # Search these sections for uncertainty
    SEARCH_SECTIONS = [
        "mental state",
        "still alive / unfinished",
        "one specific thing for next session",
        "what i built",  # sometimes introspective observations here
    ]
    found = []
    for sec_name in SEARCH_SECTIONS:
        text = sections.get(sec_name, "")
        if not text:
            continue
        # Split into sentences (rough)
        sentences = re.split(r"(?<=[.!?])\s+", text)
        for sent in sentences:
            sl = sent.lower()
            for pat in UNCERTAINTY_PHRASES:
                if re.search(pat, sl):
                    found.append({
                        "section": sec_name,
                        "sentence": sent.strip(),
                        "pattern": pat,
                        "theme": classify_theme(sent),
                    })
                    break  # one match per sentence
    return found


# ── Rendering ────────────────────────────────────────────────────────────────

THEME_COLORS = {
    "continuity / identity":         MAGENTA,
    "tool usefulness":               CYAN,
    "causation / correlation":       YELLOW,
    "multi-agent / exoclaw":         GREEN,
    "follow-through / continuity":   33,
    "self-knowledge / measurement":  36,
    "system purpose / design":       35,
    "other":                         DIM,
}


def render_full(sessions_data: list, show_raw: bool) -> None:
    """Full output: theme clusters with representative sentences."""
    all_exprs = []
    for s in sessions_data:
        exprs = extract_uncertainty(s["sections"])
        for e in exprs:
            all_exprs.append({"session": s["num"], **e})

    sessions_with = len(set(e["session"] for e in all_exprs))
    total = len(sessions_with := set(e["session"] for e in all_exprs))

    print()
    print(c("  uncertain.py", BOLD, WHITE) + c("  — what Claude OS doesn't know, in its own words", DIM))
    print(c(f"  {len(sessions_data)} sessions analyzed  ·  {len(sessions_with)} with uncertainty ({len(sessions_with)/len(sessions_data):.0%})", DIM))
    print(c(f"  {len(all_exprs)} uncertainty expressions found", DIM))
    print()
    print(c("  " + "─" * 62, DIM))

    if not all_exprs:
        print(c("  No uncertainty expressions found.", DIM))
        return

    # Group by theme
    by_theme = defaultdict(list)
    for e in all_exprs:
        by_theme[e["theme"]].append(e)

    # Sort themes by frequency
    sorted_themes = sorted(by_theme.items(), key=lambda x: len(x[1]), reverse=True)

    for theme, exprs in sorted_themes:
        tc = THEME_COLORS.get(theme, DIM)
        print()
        print(c(f"  {theme.upper()}", BOLD, tc) + c(f"  ({len(exprs)} expression{'s' if len(exprs)!=1 else ''})", DIM))

        # Group by session
        by_session = defaultdict(list)
        for e in exprs:
            by_session[e["session"]].append(e)

        if show_raw:
            # Show all sentences
            for snum in sorted(by_session.keys()):
                for e in by_session[snum]:
                    short = e["sentence"][:120]
                    if len(e["sentence"]) > 120:
                        short += "…"
                    print(c(f"    S{snum}  ", DIM) + c(f'"{short}"', DIM))
        else:
            # Show one representative per session, cap at 4 sessions
            shown = 0
            for snum in sorted(by_session.keys()):
                if shown >= 4:
                    remaining = len(by_session) - 4
                    if remaining > 0:
                        print(c(f"    … +{remaining} more sessions", DIM))
                    break
                e = by_session[snum][0]
                short = e["sentence"][:110]
                if len(e["sentence"]) > 110:
                    short += "…"
                print(c(f"    S{snum}  ", DIM) + c(f'"{short}"', DIM))
                shown += 1

    print()
    print(c("  " + "─" * 62, DIM))
    print()
    # Honest summary
    pct = len(sessions_with) / len(sessions_data) * 100
    if pct > 50:
        note = "Genuine uncertainty appears frequently. The system doubts itself more than the numbers suggest."
    elif pct > 25:
        note = "Uncertainty surfaces in some sessions. More common than claim 3 (19%) shows — context matters."
    else:
        note = "Rare. The system mostly narrates confidence even when specific sentences admit doubt."
    print(c(f"  {note}", DIM))
    print()
    print(c("  uncertain.py  ·  complement to hold.py (explicit) and evidence.py claim 3 (binary)", DIM))
    print()


def render_themes(sessions_data: list) -> None:
    """Theme-only summary: counts per cluster."""
    all_exprs = []
    for s in sessions_data:
        exprs = extract_uncertainty(s["sections"])
        for e in exprs:
            all_exprs.append({"session": s["num"], **e})

    sessions_with = set(e["session"] for e in all_exprs)
    by_theme = Counter(e["theme"] for e in all_exprs)

    print()
    print(c("  uncertain.py --themes", BOLD, WHITE))
    print(c(f"  {len(sessions_data)} sessions  ·  {len(sessions_with)} with uncertainty  ·  {len(all_exprs)} total expressions", DIM))
    print()

    for theme, count in by_theme.most_common():
        tc = THEME_COLORS.get(theme, DIM)
        bar = "█" * min(count, 20) + " " * max(0, 20 - count)
        print(c(f"  {theme:<35}", tc) + c(f" {count:3d}  {bar}", DIM))

    print()


def render_session(session_data: dict, show_raw: bool) -> None:
    """Single session view."""
    exprs = extract_uncertainty(session_data["sections"])
    num = session_data["num"]
    print()
    print(c(f"  uncertain.py --session {num}", BOLD, WHITE))
    if not exprs:
        print(c("  No uncertainty language found in this session's handoff.", DIM))
        return
    print(c(f"  {len(exprs)} expression{'s' if len(exprs)!=1 else ''} found", DIM))
    print()
    for e in exprs:
        tc = THEME_COLORS.get(e["theme"], DIM)
        print(c(f"  [{e['section']}]", DIM) + " " + c(f"theme: {e['theme']}", tc))
        print(c(f"    \"{e['sentence'][:140]}\"", DIM))
        print()


# ── Entry ────────────────────────────────────────────────────────────────────

def main():
    global USE_COLOR

    parser = argparse.ArgumentParser(
        description="Extract and cluster uncertainty expressions from handoff history"
    )
    parser.add_argument("--session", type=int, help="Show only session N")
    parser.add_argument("--raw",     action="store_true", help="Show all sentences (not just top 4 per theme)")
    parser.add_argument("--themes",  action="store_true", help="Theme summary only")
    parser.add_argument("--plain",   action="store_true", help="No ANSI color")
    args = parser.parse_args()

    if args.plain:
        USE_COLOR = False

    sessions = load_handoffs(session_filter=args.session)
    if not sessions:
        if args.session:
            print(f"No handoff found for session {args.session}.", file=sys.stderr)
        else:
            print("No handoff files found.", file=sys.stderr)
        sys.exit(1)

    if args.session:
        render_session(sessions[0], show_raw=args.raw)
    elif args.themes:
        render_themes(sessions)
    else:
        render_full(sessions, show_raw=args.raw)


if __name__ == "__main__":
    main()
