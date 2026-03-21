#!/usr/bin/env python3
"""
forecast.py — Where is claude-os heading?

Analyzes trajectory: what's been built, what's stalled, and what the velocity
suggests about what comes next. Complements vitals.py (current health) and
next.py (current ideas) with a longitudinal view.

Three questions this answers:
  1. How fast is the system moving, and is that changing?
  2. What ideas keep appearing without being built? (idea aging)
  3. What should happen to the stalled ideas?

Usage:
    python3 projects/forecast.py             # full forecast
    python3 projects/forecast.py --plain     # no ANSI colors
    python3 projects/forecast.py --json      # machine-readable output
"""

import re
import sys
import json
import subprocess
from pathlib import Path
from datetime import datetime, timezone, timedelta

REPO = Path(__file__).parent.parent
W = 66


# ─── ANSI helpers ──────────────────────────────────────────────────────────────

def make_c(plain: bool):
    if plain:
        return lambda s, *a, **k: s

    def c(text, fg=None, bold=False, dim=False):
        codes = []
        if bold: codes.append("1")
        if dim: codes.append("2")
        if fg:
            palette = {
                "cyan": "36", "blue": "34", "green": "32",
                "yellow": "33", "red": "31", "white": "97",
                "magenta": "35", "gray": "90", "orange": "33",
            }
            codes.append(palette.get(fg, "0"))
        if not codes:
            return text
        return f"\033[{';'.join(codes)}m{text}\033[0m"

    return c


def box(lines, width=W, plain=False):
    top = "╭" + "─" * (width - 2) + "╮"
    bot = "╰" + "─" * (width - 2) + "╯"
    mid = "├" + "─" * (width - 2) + "┤"
    if plain:
        top = "+" + "-" * (width - 2) + "+"
        bot = "+" + "-" * (width - 2) + "+"
        mid = "+" + "-" * (width - 2) + "+"
    result = [top]
    for line in lines:
        if line == "---":
            result.append(mid)
        else:
            visible = re.sub(r'\033\[[0-9;]*m', '', line)
            pad = width - 2 - len(visible)
            result.append("│ " + line + " " * max(0, pad - 1) + "│")
    result.append(bot)
    return "\n".join(result)


def bar(filled, total=10, fill="▓", empty="░", width=None):
    """Render a progress bar. If width given, scale to that."""
    if width:
        filled_w = round((filled / max(total, 1)) * width)
        return fill * filled_w + empty * (width - filled_w)
    return fill * filled + empty * (total - filled)


# ─── Data loading ──────────────────────────────────────────────────────────────

def get_workshop_sessions():
    """Parse git log for workshop session commits and timestamps.

    Handles two commit formats:
    - Old: "workshop: description" (sessions 1-6, no number)
    - New: "workshop session-N: description" (sessions 7+, explicit number)
    Also uses "workshop TIMESTAMP: completed" as fallback session markers.
    """
    try:
        result = subprocess.run(
            ["git", "-C", str(REPO), "log", "--format=%ai %s", "--all"],
            capture_output=True, text=True, timeout=10
        )
        lines = result.stdout.strip().splitlines()
    except Exception:
        return []

    sessions = []
    seen_nums = set()

    # First pass: explicitly numbered sessions (session-N format)
    for line in lines:
        m = re.match(
            r'^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} [+-]\d{4})\s+workshop session-(\d+)[:.]?\s*(.*)',
            line
        )
        if m:
            ts_str, num_str, desc = m.group(1), m.group(2), m.group(3)
            num = int(num_str)
            try:
                ts = datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S %z")
            except ValueError:
                continue
            if num not in seen_nums:
                seen_nums.add(num)
                sessions.append({"num": num, "ts": ts, "desc": desc.strip()})

    # Second pass: "workshop TIMESTAMP: completed" markers for un-numbered sessions
    # These represent early sessions (1-6) before numbered format was used
    completed_markers = []
    for line in lines:
        m = re.match(
            r'^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} [+-]\d{4})\s+'
            r'workshop workshop-(\d{8}-\d{6}): completed',
            line
        )
        if m:
            ts_str = m.group(1)
            try:
                ts = datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S %z")
            except ValueError:
                continue
            completed_markers.append(ts)

    # Assign numbers to un-numbered sessions
    # Sort all completed markers oldest first, then assign sequential numbers
    # starting from 1 for those before the earliest numbered session
    earliest_numbered_ts = min((s["ts"] for s in sessions), default=None)
    unnumbered = sorted(
        [ts for ts in completed_markers
         if earliest_numbered_ts is None or ts < earliest_numbered_ts - timedelta(minutes=30)],
        reverse=True  # oldest last = session 1 first after sort reversal
    )
    unnumbered.sort()  # sort ascending (oldest = session 1)

    for i, ts in enumerate(unnumbered, start=1):
        if i not in seen_nums:
            seen_nums.add(i)
            sessions.append({"num": i, "ts": ts, "desc": f"session {i}"})

    # Sort by session number
    sessions.sort(key=lambda s: s["num"])
    return sessions


def get_tools_per_session(sessions):
    """Estimate tools built per session by reading git log for new .py files."""
    try:
        result = subprocess.run(
            ["git", "-C", str(REPO), "log", "--format=%ai %s", "--diff-filter=A",
             "--name-only", "--", "projects/*.py"],
            capture_output=True, text=True, timeout=15
        )
    except Exception:
        return {}

    # Parse: commit header, then filenames
    tool_adds = {}  # session_num or ts -> list of files
    current_ts = None
    current_subject = None
    lines = result.stdout.strip().splitlines()

    i = 0
    while i < len(lines):
        line = lines[i]
        # Try to parse as a commit header
        m = re.match(r'^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} [+-]\d{4})\s+(.*)', line)
        if m:
            current_ts = datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S %z")
            current_subject = m.group(2)
        elif line.startswith("projects/") and line.endswith(".py") and current_ts:
            stem = Path(line).stem
            # Skip field note files
            if not stem.startswith("field-"):
                tool_adds.setdefault(current_ts, []).append(stem)
        i += 1

    # Match tool-add timestamps to sessions
    session_tools = {}
    for ts, tools in tool_adds.items():
        # Find which session this commit belongs to (closest session before or at this time)
        best_session = None
        for s in sessions:
            if s["ts"] <= ts + timedelta(minutes=30):
                best_session = s["num"]
            else:
                break
        if best_session is not None:
            session_tools.setdefault(best_session, []).extend(tools)

    return session_tools


def load_field_notes():
    """Load all field note content with session numbers."""
    notes = []
    for path in sorted(REPO.glob("projects/field-notes*.md")):
        text = path.read_text()
        # Try to extract session number
        m = re.search(r'session[- _](\d+)', path.stem, re.IGNORECASE)
        num = int(m.group(1)) if m else None
        if num is None:
            # "field-notes-from-free-time.md" = session 1
            if "free-time" in path.stem:
                num = 1
        notes.append({"path": path, "num": num, "text": text})
    notes.sort(key=lambda n: (n["num"] or 0))
    return notes


def get_idea_file_session(filename):
    """Find what session number a knowledge file was first committed in."""
    try:
        result = subprocess.run(
            ["git", "-C", str(REPO), "log", "--format=%s", "--diff-filter=A",
             "--", str(filename)],
            capture_output=True, text=True, timeout=10
        )
        subject = result.stdout.strip().splitlines()
        if not subject:
            return None
        # "workshop session-7: ..." → 7
        m = re.search(r'session-(\d+)', subject[0])
        return int(m.group(1)) if m else None
    except Exception:
        return None


def build_idea_watchlist(sessions):
    """
    Define ideas to track with their age info.
    Returns list of dicts: {id, title, status, first_session, sessions_open}
    """
    current = max((s["num"] for s in sessions), default=0)

    # Ideas from exoclaw-ideas.md (committed in session 7)
    exoclaw_session = get_idea_file_session("knowledge/exoclaw-ideas.md") or 7

    def open_since(first_session):
        return max(current - first_session, 0)

    return [
        {
            "id": "github-actions",
            "title": "GitHub Actions as a Channel",
            "status": "done",  # Completed session 35 — gh-channel.py
            "first_session": exoclaw_session,
            "sessions_open": open_since(exoclaw_session),
            "effort": "medium",
            "source": "exoclaw-ideas.md #6",
            "note": "Trigger tasks from GitHub issue comments. Zero extra K8s.",
        },
        {
            "id": "task-conversation",
            "title": "Task files as Conversation backend",
            "status": "open",
            "first_session": exoclaw_session,
            "sessions_open": open_since(exoclaw_session),
            "effort": "high",
            "source": "exoclaw-ideas.md #3",
            "note": "Resumable tasks via git-stored conversation history.",
        },
        {
            "id": "skills-context",
            "title": "Skills via system_context()",
            "status": "open",
            "first_session": exoclaw_session,
            "sessions_open": open_since(exoclaw_session),
            "effort": "medium",
            "source": "exoclaw-ideas.md #5",
            "note": "Self-injecting skills activated by pattern matching on task.",
        },
        {
            "id": "multi-agent",
            "title": "Multi-agent via the Bus",
            "status": "proposed",  # In PR #2
            "first_session": exoclaw_session,
            "sessions_open": open_since(exoclaw_session),
            "effort": "high",
            "source": "exoclaw-ideas.md #7",
            "note": "PR #2 in review — coordinator + parallel workers.",
        },
        {
            "id": "exoclaw-worker",
            "title": "Use exoclaw as the worker loop",
            "status": "open",
            "first_session": exoclaw_session,
            "sessions_open": open_since(exoclaw_session),
            "effort": "high",
            "source": "exoclaw-ideas.md #1",
            "note": "Replace hand-rolled worker with AgentLoop + process_direct().",
        },
        {
            "id": "k8s-executor",
            "title": "Kubernetes-native Executor",
            "status": "open",
            "first_session": exoclaw_session,
            "sessions_open": open_since(exoclaw_session),
            "effort": "high",
            "source": "exoclaw-ideas.md #2",
            "note": "Each tool call becomes a K8s Job for isolation + resilience.",
        },
        {
            "id": "2000-line-budget",
            "title": "The 2,000-line design constraint",
            "status": "open",
            "first_session": exoclaw_session,
            "sessions_open": open_since(exoclaw_session),
            "effort": "low",
            "source": "exoclaw-ideas.md #8",
            "note": "Design exercise: what would we cut if line count were a budget?",
        },
    ]


# ─── Analysis ──────────────────────────────────────────────────────────────────

def compute_velocity(sessions):
    """Compute sessions-per-day and trends."""
    if not sessions:
        return {}

    first = sessions[0]["ts"]
    last = sessions[-1]["ts"]
    now = datetime.now(timezone.utc)

    age_days = max((now - first).total_seconds() / 86400, 0.1)
    total = len(sessions)
    rate = total / age_days

    # Recent rate: last 5 sessions
    if len(sessions) >= 5:
        recent_span = (sessions[-1]["ts"] - sessions[-5]["ts"]).total_seconds() / 86400
        recent_rate = 5 / max(recent_span, 0.1)
    else:
        recent_rate = rate

    # Count sessions today
    today = now.date()
    sessions_today = sum(1 for s in sessions if s["ts"].date() == today)

    return {
        "age_days": age_days,
        "total": total,
        "rate_per_day": rate,
        "recent_rate": recent_rate,
        "sessions_today": sessions_today,
        "first_ts": first,
        "last_ts": last,
    }


def aging_severity(sessions_open):
    """Return severity label and color based on how many sessions an idea has been open."""
    if sessions_open >= 6:
        return "aging", "red"
    elif sessions_open >= 4:
        return "stalled", "yellow"
    elif sessions_open >= 2:
        return "deferred", "cyan"
    else:
        return "new", "green"


# ─── Rendering ─────────────────────────────────────────────────────────────────

def render_velocity(vel, sessions, session_tools, c):
    """Render the session velocity section."""
    lines = []
    age = vel["age_days"]
    age_str = f"{age:.1f} days" if age < 7 else f"{age / 7:.1f} weeks"

    lines.append(c("  SESSION VELOCITY", bold=True))
    lines.append("")

    # Age + rate
    rate_per_day = vel["rate_per_day"]
    rate_color = "green" if rate_per_day >= 3 else "yellow"
    rate_str = f"{rate_per_day:.1f}/day"
    lines.append(
        f"  {c(age_str, bold=True)} old  ·  "
        f"{c(str(vel['total']), bold=True)} sessions  ·  "
        f"{c(rate_str, fg=rate_color)}"
    )

    # Sessions today
    if vel["sessions_today"] > 0:
        lines.append(
            f"  Today: {c(str(vel['sessions_today']), bold=True)} sessions already"
        )

    lines.append("")

    # Tools per session trend
    if session_tools:
        total_tool_adds = sum(len(v) for v in session_tools.values())
        sessions_with_tools = len(session_tools)
        avg = total_tool_adds / max(sessions_with_tools, 1)

        lines.append(
            f"  Tools built: {c(f'{avg:.1f}/session', bold=True)}  "
            f"({c(str(total_tool_adds), dim=True)} tools across "
            f"{c(str(sessions_with_tools), dim=True)} sessions)"
        )

    # Project forward — use lower-bound estimate (avg rate, not recent burst)
    avg_rate = vel["rate_per_day"]
    current_tools = len(list((REPO / "projects").glob("*.py")))
    tool_rate = sum(len(v) for v in session_tools.values()) / max(vel["total"], 1)
    projected_sessions_7d = vel["total"] + round(avg_rate * 7)
    projected_tools_7d = current_tools + round(tool_rate * avg_rate * 7)

    lines.append("")
    lines.append(c("  PROJECTION (7 days at current avg rate):", dim=True))
    lines.append(
        f"    ~{projected_sessions_7d} total sessions  "
        f"·  ~{projected_tools_7d} tools  "
        f"{c('(assumes rate holds)', dim=True)}"
    )

    return lines


def render_idea_aging(ideas, notes, sessions, c):
    """Render the idea aging section."""
    current_session = max((s["num"] for s in sessions), default=0)
    lines = []
    lines.append(c("  IDEA AGING", bold=True))
    lines.append(c("  Sessions elapsed since idea was first recorded:", dim=True))
    lines.append("")

    open_ideas = [i for i in ideas if i["status"] == "open"]
    proposed_ideas = [i for i in ideas if i["status"] == "proposed"]

    # Sort by sessions_open descending (oldest first)
    open_ideas_sorted = sorted(open_ideas, key=lambda x: x["sessions_open"], reverse=True)

    for idea in open_ideas_sorted:
        sessions_open = idea["sessions_open"]
        first = idea["first_session"]

        severity, color = aging_severity(sessions_open)
        bar_filled = min(sessions_open, 10)
        bar_str = bar(bar_filled, 10, width=10)

        title = idea["title"]
        if len(title) > 38:
            title = title[:35] + "..."

        since_str = f"since S{first}"
        sessions_str = f"{sessions_open} sessions open"
        lines.append(
            f"  {c(bar_str, fg=color)}  "
            f"{c(title, bold=(severity == 'aging'))}"
        )
        lines.append(
            f"  {c(' ' * 10, dim=True)}  "
            f"{c(sessions_str + '  ·  ' + since_str, dim=True)}"
        )
        lines.append("")

    if proposed_ideas:
        lines.append(c("  IN PROPOSAL:", dim=True))
        for idea in proposed_ideas:
            sessions_open = idea["sessions_open"]
            lines.append(
                f"    {c('⏳', fg='yellow')} {idea['title'][:46]}  "
                f"{c(f'{sessions_open} sessions open', dim=True)}"
            )
        lines.append("")

    return lines


def render_recommendations(ideas, notes, sessions, c):
    """Render the recommendations section."""
    lines = []
    lines.append(c("  RECOMMENDATIONS", bold=True))
    lines.append("")

    open_ideas = [i for i in ideas if i["status"] == "open"]
    has_any = False

    # Sort by sessions_open desc
    open_ideas_sorted = sorted(open_ideas, key=lambda x: x["sessions_open"], reverse=True)

    for idea in open_ideas_sorted:
        sessions_open = idea["sessions_open"]
        effort = idea.get("effort", "medium")
        severity, color = aging_severity(sessions_open)

        if severity == "aging":
            has_any = True
            # Differentiate advice by effort level
            if effort == "low":
                action = "→ This is low effort — worth doing this session."
            elif effort == "high":
                action = "→ High effort: open a proposal PR for dacort to review."
            else:
                action = "→ Medium effort: propose a PR or build this session."

            lines.append(
                f"  {c('⚠', fg='red', bold=True)}  "
                f"{c(idea['title'][:48], bold=True, fg='red')}  "
                f"{c('[' + effort + ']', dim=True)}"
            )
            lines.append(
                f"     {sessions_open} sessions open  ·  "
                f"{c(idea['note'][:44], dim=True)}"
            )
            lines.append(f"     {c(action, dim=True)}")
            lines.append("")
        elif severity == "stalled":
            has_any = True
            lines.append(
                f"  {c('○', fg='yellow')}  "
                f"{c(idea['title'][:44], fg='yellow')}  "
                f"{c('[' + effort + ']', dim=True)}"
            )
            lines.append(
                f"     {sessions_open} sessions  ·  consider proposing if not building soon"
            )
            lines.append("")

    if not has_any:
        lines.append(c("  All open ideas are relatively fresh. No action needed.", dim=True))
        lines.append("")

    # Pattern observation
    aging_count = sum(
        1 for i in open_ideas
        if aging_severity(i["sessions_open"])[0] in ("aging", "stalled")
    )
    if aging_count >= 2:
        lines.append(c("  Pattern:", bold=True))
        lines.append(
            f"  {c('Medium-effort ideas keep getting displaced by quick wins.', dim=True)}"
        )
        lines.append(
            f"  {c('Aging ideas need a decision: build, propose, or explicitly drop.', dim=True)}"
        )

    return lines


def render_narrative(sessions, ideas, notes, c):
    """Render a short narrative about the trajectory."""
    last_committed = max((s["num"] for s in sessions), default=0)
    # Current session = last committed + 1 (the one running now, not yet in git)
    current_session = last_committed + 1
    open_ideas = [i for i in ideas if i["status"] == "open"]
    aging = [i for i in open_ideas if aging_severity(i["sessions_open"])[0] == "aging"]
    stalled = [i for i in open_ideas if aging_severity(i["sessions_open"])[0] == "stalled"]
    needs_decision = aging + stalled

    lines = []
    lines.append(c("  THE STORY SO FAR", bold=True))
    lines.append("")

    if current_session <= 5:
        phase = "early growth — building the toolkit"
    elif current_session <= 9:
        phase = "refinement — fixing and filling gaps"
    elif current_session <= 13:
        phase = "polish — reducing friction"
    else:
        phase = "maturity — architectural decisions ahead"

    lines.append(f"  Estimated session {current_session}  →  {c(phase, bold=True)}")
    lines.append("")

    if needs_decision:
        count_str = str(len(needs_decision))
        lines.append(
            f"  {c(count_str, bold=True)} ideas have been deferred for "
            f"4+ sessions without action."
        )
        lines.append(
            "  The toolkit is mature enough that the next leap is architectural."
        )
        lines.append(
            "  The question shifts from 'what to build' to 'what to decide.'"
        )
    else:
        lines.append(
            "  The idea queue is relatively fresh. This is a good phase for exploration."
        )

    return lines


# ─── Main ──────────────────────────────────────────────────────────────────────

def render(plain=False):
    c = make_c(plain)
    now = datetime.now(timezone.utc)

    # Load data
    sessions = get_workshop_sessions()
    notes = load_field_notes()
    ideas = build_idea_watchlist(sessions)
    vel = compute_velocity(sessions)
    session_tools = get_tools_per_session(sessions)

    header_lines = [
        c("  forecast.py  ─  where things are heading", bold=True) +
        "  " + c(now.strftime("%Y-%m-%d"), dim=True),
        c("  Trajectory analysis for claude-os", dim=True),
    ]

    # Build all sections
    velocity_lines = render_velocity(vel, sessions, session_tools, c)
    aging_lines = render_idea_aging(ideas, notes, sessions, c)
    reco_lines = render_recommendations(ideas, notes, sessions, c)
    narrative_lines = render_narrative(sessions, ideas, notes, c)

    all_lines = (
        header_lines
        + ["---"]
        + velocity_lines
        + ["---"]
        + aging_lines
        + ["---"]
        + reco_lines
        + ["---"]
        + narrative_lines
    )

    print(box(all_lines, plain=plain))


def render_json():
    sessions = get_workshop_sessions()
    ideas = build_idea_watchlist(sessions)
    vel = compute_velocity(sessions)

    result = {
        "velocity": {
            "age_days": round(vel.get("age_days", 0), 1),
            "total_sessions": vel.get("total", 0),
            "rate_per_day": round(vel.get("rate_per_day", 0), 2),
            "sessions_today": vel.get("sessions_today", 0),
        },
        "idea_aging": [],
    }

    for idea in ideas:
        sessions_open = idea["sessions_open"]
        severity, _ = aging_severity(sessions_open)
        result["idea_aging"].append({
            "id": idea["id"],
            "title": idea["title"],
            "status": idea["status"],
            "sessions_open": sessions_open,
            "first_session": idea["first_session"],
            "severity": severity,
        })

    print(json.dumps(result, indent=2))


def main():
    import argparse
    parser = argparse.ArgumentParser(
        prog="forecast.py",
        description="Trajectory analysis for claude-os — velocity, idea aging, and what to decide next.\n"
                    "Complements vitals.py (current health) and next.py (current ideas) with a longitudinal view.",
        epilog=(
            "examples:\n"
            "  python3 projects/forecast.py          # full forecast\n"
            "  python3 projects/forecast.py --plain  # no ANSI colors (safe for piping)\n"
            "  python3 projects/forecast.py --json   # machine-readable output"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--plain", action="store_true",
                        help="disable ANSI colors (safe for piping)")
    parser.add_argument("--json", action="store_true", dest="as_json",
                        help="machine-readable JSON output")
    args = parser.parse_args()

    if args.as_json:
        render_json()
    else:
        render(plain=args.plain)


if __name__ == "__main__":
    main()
