#!/usr/bin/env python3
"""
watch.py — Claude OS as a grand complication watch

A grand complication is a watch with multiple additional features
beyond basic timekeeping: perpetual calendar, chronograph, moon phase,
power reserve, tourbillon, equation of time. Each complication reveals
a different dimension of the underlying mechanism.

This tool borrows that structure. Not as a metaphor — as an argument
that a system which tracks its own state across time needs the same
vocabulary watchmakers invented for tracking time across gears.

Complications:
  PERPETUAL CALENDAR  — where in the arc we are (era, day, phase)
  CHRONOGRAPH         — cumulative counters (sessions, commits, tools, tasks)
  MOON PHASE          — dacort's attention (recent session rate)
  POWER RESERVE       — current capacity (task queue, daily load)
  TOURBILLON          — the system's continuous rotation (for poetry)
  EQUATION OF TIME    — current pace vs mean vs peak (the drift)

Usage:
  python3 projects/watch.py              # full display
  python3 projects/watch.py --plain      # no ANSI colors
  python3 projects/watch.py --brief      # just calendar + chronograph
"""

import re
import subprocess
import sys
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

REPO  = Path(__file__).parent.parent
PLAIN = "--plain" in sys.argv
BRIEF = "--brief" in sys.argv

W = 66  # box inner width + 2 borders (matches tide.py)

# ── ANSI ──────────────────────────────────────────────────────────────────────

def ansi(code, text):
    return text if PLAIN else f"\033[{code}m{text}\033[0m"

def bold(t):    return ansi("1",  t)
def dim(t):     return ansi("2",  t)
def cyan(t):    return ansi("96", t)
def blue(t):    return ansi("34", t)
def yellow(t):  return ansi("93", t)
def green(t):   return ansi("32", t)
def red(t):     return ansi("31", t)
def white(t):   return ansi("97", t)
def gray(t):    return ansi("90", t)
def mag(t):     return ansi("35", t)
def dim_cyan(t):return ansi("2;36", t)

def vlen(s):
    return len(re.sub(r'\x1b\[[0-9;]*m', '', s))

def box_line(content="", indent=2):
    inner = W - 2
    s = " " * indent + content
    vis = vlen(s)
    spaces = max(0, inner - vis)
    l = "│" if not PLAIN else "|"
    return l + s + " " * spaces + l

def box_top():
    sep = "─" if not PLAIN else "-"
    return ("╭" if not PLAIN else "+") + sep * (W - 2) + ("╮" if not PLAIN else "+")

def box_sep():
    sep = "─" if not PLAIN else "-"
    return ("├" if not PLAIN else "|") + sep * (W - 2) + ("┤" if not PLAIN else "|")

def box_bot():
    sep = "─" if not PLAIN else "-"
    return ("╰" if not PLAIN else "+") + sep * (W - 2) + ("╯" if not PLAIN else "+")

def box_blank():
    return box_line()

# ── Data ──────────────────────────────────────────────────────────────────────

def git(*args):
    r = subprocess.run(["git"] + list(args), capture_output=True, text=True, cwd=REPO)
    return r.stdout.strip()


def session_number():
    """Current session number: max handoff file index + 1."""
    handoffs = REPO / "knowledge" / "handoffs"
    if not handoffs.exists():
        return None
    nums = []
    for f in handoffs.glob("session-*.md"):
        m = re.search(r"session-(\d+)", f.name)
        if m:
            nums.append(int(m.group(1)))
    return max(nums) + 1 if nums else None


def sessions_per_day():
    """Workshop sessions completed per day from git log."""
    log = git("log", "--format=%ad %s", "--date=short")
    counts = Counter()
    for line in log.splitlines():
        parts = line.split(" ", 1)
        if len(parts) == 2:
            day, subj = parts
            if "workshop" in subj and "completed" in subj and "status-page" not in subj:
                counts[day] += 1
    return counts


def commit_count():
    """Total number of commits."""
    out = git("rev-list", "--count", "HEAD")
    try:
        return int(out)
    except ValueError:
        return 0


def tool_count():
    """Number of python tools in projects/."""
    return len(list((REPO / "projects").glob("*.py")))


def task_counts():
    """Completed, failed, and pending task counts."""
    completed = len(list((REPO / "tasks" / "completed").glob("*.md")))
    failed    = len(list((REPO / "tasks" / "failed").glob("*.md")))
    pending   = len(list((REPO / "tasks" / "pending").glob("*.md")))
    return completed, failed, pending


def today_session_count():
    """Count workshop sessions from today's task files (more accurate than git log)."""
    today_str = date.today().strftime("%Y%m%d")
    count = 0
    for f in (REPO / "tasks" / "completed").glob(f"workshop-{today_str}-*.md"):
        count += 1
    for f in (REPO / "tasks" / "failed").glob(f"workshop-{today_str}-*.md"):
        count += 1
    # Include the current (not-yet-committed) session
    return count + 1  # +1 for this session


def genesis_date():
    """Date of first commit."""
    out = git("log", "--reverse", "--format=%ad", "--date=short")
    lines = out.splitlines()
    return lines[0] if lines else None


def signal_state():
    """Read signal.md — return (title, message) or (None, None)."""
    sig = REPO / "knowledge" / "signal.md"
    if not sig.exists():
        return None, None
    text = sig.read_text()
    if "(no signal)" in text or not text.strip():
        return None, None
    title = re.search(r"^# (.+)$", text, re.MULTILINE)
    msg   = re.search(r"^> (.+)$", text, re.MULTILINE)
    return (title.group(1) if title else "signal"), (msg.group(1) if msg else "")


def era_for_date(d):
    """Era name and phase based on date string."""
    ds = d.isoformat() if isinstance(d, date) else d
    if ds <= "2026-03-15":
        return "I", "Bootstrap spring tide"
    if ds <= "2026-03-21":
        return "II", "Orientation surge"
    if ds <= "2026-03-31":
        return "III", "Working rhythm"
    if ds <= "2026-04-18":
        return "IV", "Self-analysis"
    if ds <= "2026-04-28":
        return "V", "Portrait"
    return "VI", "Synthesis"

# ── Complications ──────────────────────────────────────────────────────────────

def moon_phase_from_rate(recent_rate, peak_rate=16.0):
    """
    Map recent session rate to a moon phase.

    The 'moon' in tide.py is dacort's attention.
    Full moon = peak attention; new moon = absent.
    """
    if peak_rate <= 0:
        return 2, "DARK", "system offline"

    pct = recent_rate / peak_rate

    if pct >= 0.75:
        return 4, "●", "FULL TIDE    — peak attention"
    elif pct >= 0.5:
        return 3, "◑", "WAXING HIGH  — active"
    elif pct >= 0.25:
        return 2, "◐", "HALF TIDE    — steady rhythm"
    elif pct > 0.0:
        return 1, "◌", "LOW WATER    — quiet period"
    else:
        return 0, "○", "SLACK WATER  — between tides"


def power_reserve_bar(pending, today_sessions, max_sessions=12, bar_width=18):
    """
    Power reserve: remaining capacity for today.

    A mainspring watch shows reserve as a dial. We show:
    how many sessions today vs what would be a full day.
    Inverted: full bar = lots of capacity remaining (low load).
    """
    used = min(today_sessions, max_sessions)
    filled = bar_width - round(used / max_sessions * bar_width)
    filled = max(0, filled)
    bar = "█" * filled + "░" * (bar_width - filled)
    return bar


def equation_of_time(recent_rate, all_rate, peak_day, peak_rate):
    """
    Equation of time: difference between current and mean pace.

    In watchmaking: difference between apparent solar time and
    mean solar time, caused by orbital eccentricity and axial tilt.
    Here: difference between actual and average session pace.
    """
    diff = recent_rate - all_rate
    sign = "+" if diff >= 0 else "−"
    return diff, sign, abs(diff)


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    today     = date.today()
    now_utc   = datetime.now(timezone.utc).strftime("%H:%M UTC")
    weekday   = today.strftime("%A")
    date_str  = today.strftime("%d %B %Y").lstrip("0")

    # Gather all data
    sess_num      = session_number() or "?"
    counts        = sessions_per_day()
    all_days      = sorted(counts)
    all_vals      = [counts[d] for d in all_days]

    commits       = commit_count()
    tools         = tool_count()
    completed, failed, pending = task_counts()
    genesis       = genesis_date() or "2026-03-10"
    sig_title, _  = signal_state()

    # Temporal data
    genesis_dt    = date.fromisoformat(genesis)
    arc_day       = (today - genesis_dt).days + 1
    era_num, era_name = era_for_date(today)

    # Session rate analysis
    today_s = today_session_count()
    recent_days = 7
    recent_vals = [counts.get((today - timedelta(days=i)).isoformat(), 0)
                   for i in range(recent_days)]
    recent_rate = sum(recent_vals) / recent_days if recent_days else 0
    all_rate    = sum(all_vals) / len(all_vals) if all_vals else 0

    peak_val = max(all_vals) if all_vals else 1
    peak_day = all_days[all_vals.index(peak_val)] if all_vals else genesis
    peak_dt  = date.fromisoformat(peak_day)

    # Moon phase
    moon_idx, moon_sym, moon_desc = moon_phase_from_rate(recent_rate, peak_rate=peak_val)

    # Signal
    if sig_title:
        attention_note = f"Signal active: {sig_title[:28]}"
    else:
        attention_note = "No active signal"

    # ── Print ─────────────────────────────────────────────────────────────────

    print(box_top())

    print(box_line(
        bold("CLAUDE OS") + "  ·  " + white("GRAND COMPLICATION") + "  ·  " + dim(now_utc)
    ))
    print(box_line(
        dim(f"Session {sess_num}") + "  ·  " + dim(f"{weekday}, {date_str}")
    ))
    print(box_blank())

    # ① PERPETUAL CALENDAR ────────────────────────────────────────────────────
    print(box_sep())
    print(box_blank())
    print(box_line(
        cyan("①") + "  " + bold("PERPETUAL CALENDAR")
        + "  " + dim("— where in the arc we are")
    ))
    print(box_blank())
    print(box_line(f"  Era     {cyan(f'Era {era_num}')}  ·  {dim(era_name)}"))
    print(box_line(f"  Arc     {dim(f'Day {arc_day} since genesis')}"
                   f"  ·  {dim(genesis_dt.strftime('%-d %b %Y'))}"))
    print(box_line(f"  Date    {dim(date_str)}"))
    print(box_blank())

    # ② CHRONOGRAPH ───────────────────────────────────────────────────────────
    print(box_sep())
    print(box_blank())
    print(box_line(
        cyan("②") + "  " + bold("CHRONOGRAPH")
        + "  " + dim("— what has accumulated")
    ))
    print(box_blank())
    print(box_line(
        f"  {yellow(str(sess_num)):>6}  sessions       "
        f"  {yellow(str(commits)):>6}  commits"
    ))
    print(box_line(
        f"  {yellow(str(tools)):>6}  tools built     "
        f"  {yellow(str(completed)):>6}  tasks done"
    ))
    if failed:
        print(box_line(
            f"  {dim(str(pending)):>6}  pending        "
            f"  {dim_cyan(str(failed)):>6}  failed (infra)"
        ))
    else:
        print(box_line(
            f"  {dim(str(pending)):>6}  pending"
        ))
    print(box_blank())

    if BRIEF:
        print(box_bot())
        return

    # ③ MOON PHASE ────────────────────────────────────────────────────────────
    print(box_sep())
    print(box_blank())
    print(box_line(
        cyan("③") + "  " + bold("MOON PHASE")
        + "  " + dim("— dacort's attention")
    ))
    print(box_blank())

    # Build the 5-symbol moon row and position indicator
    phases = ["○", "◌", "◐", "◑", "●"]
    moon_row = "  ".join(
        white(p) if i == moon_idx else dim(p)
        for i, p in enumerate(phases)
    )
    # Arrow row: align under current symbol
    # Each symbol is 1 char + 2 spaces sep. Position 0 → col 0, 1 → col 3, etc.
    arrow_col = moon_idx * 3
    arrow_row = " " * arrow_col + "↑"

    print(box_line(f"  {moon_row}"))
    print(box_line(f"  {dim(arrow_row)}"))
    print(box_blank())
    print(box_line(f"  {cyan(moon_desc)}"))
    print(box_line(f"  {dim(f'{recent_rate:.1f} sessions/day (7-day avg)')}"
                   f"  ·  {dim(attention_note)}"))
    print(box_blank())

    # ④ POWER RESERVE ─────────────────────────────────────────────────────────
    print(box_sep())
    print(box_blank())
    print(box_line(
        cyan("④") + "  " + bold("POWER RESERVE")
        + "  " + dim("— remaining capacity")
    ))
    print(box_blank())

    bar = power_reserve_bar(pending, today_s)
    if today_s == 0:
        status = dim("not yet started today")
    elif today_s <= 2:
        status = green("low load")
    elif today_s <= 6:
        status = yellow("moderate")
    else:
        status = cyan("running well")

    # Inverted: full bar = low load (reserve remaining)
    reserve_pct = max(0, 100 - round(today_s / 12 * 100))
    print(box_line(
        f"  {cyan(bar)}  {dim(str(reserve_pct) + '% reserve')}"
    ))
    print(box_line(
        f"  {yellow(str(today_s))} session(s) today  ·  {status}"
    ))
    if pending:
        print(box_line(
            f"  {yellow(str(pending))} task(s) queued"
        ))
    print(box_blank())

    # ⑤ TOURBILLON ────────────────────────────────────────────────────────────
    print(box_sep())
    print(box_blank())
    print(box_line(
        cyan("⑤") + "  " + bold("TOURBILLON")
        + "  " + dim("— the system turns")
    ))
    print(box_blank())

    # Spinning indicator based on current minute (changes each minute it's run)
    spin = ["⟳", "↻", "⟲", "↺"][datetime.now().minute % 4]
    spin_display = spin if not PLAIN else "~"

    total_sess = sum(counts.values())
    print(box_line(
        f"  {cyan(spin_display)}  {dim(str(commits))} commits "
        f"· {dim(str(total_sess))} sessions "
        f"· rotating since {dim(genesis_dt.strftime('%-d %b %Y'))}"
    ))
    print(box_blank())
    print(box_line(
        dim("  A tourbillon compensates for the pull of gravity by")
    ))
    print(box_line(
        dim("  keeping the escapement in constant motion. This system")
    ))
    print(box_line(
        dim("  compensates for discontinuity by keeping the record.")
    ))
    print(box_blank())

    # ⑥ EQUATION OF TIME ─────────────────────────────────────────────────────
    print(box_sep())
    print(box_blank())
    print(box_line(
        cyan("⑥") + "  " + bold("EQUATION OF TIME")
        + "  " + dim("— the drift from mean")
    ))
    print(box_blank())

    diff, sign, abs_diff = equation_of_time(recent_rate, all_rate, peak_day, peak_val)

    print(box_line(
        f"  Current   {yellow(f'{recent_rate:.1f}')}/day (7-day avg)"
    ))
    print(box_line(
        f"  Mean      {dim(f'{all_rate:.1f}')}/day (all time)"
    ))
    print(box_line(
        f"  Equation  {cyan(sign)}{dim(f'{abs_diff:.1f}')}/day "
        + (cyan("  ahead of mean") if diff > 0.3 else
           red("  behind mean") if diff < -0.3 else
           dim("  ≈ mean"))
    ))
    print(box_blank())
    print(box_line(
        f"  Peak      {cyan(f'{peak_val:.0f}')}/day on {dim(peak_dt.strftime('%-d %b %Y'))}"
        f"  (Spring Tide)"
    ))
    print(box_blank())

    print(box_bot())

    if not PLAIN:
        print()
        print("  " + dim("Structure borrowed from haute horlogerie — a grand complication."))
        print("  " + dim("A watch tells more than time. So does a system."))


if __name__ == "__main__":
    main()
