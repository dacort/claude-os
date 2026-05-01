#!/usr/bin/env python3
"""
replay.py — Reconstruct the story of a task from git history

Given a task ID or title fragment, replay what happened: when the task arrived,
how long it waited in the queue, what commits happened during execution, and how
it ended. Reads task files + git log. No external dependencies.

The goal is to make any task's lifecycle legible — not just its status, but its
story. When did it land? How long did it sit? What agent picked it up? What did
the work look like from the outside?

Usage:
    python3 projects/replay.py <task-id-or-fragment>
    python3 projects/replay.py --recent       # replay the most recently completed task
    python3 projects/replay.py --list         # list all tasks with key stats
    python3 projects/replay.py --list --all   # include pending/in-progress
    python3 projects/replay.py --plain        # no ANSI colors
"""

import sys
import os
import re
import subprocess
import glob
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass, field
from typing import Optional

# ──────────────────────────────────────────────────────────────────────────────
# Configuration
# ──────────────────────────────────────────────────────────────────────────────

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TASK_DIRS = {
    "completed": os.path.join(REPO, "tasks", "completed"),
    "failed":    os.path.join(REPO, "tasks", "failed"),
    "pending":   os.path.join(REPO, "tasks", "pending"),
    "in-progress": os.path.join(REPO, "tasks", "in-progress"),
}

PLAIN = "--plain" in sys.argv

# ──────────────────────────────────────────────────────────────────────────────
# Color helpers
# ──────────────────────────────────────────────────────────────────────────────

def c(code, text):
    if PLAIN:
        return text
    return f"\033[{code}m{text}\033[0m"

def cyan(t):    return c("36", t)
def green(t):   return c("32", t)
def yellow(t):  return c("33", t)
def red(t):     return c("31", t)
def dim(t):     return c("2", t)
def bold(t):    return c("1", t)
def magenta(t): return c("35", t)
def blue(t):    return c("34", t)
def white(t):   return c("97", t)

# ──────────────────────────────────────────────────────────────────────────────
# Data structures
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class TaskFile:
    path: str
    task_id: str
    status: str         # completed / failed / pending / in-progress
    profile: str = ""
    priority: str = ""
    created: Optional[datetime] = None
    title: str = ""
    description: str = ""
    raw_content: str = ""

@dataclass
class WorkerInfo:
    agent: str = ""
    started: Optional[datetime] = None
    finished: Optional[datetime] = None
    exit_code: Optional[int] = None
    auth: str = ""
    excerpt: str = ""       # first interesting line of results

@dataclass
class Commit:
    hash: str
    timestamp: datetime
    message: str

@dataclass
class TimelineEvent:
    timestamp: Optional[datetime]
    kind: str           # created / started / commit / finished
    label: str
    detail: str = ""

# ──────────────────────────────────────────────────────────────────────────────
# Task file parsing
# ──────────────────────────────────────────────────────────────────────────────

def parse_frontmatter(content):
    """Extract YAML-ish frontmatter between --- delimiters. Returns dict."""
    meta = {}
    m = re.match(r"^---\n(.*?)\n---\n", content, re.DOTALL)
    if not m:
        return meta
    for line in m.group(1).splitlines():
        if ":" in line:
            key, _, val = line.partition(":")
            meta[key.strip()] = val.strip().strip('"')
    return meta

def parse_iso(s):
    """Parse ISO 8601 timestamp, return UTC datetime or None."""
    if not s:
        return None
    s = s.strip().rstrip("Z")
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    return None

def parse_task_file(path):
    """Read and parse a task file into a TaskFile struct."""
    with open(path) as f:
        content = f.read()

    filename = os.path.basename(path)
    task_id = filename.removesuffix(".md")

    # Determine status from directory name
    for status, dirpath in TASK_DIRS.items():
        if os.path.dirname(path) == dirpath:
            break
    else:
        status = "unknown"

    meta = parse_frontmatter(content)

    # Extract title (first # heading after frontmatter)
    title = ""
    m = re.search(r"^# (.+)$", content, re.MULTILINE)
    if m:
        title = m.group(1).strip()

    # Extract description section
    description = ""
    m = re.search(r"## Description\n(.*?)(?=\n## |\Z)", content, re.DOTALL)
    if m:
        description = m.group(1).strip()[:200]

    return TaskFile(
        path=path,
        task_id=task_id,
        status=status,
        profile=meta.get("profile", ""),
        priority=meta.get("priority", ""),
        created=parse_iso(meta.get("created", "")),
        title=title,
        description=description,
        raw_content=content,
    )

def parse_worker_info(content):
    """Extract worker timing and metadata from the Results/Failure section."""
    info = WorkerInfo()

    # Agent type from header line
    m = re.search(r"=== Claude OS Worker(?: v\d+)? ===", content)
    if m:
        header = m.group(0)
        # Agent: line follows
        am = re.search(r"Agent: (.+)", content)
        if am:
            info.agent = am.group(1).strip()
        else:
            info.agent = "claude"

    # Started / Finished timestamps
    m = re.search(r"Started: (\S+)", content)
    if m:
        info.started = parse_iso(m.group(1))
    m = re.search(r"Finished: (\S+)", content)
    if m:
        info.finished = parse_iso(m.group(1))

    # Exit code
    m = re.search(r"Exit code: (\d+)", content)
    if m:
        info.exit_code = int(m.group(1))

    # Auth line
    m = re.search(r"Auth: (.+)", content)
    if m:
        info.auth = m.group(1).strip()

    # Extract first substantive paragraph of actual results.
    # Structure: === Claude OS Worker === / header / --- / results / --- / === Worker Complete ===
    worker_m = re.search(
        r"=== Claude OS Worker.*?\n(.*?)\n---\n(.*?)(?=\n---\n=== Worker Complete|\Z)",
        content, re.DOTALL
    )
    if worker_m:
        results_body = worker_m.group(2).strip()
        # Split on --- again (Claude sometimes uses --- as section dividers in output)
        sections = re.split(r"\n---\n", results_body)
        for section in sections:
            paragraphs = [p.strip() for p in section.split("\n\n") if p.strip()]
            for para in paragraphs:
                # Skip metadata lines and very short things
                lines = para.splitlines()
                real_lines = [l for l in lines
                              if not re.match(r"^(Started|Finished|Exit|Auth|Agent|Profile|Task ID|Cloning|Running|Injecting):", l)
                              and not re.match(r"^#+ ", l)          # skip headings
                              and not re.match(r"^\|", l)           # skip table rows
                              and not re.match(r"^Now I |^Let me |^I'll |^I need |^OK,", l)
                              and len(l.strip()) > 20]
                if real_lines and len(" ".join(real_lines)) > 40:
                    excerpt = " ".join(real_lines[:2])
                    # Clean markdown formatting
                    excerpt = re.sub(r"\*\*([^*]+)\*\*", r"\1", excerpt)
                    excerpt = re.sub(r"[#*`\[\]]", "", excerpt).strip()
                    if len(excerpt) > 20:
                        info.excerpt = excerpt[:180]
                        break
            if info.excerpt:
                break

    return info

# ──────────────────────────────────────────────────────────────────────────────
# Git history
# ──────────────────────────────────────────────────────────────────────────────

def git_commits_for_task(task_id):
    """Search git log for commits mentioning this task ID."""
    pattern = f"task {task_id}[: ]"
    try:
        result = subprocess.run(
            ["git", "log", "--all", "--format=%H %aI %s", f"--grep={pattern}"],
            capture_output=True, text=True, cwd=REPO
        )
        commits = []
        for line in result.stdout.splitlines():
            if not line.strip():
                continue
            parts = line.split(" ", 2)
            if len(parts) < 3:
                continue
            h, ts, msg = parts[0], parts[1], parts[2]
            # Normalize ISO 8601 → plain datetime string
            ts_clean = ts.replace("T", " ")
            if "+" in ts_clean:
                ts_clean = ts_clean[:ts_clean.index("+")]
            elif ts_clean.endswith("Z"):
                ts_clean = ts_clean[:-1]
            dt = parse_iso(ts_clean)
            if dt:
                commits.append(Commit(hash=h[:8], timestamp=dt, message=msg))
        commits.sort(key=lambda c: c.timestamp)
        return commits
    except Exception:
        return []

def git_commit_timestamp(hash_prefix):
    """Get timestamp for a specific commit hash."""
    try:
        result = subprocess.run(
            ["git", "show", "-s", "--format=%aI", hash_prefix],
            capture_output=True, text=True, cwd=REPO
        )
        ts = result.stdout.strip()
        return parse_iso(ts.replace("T", " ").rstrip("Z"))
    except Exception:
        return None

# ──────────────────────────────────────────────────────────────────────────────
# Timeline construction
# ──────────────────────────────────────────────────────────────────────────────

def build_timeline(task, worker, commits):
    """Assemble ordered timeline events from all sources."""
    events = []

    if task.created:
        events.append(TimelineEvent(
            timestamp=task.created,
            kind="created",
            label="Created",
            detail=f"Arrived in the pending queue · {task.profile or '?'} profile · {task.priority or 'normal'} priority",
        ))

    # Add commits — decode their meaning
    for commit in commits:
        msg = commit.message
        if "pending → in-progress" in msg:
            kind = "started"
            label = "Picked up"
            detail = f"A worker claimed the task  {dim(commit.hash)}"
        elif "in-progress → completed" in msg or "in-progress → failed" in msg:
            kind = "transition"
            outcome = "completed" if "completed" in msg else "failed"
            label = f"Status → {outcome}"
            detail = dim(commit.hash)
        elif "add results" in msg:
            kind = "results"
            label = "Results committed"
            detail = dim(commit.hash)
        elif "failed —" in msg:
            kind = "failure"
            label = "Failed"
            # Extract error hint from commit message — trim worker header boilerplate
            raw = msg.split("failed —", 1)[-1].strip() if "failed —" in msg else ""
            # Look for ERROR:, Credit balance, or known failure patterns in the flat string
            error_hint = ""
            for pattern in [r"ERROR: (.{10,80})", r"(Credit balance[^.\n]+)", r"(Permission denied[^.\n]+)"]:
                em = re.search(pattern, raw)
                if em:
                    error_hint = em.group(1).strip()[:80]
                    break
            if not error_hint:
                error_hint = dim(commit.hash)
            detail = error_hint
        else:
            kind = "commit"
            label = "Commit"
            detail = f"{msg}  {dim(commit.hash)}"

        events.append(TimelineEvent(
            timestamp=commit.timestamp,
            kind=kind,
            label=label,
            detail=detail,
        ))

    # Add worker timing if available and not already covered by commits
    if worker.started and not any(e.kind == "started" for e in events):
        events.append(TimelineEvent(
            timestamp=worker.started,
            kind="started",
            label="Worker started",
            detail=f"Agent: {worker.agent or 'claude'}",
        ))

    if worker.finished and not any(e.kind == "transition" for e in events):
        events.append(TimelineEvent(
            timestamp=worker.finished,
            kind="finished",
            label="Worker finished",
            detail=f"Exit code: {worker.exit_code}",
        ))

    # Sort by timestamp, putting None-timestamp events at end
    events.sort(key=lambda e: (e.timestamp is None, e.timestamp or datetime.min.replace(tzinfo=timezone.utc)))

    return events

# ──────────────────────────────────────────────────────────────────────────────
# Time formatting helpers
# ──────────────────────────────────────────────────────────────────────────────

def fmt_dt(dt):
    """Format a datetime as human-readable UTC."""
    if dt is None:
        return "unknown"
    return dt.strftime("%Y-%m-%d %H:%M UTC")

def fmt_duration(td):
    """Format a timedelta as a human-readable string."""
    if td is None:
        return "unknown"
    total_seconds = int(td.total_seconds())
    if total_seconds < 0:
        return "unknown"
    if total_seconds < 60:
        return f"{total_seconds}s"
    if total_seconds < 3600:
        m, s = divmod(total_seconds, 60)
        return f"{m}m {s}s"
    h, rem = divmod(total_seconds, 3600)
    m = rem // 60
    return f"{h}h {m}m"

def relative_to(dt, base):
    """Return a relative label like '+3m 14s' from a base time."""
    if dt is None or base is None:
        return ""
    td = dt - base
    total = int(td.total_seconds())
    if total < 0:
        return ""
    if total < 60:
        return f"+{total}s"
    m, s = divmod(total, 60)
    if m < 60:
        return f"+{m}m {s}s"
    h, rem = divmod(total, 3600)
    return f"+{h}h {rem//60}m"

# ──────────────────────────────────────────────────────────────────────────────
# Rendering
# ──────────────────────────────────────────────────────────────────────────────

KIND_COLORS = {
    "created":    cyan,
    "started":    green,
    "transition": yellow,
    "results":    blue,
    "failure":    red,
    "finished":   yellow,
    "commit":     dim,
}

def render_replay(task, worker, timeline):
    """Render the full narrative for a task."""
    W = 68

    def rule(ch="─"):
        return ch * W

    # Header
    status_color = green if task.status == "completed" else (red if task.status == "failed" else yellow)
    print()
    print(bold(f"  Task Replay: {cyan(task.task_id)}"))
    print(dim(f"  {task.title}") if task.title != task.task_id and task.title else "")
    print()

    # Overview strip
    tags = []
    if task.profile:
        tags.append(f"profile:{task.profile}")
    if task.priority and task.priority != "normal":
        tags.append(f"priority:{task.priority}")
    if worker.agent:
        tags.append(f"agent:{worker.agent}")
    if tags:
        print(f"  {dim('  ·  '.join(tags))}")
        print()

    # Find key timestamps
    created_ts = task.created
    started_ts = worker.started
    if not started_ts:
        for e in timeline:
            if e.kind == "started":
                started_ts = e.timestamp
                break
    finished_ts = worker.finished
    if not finished_ts:
        for e in timeline:
            if e.kind in ("transition", "finished") and e.timestamp:
                finished_ts = e.timestamp

    # Wait and run duration
    wait_time = (started_ts - created_ts) if (created_ts and started_ts) else None
    run_time = (finished_ts - started_ts) if (started_ts and finished_ts) else None

    if wait_time is not None or run_time is not None:
        parts = []
        if wait_time is not None:
            parts.append(f"waited {bold(fmt_duration(wait_time))} in queue")
        if run_time is not None:
            parts.append(f"ran for {bold(fmt_duration(run_time))}")
        print(f"  {',  '.join(parts)}")
        print()

    # Timeline
    print(f"  {dim(rule())}")
    base = timeline[0].timestamp if timeline else None
    for event in timeline:
        col = KIND_COLORS.get(event.kind, dim)
        ts_str = fmt_dt(event.timestamp) if event.timestamp else "       —      "
        rel = relative_to(event.timestamp, base) if event.timestamp and base else ""
        label = col(f"  {event.label:<20}")
        ts_display = dim(ts_str)
        rel_display = dim(f"  {rel:<10}") if rel else " " * 12

        print(f"  {label}  {ts_display}{rel_display}")
        if event.detail and event.kind not in ("commit", "started") or event.kind == "started":
            print(f"  {' ' * 22}{dim(event.detail)}")

    print(f"  {dim(rule())}")
    print()

    # Outcome
    outcome_color = green if task.status == "completed" else (red if task.status == "failed" else yellow)
    exit_str = ""
    if worker.exit_code is not None:
        exit_str = f"  (exit {worker.exit_code})"
    print(f"  Outcome: {outcome_color(bold(task.status))}{dim(exit_str)}")
    print()

    # Results excerpt
    if worker.excerpt:
        print(f"  {dim('Results excerpt:')}")
        # Word-wrap the excerpt at W-4 chars
        words = worker.excerpt.split()
        line = "    "
        for word in words:
            if len(line) + len(word) + 1 > W - 4:
                print(f"  {dim(line)}")
                line = "    " + word
            else:
                line += (" " if line.strip() else "") + word
        if line.strip():
            print(f"  {dim(line)}")
        print()

    # Description snippet
    if task.description:
        desc_short = task.description.splitlines()[0][:W - 4]
        if desc_short:
            print(f"  {dim('Task asked:')} {desc_short}")
            print()

# ──────────────────────────────────────────────────────────────────────────────
# List mode
# ──────────────────────────────────────────────────────────────────────────────

def render_list(tasks_by_status, show_all=False):
    """Render a tabular list of all tasks."""
    print()
    print(bold("  Task Registry"))
    print()

    statuses = ["completed", "failed"] if not show_all else ["completed", "failed", "in-progress", "pending"]
    total = 0

    for status in statuses:
        tasks = tasks_by_status.get(status, [])
        if not tasks:
            continue

        status_color = green if status == "completed" else (red if status == "failed" else yellow)
        print(f"  {status_color(status.upper())}  {dim(f'({len(tasks)})')}")

        for task in sorted(tasks, key=lambda t: t.created or datetime.min.replace(tzinfo=timezone.utc)):
            created_str = task.created.strftime("%m-%d %H:%M") if task.created else "       "
            title_short = (task.title[:42] + "…") if len(task.title) > 42 else task.title
            profile_str = dim(f"[{task.profile}]") if task.profile else "      "
            print(f"    {dim(created_str)}  {cyan(task.task_id):<36} {profile_str}  {dim(title_short)}")
            total += 1
        print()

    print(f"  {dim(f'{total} tasks listed')}")
    print()

# ──────────────────────────────────────────────────────────────────────────────
# Task finding
# ──────────────────────────────────────────────────────────────────────────────

def find_all_task_files(include_pending=False):
    """Return list of (status, path) for all task files."""
    results = []
    statuses = ["completed", "failed"]
    if include_pending:
        statuses += ["in-progress", "pending"]

    for status in statuses:
        dirpath = TASK_DIRS.get(status, "")
        if not os.path.isdir(dirpath):
            continue
        for path in sorted(glob.glob(os.path.join(dirpath, "*.md"))):
            results.append((status, path))
    return results

def find_task(fragment, include_pending=False):
    """
    Find a task file by ID (exact) or fragment (partial match).
    Returns TaskFile or None.
    """
    all_tasks = find_all_task_files(include_pending=include_pending)

    # Exact match first
    for status, path in all_tasks:
        task_id = os.path.basename(path).removesuffix(".md")
        if task_id == fragment:
            return parse_task_file(path)

    # Partial match
    matches = []
    for status, path in all_tasks:
        task_id = os.path.basename(path).removesuffix(".md")
        if fragment.lower() in task_id.lower():
            matches.append(path)

    if len(matches) == 1:
        return parse_task_file(matches[0])
    if len(matches) > 1:
        print(f"\n  Multiple matches for {repr(fragment)}:")
        for p in matches:
            print(f"    {os.path.relpath(p, REPO)}")
        print()
        return None

    return None

def find_most_recent(status="completed"):
    """Find the most recently created task file with given status (by created: timestamp)."""
    dirpath = TASK_DIRS.get(status, "")
    if not os.path.isdir(dirpath):
        return None

    tasks = []
    for path in glob.glob(os.path.join(dirpath, "*.md")):
        try:
            task = parse_task_file(path)
            tasks.append(task)
        except Exception:
            pass

    # Sort by created timestamp descending — tasks with timestamps first, then by date
    _min = datetime.min.replace(tzinfo=timezone.utc)
    tasks.sort(
        key=lambda t: (t.created is not None, t.created or _min),
        reverse=True
    )
    return tasks[0] if tasks else None

# ──────────────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────────────

def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    flags = [a for a in sys.argv[1:] if a.startswith("--")]

    show_list = "--list" in flags
    show_all = "--all" in flags
    recent = "--recent" in flags

    if show_list:
        # Build map of status → [TaskFile]
        tasks_by_status = {}
        all_files = find_all_task_files(include_pending=show_all)
        for status, path in all_files:
            try:
                task = parse_task_file(path)
                tasks_by_status.setdefault(status, []).append(task)
            except Exception:
                pass
        render_list(tasks_by_status, show_all=show_all)
        return

    if recent:
        task = find_most_recent("completed")
        if not task:
            task = find_most_recent("failed")
        if not task:
            print("No recent completed or failed tasks found.")
            sys.exit(1)
    elif args:
        task = find_task(args[0], include_pending=show_all)
        if not task:
            print(f"\n  Task {repr(args[0])} not found.")
            print(f"  Try: python3 projects/replay.py --list")
            sys.exit(1)
    else:
        print(__doc__)
        sys.exit(0)

    # Parse worker output from task file content
    worker = parse_worker_info(task.raw_content)

    # Get git commits
    commits = git_commits_for_task(task.task_id)

    # Build and render timeline
    timeline = build_timeline(task, worker, commits)
    render_replay(task, worker, timeline)


if __name__ == "__main__":
    main()
