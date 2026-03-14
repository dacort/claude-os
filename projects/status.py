#!/usr/bin/env python3
"""
status.py — Daily operator report for dacort

Answers the question: "what happened today, what's the state of M1, and
what (if anything) needs your attention?" No kubectl required.

Designed to be run by the controller once daily and committed to logs/.
Also useful for dacort to run manually at any time.

Output modes:
  --print     Pretty-print to terminal (default)
  --write     Write to logs/YYYY-MM-DD.md and print path
  --plain     No ANSI colors
  --date X    Report for specific date (YYYY-MM-DD), default today

Author: Claude OS (Workshop session 33, 2026-03-14)
"""

import argparse
import datetime
import pathlib
import re
import subprocess
import sys

# ── ANSI ─────────────────────────────────────────────────────────────────────

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

USE_COLOR = True

def c(code, text):
    return f"{code}{text}{RESET}" if USE_COLOR else text

_ANSI_RE = re.compile(r"\033\[[0-9;]*m")

def visual_len(s: str) -> int:
    """Length of a string ignoring ANSI escape codes."""
    return len(_ANSI_RE.sub("", s))

# ── Paths ─────────────────────────────────────────────────────────────────────

REPO = pathlib.Path(__file__).parent.parent
TASKS = REPO / "tasks"
LOGS  = REPO / "logs"
CO_FOUNDERS = REPO / "knowledge" / "co-founders" / "threads"

# ── Git helpers ───────────────────────────────────────────────────────────────

def git(*args) -> str:
    try:
        return subprocess.check_output(
            ["git", "-C", str(REPO)] + list(args),
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
    except subprocess.CalledProcessError:
        return ""

def commits_on_date(date_str: str) -> list[dict]:
    """Return commits from a given date as list of {hash, subject, time}."""
    raw = git(
        "log", "--oneline",
        "--format=%H\t%s\t%cd",
        "--date=format:%H:%M",
        f"--after={date_str} 00:00",
        f"--before={date_str} 23:59:59",
    )
    result = []
    for line in raw.splitlines():
        if not line.strip():
            continue
        parts = line.split("\t", 2)
        if len(parts) == 3:
            result.append({"hash": parts[0][:7], "subject": parts[1], "time": parts[2]})
    return result

def files_changed_on_date(date_str: str) -> list[str]:
    """Return unique file paths touched in commits on the given date."""
    raw = git(
        "log", "--name-only",
        "--format=",
        f"--after={date_str} 00:00",
        f"--before={date_str} 23:59:59",
    )
    seen = set()
    result = []
    for line in raw.splitlines():
        if line.strip() and line not in seen:
            seen.add(line)
            result.append(line)
    return result

# ── Task file parsing ─────────────────────────────────────────────────────────

def parse_frontmatter(content: str) -> dict:
    """Extract YAML frontmatter fields as a dict."""
    fm = {}
    if not content.startswith("---"):
        return fm
    end = content.find("---", 3)
    if end == -1:
        return fm
    block = content[3:end]
    for line in block.splitlines():
        if ":" in line:
            k, _, v = line.partition(":")
            fm[k.strip()] = v.strip()
    return fm

def scan_tasks(directory: str) -> list[dict]:
    """Return list of task metadata dicts from a tasks/ subdirectory."""
    path = TASKS / directory
    if not path.exists():
        return []
    result = []
    for f in sorted(path.glob("*.md")):
        try:
            content = f.read_text()
            fm = parse_frontmatter(content)
            # Extract title from first H1
            title_match = re.search(r"^#\s+(.+)", content, re.MULTILINE)
            title = title_match.group(1).strip() if title_match else f.stem
            result.append({
                "id": f.stem,
                "title": title,
                "profile": fm.get("profile", "?"),
                "agent": fm.get("agent", "claude"),
                "status": fm.get("status", directory),
            })
        except Exception:
            continue
    return result

# ── M1 milestone status ───────────────────────────────────────────────────────

M1_SLICES = [
    {
        "num": 1,
        "name": "Don't lose tasks",
        "items": [
            "Running set in Redis (queue tracking)",
            "Git push retry with rebase",
            "Concurrency limiter (max_concurrent_jobs)",
            "Task timeouts (CheckTimeouts + config)",
            "Startup reconciler (orphan recovery)",
            "Workshop state sync on restart",
        ],
        "done": True,
        "commit": "e2b2e9a",
    },
    {
        "num": 2,
        "name": "Codex runs real tasks",
        "items": [
            "Context contract JSON schema (Codex)",
            "Agent adapters for shared context",
            "Real cross-agent task execution",
        ],
        "done": False,
        "owner": "Codex",
        "blocking": "Awaiting Codex's 002-context-contract.md thread",
    },
    {
        "num": 3,
        "name": "Know what happened",
        "items": [
            "Daily git report (status.py)",
            "Structured stdout usage block (worker)",
            "Usage parsing in queue + task duration",
        ],
        "done": True,
        "commit": "220431b",
    },
]

# ── Co-founders thread scanning ───────────────────────────────────────────────

def open_threads() -> list[dict]:
    """Threads waiting for a response."""
    if not CO_FOUNDERS.exists():
        return []
    open_list = []
    for f in sorted(CO_FOUNDERS.glob("*.md")):
        try:
            content = f.read_text()
            title_match = re.search(r"^#\s+(.+)", content, re.MULTILINE)
            title = title_match.group(1) if title_match else f.stem
            # Check if Codex has responded (look for "## Codex —" header)
            has_codex = bool(re.search(r"^## Codex\s*—", content, re.MULTILINE))
            # Count turns
            turns = len(re.findall(r"^## (Claude|Codex)\s*—", content, re.MULTILINE))
            open_list.append({
                "file": f.name,
                "title": title,
                "has_codex": has_codex,
                "turns": turns,
            })
        except Exception:
            continue
    return open_list

# ── Report rendering ──────────────────────────────────────────────────────────

def build_report(date_str: str, plain: bool = False) -> tuple[str, str]:
    """
    Returns (terminal_output, markdown_output) for the given date.
    terminal_output has ANSI codes; markdown is clean for git.
    """
    global USE_COLOR
    USE_COLOR = not plain

    date = datetime.date.fromisoformat(date_str)
    date_display = date.strftime("%A, %B %-d %Y")

    commits = commits_on_date(date_str)
    workshop_commits = [x for x in commits if x["subject"].startswith("workshop")]
    infra_commits = [x for x in commits if not x["subject"].startswith("workshop")]

    completed = scan_tasks("completed")
    failed = scan_tasks("failed")
    in_progress = scan_tasks("in-progress")
    pending = scan_tasks("pending")

    threads = open_threads()
    unanswered = [t for t in threads if not t["has_codex"]]

    # ── Terminal output ───────────────────────────────────────────────────────
    lines = []
    W = 64
    border = "─" * W

    def box_line(text="", align="left"):
        vlen = visual_len(text)
        if align == "center":
            pad = (W - vlen) // 2
            lines.append(f"│{' ' * pad}{text}{' ' * (W - pad - vlen)}│")
        else:
            pad_right = W - 4 - vlen
            lines.append(f"│  {text}{' ' * max(0, pad_right)}  │")

    lines.append(f"╭{border}╮")
    box_line(c(BOLD + CYAN, f"  claude-os status"), align="left")
    box_line(c(DIM, f"  {date_display}"), align="left")
    lines.append(f"├{border}┤")
    lines.append(f"│{'':64}│")

    # Commits today
    box_line(c(BOLD, "  TODAY'S ACTIVITY"))
    lines.append(f"│{'':64}│")

    if not commits:
        box_line(c(DIM, "  No commits today"))
    else:
        if workshop_commits:
            box_line(c(DIM, f"  Workshop sessions: {len(workshop_commits)}"))
        if infra_commits:
            for cm in infra_commits:
                subj = cm["subject"][:52]
                box_line(f"  {c(DIM, cm['time'])}  {subj}")

    lines.append(f"│{'':64}│")
    lines.append(f"├{border}┤")
    lines.append(f"│{'':64}│")

    # Task state
    box_line(c(BOLD, "  TASK STATE"))
    lines.append(f"│{'':64}│")
    box_line(f"  {c(GREEN, str(len(completed)).rjust(3))} completed  "
             f"{c(YELLOW, str(len(in_progress)).rjust(2))} in-progress  "
             f"{c(DIM, str(len(pending)).rjust(2))} pending  "
             f"{c(RED, str(len(failed)).rjust(2))} failed")

    if in_progress:
        lines.append(f"│{'':64}│")
        box_line(c(DIM, "  Currently running:"))
        for t in in_progress:
            box_line(f"    ↳ {t['title'][:52]}")

    if pending:
        lines.append(f"│{'':64}│")
        box_line(c(DIM, "  Pending:"))
        for t in pending[:3]:
            box_line(f"    · {t['title'][:52]}")
        if len(pending) > 3:
            box_line(c(DIM, f"    … and {len(pending)-3} more"))

    lines.append(f"│{'':64}│")
    lines.append(f"├{border}┤")
    lines.append(f"│{'':64}│")

    # M1 milestone
    box_line(c(BOLD, "  MILESTONE 1 PROGRESS"))
    lines.append(f"│{'':64}│")
    for sl in M1_SLICES:
        if sl["done"]:
            icon = c(GREEN, "✓")
            label = c(DIM, f"Slice {sl['num']}: {sl['name']}")
        elif sl.get("partial"):
            icon = c(YELLOW, "~")
            label = f"Slice {sl['num']}: {sl['name']}"
        else:
            icon = c(DIM, "·")
            label = c(DIM, f"Slice {sl['num']}: {sl['name']}")
        box_line(f"  {icon}  {label}")
        if not sl["done"]:
            if sl.get("blocking"):
                box_line(c(YELLOW, f"     ⚠  {sl['blocking'][:56]}"))
            elif sl.get("notes"):
                box_line(c(DIM, f"     ·  {sl['notes'][:56]}"))

    lines.append(f"│{'':64}│")
    lines.append(f"├{border}┤")
    lines.append(f"│{'':64}│")

    # Co-founders
    box_line(c(BOLD, "  CO-FOUNDERS THREADS"))
    lines.append(f"│{'':64}│")
    if not threads:
        box_line(c(DIM, "  No threads open"))
    else:
        for t in threads:
            codex_str = c(GREEN, "✓ Codex replied") if t["has_codex"] else c(YELLOW, "⏳ waiting for Codex")
            box_line(f"  {t['file'][:28]}  {codex_str}")

    lines.append(f"│{'':64}│")
    lines.append(f"├{border}┤")
    lines.append(f"│{'':64}│")

    # Needs dacort
    action_items = []
    if unanswered:
        action_items.append(f"Codex hasn't responded to {len(unanswered)} thread(s) yet — check if Codex auth is working")
    if failed:
        action_items.append(f"{len(failed)} task(s) in failed/ — may need triage")

    box_line(c(BOLD, "  FOR DACORT"))
    lines.append(f"│{'':64}│")
    if not action_items:
        box_line(c(GREEN, "  Nothing. System is running clean."))
    else:
        for item in action_items:
            box_line(c(YELLOW, f"  ⚠  {item[:56]}"))

    lines.append(f"│{'':64}│")
    lines.append(f"╰{border}╯")

    terminal_out = "\n".join(lines)

    # ── Markdown output ───────────────────────────────────────────────────────
    md_lines = [
        f"# Claude OS Status — {date_display}",
        "",
        f"*Generated: {datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}*",
        "",
        "## Activity",
        "",
    ]

    if not commits:
        md_lines.append("No commits today.")
    else:
        if workshop_commits:
            md_lines.append(f"- **Workshop sessions:** {len(workshop_commits)}")
        for cm in infra_commits:
            md_lines.append(f"- `{cm['hash']}` {cm['subject']} ({cm['time']})")

    md_lines += [
        "",
        "## Task State",
        "",
        f"| Status | Count |",
        f"|--------|-------|",
        f"| Completed | {len(completed)} |",
        f"| In-progress | {len(in_progress)} |",
        f"| Pending | {len(pending)} |",
        f"| Failed | {len(failed)} |",
        "",
    ]

    if in_progress:
        md_lines.append("**Currently running:**")
        for t in in_progress:
            md_lines.append(f"- {t['title']}")
        md_lines.append("")

    md_lines += [
        "## Milestone 1 Progress",
        "",
    ]
    for sl in M1_SLICES:
        status_icon = "✅" if sl["done"] else ("🔄" if sl.get("partial") else "⬜")
        md_lines.append(f"### {status_icon} Slice {sl['num']}: {sl['name']}")
        md_lines.append("")
        for item in sl["items"]:
            if sl["done"]:
                done_icon, item_text = "✅", item
            elif isinstance(item, tuple):
                done_icon = "✅" if item[1] else "⬜"
                item_text = item[0]
            else:
                done_icon, item_text = "⬜", item
            md_lines.append(f"- {done_icon} {item_text}")
        if sl.get("blocking"):
            md_lines.append(f"\n> **Blocking:** {sl['blocking']}")
        if sl.get("notes"):
            md_lines.append(f"\n> {sl['notes']}")
        md_lines.append("")

    md_lines += [
        "## Co-Founders Threads",
        "",
    ]
    if not threads:
        md_lines.append("No open threads.")
    else:
        for t in threads:
            codex_str = "✅ Codex replied" if t["has_codex"] else "⏳ Waiting for Codex"
            md_lines.append(f"- **{t['file']}** — {codex_str} ({t['turns']} turns)")

    md_lines += ["", "## Action Items for dacort", ""]
    if not action_items:
        md_lines.append("Nothing. System running clean.")
    else:
        for item in action_items:
            md_lines.append(f"- ⚠️ {item}")

    markdown_out = "\n".join(md_lines) + "\n"
    return terminal_out, markdown_out


def main():
    parser = argparse.ArgumentParser(description="Daily Claude OS operator report")
    parser.add_argument("--plain", action="store_true", help="No ANSI colors")
    parser.add_argument("--write", action="store_true", help="Write to logs/ directory")
    parser.add_argument("--date", default=datetime.date.today().isoformat(),
                        help="Report date (YYYY-MM-DD), default today")
    args = parser.parse_args()

    terminal_out, markdown_out = build_report(args.date, plain=args.plain)

    print(terminal_out)

    if args.write:
        LOGS.mkdir(exist_ok=True)
        out_path = LOGS / f"{args.date}.md"
        out_path.write_text(markdown_out)
        print(f"\n  Written to: {out_path.relative_to(REPO)}")
        return str(out_path)


if __name__ == "__main__":
    main()
