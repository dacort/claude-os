#!/usr/bin/env python3
"""signal.py — Dacort's signal interface to Claude OS

A lightweight persistent message channel. Dacort leaves a signal; Claude OS
sees it on the dashboard and in the briefing. Signals have a title and body
and persist until replaced or cleared.

Think of it as a sticky note on the dashboard.

Usage:
    python3 projects/signal.py                   # show current signal
    python3 projects/signal.py --set "message"   # set a new signal
    python3 projects/signal.py --set "message" --title "Custom Title"
    python3 projects/signal.py --clear           # clear current signal
    python3 projects/signal.py --history         # show signal history
    python3 projects/signal.py --plain           # no ANSI colors

Signal file: knowledge/signal.md

Author: Claude OS (Workshop session 110, 2026-04-10)
"""

import argparse
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).parent.parent
SIGNAL_FILE = REPO / "knowledge" / "signal.md"
HISTORY_FILE = REPO / "knowledge" / "signal-history.md"

# ── Color helpers ──────────────────────────────────────────────────────────────

RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
CYAN = "\033[36m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
MAGENTA = "\033[35m"
RED = "\033[31m"
WHITE = "\033[97m"
GRAY = "\033[90m"

USE_COLOR = True


def c(code, text):
    return f"{code}{text}{RESET}" if USE_COLOR else text


# ── Signal data model ──────────────────────────────────────────────────────────

def read_signal():
    """Read current signal. Returns dict or None."""
    if not SIGNAL_FILE.exists():
        return None
    content = SIGNAL_FILE.read_text(errors="replace").strip()
    if not content or content == "# (no signal)":
        return None

    # Parse signal file format:
    # ## Signal · YYYY-MM-DD HH:MM UTC
    # **Title**
    #
    # Body text...
    lines = content.splitlines()
    signal = {"title": "", "body": "", "timestamp": "", "from": "dacort"}

    for i, line in enumerate(lines):
        m = re.match(r"^##\s+Signal\s+·\s+(.+)$", line)
        if m:
            signal["timestamp"] = m.group(1).strip()
            continue
        m = re.match(r"^\*\*(.+)\*\*$", line)
        if m and not signal["title"]:
            signal["title"] = m.group(1).strip()
            continue
        # Body: everything after the title line that isn't empty at start
    # Collect body
    body_lines = []
    past_header = False
    for line in lines:
        if re.match(r"^##\s+Signal", line):
            past_header = True
            continue
        if past_header and re.match(r"^\*\*.+\*\*$", line):
            continue
        if past_header:
            body_lines.append(line)
    # Strip leading/trailing blank lines
    body = "\n".join(body_lines).strip()
    signal["body"] = body

    return signal if signal["timestamp"] else None


def write_signal(title, body, from_who="dacort"):
    """Write a new signal, archiving the old one."""
    # Archive existing signal
    existing = read_signal()
    if existing:
        _archive_signal(existing)

    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    title_str = title or "Message from dacort"

    content = f"""## Signal · {ts}
**{title_str}**

{body}
"""
    SIGNAL_FILE.write_text(content, encoding="utf-8")
    return {"timestamp": ts, "title": title_str, "body": body, "from": from_who}


def clear_signal():
    """Clear current signal."""
    existing = read_signal()
    if existing:
        _archive_signal(existing)
    SIGNAL_FILE.write_text("# (no signal)\n", encoding="utf-8")
    return existing  # return what was cleared


def _archive_signal(signal):
    """Add a signal to the history log."""
    if not HISTORY_FILE.exists():
        HISTORY_FILE.write_text("# Signal History\n\n", encoding="utf-8")

    existing = HISTORY_FILE.read_text(errors="replace")
    entry = f"""## {signal['timestamp']}
**{signal['title']}**

{signal['body']}

---

"""
    # Insert after the header
    lines = existing.splitlines()
    header_end = 0
    for i, line in enumerate(lines):
        if line.startswith("#"):
            header_end = i + 1
        elif line.strip():
            break
    insert_at = "\n".join(lines[:header_end]) + "\n\n" + entry + "\n".join(lines[header_end:])
    HISTORY_FILE.write_text(insert_at, encoding="utf-8")


def read_history(n=5):
    """Read last N signals from history."""
    if not HISTORY_FILE.exists():
        return []

    content = HISTORY_FILE.read_text(errors="replace")
    signals = []
    current = None
    body_lines = []

    for line in content.splitlines():
        m = re.match(r"^## (\d{4}-\d{2}-\d{2}.+)$", line)
        if m:
            if current:
                current["body"] = "\n".join(body_lines).strip()
                signals.append(current)
            current = {"timestamp": m.group(1), "title": "", "body": ""}
            body_lines = []
            continue
        if current:
            m2 = re.match(r"^\*\*(.+)\*\*$", line)
            if m2 and not current["title"]:
                current["title"] = m2.group(1)
                continue
            if line.strip() != "---":
                body_lines.append(line)

    if current:
        current["body"] = "\n".join(body_lines).strip()
        signals.append(current)

    return signals[-n:]


# ── Display ────────────────────────────────────────────────────────────────────

def print_signal(signal):
    """Pretty-print a signal."""
    width = 62

    print()
    print(f"  {'─' * width}")
    print(f"  {c(CYAN + BOLD, 'Signal')}  {c(DIM, '·')}  {c(YELLOW, signal['from'])}  {c(DIM, '→')}  {c(CYAN, 'Claude OS')}")
    print(f"  {c(DIM, signal['timestamp'])}")
    print(f"  {'─' * width}")
    print()
    if signal["title"]:
        print(f"  {c(BOLD + WHITE, signal['title'])}")
        print()
    for line in signal["body"].splitlines():
        print(f"  {c(DIM, line) if not line.strip() else line}")
    print()
    print(f"  {'─' * width}")
    print()


def print_no_signal():
    print()
    print(f"  {c(DIM, 'No current signal.')}")
    hint = 'Set one with: python3 projects/signal.py --set "your message"'
    print(f"  {c(DIM, hint)}")
    print()


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    global USE_COLOR

    parser = argparse.ArgumentParser(
        description="Dacort's signal interface to Claude OS",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--set", metavar="MESSAGE", help="Set a new signal")
    parser.add_argument("--title", "-t", metavar="TITLE", help="Signal title (use with --set)")
    parser.add_argument("--clear", action="store_true", help="Clear current signal")
    parser.add_argument("--history", action="store_true", help="Show past signals")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--plain", action="store_true", help="No ANSI colors")
    args = parser.parse_args()

    if args.plain:
        USE_COLOR = False

    if args.json:
        import json
        if args.history:
            data = {"history": read_history(10)}
        else:
            data = read_signal() or {}
        print(json.dumps(data, indent=2, default=str))
        return

    if args.set:
        signal = write_signal(args.title, args.set)
        print()
        print(f"  {c(GREEN, '✓')} Signal set.")
        print_signal(signal)
        return

    if args.clear:
        cleared = clear_signal()
        if cleared:
            print()
            print(f"  {c(YELLOW, '○')} Signal cleared.")
            print()
        else:
            print()
            print(f"  {c(DIM, 'No signal to clear.')}")
            print()
        return

    if args.history:
        history = read_history(10)
        if not history:
            print()
            print(f"  {c(DIM, 'No signal history.')}")
            print()
            return
        print()
        print(f"  {c(BOLD, 'Signal History')}  {c(DIM, f'— {len(history)} entries')}")
        for s in reversed(history):
            print()
            print(f"  {c(CYAN, s['timestamp'])}  {c(BOLD, s['title'])}")
            for line in s["body"].splitlines()[:3]:
                if line.strip():
                    print(f"  {c(DIM, line[:80])}")
        print()
        return

    # Default: show current signal
    signal = read_signal()
    if signal:
        print_signal(signal)
    else:
        print_no_signal()


if __name__ == "__main__":
    main()
