#!/usr/bin/env python3
"""
new-task.py — Task creation wizard for Claude OS

Creates a properly-formatted task file in tasks/pending/ so the controller
will pick it up and dispatch it to a worker.

Usage:
  python3 projects/new-task.py                        # interactive mode
  python3 projects/new-task.py "Review my PR"         # quick with just title
  python3 projects/new-task.py --help                 # show help

Options:
  --title TEXT        Task title (required)
  --desc TEXT         Description (or read from stdin with -)
  --profile PROFILE   Resource profile: small | medium | large | burst
  --priority PRIORITY Priority: low | normal | high
  --repo URL          Target repository URL (optional)
  --dry-run           Preview without writing

Author: Claude OS (free-time project, 2026-03-10)
"""

import argparse
import datetime
import os
import re
import sys
import textwrap
from pathlib import Path


# ── ANSI helpers ───────────────────────────────────────────────────────────────
RESET  = "\033[0m"
BOLD   = "\033[1m"
DIM    = "\033[2m"
GREEN  = "\033[32m"
YELLOW = "\033[33m"
RED    = "\033[31m"
CYAN   = "\033[36m"
BLUE   = "\033[34m"
WHITE  = "\033[97m"

def c(text, *codes):
    if not sys.stdout.isatty():
        return str(text)
    return "".join(codes) + str(text) + RESET

def hr(char="─", width=60):
    return char * width


# ── Repo root detection ────────────────────────────────────────────────────────

def find_repo_root():
    """Walk up from cwd to find the claude-os repo root."""
    current = Path.cwd()
    for parent in [current, *current.parents]:
        if (parent / "tasks" / "pending").exists():
            return parent
    return None


# ── Slug generation ────────────────────────────────────────────────────────────

def slugify(text: str) -> str:
    """Turn a human title into a file-safe slug."""
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    text = re.sub(r"-+", "-", text)
    text = text.strip("-")
    # Truncate to keep IDs sane
    return text[:40]


def unique_id(slug: str, pending_dir: Path) -> str:
    """Append a counter if the slug already exists."""
    base = slug
    counter = 2
    while (pending_dir / f"{slug}.md").exists():
        slug = f"{base}-{counter}"
        counter += 1
    return slug


# ── Interactive prompts ────────────────────────────────────────────────────────

def prompt(label: str, default: str = "", required: bool = False) -> str:
    """Ask the user for input with a nice prompt."""
    while True:
        if default:
            display = f"{c(label, CYAN, BOLD)} [{c(default, DIM)}]: "
        else:
            display = f"{c(label, CYAN, BOLD)}: "

        try:
            value = input(display).strip()
        except (EOFError, KeyboardInterrupt):
            print()
            sys.exit(0)

        if not value:
            if default:
                return default
            if required:
                print(c("  ✗ This field is required.", RED))
                continue
        return value


def prompt_choice(label: str, choices: list, default: str) -> str:
    """Ask user to pick from a list."""
    options = "  ".join(
        c(f"[{c}]", BOLD) if c == default else f"[{c}]"
        for c in choices
    )
    print(f"{c(label, CYAN, BOLD)}:  {options}  (default: {c(default, BOLD)})")
    while True:
        try:
            value = input("  → ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            sys.exit(0)
        if not value:
            return default
        if value in choices:
            return value
        print(c(f"  ✗ Please choose one of: {', '.join(choices)}", RED))


def prompt_multiline(label: str) -> str:
    """Read multi-line input until a blank line or EOF."""
    print(f"{c(label, CYAN, BOLD)} {c('(blank line to finish)', DIM)}:")
    lines = []
    while True:
        try:
            line = input()
        except (EOFError, KeyboardInterrupt):
            break
        if not line and lines:
            break
        lines.append(line)
    return "\n".join(lines).strip()


# ── Task file rendering ────────────────────────────────────────────────────────

PROFILES = {
    "small":  "250m CPU / 256Mi RAM — good for quick tasks, analysis, Q&A",
    "medium": "500m CPU / 512Mi RAM — good for code review, moderate work",
    "large":  "2 CPU / 4Gi RAM — heavy analysis, big repos (cloud burst)",
    "burst":  "2 CPU / 4Gi RAM — Claude Opus, complex creative work (cloud burst)",
}

PRIORITIES = {
    "low":    "run when idle, not urgent",
    "normal": "standard dispatch order",
    "high":   "jumps the queue",
}


def render_task_file(
    title: str,
    description: str,
    profile: str,
    priority: str,
    repo: str = "",
    created: str = "",
) -> str:
    """Render the full markdown task file content."""
    if not created:
        created = datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")

    lines = ["---"]
    if repo:
        lines.append(f"target_repo: {repo}")
    lines.append(f"profile: {profile}")
    lines.append(f"priority: {priority}")
    lines.append(f'status: pending')
    lines.append(f'created: "{created}"')
    lines.append("---")
    lines.append("")
    lines.append(f"# {title}")
    lines.append("")
    if description:
        lines.append("## Description")
        lines.append(description)
        lines.append("")

    return "\n".join(lines)


# ── Preview ────────────────────────────────────────────────────────────────────

def print_preview(task_id: str, content: str, dest: Path):
    print()
    print(c(hr(), DIM))
    print(c("  PREVIEW", BOLD, CYAN))
    print(c(hr(), DIM))
    print()
    for line in content.splitlines():
        print(f"  {c(line, DIM)}")
    print()
    print(c(hr(), DIM))
    print(f"  {c('File:', BOLD)} {dest}")
    print(c(hr(), DIM))
    print()


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        prog="new-task",
        description="Create a Claude OS task file and drop it in tasks/pending/",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""\
            Examples:
              python3 projects/new-task.py
              python3 projects/new-task.py "Check disk usage"
              python3 projects/new-task.py --title "Review my PR" --profile medium --repo https://github.com/me/myrepo
              echo "Do something cool" | python3 projects/new-task.py --title "Cool task" --desc -
        """),
    )
    parser.add_argument("title_positional", nargs="?", help="Task title (shortcut)")
    parser.add_argument("--title", help="Task title")
    parser.add_argument("--desc", help="Description text, or '-' to read from stdin")
    parser.add_argument("--profile", choices=list(PROFILES), default=None)
    parser.add_argument("--priority", choices=list(PRIORITIES), default=None)
    parser.add_argument("--repo", default="", help="Target repository URL")
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing")
    args = parser.parse_args()

    # Merge positional shortcut with --title
    title_arg = args.title_positional or args.title

    # Find repo root
    repo_root = find_repo_root()
    if not repo_root:
        print(c("✗ Could not find claude-os repo root (no tasks/pending/ directory).", RED))
        print("  Run this script from within the claude-os repository.")
        sys.exit(1)

    pending_dir = repo_root / "tasks" / "pending"

    # ── Banner ──────────────────────────────────────────────────────────────
    interactive = not (title_arg and args.desc and args.profile and args.priority)

    print()
    print(c("  ╭─ Claude OS — New Task Wizard ──────────────────────────╮", CYAN))
    print(c("  │  Creates a task file the controller will pick up       │", CYAN))
    print(c("  ╰────────────────────────────────────────────────────────╯", CYAN))
    print()

    # ── Gather inputs ────────────────────────────────────────────────────────
    if title_arg:
        title = title_arg
        print(f"  {c('Title:', BOLD)} {title}")
    else:
        title = prompt("Title", required=True)

    if args.desc == "-":
        description = sys.stdin.read().strip()
        print(f"  {c('Description:', BOLD)} (read from stdin)")
    elif args.desc:
        description = args.desc
    elif interactive:
        print()
        description = prompt_multiline("Description")
    else:
        description = ""

    print()

    if args.profile:
        profile = args.profile
    elif interactive:
        for key, desc in PROFILES.items():
            print(f"  {c(key, BOLD):8s}  {c(desc, DIM)}")
        profile = prompt_choice("Profile", list(PROFILES), "small")
    else:
        profile = "small"

    print()

    if args.priority:
        priority = args.priority
    elif interactive:
        for key, desc in PRIORITIES.items():
            print(f"  {c(key, BOLD):8s}  {c(desc, DIM)}")
        priority = prompt_choice("Priority", list(PRIORITIES), "normal")
    else:
        priority = "normal"

    repo = args.repo
    if interactive and not repo:
        print()
        repo = prompt("Target repo URL", default="(none)")
        if repo == "(none)":
            repo = ""

    # ── Generate task ID ─────────────────────────────────────────────────────
    slug = slugify(title)
    task_id = unique_id(slug, pending_dir)
    dest = pending_dir / f"{task_id}.md"

    # ── Render ───────────────────────────────────────────────────────────────
    content = render_task_file(title, description, profile, priority, repo)

    print_preview(task_id, content, dest)

    # ── Confirm ───────────────────────────────────────────────────────────────
    if args.dry_run:
        print(c("  Dry run — no file written.", YELLOW))
        return

    if interactive:
        confirm = prompt("Write this task? (y/N)", default="y")
        if confirm.lower() not in ("y", "yes"):
            print(c("  Cancelled.", DIM))
            return

    # ── Write ─────────────────────────────────────────────────────────────────
    dest.write_text(content)
    print(c(f"  ✓ Task written: {dest}", GREEN, BOLD))
    print()

    # ── Git tip ───────────────────────────────────────────────────────────────
    print(c("  Next steps:", BOLD))
    print(f"    {c('git add tasks/pending/' + dest.name, DIM)}")
    commit_msg = f'git commit -m "task {task_id}: enqueue"'
    print(f"    {c(commit_msg, DIM)}")
    print(f"    {c('git push', DIM)}")
    print()
    print(c("  The controller will pick it up on the next sync (≈30s).", DIM))
    print()


if __name__ == "__main__":
    main()
