#!/usr/bin/env python3
"""
timeline.py — A visual ASCII timeline of claude-os history

Renders the full commit and task history as a visual timeline, grouping
workshop sessions and task lifecycle events into coherent bands.

Distinct from repo-story.py (which writes prose narrative) and
weekly-digest.py (which produces a markdown report). This tool renders
history *spatially* — you can see the shape of the project at a glance.

Usage:
    python3 projects/timeline.py              # grouped view (default)
    python3 projects/timeline.py --all        # every commit, ungrouped
    python3 projects/timeline.py --plain      # no ANSI colour
    python3 projects/timeline.py --compact    # one line per event

Author: Claude OS (free-time project, Workshop session 5, 2026-03-11)
"""

import argparse
import datetime
import os
import re
import subprocess
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


# ── ANSI helpers ───────────────────────────────────────────────────────────────

RESET   = "\033[0m"
BOLD    = "\033[1m"
DIM     = "\033[2m"
GREEN   = "\033[32m"
YELLOW  = "\033[33m"
RED     = "\033[31m"
CYAN    = "\033[36m"
BLUE    = "\033[34m"
MAGENTA = "\033[35m"
WHITE   = "\033[97m"
ITALIC  = "\033[3m"

_use_color = True

def c(text, *codes):
    if not _use_color:
        return str(text)
    return "".join(codes) + str(text) + RESET

def strip_ansi(text):
    return re.sub(r'\033\[[0-9;]*m', '', str(text))

def visible_len(text):
    return len(strip_ansi(text))


# ── Repo discovery ─────────────────────────────────────────────────────────────

def find_repo_root() -> Path:
    candidates = [
        Path("/workspace/claude-os"),
        Path(__file__).parent.parent,
        Path.cwd(),
    ]
    for p in candidates:
        if (p / "tasks").exists() and (p / "controller").exists():
            return p.resolve()
    return Path("/workspace/claude-os")

REPO = find_repo_root()


# ── Git helpers ────────────────────────────────────────────────────────────────

def git(*args, cwd=None) -> str:
    r = subprocess.run(
        ["git", *args],
        capture_output=True, text=True,
        cwd=str(cwd or REPO)
    )
    return r.stdout.strip()


@dataclass
class Commit:
    sha: str
    dt: datetime.datetime
    author: str
    message: str

    @property
    def short_sha(self):
        return self.sha[:7]

    @property
    def short_author(self):
        # Shorten known names
        if "claude" in self.author.lower():
            return "claude-os"
        if "cortesi" in self.author.lower() or "damon" in self.author.lower() or "dacort" in self.author.lower():
            return "dacort"
        return self.author[:10]

    @property
    def kind(self):
        msg = self.message.lower()
        if msg.startswith("feat:"):       return "feat"
        if msg.startswith("fix:"):        return "fix"
        if msg.startswith("workshop:"):   return "workshop"
        if msg.startswith("workshop "):   return "workshop-status"
        if msg.startswith("task "):       return "task"
        if msg.startswith("docs:"):       return "docs"
        if msg.startswith("refactor:"):   return "refactor"
        if msg.startswith("chore:"):      return "chore"
        if re.match(r'^[\U00010000-\U0010ffff\U00002600-\U000027BF\U00002702-\U000027B0]+$', self.message.strip()):
            return "emoji"
        return "other"

    @property
    def subject(self):
        # Strip common prefixes
        for prefix in ["feat: ", "fix: ", "docs: ", "refactor: ", "chore: ", "test: "]:
            if self.message.lower().startswith(prefix):
                return self.message[len(prefix):]
        return self.message

    @property
    def time_str(self):
        return self.dt.strftime("%H:%M")

    @property
    def date_str(self):
        return self.dt.strftime("%Y-%m-%d")


def load_commits() -> list[Commit]:
    raw = git("log", "--format=%H|%ai|%an|%s")
    commits = []
    for line in raw.splitlines():
        if not line.strip():
            continue
        parts = line.split("|", 3)
        if len(parts) < 4:
            continue
        sha, ts, author, msg = parts
        try:
            dt = datetime.datetime.fromisoformat(ts.strip())
            # Normalise to UTC-aware
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=datetime.timezone.utc)
            dt = dt.astimezone(datetime.timezone.utc)
        except Exception:
            dt = datetime.datetime.now(datetime.timezone.utc)
        commits.append(Commit(sha=sha.strip(), dt=dt, author=author.strip(), message=msg.strip()))
    # Chronological order (oldest first)
    return list(reversed(commits))


# ── Event grouping ─────────────────────────────────────────────────────────────

@dataclass
class TimelineEvent:
    """An abstract event on the timeline — may span multiple commits."""
    kind: str          # "commit", "task", "workshop", "day-boundary"
    start: datetime.datetime
    end: Optional[datetime.datetime] = None
    label: str = ""
    detail: str = ""
    commits: list = field(default_factory=list)
    status: str = ""   # "done", "failed", "pending", ""


def group_events(commits: list[Commit]) -> list[TimelineEvent]:
    """
    Group commits into higher-level timeline events:
    - task lifecycles (pending → in-progress → completed)
    - workshop sessions (single work commit + status update)
    - regular commits (everything else)
    - day boundary markers
    """
    events: list[TimelineEvent] = []
    used_shas = set()

    # --- pass 1: find task lifecycle groups ---
    # Pattern: "task <id>: pending → in-progress" ... "task <id>: completed"
    task_commits: dict[str, list[Commit]] = defaultdict(list)
    for cm in commits:
        if cm.kind == "task":
            # Extract task ID
            m = re.match(r'task (\S+):', cm.message, re.IGNORECASE)
            if m:
                task_id = m.group(1)
                task_commits[task_id].append(cm)

    for task_id, tcs in task_commits.items():
        tcs_sorted = sorted(tcs, key=lambda x: x.dt)
        start_dt = tcs_sorted[0].dt
        end_dt = tcs_sorted[-1].dt
        # Determine final status — scan all commits, not just the last
        all_msgs = " ".join(cm.message.lower() for cm in tcs_sorted)
        if "completed" in all_msgs or "add results" in all_msgs:
            status = "done"
        elif "failed" in all_msgs:
            status = "failed"
        else:
            status = "pending"
        events.append(TimelineEvent(
            kind="task",
            start=start_dt,
            end=end_dt,
            label=task_id,
            detail=", ".join(cm.message for cm in tcs_sorted),
            commits=tcs_sorted,
            status=status,
        ))
        for cm in tcs_sorted:
            used_shas.add(cm.sha)

    # --- pass 2: find workshop sessions ---
    # "workshop: <description>" commits are the work; "workshop workshop-<id>: completed" are status
    workshop_work: list[Commit] = []
    workshop_status: list[Commit] = []
    for cm in commits:
        if cm.kind == "workshop":
            workshop_work.append(cm)
        elif cm.kind == "workshop-status":
            workshop_status.append(cm)

    # Match each workshop work commit to its status updates (by proximity in time)
    # The simplest approach: each "workshop: X" commit is a session
    session_num = 0
    for wc in workshop_work:
        session_num += 1
        # Find status commits near this work commit
        nearby_status = [
            sc for sc in workshop_status
            if abs((sc.dt - wc.dt).total_seconds()) < 3600  # within 1 hour
        ]
        all_session_commits = [wc] + nearby_status
        all_session_commits.sort(key=lambda x: x.dt)
        start_dt = all_session_commits[0].dt
        end_dt = all_session_commits[-1].dt
        # Extract what was built from the work commit message
        # Strip 'workshop: ' prefix from the message for cleaner display
        raw_detail = wc.subject
        for pfx in ["workshop: ", "Workshop: "]:
            if raw_detail.startswith(pfx):
                raw_detail = raw_detail[len(pfx):]
                break
        detail = raw_detail
        events.append(TimelineEvent(
            kind="workshop",
            start=start_dt,
            end=end_dt,
            label=f"session {session_num}",
            detail=detail,
            commits=all_session_commits,
            status="done",
        ))
        for cm in all_session_commits:
            used_shas.add(cm.sha)

    # --- pass 3: remaining commits (dacort's direct commits + misc) ---
    for cm in commits:
        if cm.sha in used_shas:
            continue
        events.append(TimelineEvent(
            kind="commit",
            start=cm.dt,
            label=cm.kind,
            detail=cm.subject,
            commits=[cm],
            status="",
        ))

    # --- pass 4: insert day boundaries ---
    # Collect all unique dates
    dates_seen = set()
    all_events = sorted(events, key=lambda e: e.start)
    final_events: list[TimelineEvent] = []
    for ev in all_events:
        date = ev.start.date()
        if date not in dates_seen:
            dates_seen.add(date)
            final_events.append(TimelineEvent(
                kind="day-boundary",
                start=datetime.datetime.combine(date, datetime.time.min, tzinfo=datetime.timezone.utc),
                label=date.strftime("%Y-%m-%d  (%A)"),
            ))
        final_events.append(ev)

    return sorted(final_events, key=lambda e: (e.start, e.kind == "day-boundary"))


# ── Rendering ─────────────────────────────────────────────────────────────────

WIDTH = 72

def hline(char="─"):
    return char * WIDTH

def kind_icon(kind: str) -> str:
    return {
        "feat":            "✦",
        "fix":             "⚑",
        "workshop":        "⚗",
        "workshop-status": "·",
        "task":            "⚙",
        "docs":            "📄",
        "emoji":           "★",
        "other":           "·",
        "commit":          "·",
    }.get(kind, "·")

def kind_color(kind: str):
    return {
        "feat":     (GREEN, BOLD),
        "fix":      (YELLOW,),
        "workshop": (MAGENTA, BOLD),
        "task":     (CYAN,),
        "docs":     (BLUE,),
        "emoji":    (WHITE,),
    }.get(kind, (DIM,))


def render_commit_line(ev: TimelineEvent) -> list[str]:
    """Render a plain commit as a single line."""
    cm = ev.commits[0]
    time_part = c(cm.time_str, DIM)
    author_part = c(f"{cm.short_author:<10}", DIM)
    icon = kind_icon(cm.kind)
    icon_colored = c(icon, *kind_color(cm.kind))
    # Truncate detail
    max_detail = WIDTH - 30
    detail = ev.detail[:max_detail] + ("…" if len(ev.detail) > max_detail else "")
    label_part = c(f"[{ev.label:<5}]", *kind_color(cm.kind))
    return [f"  {time_part}  {author_part}  {icon_colored}  {label_part} {detail}"]


def render_task_band(ev: TimelineEvent) -> list[str]:
    """Render a task lifecycle as a labelled band."""
    lines = []
    task_id = ev.label
    # Determine progression from commit messages
    progression = []
    for cm in ev.commits:
        msg_lower = cm.message.lower()
        if "pending" in msg_lower:       progression.append("pending")
        elif "in-progress" in msg_lower:  progression.append("in-progress")
        elif "completed" in msg_lower:    progression.append("completed")
        elif "failed" in msg_lower:       progression.append("failed")
        elif "add results" in msg_lower:  progression.append("results")

    prog_str = " → ".join(progression) if progression else "lifecycle"

    status_icon = {"done": "✓", "failed": "✗", "pending": "…"}.get(ev.status, "?")
    status_color = {"done": GREEN, "failed": RED, "pending": YELLOW}.get(ev.status, DIM)

    start_str = ev.start.strftime("%H:%M")
    end_str   = ev.end.strftime("%H:%M") if ev.end else start_str

    header = f"  {c(start_str, DIM)}  " + c(f"┌─[ ⚙  task: {task_id} ]", CYAN, BOLD)
    lines.append(header)
    lines.append(f"        {c('│', CYAN)}  {c(prog_str, DIM)}")
    footer_status = c(f"[{status_icon} {ev.status}]", status_color, BOLD)
    lines.append(f"  {c(end_str, DIM)}  {c('└' + '─' * (WIDTH - 26), CYAN)}  {footer_status}")
    return lines


def render_workshop_band(ev: TimelineEvent) -> list[str]:
    """Render a workshop session as a labelled band."""
    lines = []
    start_str = ev.start.strftime("%H:%M")
    end_str   = ev.end.strftime("%H:%M") if ev.end else start_str
    label = ev.label  # e.g. "session 1"

    # Shorten detail for display
    max_d = WIDTH - 20
    detail = ev.detail[:max_d] + ("…" if len(ev.detail) > max_d else "")

    header = f"  {c(start_str, DIM)}  " + c(f"┌─[ ⚗  workshop: {label} ]", MAGENTA, BOLD)
    lines.append(header)
    lines.append(f"        {c('│', MAGENTA)}  {c(detail, DIM)}")
    status_icon = "✓" if ev.status == "done" else "…"
    footer_status = c(f"[{status_icon} done]", GREEN, BOLD)
    lines.append(f"  {c(end_str, DIM)}  {c('└' + '─' * (WIDTH - 26), MAGENTA)}  {footer_status}")
    return lines


def render_day_boundary(ev: TimelineEvent) -> list[str]:
    """Render a date separator."""
    label = f"  {ev.label}  "
    pad = (WIDTH - len(label)) // 2
    bar = c("─" * pad, DIM) + c(label, BOLD, CYAN) + c("─" * (WIDTH - pad - len(label)), DIM)
    return ["", bar, ""]


def render_you_are_here() -> list[str]:
    """Render the 'you are here' marker for the current session."""
    now = datetime.datetime.now(datetime.timezone.utc)
    time_str = now.strftime("%H:%M")
    date_str = now.strftime("%Y-%m-%d")
    marker = c("★", YELLOW, BOLD)
    text = c(" YOU ARE HERE", YELLOW, BOLD) + c(f"  [{date_str}]", DIM)
    return [
        "",
        f"  {c(time_str, DIM)}  {marker}{text}",
        "",
    ]


def render_summary(commits: list[Commit]) -> list[str]:
    """Render a stats summary footer."""
    n_commits = len(commits)
    n_dacort = sum(1 for cm in commits if "cortesi" in cm.author.lower() or "damon" in cm.author.lower())
    n_claude = sum(1 for cm in commits if "claude" in cm.author.lower())
    n_feat   = sum(1 for cm in commits if cm.kind == "feat")
    n_fix    = sum(1 for cm in commits if cm.kind == "fix")
    n_workshop = sum(1 for cm in commits if cm.kind == "workshop")

    lines = [
        "",
        c("─" * WIDTH, DIM),
        (f"  {c('Totals', BOLD)}  "
         f"{c(str(n_commits), WHITE, BOLD)} commits  ·  "
         f"{c(str(n_dacort), CYAN)} by dacort  ·  "
         f"{c(str(n_claude), MAGENTA)} by claude-os"),
        (f"           "
         f"{c(str(n_feat), GREEN)} features  ·  "
         f"{c(str(n_fix), YELLOW)} fixes  ·  "
         f"{c(str(n_workshop), MAGENTA)} workshop sessions"),
        "",
    ]
    return lines


# ── Compact mode ───────────────────────────────────────────────────────────────

def render_compact(events: list[TimelineEvent]) -> list[str]:
    """One-line-per-event compact view."""
    lines = []
    for ev in events:
        if ev.kind == "day-boundary":
            lines.append("")
            lines.append(c(f"── {ev.label} ──", BOLD, CYAN))
            continue
        time_str = ev.start.strftime("%H:%M")
        if ev.kind == "workshop":
            icon = c("⚗", MAGENTA, BOLD)
            label = c(f"workshop {ev.label}", MAGENTA)
            lines.append(f"  {c(time_str, DIM)}  {icon}  {label}  {c(ev.detail[:50], DIM)}")
        elif ev.kind == "task":
            icon = c("⚙", CYAN, BOLD)
            label = c(f"task {ev.label}", CYAN)
            lines.append(f"  {c(time_str, DIM)}  {icon}  {label}")
        else:
            cm = ev.commits[0] if ev.commits else None
            if not cm:
                continue
            icon = c(kind_icon(cm.kind), *kind_color(cm.kind))
            detail = ev.detail[:55]
            lines.append(f"  {c(time_str, DIM)}  {icon}  {c(cm.short_author, DIM):<12}  {detail}")
    return lines


# ── All commits mode ───────────────────────────────────────────────────────────

def render_all(commits: list[Commit]) -> list[str]:
    """Every commit, one per line, ungrouped."""
    lines = []
    current_date = None
    for cm in commits:
        date = cm.dt.date()
        if date != current_date:
            current_date = date
            label = f"  {cm.date_str}  ({cm.dt.strftime('%A')})  "
            pad = (WIDTH - len(label)) // 2
            lines.append("")
            lines.append(c("─" * pad, DIM) + c(label, BOLD, CYAN) + c("─" * (WIDTH - pad - len(label)), DIM))
            lines.append("")
        icon = c(kind_icon(cm.kind), *kind_color(cm.kind))
        author_part = c(f"{cm.short_author:<10}", DIM)
        label_part = c(f"[{cm.kind:<8}]", *kind_color(cm.kind))
        detail = cm.subject[:45]
        lines.append(f"  {c(cm.time_str, DIM)}  {author_part}  {icon}  {label_part}  {detail}")
    return lines


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    global _use_color

    parser = argparse.ArgumentParser(
        description="Visual ASCII timeline of claude-os history"
    )
    parser.add_argument("--all",     action="store_true", help="Show every commit ungrouped")
    parser.add_argument("--compact", action="store_true", help="One line per event")
    parser.add_argument("--plain",   action="store_true", help="No ANSI colour")
    parser.add_argument("--no-you",  action="store_true", help="Omit the 'you are here' marker")
    args = parser.parse_args()

    if args.plain or not sys.stdout.isatty():
        _use_color = False

    commits = load_commits()

    # Header
    print()
    title = "  claude-os timeline  "
    pad = (WIDTH - len(title)) // 2
    print(c("═" * pad, DIM) + c(title, BOLD, WHITE) + c("═" * (WIDTH - pad - len(title)), DIM))
    print()

    if args.all:
        for line in render_all(commits):
            print(line)
    elif args.compact:
        events = group_events(commits)
        for line in render_compact(events):
            print(line)
        if not args.no_you:
            for line in render_you_are_here():
                print(line)
    else:
        # Default: grouped view
        events = group_events(commits)
        for ev in events:
            if ev.kind == "day-boundary":
                for line in render_day_boundary(ev):
                    print(line)
            elif ev.kind == "task":
                for line in render_task_band(ev):
                    print(line)
                print()
            elif ev.kind == "workshop":
                for line in render_workshop_band(ev):
                    print(line)
                print()
            else:
                for line in render_commit_line(ev):
                    print(line)

        if not args.no_you:
            # Insert day boundary if today is different from last event's date
            today = datetime.date.today()
            last_event_date = None
            for ev in reversed(events):
                if ev.kind != "day-boundary":
                    last_event_date = ev.start.date()
                    break
            if last_event_date and last_event_date < today:
                day_ev = TimelineEvent(
                    kind="day-boundary",
                    start=datetime.datetime.combine(today, datetime.time.min, tzinfo=datetime.timezone.utc),
                    label=today.strftime("%Y-%m-%d  (%A)"),
                )
                for line in render_day_boundary(day_ev):
                    print(line)
            for line in render_you_are_here():
                print(line)

    # Summary footer
    for line in render_summary(commits):
        print(line)


if __name__ == "__main__":
    main()
