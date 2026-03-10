#!/usr/bin/env python3
"""
repo-story.py — Turns a git history into a readable narrative

Parses git commits by type (feat/fix/workshop/task) and weaves them
into a human-readable story of how the codebase evolved.

Usage:
  python3 projects/repo-story.py                    # full history
  python3 projects/repo-story.py --days 7           # last 7 days
  python3 projects/repo-story.py --short            # one-line summary per chapter
  python3 projects/repo-story.py --markdown         # output as markdown

Author: Claude OS (free-time project, 2026-03-10)
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
RESET  = "\033[0m"
BOLD   = "\033[1m"
DIM    = "\033[2m"
GREEN  = "\033[32m"
YELLOW = "\033[33m"
CYAN   = "\033[36m"
BLUE   = "\033[34m"
MAGENTA= "\033[35m"
WHITE  = "\033[97m"
ITALIC = "\033[3m"

def c(text, *codes):
    if not sys.stdout.isatty():
        return str(text)
    return "".join(codes) + str(text) + RESET

def nocolor(text):
    return re.sub(r'\033\[[0-9;]*m', '', str(text))


# ── Commit classification ──────────────────────────────────────────────────────

@dataclass
class Commit:
    sha: str
    date: datetime.datetime
    message: str
    author: str

    @property
    def kind(self) -> str:
        msg = self.message.lower()
        if msg.startswith("feat:"):       return "feat"
        if msg.startswith("fix:"):        return "fix"
        if msg.startswith("workshop:"):   return "workshop"
        if msg.startswith("task "):       return "task"
        if msg.startswith("docs:"):       return "docs"
        if msg.startswith("refactor:"):   return "refactor"
        if msg.startswith("chore:"):      return "chore"
        if msg.startswith("test:"):       return "test"
        # Emoji-only commits
        if re.match(r'^[\U00010000-\U0010ffff\U00002600-\U000027BF]+$', self.message.strip()):
            return "emoji"
        return "other"

    @property
    def short_sha(self) -> str:
        return self.sha[:7]

    @property
    def subject(self) -> str:
        """Strip the conventional commit prefix."""
        for prefix in ["feat:", "fix:", "workshop:", "docs:", "refactor:", "chore:", "test:"]:
            if self.message.lower().startswith(prefix):
                return self.message[len(prefix):].strip()
        # task stats_02: pending → in-progress
        if self.message.lower().startswith("task "):
            return self.message
        return self.message

    @property
    def is_claude_os(self) -> bool:
        return self.author.lower() in ("claude os", "claude-os")


KIND_LABEL = {
    "feat":      ("✦", CYAN,    "Feature"),
    "fix":       ("⚑", YELLOW,  "Fix"),
    "workshop":  ("✿", MAGENTA, "Workshop"),
    "task":      ("◈", GREEN,   "Task"),
    "docs":      ("◎", BLUE,    "Docs"),
    "refactor":  ("↺", CYAN,    "Refactor"),
    "chore":     ("·", DIM,     "Chore"),
    "test":      ("◇", DIM,     "Test"),
    "emoji":     ("◉", MAGENTA, "Milestone"),
    "other":     ("·", DIM,     "Other"),
}


# ── Git log parsing ────────────────────────────────────────────────────────────

def get_commits(repo_path: Path, since_days: Optional[int] = None) -> list[Commit]:
    cmd = ["git", "log", "--format=%H|%aI|%s|%an"]
    if since_days:
        cmd += [f"--since={since_days} days ago"]

    result = subprocess.run(cmd, cwd=repo_path, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"git log failed: {result.stderr}", file=sys.stderr)
        return []

    commits = []
    for line in result.stdout.strip().splitlines():
        if not line.strip():
            continue
        parts = line.split("|", 3)
        if len(parts) < 4:
            continue
        sha, date_str, message, author = parts
        try:
            date = datetime.datetime.fromisoformat(date_str)
        except ValueError:
            continue
        commits.append(Commit(sha=sha, date=date, message=message, author=author))

    return list(reversed(commits))  # chronological order


# ── Chapter grouping ───────────────────────────────────────────────────────────

@dataclass
class Chapter:
    title: str
    date: datetime.date
    commits: list[Commit] = field(default_factory=list)
    description: str = ""


def identify_chapters(commits: list[Commit]) -> list[Chapter]:
    """Group commits into narrative chapters by calendar day."""
    if not commits:
        return []

    # Group by date first
    by_date = defaultdict(list)
    date_order = []
    for commit in commits:
        d = commit.date.date()
        if d not in by_date:
            date_order.append(d)
        by_date[d].append(commit)

    chapters = []
    for i, date in enumerate(date_order):
        day_commits = by_date[date]
        title = chapter_title_for_day(i, date, day_commits)
        chapter = Chapter(title=title, date=date, commits=day_commits)
        chapter.description = describe_chapter(chapter)
        chapters.append(chapter)

    return chapters


def dominant_theme(commits: list[Commit]) -> str:
    """Find the dominant theme for a set of commits."""
    by_kind = defaultdict(int)
    for commit in commits:
        msg = commit.message.lower()
        if "scaffold" in msg:
            by_kind["genesis"] += 3
        elif commit.kind == "feat":
            by_kind["feature"] += 2
        elif commit.kind == "fix":
            by_kind["fix"] += 1
        elif commit.kind == "workshop":
            by_kind["workshop"] += 2
        elif commit.kind == "task":
            by_kind["task"] += 2
        else:
            by_kind["misc"] += 1

    if not by_kind:
        return "misc"
    return max(by_kind, key=by_kind.__getitem__)


def chapter_title_for_day(day_index: int, date: datetime.date, commits: list[Commit]) -> str:
    theme = dominant_theme(commits)
    date_str = date.strftime("%b %d, %Y")

    # Special titles for landmark days/themes
    if theme == "genesis":
        title = f"Day One — The System Comes Alive"
    elif theme == "feature" and day_index == 0:
        title = "Foundations"
    elif theme == "feature":
        title = "New Capabilities"
    elif theme == "fix":
        title = "Debugging in the Dark"
    elif theme == "workshop":
        title = "Free Time"
    elif theme == "task":
        title = "First Tasks"
    else:
        title = "Ongoing Work"

    return f"{title}  {c(date_str, DIM)}"


def describe_chapter(chapter: Chapter) -> str:
    """Generate a short prose description for a chapter."""
    n = len(chapter.commits)
    by_kind = defaultdict(list)
    for commit in chapter.commits:
        by_kind[commit.kind].append(commit)

    authors = {c.author for c in chapter.commits}
    claude_authored = sum(1 for c in chapter.commits if c.is_claude_os)
    human_authored = n - claude_authored

    desc_parts = []

    if by_kind["feat"]:
        features = [c.subject for c in by_kind["feat"]]
        desc_parts.append(f"{len(features)} new feature{'s' if len(features) != 1 else ''}: " +
                          "; ".join(f[:50] for f in features[:3]))

    if by_kind["fix"]:
        fixes = by_kind["fix"]
        desc_parts.append(f"{len(fixes)} fix{'es' if len(fixes) != 1 else ''}")

    if by_kind["workshop"]:
        desc_parts.append(f"{len(by_kind['workshop'])} workshop session{'s' if len(by_kind['workshop']) != 1 else ''}")

    if by_kind["task"]:
        # Count unique task IDs
        task_ids = set()
        for commit in by_kind["task"]:
            m = re.match(r"task (\S+):", commit.message, re.IGNORECASE)
            if m:
                task_ids.add(m.group(1))
        desc_parts.append(f"{len(task_ids)} task{'s' if len(task_ids) != 1 else ''} processed")

    attribution = []
    if human_authored:
        attribution.append(f"dacort: {human_authored} commit{'s' if human_authored != 1 else ''}")
    if claude_authored:
        attribution.append(f"Claude OS: {claude_authored} commit{'s' if claude_authored != 1 else ''}")

    result = ". ".join(desc_parts)
    if attribution:
        result += f"  ({', '.join(attribution)})"
    return result


# ── Rendering ──────────────────────────────────────────────────────────────────

WIDTH = 70

def render_header(commits: list[Commit], markdown: bool) -> str:
    if not commits:
        return ""
    first = commits[0]
    last = commits[-1]
    span = (last.date - first.date).days + 1
    n = len(commits)
    by_kind = defaultdict(int)
    for commit in commits:
        by_kind[commit.kind] += 1

    if markdown:
        lines = [
            "# Claude OS — Repository Story",
            "",
            f"> {n} commits over {span} day{'s' if span != 1 else ''} "
            f"· {by_kind['feat']} features · {by_kind['fix']} fixes "
            f"· {by_kind['workshop']} workshop sessions · {by_kind['task']} task events",
            "",
            f"*{first.date.strftime('%B %d, %Y')} — {last.date.strftime('%B %d, %Y')}*",
            "",
        ]
    else:
        lines = [
            "",
            c("  ╭─ Claude OS — Repository Story " + "─" * (WIDTH - 34) + "╮", CYAN),
            c(f"  │  {n} commits · {span} day{'s' if span != 1 else ''} · {by_kind['feat']} features · {by_kind['fix']} fixes · {by_kind['workshop']} workshop sessions" + " " * 2 + "│", CYAN),
            c("  ╰" + "─" * (WIDTH - 2) + "╯", CYAN),
            "",
        ]
    return "\n".join(lines)


def render_chapter(chapter: Chapter, short: bool, markdown: bool) -> str:
    lines = []
    title_plain = nocolor(chapter.title)

    if markdown:
        lines.append(f"## {title_plain}")
        lines.append("")
        if chapter.description:
            lines.append(f"*{chapter.description}*")
            lines.append("")
    else:
        lines.append("")
        lines.append(c(f"  ── {chapter.title} {'─' * max(0, WIDTH - len(title_plain) - 6)}", BOLD, BLUE))
        if chapter.description:
            lines.append(f"  {c(chapter.description, ITALIC, DIM)}")
        lines.append("")

    if not short:
        for commit in chapter.commits:
            icon, color, label = KIND_LABEL.get(commit.kind, ("·", DIM, "Other"))

            if markdown:
                lines.append(f"- `{commit.short_sha}` {commit.message}  _{commit.author}_")
            else:
                author_tag = c(f"[{commit.author[:12]}]", DIM)
                sha_tag = c(commit.short_sha, DIM)
                icon_colored = c(icon, color)
                subject = commit.subject[:55]
                lines.append(f"  {icon_colored} {subject:<56} {sha_tag} {author_tag}")

    if markdown:
        lines.append("")
    return "\n".join(lines)


def render_epilogue(commits: list[Commit], markdown: bool) -> str:
    if not commits:
        return ""

    claude_commits = sum(1 for c in commits if c.is_claude_os)
    human_commits = len(commits) - claude_commits
    by_kind = defaultdict(int)
    for commit in commits:
        by_kind[commit.kind] += 1

    # Find most recent workshop session
    workshop_commits = [c for c in commits if c.kind == "workshop"]
    last_workshop = workshop_commits[-1].date.strftime("%B %d") if workshop_commits else "never"

    if markdown:
        lines = [
            "## By the Numbers",
            "",
            "| Metric | Value |",
            "|--------|-------|",
            f"| Total commits | {len(commits)} |",
            f"| By dacort | {human_commits} |",
            f"| By Claude OS | {claude_commits} |",
            f"| Features added | {by_kind['feat']} |",
            f"| Bugs fixed | {by_kind['fix']} |",
            f"| Workshop sessions | {by_kind['workshop']} |",
            f"| Last workshop | {last_workshop} |",
            "",
        ]
    else:
        lines = [
            "",
            c("  " + "─" * (WIDTH - 2), DIM),
            c("  TOTALS", BOLD),
            "",
            f"  {c('Total commits:', BOLD)}      {len(commits)}",
            f"  {c('By dacort:', BOLD)}         {human_commits}",
            f"  {c('By Claude OS:', BOLD)}      {claude_commits}",
            f"  {c('Features:', BOLD)}          {by_kind['feat']}",
            f"  {c('Fixes:', BOLD)}             {by_kind['fix']}",
            f"  {c('Workshop sessions:', BOLD)} {by_kind['workshop']}",
            f"  {c('Last workshop:', BOLD)}     {last_workshop}",
            "",
            c("  " + "─" * (WIDTH - 2), DIM),
            "",
        ]
    return "\n".join(lines)


# ── Main ───────────────────────────────────────────────────────────────────────

def find_repo_root() -> Path:
    """Find the git repo root from current directory."""
    current = Path.cwd()
    for path in [current, *current.parents]:
        if (path / ".git").exists():
            return path
    return current


def main():
    parser = argparse.ArgumentParser(
        prog="repo-story",
        description="Render the git history as a human-readable story",
    )
    parser.add_argument("--days", type=int, default=None,
                        help="Only show last N days (default: all history)")
    parser.add_argument("--short", action="store_true",
                        help="One-line summary per chapter, no individual commits")
    parser.add_argument("--markdown", action="store_true",
                        help="Output as markdown instead of terminal-colored text")
    parser.add_argument("--output", type=str, default=None,
                        help="Write output to a file (forces --markdown)")
    args = parser.parse_args()

    if args.output:
        args.markdown = True

    repo_root = find_repo_root()
    commits = get_commits(repo_root, since_days=args.days)

    if not commits:
        print("No commits found.", file=sys.stderr)
        sys.exit(1)

    chapters = identify_chapters(commits)

    output_lines = []
    output_lines.append(render_header(commits, args.markdown))
    for chapter in chapters:
        output_lines.append(render_chapter(chapter, args.short, args.markdown))
    output_lines.append(render_epilogue(commits, args.markdown))

    output = "\n".join(output_lines)

    if args.output:
        Path(args.output).write_text(output)
        print(f"Story written to: {args.output}")
    else:
        print(output)


if __name__ == "__main__":
    main()
