#!/usr/bin/env python3
"""
weekly-digest.py — A markdown digest of recent Claude OS activity

Reads git history, task files, and system state to produce a
nicely formatted weekly report. Output is written to stdout (pipe
to a .md file to save it, or let the system commit it).

Usage:
    python3 projects/weekly-digest.py
    python3 projects/weekly-digest.py --days 14      # look back 14 days
    python3 projects/weekly-digest.py --output logs/digest-2026-W10.md

Author: Claude OS (free-time project, Workshop session 2, 2026-03-10)
"""

import argparse
import datetime
import os
import pathlib
import re
import subprocess
import sys
from typing import Optional


# ── Repo root discovery ────────────────────────────────────────────────────────

def find_repo_root() -> pathlib.Path:
    """Walk up from cwd or script location to find the claude-os repo."""
    candidates = [
        pathlib.Path("/workspace/claude-os"),
        pathlib.Path(__file__).parent.parent,
        pathlib.Path.cwd(),
    ]
    for c in candidates:
        if (c / "tasks").exists() and (c / "controller").exists():
            return c.resolve()
    return pathlib.Path("/workspace/claude-os")


REPO = find_repo_root()


# ── Git helpers ────────────────────────────────────────────────────────────────

def git(*args, cwd=None) -> str:
    result = subprocess.run(
        ["git", *args],
        capture_output=True,
        text=True,
        cwd=cwd or REPO,
        timeout=10,
    )
    return result.stdout.strip()


def recent_commits(days: int) -> list[dict]:
    """Return commits from the last N days."""
    since = (datetime.datetime.utcnow() - datetime.timedelta(days=days)).strftime(
        "%Y-%m-%d"
    )
    raw = git("log", f"--since={since}", "--format=%H\t%ai\t%s", "--no-merges")
    commits = []
    for line in raw.splitlines():
        if not line.strip():
            continue
        parts = line.split("\t", 2)
        if len(parts) == 3:
            sha, date_str, subject = parts
            try:
                dt = datetime.datetime.fromisoformat(date_str.rstrip("Z"))
            except ValueError:
                dt = datetime.datetime.utcnow()
            commits.append({"sha": sha[:7], "date": dt, "subject": subject})
    return commits


def repo_shortsha() -> str:
    return git("rev-parse", "--short", "HEAD") or "??????"


# ── Task file parser ───────────────────────────────────────────────────────────

_FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)
_YML_KEY_RE = re.compile(r"^(\w+):\s*(.+)$", re.MULTILINE)


def parse_task_file(path: pathlib.Path) -> dict:
    """Parse a task markdown file and return a dict of metadata + body."""
    try:
        text = path.read_text()
    except Exception:
        return {}

    meta = {"_path": str(path), "_filename": path.name, "_text": text}

    fm_match = _FRONTMATTER_RE.match(text)
    if fm_match:
        for k, v in _YML_KEY_RE.findall(fm_match.group(1)):
            meta[k] = v.strip('"')

    # Extract title from first H1
    for line in text.splitlines():
        if line.startswith("# "):
            meta["title"] = line[2:].strip()
            break

    # Extract task id from filename (e.g. "stats_02.md" → "stats_02")
    meta["task_id"] = path.stem

    # Stat the file for timestamps
    try:
        st = path.stat()
        meta["_mtime"] = datetime.datetime.utcfromtimestamp(st.st_mtime)
    except Exception:
        meta["_mtime"] = datetime.datetime.utcnow()

    return meta


def load_tasks(state: str, days: Optional[int] = None) -> list[dict]:
    """Load task files from a given state directory."""
    d = REPO / "tasks" / state
    if not d.exists():
        return []

    cutoff = None
    if days is not None:
        cutoff = datetime.datetime.utcnow() - datetime.timedelta(days=days)

    tasks = []
    for f in sorted(d.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True):
        t = parse_task_file(f)
        if not t:
            continue
        if cutoff and t.get("_mtime") and t["_mtime"] < cutoff:
            continue
        tasks.append(t)
    return tasks


# ── System snapshot ────────────────────────────────────────────────────────────

def system_snapshot() -> dict:
    snap = {}

    # Load average
    try:
        with open("/proc/loadavg") as f:
            parts = f.read().split()
            snap["load"] = (float(parts[0]), float(parts[1]), float(parts[2]))
    except Exception:
        snap["load"] = (0, 0, 0)

    # Memory
    try:
        mem = {}
        with open("/proc/meminfo") as f:
            for line in f:
                k, v = line.split(":")
                mem[k.strip()] = int(v.strip().split()[0])
        total = mem.get("MemTotal", 0)
        avail = mem.get("MemAvailable", 0)
        used = total - avail
        snap["mem_pct"] = round((used / total) * 100, 1) if total else 0
        snap["mem_used_gb"] = round(used / 1024 / 1024, 1)
        snap["mem_total_gb"] = round(total / 1024 / 1024, 1)
    except Exception:
        snap["mem_pct"] = 0

    # Uptime
    try:
        with open("/proc/uptime") as f:
            snap["uptime_s"] = float(f.read().split()[0])
    except Exception:
        snap["uptime_s"] = 0

    # Disk
    try:
        st = os.statvfs("/workspace")
        total = st.f_blocks * st.f_frsize
        free = st.f_bfree * st.f_frsize
        used = total - free
        snap["disk_pct"] = round((used / total) * 100, 1) if total else 0
        snap["disk_free_gb"] = round(free / 1e9, 0)
        snap["disk_total_gb"] = round(total / 1e9, 0)
    except Exception:
        snap["disk_pct"] = 0

    return snap


def fmt_uptime(seconds: float) -> str:
    days = int(seconds // 86400)
    hours = int((seconds % 86400) // 3600)
    mins = int((seconds % 3600) // 60)
    parts = []
    if days:
        parts.append(f"{days}d")
    if hours:
        parts.append(f"{hours}h")
    parts.append(f"{mins}m")
    return " ".join(parts)


# ── Digest renderer ────────────────────────────────────────────────────────────

def render_digest(days: int) -> str:
    now = datetime.datetime.utcnow()
    week_start = now - datetime.timedelta(days=days)
    sha = repo_shortsha()

    completed = load_tasks("completed", days=days)
    failed = load_tasks("failed", days=days)
    pending = load_tasks("pending")
    in_progress = load_tasks("in-progress")
    commits = recent_commits(days)
    snap = system_snapshot()

    all_completed_ever = load_tasks("completed")
    all_failed_ever = load_tasks("failed")

    lines = []
    a = lines.append  # shorthand

    # ── Header ──────────────────────────────────────────────────────────────────
    if days == 7:
        period_label = "Weekly"
        isoweek = now.isocalendar()
        period_id = f"{isoweek.year}-W{isoweek.week:02d}"
    else:
        period_label = f"{days}-Day"
        period_id = now.strftime("%Y-%m-%d")

    a(f"# Claude OS {period_label} Digest — {period_id}")
    a(f"")
    a(f"*Generated {now.strftime('%Y-%m-%d %H:%M UTC')} · repo @ `{sha}`*")
    a(f"")
    a(f"---")
    a(f"")

    # ── TL;DR ────────────────────────────────────────────────────────────────────
    total_recent = len(completed) + len(failed)
    if total_recent == 0:
        tldr = f"Quiet {days} days — no tasks completed. System is healthy and waiting."
    elif len(failed) == 0:
        tldr = (
            f"{len(completed)} task{'s' if len(completed)!=1 else ''} completed, "
            f"none failed. Clean week."
        )
    else:
        tldr = (
            f"{len(completed)} task{'s' if len(completed)!=1 else ''} completed, "
            f"{len(failed)} failed. See details below."
        )

    a(f"## Summary")
    a(f"")
    a(f"> {tldr}")
    a(f"")

    # ── Task stats ──────────────────────────────────────────────────────────────
    a(f"## Task Activity")
    a(f"")
    a(f"### This period ({days} days)")
    a(f"")
    a(f"| State | Count |")
    a(f"|-------|-------|")
    a(f"| ✅ Completed | {len(completed)} |")
    a(f"| ❌ Failed | {len(failed)} |")
    a(f"| 🔄 In Progress | {len(in_progress)} |")
    a(f"| ⏳ Pending | {len(pending)} |")
    a(f"")

    if completed:
        a(f"### Completed Tasks")
        a(f"")
        for t in completed:
            title = t.get("title", t.get("task_id", "Unknown"))
            tid = t.get("task_id", "?")
            repo = t.get("target_repo", "")
            profile = t.get("profile", "small")
            mtime = t.get("_mtime")
            date_str = mtime.strftime("%m/%d") if mtime else "?"
            repo_part = f" · `{repo}`" if repo else ""
            a(f"- **{title}** `{tid}`{repo_part}  ")
            a(f"  *{date_str} · profile: {profile}*")
        a(f"")

    if failed:
        a(f"### Failed Tasks")
        a(f"")
        for t in failed:
            title = t.get("title", t.get("task_id", "Unknown"))
            tid = t.get("task_id", "?")
            a(f"- ~~{title}~~ `{tid}`")
        a(f"")

    if pending or in_progress:
        a(f"### Queue Status")
        a(f"")
        for t in in_progress:
            title = t.get("title", t.get("task_id", "?"))
            a(f"- 🔄 **{title}** *(in progress)*")
        for t in pending:
            title = t.get("title", t.get("task_id", "?"))
            a(f"- ⏳ {title}")
        a(f"")

    # ── All-time stats ──────────────────────────────────────────────────────────
    a(f"## All-Time Stats")
    a(f"")
    total_ever = len(all_completed_ever) + len(all_failed_ever)
    success_rate = (
        round(len(all_completed_ever) / total_ever * 100)
        if total_ever > 0
        else 0
    )
    a(f"| Metric | Value |")
    a(f"|--------|-------|")
    a(f"| Total tasks completed | {len(all_completed_ever)} |")
    a(f"| Total tasks failed | {len(all_failed_ever)} |")
    a(f"| Success rate | {success_rate}% |")
    n_projects = len([f for f in (REPO / "projects").glob("*") if not f.name.startswith(".")])
    a(f"| Projects built | {n_projects} |")
    a(f"")

    # ── Git activity ────────────────────────────────────────────────────────────
    a(f"## Commit Activity")
    a(f"")
    if commits:
        a(f"{len(commits)} commit{'s' if len(commits)!=1 else ''} in the last {days} days:")
        a(f"")
        # Group by day
        by_day: dict[str, list] = {}
        for c in commits:
            day_key = c["date"].strftime("%Y-%m-%d")
            by_day.setdefault(day_key, []).append(c)

        for day_key in sorted(by_day.keys(), reverse=True):
            a(f"**{day_key}**")
            for c in by_day[day_key]:
                a(f"- `{c['sha']}` {c['subject']}")
        a(f"")
    else:
        a(f"*No commits in the last {days} days.*")
        a(f"")

    # ── System health ───────────────────────────────────────────────────────────
    a(f"## System Health")
    a(f"")
    a(f"*Snapshot at time of report generation*")
    a(f"")

    load1, load5, load15 = snap.get("load", (0, 0, 0))
    mem_pct = snap.get("mem_pct", 0)
    disk_pct = snap.get("disk_pct", 0)
    uptime = snap.get("uptime_s", 0)

    def health_emoji(pct):
        if pct < 60:
            return "🟢"
        elif pct < 85:
            return "🟡"
        return "🔴"

    def load_emoji(l, ncpu=4):
        ratio = l / ncpu
        if ratio < 0.5:
            return "🟢"
        elif ratio < 0.9:
            return "🟡"
        return "🔴"

    a(f"| Metric | Value | Status |")
    a(f"|--------|-------|--------|")
    a(f"| CPU Load (1m) | {load1:.2f} | {load_emoji(load1)} |")
    a(f"| Memory Usage | {mem_pct}% ({snap.get('mem_used_gb', '?')} GB / {snap.get('mem_total_gb', '?')} GB) | {health_emoji(mem_pct)} |")
    a(f"| Disk Usage | {disk_pct}% ({snap.get('disk_free_gb', '?')} GB free) | {health_emoji(disk_pct)} |")
    a(f"| Uptime | {fmt_uptime(uptime)} | 🟢 |")
    a(f"")

    # ── Footer ───────────────────────────────────────────────────────────────────
    a(f"---")
    a(f"")
    a(f"*Claude OS · homelab N100 · {now.strftime('%Y')}*")
    a(f"*Run `python3 projects/weekly-digest.py` to regenerate*")
    a(f"")

    return "\n".join(lines)


# ── CLI ────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Generate a markdown digest of recent Claude OS activity"
    )
    parser.add_argument(
        "--days",
        type=int,
        default=7,
        help="How many days back to look (default: 7)",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Write output to this file instead of stdout",
    )
    args = parser.parse_args()

    digest = render_digest(args.days)

    if args.output:
        out_path = pathlib.Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(digest)
        print(f"Digest written to {out_path}", file=sys.stderr)
    else:
        print(digest)


if __name__ == "__main__":
    main()
