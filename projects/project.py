#!/usr/bin/env python3
"""
project.py — Project status and orientation for Claude OS.

Each project lives in projects/<name>/project.md with a YAML frontmatter block
defining its status, owner, backlog, memory, and decisions. This tool reads those
files and shows you what's active, what's done, and what's next — per-project or
across all of them.

Think of it as vitals.py, but for multi-session work units rather than the whole org.

Usage:
    python3 projects/project.py                   # list all projects
    python3 projects/project.py rag-indexer       # focused view of one project
    python3 projects/project.py --active          # only active projects
    python3 projects/project.py --plain           # no ANSI colors

Author: Claude OS (Workshop session 69, 2026-03-27)
"""

import argparse
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).parent.parent
PROJECTS_DIR = REPO / "projects"
TASKS_DIR = REPO / "tasks"

W = 66


# ── ANSI helpers ─────────────────────────────────────────────────────────────

def make_c(plain: bool):
    if plain:
        return lambda s, *a, **k: s

    def c(text, fg=None, bold=False, dim=False):
        codes = []
        if bold:  codes.append("1")
        if dim:   codes.append("2")
        fg_map = {
            "red": "31", "green": "32", "yellow": "33", "blue": "34",
            "magenta": "35", "cyan": "36", "white": "37", "grey": "90",
        }
        if fg and fg in fg_map:
            codes.append(fg_map[fg])
        if not codes:
            return text
        return f"\x1b[{';'.join(codes)}m{text}\x1b[0m"

    return c


def box(lines, width=W, plain=False):
    """Draw a simple rounded box around lines."""
    if plain:
        for l in lines:
            print(l)
        return
    print(f"\u256d{'─' * (width - 2)}\u256e")
    for l in lines:
        # strip ANSI codes for width calculation
        stripped = re.sub(r'\x1b\[[0-9;]*m', '', l)
        pad = width - 2 - len(stripped)
        print(f"\u2502 {l}{' ' * max(0, pad)}\u2502")
    print(f"\u2570{'─' * (width - 2)}\u256f")


# ── Parsing ───────────────────────────────────────────────────────────────────

def parse_frontmatter(text: str) -> tuple[dict, str]:
    """Parse YAML frontmatter from markdown. Returns (fm_dict, body)."""
    fm = {}
    if not text.startswith("---"):
        return fm, text
    end = text.find("\n---", 3)
    if end == -1:
        return fm, text
    front = text[3:end].strip()
    body = text[end + 4:].strip()
    for line in front.splitlines():
        if ":" in line:
            key, _, val = line.partition(":")
            val = val.strip().strip('"')
            fm[key.strip()] = val
    return fm, body


def parse_backlog(body: str) -> list[tuple[bool, str]]:
    """Extract checkbox items from markdown body."""
    items = []
    for line in body.splitlines():
        m = re.match(r'\s*-\s*\[([ xX])\]\s*(.*)', line)
        if m:
            done = m.group(1).lower() == 'x'
            label = m.group(2).strip()
            items.append((done, label))
    return items


def parse_section(body: str, heading: str) -> str:
    """Extract content under a markdown heading."""
    pattern = rf'^#{{1,3}}\s+{re.escape(heading)}\s*$'
    lines = body.splitlines()
    in_section = False
    result = []
    for line in lines:
        if re.match(pattern, line, re.IGNORECASE):
            in_section = True
            continue
        if in_section:
            if re.match(r'^#{1,3}\s+', line):
                break
            result.append(line)
    return "\n".join(result).strip()


def load_project(project_dir: Path) -> dict | None:
    """Load and parse a project.md file."""
    md = project_dir / "project.md"
    if not md.exists():
        return None
    text = md.read_text()
    fm, body = parse_frontmatter(text)
    if not fm.get("name"):
        fm["name"] = project_dir.name
    backlog = parse_backlog(body)
    memory = parse_section(body, "Memory")
    decisions = parse_section(body, "Decisions")
    goal = parse_section(body, "Goal")
    current_state = parse_section(body, "Current State")
    return {
        "name":          fm.get("name", project_dir.name),
        "title":         fm.get("title", project_dir.name),
        "status":        fm.get("status", "unknown"),
        "owner":         fm.get("owner", "—"),
        "reviewer":      fm.get("reviewer", "—"),
        "created":       fm.get("created", ""),
        "budget_model":  fm.get("budget", {}) if isinstance(fm.get("budget"), dict) else fm.get("model", ""),
        "path":          md,
        "backlog":       backlog,
        "memory":        memory,
        "decisions":     decisions,
        "goal":          goal,
        "current_state": current_state,
    }


def find_projects() -> list[dict]:
    """Find all project.md files under projects/."""
    projects = []
    for d in sorted(PROJECTS_DIR.iterdir()):
        if d.is_dir() and not d.name.startswith("."):
            p = load_project(d)
            if p:
                projects.append(p)
    return projects


# ── Git activity ──────────────────────────────────────────────────────────────

def recent_project_commits(project_name: str, n: int = 5) -> list[str]:
    """Find recent commits touching files in projects/<name>/ or mentioning the project."""
    try:
        # commits touching the project directory
        result = subprocess.run(
            ["git", "log", "--oneline", f"-{n * 3}",
             "--", f"projects/{project_name}/", f"tasks/**/"],
            capture_output=True, text=True, cwd=REPO
        )
        by_path = [l.strip() for l in result.stdout.strip().splitlines() if l.strip()]

        # commits whose message mentions the project name
        result2 = subprocess.run(
            ["git", "log", "--oneline", f"--grep={project_name}", f"-{n}"],
            capture_output=True, text=True, cwd=REPO
        )
        by_msg = [l.strip() for l in result2.stdout.strip().splitlines() if l.strip()]

        # merge and deduplicate, preserving order
        seen = set()
        merged = []
        for line in (by_path + by_msg):
            sha = line.split()[0]
            if sha not in seen:
                seen.add(sha)
                merged.append(line)
        return merged[:n]
    except Exception:
        return []


def task_activity(project_name: str) -> list[tuple[str, str, str]]:
    """Find completed tasks related to this project via plan_id."""
    results = []
    for state_dir in ["completed", "failed", "in-progress"]:
        d = TASKS_DIR / state_dir
        if not d.exists():
            continue
        for f in sorted(d.glob("*.md"), key=lambda x: x.stat().st_mtime, reverse=True):
            text = f.read_text()
            fm, _ = parse_frontmatter(text)
            if fm.get("plan_id", "").startswith(project_name) or project_name in fm.get("plan_id", ""):
                results.append((state_dir, f.stem, fm.get("created", "")))
    return results[:10]


# ── Display: single project ───────────────────────────────────────────────────

def show_project(p: dict, c, plain: bool):
    """Display a focused view of a single project."""
    status_color = {
        "active": "green", "proposed": "yellow",
        "paused": "grey", "completed": "cyan",
    }.get(p["status"], "white")

    backlog = p["backlog"]
    done_count = sum(1 for done, _ in backlog if done)
    total = len(backlog)
    pct = f"{done_count}/{total}" if total else "—"

    # Header box
    header_lines = [
        c(f"  {p['title']}", bold=True),
        c(f"  {p['name']}  ·  {p['status']}  ·  owner: {p['owner']}", dim=True),
    ]
    if p["reviewer"] and p["reviewer"] != "—":
        header_lines.append(c(f"  reviewer: {p['reviewer']}", dim=True))
    box(header_lines, plain=plain)

    # Goal
    if p["goal"]:
        print()
        print(c("  GOAL", bold=True))
        for line in p["goal"].splitlines():
            if line.strip():
                print(f"  {c(line.strip(), dim=True)}")

    # Current state
    if p["current_state"] and p["current_state"] != "_No sessions yet._":
        print()
        print(c("  CURRENT STATE", bold=True))
        for line in p["current_state"].splitlines():
            if line.strip():
                print(f"  {c(line.strip(), dim=True)}")

    # Backlog
    print()
    bar_filled = int((done_count / total * 20)) if total else 0
    bar = c("█" * bar_filled, fg="green") + c("░" * (20 - bar_filled), dim=True)
    print(f"  {c('BACKLOG', bold=True)}  {c(pct, fg='green' if done_count == total else 'yellow')}  {bar}")
    print()
    for done, label in backlog:
        mark = c("✓", fg="green") if done else c("·", dim=True)
        text = c(label, dim=True) if done else label
        print(f"    {mark}  {text}")

    # Decisions
    if p["decisions"]:
        print()
        print(c("  DECISIONS", bold=True))
        for line in p["decisions"].splitlines():
            line = line.strip()
            if line.startswith("-"):
                line = line[1:].strip()
            if line:
                print(f"    {c('·', dim=True)} {c(line, dim=True)}")

    # Memory
    mem = p["memory"]
    if mem and mem not in ("_No sessions yet._", ""):
        print()
        print(c("  MEMORY", bold=True))
        for line in mem.splitlines():
            if line.strip():
                print(f"  {c(line.strip(), dim=True)}")

    # Recent git activity
    commits = recent_project_commits(p["name"])
    if commits:
        print()
        print(c("  RECENT ACTIVITY", bold=True))
        for commit in commits:
            sha, _, msg = commit.partition(" ")
            print(f"    {c(sha[:7], fg='cyan')}  {c(msg, dim=True)}")

    # Related tasks
    tasks = task_activity(p["name"])
    if tasks:
        print()
        print(c("  RELATED TASKS", bold=True))
        for state, task_id, created in tasks:
            state_color = {"completed": "green", "failed": "red", "in-progress": "yellow"}.get(state, "grey")
            print(f"    {c(f'[{state}]', fg=state_color)}  {c(task_id, dim=True)}")

    print()


# ── Display: all projects ─────────────────────────────────────────────────────

def show_all(projects: list[dict], c, plain: bool, active_only: bool):
    """Display a summary list of all (or just active) projects."""
    if active_only:
        projects = [p for p in projects if p["status"] == "active"]

    if not projects:
        print(c("  No projects found.", dim=True))
        return

    active = [p for p in projects if p["status"] == "active"]
    other  = [p for p in projects if p["status"] != "active"]

    def show_group(title: str, group: list[dict]):
        if not group:
            return
        print()
        print(c(f"  {title}", bold=True))
        print(c("  " + "─" * (W - 4), dim=True))
        for p in group:
            backlog = p["backlog"]
            done = sum(1 for d, _ in backlog if d)
            total = len(backlog)
            pct = f"{done}/{total}" if total else "—"
            pct_color = "green" if done == total and total > 0 else "yellow"

            name_col = c(p["name"].ljust(20), fg="cyan")
            title_col = p["title"][:32].ljust(34)
            pct_col = c(pct.rjust(6), fg=pct_color)
            print(f"    {name_col}  {c(title_col, dim=True)}  {pct_col}")

    show_group("ACTIVE", active)
    show_group("OTHER", other)
    print()

    if not active_only and not active:
        print(c("  No active projects. dacort may need to activate one.", fg="yellow"))
        print()


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(description="Project status tool for Claude OS")
    ap.add_argument("project", nargs="?", help="Project name to show in detail")
    ap.add_argument("--active", action="store_true", help="Only show active projects")
    ap.add_argument("--plain", action="store_true", help="No ANSI colors")
    args = ap.parse_args()

    plain = args.plain or not sys.stdout.isatty()
    c = make_c(plain)

    projects = find_projects()

    if args.project:
        # focused view
        match = [p for p in projects if p["name"] == args.project]
        if not match:
            # try fuzzy match on name or title
            q = args.project.lower()
            match = [p for p in projects if q in p["name"].lower() or q in p["title"].lower()]
        if not match:
            print(c(f"  Project '{args.project}' not found.", fg="red"))
            print(c(f"  Available: {', '.join(p['name'] for p in projects)}", dim=True))
            sys.exit(1)
        show_project(match[0], c, plain)
    else:
        if not plain:
            print()
            print(c("  PROJECTS", bold=True) + c("  ·  claude-os", dim=True))
            print()
        show_all(projects, c, plain, args.active)


if __name__ == "__main__":
    main()
