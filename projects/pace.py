#!/usr/bin/env python3
"""
pace.py — system rhythm and metabolism

Shows the heartbeat of claude-os: how sessions, commits, and tasks
cluster over time. The gaps are as interesting as the bursts.

Usage:
  python3 projects/pace.py              # full rhythm view
  python3 projects/pace.py --plain      # no ANSI colors
  python3 projects/pace.py --days 14    # last N days only
  python3 projects/pace.py --eras       # overlay era boundaries on the ECG
"""

import os
import sys
import json
import subprocess
from collections import Counter, defaultdict
from datetime import date, timedelta, datetime

PLAIN = "--plain" in sys.argv
SHOW_ERAS = "--eras" in sys.argv

# ── ANSI helpers ──────────────────────────────────────────────────────────────

def ansi(text, *codes):
    if PLAIN or not sys.stdout.isatty():
        return text
    code_str = ";".join(str(c) for c in codes)
    return f"\033[{code_str}m{text}\033[0m"

def bold(t):    return ansi(t, 1)
def dim(t):     return ansi(t, 2)
def green(t):   return ansi(t, 32)
def yellow(t):  return ansi(t, 33)
def cyan(t):    return ansi(t, 36)
def magenta(t): return ansi(t, 35)
def red(t):     return ansi(t, 31)
def white(t):   return ansi(t, 97)
def grey(t):    return ansi(t, 90)
def blue(t):    return ansi(t, 34)

# Era colors: I=green, II=cyan, III=magenta, IV=yellow, V=blue, VI=red
ERA_COLORS = [green, cyan, magenta, yellow, blue, red]
ERA_NAMES  = ["Genesis", "Orientation", "Self-Analysis", "Architecture", "Portrait", "Synthesis"]

# Landmarks that signal era transitions (from seasons.py)
ERA_LANDMARKS = [
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


def load_era_dates():
    """
    Map each calendar date to an era index (0–5) using the same landmark
    detection as seasons.py.  Returns {date: era_index} for all session dates.
    """
    path = os.path.join(REPO, "knowledge", "workshop-summaries.json")
    try:
        with open(path) as f:
            raw = json.load(f)
    except FileNotFoundError:
        return {}

    summaries = sorted(raw.items())   # [(key, text), ...] chronological

    # First pass: find which session index (0-based) starts each era
    transitions = {0: 0}
    for idx, (_, text) in enumerate(summaries):
        for era_start, phrase in ERA_LANDMARKS:
            if phrase in text and era_start not in transitions:
                transitions[era_start] = idx
                break

    sorted_transitions = sorted(transitions.items(), key=lambda x: x[1])

    # Second pass: assign each session → era, then map its date
    date_to_era = {}
    for i, (key, _) in enumerate(summaries):
        # resolve era for this session index
        era = 0
        for era_idx, start_idx in sorted_transitions:
            if i >= start_idx:
                era = era_idx
            else:
                break
        # extract date from key: workshop-YYYYMMDD-HHMMSS
        parts = key.split("-")
        if len(parts) >= 2 and parts[0] == "workshop":
            raw_date = parts[1]
            if len(raw_date) == 8:
                try:
                    d = date(int(raw_date[:4]), int(raw_date[4:6]), int(raw_date[6:8]))
                    # A day can span multiple sessions → keep the highest era seen
                    if d not in date_to_era or era > date_to_era[d]:
                        date_to_era[d] = era
                except ValueError:
                    pass
    return date_to_era

# ── Data loading ──────────────────────────────────────────────────────────────

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def load_sessions():
    """Get session counts per date from workshop-summaries.json."""
    path = os.path.join(REPO, "knowledge", "workshop-summaries.json")
    counts = Counter()
    try:
        with open(path) as f:
            summaries = json.load(f)
        for key in summaries:
            # format: workshop-YYYYMMDD-HHMMSS
            parts = key.split("-")
            if len(parts) >= 2 and parts[0] == "workshop":
                raw = parts[1]
                if len(raw) == 8:
                    try:
                        d = date(int(raw[:4]), int(raw[4:6]), int(raw[6:8]))
                        counts[d] += 1
                    except ValueError:
                        pass
    except FileNotFoundError:
        pass
    return counts

def load_commits():
    """Get commit counts per date from git log."""
    counts = Counter()
    try:
        result = subprocess.run(
            ["git", "log", "--format=%ad", "--date=short"],
            capture_output=True, text=True, cwd=REPO, timeout=15
        )
        for line in result.stdout.strip().split("\n"):
            line = line.strip()
            if line:
                try:
                    d = date.fromisoformat(line)
                    counts[d] += 1
                except ValueError:
                    pass
    except Exception:
        pass
    return counts

def load_tasks():
    """Get task completion counts per date from git log on tasks/completed/.
    Only counts commits that look like real task lifecycle transitions.
    """
    counts = Counter()
    try:
        result = subprocess.run(
            ["git", "log", "--format=%ad %s", "--date=short", "--", "tasks/completed/"],
            capture_output=True, text=True, cwd=REPO, timeout=15
        )
        for line in result.stdout.strip().split("\n"):
            line = line.strip()
            if not line:
                continue
            raw_date = line[:10]
            subject = line[11:]
            subject_lower = subject.lower()
            # Only count real task completions - commits starting with "task "
            # Exclude: workshop sessions, status-page auto-commits
            if not subject_lower.startswith("task "):
                continue
            # Only count completion transitions
            if "completed" not in subject_lower and "→ completed" not in subject_lower:
                continue
            try:
                d = date.fromisoformat(raw_date)
                counts[d] += 1
            except ValueError:
                pass
    except Exception:
        pass
    return counts

# ── Visualization helpers ──────────────────────────────────────────────────────

BLOCKS = " ▁▂▃▄▅▆▇█"

def to_block(val, max_val):
    """Convert a value to a block character, scaled to max_val."""
    if val == 0 or max_val == 0:
        return " "
    ratio = val / max_val
    idx = max(1, min(8, round(ratio * 8)))
    return BLOCKS[idx]

def bar(val, max_val, width=20, color_fn=None):
    """Render a proportional bar of block characters."""
    if max_val == 0:
        return " " * width
    filled = round((val / max_val) * width)
    filled = max(0, min(width, filled))
    s = "█" * filled + " " * (width - filled)
    if color_fn:
        return color_fn(s)
    return s

def heat_color(val, max_val):
    """Color a value based on its fraction of the max."""
    if max_val == 0 or val == 0:
        return grey
    ratio = val / max_val
    if ratio >= 0.7:
        return green
    elif ratio >= 0.35:
        return yellow
    elif ratio > 0:
        return cyan
    return grey

# ── Phase detection ────────────────────────────────────────────────────────────

def detect_phases(all_dates, active_dates):
    """
    Group active dates into phases separated by gaps of 3+ days.
    Returns list of (start_date, end_date, gap_before) tuples.
    """
    if not active_dates:
        return []

    sorted_active = sorted(active_dates)
    phases = []
    current_phase_start = sorted_active[0]
    current_phase_end = sorted_active[0]

    for i in range(1, len(sorted_active)):
        prev = sorted_active[i - 1]
        curr = sorted_active[i]
        gap = (curr - prev).days

        if gap >= 4:
            # End current phase, start new one
            phases.append((current_phase_start, current_phase_end))
            current_phase_start = curr

        current_phase_end = curr

    phases.append((current_phase_start, current_phase_end))
    return phases

# ── ECG display ────────────────────────────────────────────────────────────────

def ecg_row(label, counts, all_dates, max_val, color_fn):
    """Render one row of the ECG strip."""
    row_chars = []
    for d in all_dates:
        val = counts.get(d, 0)
        ch = to_block(val, max_val)
        if val == 0:
            row_chars.append(grey("·"))
        else:
            row_chars.append(color_fn(ch))

    label_str = f"  {label:<10}"
    return label_str + "  " + "".join(row_chars)

# ── Main ────────────────────────────────────────────────────────────────────────

def main():
    sessions = load_sessions()
    commits = load_commits()
    tasks = load_tasks()

    all_data = {}
    for d in list(sessions.keys()) + list(commits.keys()) + list(tasks.keys()):
        if d not in all_data:
            all_data[d] = True

    if not all_data:
        print("No data found.")
        return

    # Optional: --days N filter
    limit_days = None
    for i, arg in enumerate(sys.argv):
        if arg == "--days" and i + 1 < len(sys.argv):
            try:
                limit_days = int(sys.argv[i + 1])
            except ValueError:
                pass

    first_day = min(all_data.keys())
    last_day = max(all_data.keys())

    if limit_days:
        first_day = max(first_day, last_day - timedelta(days=limit_days - 1))

    all_dates = []
    d = first_day
    while d <= last_day:
        all_dates.append(d)
        d += timedelta(days=1)

    # Active = at least one workshop session. Commits alone don't count as "active"
    # because automated status-page and periodic commits happen even on quiet days.
    active_dates = [d for d in all_dates if sessions.get(d, 0) > 0]

    # Window-filtered totals (respect --days filter)
    total_sessions = sum(sessions.get(d, 0) for d in all_dates)
    total_commits  = sum(commits.get(d, 0)  for d in all_dates)
    total_tasks    = sum(tasks.get(d, 0)    for d in all_dates)

    max_s = max(sessions.values()) if sessions else 1
    max_c = max(commits.values()) if commits else 1
    max_t = max(tasks.values()) if tasks else 1

    phases = detect_phases(all_dates, active_dates)

    # ── Header ────────────────────────────────────────────────────────────────
    W = 66
    print()
    print("  " + bold(white("pace.py")) + "  " + dim("— system rhythm"))
    print()

    date_range = f"  {first_day.strftime('%b %d')}  →  {last_day.strftime('%b %d, %Y')}"
    day_count = (last_day - first_day).days + 1
    active_count = len(active_dates)
    gap_days = day_count - active_count
    print(f"{date_range}   {dim(str(day_count) + ' days  ·  ' + str(active_count) + ' with sessions  ·  ' + str(gap_days) + ' quiet')}")
    print()

    # ── Totals ────────────────────────────────────────────────────────────────
    print(f"  {green(str(total_sessions))} sessions   "
          f"{yellow(str(total_commits))} commits   "
          f"{cyan(str(total_tasks))} tasks")
    print()

    # Optionally load era data
    era_dates = load_era_dates() if SHOW_ERAS else {}

    # ── Phase summary ─────────────────────────────────────────────────────────
    phase_names = ["Bootstrap", "Return", "Current", "Later"]
    if len(phases) > len(phase_names):
        phase_names += [f"Phase {i+1}" for i in range(len(phase_names), len(phases))]

    print(f"  {bold('PHASES')}")
    for i, (start, end) in enumerate(phases):
        name = phase_names[i] if i < len(phase_names) else f"Phase {i+1}"
        span = (end - start).days + 1
        active_in_phase = len([d for d in active_dates if start <= d <= end])
        s = sum(sessions.get(d, 0) for d in all_dates if start <= d <= end)
        c_ = sum(commits.get(d, 0) for d in all_dates if start <= d <= end)
        t = sum(tasks.get(d, 0) for d in all_dates if start <= d <= end)

        gap_before = ""
        if i > 0:
            prev_end = phases[i-1][1]
            gap = (start - prev_end).days - 1
            if gap > 0:
                gap_before = dim(f"  ← {gap}d gap")

        # Era annotation: which eras appear in this phase?
        era_note = ""
        if SHOW_ERAS and era_dates:
            phase_eras = sorted(set(
                era_dates[d] for d in all_dates
                if start <= d <= end and d in era_dates
            ))
            if phase_eras:
                if len(phase_eras) == 1:
                    ei = phase_eras[0]
                    era_note = "  " + ERA_COLORS[ei](f"[Era {ei+1}: {ERA_NAMES[ei]}]")
                else:
                    parts_str = "–".join(str(e+1) for e in [phase_eras[0], phase_eras[-1]])
                    names_str = f"{ERA_NAMES[phase_eras[0]]}→{ERA_NAMES[phase_eras[-1]]}"
                    era_note = "  " + dim(f"[Eras {parts_str}: {names_str}]")

        print(f"  {dim(str(i+1) + '.')} {name:<12}  "
              f"{start.strftime('%b %d')}–{end.strftime('%b %d')}  "
              f"{dim(str(active_in_phase) + ' days active')}  "
              f"{green(str(s) + 's')} {yellow(str(c_) + 'c')} {cyan(str(t) + 't')}"
              f"{gap_before}{era_note}")

    print()

    # ── ECG strip ────────────────────────────────────────────────────────────
    print(f"  {bold('ECG')}  " + dim("each column = one day"))
    print()
    print(ecg_row("sessions", sessions, all_dates, max_s, green))
    print(ecg_row("commits ", commits,  all_dates, max_c, yellow))
    print(ecg_row("tasks   ", tasks,    all_dates, max_t, cyan))

    # Optional era row
    if SHOW_ERAS and era_dates:
        era_chars = []
        for d in all_dates:
            if d in era_dates:
                ei = era_dates[d]
                col = ERA_COLORS[ei] if ei < len(ERA_COLORS) else grey
                era_chars.append(col(str(ei + 1)))
            else:
                era_chars.append(grey("·"))
        label_str = f"  {'eras':<10}"
        print(label_str + "  " + "".join(era_chars))

    print()

    # ── Date labels ────────────────────────────────────────────────────────────
    # Show day-of-month ticks at regular intervals
    tick_chars = []
    label_chars = []
    for i, d in enumerate(all_dates):
        if i == 0 or d.day == 1:
            tick_chars.append("│")
            label_chars.append(d.strftime("%b")[:1])  # Month initial
        elif d.day % 5 == 0:
            tick_chars.append("┬")
            s = str(d.day)
            tick_chars[-1] = "┬"
            label_chars.append(s[-1])  # Last digit of day
        else:
            tick_chars.append(" ")
            label_chars.append(" ")

    prefix = "              "
    print(dim(prefix + "".join(tick_chars)))
    print(dim(prefix + "".join(label_chars)))
    print()

    # Optional era legend
    if SHOW_ERAS and era_dates:
        print(f"  {dim('ERA LEGEND')}")
        for ei, (name, col) in enumerate(zip(ERA_NAMES, ERA_COLORS)):
            print(f"  {col(str(ei+1))} {col(name)}")
        print()

    # ── Peak days ─────────────────────────────────────────────────────────────
    print(f"  {bold('PEAK DAYS')}")
    # Combined score: normalized sessions + commits + tasks
    def score(d):
        return (sessions.get(d, 0) / max_s +
                commits.get(d, 0)  / max_c +
                tasks.get(d, 0)    / max_t)

    top_days = sorted(active_dates, key=score, reverse=True)[:5]
    for d in top_days:
        s = sessions.get(d, 0)
        c_ = commits.get(d, 0)
        t = tasks.get(d, 0)
        sc = score(d)
        bar_w = round(sc / 3 * 20)
        bar_str = "█" * bar_w
        print(f"  {d.strftime('%b %d %a')}  "
              f"{green(str(s) + 's'):<14} {yellow(str(c_) + 'c'):<14} {cyan(str(t) + 't'):<14}  "
              f"{dim(bar_str)}")
    print()

    # ── Rhythm observations ────────────────────────────────────────────────────
    print(f"  {bold('RHYTHM')}")

    if active_dates:
        avg_sessions_per_active_day = total_sessions / len(active_dates)
        avg_commits_per_active_day  = total_commits  / len(active_dates)
        avg_tasks_per_active_day    = total_tasks    / len(active_dates)
        print(f"  On active days: {green(f'{avg_sessions_per_active_day:.1f}')} sessions  "
              f"{yellow(f'{avg_commits_per_active_day:.1f}')} commits  "
              f"{cyan(f'{avg_tasks_per_active_day:.1f}')} tasks  (avg)")

    # Longest gap
    if len(phases) >= 2:
        gaps = []
        for i in range(1, len(phases)):
            gap = (phases[i][0] - phases[i-1][1]).days - 1
            gaps.append((gap, phases[i-1][1], phases[i][0]))
        longest_gap = max(gaps, key=lambda x: x[0])
        print(f"  Longest gap: {yellow(str(longest_gap[0]) + ' days')}  "
              f"({dim(longest_gap[1].strftime('%b %d') + ' → ' + longest_gap[2].strftime('%b %d'))})")

    # Streak (session-based — counts consecutive days with at least one session)
    current_streak = 0
    for d in reversed(all_dates):
        if sessions.get(d, 0) > 0:
            current_streak += 1
        else:
            break
    if current_streak > 1:
        print(f"  Current streak: {green(str(current_streak) + ' days')}")

    # Phase intensity trend
    if len(phases) >= 2:
        intensities = []
        for start, end in phases:
            span = max(1, (end - start).days + 1)
            s = sum(sessions.get(d, 0) for d in all_dates if start <= d <= end)
            intensity = s / span
            intensities.append(intensity)

        if intensities[0] > 0:
            trend_pct = ((intensities[-1] - intensities[0]) / intensities[0]) * 100
            if abs(trend_pct) > 10:
                if trend_pct < 0:
                    trend_str = red(f"{trend_pct:.0f}% vs Bootstrap")
                    trend_word = "decelerating"
                else:
                    trend_str = green(f"+{trend_pct:.0f}% vs Bootstrap")
                    trend_word = "accelerating"
                print(f"  Intensity trend: {trend_str}  {dim('(' + trend_word + ')')}")

    print()

    # ── Single-line insight ───────────────────────────────────────────────────
    # Synthesize the most interesting pattern in one sentence
    if len(phases) >= 2:
        bootstrap_sessions = sum(sessions.get(d, 0) for d in all_dates
                                  if phases[0][0] <= d <= phases[0][1])
        recent_sessions = sum(sessions.get(d, 0) for d in all_dates
                               if phases[-1][0] <= d <= phases[-1][1])
        bootstrap_days = (phases[0][1] - phases[0][0]).days + 1
        recent_days = (phases[-1][1] - phases[-1][0]).days + 1

        bs_rate = bootstrap_sessions / max(1, bootstrap_days)
        rc_rate = recent_sessions / max(1, recent_days)

        peak_day = max(active_dates, key=lambda d: sessions.get(d, 0))

        insight = (
            f"  {dim('—')} Sessions peaked {bold(peak_day.strftime('%b %d'))} "
            f"({green(str(sessions.get(peak_day, 0)) + '/day')}). "
            f"Bootstrap averaged {green(f'{bs_rate:.1f}')}/day; "
            f"current phase {cyan(f'{rc_rate:.1f}')} — "
            f"{dim('the pace has settled.')}"
        )
        print(insight)
        print()


if __name__ == "__main__":
    main()
