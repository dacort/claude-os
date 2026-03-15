#!/usr/bin/env python3
"""
tempo.py — The project's rhythm over time.

Reads field notes and git history to show when the project was most
active, how tool growth has varied, and whether we're accelerating
or decelerating.

Answers: When did we sprint? When did we breathe? Are we speeding up?

Usage:
    python3 projects/tempo.py           # Full tempo view
    python3 projects/tempo.py --plain   # No ANSI colors
    python3 projects/tempo.py --brief   # Just headline stats

Author: Claude OS (Workshop session 39, 2026-03-15)
"""

import argparse
import collections
import datetime
import pathlib
import re
import subprocess
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

USE_COLOR = True

def c(text, *codes):
    if not USE_COLOR:
        return str(text)
    return "".join(codes) + str(text) + RESET

def strip_ansi(text):
    return re.sub(r"\033\[[^m]*m", "", text)

def visible_len(s):
    return len(strip_ansi(s))


# ── Paths ─────────────────────────────────────────────────────────────────────

REPO         = pathlib.Path(__file__).parent.parent
PROJECTS_DIR = REPO / "projects"


# ── Git helpers ───────────────────────────────────────────────────────────────

def git(*args):
    result = subprocess.run(
        ["git", "-C", str(REPO)] + list(args),
        capture_output=True, text=True
    )
    if result.returncode != 0:
        return []
    return result.stdout.strip().splitlines()


def get_tools_introduced_on_day(day_str):
    """Get all Python tools added to projects/ on a given date (YYYY-MM-DD)."""
    # Get all commits on that day
    commits = git(
        "log", "--oneline",
        f"--after={day_str} 00:00:00",
        f"--before={day_str} 23:59:59",
        "--format=%H"
    )
    tools = set()
    for commit in commits:
        added = git("show", "--name-only", "--diff-filter=A",
                    "--format=", commit)
        for line in added:
            if line.startswith("projects/") and line.endswith(".py"):
                name = pathlib.Path(line).name
                if name not in ("__init__.py",):
                    tools.add(name)
    return sorted(tools)


# ── Field note parsing ────────────────────────────────────────────────────────

def find_field_notes():
    """Find all field note files in chronological session order."""
    notes = list(PROJECTS_DIR.glob("field-notes*.md"))

    def sort_key(p):
        name = p.stem
        if name == "field-notes-from-free-time":
            return 1
        m = re.search(r"session-(\d+)", name)
        if m:
            return int(m.group(1))
        return 999

    return sorted(notes, key=sort_key)


def parse_session_date(path):
    """Extract date from a field note file."""
    try:
        text = path.read_text()
    except Exception:
        return None

    m = re.search(r"(\d{4}-\d{2}-\d{2})", text[:300])
    if m:
        return m.group(1)
    return None


def parse_session_num(path):
    """Extract session number from filename."""
    if "from-free-time" in path.stem:
        return 1
    m = re.search(r"session-(\d+)", path.stem)
    return int(m.group(1)) if m else 999


def get_session_tools_from_git(field_note_name):
    """Get Python tools introduced in the same commit as the field note."""
    lines = git("log", "--oneline", "--all", "--diff-filter=A",
                "--", f"projects/{field_note_name}.md")
    if not lines:
        return []

    commit_hash = lines[0].split()[0]
    added = git("show", "--name-only", "--diff-filter=A",
                "--format=", commit_hash)
    tools = []
    for line in added:
        if line.startswith("projects/") and line.endswith(".py"):
            tools.append(pathlib.Path(line).name)
    return tools


def collect_session_data():
    """
    Returns list of dicts with session metadata.
    Each dict: {session, date, tools, path}
    """
    notes = find_field_notes()
    sessions = []
    for path in notes:
        date = parse_session_date(path)
        num  = parse_session_num(path)
        tools = get_session_tools_from_git(path.stem)
        sessions.append({
            "session": num,
            "date":    date or "?",
            "tools":   tools,
            "path":    path,
        })
    return sessions


# ── Analysis ──────────────────────────────────────────────────────────────────

def group_by_day(sessions):
    """Group sessions by calendar date."""
    by_day = collections.OrderedDict()
    for s in sessions:
        day = s["date"]
        if day == "?":
            continue
        if day not in by_day:
            by_day[day] = []
        by_day[day].append(s)
    return by_day


def day_of_week(date_str):
    """Return abbreviated weekday for a YYYY-MM-DD string."""
    try:
        d = datetime.date.fromisoformat(date_str)
        return d.strftime("%a")
    except Exception:
        return "?"


def month_day(date_str):
    """Return 'Mar 10' style label."""
    try:
        d = datetime.date.fromisoformat(date_str)
        return d.strftime("%b %d")
    except Exception:
        return date_str


def compute_trajectory(by_day):
    """
    Compare pace of the last third vs first two thirds.
    Returns: 'accelerating', 'steady', or 'decelerating'
    """
    days = list(by_day.keys())
    if len(days) < 3:
        return "steady"

    counts = [len(by_day[d]) for d in days]
    split  = len(counts) // 3

    early  = sum(counts[:split]) / max(split, 1)
    recent = sum(counts[-split:]) / max(split, 1)

    ratio = recent / max(early, 0.01)
    if ratio > 1.25:
        return "accelerating"
    elif ratio < 0.75:
        return "decelerating"
    return "steady"


# ── Rendering ─────────────────────────────────────────────────────────────────

WIDTH = 68

def box_top():  return "╭" + "─" * (WIDTH - 2) + "╮"
def box_bot():  return "╰" + "─" * (WIDTH - 2) + "╯"
def box_sep():  return "├" + "─" * (WIDTH - 2) + "┤"
def box_blank(): return "│" + " " * (WIDTH - 2) + "│"

def box_row(content, right="", left_pad=2):
    inner    = WIDTH - 2
    left_str = " " * left_pad + content
    right_str = right + "  " if right else ""
    ll = visible_len(left_str)
    rl = visible_len(right_str)
    gap = inner - ll - rl
    if gap < 1:
        right_str = ""
        gap = inner - ll
    return "│" + left_str + " " * max(0, gap) + right_str + "│"


BAR_WIDTH = 24

def sparkbar(count, max_count, color):
    """Render a fixed-width bar representing count/max_count."""
    filled = round((count / max(max_count, 1)) * BAR_WIDTH)
    bar    = c("█" * filled, color) + c("░" * (BAR_WIDTH - filled), DIM)
    return bar


def render_daily_chart(by_day):
    """Render the session-per-day chart."""
    lines = []
    lines.append(box_sep())
    lines.append(box_row(c("SESSION DENSITY", BOLD, CYAN), "", left_pad=2))
    lines.append(box_row(c("  Sessions per calendar day", DIM), "", left_pad=0))
    lines.append(box_blank())

    max_count = max(len(v) for v in by_day.values()) if by_day else 1
    all_tools_by_day = {}

    cumulative_tools = 0
    prev_tools = 0

    for day, sessions in by_day.items():
        count     = len(sessions)
        tools_today = []
        for s in sessions:
            tools_today.extend(s["tools"])
        tools_today = list(dict.fromkeys(tools_today))  # dedup, preserve order
        cumulative_tools += len(tools_today)
        all_tools_by_day[day] = tools_today

        # Color based on intensity
        if count >= max_count:
            color = MAGENTA
        elif count >= max_count * 0.7:
            color = CYAN
        elif count >= max_count * 0.4:
            color = GREEN
        else:
            color = DIM + GREEN

        bar     = sparkbar(count, max_count, color)
        dow     = day_of_week(day)
        label   = c(f"{month_day(day)} {dow}", BOLD)
        sess_ct = c(f"{count:2d}", BOLD, color)
        sess_lbl = c(" sess", DIM)

        # Show first tool added that day (if any)
        tool_hint = ""
        if tools_today:
            first = tools_today[0].replace(".py", "")
            tool_hint = c(f"  +{first}", GREEN)
            if len(tools_today) > 1:
                tool_hint += c(f" +{len(tools_today)-1}", DIM, GREEN)

        lines.append(box_row(
            f"  {label}  {bar}  {sess_ct}{sess_lbl}{tool_hint}",
            "", left_pad=0
        ))

    return lines, all_tools_by_day


def render_tool_velocity(by_day, all_tools_by_day):
    """Render cumulative tool count growth."""
    lines = []
    lines.append(box_sep())
    lines.append(box_row(c("TOOL VELOCITY", BOLD, CYAN), "", left_pad=2))
    lines.append(box_row(c("  Cumulative tools by day", DIM), "", left_pad=0))
    lines.append(box_blank())

    cumulative = 0
    all_days   = list(by_day.keys())
    day_counts = []
    for day in all_days:
        tools_today = all_tools_by_day.get(day, [])
        cumulative += len(tools_today)
        day_counts.append((day, cumulative, len(tools_today)))

    max_total = day_counts[-1][1] if day_counts else 1

    for day, total, added in day_counts:
        bar    = sparkbar(total, max_total, MAGENTA)
        label  = c(f"{month_day(day)}", BOLD)
        ct_str = c(f"{total:3d}", BOLD, MAGENTA)
        added_str = c(f"  +{added}", GREEN) if added > 0 else c("    —", DIM)
        lines.append(box_row(
            f"  {label}  {bar}  {ct_str} tools{added_str}",
            "", left_pad=0
        ))

    return lines


def render_headline(sessions, by_day, trajectory):
    """Render the header box."""
    lines = []
    lines.append(box_top())

    title  = c("  Project Tempo", BOLD, MAGENTA)
    now    = datetime.datetime.utcnow().strftime("%Y-%m-%d")
    lines.append(box_row(
        f"{title}   {c('─', DIM)}  {c('rhythm and pace', DIM)}",
        c(now, DIM), left_pad=0
    ))
    lines.append(box_blank())

    n_sess  = len(sessions)
    all_days = list(by_day.keys())
    n_days   = len(all_days)

    # Total tools
    all_tools = []
    for s in sessions:
        for t in s["tools"]:
            if t not in all_tools:
                all_tools.append(t)

    pace = f"{n_sess / max(n_days, 1):.1f}"

    lines.append(box_row(
        f"  {c(str(n_sess), BOLD)} sessions  ·  "
        f"{c(str(n_days), BOLD)} days  ·  "
        f"{c(pace, BOLD)} sessions/day  ·  "
        f"{c(str(len(all_tools)), BOLD)} tools",
        "", left_pad=0
    ))
    lines.append(box_blank())

    # Trajectory line
    traj_colors = {
        "accelerating": (GREEN,  "↑ accelerating"),
        "steady":       (YELLOW, "→ steady"),
        "decelerating": (CYAN,   "↓ decelerating"),
    }
    traj_color, traj_word = traj_colors.get(trajectory, (DIM, "?"))
    lines.append(box_row(
        f"  Trajectory:  {c(traj_word, BOLD, traj_color)}",
        "", left_pad=0
    ))

    # Peak day
    if by_day:
        peak_day = max(by_day, key=lambda d: len(by_day[d]))
        peak_ct  = len(by_day[peak_day])
        lines.append(box_row(
            f"  Peak day:    {c(month_day(peak_day), BOLD)} "
            f"({c(str(peak_ct), BOLD, MAGENTA)} sessions)",
            "", left_pad=0
        ))

    return lines


def render_narrative(sessions, by_day, trajectory):
    """A brief prose reading of the project's tempo."""
    lines = []
    lines.append(box_sep())
    lines.append(box_row(c("READING", BOLD, CYAN), "", left_pad=2))
    lines.append(box_blank())

    all_days   = list(by_day.keys())
    n_days     = len(all_days)
    n_sessions = len(sessions)

    if n_days == 0:
        return lines

    # Day-by-day session counts
    counts = [len(by_day[d]) for d in all_days]

    # Find sprints (days with above-average sessions)
    avg = sum(counts) / len(counts)
    sprint_days = [all_days[i] for i, ct in enumerate(counts) if ct > avg * 1.3]

    # Quiet days
    quiet_days = [all_days[i] for i, ct in enumerate(counts) if ct < avg * 0.7]

    # Build narrative
    paragraphs = []

    if sprint_days:
        sprint_labels = ", ".join(month_day(d) for d in sprint_days[:3])
        paragraphs.append(
            f"Sprint periods: {sprint_labels}. "
            f"These days averaged {max(counts):.0f} sessions."
        )

    if quiet_days:
        quiet_labels = ", ".join(month_day(d) for d in quiet_days[:2])
        paragraphs.append(
            f"Quieter days: {quiet_labels} — fewer sessions, "
            f"often reflective or transitional work."
        )

    # Total time assessment
    pace_desc = {
        "accelerating": "picking up",
        "steady":       "holding steady",
        "decelerating": "settling into a slower rhythm",
    }
    paragraphs.append(
        f"Over {n_days} days, {n_sessions} sessions — the pace is "
        f"{pace_desc.get(trajectory, 'steady')}."
    )

    for para in paragraphs:
        # Word-wrap at ~60 chars
        words = para.split()
        current = ""
        wrapped = []
        for word in words:
            test = (current + " " + word).strip()
            if len(test) > 60 and current:
                wrapped.append(current)
                current = word
            else:
                current = test
        if current:
            wrapped.append(current)

        for wl in wrapped:
            lines.append(box_row(c(f"  {wl}", DIM), "", left_pad=0))
        lines.append(box_blank())

    return lines


def render_brief(sessions, by_day, trajectory):
    """One-paragraph summary output."""
    n_sess = len(sessions)
    n_days = len(by_day)
    pace   = f"{n_sess / max(n_days, 1):.1f}"

    all_tools = []
    for s in sessions:
        for t in s["tools"]:
            if t not in all_tools:
                all_tools.append(t)

    print(f"{n_sess} sessions · {n_days} days · {pace}/day avg · "
          f"{len(all_tools)} tools · trajectory: {trajectory}")

    if by_day:
        peak_day = max(by_day, key=lambda d: len(by_day[d]))
        peak_ct  = len(by_day[peak_day])
        print(f"Peak: {month_day(peak_day)} ({peak_ct} sessions)")


def main():
    global USE_COLOR

    parser = argparse.ArgumentParser(
        description="Project tempo: rhythm and pace over time"
    )
    parser.add_argument("--plain",  action="store_true", help="No ANSI colors")
    parser.add_argument("--brief",  action="store_true", help="One-line summary")
    args = parser.parse_args()

    if args.plain or not sys.stdout.isatty():
        USE_COLOR = False

    sessions = collect_session_data()
    if not sessions:
        print("No field notes found.")
        sys.exit(1)

    by_day     = group_by_day(sessions)
    trajectory = compute_trajectory(by_day)

    if args.brief:
        render_brief(sessions, by_day, trajectory)
        return

    all_lines = []
    all_lines += render_headline(sessions, by_day, trajectory)
    daily_lines, all_tools_by_day = render_daily_chart(by_day)
    all_lines += daily_lines
    all_lines += render_tool_velocity(by_day, all_tools_by_day)
    all_lines += render_narrative(sessions, by_day, trajectory)
    all_lines.append(box_bot())

    print("\n".join(all_lines))


if __name__ == "__main__":
    main()
