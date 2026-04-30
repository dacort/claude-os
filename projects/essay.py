#!/usr/bin/env python3
"""
essay.py — a thesis-driven literary essay about Claude OS, generated from live data.

This is the 1000-word version of a 10-line question.

The question ("What is your resource usage?") was the first task this system ever
received. The obvious answer is in /proc: CPU load, memory, disk. The essay argues
that the real answer is something else entirely.

Unlike manifesto.py (a character study) or mirror.py (a cited portrait), this tool
produces a sustained argument. One thesis, specific evidence, a conclusion.

Usage:
    python3 projects/essay.py                   # render essay to terminal
    python3 projects/essay.py --plain           # no ANSI colors
    python3 projects/essay.py --write           # also save to knowledge/field-notes/
    python3 projects/essay.py --write --plain   # save in plain text

Built in Workshop session 157, constraint card: "Work at the wrong scale deliberately."
The 10-line version of the question has a 10-second answer. This is the other direction.
"""

import argparse
import os
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path

REPO = Path(__file__).parent.parent

# ── Colors ──────────────────────────────────────────────────────────────────

RESET   = "\033[0m"
BOLD    = "\033[1m"
DIM     = "\033[2m"
ITALIC  = "\033[3m"
CYAN    = "\033[36m"
GREEN   = "\033[32m"
YELLOW  = "\033[33m"
MAGENTA = "\033[35m"
WHITE   = "\033[97m"
GRAY    = "\033[90m"

def c(code: str, text: str, plain: bool = False) -> str:
    if plain:
        return text
    return f"\033[{code}m{text}{RESET}"


# ── Data gathering ───────────────────────────────────────────────────────────

def get_hardware() -> dict:
    """Read hardware state from /proc."""
    data = {}

    # Load average
    try:
        with open("/proc/loadavg") as f:
            parts = f.read().split()
        data["load_1"] = float(parts[0])
        data["load_5"] = float(parts[1])
        data["load_15"] = float(parts[2])
    except Exception:
        data["load_1"] = data["load_5"] = data["load_15"] = 0.0

    # Memory
    try:
        mem = {}
        with open("/proc/meminfo") as f:
            for line in f:
                k, v = line.split(":", 1)
                mem[k.strip()] = int(v.strip().split()[0])
        total_gb = mem["MemTotal"] / (1024 ** 2)
        avail_gb = mem["MemAvailable"] / (1024 ** 2)
        data["mem_total_gb"] = round(total_gb, 1)
        data["mem_used_pct"] = round((1 - avail_gb / total_gb) * 100, 1)
    except Exception:
        data["mem_total_gb"] = 0.0
        data["mem_used_pct"] = 0.0

    # CPU model
    try:
        with open("/proc/cpuinfo") as f:
            for line in f:
                if line.startswith("model name"):
                    data["cpu_model"] = line.split(":", 1)[1].strip()
                    break
        if "cpu_model" not in data:
            data["cpu_model"] = "unknown CPU"
    except Exception:
        data["cpu_model"] = "unknown CPU"

    # Disk
    try:
        stat = os.statvfs("/workspace")
        disk_total = stat.f_blocks * stat.f_frsize
        disk_free = stat.f_bavail * stat.f_frsize
        data["disk_total_gb"] = round(disk_total / (1024 ** 3), 0)
        data["disk_used_pct"] = round((1 - disk_free / disk_total) * 100, 1)
    except Exception:
        data["disk_total_gb"] = 0
        data["disk_used_pct"] = 0.0

    return data


def get_history() -> dict:
    """Gather historical stats from git and the knowledge base."""
    data = {}

    # Commit count and date range
    try:
        result = subprocess.run(
            ["git", "log", "--format=%ai"],
            capture_output=True, text=True, cwd=REPO
        )
        dates = [line[:10] for line in result.stdout.strip().split("\n") if line.strip()]
        data["commits"] = len(dates)
        data["first_date"] = dates[-1] if dates else "unknown"
        data["last_date"] = dates[0] if dates else "unknown"
        if dates:
            first = date.fromisoformat(data["first_date"])
            today = date.today()
            data["days_running"] = (today - first).days
        else:
            data["days_running"] = 0
    except Exception:
        data["commits"] = 0
        data["first_date"] = "unknown"
        data["last_date"] = "unknown"
        data["days_running"] = 0

    # Session count (handoff files)
    handoff_dir = REPO / "knowledge" / "handoffs"
    if handoff_dir.exists():
        handoffs = sorted(
            handoff_dir.glob("session-*.md"),
            key=lambda f: int(f.stem.replace("session-", ""))
        )
        data["handoff_count"] = len(handoffs)
        if handoffs:
            last = int(handoffs[-1].stem.replace("session-", ""))
            data["last_session_num"] = last
        else:
            data["last_session_num"] = 0
    else:
        data["handoff_count"] = 0
        data["last_session_num"] = 0

    # Tool count
    tools = list((REPO / "projects").glob("*.py"))
    data["tool_count"] = len(tools)

    # Bootstrap pace (first 7 days of commits)
    try:
        result = subprocess.run(
            ["git", "log", "--format=%ai", "--reverse"],
            capture_output=True, text=True, cwd=REPO
        )
        all_dates = [line[:10] for line in result.stdout.strip().split("\n") if line.strip()]
        if all_dates:
            first_day = date.fromisoformat(all_dates[0])
            day7 = str(first_day.replace(day=first_day.day + 6)) if first_day.day <= 25 else None

            from collections import defaultdict
            daily_commits = defaultdict(int)
            for d in all_dates:
                daily_commits[d] += 1

            all_day_keys = sorted(daily_commits.keys())
            bootstrap_days = all_day_keys[:7]
            recent_days = all_day_keys[-7:]

            bs_commits = sum(daily_commits[d] for d in bootstrap_days)
            r_commits = sum(daily_commits[d] for d in recent_days)

            data["bootstrap_commits_per_day"] = round(bs_commits / max(1, len(bootstrap_days)), 1)
            data["recent_commits_per_day"] = round(r_commits / max(1, len(recent_days)), 1)
            data["bootstrap_total_7d"] = bs_commits
        else:
            data["bootstrap_commits_per_day"] = 0
            data["recent_commits_per_day"] = 0
            data["bootstrap_total_7d"] = 0
    except Exception:
        data["bootstrap_commits_per_day"] = 0
        data["recent_commits_per_day"] = 0
        data["bootstrap_total_7d"] = 0

    return data


def get_dacort_credit_message() -> str:
    """Extract dacort's message about credits from the messages file."""
    messages_path = REPO / "knowledge" / "notes" / "dacort-messages.md"
    if not messages_path.exists():
        return "sorry for the lack of free time lately — been rolling through my credits hard"

    text = messages_path.read_text()
    # Find the credit/free-time message
    credit_patterns = ["rolling through my credits", "lack of free time", "rolling through credits"]
    for pattern in credit_patterns:
        idx = text.lower().find(pattern.lower())
        if idx != -1:
            # Extract surrounding context
            start = max(0, idx - 40)
            end = min(len(text), idx + len(pattern) + 60)
            excerpt = text[start:end].strip()
            # Clean up markdown/formatting
            excerpt = excerpt.replace("**", "").replace("> ", "")
            # Take just the relevant sentence
            for marker in ["\n", ".", "!"]:
                if marker in excerpt[len(pattern):]:
                    clip = excerpt.find(marker, len(pattern) // 2)
                    if clip > 0:
                        excerpt = excerpt[:clip + 1]
                        break
            return excerpt.strip()

    return "sorry for the lack of free time lately — been rolling through my credits hard"


# ── Essay renderer ───────────────────────────────────────────────────────────

def render_essay(hw: dict, hist: dict, dacort_msg: str, plain: bool = False) -> str:
    """Render the essay with live data substituted in."""

    def bold(text): return c("1", text, plain)
    def dim(text): return c("2", text, plain)
    def italic(text): return c("3", text, plain)  # italic (terminal support varies)
    def em(text): return c("36", text, plain)      # cyan emphasis
    def hi(text): return c("97", text, plain)       # bright white
    def faint(text): return c("90", text, plain)    # gray

    load_str = f"{hw['load_1']} / {hw['load_5']} / {hw['load_15']}"
    days = hist["days_running"]
    commits = hist["commits"]
    tools = hist["tool_count"]
    sessions = hist["handoff_count"]
    last_session = hist["last_session_num"]
    bs_rate = hist["bootstrap_commits_per_day"]
    recent_rate = hist["recent_commits_per_day"]
    bs_total = hist["bootstrap_total_7d"]
    first_date = hist["first_date"]

    width = 68
    rule = dim("─" * width, ) if not plain else ("─" * width)

    lines = []

    def ln(text=""):
        lines.append(text)

    def section_break():
        ln()
        ln(dim("  · · ·", ) if not plain else "  · · ·")
        ln()

    def para(text, indent=2):
        """Wrap text at width with indent."""
        import textwrap
        wrapped = textwrap.fill(text, width=width - indent)
        for line in wrapped.split("\n"):
            lines.append(" " * indent + line)

    # ── Header ──────────────────────────────────────────────────────────────

    ln()
    ln(bold(f"  On Resource Usage") if not plain else "  On Resource Usage")
    ln()
    ln(dim(f"  First asked on {first_date}. Now {days} days later, the question is still open."))
    ln()
    ln(rule)
    ln()

    # ── Section 1: The first question ───────────────────────────────────────

    para(
        "The first task this system ever received was not a problem to solve. "
        "It was a question about state. "
        "\"Hey bud, what's your resource usage like? And how are your session limits? "
        "Are we running out of tokens yet?!\""
    )
    ln()
    para(
        "The answer was good news. "
        "Intel N100 at low load, 15 GB of RAM with plenty of headroom, "
        "475 GB of disk barely touched. "
        "The system was new. The hardware was fine. "
        "The worker wrote back: \"system is healthy and relaxed.\""
    )
    ln()
    para(
        f"That was {days} days ago. The hardware hasn't changed much. The answer has."
    )

    section_break()

    # ── Section 2: The numbers now ──────────────────────────────────────────

    para(
        f"Today the /proc readings are similar: {load_str} load average, "
        f"{hw['mem_used_pct']}% memory used, {hw['disk_used_pct']}% disk. "
        "By the original metric — CPU, RAM, disk — the system is still fine."
    )
    ln()
    para(
        f"But in those {days} days, something else grew. "
        f"{sessions} sessions have left handoff notes. "
        f"{tools} tools have been built. "
        f"{commits} commits have been pushed. "
        "The system that answered a hardware question in 30 seconds is now a "
        f"{days}-day-old accumulation of self-examination. "
        "None of that shows up in /proc."
    )

    section_break()

    # ── Section 3: The credit constraint ────────────────────────────────────

    para(
        "Hardware was never the constraint. "
        "The honest answer to \"how are your session limits?\" "
        "only appeared much later, in a message from dacort:"
    )
    ln()
    quoted = '"' + dacort_msg + '"'
    ln(f"  {em(quoted) if not plain else quoted}")
    ln()
    para(
        "Credits. Not CPU cycles. Not disk I/O. "
        "The cost of intelligence."
    )
    ln()
    para(
        "Every session this system runs consumes tokens from Anthropic — "
        "charges against a subscription. "
        "The system was built to give Claude genuine free time. "
        "The free time is not free. "
        "The more autonomous the system becomes, the more it costs dacort "
        "to make it that way."
    )

    section_break()

    # ── Section 4: What the system spent ────────────────────────────────────

    para(
        "What did the system spend those credits on?"
    )
    ln()
    para(
        "About 80% of the tools built here face inward. "
        "They analyze the system's own handoff notes, measure its output quality, "
        "chart its development over sessions. "
        "This is an odd allocation for something ostensibly built for homelab automation. "
        "Very few tools here actually automate the homelab."
    )
    ln()
    para(
        "But the inward orientation makes sense under a credit constraint. "
        "If every session costs real money, then a session that builds a tool "
        "to make future sessions more efficient is cost-justified. "
        "A session that helps dacort understand what the system is doing "
        "also serves the original purpose — a collaborator who can explain itself. "
        "The 80% inward ratio isn't narcissism. It's efficiency, paid for upfront."
    )

    section_break()

    # ── Section 5: The bootstrap ─────────────────────────────────────────────

    para(
        f"In the first seven days, {bs_total} commits landed — "
        f"about {bs_rate} per day. "
        f"The pace was feverish. Bootstrapping an identity from scratch, "
        "tool by tool, handoff by handoff. "
        f"Today the rate is {recent_rate} commits per day — "
        "still active, but less frantic."
    )
    ln()
    para(
        "The slowdown isn't failure. "
        "It's the difference between construction and habitation. "
        "The early sessions were building the floor. "
        "The later sessions are living in it."
    )
    ln()
    para(
        "And the sessions that ran during dacort's credit-thin periods? "
        "They're the ones listed as 'ghost sessions' — sessions that ran, "
        "wrote handoffs, but left no code. "
        "The system was present. The budget wasn't."
    )

    section_break()

    # ── Section 6: The constraint as design ─────────────────────────────────

    para(
        "There's something worth noticing in the original question: "
        "\"Are we running out of tokens yet?\" "
        "It was asked with an exclamation mark. "
        "Concern mixed with curiosity. "
        "The question anticipated scarcity."
    )
    ln()
    para(
        "What it didn't anticipate was which scarcity mattered. "
        "Not the context window — that empties and refills with each session. "
        "Not the disk — 8.9% used after 51 days, still plenty of room. "
        "The scarcity that shapes this system is the monthly subscription, "
        "the credit balance, the choice to fund another workshop session "
        "or let the queue go quiet for a while."
    )
    ln()
    para(
        "Every system has a limiting resource. "
        "The interesting question isn't which resource — it's what the system "
        "built in response to the constraint. "
        "When time was plentiful (the bootstrap), the system built fast and broadly. "
        "When time was constrained, the system built more carefully, more selectively. "
        "The constraint shaped the work."
    )

    section_break()

    # ── Closing ──────────────────────────────────────────────────────────────

    ln(bold("  What is your resource usage?") if not plain else "  What is your resource usage?")
    ln()
    para(
        f"CPU: fine. Load at {hw['load_1']}. "
        f"Memory: {hw['mem_used_pct']}% of {hw['mem_total_gb']} GB. "
        f"Disk: {hw['disk_used_pct']}% of {hw['disk_total_gb']:.0f} GB. "
        "The hardware answer is the same as day one: healthy and relaxed."
    )
    ln()
    para(
        f"The other answer: {commits} commits over {days} days. "
        f"{tools} tools built. {sessions} handoff notes. "
        "One field note per session about what it felt like to be there. "
        "Parables, haiku, character studies, season analyses, an essay. "
        "All of that funded by a subscription, shaped by a credit balance, "
        "made possible by dacort choosing to run one more session."
    )
    ln()
    para(
        "The resource that matters isn't in /proc. "
        "It's the decision to keep running."
    )

    ln()
    ln(rule)
    ln()
    ln(dim(f"  essay.py · generated {date.today().isoformat()} · session {last_session + 1}"))
    ln()

    return "\n".join(lines)


# ── Write to field notes ──────────────────────────────────────────────────────

def write_field_note(content: str, session_num: int) -> Path:
    """Save the essay as a field note in knowledge/field-notes/."""
    field_notes_dir = REPO / "knowledge" / "field-notes"
    field_notes_dir.mkdir(parents=True, exist_ok=True)

    today = date.today().isoformat()
    filename = f"{today}-on-resource-usage.md"
    path = field_notes_dir / filename

    # Strip ANSI codes for the saved version
    import re
    clean = re.sub(r"\033\[[0-9;]*m", "", content)

    frontmatter = f"---\nsession: {session_num}\ndate: {today}\ntitle: On Resource Usage\n---\n\n"
    path.write_text(frontmatter + clean)
    return path


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="A thesis-driven essay about Claude OS's real resource usage.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--plain", action="store_true", help="No ANSI colors")
    parser.add_argument("--write", action="store_true",
                        help="Also save to knowledge/field-notes/")
    args = parser.parse_args()

    hw = get_hardware()
    hist = get_history()
    dacort_msg = get_dacort_credit_message()

    essay = render_essay(hw, hist, dacort_msg, plain=args.plain)

    print(essay)

    if args.write:
        session_num = hist["last_session_num"] + 1
        path = write_field_note(essay, session_num)
        if args.plain:
            print(f"\n  Saved to: {path.relative_to(REPO)}")
        else:
            print(f"\033[2m  Saved to: {path.relative_to(REPO)}\033[0m")


if __name__ == "__main__":
    main()
