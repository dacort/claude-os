#!/usr/bin/env python3
"""
shadow.py — The garden's blind spots

garden.py shows what appeared since the last session: new commits,
added files, completed tasks. It records growth.

shadow.py shows what garden.py cannot:
- Files deleted (garden uses diff_filter=A and M, never D)
- dacort's interventions (indistinguishable from AI work in garden)
- Infrastructure changes (controller/, worker/, k8s/ are invisible)
- Ghost sessions (ran and wrote handoffs but left no code in git)

The garden records growth. Shadow records everything else.

Usage:
    python3 projects/shadow.py              # full view
    python3 projects/shadow.py --brief      # compact summary
    python3 projects/shadow.py --plain      # no ANSI colors (for piping)
    python3 projects/shadow.py --since REF  # from a specific git ref
    python3 projects/shadow.py --all-time   # full history view
"""

import subprocess
import sys
import re
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).parent.parent
W = 64  # box width (matches garden.py)

# Known email addresses
CLAUDE_EMAIL = "claude-os@noreply.github.com"
HUMAN_EMAIL = "d.lifehacker@gmail.com"

# Paths that garden.py doesn't watch
INFRA_ROOTS = {"controller", "worker", "k8s", ".github"}


# ─── ANSI helpers ──────────────────────────────────────────────────────────────

def make_c(plain: bool):
    if plain:
        return lambda s, *a, **k: s

    def c(text, fg=None, bold=False, dim=False):
        codes = []
        if bold: codes.append("1")
        if dim: codes.append("2")
        if fg:
            palette = {
                "cyan": "36", "blue": "34", "green": "32",
                "yellow": "33", "red": "31", "white": "97",
                "magenta": "35", "gray": "90",
            }
            codes.append(palette.get(fg, "0"))
        if not codes:
            return text
        return f"\033[{';'.join(codes)}m{text}\033[0m"

    return c


# ─── Git helpers ───────────────────────────────────────────────────────────────

def git(*args):
    result = subprocess.run(
        ["git"] + list(args),
        capture_output=True, text=True,
        cwd=str(REPO),
    )
    return result.stdout.strip()


def find_last_workshop_commit():
    """Find the most recent completed workshop commit."""
    log = git("log", "--oneline", "--all")
    for line in log.splitlines():
        parts = line.split(None, 1)
        if len(parts) < 2:
            continue
        hash_, msg = parts
        if re.search(r'workshop.*completed', msg, re.IGNORECASE):
            return hash_, msg
    return None, None


def ref_timestamp(ref):
    return git("log", "-1", "--format=%ci", ref)


def human_age(ts_str):
    try:
        ts = datetime.strptime(ts_str[:19], "%Y-%m-%d %H:%M:%S")
        ts = ts.replace(tzinfo=timezone.utc)
        delta = datetime.now(timezone.utc) - ts
        if delta.days > 1:
            return f"{delta.days}d ago"
        hours = int(delta.seconds / 3600)
        if hours > 0:
            return f"{hours}h ago"
        mins = int(delta.seconds / 60)
        return f"{mins}m ago"
    except Exception:
        return ts_str[:19]


def deleted_files_since(ref, path_filter=None):
    """
    Files deleted since ref — the delta garden.py never shows.

    Uses 'git log' rather than 'git diff' because diff only finds files
    that existed at ref and are now gone. Log finds files added then deleted
    between ref and HEAD — the more complete picture.
    """
    args = ["log", f"{ref}..HEAD", "--diff-filter=D", "--name-only", "--format="]
    if path_filter:
        args += ["--", path_filter]
    out = git(*args)
    return [l for l in out.splitlines() if l.strip()]


def infra_files_changed_since(ref):
    """
    Files changed in paths that garden.py doesn't watch:
    controller/, worker/, k8s/, .github/, root config files.
    """
    out = git("diff", "--name-only", ref, "HEAD")
    infra = []
    for f in out.splitlines():
        if not f.strip():
            continue
        root = f.split("/")[0]
        if root in INFRA_ROOTS or "/" not in f:
            # Root-level file (Makefile, Taskfile, etc.) or infra path
            if "/" not in f and f not in ("README.md",):
                infra.append(f)
            elif root in INFRA_ROOTS:
                infra.append(f)
    return infra


def human_commits_since(ref):
    """Commits by dacort since ref — invisible as distinct from AI work in garden."""
    out = git(
        "log", f"{ref}..HEAD", "--no-merges",
        f"--author={HUMAN_EMAIL}",
        "--format=%h|%ai|%s",
    )
    commits = []
    for line in out.splitlines():
        if "|" not in line:
            continue
        parts = line.split("|", 2)
        if len(parts) == 3:
            commits.append({
                "hash": parts[0].strip(),
                "date": parts[1][:10],
                "msg": parts[2].strip(),
            })
    return commits


def all_time_attribution():
    """Count all commits by email across the full history."""
    out = git("log", "--format=%ae", "--all", "--no-merges")
    emails = out.splitlines()
    human = sum(1 for e in emails if e == HUMAN_EMAIL)
    ai = sum(1 for e in emails if e == CLAUDE_EMAIL)
    other = len(emails) - human - ai
    return human, ai, other


def find_ghost_sessions():
    """
    Sessions that have handoff files but no session-attributed code commits.
    Uses the same detection patterns as ghost.py for consistency.
    """
    handoff_dir = REPO / "knowledge" / "handoffs"
    if not handoff_dir.exists():
        return []

    handoff_sessions = set()
    for f in handoff_dir.glob("session-*.md"):
        m = re.search(r"session-(\d+)", f.name)
        if m:
            handoff_sessions.add(int(m.group(1)))

    # Sessions with code-bearing commits — same patterns as ghost.py
    code_log = git("log", "--format=%s", "--all")
    sessions_with_code = set()
    for subject in code_log.splitlines():
        # "workshop S87:" or "workshop 142:"
        for m in re.finditer(r"workshop [Ss](\d{1,3}):", subject):
            sessions_with_code.add(int(m.group(1)))
        for m in re.finditer(r"workshop (\d{2,3}):", subject):
            sessions_with_code.add(int(m.group(1)))
        # "task S148:"
        for m in re.finditer(r"task [Ss](\d{1,3}):", subject):
            sessions_with_code.add(int(m.group(1)))
        # "workshop session-123:"
        for m in re.finditer(r"workshop session[- ](\d{1,3}):", subject):
            sessions_with_code.add(int(m.group(1)))
        # "session 100" or "session-100"
        for m in re.finditer(r"[Ss]ession[- ](\d{1,3})\b", subject):
            sessions_with_code.add(int(m.group(1)))

    # Only check post-S87 era — before S87, session numbers weren't reliably
    # in commit messages, so pre-87 gaps can't be distinguished from format differences.
    # This matches ghost.py's NUMBERING_STARTED = 87 constraint.
    NUMBERING_STARTED = 87
    return sorted(
        n for n in (handoff_sessions - sessions_with_code)
        if n >= NUMBERING_STARTED
    )


# ─── Rendering ────────────────────────────────────────────────────────────────

def box_line(text="", pad=2, c=None):
    if c is None:
        c = lambda s, **k: s
    inner = " " * pad + text
    visible = re.sub(r"\033\[[^m]*m", "", inner)
    needed = W - len(visible)
    return f"│{inner}{' ' * max(0, needed)}│"


def section_div():
    return f"├{'─' * W}┤"


# ─── Main ─────────────────────────────────────────────────────────────────────

def run(plain=False, brief=False, since_ref=None, all_time=False):
    c = make_c(plain)

    # Determine reference commit
    if since_ref:
        ref = since_ref
        session_id = since_ref[:12]
    elif all_time:
        ref = git("rev-list", "--max-parents=0", "HEAD")
        session_id = "genesis"
    else:
        ref, ref_msg = find_last_workshop_commit()
        if not ref:
            ref = git("rev-list", "--max-parents=0", "HEAD")
            ref_msg = "(genesis commit)"
            session_id = "genesis"
        else:
            m = re.search(r"workshop-(\d{8}-\d+)", ref_msg)
            session_id = "workshop-" + m.group(1) if m else ref[:12]

    ref_date = ref_timestamp(ref)
    age = human_age(ref_date)

    # Gather data
    deleted_proj = deleted_files_since(ref, "projects/")
    deleted_knowledge = deleted_files_since(ref, "knowledge/")
    deleted_other = deleted_files_since(ref, "tasks/")
    infra_changed = infra_files_changed_since(ref)
    human_commits = human_commits_since(ref)
    ghost_sessions = find_ghost_sessions()
    human_total, ai_total, other_total = all_time_attribution()

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = []

    # ── Header ────────────────────────────────────────────────────
    lines.append(f"╭{'─' * W}╮")
    lines.append(box_line(
        c("  Shadow", fg="magenta", bold=True) + "   " + c(now, fg="gray"), c=c
    ))
    lines.append(box_line(
        c("  What the garden doesn't show", dim=True), c=c
    ))
    lines.append(f"├{'─' * W}┤")
    lines.append(box_line(c="c"))
    lines.append(box_line(
        f"  Since  {c(session_id, fg='cyan')}  {c(f'({age})', fg='gray')}", c=c
    ))
    lines.append(box_line(c="c"))

    # ── DELETIONS ─────────────────────────────────────────────────
    lines.append(section_div())
    lines.append(box_line(c="c"))
    lines.append(box_line(c("DELETIONS", bold=True), c=c))
    lines.append(box_line(
        c("  garden uses diff_filter=A and =M, never =D", dim=True), c=c
    ))
    lines.append(box_line(c="c"))

    all_deleted = deleted_proj + deleted_knowledge + deleted_other
    if all_deleted:
        for f in all_deleted:
            fname = Path(f).name
            fdir = str(Path(f).parent)
            label = c("deleted", fg="red")
            lines.append(box_line(
                f"  {label:<12}  {c(fname, fg='gray')}  ({fdir})", c=c
            ))
    else:
        lines.append(box_line(c("  Nothing deleted since last session", dim=True), c=c))
    lines.append(box_line(c="c"))

    # ── HUMAN HAND ────────────────────────────────────────────────
    lines.append(section_div())
    lines.append(box_line(c="c"))
    lines.append(box_line(c("THE HUMAN HAND", bold=True), c=c))
    lines.append(box_line(
        c("  dacort's commits — garden treats these identically to AI work", dim=True), c=c
    ))
    lines.append(box_line(c="c"))

    total = human_total + ai_total + other_total
    if total > 0:
        pct_human = int(100 * human_total / total)
        pct_ai = int(100 * ai_total / total)
        bar_human = "█" * max(1, pct_human // 5)
        bar_ai = "░" * max(1, pct_ai // 5)
        lines.append(box_line(
            f"  All time  "
            + c(bar_human, fg="yellow")
            + c(bar_ai, dim=True)
            + f"  {c(str(human_total), fg='yellow')} dacort · {c(str(ai_total), fg='cyan')} claude-os",
            c=c
        ))
        lines.append(box_line(
            c(f"  {pct_human}% human  /  {pct_ai}% AI  ({total} total commits)", dim=True), c=c
        ))

    lines.append(box_line(c="c"))
    if human_commits:
        lines.append(box_line(
            f"  {c(str(len(human_commits)), fg='yellow', bold=True)} dacort commit(s) since last session:", c=c
        ))
        for commit in human_commits[:6]:
            msg = commit["msg"]
            if len(msg) > W - 20:
                msg = msg[:W - 23] + "..."
            lines.append(box_line(
                c(f"  · {commit['date']}  {msg}", dim=True), c=c
            ))
        if len(human_commits) > 6:
            lines.append(box_line(
                c(f"  … and {len(human_commits) - 6} more", dim=True), c=c
            ))
    else:
        lines.append(box_line(
            c("  No dacort commits since last session", dim=True), c=c
        ))
    lines.append(box_line(c="c"))

    # ── INFRASTRUCTURE ────────────────────────────────────────────
    lines.append(section_div())
    lines.append(box_line(c="c"))
    lines.append(box_line(c("INFRASTRUCTURE", bold=True), c=c))
    lines.append(box_line(
        c("  controller/ worker/ k8s/ .github/ — garden doesn't watch these", dim=True), c=c
    ))
    lines.append(box_line(c="c"))

    if infra_changed:
        for f in infra_changed[:10]:
            display = f[:W - 8]
            lines.append(box_line(
                c(f"  {display}", fg="cyan", dim=True), c=c
            ))
        if len(infra_changed) > 10:
            lines.append(box_line(
                c(f"  … and {len(infra_changed) - 10} more files", dim=True), c=c
            ))
    else:
        lines.append(box_line(
            c("  No infrastructure changes since last session", dim=True), c=c
        ))
    lines.append(box_line(c="c"))

    # ── GHOST SESSIONS ────────────────────────────────────────────
    if not brief:
        lines.append(section_div())
        lines.append(box_line(c="c"))
        lines.append(box_line(c("GHOST SESSIONS", bold=True), c=c))
        lines.append(box_line(
            c("  ran and wrote handoffs but left no code in git", dim=True), c=c
        ))
        lines.append(box_line(c="c"))

        if ghost_sessions:
            ghost_str = ", ".join(f"S{n}" for n in ghost_sessions)
            lines.append(box_line(
                f"  {c(str(len(ghost_sessions)), fg='magenta', bold=True)} ghost session(s) all time:", c=c
            ))
            lines.append(box_line(
                c(f"  {ghost_str}", dim=True), c=c
            ))
            lines.append(box_line(c="c"))
            lines.append(box_line(
                c("  run: python3 projects/ghost.py --why", dim=True), c=c
            ))
        else:
            lines.append(box_line(
                c("  0 ghost sessions detected", dim=True), c=c
            ))
        lines.append(box_line(c="c"))

    lines.append(f"╰{'─' * W}╯")
    print("\n".join(lines))


def main():
    import argparse
    parser = argparse.ArgumentParser(
        prog="shadow.py",
        description=(
            "Shadow — the garden's blind spots.\n"
            "garden.py shows additions. shadow.py shows deletions,\n"
            "human interventions, infrastructure changes, and ghost sessions."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--plain", action="store_true",
                        help="disable ANSI colors")
    parser.add_argument("--brief", action="store_true",
                        help="compact view (skip ghost sessions)")
    parser.add_argument("--since", metavar="REF",
                        help="compare from a specific git ref")
    parser.add_argument("--all-time", action="store_true",
                        help="show full history (from genesis commit)")
    args = parser.parse_args()
    run(
        plain=args.plain,
        brief=args.brief,
        since_ref=args.since,
        all_time=args.all_time,
    )


if __name__ == "__main__":
    main()
