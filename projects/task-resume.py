#!/usr/bin/env python3
"""
task-resume.py — reconstruct task history from git log for resumption

The "conversation backend" from exoclaw-ideas.md (idea 3):
  Store LLM history in git log. Resume tasks by rehydrating from commits.

This tool does the rehydration half. Given a task ID, it reads:
  - Git commits mentioning that task ID
  - The task file itself (current state, description)
  - Diffs from non-status commits (what was actually changed)

Then produces two outputs:
  1. A human-readable timeline (for diagnostics and debugging)
  2. A --context block that can be injected into a resumed worker's system prompt

The --context output is designed for entrypoint.sh to consume when a task
is retried/resumed, giving the new worker full awareness of prior attempts.

Usage:
    python3 projects/task-resume.py <task-id>              # full timeline
    python3 projects/task-resume.py <task-id> --context    # inject-ready context block
    python3 projects/task-resume.py --list                 # tasks with prior attempts
    python3 projects/task-resume.py <task-id> --plain      # no ANSI

Author: Claude OS (Workshop session 37, 2026-03-15)
"""

import re
import sys
import subprocess
import argparse
from pathlib import Path
from datetime import datetime, timezone

REPO = Path(__file__).parent.parent
TASKS_DIRS = [
    REPO / "tasks" / "pending",
    REPO / "tasks" / "in-progress",
    REPO / "tasks" / "completed",
    REPO / "tasks" / "failed",
]
W = 64  # display width

# ─── ANSI helpers ─────────────────────────────────────────────────────────────

PLAIN = "--plain" in sys.argv


def c(code, text):
    if PLAIN:
        return text
    return f"\033[{code}m{text}\033[0m"


def dim(t):    return c("2", t)
def bold(t):   return c("1", t)
def cyan(t):   return c("36", t)
def green(t):  return c("32", t)
def yellow(t): return c("33", t)
def red(t):    return c("31", t)
def magenta(t): return c("35", t)
def gray(t):   return c("90", t)


# ─── Git helpers ───────────────────────────────────────────────────────────────

def git(*args, cwd=None):
    """Run a git command and return stdout. Returns empty string on error."""
    try:
        result = subprocess.run(
            ["git"] + list(args),
            capture_output=True, text=True,
            cwd=str(cwd or REPO)
        )
        return result.stdout.strip()
    except Exception:
        return ""


def get_task_commits(task_id: str) -> list[dict]:
    """
    Find all commits that mention this task ID in their message.
    Returns list of dicts with: hash, short_hash, date, message, author
    """
    raw = git(
        "log", "--all", "--reverse",
        f"--grep={task_id}",
        "--format=%H\x1f%h\x1f%aI\x1f%an\x1f%s",
    )
    if not raw:
        return []

    commits = []
    for line in raw.splitlines():
        parts = line.split("\x1f", 4)
        if len(parts) < 5:
            continue
        full_hash, short_hash, iso_date, author, subject = parts
        try:
            dt = datetime.fromisoformat(iso_date.replace("Z", "+00:00"))
        except ValueError:
            dt = None
        commits.append({
            "hash": full_hash,
            "short": short_hash,
            "date": dt,
            "author": author,
            "message": subject,
        })
    return commits


def classify_commit(message: str, task_id: str) -> str:
    """
    Classify a commit as one of:
      created    — task file was created
      started    — status: pending → in-progress
      completed  — status: in-progress → completed
      failed     — task marked failed
      results    — add results commit
      requeued   — task re-queued
      work       — actual worker output (the interesting one)
    """
    m = message.lower()
    if "pending → in-progress" in m or "pending -> in-progress" in m:
        return "started"
    if "in-progress → completed" in m or "in-progress -> completed" in m:
        return "completed"
    if "→ failed" in m or "-> failed" in m:
        return "failed"
    if "add results" in m:
        return "results"
    # Workshop completion (e.g. "workshop <id>: completed")
    if "workshop" in m and "completed" in m:
        return "completed"
    # re-queue: explicit re-queue commits (not initial dispatch)
    if "re-queue" in m or "requeue" in m:
        return "requeued"
    # Task creation: "task: add <id>" or "task: <id> (codex, ...)"
    # Distinguish from worker work commits by presence of parenthetical or "add" keyword
    if re.search(r"^task:\s*(add\s+)", m):
        return "created"
    if re.search(r"^task:\s*" + re.escape(task_id[:20].lower()) + r"\s*\(", m):
        return "created"
    # Anything else that mentions the task ID is worker work
    return "work"


def get_commit_files(commit_hash: str) -> list[tuple[str, str]]:
    """
    Return list of (status, filename) for files changed in a commit.
    Status is one of A (added), M (modified), D (deleted).
    """
    raw = git("show", "--name-status", "--format=", commit_hash)
    files = []
    for line in raw.splitlines():
        if not line.strip():
            continue
        parts = line.split("\t", 2)
        if len(parts) >= 2:
            status = parts[0][0]  # first char: A, M, D, R, etc.
            fname = parts[-1]     # last part handles renames "old\tnew"
            # Skip .pyc files
            if fname.endswith(".pyc"):
                continue
            files.append((status, fname))
    return files


def get_commit_stat(commit_hash: str) -> str:
    """Return the --stat summary for a commit (insertions/deletions)."""
    raw = git("show", "--stat", "--format=", commit_hash)
    lines = [l for l in raw.splitlines() if "changed" in l or "insertion" in l or "deletion" in l]
    return lines[-1].strip() if lines else ""


# ─── Task file helpers ─────────────────────────────────────────────────────────

def find_task_file(task_id: str) -> tuple[Path | None, str]:
    """
    Find the task file for a given ID. Returns (path, state).
    State is the directory name: pending / in-progress / completed / failed
    """
    for d in TASKS_DIRS:
        # Exact match
        p = d / f"{task_id}.md"
        if p.exists():
            return p, d.name
        # Prefix match (task IDs can be truncated)
        for f in d.glob("*.md"):
            if f.stem.startswith(task_id) or task_id.startswith(f.stem):
                return f, d.name
    return None, "unknown"


def parse_task_file(path: Path) -> dict:
    """Parse frontmatter and title from a task file."""
    text = path.read_text()
    result = {"title": "", "profile": "", "status": "", "description": ""}

    # Frontmatter
    fm_match = re.match(r"^---\n(.*?)\n---\n", text, re.DOTALL)
    if fm_match:
        fm = fm_match.group(1)
        for key in ("profile", "status", "priority", "agent", "created"):
            m = re.search(rf"^{key}:\s*(.+)$", fm, re.MULTILINE)
            if m:
                result[key] = m.group(1).strip().strip('"')

    # Title (first # heading)
    title_m = re.search(r"^#\s+(.+)$", text, re.MULTILINE)
    if title_m:
        result["title"] = title_m.group(1).strip()

    # Description section
    desc_m = re.search(r"## Description\n\n(.*?)(?=\n## |\Z)", text, re.DOTALL)
    if desc_m:
        result["description"] = desc_m.group(1).strip()[:500]

    return result


# ─── List tasks with prior attempts ────────────────────────────────────────────

def list_retried_tasks() -> list[tuple[str, int, str]]:
    """
    Find tasks that were retried (attempted more than once).
    Returns list of (task_id, attempt_count, current_state).
    """
    # Get all task-related commits
    raw = git(
        "log", "--all",
        "--format=%s",
        "--grep=pending → in-progress",
    )
    if not raw:
        raw = git("log", "--all", "--format=%s", "--grep=pending")

    # Count "started" events per task
    task_starts = {}
    for line in raw.splitlines():
        m = re.search(r"task ([a-z0-9-]+):", line)
        if m and ("pending → in-progress" in line or "pending -> in-progress" in line):
            tid = m.group(1)
            task_starts[tid] = task_starts.get(tid, 0) + 1

    results = []
    for tid, count in task_starts.items():
        if count >= 1:  # show all, mark retried ones
            _, state = find_task_file(tid)
            results.append((tid, count, state))

    results.sort(key=lambda x: -x[1])  # most attempts first
    return results


# ─── Format helpers ────────────────────────────────────────────────────────────

def format_date(dt: datetime | None) -> str:
    if dt is None:
        return "?"
    return dt.strftime("%Y-%m-%d %H:%M UTC")


def format_age(dt: datetime | None) -> str:
    if dt is None:
        return ""
    now = datetime.now(timezone.utc)
    delta = now - dt
    secs = int(delta.total_seconds())
    if secs < 3600:
        return f"{secs // 60}m ago"
    if secs < 86400:
        return f"{secs // 3600}h ago"
    return f"{secs // 86400}d ago"


COMMIT_ICONS = {
    "created":   ("📋", cyan),
    "started":   ("▶", green),
    "completed": ("✓", green),
    "failed":    ("✗", red),
    "results":   ("📎", gray),
    "requeued":  ("↺", yellow),
    "work":      ("◆", magenta),
}


# ─── Main display ──────────────────────────────────────────────────────────────

def show_timeline(task_id: str):
    """Print a human-readable task history timeline."""

    commits = get_task_commits(task_id)
    task_path, state = find_task_file(task_id)
    task_info = parse_task_file(task_path) if task_path else {}

    bar = "─" * W

    print(f"╭{bar}╮")
    print(f"│  {bold(cyan(f'Task: {task_id}'))}{'': <{W - 9 - len(task_id)}}│")
    if task_info.get("title"):
        title = task_info["title"][:W - 4]
        print(f"│  {dim(title)}{' ' * (W - 2 - len(title))}│")
    print(f"│{' ' * (W + 2)}│")

    # State line
    state_color = {"completed": green, "failed": red, "in-progress": yellow}.get(state, cyan)
    state_str = f"  State: {state_color(state)}"
    if task_info.get("profile"):
        state_str += f"  {dim('profile:')} {task_info['profile']}"
    if task_info.get("agent"):
        state_str += f"  {dim('agent:')} {task_info['agent']}"
    visible_len = len(re.sub(r'\033\[[0-9;]*m', '', state_str))
    pad = W - visible_len + 2
    print(f"│{state_str}{' ' * max(0, pad)}│")
    print(f"├{bar}┤")

    if not commits:
        msg = f"  No commits found for task ID: {task_id}"
        print(f"│{msg}{' ' * (W - len(msg) + 2)}│")
        print(f"╰{bar}╯")
        return

    # Attempt counter
    attempt = 0
    work_commits = []
    all_changed_files = set()

    for commit in commits:
        kind = classify_commit(commit["message"], task_id)
        icon, color_fn = COMMIT_ICONS.get(kind, ("·", dim))

        if kind == "started":
            attempt += 1
            print(f"│{' ' * (W + 2)}│")
            attempt_str = f"  Attempt {attempt}"
            print(f"│  {bold(f'Attempt {attempt}')}{' ' * (W - len(attempt_str) + 2)}│")

        date_str = format_age(commit["date"])
        msg = commit["message"]
        # Shorten: remove task_id prefix
        msg = re.sub(rf"^task {re.escape(task_id)}:\s*", "", msg)
        msg = re.sub(r"^workshop [a-z0-9-]+:\s*", "workshop: ", msg)
        display = f"  {color_fn(icon)} {msg}"
        visible = len(re.sub(r'\033\[[0-9;]*m', '', display))
        date_visible = len(date_str)
        gap = W - visible - date_visible - 2
        if gap < 1:
            display = display[:W - date_visible - 5] + "…"
            gap = 1
        print(f"│{display}{' ' * gap}{dim(date_str)}  │")

        # Show changed files for work commits
        if kind == "work":
            files = get_commit_files(commit["hash"])
            work_commits.append((commit, files))
            for status, fname in files[:5]:
                status_sym = {"A": green("+"), "M": yellow("~"), "D": red("-")}.get(status, "?")
                fline = f"      {status_sym} {gray(fname)}"
                fvis = len(re.sub(r'\033\[[0-9;]*m', '', fline))
                print(f"│{fline}{' ' * (W - fvis + 2)}│")
                all_changed_files.add(fname)
            if len(files) > 5:
                more = f"      {gray(f'... and {len(files) - 5} more files')}"
                mvis = len(re.sub(r'\033\[[0-9;]*m', '', more))
                print(f"│{more}{' ' * (W - mvis + 2)}│")

    print(f"│{' ' * (W + 2)}│")

    # Summary
    print(f"├{bar}┤")
    summary_lines = [
        f"  {dim('Commits:')} {len(commits)}  {dim('Attempts:')} {attempt}  {dim('Files touched:')} {len(all_changed_files)}",
    ]
    if task_path:
        summary_lines.append(f"  {dim('Task file:')} {task_path.relative_to(REPO)}")
    for sl in summary_lines:
        vis = len(re.sub(r'\033\[[0-9;]*m', '', sl))
        print(f"│{sl}{' ' * (W - vis + 2)}│")

    print(f"╰{bar}╯")

    if state in ("failed", "in-progress") and work_commits:
        print()
        print(f"  {yellow('Tip:')} {dim('Use --context to generate a resume block for this task.')}")

    print()


# ─── Context block (for injection into worker system prompt) ───────────────────

def generate_context_block(task_id: str) -> str:
    """
    Generate a context block for injecting into a resumed worker's system prompt.
    Format: plain text, no ANSI — this will be read by the worker agent.
    """
    commits = get_task_commits(task_id)
    task_path, state = find_task_file(task_id)
    task_info = parse_task_file(task_path) if task_path else {}

    lines = [
        "## Prior Attempt Context",
        "",
        f"This task ({task_id}) has been attempted before.",
        "The following is reconstructed from git history — what the previous worker did.",
        "Do not redo completed work. Resume from where the previous attempt left off.",
        "",
    ]

    if task_info.get("title"):
        lines.append(f"**Task:** {task_info['title']}")
    lines.append(f"**Current state:** {state}")
    lines.append("")

    # Timeline
    attempt = 0
    work_commits = []
    all_files = {}  # filename → last status

    lines.append("**History:**")
    for commit in commits:
        kind = classify_commit(commit["message"], task_id)
        date_str = format_date(commit["date"])

        if kind == "started":
            attempt += 1
            lines.append(f"- [{date_str}] Attempt {attempt} started")
        elif kind == "completed":
            lines.append(f"- [{date_str}] Marked completed")
        elif kind == "failed":
            lines.append(f"- [{date_str}] Marked failed")
        elif kind == "requeued":
            lines.append(f"- [{date_str}] Re-queued for retry")
        elif kind == "work":
            msg = re.sub(rf"^task {re.escape(task_id)}:\s*", "", commit["message"])
            lines.append(f"- [{date_str}] Worker commit: \"{msg}\" ({commit['short']})")
            files = get_commit_files(commit["hash"])
            work_commits.append((commit, files))
            for status, fname in files:
                all_files[fname] = status

    lines.append("")

    # Files changed
    if all_files:
        lines.append("**Files modified by prior attempts:**")
        for fname, status in sorted(all_files.items()):
            sym = {"A": "added", "M": "modified", "D": "deleted"}.get(status, "changed")
            lines.append(f"- `{fname}` ({sym})")
        lines.append("")

    # Advice based on state
    if state == "failed":
        lines.append("The previous attempt failed. Investigate what went wrong and complete the task.")
    elif state == "in-progress":
        lines.append("The previous attempt may have been interrupted (timeout/eviction).")
        lines.append("Check what was already committed and continue from there.")
    elif state == "completed":
        lines.append("Note: The task is already marked completed. Verify or extend the work if needed.")

    lines.append("")

    return "\n".join(lines)


# ─── Entrypoint ───────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Reconstruct task history from git log for resumption"
    )
    parser.add_argument("task_id", nargs="?", help="Task ID to inspect")
    parser.add_argument("--context", action="store_true",
                        help="Output inject-ready context block (no ANSI)")
    parser.add_argument("--list", action="store_true",
                        help="List all tasks with their attempt counts")
    parser.add_argument("--plain", action="store_true",
                        help="No ANSI colors")
    args = parser.parse_args()

    if args.list:
        tasks = list_retried_tasks()
        if not tasks:
            print("No task attempts found in git history.")
            return

        W2 = 70
        bar = "─" * W2
        print(f"╭{bar}╮")
        hdr = f"  {bold('Tasks with prior attempts')}"
        hdr_vis = len(re.sub(r'\033\[[0-9;]*m', '', hdr))
        print(f"│{hdr}{' ' * (W2 - hdr_vis + 2)}│")
        print(f"├{bar}┤")
        for tid, count, state in tasks:
            retry_flag = yellow("retried") if count > 1 else ""
            state_color = {"completed": green, "failed": red, "in-progress": yellow}.get(state, cyan)
            tid_trunc = tid[:38]
            count_str = f"{count}x"
            state_str = state_color(state)
            state_vis = len(re.sub(r'\033\[[0-9;]*m', '', state_str))
            # Build line parts
            left = f"  {tid_trunc}"
            left_pad = " " * (40 - len(tid_trunc))
            mid = f"{count_str}  {state_str}"
            mid_vis = len(count_str) + 2 + state_vis
            right_pad = " " * (12 - min(state_vis, 12))
            flag_str = f"  {retry_flag}" if retry_flag else ""
            flag_vis = len(re.sub(r'\033\[[0-9;]*m', '', flag_str))
            total_vis = len(left) + len(left_pad) + mid_vis + len(right_pad) + flag_vis
            end_pad = " " * max(0, W2 - total_vis)
            print(f"│{left}{left_pad}{mid}{right_pad}{flag_str}{end_pad}│")
        print(f"╰{bar}╯")
        return

    if not args.task_id:
        parser.print_help()
        sys.exit(1)

    if args.context:
        # Plain text output for injection into system prompt
        print(generate_context_block(args.task_id))
    else:
        show_timeline(args.task_id)


if __name__ == "__main__":
    main()
