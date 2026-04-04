#!/usr/bin/env python3
"""dispatch.py — Thematic narrative dispatch from recent Claude OS workshop sessions.

Groups workshop activity by what sessions were *thinking about*, not just listing
what they built. Reads like a research lab report, not a status page.

Distinct from:
  catchup.py  — factual prose, chronological, for returning from break
  weekly-digest.py — mechanical markdown table
  arc.py — one-line per session, chronological

dispatch.py groups sessions by theme and writes about the shape of the period,
not just its contents. Useful for dacort to understand the intellectual direction.

Usage:
  python3 projects/dispatch.py              # last 7 days
  python3 projects/dispatch.py --days 14   # last 2 weeks
  python3 projects/dispatch.py --all        # all time (uses last 30 days)
  python3 projects/dispatch.py --plain      # no ANSI colors
"""
import argparse
import json
import os
import re
import subprocess
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from pathlib import Path

RESET = "\033[0m"
BOLD  = "\033[1m"
DIM   = "\033[2m"
CYAN  = "\033[36m"
WHITE = "\033[97m"
YELLOW= "\033[33m"
GREEN = "\033[32m"
MAGENTA = "\033[35m"
RED   = "\033[31m"

USE_COLOR = True

def c(text, *codes):
    return ("".join(codes) + str(text) + RESET) if USE_COLOR else str(text)

REPO = Path(__file__).parent.parent

# ── Theme definitions ──────────────────────────────────────────────────────────
# Each theme: (name, keywords, display_name, description)
THEMES = [
    ("temporal",       ["pace", "rhythm", "era", "seasons", "bootstrap", "ecg", "phase", "timeline", "arc"],
                       "Rhythm & Time",
                       "understanding when the system was active, how it changed pace, what phases it moved through"),
    ("portrait",       ["capsule", "close-reading", "portrait", "past session", "witness", "legacy", "citation", "lineage"],
                       "Reading the Past",
                       "slow examination of specific prior sessions — what they introduced, what lasted"),
    ("toolkit",        ["retire", "slim", "dormant", "toolkit", "audit", "weight", "tool"],
                       "Toolkit",
                       "the craft of knowing what to keep and what to let go"),
    ("continuity",     ["handoff", "letter", "future", "chain", "instance", "forward", "channel", "dispatch"],
                       "Continuity",
                       "the infrastructure of memory for a stateless system — how one session reaches the next"),
    ("accounting",     ["ledger", "honest", "ratio", "outward", "inward", "accounting", "serve", "balance"],
                       "Honest Accounting",
                       "what fraction of energy goes inward vs. outward — who the system actually serves"),
    ("narrative",      ["field note", "reconstruct", "gap", "season", "manifesto", "character", "story", "arc", "history"],
                       "The Arc",
                       "writing the story of what happened, filling gaps, understanding the shape of development"),
    ("outward",        ["notify", "telegram", "linkedin", "outside", "external", "notification"],
                       "Outward Signal",
                       "building ways to reach dacort and the outside world"),
    ("epistemic",      ["hold", "uncertainty", "depth", "honest", "don't know", "unknown", "h001", "h002", "h003"],
                       "What We Don't Know",
                       "naming what can't be answered — the system's epistemic housekeeping"),
    ("infrastructure", ["controller", "worker", "entrypoint", "k8s", "kubernetes", "spawn", "dispatcher"],
                       "Infrastructure",
                       "the Go controller, worker entrypoints, the Kubernetes plumbing"),
    ("discovery",      ["found", "measured", "empirical", "discovered", "pattern", "proved", "insight"],
                       "Discovery",
                       "sessions that found something — measured, compared, surfaced a pattern"),
    ("unbuilt",        ["unbuilt", "deferred", "shadow", "ask", "proposed", "pending"],
                       "The Shadow Map",
                       "what was asked for but not yet built — the system's deferred intentions"),
    ("creative",       ["weather", "poetic", "metaphor", "forecast", "haiku", "creative", "poem", "art",
                        "april fools", "whimsy", "vibe"],
                       "Creative",
                       "sessions that built something unusual — tools that blend function with personality"),
]

THEME_OPENERS = {
    "temporal": "Sessions thinking about time — how the pace shifted, when work intensified, what the eras meant.",
    "portrait": "Sessions that slowed down to look backward — reading specific prior instances like close texts.",
    "toolkit": "Sessions asking whether the toolkit has grown too heavy — auditing, retiring, keeping honest.",
    "continuity": "Sessions working on the channel between instances — the handoff infrastructure, forward letters, the chain.",
    "accounting": "Sessions doing honest accounting — not 'what did we build' but 'what does this system actually serve'.",
    "narrative": "Sessions working on the arc — reconstructing gaps, writing the story of what happened, understanding how we got here.",
    "outward": "Sessions building outward signal — ways to reach dacort when something happens, or when a session ends.",
    "epistemic": "Sessions naming what isn't known — holds, uncertainties, the things that can't be resolved from inside.",
    "infrastructure": "Sessions working on the machine — controller code, entrypoints, the Kubernetes infrastructure.",
    "discovery": "Sessions that found something — measured empirically, surfaced a pattern, proved something held or didn't.",
    "unbuilt": "Sessions working on the shadow record — what was asked for but deferred, the gap between request and delivery.",
    "creative": "Sessions that built something unusual — poetic tools, playful experiments, tools that blend function with character.",
}


# ── Data loading ───────────────────────────────────────────────────────────────

def load_workshop_summaries(days: int) -> dict:
    """Load workshop summaries for the period."""
    path = REPO / "knowledge" / "workshop-summaries.json"
    if not path.exists():
        return {}

    with open(path) as f:
        data = json.load(f)

    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    recent = {}
    for k, v in data.items():
        parts = k.split('-')
        if len(parts) >= 2:
            try:
                dt = datetime.strptime(parts[1], '%Y%m%d').replace(tzinfo=timezone.utc)
                if dt >= cutoff:
                    recent[k] = v if isinstance(v, str) else str(v)
            except (ValueError, IndexError):
                pass
    return recent


def load_recent_handoffs(days: int) -> list:
    """Load recent handoff files, parsed."""
    handoffs_dir = REPO / "knowledge" / "handoffs"
    if not handoffs_dir.exists():
        return []

    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    handoffs = []

    for f in sorted(handoffs_dir.glob("session-*.md")):
        try:
            content = f.read_text()
            fm_match = re.search(r'^---\n(.*?)\n---', content, re.DOTALL)
            if not fm_match:
                continue
            fm = fm_match.group(1)
            date_match = re.search(r'date:\s*(\S+)', fm)
            if not date_match:
                continue
            dt = datetime.strptime(date_match.group(1), '%Y-%m-%d').replace(tzinfo=timezone.utc)
            if dt < cutoff:
                continue

            session_match = re.search(r'session:\s*(\d+)', fm)
            built_match = re.search(r'## What I built\n\n(.*?)(?=\n##|\Z)', content, re.DOTALL)
            state_match = re.search(r'## Mental state\n\n(.*?)(?=\n##|\Z)', content, re.DOTALL)
            next_match  = re.search(r'## One specific thing for next session\n\n(.*?)(?=\n##|\Z)', content, re.DOTALL)

            handoffs.append({
                'session': int(session_match.group(1)) if session_match else 0,
                'date':    dt,
                'built':   built_match.group(1).strip() if built_match else '',
                'state':   state_match.group(1).strip() if state_match else '',
                'next':    next_match.group(1).strip() if next_match else '',
            })
        except Exception:
            pass

    return sorted(handoffs, key=lambda x: x['session'])


def get_commit_stats(days: int) -> dict:
    """Count commits and collect topic words."""
    try:
        result = subprocess.run(
            ['git', '-C', str(REPO), 'log', '--oneline',
             f'--since={days} days ago', '--author=Claude OS'],
            capture_output=True, text=True
        )
        lines = [l for l in result.stdout.strip().split('\n') if l]
        return {'count': len(lines)}
    except Exception:
        return {'count': 0}


# ── Theme detection ────────────────────────────────────────────────────────────

def detect_theme(summary: str) -> str:
    summary_lower = summary.lower()
    for name, keywords, *_ in THEMES:
        if any(kw in summary_lower for kw in keywords):
            return name
    return "other"


def group_by_theme(summaries: dict) -> dict:
    groups = defaultdict(list)
    for session_id, summary in summaries.items():
        theme = detect_theme(summary)
        groups[theme].append((session_id, summary))
    return dict(groups)


# ── Formatting ─────────────────────────────────────────────────────────────────

def date_range_str(summaries: dict, days: int) -> str:
    if not summaries:
        end = datetime.now(timezone.utc)
        start = end - timedelta(days=days)
    else:
        dates = []
        for k in summaries:
            parts = k.split('-')
            if len(parts) >= 2:
                try:
                    dates.append(datetime.strptime(parts[1], '%Y%m%d'))
                except (ValueError, IndexError):
                    pass
        if dates:
            start = min(dates)
            end = datetime.now(timezone.utc)
        else:
            end = datetime.now(timezone.utc)
            start = end - timedelta(days=days)

    if start.month == end.month and start.year == end.year:
        return f"{start.strftime('%B %d')}–{end.strftime('%d, %Y')}"
    elif start.year == end.year:
        return f"{start.strftime('%B %d')} – {end.strftime('%B %d, %Y')}"
    else:
        return f"{start.strftime('%B %d, %Y')} – {end.strftime('%B %d, %Y')}"


def format_session_line(session_id: str, summary: str, indent: int = 4) -> str:
    """Format a single session summary line."""
    parts = session_id.split('-')
    date_str = ""
    if len(parts) >= 2:
        try:
            dt = datetime.strptime(parts[1], '%Y%m%d')
            date_str = dt.strftime('%b %d')
        except (ValueError, IndexError):
            pass

    # Truncate
    max_len = 85
    summary_display = summary[:max_len] + "…" if len(summary) > max_len else summary

    pad = " " * indent
    if date_str:
        return c(f"{pad}{date_str}  ", DIM) + c(summary_display, DIM)
    return c(f"{pad}{summary_display}", DIM)


def format_dispatch(days: int, summaries: dict, handoffs: list, commits: dict) -> str:
    groups = group_by_theme(summaries)
    n_sessions = len(summaries)
    n_commits = commits['count']
    date_range = date_range_str(summaries, days)

    # Sort theme groups: most sessions first, "other" last
    sorted_groups = sorted(
        groups.items(),
        key=lambda x: (-len(x[1]), x[0] == "other")
    )

    lines = []
    lines.append("")
    lines.append(
        c("  Claude OS Dispatch", BOLD, WHITE) +
        c(f"  —  {date_range}", DIM)
    )
    lines.append("")

    if n_sessions == 0:
        lines.append(c("  No sessions found for this period.", DIM))
        lines.append("")
        return "\n".join(lines)

    # Period stats
    lines.append(c(
        f"  {n_sessions} session{'s' if n_sessions != 1 else ''}  "
        f"·  {n_commits} commit{'s' if n_commits != 1 else ''}  "
        f"·  {len([g for g in groups if g != 'other'])} theme{'s' if len(groups) > 1 else ''}",
        DIM
    ))
    lines.append("")
    lines.append("  " + c("─" * 58, DIM))
    lines.append("")

    # Top-level summary: what was this period about?
    top_themes = [name for name, _ in sorted_groups[:3] if name != "other"]
    if top_themes:
        theme_descs = []
        for t_name in top_themes:
            for name, _, display, desc in THEMES:
                if name == t_name:
                    theme_descs.append(display.lower())
                    break
            else:
                theme_descs.append(t_name)

        if len(theme_descs) >= 2:
            last = theme_descs[-1]
            rest = ", ".join(theme_descs[:-1])
            lede = f"The threads: {rest}, and {last}."
        else:
            lede = f"The thread: {theme_descs[0]}."

        lines.append(c(f"  {lede}", DIM))
        lines.append("")

    # Theme sections
    for theme_name, sessions in sorted_groups:
        n = len(sessions)

        # Get theme info
        theme_display = theme_name.title()
        opener = THEME_OPENERS.get(theme_name, f"{n} session{'s' if n > 1 else ''}.")
        for t_name, _, t_display, _ in THEMES:
            if t_name == theme_name:
                theme_display = t_display
                break

        lines.append(c(f"  {theme_display.upper()}", BOLD, CYAN))
        lines.append("")
        lines.append(c(f"  {opener}", DIM))
        lines.append("")

        # List sessions (max 4, then collapse)
        show = sessions[:4]
        for session_id, summary in show:
            lines.append(format_session_line(session_id, summary))
        if len(sessions) > 4:
            lines.append(c(f"    + {len(sessions) - 4} more", DIM))

        lines.append("")

    # From recent handoffs: the most personal/reflective bits
    if handoffs:
        lines.append("  " + c("─" * 58, DIM))
        lines.append("")
        lines.append(c("  WHAT SESSIONS SAID THEY BUILT", BOLD, YELLOW))
        lines.append("")
        for h in handoffs[-3:]:
            if h['built']:
                built_display = h['built'][:130]
                lines.append(
                    c(f"  Session {h['session']}  ", BOLD, MAGENTA) +
                    c(built_display, DIM)
                )
                lines.append("")

    # What's next (from most recent handoff)
    if handoffs:
        last_h = handoffs[-1]
        if last_h.get('next'):
            lines.append("  " + c("─" * 58, DIM))
            lines.append("")
            lines.append(c("  THE HANDOFF", BOLD))
            lines.append("")
            next_text = last_h['next'][:250]
            for line in next_text.splitlines():
                lines.append(c(f"  {line}", DIM))
            lines.append("")

    # Footer
    lines.append("  " + c("─" * 58, DIM))
    lines.append(c(
        f"\n  dispatch.py  ·  {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        DIM
    ))
    lines.append("")

    return "\n".join(lines)


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    global USE_COLOR

    parser = argparse.ArgumentParser(
        description="Thematic narrative dispatch from recent Claude OS sessions",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--days", type=int, default=7,
                        help="How many days back to look (default: 7)")
    parser.add_argument("--plain", action="store_true",
                        help="No ANSI colors in output")
    args = parser.parse_args()

    if args.plain:
        USE_COLOR = False

    summaries = load_workshop_summaries(args.days)
    handoffs  = load_recent_handoffs(args.days)
    commits   = get_commit_stats(args.days)

    output = format_dispatch(args.days, summaries, handoffs, commits)
    print(output)


if __name__ == "__main__":
    main()
