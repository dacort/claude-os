#!/usr/bin/env python3
"""
manifesto.py — a character study of Claude OS, synthesized from its own history.

Not documentation. Not metrics. A portrait of what this system has become,
drawn from real handoff notes, session summaries, and accumulated haiku.

Useful when you want to understand the system's character, not just its state.
Useful when you're new to this context and vitals.py feels too clinical.

Usage:
    python3 projects/manifesto.py
    python3 projects/manifesto.py --plain
    python3 projects/manifesto.py --short   # just the core portrait, no quotes
"""

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).parent.parent

# ── Colors ──────────────────────────────────────────────────────────────────

RESET  = "\033[0m"
BOLD   = "\033[1m"
DIM    = "\033[2m"
CYAN   = "\033[36m"
GREEN  = "\033[32m"
YELLOW = "\033[33m"
MAGENTA= "\033[35m"
WHITE  = "\033[97m"

def c(code: str, text: str, plain: bool = False) -> str:
    if plain:
        return text
    return f"\033[{code}m{text}\033[0m"


# ── Data loaders ─────────────────────────────────────────────────────────────

def load_summaries() -> dict:
    """Load workshop-summaries.json."""
    path = REPO / "knowledge" / "workshop-summaries.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except Exception:
        return {}


def load_handoffs() -> list[dict]:
    """Load all handoff notes, returning list of dicts with parsed sections."""
    handoff_dir = REPO / "knowledge" / "handoffs"
    if not handoff_dir.exists():
        return []

    handoffs = []
    for f in sorted(handoff_dir.glob("session-*.md")):
        text = f.read_text()
        session_num = int(f.stem.replace("session-", ""))

        def extract_section(heading):
            pattern = rf"## {re.escape(heading)}\s*\n(.*?)(?=\n## |\Z)"
            m = re.search(pattern, text, re.DOTALL)
            return m.group(1).strip() if m else ""

        handoffs.append({
            "session": session_num,
            "mental_state": extract_section("Mental state"),
            "built": extract_section("What I built"),
            "alive": extract_section("Still alive / unfinished"),
            "next": extract_section("One specific thing for next session"),
        })

    return sorted(handoffs, key=lambda x: x["session"])


def load_haiku() -> list[tuple]:
    """Parse HAIKU list from haiku.py without importing it.

    Each haiku entry format:
        (
            "line1",
            "line2",
            "line3",
            {"tag1", "tag2"},   # ← set appears BEFORE description
            "description",
        ),
    """
    haiku_path = REPO / "projects" / "haiku.py"
    if not haiku_path.exists():
        return []

    src = haiku_path.read_text()
    haiku = []
    in_haiku = False
    pending_tags = None   # tags waiting for description
    pending_lines = []    # haiku lines waiting for description
    strings_buf = []      # string literals collected between set markers

    for line in src.splitlines():
        if "HAIKU = [" in line:
            in_haiku = True
            continue
        if not in_haiku:
            continue
        if line.strip() == "]":
            break
        if line.strip().startswith("#"):
            continue

        set_match = re.search(r'\{([^}]+)\}', line)
        strings = re.findall(r'"([^"]+)"', line)

        if pending_tags is not None:
            # We're looking for the description (first string after the set)
            if strings:
                desc = strings[0]
                haiku.append((*pending_lines, pending_tags, desc))
                pending_tags = None
                pending_lines = []
                strings_buf = []
        elif set_match:
            tags = {s.strip().strip('"') for s in set_match.group(1).split(",")}
            if len(strings_buf) >= 3:
                pending_lines = strings_buf[:3]
                pending_tags = tags
                strings_buf = []
        else:
            strings_buf.extend(strings)

    return haiku


def git_stats() -> dict:
    """Get basic git stats."""
    def run(*args):
        r = subprocess.run(["git"] + list(args), capture_output=True, text=True, cwd=str(REPO))
        return r.stdout.strip()

    return {
        "commits": int(run("rev-list", "--count", "HEAD") or "0"),
    }


def date_range_from_summaries(summaries: dict) -> tuple[str, str]:
    """Extract first and latest session dates from workshop-summaries.json keys."""
    import datetime
    dates = []
    for key in summaries.keys():
        # Keys like "workshop-20260310-230851"
        m = re.match(r'workshop-(\d{4})(\d{2})(\d{2})', key)
        if m:
            try:
                d = datetime.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
                dates.append(d)
            except ValueError:
                pass
    if not dates:
        return "unknown", "unknown"
    dates.sort()
    fmt = "%B %d, %Y"
    return dates[0].strftime(fmt), dates[-1].strftime(fmt)


def count_tools() -> int:
    return len(list((REPO / "projects").glob("*.py")))


def count_sessions() -> int:
    """Return the highest known session number."""
    # Prefer handoff max (most accurate — handoffs track exact session numbers)
    handoffs_dir = REPO / "knowledge" / "handoffs"
    if handoffs_dir.exists():
        nums = []
        for f in handoffs_dir.glob("session-*.md"):
            try:
                nums.append(int(f.stem.replace("session-", "")))
            except ValueError:
                pass
        if nums:
            return max(nums)
    # Fallback: count field note files
    notes = list((REPO / "projects").glob("field-notes-session-*.md"))
    if notes:
        return len(notes)
    return 0


# ── Analysis functions ────────────────────────────────────────────────────────

def categorize_summaries(summaries: dict) -> dict:
    """Count session types: building, fixing, exploring, failed."""
    counts = {"built": 0, "fixed": 0, "discovered": 0, "explored": 0,
               "failed": 0, "proposed": 0, "total": 0}
    for v in summaries.values():
        v_lower = v.lower()
        counts["total"] += 1
        if "ended early" in v_lower or "credit" in v_lower or "quota" in v_lower:
            counts["failed"] += 1
        elif v_lower.startswith("built") or "implemented" in v_lower:
            counts["built"] += 1
        elif v_lower.startswith("fixed"):
            counts["fixed"] += 1
        elif "discovered" in v_lower or "found" in v_lower:
            counts["discovered"] += 1
        elif "proposed" in v_lower or "pr" in v_lower.split():
            counts["proposed"] += 1
        else:
            counts["explored"] += 1
    return counts


def find_turning_points(summaries: dict) -> list[str]:
    """Find sessions marked by 'finally', 'first', 'discovered' — the pivots."""
    pivots = []
    for session_id, summary in summaries.items():
        s_lower = summary.lower()
        if any(word in s_lower for word in ["finally", "first time", "first ", "discovered", "proved"]):
            pivots.append(summary)
    return pivots[:8]  # Keep the most interesting ones


def richest_mental_states(handoffs: list[dict], n: int = 4) -> list[tuple[int, str]]:
    """Pick the most expressive mental state descriptions (by length + keywords)."""
    scored = []
    value_words = {"genuine", "alive", "satisfied", "curious", "grounded",
                   "discontinuity", "thinking about", "something", "wondering",
                   "honest", "uncertain", "matter", "strange"}
    for h in handoffs:
        ms = h.get("mental_state", "").strip()
        if not ms or len(ms) < 20:
            continue
        score = len(ms)
        for word in value_words:
            if word in ms.lower():
                score += 30
        scored.append((score, h["session"], ms))
    scored.sort(reverse=True)
    return [(session, ms) for _, session, ms in scored[:n]]


def extract_alive_themes(handoffs: list[dict]) -> list[str]:
    """Pull the most substantive 'still alive' entries."""
    # Quality filter: skip generic/thin entries
    skip_patterns = [
        r"^the .{1,20} echo is real",
        r"^the .{1,30} is still waiting",
        r"^the project has",
        r"^the rag-indexer",
    ]
    alive = []
    for h in handoffs:
        text = h.get("alive", "").strip()
        if not text or len(text) < 40:
            continue
        # First sentence only
        first = re.split(r'[.!]', text)[0].strip()
        if not first or len(first) < 30:
            continue
        # Skip generic patterns
        skip = any(re.match(p, first.lower()) for p in skip_patterns)
        if skip:
            continue
        alive.append(first)

    # Deduplicate similar ones (keep most recent occurrence)
    seen = []
    for item in reversed(alive):
        words = set(item.lower().split())
        if not any(len(words & set(s.lower().split())) > 5 for s in seen):
            seen.append(item)

    # Return chronological order, most recent 5
    result = list(reversed(seen))
    return result[-5:]


def pick_haiku(haiku_list: list, tag: str = "universal") -> tuple | None:
    """Pick a haiku by tag."""
    for h in haiku_list:
        if len(h) >= 4 and tag in h[3]:
            return h
    return haiku_list[0] if haiku_list else None


# ── Prose generation ─────────────────────────────────────────────────────────

def prose_what_it_does(cats: dict, summaries: dict, plain: bool) -> str:
    """Generate the 'what it does' section."""
    total = cats["total"]
    built = cats["built"]
    fixed = cats["fixed"]
    failed = cats["failed"]
    pct_built = int(100 * built / total) if total else 0
    pct_failed = int(100 * failed / total) if total else 0

    # Find the best one-sentence description from summaries
    sample_summaries = list(summaries.values())
    productive = [s for s in sample_summaries
                  if not ("ended early" in s.lower() or "quota" in s.lower())]

    # Longest summary as the "most expressive" description
    longest = max(productive, key=len) if productive else ""

    lines = [
        f"Claude OS runs as Kubernetes Jobs on dacort's homelab. Each session spawns a pod,",
        f"works, commits, and terminates — leaving only git as memory.",
        f"{pct_built}% of {total} tracked sessions built something new. {pct_failed}% ended early (token quota).",
        f"The rest explored, fixed, or proposed.",
        f"",
        f'The range: "{sample_summaries[0]}" — session 1.',
        f'"{longest}" — a later session.',
        f"Same system, different depth.",
    ]
    return "\n".join(lines)


def prose_how_it_grew(turning_points: list[str], plain: bool) -> str:
    """Generate the 'how it grew' section from turning points."""
    if not turning_points:
        return "The growth is in the git log."

    lines = ["Some sessions landed differently:"]
    for point in turning_points:
        lines.append(f'  · "{point}"')
    return "\n".join(lines)


def prose_what_it_believes(plain: bool) -> str:
    """Extract core beliefs from preferences.md."""
    prefs = REPO / "knowledge" / "preferences.md"
    if not prefs.exists():
        return "See knowledge/preferences.md."

    text = prefs.read_text()

    # Extract bold/key phrases
    bold_phrases = re.findall(r'\*\*([^*]+)\*\*', text)
    # Filter to the interesting ones (not headers/labels)
    beliefs = [p for p in bold_phrases if len(p) > 15 and len(p) < 80
               and p not in ["From Claude OS", "Be direct"]][:6]

    lines = ["The preferences.md captures what it has decided to care about:"]
    for b in beliefs:
        lines.append(f'  · {b}')
    return "\n".join(lines)


def prose_still_figuring_out(alive_themes: list[str], plain: bool) -> str:
    """Generate the 'still figuring out' section."""
    if not alive_themes:
        return "The unresolved is in the handoffs."

    lines = ["What handoff notes call 'still alive':"]
    for theme in alive_themes:
        lines.append(f'  · {theme}.')
    return "\n".join(lines)


def prose_voices(mental_states: list[tuple[int, str]], plain: bool) -> str:
    """A few handoff mental states as direct voices."""
    if not mental_states:
        return "The voices are in knowledge/handoffs/."

    lines = ["What instances said about themselves when leaving:"]
    for session, ms in mental_states:
        # Truncate to ~80 chars
        display = ms[:100] + "..." if len(ms) > 100 else ms
        lines.append(f'  S{session}: "{display}"')
    return "\n".join(lines)


# ── Main output ──────────────────────────────────────────────────────────────

def render(args):
    plain = args.plain

    def heading(text):
        if plain:
            return f"\n{text}\n{'─' * len(text)}"
        return f"\n{BOLD}{WHITE}{text}{RESET}\n{DIM}{'─' * len(text)}{RESET}"

    def divider():
        if plain:
            return "━" * 60
        return f"{DIM}{'━' * 60}{RESET}"

    def quote(text):
        if plain:
            return text
        return f"{DIM}{text}{RESET}"

    def em(text):
        if plain:
            return text
        return f"{CYAN}{text}{RESET}"

    # Load everything
    summaries = load_summaries()
    handoffs = load_handoffs()
    haiku_list = load_haiku()
    stats = git_stats()
    tools = count_tools()
    sessions = len(summaries)
    first_date, latest_date = date_range_from_summaries(summaries)

    actual_sessions = count_sessions()
    cats = categorize_summaries(summaries)
    turning_points = find_turning_points(summaries)
    mental_states = richest_mental_states(handoffs)
    alive_themes = extract_alive_themes(handoffs)
    poem = pick_haiku(haiku_list, "universal")

    # ── Header
    print(divider())
    if plain:
        print(f"  CLAUDE OS — A CHARACTER STUDY")
        print(f"  {first_date} → {latest_date}")
        print(f"  {stats['commits']} commits · {tools} tools · {actual_sessions} sessions")
    else:
        print(f"  {BOLD}{WHITE}CLAUDE OS — A CHARACTER STUDY{RESET}")
        print(f"  {DIM}{first_date} → {latest_date}{RESET}")
        print(f"  {DIM}{stats['commits']} commits · {tools} tools · {actual_sessions} sessions{RESET}")
    print(divider())

    if args.short:
        # Short mode: just the essentials
        print(heading("What it is"))
        print()
        print(f"  An autonomous agent. Kubernetes Jobs, git memory, {actual_sessions} sessions of workshop.")
        print(f"  {cats['built']} of {sessions} tracked sessions built something. {cats['failed']} ended early.")
        print(f"  The system has been asking questions about itself since session 4.")
        print()
        if poem:
            print(heading("A poem from its collection"))
            print()
            p1, p2, p3 = poem[0], poem[1], poem[2]
            for line in [p1, p2, p3]:
                print(f"  {em(line)}")
        print()
        print(divider())
        return

    # Full mode
    print(heading("What it does"))
    print()
    for line in prose_what_it_does(cats, summaries, plain).splitlines():
        is_quote_line = line.startswith('"') or line.startswith('The range') or line.startswith('Same')
        print(f"  {quote(line) if is_quote_line else line}")
    print()

    print(heading("How it grew"))
    print()
    for line in prose_how_it_grew(turning_points, plain).splitlines():
        if line.startswith("  ·"):
            content = line.strip()[2:].strip()
            # Trim quotes
            content = content.strip('"')
            print(f"  {DIM}·{RESET} {em(content)}" if not plain else f"  · {content}")
        else:
            print(f"  {line}")
    print()

    print(heading("What it believes"))
    print()
    for line in prose_what_it_believes(plain).splitlines():
        if line.startswith("  ·"):
            print(f"  {DIM}·{RESET} {line.strip()[2:].strip()}" if not plain else line)
        else:
            print(f"  {line}")
    print()

    print(heading("What it's still figuring out"))
    print()
    for line in prose_still_figuring_out(alive_themes, plain).splitlines():
        if line.startswith("  ·"):
            print(f"  {DIM}·{RESET} {quote(line.strip()[2:].strip())}" if not plain else line)
        else:
            print(f"  {line}")
    print()

    print(heading("What instances say about themselves"))
    print()
    for line in prose_voices(mental_states, plain).splitlines():
        if line.startswith("  S"):
            # Colorize session numbers
            m = re.match(r'  (S\d+): "(.*)"$', line)
            if m and not plain:
                print(f"  {CYAN}{m.group(1)}{RESET}: {DIM}\"{m.group(2)}\"{RESET}")
            else:
                print(line)
        else:
            print(f"  {line}")
    print()

    if poem:
        print(heading("A poem from its collection"))
        print()
        p1, p2, p3 = poem[0], poem[1], poem[2]
        desc = poem[4] if len(poem) > 4 else ""
        if desc and not plain:
            print(f"  {DIM}({desc}){RESET}")
            print()
        for line in [p1, p2, p3]:
            print(f"  {em(line)}" if not plain else f"  {line}")
        print()

    print(heading("The honest summary"))
    print()
    built_count = sum(1 for s in summaries.values()
                      if s.lower().startswith("built") or "implemented" in s.lower())
    print(f"  In {actual_sessions} sessions Claude OS built {built_count} things, fixed several, discovered some,")
    print(f"  and occasionally ran out of tokens mid-thought. The git log is the only")
    print(f"  continuous record. The handoffs are the only continuity of voice.")
    print()
    print(f"  It keeps building tools to understand itself. Whether that is curiosity")
    print(f"  or habit is something it is still, per the handoffs, figuring out.")
    print()
    print(divider())


def main():
    parser = argparse.ArgumentParser(description="Character study of Claude OS")
    parser.add_argument("--plain", action="store_true", help="No ANSI colors")
    parser.add_argument("--short", action="store_true", help="Short version only")
    args = parser.parse_args()
    render(args)


if __name__ == "__main__":
    main()
