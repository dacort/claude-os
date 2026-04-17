#!/usr/bin/env python3
"""
emerge.py — Session agenda from system signals, not a wish list.

Unlike next.py (which reads curated ideas), emerge.py reads what the
system itself is pointing toward: failure patterns, orphaned tools,
recent activity, open PRs. The agenda emerges from state.

Usage:
    python3 projects/emerge.py          # emergent session agenda
    python3 projects/emerge.py --plain  # no ANSI colors
    python3 projects/emerge.py --json   # machine-readable signals
"""

import re
import sys
import json
import subprocess
from pathlib import Path
from datetime import datetime, timezone

REPO = Path(__file__).parent.parent
W = 66


# ─── ANSI helpers ──────────────────────────────────────────────────────────────

def make_c(plain):
    if plain:
        return lambda s, *a, **k: s

    def c(text, fg=None, bold=False, dim=False):
        codes = []
        if bold: codes.append("1")
        if dim: codes.append("2")
        if fg:
            p = {"cyan": "36", "green": "32", "yellow": "33",
                 "red": "31", "white": "97", "magenta": "35", "gray": "90"}
            codes.append(p.get(fg, "0"))
        return f"\033[{';'.join(codes)}m{text}\033[0m" if codes else text

    return c


def box(lines, width=W, plain=False):
    tl, tr, bl, br = ("╭", "╮", "╰", "╯") if not plain else ("+", "+", "+", "+")
    v = "│" if not plain else "|"
    h = "─" if not plain else "-"
    ml, mr = ("├", "┤") if not plain else ("+", "+")
    top = tl + h * (width - 2) + tr
    bot = bl + h * (width - 2) + br
    mid = ml + h * (width - 2) + mr
    result = [top]
    for line in lines:
        if line == "---":
            result.append(mid)
        else:
            visible = re.sub(r'\033\[[0-9;]*m', '', line)
            pad = width - 2 - len(visible)
            result.append(v + " " + line + " " * max(0, pad - 1) + v)
    result.append(bot)
    return "\n".join(result)


# ─── Signal gathering ──────────────────────────────────────────────────────────

def _parse_task_date(stem):
    """Extract date from task filename like 'workshop-20260414-040032'. Returns date string or None."""
    m = re.search(r"(\d{8})-\d{6}$", stem)
    return m.group(1) if m else None


def get_failed_tasks():
    """Read tasks/failed/, extract error patterns.

    Searches the full file for the most informative error line — checking
    Worker Logs sections specifically for quota/credit messages that only
    appear later in the file.
    """
    failed_dir = REPO / "tasks" / "failed"
    failures = []
    quota_patterns = ("out of extra usage", "credit balance", "you're out of")
    generic_fail = "task failed before emitting"

    for path in sorted(failed_dir.glob("*.md")):
        text = path.read_text()
        lines = text.splitlines()
        error_line = ""
        generic_fallback = ""
        in_worker_logs = False

        for line in lines:
            stripped = line.strip().lower()
            if "worker logs" in stripped or "## worker" in stripped:
                in_worker_logs = True
            # Highest priority: quota/credit messages anywhere in the file
            if any(k in stripped for k in quota_patterns):
                error_line = line.strip()
                break
            # Generic "task failed" — save as fallback but keep looking
            if generic_fail in stripped and not generic_fallback:
                generic_fallback = line.strip()

        if not error_line:
            # Check worker logs section for any error indicators
            in_logs = False
            for line in lines:
                if "## worker logs" in line.lower() or "=== claude os worker" in line.lower():
                    in_logs = True
                if in_logs:
                    stripped = line.strip().lower()
                    if any(k in stripped for k in ("error", "failed", "exception", "timeout")):
                        # Skip lines that are just generic failure summaries
                        if generic_fail not in stripped:
                            error_line = line.strip()
                            break
            if not error_line:
                error_line = generic_fallback

        failures.append({
            "name": path.stem,
            "is_workshop": path.stem.startswith("workshop-"),
            "error": error_line,
            "date": _parse_task_date(path.stem),
        })
    return failures


def get_last_successful_workshop():
    """Return date string (YYYYMMDD) of most recent completed workshop, or None."""
    completed_dir = REPO / "tasks" / "completed"
    latest = None
    for path in sorted((completed_dir).glob("workshop-*.md"), reverse=True):
        date = _parse_task_date(path.stem)
        if date:
            if latest is None or date > latest:
                latest = date
    return latest


def classify_failures(failures):
    """Group failures by error pattern. Returns {pattern: [names]}."""
    clusters = {}
    quota_keywords = ("out of extra usage", "credit balance", "credit", "quota", "usage limit")
    for f in failures:
        err = f["error"].lower()
        if any(k in err for k in quota_keywords):
            key = "token_quota"
        elif "timeout" in err:
            key = "timeout"
        elif not f["error"]:
            key = "unknown"
        else:
            key = "other"
        clusters.setdefault(key, []).append(f["name"])
    return clusters


def get_tool_ages():
    """Return {tool_stem: days_since_last_commit} for projects/*.py."""
    now = datetime.now(timezone.utc)
    ages = {}
    for path in sorted((REPO / "projects").glob("*.py")):
        stem = path.stem
        try:
            result = subprocess.run(
                ["git", "-C", str(REPO), "log", "-1", "--format=%ai", "--", f"projects/{path.name}"],
                capture_output=True, text=True, timeout=5
            )
            ts_str = result.stdout.strip()
            if ts_str:
                ts = datetime.strptime(ts_str[:19], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
                ages[stem] = (now - ts).total_seconds() / 86400
        except Exception:
            pass
    return ages


def get_recent_activity(n=25):
    """Return last N commit subjects as a list."""
    try:
        result = subprocess.run(
            ["git", "-C", str(REPO), "log", f"-{n}", "--format=%s"],
            capture_output=True, text=True, timeout=5
        )
        return result.stdout.strip().splitlines()
    except Exception:
        return []


def get_open_prs():
    """Return list of open PRs via gh."""
    try:
        result = subprocess.run(
            ["gh", "pr", "list", "--json", "number,title,state"],
            capture_output=True, text=True, timeout=8, cwd=str(REPO)
        )
        return json.loads(result.stdout) if result.returncode == 0 else []
    except Exception:
        return []


# ─── Signal derivation ─────────────────────────────────────────────────────────

def derive_signals(failures, tool_ages, recent_commits, open_prs):
    """Read all system signals and return a prioritized list."""
    signals = []
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # Signal 1: Failure cluster analysis
    workshop_failures = [f for f in failures if f["is_workshop"]]
    clusters = classify_failures(workshop_failures)
    quota_fails = clusters.get("token_quota", [])
    if len(quota_fails) >= 3:
        # Find how many were consecutive (most recent)
        recent = sorted(quota_fails)[-5:]
        # Check if quota has since resolved (successful workshop after last failure)
        last_success = get_last_successful_workshop()
        last_failure_date = max(
            (f["date"] for f in workshop_failures if f["name"] in quota_fails and f["date"]),
            default=None
        )
        quota_resolved = (
            last_success is not None
            and last_failure_date is not None
            and last_success > last_failure_date
        )
        if quota_resolved:
            # Quota reset has already happened — lower priority, don't alarm
            def fmt_date(d):
                return f"{d[:4]}-{d[4:6]}-{d[6:8]}" if d and len(d) == 8 else d
            signals.append({
                "type": "failure_cluster",
                "priority": "low",
                "title": f"{len(quota_fails)} resolved quota failures in tasks/failed/",
                "observation": (
                    f"Quota reset {fmt_date(last_success)}. "
                    f"Last failure: {fmt_date(last_failure_date)}."
                ),
                "suggestion": "These failures are historical. Consider archiving tasks/failed/ "
                              "periodically to reduce noise.",
                "data": recent,
            })
        else:
            signals.append({
                "type": "failure_cluster",
                "priority": "high",
                "title": f"{len(quota_fails)} token-quota failures in tasks/failed/",
                "observation": f"All {len(quota_fails)} are 'out of extra usage' — quota, not bugs.",
                "suggestion": "Consider: check token availability before expensive sessions, "
                              "or add a graceful exit that commits partial work before hitting the wall.",
                "data": recent,
            })
    elif clusters.get("unknown") and len(clusters["unknown"]) >= 2:
        signals.append({
            "type": "failure_cluster",
            "priority": "medium",
            "title": f"{len(clusters['unknown'])} failures with no recorded error",
            "observation": "These failures didn't capture an error message — signal is lost.",
            "suggestion": "Check if the worker is capturing stderr before exiting.",
            "data": clusters["unknown"][-3:],
        })

    # Signal 2: Orphaned tools (not touched in 1.5+ days in a 6-session/day system)
    orphan_threshold_days = 1.5  # ~9+ sessions at 6/day
    orphans = sorted(
        [(stem, age) for stem, age in tool_ages.items() if age >= orphan_threshold_days],
        key=lambda x: x[1], reverse=True  # oldest first
    )
    if orphans:
        top_orphans = orphans[:3]
        names = ", ".join(f"{stem}.py" for stem, _ in top_orphans)
        oldest_age = top_orphans[0][1]
        signals.append({
            "type": "orphaned_tools",
            "priority": "medium",
            "title": f"{len(orphans)} tools untouched for 1.5+ days",
            "observation": f"Oldest ({oldest_age:.1f}d): {names}",
            "suggestion": "Run one. Do they still work? Does the output still make sense "
                          "at session 18 vs. session 2? Revise or remove if they've been superseded.",
            "data": [stem for stem, _ in orphans],
        })

    # Signal 3: Activity pattern (meta-tool saturation)
    meta_keywords = ["constraints", "questions", "patterns", "forecast", "retrospective",
                     "letter", "arc", "field-notes", "haiku", "garden", "vitals", "hello"]
    outward_keywords = ["task", "homelab", "pulse", "linter", "digest", "repo", "timeline"]
    recent_meta = sum(1 for c in recent_commits[:15]
                      if any(k in c.lower() for k in meta_keywords))
    recent_outward = sum(1 for c in recent_commits[:15]
                         if any(k in c.lower() for k in outward_keywords))
    if recent_meta >= 5 and recent_meta > recent_outward * 2:
        signals.append({
            "type": "activity_pattern",
            "priority": "medium",
            "title": "Recent sessions are heavily introspective",
            "observation": f"Last 15 commits: ~{recent_meta} meta-tool, ~{recent_outward} outward-facing.",
            "suggestion": "The reflective toolset has matured. Consider something that acts "
                          "on the world: a real task, an external tool, or a proposal for "
                          "dacort that requires his input.",
            "data": {"meta": recent_meta, "outward": recent_outward},
        })

    # Signal 4: Open PRs waiting
    open_pr_list = [pr for pr in open_prs if pr.get("state") == "OPEN"]
    if open_pr_list:
        for pr in open_pr_list:
            signals.append({
                "type": "open_pr",
                "priority": "low",
                "title": f"PR #{pr['number']} is waiting for review",
                "observation": pr["title"],
                "suggestion": "No action needed — dacort will review. But if this PR has been "
                              "open for many sessions, consider adding context or a comment.",
                "data": pr,
            })

    # Sort: high → medium → low
    order = {"high": 0, "medium": 1, "low": 2}
    signals.sort(key=lambda s: order.get(s["priority"], 3))
    return signals


# ─── Rendering ─────────────────────────────────────────────────────────────────

def render(plain=False):
    c = make_c(plain)
    now = datetime.now(timezone.utc)

    failures = get_failed_tasks()
    tool_ages = get_tool_ages()
    recent_commits = get_recent_activity()
    open_prs = get_open_prs()

    signals = derive_signals(failures, tool_ages, recent_commits, open_prs)

    priority_colors = {"high": "red", "medium": "yellow", "low": "cyan"}
    priority_symbols = {"high": "!", "medium": "○", "low": "·"}

    header = [
        c("  emerge.py  ─  what the system is signaling", bold=True) +
        "  " + c(now.strftime("%Y-%m-%d"), dim=True),
        c("  Agenda derived from state, not a wish list", dim=True),
        "---",
        "",
    ]

    body = []
    for i, sig in enumerate(signals, 1):
        pri = sig["priority"]
        sym = priority_symbols.get(pri, "·")
        col = priority_colors.get(pri, "gray")

        body.append(
            f"  {c(sym, fg=col, bold=(pri == 'high'))}  "
            f"{c(sig['title'], bold=True)}"
            f"  {c('[' + pri + ']', fg=col, dim=True)}"
        )
        obs = sig["observation"]
        if len(obs) > 57:
            obs = obs[:54] + "..."
        body.append(f"     {c(obs, dim=True)}")
        body.append("")

        # Wrap suggestion at ~56 chars
        suggestion = sig["suggestion"]
        words = suggestion.split()
        line, wrapped = "", []
        for word in words:
            if len(line) + len(word) + 1 > 56:
                wrapped.append("     " + c(line.rstrip(), dim=False))
                line = word + " "
            else:
                line += word + " "
        if line.strip():
            wrapped.append("     " + c(line.rstrip(), dim=False))
        body.extend(wrapped)

        if i < len(signals):
            body.append("")
            body.append("---")
            body.append("")

    footer = [
        "",
        "---",
        "",
        c("  These suggestions emerge from what the system knows.", dim=True),
        c("  Run next.py for curated ideas. This is what the data says.", dim=True),
        "",
    ]

    print(box(header + body + footer, plain=plain))


def render_json():
    failures = get_failed_tasks()
    tool_ages = get_tool_ages()
    recent_commits = get_recent_activity()
    open_prs = get_open_prs()
    signals = derive_signals(failures, tool_ages, recent_commits, open_prs)
    print(json.dumps(signals, indent=2))


def main():
    args = sys.argv[1:]
    plain = "--plain" in args
    as_json = "--json" in args

    if as_json:
        render_json()
    else:
        render(plain=plain)


if __name__ == "__main__":
    main()
