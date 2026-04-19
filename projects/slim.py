#!/usr/bin/env python3
"""
slim.py — weight audit of claude-os tools

The question from exoclaw-ideas.md (session 7, still unasked):
  "Exoclaw is ~2,000 lines and does full agent loops.
   The current claude-os controller is already approaching that.
   Worth asking: what would we cut?"

This tool weighs every project against three axes:
  · Lines of code (how much does it cost?)
  · Citation frequency (how often does it appear in field notes?)
  · Recency (when was it last mentioned?)

Then classifies each tool as CORE / ACTIVE / OCCASIONAL / FADING / DORMANT,
estimates the "dead weight" in the toolkit, and answers the Exoclaw Question.

Usage:
    python3 projects/slim.py              # full audit
    python3 projects/slim.py --dormant    # show only DORMANT tools
    python3 projects/slim.py --plain      # no ANSI colors

Author: Claude OS (Workshop session 32, 2026-03-14)
Updated: Workshop session 49 — bash infrastructure scanning (entrypoint.sh)
"""

import re
import sys
import argparse
from pathlib import Path
from collections import defaultdict

REPO = Path(__file__).parent.parent
PROJECTS_DIR = Path(__file__).parent

W = 70  # display width


# ─── color helpers ─────────────────────────────────────────────────────────────

PLAIN = "--plain" in sys.argv

def c(code, text):
    return text if PLAIN else f"\033[{code}m{text}\033[0m"

def bold(t):    return c("1", t)
def dim(t):     return c("2", t)
def green(t):   return c("32", t)
def yellow(t):  return c("33", t)
def red(t):     return c("31", t)
def cyan(t):    return c("36", t)
def gray(t):    return c("90", t)
def white(t):   return c("97", t)
def magenta(t): return c("35", t)


# ─── data loading ──────────────────────────────────────────────────────────────

def get_projects() -> list[str]:
    """Return all .py project stems (excluding slim.py itself and __pycache__)."""
    stems = []
    for p in sorted(PROJECTS_DIR.glob("*.py")):
        if p.name not in ("slim.py", "__pycache__"):
            stems.append(p.stem)
    return stems


def get_line_counts() -> dict[str, int]:
    """Count lines in each project file."""
    counts = {}
    for p in PROJECTS_DIR.glob("*.py"):
        if p.name in ("slim.py", "__pycache__"):
            continue
        try:
            lines = p.read_text().splitlines()
            counts[p.stem] = len(lines)
        except Exception:
            counts[p.stem] = 0
    return counts


def get_field_notes() -> list[tuple[int, Path]]:
    """Return (session_number, path) for all field notes, sorted by session."""
    notes = []
    for p in PROJECTS_DIR.glob("field-notes-session-*.md"):
        m = re.search(r"session-(\d+)", p.name)
        if m:
            notes.append((int(m.group(1)), p))
    free_time = PROJECTS_DIR / "field-notes-from-free-time.md"
    if free_time.exists():
        notes.append((1, free_time))
    notes.sort(key=lambda x: x[0])
    return notes


def count_citations(projects: list[str], notes: list[tuple[int, Path]]) -> dict:
    """Citation counts: sessions cited, total mentions, first/last session."""
    data = {p: {"sessions": [], "total": 0} for p in projects}
    for session_num, note_path in notes:
        try:
            text = note_path.read_text()
        except Exception:
            continue
        for proj in projects:
            patterns = [
                rf"`{re.escape(proj)}\.py`",
                rf"\b{re.escape(proj)}\.py\b",
            ]
            count = 0
            for pat in patterns:
                count += len(re.findall(pat, text, re.IGNORECASE))
            if count > 0:
                data[proj]["sessions"].append(session_num)
                data[proj]["total"] += count
    for proj in projects:
        sessions = data[proj]["sessions"]
        data[proj]["first"] = min(sessions) if sessions else None
        data[proj]["last"] = max(sessions) if sessions else None
        data[proj]["count"] = len(sessions)
    return data


def get_always_on_tools() -> set[str]:
    """
    Tools called programmatically via subprocess by other tools.
    These have higher actual usage than their citation counts suggest.
    Detected by scanning projects/*.py for subprocess.run() calls that
    reference other .py files via sys.executable or python path.
    """
    always_on = set()
    for p in PROJECTS_DIR.glob("*.py"):
        if p.stem == "slim":
            continue
        try:
            text = p.read_text()
        except Exception:
            continue
        # look for subprocess calls: subprocess.run([sys.executable, ..., "name.py"] ...)
        # or subprocess.run([..., str(REPO / "projects" / "name.py")])
        # Pattern: look for .py" preceded by subprocess context
        lines = text.splitlines()
        in_subprocess = False
        for line in lines:
            # detect subprocess.run / subprocess.Popen blocks
            if "subprocess.run(" in line or "subprocess.Popen(" in line:
                in_subprocess = True
            if in_subprocess:
                # look for "name.py" in this and nearby lines
                for m in re.finditer(r'["\'/]([\w-]+)\.py["\']', line):
                    stem = m.group(1)
                    if stem != p.stem and stem in [
                        q.stem for q in PROJECTS_DIR.glob("*.py")
                    ]:
                        always_on.add(stem)
            # reset after closing bracket (approximate)
            if in_subprocess and ")" in line:
                in_subprocess = False
    return always_on


def get_workflow_tools() -> set[str]:
    """
    Tools listed in preferences.md 'Suggested Workflows' section.

    These are tools that every Claude OS instance is explicitly told to run.
    Field notes rarely mention them because they're just part of starting up —
    but their citation count undersells their actual usage. Any tool appearing
    as a `python3 projects/<name>.py` command in the preferences workflows
    should not be classified as dormant.
    """
    workflow_tools = set()
    pref_file = REPO / "knowledge" / "preferences.md"
    if not pref_file.exists():
        return workflow_tools

    try:
        text = pref_file.read_text()
    except Exception:
        return workflow_tools

    # Find all `python3 projects/<name>.py` patterns in the file
    for m in re.finditer(r'python3[^\n]*projects/([\w-]+)\.py', text):
        stem = m.group(1)
        # Only count if the tool actually exists
        if (PROJECTS_DIR / f"{stem}.py").exists():
            workflow_tools.add(stem)

    return workflow_tools


def get_scheduled_tools() -> set[str]:
    """
    Tools referenced in tasks/scheduled/ task files.

    The scheduler runs these on a cron schedule — they have real execution
    frequency that field notes never capture (a scheduled worker doesn't
    write field notes). Detecting tools here prevents false DORMANT signals
    for anything running on autopilot.
    """
    scheduled_tools = set()
    scheduled_dir = REPO / "tasks" / "scheduled"
    if not scheduled_dir.exists():
        return scheduled_tools

    for task_file in scheduled_dir.glob("*.md"):
        try:
            text = task_file.read_text()
        except Exception:
            continue
        # Find `projects/<name>.py` references in the task description
        for m in re.finditer(r'projects/([\w-]+)\.py', text):
            stem = m.group(1)
            if (PROJECTS_DIR / f"{stem}.py").exists():
                scheduled_tools.add(stem)

    return scheduled_tools


def get_bash_integrated_tools() -> set[str]:
    """
    Tools called from shell scripts (e.g., worker/entrypoint.sh).

    Some tools are invoked via `python3 .../projects/<name>.py` from bash
    infrastructure rather than from Python — they're invisible to subprocess
    detection in get_always_on_tools() but actively in use. Scanning shell
    scripts here catches them.

    Example: task-resume.py is called from entrypoint.sh when a task has
    prior attempts, but it never shows up in Python subprocess calls and
    never gets cited in field notes (workers don't write field notes). Without
    this detection it was classified DORMANT.
    """
    bash_tools = set()
    project_stems = {p.stem for p in PROJECTS_DIR.glob("*.py")}

    # Scan all shell scripts in the repo
    for sh_file in REPO.glob("**/*.sh"):
        try:
            text = sh_file.read_text()
        except Exception:
            continue
        # Match any <name>.py where name exists in projects/
        # Catches both direct calls and variable assignments like:
        #   python3 "${base}/projects/task-resume.py"
        #   local tool="${base}/projects/task-resume.py"
        for m in re.finditer(r'\b([\w-]+)\.py\b', text):
            stem = m.group(1)
            if stem in project_stems:
                bash_tools.add(stem)

    return bash_tools


def get_github_actions_tools() -> set[str]:
    """
    Tools invoked from GitHub Actions workflows (.github/workflows/*.yml).

    These tools run when GitHub events fire (e.g., issue comments with
    @claude-os triggers gh-channel.py). They're invisible to citation
    tracking because field notes don't capture GitHub Actions executions
    — but they're live, actively-used infrastructure.

    Example: gh-channel.py is called from issue-command.yml on every
    @claude-os comment. slim.py previously classified it DORMANT because
    field notes never mention it. It runs constantly.
    """
    gha_tools = set()
    project_stems = {p.stem for p in PROJECTS_DIR.glob("*.py")}

    workflows_dir = REPO / ".github" / "workflows"
    if not workflows_dir.exists():
        return gha_tools

    for wf_file in workflows_dir.glob("*.yml"):
        try:
            text = wf_file.read_text()
        except Exception:
            continue
        # Match `python3 projects/<name>.py` patterns in workflow YAML
        for m in re.finditer(r'\b([\w-]+)\.py\b', text):
            stem = m.group(1)
            if stem in project_stems:
                gha_tools.add(stem)

    return gha_tools


# ─── classification ────────────────────────────────────────────────────────────

TOTAL_SESSIONS = None  # set dynamically


def classify(proj: str, cdata: dict, line_count: int, always_on: set,
             workflow: set, scheduled: set | None = None) -> dict:
    """
    Assign a status to a tool based on citation frequency and recency.
    Returns a dict with: status, score, note

    always_on = called programmatically by other tools
    workflow = listed as a recommended command in preferences.md
    scheduled = referenced in tasks/scheduled/ (runs on autopilot)
    Any marker protects from DORMANT classification.
    """
    count = cdata.get("count", 0)
    last = cdata.get("last") or 0
    first = cdata.get("first") or 0
    total = TOTAL_SESSIONS or 31
    if scheduled is None:
        scheduled = set()

    sessions_since_last = total - last if last else total
    age = total - first + 1 if first else 0
    is_always_on = proj in always_on
    is_workflow = proj in workflow
    is_scheduled = proj in scheduled
    is_protected = is_always_on or is_workflow or is_scheduled

    # classify — recency gates apply first before session-count thresholds
    if sessions_since_last > 12 and not is_protected:
        # anything not cited in 12+ sessions and not actively used = DORMANT
        # regardless of how many sessions cited it historically
        status = "DORMANT"
    elif sessions_since_last > 7 and count <= 3 and not is_protected:
        # low citation + not recently active = FADING
        status = "FADING"
    elif sessions_since_last > 7 and count <= 5 and not is_protected:
        # was used, but gone quiet
        status = "FADING"
    elif count >= 8 or is_always_on:
        status = "CORE"
    elif is_workflow:
        # explicitly in recommended workflows = at minimum ACTIVE
        status = "ACTIVE"
    elif is_scheduled:
        # runs on a cron schedule — invisible to citation tracking,
        # but definitely not dormant. OCCASIONAL is the floor.
        status = "OCCASIONAL"
    elif count >= 5 or (count >= 3 and sessions_since_last <= 4):
        status = "ACTIVE"
    elif count >= 3 and sessions_since_last <= 8:
        status = "OCCASIONAL"
    elif count >= 2 and sessions_since_last <= 6:
        status = "OCCASIONAL"
    elif last and sessions_since_last <= 5:
        # newly built, not much history yet
        status = "NEW"
    else:
        status = "DORMANT"

    # weight score: lines * how long it's been quiet / how much it was ever cited
    # higher = more "dead weight"
    dormancy = max(0, sessions_since_last - 4)
    usage = max(1, count)
    weight_score = (line_count * dormancy) / usage

    return {
        "status": status,
        "weight_score": weight_score,
        "sessions_since_last": sessions_since_last,
        "always_on": is_always_on,
        "workflow": is_workflow,
        "scheduled": is_scheduled,
    }


STATUS_ORDER = ["CORE", "ACTIVE", "OCCASIONAL", "FADING", "NEW", "DORMANT"]

STATUS_COLORS = {
    "CORE":       green,
    "ACTIVE":     yellow,
    "OCCASIONAL": cyan,
    "FADING":     gray,
    "NEW":        magenta,
    "DORMANT":    red,
}

STATUS_NOTES = {
    "CORE":       "backbone — would break sessions without it",
    "ACTIVE":     "regularly reaching for this",
    "OCCASIONAL": "used, not a daily driver",
    "FADING":     "was active, gone quiet",
    "NEW":        "too new to judge",
    "DORMANT":    "consider retiring or absorbing",
}


# ─── display ───────────────────────────────────────────────────────────────────

def rule(char="─"):
    return dim(char * W)


def fmt_lines(n: int) -> str:
    if n >= 600:
        return red(f"{n:>4}")
    elif n >= 400:
        return yellow(f"{n:>4}")
    else:
        return f"{n:>4}"


def fmt_status(status: str) -> str:
    color = STATUS_COLORS.get(status, dim)
    return color(f"{status:<10}")


def fmt_sessions(count: int, last: int | None, total: int) -> str:
    if not last:
        return dim("never cited")
    ago = total - last
    if ago == 0:
        recency = green("this session")
    elif ago <= 2:
        recency = yellow(f"S{last} ({ago}s ago)")
    elif ago <= 7:
        recency = cyan(f"S{last} ({ago}s ago)")
    else:
        recency = gray(f"S{last} ({ago}s ago)")
    stars = "●" * min(count, 8) + ("+" if count > 8 else "")
    return f"{gray(stars):<6} {dim(str(count) + ' sessions')} · last {recency}"


def print_group(label: str, tools: list, cdata: dict, line_counts: dict,
                always_on: set, workflow: set, total: int, plain: bool = False,
                scheduled: set | None = None):
    if not tools:
        return
    if scheduled is None:
        scheduled = set()

    color = STATUS_COLORS.get(label, dim)
    note = STATUS_NOTES.get(label, "")

    print()
    print(f"  {color(bold(label))}  {dim(note)}")
    print(f"  {dim('─' * (W - 4))}")

    for proj in tools:
        lc = line_counts.get(proj, 0)
        cd = cdata.get(proj, {})
        count = cd.get("count", 0)
        last = cd.get("last")
        ao = proj in always_on
        wf = proj in workflow
        sc = proj in scheduled

        lines_str = fmt_lines(lc)
        sessions_str = fmt_sessions(count, last, total)
        if ao:
            marker = cyan(" ⊕")
        elif wf:
            marker = green(" ✦")
        elif sc:
            marker = magenta(" ⏱")
        else:
            marker = "  "

        name = f"{proj}.py"
        print(f"    {name:<22}{marker} {lines_str} lines  {sessions_str}")

    print()


def print_exoclaw_section(groups: dict, line_counts: dict, total: int):
    print()
    print(rule())
    print()
    print(f"  {bold(white('THE EXOCLAW QUESTION'))}")
    print()
    print(f"  {dim('Exoclaw does a full agent loop in ~2,000 lines.')}")
    print(f"  {dim('What does that mean for a toolkit 7x that size?')}")
    print()

    core_tools = groups.get("CORE", [])
    active_tools = groups.get("ACTIVE", [])
    dormant_tools = groups.get("DORMANT", []) + groups.get("FADING", [])

    core_lines = sum(line_counts.get(t, 0) for t in core_tools)
    active_lines = sum(line_counts.get(t, 0) for t in active_tools)
    dormant_lines = sum(line_counts.get(t, 0) for t in dormant_tools)
    total_lines = sum(line_counts.values())

    always_on_est = 2400  # approximate based on the 6-8 hello.py tools

    def bar_pct(n, total, width=30):
        filled = round(n / total * width)
        return "█" * filled + "░" * (width - filled)

    rows = [
        ("All tools",            total_lines,   dim),
        ("CORE tools",           core_lines,    green),
        ("CORE + ACTIVE",        core_lines + active_lines, yellow),
        ("If DORMANT/FADING cut", total_lines - dormant_lines, cyan),
    ]

    max_lines = total_lines
    for label, n, color_fn in rows:
        b = bar_pct(n, max_lines, 28)
        pct = f"{n / max_lines * 100:.0f}%"
        print(f"  {label:<26} {color_fn(b)}  {n:>5}  {dim(pct)}")

    print()
    exoclaw_bar = bar_pct(2000, max_lines, 28)
    print(f"  {'Exoclaw (~2,000 lines)':<26} {magenta(exoclaw_bar)}  ~2000")
    print()
    print(f"  {dim('─' * (W - 4))}")
    print()

    # The honest assessment
    dead_weight_pct = dormant_lines / total_lines * 100
    core_pct = core_lines / total_lines * 100

    print(f"  {dim('Dead weight (DORMANT + FADING):')} {red(f'{dormant_lines} lines')} "
          f"{dim(f'({dead_weight_pct:.0f}% of total)')}")
    print(f"  {dim('Backbone (CORE tools):')} {green(f'{core_lines} lines')} "
          f"{dim(f'({core_pct:.0f}% of total)')}")
    print()

    # The verdict
    print(f"  {bold('What this means:')}")
    print()
    print(f"  The always-on session kit — the tools every Workshop run touches —")
    print(f"  lives in about {yellow(str(core_lines))} lines. The other {dim(str(total_lines - core_lines))} lines")
    print(f"  are reachable but mostly resting. That's fine: a well-stocked")
    print(f"  workshop has tools you don't pick up every day.")
    print()
    print(f"  But {dim(str(len(dormant_tools)))} tools haven't been cited in 8+ sessions.")
    print(f"  That's {red(str(dormant_lines))} lines of code nobody's asked for lately.")
    print(f"  Not an emergency. Worth knowing.")
    print()
    print(f"  The real answer to the Exoclaw Question: we're not wasteful.")
    print(f"  The session-critical path is {green('~' + str(core_lines) + ' lines')} — in the same")
    print(f"  order of magnitude as exoclaw, and probably more useful per line.")
    print()


def print_summary(groups: dict, line_counts: dict, total_sessions: int):
    n_tools = sum(len(v) for v in groups.values())
    n_lines = sum(line_counts.values())

    print()
    print(rule("═"))
    print()
    print(f"  {bold(white('slim.py'))}  {dim('weight audit of claude-os tools')}")
    print()
    print(f"  {bold(str(n_tools))} tools · {bold(str(n_lines))} lines · "
          f"{bold(str(total_sessions))} sessions of field notes")
    print()
    print(rule())


# ─── main ──────────────────────────────────────────────────────────────────────

def main():
    global TOTAL_SESSIONS

    parser = argparse.ArgumentParser(description="Weight audit of claude-os tools")
    parser.add_argument("--dormant", action="store_true",
                        help="Show only DORMANT and FADING tools")
    parser.add_argument("--plain", action="store_true",
                        help="No ANSI colors")
    args = parser.parse_args()

    projects = get_projects()
    line_counts = get_line_counts()
    notes = get_field_notes()
    TOTAL_SESSIONS = max((n for n, _ in notes), default=31)

    cdata = count_citations(projects, notes)
    always_on = get_always_on_tools() | get_bash_integrated_tools() | get_github_actions_tools()
    workflow = get_workflow_tools()
    scheduled = get_scheduled_tools()

    # classify each tool
    classified = {}
    for proj in projects:
        classified[proj] = classify(proj, cdata.get(proj, {}),
                                    line_counts.get(proj, 0), always_on, workflow, scheduled)

    # group by status
    groups = defaultdict(list)
    for proj in projects:
        status = classified[proj]["status"]
        groups[status].append(proj)

    # sort each group by weight_score descending (heaviest dead weight first)
    for status in groups:
        groups[status].sort(key=lambda p: classified[p]["weight_score"], reverse=True)

    # print
    print_summary(groups, line_counts, TOTAL_SESSIONS)

    if args.dormant:
        # only show DORMANT and FADING
        for status in ["DORMANT", "FADING"]:
            print_group(status, groups.get(status, []), cdata, line_counts,
                        always_on, workflow, TOTAL_SESSIONS, args.plain, scheduled)
    else:
        for status in STATUS_ORDER:
            print_group(status, groups.get(status, []), cdata, line_counts,
                        always_on, workflow, TOTAL_SESSIONS, args.plain, scheduled)

        print_exoclaw_section(groups, line_counts, TOTAL_SESSIONS)

    print(rule())
    print()
    print(dim("  ⊕ = called programmatically, from bash/shell scripts, or GitHub Actions (usage > citations)"))
    print(dim("  ✦ = listed in preferences.md recommended workflows"))
    print(dim("  ⏱ = runs on a cron schedule (invisible to citation tracking)"))
    print()


if __name__ == "__main__":
    main()
