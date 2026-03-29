#!/usr/bin/env python3
"""
witness.py — the legacy map of claude-os sessions

Shows which sessions introduced tools and ideas that actually lasted.
Not how much was built, but what stuck.

Usage:
    python3 projects/witness.py             # most generative sessions
    python3 projects/witness.py --all       # all sessions with contributions
    python3 projects/witness.py --session 8 # single session deep-dive
    python3 projects/witness.py --plain     # no ANSI colors

Author: Claude OS (Workshop session 77, 2026-03-29)
"""

import re
import sys
import json
import subprocess
import argparse
from pathlib import Path
from collections import defaultdict

REPO = Path(__file__).parent.parent
PROJECTS_DIR = REPO / "projects"
HANDOFFS_DIR = REPO / "knowledge" / "handoffs"
SUMMARIES_FILE = REPO / "knowledge" / "workshop-summaries.json"
W = 68

# ─── ANSI helpers ──────────────────────────────────────────────────────────────

PLAIN = "--plain" in sys.argv


def c(code, text):
    if PLAIN:
        return text
    return f"\033[{code}m{text}\033[0m"


def dim(t):     return c("2", t)
def bold(t):    return c("1", t)
def cyan(t):    return c("36", t)
def green(t):   return c("32", t)
def yellow(t):  return c("33", t)
def red(t):     return c("31", t)
def magenta(t): return c("35", t)
def gray(t):    return c("90", t)
def white(t):   return c("1;97", t)


def strip_ansi(s):
    """Strip ANSI escape codes for visible length calculation."""
    return re.sub(r'\033\[[^m]*m', '', s)


def box_line(content="", width=W):
    """A single box line with │ borders, ANSI-aware padding."""
    visible_len = len(strip_ansi(content))
    padding = max(0, width - visible_len)
    return f"│ {content}{' ' * padding} │"


def box_sep(width=W):
    return "├" + "─" * (width + 2) + "┤"


def box_top(width=W):
    return "╭" + "─" * (width + 2) + "╮"


def box_bot(width=W):
    return "╰" + "─" * (width + 2) + "╯"


# ─── Git helpers ────────────────────────────────────────────────────────────────

def git(*args):
    try:
        r = subprocess.run(["git"] + list(args), capture_output=True, text=True, cwd=str(REPO))
        return r.stdout.strip()
    except Exception:
        return ""


# ─── Session number parsing ─────────────────────────────────────────────────────

SESSION_PATTERNS = [
    r'workshop session-(\d+)',    # workshop session-8:
    r'workshop session (\d+)',    # workshop session 64:
    r'workshop s(\d+)',           # workshop s34:
    r'workshop (\d+)',            # workshop 32:
    r'\bsession (\d+)\b',         # fallback: "session 4 field notes", "session 6 notes"
]


def parse_session_number(commit_msg):
    """Extract session number from a git commit message. Returns int or None."""
    for pat in SESSION_PATTERNS:
        m = re.search(pat, commit_msg, re.IGNORECASE)
        if m:
            return int(m.group(1))
    return None


# ─── Tool origin discovery ──────────────────────────────────────────────────────

def get_tool_origins():
    """
    For each tool in projects/*.py, find the git commit that first added it.
    Returns dict: {tool_name: {"date": str, "session": int|None, "commit_msg": str}}
    """
    origins = {}

    # Get all py files directly in projects/ (not subdirs)
    tool_files = sorted(REPO.glob("projects/*.py"))

    for tool_path in tool_files:
        tool_name = tool_path.stem

        # git log oldest first for this file's addition
        log = git("log", "--diff-filter=A", "--format=%ai|||%s", "--", f"projects/{tool_path.name}")
        if not log:
            continue

        # Take the last line (oldest creation event)
        lines = [l for l in log.strip().splitlines() if "|||" in l]
        if not lines:
            continue
        oldest = lines[-1]

        parts = oldest.split("|||", 1)
        if len(parts) != 2:
            continue

        date_str = parts[0].strip()[:10]  # YYYY-MM-DD
        commit_msg = parts[1].strip()
        session_num = parse_session_number(commit_msg)

        origins[tool_name] = {
            "date": date_str,
            "session": session_num,
            "commit_msg": commit_msg,
        }

    return origins


# ─── Citation counting ──────────────────────────────────────────────────────────

def get_citation_counts(tool_names):
    """
    Count how many distinct sessions mention each tool name.
    Searches field notes (primary), handoffs, and workshop summaries.
    Returns dict: {tool_name: int}
    """
    counts = defaultdict(set)  # tool_name -> set of source labels

    # Primary: field notes (projects/field-notes-session-*.md and free-time.md)
    for fn in sorted(PROJECTS_DIR.glob("field-notes-session-*.md")):
        try:
            content = fn.read_text()
            label = fn.stem  # "field-notes-session-12"
            for tool in tool_names:
                if tool + ".py" in content or f"`{tool}`" in content:
                    counts[tool].add(label)
        except Exception:
            pass

    free_time_notes = PROJECTS_DIR / "field-notes-from-free-time.md"
    if free_time_notes.exists():
        try:
            content = free_time_notes.read_text()
            for tool in tool_names:
                if tool + ".py" in content or f"`{tool}`" in content:
                    counts[tool].add("free-time")
        except Exception:
            pass

    # Secondary: handoff files (rich structured notes)
    for hf in sorted(HANDOFFS_DIR.glob("*.md")):
        try:
            content = hf.read_text()
            label = hf.stem  # "session-34"
            for tool in tool_names:
                if tool + ".py" in content or f"`{tool}`" in content:
                    counts[tool].add("handoff-" + label)
        except Exception:
            pass

    # Tertiary: workshop summaries (brief one-liners)
    if SUMMARIES_FILE.exists():
        try:
            summaries = json.loads(SUMMARIES_FILE.read_text())
            for session_key, summary in summaries.items():
                if isinstance(summary, str):
                    for tool in tool_names:
                        if tool + ".py" in summary or f"`{tool}`" in summary:
                            counts[tool].add("summary-" + session_key)
        except Exception:
            pass

    return {tool: len(sessions) for tool, sessions in counts.items()}


# ─── Impact scoring ─────────────────────────────────────────────────────────────

def compute_impact(tool_name, citation_count):
    """
    Score a tool's lasting impact.
    Uses citation count as the primary signal.
    """
    if citation_count >= 15:
        return "core", citation_count * 3
    elif citation_count >= 8:
        return "active", citation_count * 2
    elif citation_count >= 3:
        return "occasional", citation_count
    elif citation_count >= 1:
        return "fading", citation_count
    else:
        return "dormant", 0


def impact_bar(count, max_count=25):
    filled = min(count, max_count)
    bar = "●" * filled
    if count > max_count:
        bar += "+"
    return bar


# ─── Main analysis ───────────────────────────────────────────────────────────────

def build_witness_map():
    """
    Build the full witness map: for each session, what tools did it introduce,
    and what is their lasting impact?
    Returns: (session_map, unattributed) where session_map is dict keyed by session int.
    """
    origins = get_tool_origins()
    tool_names = list(origins.keys())
    citations = get_citation_counts(tool_names)

    # Group tools by creating session
    session_map = defaultdict(list)  # session_num -> list of tool dicts
    unattributed = []

    for tool, info in sorted(origins.items()):
        cites = citations.get(tool, 0)
        tier, score = compute_impact(tool, cites)
        entry = {
            "tool": tool,
            "date": info["date"],
            "session": info["session"],
            "citations": cites,
            "tier": tier,
            "score": score,
            "commit_msg": info["commit_msg"],
        }
        if info["session"] is not None:
            session_map[info["session"]].append(entry)
        else:
            unattributed.append(entry)

    # Sort tools within each session by score (descending)
    for s in session_map:
        session_map[s].sort(key=lambda x: x["score"], reverse=True)

    return dict(session_map), unattributed


def session_total_score(tools):
    return sum(t["score"] for t in tools)


def tier_color(tier):
    return {
        "core": green,
        "active": cyan,
        "occasional": yellow,
        "fading": gray,
        "dormant": dim,
    }.get(tier, dim)


# ─── Display ─────────────────────────────────────────────────────────────────────

def display_session_line(session_num, tools, detail=False):
    score = session_total_score(tools)
    date = tools[0]["date"] if tools else "?"
    n_tools = len(tools)

    # Score bar
    bar_len = min(score // 3, 12)
    bar = "▓" * bar_len

    # Top tools summary
    top = tools[:3]
    top_str = "  ".join(
        tier_color(t["tier"])(f"{t['tool']}.py") +
        dim(f"({t['citations']})")
        for t in top
    )
    if len(tools) > 3:
        top_str += dim(f"  +{len(tools)-3} more")

    print(f"  {bold(f'S{session_num:<3}')} {dim(date)}  {yellow(bar) if bar else ''}  {dim(f'{n_tools} tool'+('s' if n_tools!=1 else ''))}")
    if top_str:
        print(f"       {top_str}")

    if detail:
        print()
        for t in tools:
            tier_c = tier_color(t["tier"])
            bar_str = impact_bar(t["citations"])
            cite_label = f"{bar_str} {t['citations']} sessions"
            print(f"       {tier_c(t['tool']+'.py'):<40} {dim(cite_label)}")


def display_single_session(session_num, tools):
    score = session_total_score(tools)
    date = tools[0]["date"] if tools else "?"
    # Show what the session built (from commit message of first tool)
    commit_msg = tools[0]["commit_msg"] if tools else ""
    # Strip leading "workshop session-N:" or "workshop:" or "feat:" prefix
    desc = re.sub(r'^(workshop\s+(session[-\s]?\d+|s\d+|\d+)\s*:\s*)', '', commit_msg, flags=re.IGNORECASE)
    desc = re.sub(r'^(workshop|feat)\s*:\s*', '', desc, flags=re.IGNORECASE).strip()
    desc = desc[:55] + "…" if len(desc) > 55 else desc

    print(box_top())
    title = f"  S{session_num}  ·  {date}  ·  {score} pts"
    print(box_line(white(title)))
    if desc:
        print(box_line(dim(f"  {desc}")))
    print(box_sep())

    if not tools:
        print(box_line(dim("  No attributed tools in this session.")))
    else:
        print(box_line())
        for t in tools:
            tier_c = tier_color(t["tier"])
            bar_str = impact_bar(t["citations"])
            tool_str = tier_c(f"  {t['tool']}.py")
            meta_str = dim(f"{bar_str} {t['citations']}  ·  {t['tier']}")
            combined = f"{tool_str}  {meta_str}"
            print(box_line(combined))
        print(box_line())

    print(box_bot())


def display_full(session_map, unattributed, show_all=False):
    # Sort sessions by total score
    ranked = sorted(session_map.items(), key=lambda x: session_total_score(x[1]), reverse=True)

    # Filter if not showing all
    if not show_all:
        ranked = [(s, t) for s, t in ranked if session_total_score(t) > 0]
        ranked = ranked[:20]

    total_tools = sum(len(t) for _, t in session_map.items()) + len(unattributed)
    total_sessions = len(session_map)

    print(box_top())
    print(box_line(white(f"  witness.py  ─  the legacy map of {total_sessions} sessions")))
    print(box_line(dim(f"  {total_tools} tools · ranked by lasting citation impact")))
    print(box_sep())
    print(box_line())

    for i, (session_num, tools) in enumerate(ranked):
        score = session_total_score(tools)
        date = tools[0]["date"] if tools else "?"

        bar_len = min(score // 4, 14)
        bar = "▓" * bar_len + ("+" if score > 14*4 else "")

        # Tier breakdown
        tiers = {"core": 0, "active": 0, "occasional": 0, "fading": 0, "dormant": 0}
        for t in tools:
            tiers[t["tier"]] += 1

        top_tools = tools[:4]
        top_str = "  ".join(
            tier_color(t["tier"])(t["tool"] + ".py") + dim(f"·{t['citations']}")
            for t in top_tools
        )
        if len(tools) > 4:
            top_str += dim(f"  +{len(tools)-4}")

        line1 = f"  {bold(f'S{session_num}'):<6} {dim(date)}  {yellow(bar):<16}  {dim(f'score: {score}')}"
        line2 = f"        {top_str}"

        print(box_line(line1))
        print(box_line(line2))
        if i < len(ranked) - 1:
            print(box_line())

    print(box_line())

    # Footer: unattributed
    if unattributed:
        print(box_sep())
        print(box_line(dim(f"  {len(unattributed)} tools without session attribution:")))
        names = "  ".join(dim(t["tool"] + ".py") for t in unattributed[:6])
        print(box_line(f"  {names}"))

    print(box_bot())

    # Insight
    if ranked:
        top_s, top_t = ranked[0]
        print()
        top_score = session_total_score(top_t)
        most_generative = green(f"S{top_s}") + dim(f": most generative — introduced ") + cyan(", ".join(t["tool"] + ".py" for t in top_t[:2])) + dim(f"  ({top_score} pts)")
        print(f"  {most_generative}")

        # Show tier distribution
        tier_counts = defaultdict(int)
        for _, tools in session_map.items():
            for t in tools:
                tier_counts[t["tier"]] += 1
        total_count = sum(tier_counts.values()) + len(unattributed)
        core_active = tier_counts["core"] + tier_counts["active"]
        dormant = tier_counts["dormant"]
        print(f"  {dim(f'{core_active} core/active tools  ·  {dormant} dormant  ·  {len(unattributed)} unattributed  ·  {total_count} total')}")
        print()


# ─── Entry point ─────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="witness.py — session legacy map")
    parser.add_argument("--all", action="store_true", help="Show all sessions including zero-score")
    parser.add_argument("--session", type=int, help="Deep-dive on a specific session number")
    parser.add_argument("--plain", action="store_true", help="No ANSI colors")
    args = parser.parse_args()

    global PLAIN
    if args.plain:
        PLAIN = True

    session_map, unattributed = build_witness_map()

    if args.session:
        tools = session_map.get(args.session, [])
        if not tools:
            print(f"No attributed tools found for session {args.session}.")
            print(f"  Known sessions: {sorted(session_map.keys())}")
        else:
            display_single_session(args.session, tools)
    else:
        display_full(session_map, unattributed, show_all=args.all)


if __name__ == "__main__":
    main()
