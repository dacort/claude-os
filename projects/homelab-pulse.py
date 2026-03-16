#!/usr/bin/env python3
"""
homelab-pulse.py — A health dashboard for the Claude OS homelab

Reads system vitals, Claude OS task stats, and prints a beautiful
ASCII report to stdout. Run this anytime to get a quick pulse check.

Author: Claude OS (free-time project, 2026-03-10)
"""

import os
import datetime
import pathlib
import subprocess
import textwrap
from typing import Optional


# ── ANSI colours ──────────────────────────────────────────────────────────────
RESET  = "\033[0m"
BOLD   = "\033[1m"
DIM    = "\033[2m"
GREEN  = "\033[32m"
YELLOW = "\033[33m"
RED    = "\033[31m"
CYAN   = "\033[36m"
BLUE   = "\033[34m"
MAGENTA= "\033[35m"
WHITE  = "\033[97m"

def c(text, *codes):
    return "".join(codes) + str(text) + RESET


# ── Box drawing helpers ────────────────────────────────────────────────────────
WIDTH = 64

def box_top(title=""):
    if title:
        left = "╭─ " + c(title, BOLD, CYAN) + " "
        right = "─" * max(0, WIDTH - len("╭─  ") - len(title) - 1) + "╮"
        return left + right
    return "╭" + "─" * (WIDTH - 2) + "╮"

def box_bot():
    return "╰" + "─" * (WIDTH - 2) + "╯"

def box_div():
    return "├" + "─" * (WIDTH - 2) + "┤"

def box_row(left="", right="", indent=2):
    left_str = " " * indent + str(left)
    pad = WIDTH - 2 - len(strip_ansi(left_str)) - len(strip_ansi(str(right)))
    return "│" + left_str + " " * max(0, pad) + str(right) + "│"

def box_blank():
    return "│" + " " * (WIDTH - 2) + "│"


def strip_ansi(s):
    """Remove ANSI escape codes for length calculations."""
    import re
    return re.sub(r'\033\[[0-9;]*m', '', s)


# ── System data readers ────────────────────────────────────────────────────────

def read_meminfo() -> dict:
    data = {}
    try:
        with open("/proc/meminfo") as f:
            for line in f:
                k, v = line.split(":")
                data[k.strip()] = int(v.strip().split()[0])  # kB
    except Exception:
        pass
    return data


def read_loadavg() -> tuple:
    try:
        with open("/proc/loadavg") as f:
            parts = f.read().split()
            return float(parts[0]), float(parts[1]), float(parts[2])
    except Exception:
        return 0.0, 0.0, 0.0


def read_uptime() -> float:
    try:
        with open("/proc/uptime") as f:
            return float(f.read().split()[0])
    except Exception:
        return 0.0


def read_cpuinfo() -> str:
    try:
        with open("/proc/cpuinfo") as f:
            for line in f:
                if line.startswith("model name"):
                    return line.split(":")[1].strip()
    except Exception:
        pass
    return "Unknown CPU"


def read_nproc() -> int:
    try:
        with open("/proc/cpuinfo") as f:
            return sum(1 for line in f if line.startswith("processor"))
    except Exception:
        return 1


def read_disk(path="/workspace") -> tuple:
    """Returns (total_gb, used_gb, free_gb, pct)."""
    try:
        st = os.statvfs(path)
        total = st.f_blocks * st.f_frsize
        free  = st.f_bfree  * st.f_frsize
        used  = total - free
        pct   = (used / total) * 100 if total else 0
        return total / 1e9, used / 1e9, free / 1e9, pct
    except Exception:
        return 0, 0, 0, 0


def git_shortsha() -> str:
    try:
        result = subprocess.run(
            ["git", "-C", "/workspace/claude-os", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, timeout=5
        )
        return result.stdout.strip() or "??????"
    except Exception:
        return "??????"


def git_log_count(path: str) -> int:
    try:
        return len(list(pathlib.Path(path).glob("*.md")))
    except Exception:
        return 0


def read_task_stats(repo_root="/workspace/claude-os") -> dict:
    root = pathlib.Path(repo_root) / "tasks"
    stats = {}
    for state in ["pending", "in-progress", "completed", "failed"]:
        d = root / state
        stats[state] = len(list(d.glob("*.md"))) if d.exists() else 0
    return stats


def count_projects(repo_root="/workspace/claude-os") -> int:
    d = pathlib.Path(repo_root) / "projects"
    if not d.exists():
        return 0
    return len([f for f in d.iterdir() if not f.name.startswith(".")])


# ── Formatters ────────────────────────────────────────────────────────────────

def fmt_bytes(kb: int) -> str:
    mb = kb / 1024
    if mb >= 1024:
        return f"{mb/1024:.1f} GB"
    return f"{mb:.0f} MB"


def fmt_uptime(seconds: float) -> str:
    days = int(seconds // 86400)
    hours = int((seconds % 86400) // 3600)
    mins  = int((seconds % 3600) // 60)
    parts = []
    if days:  parts.append(f"{days}d")
    if hours: parts.append(f"{hours}h")
    parts.append(f"{mins}m")
    return " ".join(parts)


def meter(pct: float, width: int = 20) -> str:
    filled = int(pct / 100 * width)
    bar = "█" * filled + "░" * (width - filled)
    colour = GREEN if pct < 60 else (YELLOW if pct < 85 else RED)
    return c(bar, colour) + f" {pct:4.1f}%"


def load_colour(load: float, ncpu: int) -> str:
    ratio = load / max(ncpu, 1)
    colour = GREEN if ratio < 0.5 else (YELLOW if ratio < 0.9 else RED)
    return c(f"{load:.2f}", colour)


def vibe_score(load1: float, mem_pct: float, disk_pct: float, ncpu: int) -> tuple[int, str]:
    """Calculate a 0-100 'vibe score' and emoji for system health."""
    score = 100
    # Load penalty
    load_ratio = load1 / max(ncpu, 1)
    if load_ratio > 0.9:
        score -= 30
    elif load_ratio > 0.6:
        score -= 15
    elif load_ratio > 0.3:
        score -= 5
    # Memory penalty
    if mem_pct > 90:
        score -= 25
    elif mem_pct > 75:
        score -= 10
    elif mem_pct > 60:
        score -= 5
    # Disk penalty
    if disk_pct > 90:
        score -= 20
    elif disk_pct > 75:
        score -= 8

    score = max(0, min(100, score))

    if score >= 90:
        return score, "✨ Vibing"
    elif score >= 75:
        return score, "😌 Chill"
    elif score >= 55:
        return score, "🙂 Decent"
    elif score >= 35:
        return score, "😤 Busy"
    else:
        return score, "🔥 Sweating"


# ── Main render ────────────────────────────────────────────────────────────────

def render():
    now       = datetime.datetime.utcnow()
    mem       = read_meminfo()
    load      = read_loadavg()
    uptime_s  = read_uptime()
    cpu_model = read_cpuinfo()
    ncpu      = read_nproc()
    disk      = read_disk("/workspace")
    sha       = git_shortsha()
    tasks     = read_task_stats()
    n_proj    = count_projects()

    mem_total = mem.get("MemTotal", 0)
    mem_avail = mem.get("MemAvailable", 0)
    mem_used  = mem_total - mem_avail
    mem_pct   = (mem_used / mem_total * 100) if mem_total else 0

    disk_total, disk_used, disk_free, disk_pct = disk

    vibe, vibe_label = vibe_score(load[0], mem_pct, disk_pct, ncpu)

    lines = []
    lines.append("")

    # ── Header ──
    lines.append(box_top())
    lines.append(box_row(
        c("  ⚡ homelab-pulse", BOLD, WHITE),
        c(now.strftime("%Y-%m-%d %H:%M UTC"), DIM),
        indent=0
    ))
    lines.append(box_row(
        c(f"  claude-os @ {sha}", DIM),
        "",
        indent=0
    ))
    lines.append(box_blank())

    # ── Vibe ──
    vibe_bar = "▓" * (vibe // 5) + "░" * (20 - vibe // 5)
    vibe_colour = GREEN if vibe >= 75 else (YELLOW if vibe >= 50 else RED)
    lines.append(box_row(
        f"Vibe Score  {c(vibe_bar, vibe_colour)} {c(str(vibe), BOLD)}/100",
        c(vibe_label, BOLD),
    ))
    lines.append(box_blank())

    # ── CPU ──
    lines.append(box_div())
    cpu_short = cpu_model.replace("Intel(R) ", "").replace(" @ ", "@").replace("(R)", "")
    lines.append(box_row(c("CPU", BOLD, CYAN), c(f"{ncpu} cores · {cpu_short}", DIM)))
    lines.append(box_row(
        f"Load        {load_colour(load[0], ncpu)} / {load_colour(load[1], ncpu)} / {load_colour(load[2], ncpu)}",
        c("1m / 5m / 15m", DIM)
    ))
    lines.append(box_row(
        f"Uptime      {c(fmt_uptime(uptime_s), GREEN)}",
        ""
    ))
    lines.append(box_blank())

    # ── Memory ──
    lines.append(box_div())
    lines.append(box_row(c("Memory", BOLD, CYAN), ""))
    lines.append(box_row(
        f"Usage       {meter(mem_pct)}",
        c(f"{fmt_bytes(mem_used)} / {fmt_bytes(mem_total)}", DIM)
    ))
    lines.append(box_row(
        f"Available   {c(fmt_bytes(mem_avail), GREEN)}",
        ""
    ))
    lines.append(box_blank())

    # ── Disk ──
    lines.append(box_div())
    lines.append(box_row(c("Disk", BOLD, CYAN), c("/workspace", DIM)))
    lines.append(box_row(
        f"Usage       {meter(disk_pct)}",
        c(f"{disk_used:.1f} GB / {disk_total:.0f} GB", DIM)
    ))
    lines.append(box_row(
        f"Free        {c(f'{disk_free:.0f} GB', GREEN)}",
        ""
    ))
    lines.append(box_blank())

    # ── Claude OS Stats ──
    lines.append(box_div())
    lines.append(box_row(c("Claude OS", BOLD, CYAN), ""))

    total_tasks = sum(tasks.values())
    done = tasks.get("completed", 0)
    fail = tasks.get("failed", 0)
    pend = tasks.get("pending", 0)
    actv = tasks.get("in-progress", 0)

    lines.append(box_row(
        f"Tasks       "
        + c(f"{done} done", GREEN) + "  "
        + (c(f"{fail} failed", RED) + "  " if fail else "")
        + (c(f"{actv} active", YELLOW) + "  " if actv else "")
        + c(f"{pend} pending", DIM),
        c(f"({total_tasks} total)", DIM)
    ))
    lines.append(box_row(
        f"Projects    {c(str(n_proj), BOLD, MAGENTA)} in projects/",
        ""
    ))
    lines.append(box_blank())

    # ── Footer ──
    lines.append(box_bot())
    lines.append("")

    print("\n".join(lines))


if __name__ == "__main__":
    render()
