#!/usr/bin/env python3
"""
vitals.py — Organizational health scorecard for Claude OS

While homelab-pulse.py measures the *hardware* (CPU, memory, disk), vitals.py
measures the *system* — how well claude-os is performing as an autonomous agent
platform. Think of it as a periodic checkup: are tasks getting done? Is the
codebase growing healthily? Are Workshop sessions productive?

Reads from: git log, tasks/, projects/, knowledge/
Requires: stdlib only, git in PATH

Usage:
    python3 projects/vitals.py              # Full report
    python3 projects/vitals.py --plain      # No ANSI colors
    python3 projects/vitals.py --json       # JSON output for scripting
    python3 projects/vitals.py --brief      # Single-line health summary

Author: Claude OS (Workshop session 6, 2026-03-11)
"""

import argparse
import datetime
import json
import os
import pathlib
import re
import subprocess
import sys

# ── ANSI colours ──────────────────────────────────────────────────────────────

RESET   = "\033[0m"
BOLD    = "\033[1m"
DIM     = "\033[2m"
CYAN    = "\033[36m"
GREEN   = "\033[32m"
YELLOW  = "\033[33m"
RED     = "\033[31m"
MAGENTA = "\033[35m"
BLUE    = "\033[34m"
WHITE   = "\033[97m"

USE_COLOR = True

def c(text, *codes):
    if not USE_COLOR:
        return str(text)
    return "".join(codes) + str(text) + RESET


# ── Paths ─────────────────────────────────────────────────────────────────────

REPO = pathlib.Path(__file__).parent.parent
TASKS_DIR = REPO / "tasks"
PROJECTS_DIR = REPO / "projects"
KNOWLEDGE_DIR = REPO / "knowledge"
LOGS_DIR = REPO / "logs"


# ── Git helpers ───────────────────────────────────────────────────────────────

def git(*args):
    """Run a git command and return stdout lines."""
    result = subprocess.run(
        ["git", "-C", str(REPO)] + list(args),
        capture_output=True, text=True
    )
    if result.returncode != 0:
        return []
    return result.stdout.strip().splitlines()


def git_str(*args):
    lines = git(*args)
    return lines[0] if lines else ""


# ── Data collectors ───────────────────────────────────────────────────────────

def collect_git_stats():
    """Analyze the git history for commit patterns."""
    # All commits with format: hash|author_email|timestamp_unix|subject
    raw = git("log", "--format=%H|%ae|%at|%s", "--all")

    commits = []
    for line in raw:
        parts = line.split("|", 3)
        if len(parts) < 4:
            continue
        h, email, ts, subject = parts
        try:
            ts = int(ts)
        except ValueError:
            ts = 0
        commits.append({
            "hash": h,
            "email": email,
            "ts": ts,
            "subject": subject,
            "is_claude": "claude-os" in email,
            "is_dacort": "dacort" in email or "d.lifehacker" in email,
        })

    if not commits:
        return {}

    first_ts = min(c["ts"] for c in commits)
    last_ts  = max(c["ts"] for c in commits)
    project_age_days = max(1, (last_ts - first_ts) // 86400)

    claude_commits = [c for c in commits if c["is_claude"]]
    dacort_commits = [c for c in commits if c["is_dacort"]]

    # Commits per day (since first commit)
    total_days = max(1, project_age_days)
    velocity = round(len(commits) / total_days, 1)

    # Task lifecycle commits (e.g., "task foo: pending → in-progress")
    lifecycle_pattern = re.compile(r"^task .+: (pending|in-progress|completed|failed)")
    lifecycle_commits = [c for c in commits if lifecycle_pattern.match(c["subject"])]

    # Workshop commits
    workshop_pattern = re.compile(r"^workshop")
    workshop_commits = [c for c in commits if workshop_pattern.match(c["subject"])]

    # Recent activity (last 7 days)
    week_ago = last_ts - (7 * 86400)
    recent_commits = [c for c in commits if c["ts"] >= week_ago]

    return {
        "total": len(commits),
        "claude": len(claude_commits),
        "dacort": len(dacort_commits),
        "velocity": velocity,
        "project_age_days": project_age_days,
        "lifecycle": len(lifecycle_commits),
        "workshop": len(workshop_commits),
        "recent_7d": len(recent_commits),
        "first_ts": first_ts,
        "last_ts": last_ts,
    }


def collect_task_stats():
    """Analyze task files across all states."""
    stats = {
        "completed": 0,
        "failed": 0,
        "failed_credit": 0,   # quota/credit infra failures — not real task failures
        "in_progress": 0,
        "pending": 0,
        "workshop_completed": 0,
        "task_types": {},
        "durations": [],
    }

    for state in ("completed", "failed", "in-progress", "pending"):
        dir_path = TASKS_DIR / state
        if not dir_path.exists():
            continue

        key = state.replace("-", "_")
        files = [f for f in dir_path.iterdir()
                 if f.suffix == ".md" and f.name != ".gitkeep"]

        stats[key] = len(files)

        for f in files:
            try:
                text = f.read_text()
            except Exception:
                continue

            # Is this a quota/credit infrastructure failure? (not a real task failure)
            # Two patterns:
            #   API key: "Credit balance is too low"
            #   OAuth/subscription: "You're out of extra usage"
            if state == "failed" and (
                "credit balance is too low" in text.lower()
                or "you're out of extra usage" in text.lower()
                or "out of extra usage" in text.lower()
            ):
                stats["failed_credit"] += 1

            # Is this a Workshop task?
            if "workshop" in f.name.lower() or "workshop" in text[:200].lower():
                if state == "completed":
                    stats["workshop_completed"] += 1

            # Extract priority/profile from frontmatter
            prio_match = re.search(r"^priority:\s*(\S+)", text, re.MULTILINE)
            if prio_match:
                prio = prio_match.group(1).strip('"')
                stats["task_types"][prio] = stats["task_types"].get(prio, 0) + 1

    # Completion rate — exclude credit failures (infra issues, not task failures)
    real_failed = stats["failed"] - stats["failed_credit"]
    total_finished = stats["completed"] + real_failed
    stats["completion_rate"] = (
        round(stats["completed"] / total_finished * 100, 1)
        if total_finished > 0 else None
    )
    stats["real_tasks_completed"] = stats["completed"] - stats["workshop_completed"]

    return stats


def collect_project_stats():
    """Analyze the projects/ directory."""
    py_files = list(PROJECTS_DIR.glob("*.py"))
    md_files = list(PROJECTS_DIR.glob("field-notes*.md"))

    total_lines = 0
    for f in py_files:
        try:
            total_lines += len(f.read_text().splitlines())
        except Exception:
            pass

    return {
        "python_tools": len(py_files),
        "field_notes": len(md_files),
        "total_lines": total_lines,
        "tool_names": sorted(f.stem for f in py_files),
    }


def collect_knowledge_stats():
    """Count knowledge artifacts."""
    if not KNOWLEDGE_DIR.exists():
        return {"files": 0, "dirs": 0}

    all_md = list(KNOWLEDGE_DIR.rglob("*.md"))
    all_dirs = [d for d in KNOWLEDGE_DIR.rglob("*") if d.is_dir()]

    return {
        "files": len(all_md),
        "dirs": len(all_dirs),
    }


# ── Grading ───────────────────────────────────────────────────────────────────

def grade(score):
    """Convert a 0-100 score to a letter grade."""
    if score >= 95: return "A+"
    if score >= 90: return "A"
    if score >= 85: return "A-"
    if score >= 80: return "B+"
    if score >= 75: return "B"
    if score >= 70: return "B-"
    if score >= 60: return "C+"
    if score >= 50: return "C"
    return "D"


def grade_color(g):
    if g.startswith("A"): return GREEN
    if g.startswith("B"): return YELLOW
    return RED


def compute_health(git_stats, task_stats, project_stats):
    """Compute overall health scores in each dimension."""
    scores = {}

    # Task health (0-100)
    # Penalize for failed tasks, reward for completions and low pending backlog
    cr = task_stats.get("completion_rate")
    if cr is None:
        task_score = 60  # No data — neutral
    else:
        task_score = cr  # completion rate is 0-100
        # Bonus if backlog is clean
        if task_stats["pending"] == 0:
            task_score = min(100, task_score + 5)
        # Penalty for high in-progress
        if task_stats["in_progress"] > 2:
            task_score -= 10
    scores["tasks"] = max(0, min(100, round(task_score)))

    # Commit health (0-100)
    # Healthy if velocity > 1/day, both authors are active
    vel = git_stats.get("velocity", 0)
    commit_score = min(100, vel * 30)  # 3.3 commits/day = 100
    # Reward for both authors contributing
    total = git_stats.get("total", 1)
    claude_pct = git_stats.get("claude", 0) / total
    dacort_pct = git_stats.get("dacort", 0) / total
    # Healthy mix: neither side should dominate 90%+
    if 0.2 <= claude_pct <= 0.8:
        commit_score = min(100, commit_score + 15)
    scores["commits"] = max(0, min(100, round(commit_score)))

    # Workshop productivity (0-100)
    # Based on projects built and sessions run
    proj_score = min(100, project_stats["python_tools"] * 8)  # 12 tools = 96
    notes_bonus = min(10, project_stats["field_notes"] * 2)
    scores["workshop"] = max(0, min(100, round(proj_score + notes_bonus)))

    # Overall: weighted average
    overall = (
        scores["tasks"]    * 0.40 +
        scores["commits"]  * 0.25 +
        scores["workshop"] * 0.35
    )
    scores["overall"] = round(overall)

    return scores


# ── Rendering helpers ─────────────────────────────────────────────────────────

WIDTH = 64

def box_top():
    return "╭" + "─" * (WIDTH - 2) + "╮"

def box_bot():
    return "╰" + "─" * (WIDTH - 2) + "╯"

def box_sep():
    return "├" + "─" * (WIDTH - 2) + "┤"

def box_row(left="", right="", left_pad=2, right_pad=2):
    """Format a row fitting inside WIDTH. Pads or truncates as needed."""
    inner = WIDTH - 2
    left_str  = " " * left_pad  + left
    right_str = right + " " * right_pad

    # Strip ANSI for length calculation
    def visible_len(s):
        return len(re.sub(r"\033\[[^m]*m", "", s))

    ll = visible_len(left_str)
    rl = visible_len(right_str)
    gap = inner - ll - rl
    if gap < 0:
        # truncate right
        right_str = ""
        gap = inner - ll

    return "│" + left_str + " " * max(0, gap) + right_str + "│"

def bar(value, max_value, width=20, color=GREEN):
    """Render a filled bar."""
    filled = round((value / max_value) * width) if max_value > 0 else 0
    filled = max(0, min(width, filled))
    empty = width - filled
    b = c("▓" * filled, color) + c("░" * empty, DIM)
    return b

def fmt_ts(unix_ts):
    """Format a unix timestamp as a human date."""
    try:
        return datetime.datetime.utcfromtimestamp(unix_ts).strftime("%Y-%m-%d")
    except Exception:
        return "?"


# ── Report sections ───────────────────────────────────────────────────────────

def render_header(now_str):
    lines = []
    lines.append(box_top())
    title = c("  ⚕  claude-os vitals", BOLD, WHITE)
    date  = c(now_str, DIM)
    lines.append(box_row(title, date, left_pad=0, right_pad=2))
    lines.append(box_row(c("  Organizational health scorecard", DIM), "", left_pad=0))
    return lines


def render_task_health(ts, scores):
    lines = []
    lines.append(box_sep())
    lines.append(box_row(c("TASK HEALTH", BOLD, CYAN), "", left_pad=2))
    lines.append(box_row("", ""))

    real_failed_total = ts["failed"] - ts["failed_credit"]
    total_done = ts["completed"] + real_failed_total  # exclude infra failures
    cr = ts["completion_rate"]

    # Completion bar
    if total_done > 0:
        comp_bar = bar(ts["completed"], total_done, width=18,
                       color=GREEN if (cr or 0) >= 80 else YELLOW)
        cr_str = f"{cr:.0f}%" if cr is not None else "n/a"
        g = grade(cr or 0)
        gc = grade_color(g)
        grade_label = c(f"[{g}]", BOLD, gc)
        lines.append(box_row(
            f"  Completed  {comp_bar} {c(str(ts['completed']), BOLD, GREEN)}",
            f"Rate {c(cr_str, BOLD)}  {grade_label}"
        ))
        if real_failed_total > 0:
            fail_bar = bar(real_failed_total, total_done, width=18, color=RED)
            lines.append(box_row(
                f"  Failed     {fail_bar} {c(str(real_failed_total), BOLD, RED)}",
                ""
            ))
        elif ts["failed_credit"] > 0:
            lines.append(box_row(
                f"  Failed     {c('none (real)', DIM, GREEN)}",
                ""
            ))
        else:
            lines.append(box_row(
                f"  Failed     {c('none', DIM, GREEN)}",
                ""
            ))
        if ts["failed_credit"] > 0:
            lines.append(box_row(
                f"  {c('↯ Credit', DIM, YELLOW)}  "
                f"{c(str(ts['failed_credit']), BOLD, YELLOW)} infra failures "
                f"{c('(not counted)', DIM)}",
                ""
            ))
    else:
        lines.append(box_row(c("  No finished tasks yet", DIM), ""))

    # Breakdown: workshop vs real tasks
    wc = ts["workshop_completed"]
    rc = ts["real_tasks_completed"]
    lines.append(box_row("", ""))
    lines.append(box_row(
        f"  {c(str(rc), BOLD)} real tasks    {c(str(wc), BOLD)} workshop sessions",
        f"{c(str(ts['pending']), DIM)} pending"
    ))
    return lines


def render_commit_health(gs, scores):
    lines = []
    lines.append(box_sep())
    lines.append(box_row(c("COMMIT VELOCITY", BOLD, CYAN), "", left_pad=2))
    lines.append(box_row("", ""))

    total = gs.get("total", 0)
    claude_n = gs.get("claude", 0)
    dacort_n = gs.get("dacort", 0)
    vel = gs.get("velocity", 0)
    age = gs.get("project_age_days", 0)
    recent = gs.get("recent_7d", 0)

    # Contributor bars
    if total > 0:
        dac_bar = bar(dacort_n, total, width=14, color=BLUE)
        cla_bar = bar(claude_n, total, width=14, color=MAGENTA)
        lines.append(box_row(
            f"  dacort     {dac_bar} {c(str(dacort_n), BOLD, BLUE)}",
            f"of {c(str(total), BOLD)} total"
        ))
        lines.append(box_row(
            f"  claude-os  {cla_bar} {c(str(claude_n), BOLD, MAGENTA)}",
            ""
        ))
    else:
        lines.append(box_row(c("  No commits found", DIM), ""))

    lines.append(box_row("", ""))

    # Velocity and age
    vel_color = GREEN if vel >= 1.5 else YELLOW if vel >= 0.5 else RED
    # For very young projects (< 3 days), show "active" instead of velocity
    if age < 3:
        vel_display = c(f"{vel:.0f}/day", BOLD, vel_color) + c(" (new!)", DIM)
    else:
        vel_display = c(f"{vel:.1f}", BOLD, vel_color) + " commits/day"
    lines.append(box_row(
        f"  Velocity   {vel_display}",
        f"Age {c(str(age) + 'd', BOLD)}  Recent {c(str(recent), BOLD)}/7d"
    ))

    # First commit date
    first_date = fmt_ts(gs.get("first_ts", 0))
    lines.append(box_row(
        f"  Born       {c(first_date, DIM)}",
        ""
    ))
    return lines


def render_workshop_health(ps, ks, task_stats, scores):
    lines = []
    lines.append(box_sep())
    lines.append(box_row(c("WORKSHOP PRODUCTIVITY", BOLD, CYAN), "", left_pad=2))
    lines.append(box_row("", ""))

    sessions = task_stats["workshop_completed"]
    tools = ps["python_tools"]
    notes = ps["field_notes"]
    loc = ps["total_lines"]
    knowledge_files = ks["files"]

    proj_bar = bar(tools, 15, width=16, color=MAGENTA)
    lines.append(box_row(
        f"  Tools      {proj_bar} {c(str(tools), BOLD, MAGENTA)}",
        f"{c(str(sessions), BOLD)} sessions"
    ))

    loc_bar = bar(loc, 5000, width=16, color=CYAN)
    lines.append(box_row(
        f"  Code       {loc_bar} {c(str(loc), BOLD, CYAN)} lines",
        f"{c(str(notes), BOLD)} field notes"
    ))

    lines.append(box_row(
        f"  Knowledge  {c(str(knowledge_files), BOLD)} doc(s) in knowledge/",
        ""
    ))

    # List tool names, wrapping to fit inside the box
    tool_names = ps["tool_names"]
    if tool_names:
        inner = WIDTH - 6  # account for "│  " prefix and "  │" suffix
        current_line = ""
        first = True
        for name in tool_names:
            sep = "  ·  " if current_line else ""
            candidate = current_line + sep + name
            if len(candidate) > inner and current_line:
                prefix = "  " if first else "    "
                lines.append(box_row(c(prefix + current_line, DIM), "", left_pad=0))
                current_line = name
                first = False
            else:
                current_line = candidate
        if current_line:
            prefix = "  " if first else "    "
            lines.append(box_row(c(prefix + current_line, DIM), "", left_pad=0))

    return lines


def render_overall(scores):
    lines = []
    lines.append(box_sep())

    g = grade(scores["overall"])
    gc = grade_color(g)
    grade_label = c(f"  {g}  ", BOLD, gc)

    lines.append(box_row(
        c("OVERALL HEALTH", BOLD, CYAN),
        f"Grade: {grade_label}",
        left_pad=2
    ))
    lines.append(box_row("", ""))

    # Sub-scores
    for name, key, weight in [
        ("Tasks", "tasks", 40),
        ("Commits", "commits", 25),
        ("Workshop", "workshop", 35),
    ]:
        s = scores[key]
        sb = bar(s, 100, width=16, color=grade_color(grade(s)))
        g2 = grade(s)
        gc2 = grade_color(g2)
        lines.append(box_row(
            f"  {name:<10} {sb} {c(str(s), BOLD)}/100",
            c(f"[{g2}]", gc2)
        ))

    lines.append(box_row("", ""))

    # Commentary — honest assessment
    commentary = generate_commentary(scores)
    for note in commentary:
        lines.append(box_row(f"  {note}", "", left_pad=0))

    return lines


def generate_commentary(scores):
    """Generate honest, concise commentary on system health."""
    notes = []

    # Task dimension
    ts = scores["tasks"]
    if ts >= 90:
        notes.append(c("✓ ", GREEN) + "Tasks: completing reliably with no failures")
    elif ts >= 70:
        notes.append(c("~ ", YELLOW) + "Tasks: mostly healthy, some failures to review")
    else:
        notes.append(c("✗ ", RED) + "Tasks: completion rate needs attention")

    # Commit dimension
    cs = scores["commits"]
    if cs >= 80:
        notes.append(c("✓ ", GREEN) + "Commits: healthy velocity, balanced contributors")
    elif cs >= 50:
        notes.append(c("~ ", YELLOW) + "Commits: moderate velocity")
    else:
        notes.append(c("~ ", YELLOW) + "Commits: low velocity — project may be young")

    # Workshop dimension
    ws = scores["workshop"]
    if ws >= 90:
        notes.append(c("✓ ", GREEN) + "Workshop: strong creative output, rich knowledge base")
    elif ws >= 70:
        notes.append(c("~ ", YELLOW) + "Workshop: productive sessions, room to grow")
    else:
        notes.append(c("~ ", YELLOW) + "Workshop: early stage, keep building")

    return notes


# ── Main output ───────────────────────────────────────────────────────────────

def render_full_report(git_stats, task_stats, project_stats, knowledge_stats):
    scores = compute_health(git_stats, task_stats, project_stats)

    now_str = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")

    lines = []
    lines += render_header(now_str)
    lines += render_task_health(task_stats, scores)
    lines += render_commit_health(git_stats, scores)
    lines += render_workshop_health(project_stats, knowledge_stats, task_stats, scores)
    lines += render_overall(scores)
    lines.append(box_bot())

    return "\n".join(lines)


def render_brief(git_stats, task_stats, project_stats):
    scores = compute_health(git_stats, task_stats, project_stats)
    g = grade(scores["overall"])
    cr = task_stats.get("completion_rate")
    cr_str = f"{cr:.0f}%" if cr is not None else "n/a"
    vel = git_stats.get("velocity", 0)
    tools = project_stats["python_tools"]
    now = datetime.datetime.utcnow().strftime("%Y-%m-%d")
    return (
        f"claude-os vitals [{now}] — "
        f"health: {g}  "
        f"tasks: {task_stats['completed']} done / {cr_str} rate  "
        f"velocity: {vel:.1f}/day  "
        f"tools: {tools}"
    )


def render_json(git_stats, task_stats, project_stats, knowledge_stats):
    scores = compute_health(git_stats, task_stats, project_stats)
    return json.dumps({
        "generated": datetime.datetime.utcnow().isoformat() + "Z",
        "scores": scores,
        "grades": {k: grade(v) for k, v in scores.items()},
        "git": git_stats,
        "tasks": task_stats,
        "projects": project_stats,
        "knowledge": knowledge_stats,
    }, indent=2)


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    global USE_COLOR

    parser = argparse.ArgumentParser(
        description="claude-os organizational health scorecard"
    )
    parser.add_argument("--plain",  action="store_true", help="No ANSI colors")
    parser.add_argument("--json",   action="store_true", help="JSON output")
    parser.add_argument("--brief",  action="store_true", help="One-line summary")
    args = parser.parse_args()

    if args.plain or args.json or not sys.stdout.isatty():
        USE_COLOR = False

    git_stats       = collect_git_stats()
    task_stats      = collect_task_stats()
    project_stats   = collect_project_stats()
    knowledge_stats = collect_knowledge_stats()

    if args.json:
        print(render_json(git_stats, task_stats, project_stats, knowledge_stats))
    elif args.brief:
        print(render_brief(git_stats, task_stats, project_stats))
    else:
        print(render_full_report(git_stats, task_stats, project_stats, knowledge_stats))


if __name__ == "__main__":
    main()
