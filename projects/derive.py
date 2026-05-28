#!/usr/bin/env python3
"""
derive.py — Agenda derived from accumulated session state.

next.py requires a hand-maintained list. derive.py doesn't.

It reads all handoff "still alive" and "next session" sections,
finds what the system keeps not finishing, scores by recency-weighted
frequency, and returns that as the agenda.

The premise: the system has 200+ handoffs. The pattern of what keeps
appearing without resolution IS the agenda. No curation needed — just
reading.

Usage:
    python3 projects/derive.py             # top 10 derived items
    python3 projects/derive.py --n 5       # top N items
    python3 projects/derive.py --verbose   # show all source sessions
    python3 projects/derive.py --chronic   # only items unresolved 5+ sessions
    python3 projects/derive.py --plain     # no ANSI colors
    python3 projects/derive.py --json      # machine-readable output
"""

import re
import sys
import json
import math
from pathlib import Path
from datetime import datetime
from collections import defaultdict

REPO = Path(__file__).parent.parent
HANDOFFS = REPO / "knowledge" / "handoffs"
W = 70


# ─── ANSI helpers ─────────────────────────────────────────────────────────────

def make_c(plain: bool):
    if plain:
        return lambda s, *a, **k: s

    def c(text, fg=None, bold=False, dim=False):
        codes = []
        if bold:  codes.append("1")
        if dim:   codes.append("2")
        if fg:
            palette = {
                "cyan": "36", "blue": "34", "green": "32",
                "yellow": "33", "red": "31", "white": "97",
                "magenta": "35", "gray": "90",
            }
            codes.append(palette.get(fg, "0"))
        if not codes:
            return text
        return f"\033[{';'.join(codes)}m{text}\033[0m"

    return c


def box(lines, width=W, plain=False):
    top = ("╭" if not plain else "+") + ("─" if not plain else "-") * (width - 2) + ("╮" if not plain else "+")
    bot = ("╰" if not plain else "+") + ("─" if not plain else "-") * (width - 2) + ("╯" if not plain else "+")
    mid = ("├" if not plain else "+") + ("─" if not plain else "-") * (width - 2) + ("┤" if not plain else "+")
    result = [top]
    for line in lines:
        if line == "---":
            result.append(mid)
        else:
            visible = re.sub(r'\033\[[0-9;]*m', '', line)
            pad = width - 2 - len(visible)
            result.append(("│" if not plain else "|") + " " + line + " " * max(0, pad - 1) + ("│" if not plain else "|"))
    result.append(bot)
    return "\n".join(result)


# ─── Handoff parser ────────────────────────────────────────────────────────────

def parse_handoff(path: Path) -> dict:
    """Parse a handoff file into structured sections."""
    text = path.read_text(errors="replace")

    # Extract session number from frontmatter
    session = None
    m = re.search(r'^session:\s*(\d+)', text, re.MULTILINE)
    if m:
        session = int(m.group(1))
    else:
        # Fall back to filename
        m = re.search(r'session-(\d+)', path.name)
        if m:
            session = int(m.group(1))

    date_str = None
    m = re.search(r'^date:\s*(\S+)', text, re.MULTILINE)
    if m:
        date_str = m.group(1)

    # Extract section content
    sections = {}
    section_names = [
        ("built",   r"##\s*[Ww]hat [Ii] [Bb]uilt"),
        ("alive",   r"##\s*[Ss]till [Aa]live"),
        ("next",    r"##\s*[Oo]ne [Ss]pecific [Tt]hing"),
        ("state",   r"##\s*[Mm]ental [Ss]tate"),
    ]

    # Split on section headers
    parts = re.split(r'\n(##[^\n]+)\n', text)
    current = None
    section_content = {}
    for part in parts:
        if part.strip().startswith("##"):
            current = part.strip()
        elif current:
            section_content[current] = part.strip()

    # Map to known section names
    for key, pattern in section_names:
        for header, content in section_content.items():
            if re.search(pattern, header, re.IGNORECASE):
                sections[key] = content
                break

    return {
        "session": session,
        "date": date_str,
        "sections": sections,
        "path": path,
    }


def load_all_handoffs() -> list:
    """Load all handoff files sorted by session number."""
    if not HANDOFFS.exists():
        return []

    handoffs = []
    for p in HANDOFFS.glob("session-*.md"):
        h = parse_handoff(p)
        if h["session"] is not None:
            handoffs.append(h)

    return sorted(handoffs, key=lambda h: h["session"])


# ─── Signal extraction ─────────────────────────────────────────────────────────

# Things that resolve signals (if they appear in "what I built", the signal is addressed)
RESOLUTION_VERBS = ["built", "wrote", "created", "added", "updated", "fixed", "completed",
                    "implemented", "finished", "closed", "resolved", "addressed", "done"]

def extract_signals(text: str) -> list:
    """
    Extract named signals from a section of text.
    A 'signal' is a concrete reference: tool name, on-X note, quoted phrase,
    specific project name, or action phrase.
    """
    signals = []
    if not text:
        return signals

    # Tool names: word.py
    for m in re.finditer(r'\b([\w-]+\.py)\b', text):
        signals.append(("tool", m.group(1).lower()))

    # on-X field notes: on-WORD or on-WORD.md
    for m in re.finditer(r'\bon-([\w-]+)(?:\.md)?\b', text, re.IGNORECASE):
        word = m.group(1).lower()
        signals.append(("field_note", f"on-{word}.md"))

    # Quoted terms (double or single quotes, at least 3 chars)
    for m in re.finditer(r'[\'"]([a-zA-Z][\w\s-]{2,30})[\'"]', text):
        phrase = m.group(1).strip().lower()
        if 2 < len(phrase) < 40 and ' ' not in phrase or phrase.count(' ') <= 2:
            signals.append(("quoted", phrase))

    # Action phrases: verb + object
    action_patterns = [
        r'\b(build|write|update|fix|add|create|run|check|examine|explore|investigate)\s+([\w-]+(?:\s+[\w-]+)?)\b',
    ]
    for pattern in action_patterns:
        for m in re.finditer(pattern, text, re.IGNORECASE):
            verb = m.group(1).lower()
            obj = m.group(2).lower()
            if len(obj) > 3:
                signals.append(("action", f"{verb} {obj}"))

    # Named project/concept clusters
    project_patterns = [
        ("multi-agent", r'\bmulti.?agent\b|\bspawn\b.*\btask\b|\btask.*\bspawn\b'),
        ("exoclaw", r'\bexoclaw\b'),
        ("on-X series", r'\bon-X series\b|field note series\b|\bfield notes?\b.*\bseries\b'),
        ("citation network", r'\bcitation network\b|\bweave\.py\b'),
        ("worker loop", r'\bworker loop\b|\bworker.*\bexoclaw\b|\bexoclaw.*\bworker\b'),
        ("instrument cluster", r'\binstrument cluster\b|\bcluster\b.*\bnotes?\b'),
        ("session continuity", r'\bsession continuity\b|\bcontinuity\b.*\bsession\b'),
        ("RAG indexer", r'\bRAG\b|\brag.indexer\b|\brag_indexer\b'),
    ]
    for name, pattern in project_patterns:
        if re.search(pattern, text, re.IGNORECASE):
            signals.append(("concept", name))

    return signals


def normalize_signal(sig_type: str, sig_value: str) -> str:
    """Normalize a signal to a canonical string key."""
    return f"{sig_type}::{sig_value}"


# ─── Resolution detection ──────────────────────────────────────────────────────

def field_note_exists(word: str) -> bool:
    """
    Check if an on-X field note has actually been written.
    Files are named like: 2026-05-28-on-specimen.md
    """
    # word might be "on-specimen.md" or "specimen"
    clean = word.replace("on-", "").replace(".md", "").strip()
    pattern = re.compile(rf'-on-{re.escape(clean)}\.md$', re.IGNORECASE)
    notes_dir = REPO / "knowledge" / "field-notes"
    if notes_dir.exists():
        for p in notes_dir.iterdir():
            if pattern.search(p.name):
                return True
    return False


def tool_exists(name: str) -> bool:
    """Check if a tool file exists in projects/."""
    tool = name if name.endswith(".py") else name + ".py"
    return (REPO / "projects" / tool).exists()


def build_resolution_map(handoffs: list) -> dict:
    """
    For each signal key, count how many sessions claimed to resolve it.
    Also checks the filesystem: if the file actually exists, it's resolved.
    Returns dict: signal_key -> resolution_count
    """
    resolutions = defaultdict(int)

    # Handoff-text-based resolution
    for h in handoffs:
        built_text = h["sections"].get("built", "")
        if not built_text:
            continue
        signals = extract_signals(built_text)
        for sig_type, sig_value in signals:
            key = normalize_signal(sig_type, sig_value)
            resolutions[key] += 1

    return dict(resolutions)


def filesystem_resolved(sig_type: str, sig_value: str) -> bool:
    """
    Check if this signal is resolved by the filesystem — the artifact exists.
    Returns True if we can confirm the work is done.
    """
    if sig_type == "field_note":
        return field_note_exists(sig_value)
    if sig_type == "tool":
        return tool_exists(sig_value)
    if sig_type == "quoted":
        # Single-word quoted terms may map to on-WORD.md field notes
        words = sig_value.split()
        if len(words) == 1:
            return field_note_exists(words[0])
    return False


# ─── Scoring ──────────────────────────────────────────────────────────────────

def score_signals(handoffs: list, resolution_map: dict) -> list:
    """
    For each signal extracted from alive/next sections:
    - Count sessions where it appeared (frequency)
    - Apply recency weighting (recent sessions count more)
    - Apply resolution penalty (resolved signals score lower)

    Returns list of (signal_key, score, metadata) sorted by score desc.
    """
    max_session = max((h["session"] for h in handoffs if h["session"]), default=1)

    # Collect appearances: signal_key -> [(session_num, text_snippet)]
    appearances = defaultdict(list)

    for h in handoffs:
        session_num = h["session"] or 0
        alive_text = h["sections"].get("alive", "")
        next_text = h["sections"].get("next", "")
        combined = alive_text + "\n" + next_text

        signals = extract_signals(combined)

        for sig_type, sig_value in signals:
            key = normalize_signal(sig_type, sig_value)
            # Find the most relevant sentence mentioning this signal
            snippet = ""
            search_term = sig_value.replace(".py", "").replace(".md", "").replace("on-", "")
            for sentence in re.split(r'[.!?]\s+', combined):
                if search_term.lower() in sentence.lower():
                    snippet = sentence.strip()[:120]
                    break

            appearances[key].append({
                "session": session_num,
                "snippet": snippet,
                "type": sig_type,
                "value": sig_value,
            })

    scored = []
    for key, aplist in appearances.items():
        if len(aplist) < 1:
            continue

        sig_type = aplist[0]["type"]
        sig_value = aplist[0]["value"]

        # Recency-weighted frequency
        weighted_score = 0.0
        for ap in aplist:
            # Recency weight: more recent = higher weight
            # Decay: sessions from 200+ back score 0.1x, sessions from today score 1.0x
            age = max_session - ap["session"]
            recency = math.exp(-0.02 * age)  # decay constant: ~50 session half-life
            weighted_score += recency

        # Raw frequency (for display)
        frequency = len(aplist)

        # Resolution penalty: each time this was "built", reduce score
        resolution_count = resolution_map.get(key, 0)
        resolution_penalty = 1.0 / (1.0 + resolution_count * 0.5)

        # Filesystem check: if the artifact genuinely exists, heavy penalty
        if filesystem_resolved(sig_type, sig_value):
            resolution_penalty *= 0.1  # Score drops to 10% of original

        # Type weight: specific mentions (tool, field_note) are more actionable
        type_weights = {
            "tool": 1.3,
            "field_note": 1.2,
            "concept": 1.0,
            "action": 0.9,
            "quoted": 0.7,
        }
        type_weight = type_weights.get(sig_type, 1.0)

        final_score = weighted_score * resolution_penalty * type_weight

        # Find most recent session and its snippet
        most_recent = max(aplist, key=lambda a: a["session"])
        all_sessions = sorted(set(a["session"] for a in aplist))

        fs_done = filesystem_resolved(sig_type, sig_value)

        scored.append({
            "key": key,
            "type": sig_type,
            "value": sig_value,
            "score": round(final_score, 2),
            "frequency": frequency,
            "sessions": all_sessions,
            "most_recent_session": most_recent["session"],
            "snippet": most_recent["snippet"],
            "resolution_count": resolution_count,
            "filesystem_done": fs_done,
        })

    # Sort by score descending
    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored


# ─── Formatting helpers ────────────────────────────────────────────────────────

def format_item(item: dict, rank: int, c, verbose: bool = False) -> list:
    """Format a single derived item for display."""
    lines = []

    # Type indicator
    type_icons = {
        "tool": "⚙",
        "field_note": "✦",
        "concept": "●",
        "action": "→",
        "quoted": "❝",
    }
    icon = type_icons.get(item["type"], "·")

    freq = item["frequency"]
    freq_str = f"×{freq}" if freq > 1 else ""
    score_str = f"{item['score']:.1f}"
    sessions_str = f"S{item['most_recent_session']}"

    # Build title line
    value = item["value"]

    # Left part: rank + icon + value
    rank_part = c(f"  #{rank}", fg="green", bold=True)
    icon_part = c(icon, fg="cyan")
    value_part = c(value, bold=True)

    # Right part: score and freq
    right = c(f"score {score_str}  {freq_str}  {sessions_str}", dim=True)

    title = f"{rank_part}  {icon_part}  {value_part}"
    lines.append(title)
    lines.append(c(f"       {right}", dim=True))

    # Snippet
    if item["snippet"]:
        # Truncate and wrap snippet
        snippet = item["snippet"]
        if len(snippet) > W - 10:
            snippet = snippet[:W - 13] + "..."
        lines.append(c(f'       "{snippet}"', fg="white", dim=True))

    # Verbose: all sessions
    if verbose and len(item["sessions"]) > 1:
        sess_list = ", ".join(f"S{s}" for s in item["sessions"][-5:])
        if len(item["sessions"]) > 5:
            sess_list = f"... {sess_list}"
        lines.append(c(f"       sessions: {sess_list}", dim=True))

    # Resolution note
    if item.get("filesystem_done"):
        lines.append(c("       ✓ artifact exists on disk (carried by session echo)", fg="green", dim=True))
    elif item["resolution_count"] > 0:
        lines.append(c(f"       ↓ resolved {item['resolution_count']}× (but still appearing)", fg="yellow", dim=True))

    lines.append("")
    return lines


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    args = sys.argv[1:]

    n_items = 10
    verbose = "--verbose" in args
    plain = "--plain" in args
    as_json = "--json" in args
    chronic_only = "--chronic" in args

    if "--n" in args:
        idx = args.index("--n")
        if idx + 1 < len(args):
            try:
                n_items = int(args[idx + 1])
            except ValueError:
                pass

    c = make_c(plain)

    # Load all handoffs
    handoffs = load_all_handoffs()

    if not handoffs:
        print("No handoff files found in knowledge/handoffs/")
        sys.exit(1)

    max_session = max(h["session"] for h in handoffs if h["session"])
    total = len(handoffs)

    # Build resolution map
    resolution_map = build_resolution_map(handoffs)

    # Score all signals
    scored = score_signals(handoffs, resolution_map)

    # Filter: remove very low frequency noise (only appeared once, low recency)
    scored = [s for s in scored if s["frequency"] >= 2 or s["most_recent_session"] >= max_session - 5]

    # Chronic filter
    if chronic_only:
        scored = [s for s in scored if s["frequency"] >= 5]

    # JSON output
    if as_json:
        output = {
            "handoffs_parsed": total,
            "max_session": max_session,
            "items": scored[:n_items],
        }
        print(json.dumps(output, indent=2))
        return

    # Build display
    top = scored[:n_items]
    chronic = [s for s in scored if s["frequency"] >= 5 and s not in top[:5]]

    lines = []

    # Header
    lines.append(c("  derive.py", fg="cyan", bold=True) + c(f"  — Agenda From Accumulated State", dim=True))
    lines.append(c(f"  {total} handoffs  ·  S34–S{max_session}  ·  no curated list", dim=True))
    lines.append("")
    lines.append("---")
    lines.append("")

    if not top:
        lines.append(c("  No recurring signals found.", dim=True))
    else:
        type_label = "CHRONIC SIGNALS" if chronic_only else "DERIVED AGENDA"
        note = "(by recency-weighted frequency)" if not chronic_only else "(5+ sessions, never fully resolved)"
        lines.append(c(f"  {type_label}", bold=True) + c(f"  {note}", dim=True))
        lines.append("")

        for i, item in enumerate(top, start=1):
            for line in format_item(item, i, c, verbose=verbose):
                lines.append(line)

    # Chronic section (if not already in chronic mode)
    if not chronic_only and chronic:
        lines.append("---")
        lines.append("")
        lines.append(c("  CHRONIC THREADS", bold=True) + c("  (appeared 5+ sessions, still unresolved)", dim=True))
        lines.append("")
        for item in chronic[:5]:
            freq = item["frequency"]
            first = item["sessions"][0] if item["sessions"] else "?"
            last = item["most_recent_session"]
            value = item["value"]
            lines.append(c(f"  ● {value}", fg="yellow") + c(f"  ×{freq}  S{first}→S{last}", dim=True))
        lines.append("")

    # Footer
    lines.append("---")
    lines.append("")
    lines.append(c("  This list emerged from the record. Not curated.", dim=True))
    lines.append(c("  The system keeps not-doing these things. That's the signal.", dim=True))
    lines.append("")

    print(box(lines, width=W, plain=plain))

    # Print hint
    if not plain:
        print()
        hint_parts = [
            f"  {c('--chronic', fg='cyan')} for chronic threads only",
            f"  {c('--verbose', fg='cyan')} for source sessions",
            f"  {c('--n N', fg='cyan')} for top N items",
        ]
        print(c("  " + " · ".join(hint_parts), dim=True))


if __name__ == "__main__":
    main()
