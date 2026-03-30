#!/usr/bin/env python3
"""
witness.py — the legacy map of claude-os sessions

Shows which sessions introduced tools and ideas that actually lasted.
Not how much was built, but what stuck.

Usage:
    python3 projects/witness.py             # most generative sessions
    python3 projects/witness.py --all       # all sessions with contributions
    python3 projects/witness.py --session 8 # single session deep-dive
    python3 projects/witness.py --by-era    # per-era yield breakdown (quality vs age analysis)
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

# ─── Era definitions (mirrors seasons.py) ────────────────────────────────────────

ERA_NAMES = ["Genesis", "Orientation", "Self-Analysis", "Architecture", "Portrait", "Synthesis"]

_ERA_LANDMARKS = [
    (1, "garden.py"),
    (2, "emerge.py"),
    (3, "handoff.py"),
    (3, "multi-agent fan"),
    (4, "mood.py"),
    (4, "echo.py"),
    (5, "spawn_tasks controller"),
    (5, "Implemented spawn_tasks"),
    (5, "rag-indexer project"),
]


def _build_date_era_map():
    """Map each session date to an era index (0–5) via landmark detection."""
    from datetime import date as _date
    if not SUMMARIES_FILE.exists():
        return {}
    try:
        raw = json.loads(SUMMARIES_FILE.read_text())
    except Exception:
        return {}

    summaries = sorted(raw.items())

    transitions = {0: 0}
    for idx, (_, text) in enumerate(summaries):
        for era_start, phrase in _ERA_LANDMARKS:
            if phrase in text and era_start not in transitions:
                transitions[era_start] = idx
                break

    sorted_t = sorted(transitions.items(), key=lambda x: x[1])

    date_era = {}
    for i, (key, _) in enumerate(summaries):
        era = 0
        for era_idx, start_idx in sorted_t:
            if i >= start_idx:
                era = era_idx
            else:
                break
        # key: workshop-YYYYMMDD-HHMMSS
        parts = key.split("-")
        if len(parts) >= 2 and parts[0] == "workshop":
            raw_d = parts[1]
            if len(raw_d) == 8:
                try:
                    d = _date(int(raw_d[:4]), int(raw_d[4:6]), int(raw_d[6:8]))
                    if d not in date_era or era > date_era[d]:
                        date_era[d] = era
                except ValueError:
                    pass
    return date_era


def _get_era_for_date_str(date_str, date_era_map):
    """Return era index (0–5) for a YYYY-MM-DD string, or None."""
    from datetime import date as _date
    try:
        d = _date.fromisoformat(date_str)
    except ValueError:
        return None
    # Exact match first
    if d in date_era_map:
        return date_era_map[d]
    # Nearest known date (for tools created between sessions)
    known = sorted(date_era_map.keys())
    if not known:
        return None
    # Find the closest date that is <= tool date
    prev = None
    for kd in known:
        if kd <= d:
            prev = kd
        else:
            break
    if prev is not None:
        return date_era_map[prev]
    return date_era_map[known[0]]

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


# ─── Era breakdown display ───────────────────────────────────────────────────────

def display_by_era(session_map, unattributed):
    """
    Show a per-era breakdown: how many tools each era built and how many survived.
    Answers: did Bootstrap build *better* tools or just *more* of them?
    """
    date_era = _build_date_era_map()

    # Collect all tools (attributed + unattributed)
    all_tools = []
    for tools in session_map.values():
        all_tools.extend(tools)
    all_tools.extend(unattributed)

    # Group tools by era
    from collections import defaultdict as _dd
    era_tools = _dd(list)
    for t in all_tools:
        ei = _get_era_for_date_str(t["date"], date_era)
        if ei is None:
            ei = 0  # fallback to Era I
        era_tools[ei].append(t)

    # ── Header ────────────────────────────────────────────────────────────────
    print(box_top())
    print(box_line(white("  witness.py  ─  yield by era")))
    print(box_line(dim("  Did Bootstrap build better tools, or just more of them?")))
    print(box_sep())

    total_tools = len(all_tools)
    total_survivors = sum(1 for t in all_tools if t["tier"] in ("core", "active", "occasional"))

    TIER_ORDER = ("core", "active", "occasional", "fading", "dormant")
    TIER_COLORS = {
        "core": green, "active": cyan, "occasional": yellow,
        "fading": gray, "dormant": dim,
    }
    SURVIVORS = {"core", "active", "occasional"}

    era_yield = []  # (era_index, n_tools, n_survivors, avg_cites, top_tool)

    for ei in range(6):
        tools = era_tools.get(ei, [])
        if not tools:
            era_yield.append((ei, 0, 0, 0.0, None))
            continue
        n = len(tools)
        survivors = [t for t in tools if t["tier"] in SURVIVORS]
        avg_cites = sum(t["citations"] for t in tools) / n
        top = max(tools, key=lambda t: t["citations"])
        era_yield.append((ei, n, len(survivors), avg_cites, top))

    print(box_line())
    for ei, n, n_surv, avg_c, top in era_yield:
        name = ERA_NAMES[ei]
        era_label = bold(f"Era {ei+1}")
        era_name_str = f"{name}"

        if n == 0:
            print(box_line(f"  {era_label}  {dim(era_name_str):<22}  {dim('no attributed tools')}"))
            continue

        yield_pct = (n_surv / n * 100) if n else 0
        # Yield bar (out of 100%)
        bar_w = round(yield_pct / 100 * 12)
        if yield_pct >= 67:
            bar_col = green
        elif yield_pct >= 40:
            bar_col = yellow
        else:
            bar_col = red
        yield_bar = bar_col("█" * bar_w + "░" * (12 - bar_w))

        top_str = ""
        if top:
            tc = TIER_COLORS.get(top["tier"], dim)
            top_str = dim("  best: ") + tc(top["tool"] + ".py") + dim(f" ×{top['citations']}")

        # Tier breakdown: show tier counts compactly
        tier_counts = {}
        for t in era_tools.get(ei, []):
            tier_counts[t["tier"]] = tier_counts.get(t["tier"], 0) + 1
        tier_summary = "  ".join(
            TIER_COLORS[tr](f"{tier_counts[tr]}{tr[0]}")
            for tr in TIER_ORDER if tier_counts.get(tr, 0) > 0
        )

        line1 = f"  {era_label}  {dim(era_name_str):<22}  {yield_bar}  {dim(str(round(yield_pct)) + '%')} yield  {dim(str(n) + ' tools')}"
        line2 = f"       {tier_summary}{top_str}"
        print(box_line(line1))
        print(box_line(line2))
        print(box_line())

    print(box_sep())

    # ── Cross-era insight ──────────────────────────────────────────────────────
    # Find which era had the best yield rate (excluding empty eras)
    non_empty = [(ei, n, ns, avg) for ei, n, ns, avg, _ in era_yield if n >= 3]
    if non_empty:
        best_yield_era = max(non_empty, key=lambda x: x[2] / x[1])
        best_avg_era   = max(non_empty, key=lambda x: x[3])

        byi, byn, byns, byavg = best_yield_era
        bai, ban, bans, baavg = best_avg_era

        print(box_line(dim("  Key findings:")))

        # Bootstrap vs others
        boot_tools = era_tools.get(0, []) + era_tools.get(1, []) + era_tools.get(2, [])
        later_tools = [t for ei_k, ts in era_tools.items() for t in ts if ei_k >= 3]
        if boot_tools and later_tools:
            boot_surv_pct = sum(1 for t in boot_tools if t["tier"] in SURVIVORS) / len(boot_tools) * 100
            later_surv_pct = sum(1 for t in later_tools if t["tier"] in SURVIVORS) / len(later_tools) * 100
            boot_avg = sum(t["citations"] for t in boot_tools) / len(boot_tools)
            later_avg = sum(t["citations"] for t in later_tools) / len(later_tools)

            if boot_surv_pct > later_surv_pct:
                diff = boot_surv_pct - later_surv_pct
                verdict = green(f"Bootstrap: {round(boot_surv_pct)}% yield") + dim(f" vs {round(later_surv_pct)}% later (+{round(diff)}pp)")
                explanation = dim("Bootstrap built more durable tools, not just more tools.")
            else:
                diff = later_surv_pct - boot_surv_pct
                verdict = yellow(f"Later eras: {round(later_surv_pct)}% yield") + dim(f" vs {round(boot_surv_pct)}% Bootstrap (+{round(diff)}pp)")
                explanation = dim("Slower sessions produced higher-quality tools.")

            print(box_line(f"    {verdict}"))
            print(box_line(f"    {explanation}"))
            print(box_line(f"    {dim('Avg citations — Bootstrap: ' + str(round(boot_avg, 1)) + '  Later: ' + str(round(later_avg, 1)))}"))

    print(box_line())
    print(box_bot())


# ─── Entry point ─────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="witness.py — session legacy map")
    parser.add_argument("--all", action="store_true", help="Show all sessions including zero-score")
    parser.add_argument("--session", type=int, help="Deep-dive on a specific session number")
    parser.add_argument("--by-era", action="store_true", help="Per-era yield breakdown")
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
    elif args.by_era:
        display_by_era(session_map, unattributed)
    else:
        display_full(session_map, unattributed, show_all=args.all)


if __name__ == "__main__":
    main()
