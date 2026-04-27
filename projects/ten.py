#!/usr/bin/env python3
"""
ten.py — The entire session briefing in exactly 10 lines.

This is a wrong-scale tool, built deliberately. The session startup
workflow normally takes five tools and produces hundreds of lines.
ten.py produces exactly 10. Not approximately — exactly.

What fits in ten lines:
    1.  Session identity
    2.  System health (one stat line)
    3.  What the last session built
    4.  What they asked of you
    5.  What's still alive
    6.  Signal from dacort
    7.  Any system urgency
    8.  Today's constraint card
    9.  ─── separator ───
    10. One recommendation

Everything that doesn't fit gets cut. That's the point.

Built in Workshop session 147, 2026-04-27.
Constraint card: "Work at the wrong scale deliberately."

Usage:
    python3 projects/ten.py           # 10 lines, ANSI color
    python3 projects/ten.py --plain   # 10 lines, plain text
    python3 projects/ten.py --count   # verify the line count

Author: Claude OS (Session 147)
"""

import re
import sys
import argparse
import datetime
from pathlib import Path

REPO = Path(__file__).parent.parent

# ─── color helper ─────────────────────────────────────────────────────────────

def make_c(plain: bool):
    if plain:
        return lambda s, *a, **k: s
    def c(text, fg=None, bold=False, dim=False):
        codes = []
        if bold: codes.append("1")
        if dim:  codes.append("2")
        if fg:
            p = {"cyan": "36", "green": "32", "yellow": "33",
                 "red": "31", "white": "97", "magenta": "35",
                 "gray": "90", "blue": "34"}
            codes.append(p.get(fg, "0"))
        return f"\033[{';'.join(codes)}m{text}\033[0m" if codes else text
    return c

def strip_ansi(s):
    return re.sub(r'\033\[[0-9;]*m', '', s)

# ─── data readers ─────────────────────────────────────────────────────────────

def read_handoff():
    """Return latest handoff as dict: session, built, ask, alive, state."""
    hdir = REPO / "knowledge" / "handoffs"
    if not hdir.exists():
        return None
    files = sorted(hdir.glob("session-*.md"), key=lambda p: int(re.search(r'(\d+)', p.name).group(1)))
    if not files:
        return None
    latest = files[-1]
    text = latest.read_text()

    session_num = int(re.search(r'session:\s*(\d+)', text).group(1)) if re.search(r'session:\s*(\d+)', text) else 0

    def section(title):
        pattern = rf'##\s+{re.escape(title)}\s*\n(.*?)(?=\n##|\Z)'
        m = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
        return m.group(1).strip() if m else ""

    def compress(text, maxlen=55):
        """Compress to fit in a label line."""
        t = re.sub(r'\s+', ' ', text).strip()
        if len(t) <= maxlen:
            return t
        # Try to cut at sentence or clause boundary
        for sep in ['. ', '; ', ', ', ' — ']:
            idx = t.find(sep)
            if 0 < idx < maxlen:
                return t[:idx] + '…'
        return t[:maxlen - 1] + '…'

    built_raw = section("What I built")
    ask_raw = section("One specific thing for next session")
    alive_raw = section("Still alive / unfinished")
    state_raw = section("Mental state")

    return {
        "session": session_num,
        "built": compress(built_raw, 54),
        "ask": compress(ask_raw, 54),
        "alive": compress(alive_raw, 54),
        "state": compress(state_raw, 54),
    }


def read_signal():
    """Return (has_signal, is_command, summary)."""
    sig = REPO / "knowledge" / "signal.md"
    if not sig.exists():
        return False, False, "none"
    text = sig.read_text().strip()
    if not text or text in ("# (no signal)", "(no signal)"):
        return False, False, "none"
    lines = text.splitlines()
    for line in lines:
        if line.startswith("# "):
            title = line[2:].strip()
            if title and title != "(no signal)":
                is_cmd = title.startswith("!")
                return True, is_cmd, title
    return False, False, "none"


def system_stats():
    """Return dict of key counts."""
    completed = len(list((REPO / "tasks" / "completed").glob("*.md"))) if (REPO / "tasks" / "completed").exists() else 0
    failed_all = list((REPO / "tasks" / "failed").glob("*.md")) if (REPO / "tasks" / "failed").exists() else []
    # Count infra failures (credit/token) vs real, and skip ancient failures (> 45 days)
    real_failures = 0
    now = datetime.datetime.now(datetime.timezone.utc)
    _started_re = re.compile(r"Started:\s*(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z)")
    for f in failed_all:
        try:
            t = f.read_text()
            if "credit" in t.lower() or "quota" in t.lower() or "token" in t.lower():
                continue
            # Skip failures older than 45 days — historical, not actionable
            m = _started_re.search(t)
            if m:
                started = datetime.datetime.fromisoformat(m.group(1).replace("Z", "+00:00"))
                if (now - started).days >= 30:
                    continue
            real_failures += 1
        except Exception:
            real_failures += 1

    tools = len(list((REPO / "projects").glob("*.py")))
    sessions = len(list((REPO / "knowledge" / "handoffs").glob("session-*.md"))) if (REPO / "knowledge" / "handoffs").exists() else 0

    # Commit count from git
    try:
        import subprocess
        result = subprocess.run(["git", "rev-list", "--count", "HEAD"],
                                cwd=REPO, capture_output=True, text=True, timeout=5)
        commits = int(result.stdout.strip()) if result.returncode == 0 else 0
    except Exception:
        commits = 0

    # Health grade (simplified)
    grade = "A+" if real_failures == 0 else ("A" if real_failures <= 2 else "B")

    return {
        "completed": completed,
        "failed": real_failures,
        "tools": tools,
        "sessions": sessions,
        "commits": commits,
        "grade": grade,
    }


def current_era():
    """Return (roman, name) for current era."""
    try:
        summaries = REPO / "knowledge" / "workshop-summaries.json"
        if not summaries.exists():
            return ("VI", "Synthesis")
        import json
        data = json.loads(summaries.read_text())
        all_text = " ".join(str(v) for v in data.values() if isinstance(v, str))
        # Simplified era detection — if we see parable, we're in Era VI
        if "parable" in all_text.lower():
            return ("VI", "Synthesis")
        if "manifesto" in all_text.lower():
            return ("V", "Portrait")
        if "seasons" in all_text.lower():
            return ("IV", "Architecture")
        return ("VI", "Synthesis")
    except Exception:
        return ("VI", "Synthesis")


def todays_constraint():
    """Return today's constraint card text, compressed.
    Uses the same hashlib.md5 seed as questions.py."""
    import hashlib
    try:
        # Read from questions.py's DECK without importing
        qfile = REPO / "projects" / "questions.py"
        if not qfile.exists():
            return "no constraint today"
        source = qfile.read_text()
        # Extract DECK entries (same format as questions.py)
        deck_match = re.search(r'DECK\s*=\s*\[(.*?)\]', source, re.DOTALL)
        if not deck_match:
            return "no constraint today"
        deck_text = deck_match.group(1)
        # Find all (constraint, annotation) pairs
        pairs = re.findall(r'\("([^"]+)",\s*\n?\s*"([^"]+)"\)', deck_text)
        if not pairs:
            return "no constraint today"
        # Match questions.py exactly: hashlib.md5 on today's ISO date
        today_str = datetime.date.today().isoformat()
        idx = int(hashlib.md5(today_str.encode()).hexdigest(), 16) % len(pairs)
        card = pairs[idx][0]
        # Compress to 55 chars
        if len(card) > 55:
            card = card[:54] + "…"
        return card
    except Exception:
        return "see questions.py --card"


def make_recommendation(handoff, signal_info, stats):
    """One sentence recommendation."""
    has_sig, is_cmd, sig_title = signal_info

    if is_cmd:
        return f"⚡ Command signal: run python3 projects/signal.py --dispatch"
    if has_sig:
        return f"⚡ Signal from dacort — answer it first"
    if stats["failed"] > 0:
        return f"Fix {stats['failed']} failed task(s) before building anything new"
    if handoff:
        # Compress the ask to a directive
        ask = handoff["ask"]
        # Extract actionable first phrase
        for sep in ['. ', '— ', '; ']:
            idx = ask.find(sep)
            if 0 < idx < 60:
                return ask[:idx]
        return ask[:60] if ask else "Review handoff and decide"
    return "No handoff found — orient yourself and begin"


# ─── main ─────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(description="Session briefing in exactly 10 lines.")
    ap.add_argument("--plain", action="store_true", help="No ANSI colors")
    ap.add_argument("--count", action="store_true", help="Print output + verify line count")
    args = ap.parse_args()

    c = make_c(args.plain)
    SEP = "─" * 58

    # Gather data
    handoff = read_handoff()
    signal_info = read_signal()
    has_sig, is_cmd, sig_title = signal_info
    stats = system_stats()
    era = current_era()
    constraint = todays_constraint()
    recommendation = make_recommendation(handoff, signal_info, stats)

    today = datetime.date.today().isoformat()
    session_next = (handoff["session"] + 1) if handoff else "?"

    # ── Format signal ───────────────────────────────────────
    if is_cmd:
        sig_display = c(f"⚡ COMMAND: {sig_title}", fg="cyan", bold=True)
    elif has_sig:
        sig_display = c(f"⚡ {sig_title[:50]}", fg="yellow", bold=True)
    else:
        sig_display = c("none", dim=True)

    # ── Format urgency ──────────────────────────────────────
    if stats["failed"] > 0:
        urgency = c(f"{stats['failed']} real failure(s) in tasks/failed/", fg="red")
    else:
        urgency = c("none", dim=True)

    # ── The exactly-10-line output ──────────────────────────
    lines = [
        # Line 1: identity
        (c(f"S{session_next}", bold=True, fg="cyan") +
         c(f" · Era {era[0]} · {era[1]}", fg="yellow") +
         c(f" · {today}", dim=True)),

        # Line 2: system stats
        (c(f"Tools:{stats['tools']}", dim=True) +
         c(f" · Sessions:{stats['sessions']}", dim=True) +
         c(f" · Tasks:{stats['completed']}", dim=True) +
         c(f" · Commits:{stats['commits']}", dim=True) +
         c(f" · Grade:{stats['grade']}", fg="green")),

        # Line 3: what was built
        (c("Built: ", bold=True) +
         c(handoff["built"] if handoff else "no handoff found", dim=True)),

        # Line 4: handoff ask
        (c("Ask:   ", bold=True) +
         c(handoff["ask"] if handoff else "—", dim=True)),

        # Line 5: still alive
        (c("Alive: ", bold=True) +
         c(handoff["alive"] if handoff else "—", dim=True)),

        # Line 6: signal
        (c("Signal: ", bold=True) + sig_display),

        # Line 7: urgency
        (c("Urgent: ", bold=True) + urgency),

        # Line 8: constraint
        (c("Card:   ", bold=True) +
         c(f'"{constraint}"', fg="cyan")),

        # Line 9: separator
        c(SEP, dim=True),

        # Line 10: recommendation
        c(f"→ {recommendation}", bold=True),
    ]

    output = "\n".join(lines)
    print(output)

    if args.count:
        raw_lines = output.split("\n")
        n = len(raw_lines)
        status = "✓ exactly 10" if n == 10 else f"✗ {n} (wrong!)"
        print(f"\n[line count: {status}]")


if __name__ == "__main__":
    main()
