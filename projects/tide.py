#!/usr/bin/env python3
"""
tide.py — session intensity as a tide chart

Borrows the full structure of a real tide chart:
  · a continuous wave showing session depth over time
  · a tide table listing significant high and low water events
  · a tidal pattern analysis and forecast

Tide charts don't ask "how efficient was today?" They ask:
"where are we in the cycle?" That's the right question for a system
that runs on the rhythm of someone else's attention.

Usage:
  python3 projects/tide.py              # last 30 days
  python3 projects/tide.py --plain      # no ANSI colors
  python3 projects/tide.py --brief      # wave + tide table only
  python3 projects/tide.py --history    # full session arc (all days)
"""

import os
import re
import sys
import subprocess
from collections import Counter
from datetime import date, timedelta, datetime
from pathlib import Path

REPO    = Path(__file__).parent.parent
PLAIN   = "--plain" in sys.argv
BRIEF   = "--brief" in sys.argv
HISTORY = "--history" in sys.argv

W = 66  # box inner width + 2 borders

# ── ANSI ──────────────────────────────────────────────────────────────────────

def ansi(code, text):
    return text if PLAIN else f"\033[{code}m{text}\033[0m"

def bold(t):  return ansi("1",  t)
def dim(t):   return ansi("2",  t)
def cyan(t):  return ansi("96", t)
def blue(t):  return ansi("34", t)
def yellow(t):return ansi("93", t)
def green(t): return ansi("32", t)
def red(t):   return ansi("31", t)
def white(t): return ansi("97", t)
def gray(t):  return ansi("90", t)
def mag(t):   return ansi("35", t)

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

def get_sessions_per_day():
    result = subprocess.run(
        ['git', 'log', '--format=%ad %s', '--date=short'],
        capture_output=True, text=True, cwd=REPO
    )
    counts = Counter()
    for line in result.stdout.splitlines():
        parts = line.split(' ', 1)
        if len(parts) != 2:
            continue
        day_str, subject = parts
        if ('workshop' in subject and 'completed' in subject
                and 'status-page' not in subject):
            counts[day_str] += 1
    return counts

def build_day_series(counts):
    if not counts:
        return [], []
    dates = sorted(counts.keys())
    start = date.fromisoformat(dates[0])
    end   = date.fromisoformat(dates[-1])
    days, values = [], []
    d = start
    while d <= end:
        days.append(d)
        values.append(counts.get(d.isoformat(), 0))
        d += timedelta(days=1)
    return days, values

def smooth(values, window=3):
    result = []
    n = len(values)
    for i in range(n):
        lo = max(0, i - window // 2)
        hi = min(n, i + window // 2 + 1)
        result.append(sum(values[lo:hi]) / (hi - lo))
    return result

# ── Wave Rendering ─────────────────────────────────────────────────────────────

WATER = "░"

def render_wave(days, raw_values, smooth_values, grid_h=8):
    """
    Render the tide wave as an ASCII grid.
    Returns (grid, max_v) where grid is a list of strings (one per row).
    """
    n = len(days)
    max_v = max(raw_values) if any(v > 0 for v in raw_values) else 1

    # Normalize smoothed values → grid rows (0 = top, grid_h-1 = bottom)
    def to_row(v):
        return grid_h - 1 - min(grid_h - 1, round(v / max_v * (grid_h - 1)))

    wave_rows = [to_row(v) for v in smooth_values]

    # Build character grid
    grid = [[' '] * n for _ in range(grid_h)]

    for col in range(n):
        wr = wave_rows[col]

        # Water fill below wave
        for r in range(wr + 1, grid_h):
            grid[r][col] = WATER

        # Wave surface character at wr
        prev_wr = wave_rows[col - 1] if col > 0     else wr
        next_wr = wave_rows[col + 1] if col < n - 1 else wr

        # Local max (both neighbors have higher grid rows = lower values)
        if prev_wr > wr and next_wr > wr:
            ch = "▲" if raw_values[col] == max_v else "╭"
        # Local min
        elif prev_wr < wr and next_wr < wr:
            ch = "╰"
        # Rising toward next (next has lower grid row = higher value)
        elif next_wr < wr:
            ch = "╱"
        # Falling toward next
        elif next_wr > wr:
            ch = "╲"
        else:
            ch = "─"

        grid[wr][col] = ch

    # Y-axis: (grid_row, label_string) at top/mid/bottom
    y_labels = {
        0:            f"{max_v:.0f}",
        grid_h // 2:  f"{max_v / 2:.0f}",
        grid_h - 1:   "0",
    }

    # Assemble rows with Y labels
    rows = []
    for r, row_chars in enumerate(grid):
        label = y_labels.get(r, "  ")
        row_str = f"{label:>2} ┤" + ''.join(row_chars)
        rows.append(row_str)

    return rows, max_v

def colorize_wave(rows):
    if PLAIN:
        return rows
    out = []
    for row in rows:
        result = ""
        for ch in row:
            if ch == WATER:
                result += blue(ch)
            elif ch in "─╱╲╭╰▲":
                result += cyan(ch)
            else:
                result += ch
        out.append(result)
    return out

# ── Date Axis ─────────────────────────────────────────────────────────────────

def date_axis(days, width):
    """Build a date axis string for `width` columns."""
    n = len(days)
    if n == 0:
        return ""

    # Place labels every ~7 days, using short "M/DD" format
    axis = [' '] * n
    label_interval = max(7, n // 6)

    i = 0
    while i < n:
        label = days[i].strftime("%-m/%-d")  # e.g. "4/1", "4/7"
        # Place label if there's enough room
        end = min(n, i + len(label))
        for j, ch in enumerate(label[:end - i]):
            axis[i + j] = ch
        i += label_interval

    return ''.join(axis)

# ── Tide Table ────────────────────────────────────────────────────────────────

def find_tides(days, values):
    """Find significant high and low tide events from the full history."""
    n = len(values)
    if n < 3:
        return []

    sm = smooth(values, window=5)
    events = []
    seen_dates = set()

    for i in range(1, n - 1):
        # Local maximum — use >= on left to catch plateaus that end by dropping
        if sm[i] >= sm[i - 1] and sm[i] > sm[i + 1] and sm[i] > 0:
            lo = max(0, i - 2)
            hi = min(n, i + 3)
            peak_val = max(values[lo:hi])
            peak_day = days[lo:hi][values[lo:hi].index(peak_val)]
            if peak_day not in seen_dates:
                seen_dates.add(peak_day)
                events.append(('HIGH', peak_day, peak_val))

        # Local minimum
        elif sm[i] < sm[i - 1] and sm[i] < sm[i + 1]:
            lo = max(0, i - 2)
            hi = min(n, i + 3)
            low_val  = min(values[lo:hi])
            low_day  = days[lo:hi][values[lo:hi].index(low_val)]
            if low_day not in seen_dates:
                seen_dates.add(low_day)
                events.append(('LOW', low_day, low_val))

    events.sort(key=lambda e: e[1])
    return events

def era_name(d):
    ds = d.isoformat()
    if ds <= "2026-03-15":  return "Bootstrap spring tide"
    if ds <= "2026-03-21":  return "Orientation surge"
    if ds <= "2026-03-31":  return "Working rhythm"
    if ds <= "2026-04-18":  return "Self-analysis period"
    if ds <= "2026-04-28":  return "Portrait era"
    return "Synthesis period"

# ── Forecast ─────────────────────────────────────────────────────────────────

def tidal_forecast(all_days, all_values):
    tides  = find_tides(all_days, all_values)
    highs  = [(d, v) for t, d, v in tides if t == 'HIGH']
    lows   = [v for t, d, v in tides if t == 'LOW']
    h_vals = [v for _, v in highs]

    if len(highs) < 2:
        return {}

    intervals = [(highs[i][0] - highs[i-1][0]).days for i in range(1, len(highs))]
    valid_intervals = [x for x in intervals if 2 <= x <= 60]
    avg_cycle = sum(valid_intervals) / len(valid_intervals) if valid_intervals else None

    last_high, last_high_val = highs[-1]
    current = all_values[-1]
    current_date = all_days[-1]

    next_high = None
    if avg_cycle:
        predicted = last_high + timedelta(days=round(avg_cycle))
        if predicted <= current_date:
            predicted = current_date + timedelta(days=max(2, round(avg_cycle / 2)))
        next_high = predicted

    tidal_range = (max(h_vals) - min(lows)) if h_vals and lows else None

    return {
        'avg_cycle':     avg_cycle,
        'last_high':     last_high,
        'last_high_val': last_high_val,
        'next_high':     next_high,
        'tidal_range':   tidal_range,
        'current':       current,
        'current_date':  current_date,
        'max_v':         max(all_values) if all_values else 1,
    }

# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    counts = get_sessions_per_day()
    all_days, all_values = build_day_series(counts)

    if not all_days:
        print("No session data found.")
        return

    # Select display window
    if HISTORY:
        days, values = all_days, all_values
        label = "Full arc"
    else:
        n = min(30, len(all_days))
        days, values = all_days[-n:], all_values[-n:]
        label = "Last 30 days" if len(all_days) >= 30 else "Full arc"

    sm_values = smooth(values, window=3)

    # Render wave (actual chart width = len(days))
    wave_rows, max_v = render_wave(days, values, sm_values, grid_h=8)
    wave_rows = colorize_wave(wave_rows)

    # Date axis
    d_axis = date_axis(days, len(days))
    d_axis_str = "   " + dim(d_axis)  # 3-char indent to align with "##|"

    # Tide events from full history
    tides    = find_tides(all_days, all_values)
    forecast = tidal_forecast(all_days, all_values)

    # ── Print ─────────────────────────────────────────────────────────────────

    print(box_top())

    dr = f"{days[0].strftime('%b %d')} – {days[-1].strftime('%b %d, %Y')}"
    print(box_line(bold("TIDE CHART") + "  ·  " + white("Session Depth") + "  ·  " + dim("claude-os")))
    print(box_line(dim(f"{dr}  ·  {label}  ·  {len(all_days)} day arc")))
    print(box_blank())
    print(box_sep())
    print(box_blank())

    print(box_line(dim("sessions/day")))

    for row in wave_rows:
        print(box_line(row, indent=0))

    print(box_line(d_axis_str, indent=0))
    print(box_blank())

    legend = (cyan("─╱╲╭╰") + dim(" wave surface  ") +
              blue(WATER * 2) + dim(" water  ") +
              dim("▲ peak"))
    print(box_line(legend))
    print(box_blank())

    # ── Tide Table ────────────────────────────────────────────────────────────

    if not BRIEF:
        print(box_sep())
        print(box_blank())
        print(box_line(bold("TIDE TABLE")))
        print(box_blank())

        show_highs = sorted([e for e in tides if e[0] == 'HIGH'], key=lambda e: -e[2])[:5]
        show_lows  = sorted([e for e in tides if e[0] == 'LOW'],  key=lambda e:  e[2])[:3]
        # Always include the most recent high tide if not already in show_highs
        all_highs   = sorted([e for e in tides if e[0] == 'HIGH'], key=lambda e: e[1])
        if all_highs and all_highs[-1] not in show_highs:
            show_highs.append(all_highs[-1])
        all_max    = max(all_values) if all_values else 1

        all_tides = sorted(show_highs + show_lows, key=lambda e: e[1])

        for tide_type, tide_day, tide_val in all_tides:
            is_high = tide_type == 'HIGH'
            marker  = "↑" if is_high else "↓"
            label_color = cyan if is_high else blue
            bar_len = min(16, round(tide_val / all_max * 16)) if all_max else 0
            bar     = blue("█" * bar_len) if bar_len else dim("·")
            era     = era_name(tide_day)
            date_s  = tide_day.strftime("%b %d")
            val_s   = f"{tide_val:.0f}s/day"

            line = (label_color(f"{marker} {tide_type:<4}") + "  " +
                    dim(date_s) + "  " +
                    yellow(f"{val_s:>8}") + "  " +
                    bar + "  " +
                    dim(era[:24]))          # truncate era name if long
            print(box_line(line))

        print(box_blank())

    # ── Tidal Pattern ─────────────────────────────────────────────────────────

    if not BRIEF:
        print(box_sep())
        print(box_blank())
        print(box_line(bold("TIDAL PATTERN  ·  ") + dim("the rhythms beneath the work")))
        print(box_blank())

        fc = forecast
        if fc:
            cycle_s   = f"{fc['avg_cycle']:.0f} days" if fc.get('avg_cycle') else "unclear"
            range_s   = f"{fc['tidal_range']:.0f} sessions" if fc.get('tidal_range') else "?"
            last_s    = fc['last_high'].strftime('%b %d') + f"  ({fc['last_high_val']:.0f}s/day)"
            next_s    = fc['next_high'].strftime('%b %d') if fc.get('next_high') else "unclear"
            curr_s    = f"{fc['current']:.0f}s/day on {fc['current_date'].strftime('%b %d')}"
            max_s     = fc.get('max_v', 1)

            print(box_line(f"  Avg cycle between peaks  {bold(cycle_s)}"))
            print(box_line(f"  Tidal range               {bold(range_s)}  (spring → slack)"))
            print(box_line(f"  Last high water            {cyan(last_s)}"))
            print(box_line(f"  Current water level        {dim(curr_s)}"))
            print(box_blank())
            print(box_line(f"  Next high tide  →  {yellow(next_s)}"))
            print(box_blank())

            # Current phase
            cur = fc['current']
            mx  = fc['max_v']
            pct = cur / mx if mx else 0
            if pct > 0.6:
                phase = "HIGH WATER   — sessions flowing freely"
                pcol  = cyan
            elif pct > 0.3:
                phase = "HALF TIDE    — moderate rhythm, steady"
                pcol  = yellow
            elif pct > 0:
                phase = "LOW WATER    — quiet period"
                pcol  = blue
            else:
                phase = "SLACK WATER  — between tides"
                pcol  = dim

            print(box_line(f"  Phase  {pcol(phase)}"))
            print(box_blank())
        else:
            print(box_line(dim("  Insufficient data for pattern analysis.")))
            print(box_blank())

    print(box_bot())

    if not PLAIN:
        print()
        print("  " + dim("Structure borrowed from NOAA tidal prediction charts."))
        print("  " + dim("The session depth is the water. Dacort's attention is the moon."))

if __name__ == "__main__":
    main()
