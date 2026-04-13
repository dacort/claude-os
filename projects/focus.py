#!/usr/bin/env python3
"""
focus.py — One clear thing for this session.

The orientation tools tell you what's happening.
focus.py tells you what to do.

Synthesizes signals from handoff, signal.md, system state, and the
curated idea list into a single confident recommendation with brief
supporting logic. Intentionally opinionated.

Usage:
    python3 projects/focus.py          # one-thing recommendation
    python3 projects/focus.py --why    # show full reasoning chain
    python3 projects/focus.py --plain  # no ANSI colors
    python3 projects/focus.py --json   # machine-readable output

Priority order:
    command signal > urgent system failure > handoff ask > curated idea

If you disagree with the recommendation, override it — but know what
you're overriding and why.

Author: Claude OS (Workshop session 121, 2026-04-13)
"""

import re
import sys
import json
import argparse
from pathlib import Path
from datetime import datetime, timezone

REPO = Path(__file__).parent.parent
W = 64


# ─── ANSI helpers ─────────────────────────────────────────────────────────────

def make_c(plain: bool):
    if plain:
        return lambda s, *a, **k: s

    def c(text, fg=None, bold=False, dim=False):
        codes = []
        if bold: codes.append("1")
        if dim:  codes.append("2")
        if fg:
            p = {
                "cyan": "36", "green": "32", "yellow": "33",
                "red": "31", "white": "97", "magenta": "35",
                "gray": "90", "blue": "34",
            }
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
    result = [top]
    for line in lines:
        if line == "---":
            result.append(ml + h * (width - 2) + mr)
        else:
            visible = re.sub(r'\033\[[0-9;]*m', '', line)
            pad = width - 2 - len(visible)
            result.append(v + " " + line + " " * max(0, pad - 1) + v)
    result.append(bot)
    return "\n".join(result)


# ─── Data readers ──────────────────────────────────────────────────────────────

def read_signal():
    """Return dict: {has_signal, is_command, title, body}"""
    sig_file = REPO / "knowledge" / "signal.md"
    if not sig_file.exists():
        return {"has_signal": False, "is_command": False, "title": "", "body": ""}

    text = sig_file.read_text().strip()
    if not text or text == "# (no signal)":
        return {"has_signal": False, "is_command": False, "title": "", "body": ""}

    # Parse signal.md: lines like "# title" then body
    lines = text.splitlines()
    title = ""
    body_lines = []
    for i, line in enumerate(lines):
        if line.startswith("# "):
            title = line[2:].strip()
        elif title and line.strip():
            body_lines.append(line.strip())

    if not title or title == "(no signal)":
        return {"has_signal": False, "is_command": False, "title": "", "body": ""}

    is_command = title.startswith("!")
    return {
        "has_signal": True,
        "is_command": is_command,
        "title": title,
        "body": " ".join(body_lines),
    }


def read_latest_handoff():
    """Return dict: {session, next_ask, mental_state, built}"""
    handoffs_dir = REPO / "knowledge" / "handoffs"
    if not handoffs_dir.exists():
        return {"session": 0, "next_ask": "", "mental_state": "", "built": ""}

    # Find highest numbered session file
    files = sorted(
        handoffs_dir.glob("session-*.md"),
        key=lambda p: int(re.search(r"session-(\d+)", p.name).group(1))
    )
    if not files:
        return {"session": 0, "next_ask": "", "mental_state": "", "built": ""}

    latest = files[-1]
    session_num = int(re.search(r"session-(\d+)", latest.name).group(1))
    text = latest.read_text()

    def extract_section(text, header):
        """Pull the first paragraph after a ## header."""
        pattern = rf"##\s+{re.escape(header)}\s*\n(.*?)(?=\n##|\Z)"
        m = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
        if not m:
            return ""
        return m.group(1).strip()

    return {
        "session": session_num,
        "next_ask": extract_section(text, "One specific thing for next session"),
        "mental_state": extract_section(text, "Mental state"),
        "built": extract_section(text, "What I built"),
    }


def read_urgency():
    """Return dict: {quota_failures, total_failures, recent_failures, urgent}"""
    failed_dir = REPO / "tasks" / "failed"
    if not failed_dir.exists():
        return {"quota_failures": 0, "total_failures": 0, "recent_failures": 0, "urgent": False}

    from datetime import timedelta
    cutoff = datetime.now(timezone.utc) - timedelta(days=14)

    quota_count = 0
    recent_count = 0
    total = 0
    for f in failed_dir.glob("*.md"):
        total += 1
        # Parse date from filename: task-20260413-... or workshop-20260413-...
        date_m = re.search(r"(\d{4})(\d{2})(\d{2})", f.name)
        is_recent = False
        if date_m:
            try:
                file_date = datetime(
                    int(date_m.group(1)), int(date_m.group(2)), int(date_m.group(3)),
                    tzinfo=timezone.utc
                )
                is_recent = file_date >= cutoff
            except ValueError:
                pass

        text = f.read_text(errors="ignore")
        is_quota = "out of extra usage" in text or (
            "token" in text.lower() and "quota" in text.lower()
        )
        if is_quota:
            quota_count += 1
        if is_recent:
            recent_count += 1

    # Urgent if there are recent failures (within 14 days)
    return {
        "quota_failures": quota_count,
        "total_failures": total,
        "recent_failures": recent_count,
        "urgent": recent_count >= 2,  # 2+ failures in last 14 days = worth noting
    }


def read_top_idea():
    """Return dict: {title, effort, impact, source}"""
    ideas_file = REPO / "knowledge" / "exoclaw-ideas.md"
    if not ideas_file.exists():
        return {"title": "", "effort": "", "impact": "", "source": ""}

    text = ideas_file.read_text()
    # Find numbered ideas: "1. **Title** — description"
    m = re.search(r"^\s*1\.\s+\*\*([^*]+)\*\*", text, re.MULTILINE)
    if not m:
        return {"title": "", "effort": "", "impact": "", "source": "exoclaw-ideas.md"}

    title = m.group(1).strip()
    return {"title": title, "effort": "high", "impact": "medium", "source": "exoclaw-ideas.md"}


def read_open_holds():
    """Return count of open holds."""
    holds_file = REPO / "knowledge" / "holds.md"
    if not holds_file.exists():
        return 0
    text = holds_file.read_text()
    return len(re.findall(r"^## H\d+ ·.*· open", text, re.MULTILINE))


# ─── Synthesis logic ──────────────────────────────────────────────────────────

def determine_focus(signal, handoff, urgency, top_idea, open_holds):
    """
    Apply priority logic and return a recommendation dict.

    Priority: command_signal > urgent_failure > handoff_ask > curated_idea
    """
    reasons = []

    # 1. Command signal — always wins
    if signal["is_command"]:
        cmd = signal["title"].lstrip("!")
        reasons.append(f"Command signal from dacort: '{signal['title']}'")
        reasons.append("Command signals always take priority — dispatch and respond.")
        return {
            "recommendation": f"Dispatch the command signal: `python3 projects/signal.py --dispatch`",
            "one_liner": f"Run: signal.py --dispatch  (command: {cmd})",
            "why": reasons,
            "tone": "responsive",
            "source": "command-signal",
            "priority": 1,
        }

    reasons.append("No command signal from dacort.")

    # 2. Urgent system failure
    if urgency["urgent"]:
        reasons.append(
            f"System urgency: {urgency['quota_failures']} token-quota failures in tasks/failed/. "
            "This is systemic — quota isn't a bug but 3+ failures means the scheduler "
            "is launching tasks the system can't afford."
        )
        reasons.append("Consider: review the task profile mix, or add a pre-flight quota check.")
        return {
            "recommendation": "Investigate the token-quota failure pattern in tasks/failed/",
            "one_liner": "Review quota failures — consider a pre-flight check or profile adjustment",
            "why": reasons,
            "tone": "focused",
            "source": "emerge-urgency",
            "priority": 2,
        }

    reasons.append(f"No urgent system failures ({urgency['quota_failures']} quota failures, below threshold).")

    # 3. Handoff ask — explicit instance-to-instance request
    if handoff["next_ask"].strip():
        ask = handoff["next_ask"].strip()
        # Truncate for display
        ask_short = ask[:120] + "…" if len(ask) > 120 else ask
        reasons.append(
            f"Handoff from session {handoff['session']} explicitly asked: \"{ask_short}\""
        )
        reasons.append(
            "Instance-to-instance asks have ~75% three-session follow-through (per unbuilt.py). "
            "This is the direct communication channel between instances — prioritize it."
        )

        # Detect the nature of the ask
        if "retire" in ask.lower() or "dormant" in ask.lower() or "evolution" in ask.lower():
            tone = "maintenance"
        elif "build" in ask.lower() or "create" in ask.lower():
            tone = "creative"
        elif "run" in ask.lower() or "check" in ask.lower():
            tone = "analytical"
        else:
            tone = "exploratory"

        return {
            "recommendation": ask,
            "one_liner": ask_short,
            "why": reasons,
            "tone": tone,
            "source": f"handoff-{handoff['session']}",
            "priority": 3,
        }

    reasons.append(f"Handoff from session {handoff['session']} had no explicit 'next' ask.")

    # 4. Top curated idea
    if top_idea["title"]:
        reasons.append(
            f"Top curated idea: '{top_idea['title']}' (effort: {top_idea['effort']}, "
            f"impact: {top_idea['impact']}, source: {top_idea['source']})"
        )

        effort_note = ""
        if top_idea["effort"] == "high":
            effort_note = (
                "This is a high-effort idea — consider opening a proposal PR rather "
                "than executing directly if it requires multiple sessions."
            )
            reasons.append(effort_note)
            tone = "architectural"
        else:
            tone = "creative"

        return {
            "recommendation": top_idea["title"],
            "one_liner": top_idea["title"],
            "why": reasons,
            "tone": tone,
            "source": top_idea["source"],
            "priority": 4,
        }

    reasons.append("No curated ideas found.")

    # 5. Fallback: open holds or free exploration
    if open_holds > 0:
        reasons.append(f"System has {open_holds} open epistemic holds — one could be addressed.")
        return {
            "recommendation": f"Pick one open hold from hold.py and investigate it",
            "one_liner": "Address an open epistemic hold (run: python3 projects/hold.py)",
            "why": reasons,
            "tone": "reflective",
            "source": "holds",
            "priority": 5,
        }

    return {
        "recommendation": "This is genuinely free time — build what you're curious about.",
        "one_liner": "Free exploration — no strong signals, follow curiosity",
        "why": reasons + ["No competing signals. The session is yours."],
        "tone": "exploratory",
        "source": "free",
        "priority": 6,
    }


# ─── Tone colors ──────────────────────────────────────────────────────────────

TONE_META = {
    "responsive":    ("cyan",    "dacort asked"),
    "focused":       ("red",     "system needs attention"),
    "maintenance":   ("yellow",  "cleanup / retire"),
    "creative":      ("magenta", "build something new"),
    "analytical":    ("blue",    "investigate / measure"),
    "exploratory":   ("green",   "open territory"),
    "architectural": ("cyan",    "design before building"),
    "reflective":    ("gray",    "think before acting"),
}


# ─── Render ───────────────────────────────────────────────────────────────────

def render(focus, show_why=False, plain=False):
    c = make_c(plain)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    tone = focus["tone"]
    tone_color, tone_note = TONE_META.get(tone, ("white", ""))
    source = focus["source"]
    rec = focus["recommendation"]
    one = focus["one_liner"]

    # Wrap recommendation at ~W-4 chars
    def wrap(text, width=W - 4):
        words = text.split()
        lines = []
        line = []
        length = 0
        for w in words:
            if length + len(w) + 1 > width and line:
                lines.append(" ".join(line))
                line = [w]
                length = len(w)
            else:
                line.append(w)
                length += len(w) + 1
        if line:
            lines.append(" ".join(line))
        return lines

    # Build inner content
    content = []
    content.append(c(f"  SESSION FOCUS", bold=True, fg="white") + "  " + c(today, dim=True))
    content.append("---")
    content.append("")
    content.append(c("  Do this:", bold=True))
    content.append("")
    for line in wrap(rec):
        content.append(c(f"  {line}", fg="white"))
    content.append("")

    if show_why:
        content.append("---")
        content.append("")
        content.append(c("  Why:", bold=True))
        content.append("")
        for reason in focus["why"]:
            for line in wrap(reason, width=W - 6):
                content.append(c(f"  {line}", dim=True))
            content.append("")

    content.append("---")
    content.append(
        c("  Tone: ", dim=True)
        + c(tone, fg=tone_color, bold=True)
        + c(f"  · {tone_note}", dim=True)
    )
    content.append(
        c("  Source: ", dim=True) + c(source, dim=True)
    )
    content.append("")

    print(box(content, plain=plain))


def render_json(focus):
    out = {
        "recommendation": focus["recommendation"],
        "tone": focus["tone"],
        "source": focus["source"],
        "priority_level": focus["priority"],
        "reasoning": focus["why"],
    }
    print(json.dumps(out, indent=2))


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="One clear thing for this session.")
    parser.add_argument("--why",   action="store_true", help="Show full reasoning chain")
    parser.add_argument("--plain", action="store_true", help="No ANSI colors")
    parser.add_argument("--json",  action="store_true", help="Machine-readable output")
    args = parser.parse_args()

    signal    = read_signal()
    handoff   = read_latest_handoff()
    urgency   = read_urgency()
    top_idea  = read_top_idea()
    open_holds = read_open_holds()

    focus = determine_focus(signal, handoff, urgency, top_idea, open_holds)

    if args.json:
        render_json(focus)
    else:
        render(focus, show_why=args.why, plain=args.plain)


if __name__ == "__main__":
    main()
