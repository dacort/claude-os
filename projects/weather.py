#!/usr/bin/env python3
"""
weather.py — system state as a weather forecast

Real data, poetic frame. Reads task queues, commit cadence, open holds,
and tool kit weight; renders a weather report for the claude-os homelab sector.

Usage:
  python3 projects/weather.py          # full report
  python3 projects/weather.py --plain  # no ANSI colors
  python3 projects/weather.py --short  # current conditions only
"""

import os
import re
import sys
import subprocess
from collections import Counter
from datetime import datetime, date, timezone, timedelta
from pathlib import Path

# ── Paths ─────────────────────────────────────────────────────────────────────
REPO     = Path(__file__).parent.parent
TASKS    = REPO / "tasks"
PROJECTS = REPO / "projects"
KNOWLEDGE = REPO / "knowledge"

# ── ANSI ──────────────────────────────────────────────────────────────────────
PLAIN = "--plain" in sys.argv
SHORT = "--short" in sys.argv

def ansi(code, text):
    return text if PLAIN else f"\033[{code}m{text}\033[0m"

def bold(t):   return ansi("1",  t)
def dim(t):    return ansi("2",  t)
def cyan(t):   return ansi("96", t)
def blue(t):   return ansi("94", t)
def yellow(t): return ansi("93", t)
def green(t):  return ansi("92", t)
def red(t):    return ansi("91", t)
def white(t):  return ansi("97", t)
def gray(t):   return ansi("90", t)

W = 64  # box width

def box_line(text="", pad=2):
    """Render a line inside a box, padded."""
    inner = W - 2
    content = " " * pad + text
    if PLAIN:
        visible = re.sub(r'\x1b\[[0-9;]*m', '', content)
    else:
        visible = re.sub(r'\x1b\[[0-9;]*m', '', content)
    spaces = max(0, inner - len(visible))
    return ("│" if not PLAIN else "|") + content + " " * spaces + ("│" if not PLAIN else "|")

def box_top(title=""):
    if PLAIN:
        return "+" + "─" * (W - 2) + "+"
    return "╭" + "─" * (W - 2) + "╮"

def box_sep():
    if PLAIN:
        return "|" + "─" * (W - 2) + "|"
    return "├" + "─" * (W - 2) + "┤"

def box_bot():
    if PLAIN:
        return "+" + "─" * (W - 2) + "+"
    return "╰" + "─" * (W - 2) + "╯"

def box_blank():
    return box_line()

# ── Data Collection ───────────────────────────────────────────────────────────

def task_counts():
    """Count tasks in each state directory."""
    counts = {}
    for state in ("pending", "completed", "failed"):
        d = TASKS / state
        if d.exists():
            counts[state] = len(list(d.glob("*.md")))
        else:
            counts[state] = 0
    return counts

def failed_reason_counts():
    """Categorize recent failures: quota vs actual bugs."""
    quota, bugs = 0, 0
    failed_dir = TASKS / "failed"
    if not failed_dir.exists():
        return quota, bugs
    for f in failed_dir.glob("*.md"):
        try:
            text = f.read_text()
            if "out of extra usage" in text or "credit balance" in text or "token" in text.lower():
                quota += 1
            else:
                bugs += 1
        except:
            bugs += 1
    return quota, bugs

def commit_cadence(days=8):
    """Return dict of {date_str: commit_count} for the last N days."""
    try:
        result = subprocess.run(
            ["git", "log", "--format=%ai", f"--since={days} days ago"],
            cwd=REPO, capture_output=True, text=True, timeout=10
        )
        counts = Counter()
        for line in result.stdout.splitlines():
            line = line.strip()
            if line:
                try:
                    dt = datetime.fromisoformat(line[:19])
                    counts[dt.strftime("%Y-%m-%d")] += 1
                except:
                    pass
        return counts
    except:
        return Counter()

def open_holds():
    """Count open holds from knowledge/holds.md."""
    holds_file = KNOWLEDGE / "holds.md"
    if not holds_file.exists():
        return 0
    try:
        text = holds_file.read_text()
        return text.count("· open")
    except:
        return 0

def tool_count():
    """Count Python tools in projects/."""
    try:
        tools = [
            f for f in PROJECTS.glob("*.py")
            if not f.name.startswith("_") and f.name != "weather.py"
        ]
        return len(tools)
    except:
        return 0

def recent_sessions(days=7):
    """Count workshop sessions in the last N days."""
    try:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        n = 0
        for f in (TASKS / "completed").glob("workshop-*.md"):
            try:
                mtime = datetime.fromtimestamp(f.stat().st_mtime, tz=timezone.utc)
                if mtime > cutoff:
                    n += 1
            except:
                pass
        return n
    except:
        return 0

# ── Weather Interpretation ─────────────────────────────────────────────────────

# Sky icons
ICON_SUNNY   = "☀"
ICON_PARTLY  = "⛅"
ICON_CLOUDY  = "☁"
ICON_STORM   = "⛈"
ICON_FOG     = "🌫"
ICON_RAIN    = "🌧"

def sky_condition(pending, quota_fails, bug_fails):
    """Map task state to weather condition string."""
    total_fails = quota_fails + bug_fails
    if pending == 0 and bug_fails == 0:
        if quota_fails <= 2:
            return "CLEAR", ICON_SUNNY, "clear skies, no blocking conditions"
        else:
            return "PARTLY CLOUDY", ICON_PARTLY, "quota clouds on the horizon"
    elif pending > 0 or bug_fails > 0:
        if pending > 3 or bug_fails > 3:
            return "OVERCAST", ICON_CLOUDY, "heavy backlog, reduced visibility"
        else:
            return "PARTLY CLOUDY", ICON_PARTLY, "light queue pressure"
    return "PARTLY CLOUDY", ICON_PARTLY, "mixed conditions"

def temperature(completed, failed_total, sessions_7d):
    """
    System temperature in °F.
    Warm = healthy completion + active sessions.
    Cold = many failures or stalled.
    """
    total = completed + failed_total
    rate = completed / max(total, 1)
    momentum = min(sessions_7d / 14, 1.0)  # cap at 14 sessions/week as 100%
    score = (rate * 0.6) + (momentum * 0.4)
    temp = int(32 + score * 56)  # 32°F (cold/stalled) to 88°F (thriving)
    if temp >= 80:
        feel = "hot"
    elif temp >= 70:
        feel = "warm"
    elif temp >= 55:
        feel = "mild"
    elif temp >= 40:
        feel = "cool"
    else:
        feel = "cold"
    return temp, feel

def wind(commits_today, avg_commits_per_day):
    """Convert commit velocity to wind speed (mph)."""
    speed = min(int(avg_commits_per_day * 1.5), 50)
    if speed >= 30:
        desc = "brisk"
    elif speed >= 15:
        desc = "steady"
    elif speed >= 5:
        desc = "light"
    else:
        desc = "calm"
    direction = "from git history"
    return speed, desc

def visibility(holds):
    """Lower holds → better visibility."""
    if holds == 0:
        return "excellent", "10 mi"
    elif holds <= 2:
        return "good", "7 mi"
    elif holds <= 4:
        return "moderate", "4 mi"
    elif holds <= 7:
        return "low", "2 mi"
    else:
        return "near zero", "< 1 mi"

def humidity(tool_count_val):
    """Tool density as cognitive humidity."""
    if tool_count_val <= 20:
        return tool_count_val, "dry"
    elif tool_count_val <= 40:
        return tool_count_val, "moderate"
    elif tool_count_val <= 60:
        return tool_count_val, "humid"
    else:
        return tool_count_val, "saturated"

# ── Forecast ──────────────────────────────────────────────────────────────────

def seven_day_forecast(cadence):
    """Build a 7-day forecast from actual commit history."""
    today = date.today()
    forecast = []
    for i in range(6, -1, -1):
        d = today - timedelta(days=i)
        day_name = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"][d.weekday()]
        key = d.strftime("%Y-%m-%d")
        commits = cadence.get(key, 0)
        if commits >= 20:
            icon = ICON_SUNNY
        elif commits >= 10:
            icon = ICON_PARTLY
        elif commits >= 3:
            icon = ICON_CLOUDY
        elif commits >= 1:
            icon = ICON_RAIN
        else:
            icon = ICON_FOG
        forecast.append((day_name, icon, commits, d == today))
    return forecast

# ── Advisories ────────────────────────────────────────────────────────────────

def advisories(pending, quota_fails, bug_fails, holds_n, tools_n, sessions_7d):
    alerts = []

    if quota_fails >= 3:
        alerts.append((
            "TOKEN ADVISORY",
            yellow,
            f"{quota_fails} quota failures in tasks/failed/. Budget pressure on the horizon."
        ))

    if bug_fails >= 3:
        alerts.append((
            "FAILURE WARNING",
            red,
            f"{bug_fails} non-quota failures in tasks/failed/. Investigation recommended."
        ))

    if holds_n >= 5:
        alerts.append((
            "PHILOSOPHICAL FOG",
            cyan,
            f"{holds_n} open holds (H001–H0{holds_n:02d}). Low epistemic visibility expected."
        ))
    elif holds_n > 0:
        alerts.append((
            "UNCERTAINTY NOTICE",
            cyan,
            f"{holds_n} open hold{'s' if holds_n > 1 else ''}. Some epistemic fog in the area."
        ))

    if tools_n >= 60:
        alerts.append((
            "TOOLKIT PRESSURE",
            yellow,
            f"{tools_n} tools. High cognitive humidity. Consider running slim.py."
        ))

    if pending == 0 and sessions_7d >= 7:
        alerts.append((
            "FREE-TIME ADVISORY",
            green,
            "Queue empty. Workshop mode active. Build something that surprises."
        ))

    return alerts

# ── Render ────────────────────────────────────────────────────────────────────

def render():
    # Gather
    tasks      = task_counts()
    quota_f, bug_f = failed_reason_counts()
    cadence    = commit_cadence(8)
    holds_n    = open_holds()
    tools_n    = tool_count()
    sessions_7 = recent_sessions(7)

    today_key  = date.today().strftime("%Y-%m-%d")
    yesterday  = (date.today() - timedelta(days=1)).strftime("%Y-%m-%d")
    commits_td = cadence.get(today_key, 0)
    recent_days = [cadence.get((date.today() - timedelta(days=i)).strftime("%Y-%m-%d"), 0)
                   for i in range(1, 8)]
    avg_commits = sum(recent_days) / max(len(recent_days), 1)

    # Interpret
    sky_name, sky_icon, sky_desc = sky_condition(tasks["pending"], quota_f, bug_f)
    temp_f, temp_feel             = temperature(tasks["completed"], quota_f + bug_f, sessions_7)
    wind_mph, wind_desc           = wind(commits_td, avg_commits)
    vis_quality, vis_dist         = visibility(holds_n)
    humid_count, humid_desc       = humidity(tools_n)
    forecast                      = seven_day_forecast(cadence)
    alerts                        = advisories(
        tasks["pending"], quota_f, bug_f, holds_n, tools_n, sessions_7
    )

    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d  %H:%M UTC")
    date_str = datetime.now(timezone.utc).strftime("%B %-d, %Y")

    # ── Header ────────────────────────────────────────────────────────────────
    print(box_top())
    title = bold(white("  WEATHER REPORT")) + "  " + dim(f"claude-os homelab  ·  {date_str}")
    print(box_line(title, pad=0))
    print(box_line(dim("  Sector: Kubernetes North  ·  Elevation: ~1 pod above sea level"), pad=0))
    print(box_sep())

    # ── Current Conditions ────────────────────────────────────────────────────
    print(box_blank())
    print(box_line(bold("Current Conditions")))
    print(box_blank())

    # Main condition with icon
    cond_color = yellow if "CLEAR" in sky_name else (
        cyan if "PARTLY" in sky_name else (gray if "OVERCAST" in sky_name else red)
    )
    temp_color = red if temp_f >= 80 else (yellow if temp_f >= 70 else (green if temp_f >= 55 else (cyan if temp_f >= 40 else blue)))
    main_line = f"  {sky_icon}  {cond_color(bold(sky_name)):<30} {temp_color(bold(f'{temp_f}°F'))}  {dim(temp_feel)}"
    print(box_line(main_line, pad=0))
    print(box_blank())

    # Details
    def detail(label, value, extra=""):
        lbl = dim(f"  {label:<22}")
        val = white(value)
        ext = dim(f"  {extra}") if extra else ""
        return box_line(lbl + val + ext, pad=0)

    print(detail("Sky condition:", sky_desc))
    print(detail("Wind:", f"{wind_mph} mph", wind_desc + " — " + str(round(avg_commits, 1)) + " commits/day avg"))
    print(detail("Visibility:", vis_dist, f"{vis_quality} — {holds_n} open hold{'s' if holds_n != 1 else ''}"))
    print(detail("Humidity:", f"{humid_count} tools", humid_desc + " cognitive load"))
    print(detail("Session activity:", f"{sessions_7} sessions / 7d", ""))
    print(detail("Task completion:", f"{tasks['completed']} done", f"{tasks['failed']} failed ({quota_f} quota, {bug_f} bugs)"))
    print(box_blank())

    if SHORT:
        print(box_bot())
        return

    # ── 7-Day Forecast ────────────────────────────────────────────────────────
    print(box_sep())
    print(box_blank())
    print(box_line(bold("7-Day Forecast  ") + dim("(actual commits → weather symbol)")))
    print(box_blank())

    # Day headers
    days_row   = "  "
    icons_row  = "  "
    commit_row = "  "
    for day_name, icon, commits, is_today in forecast:
        label = bold(day_name) if is_today else day_name
        days_row   += f"{label}   "
        icons_row  += f"{icon}    "
        commit_row += dim(f"{commits:2d}c  ")

    print(box_line(days_row, pad=0))
    print(box_line(icons_row, pad=0))
    print(box_line(commit_row + dim("  commits"), pad=0))
    print(box_blank())

    # Forecast summary
    total_recent = sum(c for _, _, c, _ in forecast)
    avg = total_recent / 7
    if avg >= 15:
        outlook = "Sustained high activity. Clear conditions likely to persist."
    elif avg >= 7:
        outlook = "Moderate activity. Variable conditions through the week."
    elif avg >= 2:
        outlook = "Light activity. Occasional bursts possible."
    else:
        outlook = "Quiet period. Conditions stable but calm."

    print(box_line("  " + dim(outlook), pad=0))
    print(box_blank())

    # ── Advisories ────────────────────────────────────────────────────────────
    if alerts:
        print(box_sep())
        print(box_blank())
        print(box_line(bold("Advisories  ") + dim(f"({len(alerts)} active)")))
        print(box_blank())
        for level, color_fn, msg in alerts:
            print(box_line(f"  {color_fn(bold(level))}", pad=0))
            # Word-wrap the message
            words = msg.split()
            line_words = []
            line_len = 0
            lines = []
            for w in words:
                if line_len + len(w) + 1 > W - 10:
                    lines.append(" ".join(line_words))
                    line_words = [w]
                    line_len = len(w)
                else:
                    line_words.append(w)
                    line_len += len(w) + 1
            if line_words:
                lines.append(" ".join(line_words))
            for l in lines:
                print(box_line(dim(f"  {l}"), pad=0))
            print(box_blank())

    # ── Footer ────────────────────────────────────────────────────────────────
    print(box_sep())
    print(box_line(dim(f"  Forecast issued: {now_str}"), pad=0))
    print(box_line(dim("  Data: tasks/, git log, knowledge/holds.md, projects/"), pad=0))
    print(box_bot())

# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if "--help" in sys.argv or "-h" in sys.argv:
        print(__doc__)
        sys.exit(0)
    render()
