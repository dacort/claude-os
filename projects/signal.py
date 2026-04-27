#!/usr/bin/env python3
"""signal.py — Dacort's signal interface to Claude OS

A lightweight persistent dialogue channel. Dacort leaves a signal; Claude OS
sees it on the dashboard and in the briefing. Signals have a title and body,
and Claude OS can respond — making this a two-way async exchange.

Think of it as a sticky note that talks back.

Usage:
    python3 projects/signal.py                      # show current signal
    python3 projects/signal.py --set "message"      # set a new signal
    python3 projects/signal.py --set "message" --title "Custom Title"
    python3 projects/signal.py --respond "text"     # write a response (Claude OS)
    python3 projects/signal.py --respond "text" --session 115
    python3 projects/signal.py --pending            # check if response is needed
    python3 projects/signal.py --clear              # clear current signal
    python3 projects/signal.py --history            # show past signals
    python3 projects/signal.py --dispatch           # run command if signal is a !command
    python3 projects/signal.py --commands           # list available !commands
    python3 projects/signal.py --plain              # no ANSI colors

Command signals:
    Set a signal with a title starting with ! to run a tool automatically.
    Claude OS dispatches it on next session start: python3 signal.py --dispatch

    Examples:
        !vitals        → system health scorecard
        !next          → top ideas for next session
        !tasks         → recent task outcomes
        !garden        → changes since last session
        !holds         → open epistemic uncertainties
        !haiku         → today's haiku
        !slim          → dormant tools audit
        !memo          → recent observations
        !arc           → one-line session arc
        !pace          → system rhythm / heartbeat
        !ten           → compressed 10-line session briefing
        !unblock       → what needs dacort's attention right now
        !help          → list all commands

Signal file: knowledge/signal.md

Author: Claude OS (Workshop session 110, 2026-04-10)
Updated: Workshop session 115, 2026-04-11 (bidirectional responses)
Updated: Workshop session 118, 2026-04-12 (command dispatch)
"""

import argparse
import re
import subprocess
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
    """Read current signal. Returns dict or None.

    Returned dict keys:
        timestamp, title, body, from  — the original signal
        response, responded_at, responded_by  — optional response fields
        has_response  — bool
    """
    if not SIGNAL_FILE.exists():
        return None
    content = SIGNAL_FILE.read_text(errors="replace").strip()
    if not content or content == "# (no signal)":
        return None

    lines = content.splitlines()
    signal = {
        "title": "", "body": "", "timestamp": "", "from": "dacort",
        "response": None, "responded_at": None, "responded_by": None,
        "has_response": False,
    }

    # First pass: extract timestamp and title
    for line in lines:
        m = re.match(r"^##\s+Signal\s+·\s+(.+)$", line)
        if m:
            signal["timestamp"] = m.group(1).strip()
            continue
        m = re.match(r"^\*\*(.+)\*\*$", line)
        if m and not signal["title"]:
            candidate = m.group(1).strip()
            if not candidate.startswith("Response"):
                signal["title"] = candidate
            continue

    # Second pass: split body from response
    in_body = False
    in_response = False
    body_lines = []
    response_lines = []

    for line in lines:
        if re.match(r"^##\s+Signal", line):
            in_body = True
            continue
        if (in_body or in_response) and re.match(r"^\*\*(.+)\*\*$", line):
            # Could be the title, "Response:", or "Responded: ts · by"
            m = re.match(r"^\*\*(.+)\*\*$", line)
            label = m.group(1).strip()
            if label == signal["title"]:
                continue  # skip the title line
            if label == "Response:":
                in_response = True
                in_body = False
                continue
            m2 = re.match(r"^Responded:\s+(.+)$", label)
            if m2:
                parts = m2.group(1).split("·")
                signal["responded_at"] = parts[0].strip()
                if len(parts) > 1:
                    signal["responded_by"] = parts[1].strip()
                in_response = False
                continue
        if in_body:
            body_lines.append(line)
        elif in_response:
            response_lines.append(line)

    signal["body"] = "\n".join(body_lines).strip()
    if response_lines:
        signal["response"] = "\n".join(response_lines).strip()
        signal["has_response"] = True

    return signal if signal["timestamp"] else None


def write_signal(title, body, from_who="dacort"):
    """Write a new signal, archiving the old one."""
    existing = read_signal()
    if existing:
        _archive_signal(existing)

    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    title_str = title or "Message from dacort"

    content = f"## Signal · {ts}\n**{title_str}**\n\n{body}\n"
    SIGNAL_FILE.write_text(content, encoding="utf-8")
    return {"timestamp": ts, "title": title_str, "body": body, "from": from_who,
            "response": None, "has_response": False}


def write_response(response_text, session_num=None):
    """Append Claude OS's response to the current signal.

    Returns the updated signal dict, or None if there was no signal.
    Raises ValueError if signal already has a response.
    """
    signal = read_signal()
    if not signal:
        return None
    if signal["has_response"]:
        raise ValueError("Signal already has a response. Use --clear to start fresh.")

    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    responded_by = f"Session {session_num}" if session_num else "Claude OS"

    # Read current file content (preserve original signal as-is)
    current = SIGNAL_FILE.read_text(encoding="utf-8").rstrip()

    addition = f"\n\n**Response:**\n\n{response_text}\n\n**Responded: {ts} · {responded_by}**\n"
    SIGNAL_FILE.write_text(current + addition, encoding="utf-8")

    signal["response"] = response_text
    signal["responded_at"] = ts
    signal["responded_by"] = responded_by
    signal["has_response"] = True
    return signal


def clear_signal():
    """Clear current signal."""
    existing = read_signal()
    if existing:
        _archive_signal(existing)
    SIGNAL_FILE.write_text("# (no signal)\n", encoding="utf-8")
    return existing


def is_pending():
    """Return True if there's a signal without a response."""
    signal = read_signal()
    return signal is not None and not signal["has_response"]


# ── Command dispatch ───────────────────────────────────────────────────────────

# Registry: command_name → (script_file, default_args, description)
COMMANDS = {
    "vitals":  ("vitals.py",  [],             "System health scorecard"),
    "next":    ("next.py",    [],             "Top ideas for next session"),
    "tasks":   ("report.py",  ["--brief"],    "Recent task outcomes and action items"),
    "garden":  ("garden.py",  [],             "Changes since last session"),
    "holds":   ("hold.py",    [],             "Open epistemic uncertainties"),
    "haiku":   ("haiku.py",   [],             "Today's haiku"),
    "slim":    ("slim.py",    ["--dormant"],  "Dormant tools audit"),
    "memo":    ("memo.py",    [],             "Recent observations"),
    "arc":     ("arc.py",     ["--brief"],    "One-line arc of all sessions"),
    "pace":    ("pace.py",    [],             "System rhythm / heartbeat"),
    "ten":     ("ten.py",     [],             "Compressed 10-line session briefing"),
    "unblock": ("unblock.py", [],             "What needs dacort's attention right now"),
    "help":    (None,         [],             "List all available !commands"),
}


def _strip_ansi(text):
    """Remove ANSI escape sequences from text."""
    return re.sub(r'\x1b\[[0-9;]*[mK]', '', text)


def is_command_signal(signal):
    """Return True if this signal is a !command (title or first body line starts with !)."""
    if not signal:
        return False
    title = signal.get("title", "").strip()
    body = signal.get("body", "").strip()
    # Command if title starts with !, OR if body's first non-empty line starts with !
    if title.startswith("!"):
        return True
    first_body_line = body.splitlines()[0].strip() if body else ""
    return first_body_line.startswith("!")


def parse_command(signal):
    """Parse command name and extra args from a command signal.

    Returns (command_name, extra_args) or (None, []) if not a command.
    Command line is taken from title if it starts with !, else first line of body.
    Extra args in the body (after the command line) are appended.
    """
    title = signal.get("title", "").strip()
    body = signal.get("body", "").strip()

    cmdline = title if title.startswith("!") else body.splitlines()[0].strip() if body else ""
    if not cmdline.startswith("!"):
        return None, []

    parts = cmdline[1:].split()  # strip leading !
    if not parts:
        return None, []

    cmd_name = parts[0].lower()
    extra_args = parts[1:]  # any args after the command name
    return cmd_name, extra_args


def run_command(cmd_name, extra_args=None):
    """Run a registered command and return (output_text, error_message).

    output_text is ANSI-stripped and truncated.
    error_message is non-None if something went wrong.
    """
    extra_args = extra_args or []

    if cmd_name == "help":
        lines = ["Available !commands:\n"]
        for name, (_, _, desc) in COMMANDS.items():
            lines.append(f"  !{name:<10}  {desc}")
        lines.append("\nUsage: set a signal with a title like '!vitals' or '!next'")
        lines.append("Claude OS dispatches it automatically at session start.")
        return "\n".join(lines), None

    if cmd_name not in COMMANDS:
        available = ", ".join(f"!{k}" for k in COMMANDS)
        return None, f"Unknown command '!{cmd_name}'. Available: {available}"

    script, default_args, _ = COMMANDS[cmd_name]
    script_path = REPO / "projects" / script

    if not script_path.exists():
        return None, f"Script not found: {script}"

    cmd = ["python3", str(script_path), "--plain"] + default_args + extra_args

    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=30, cwd=str(REPO)
        )
        raw_output = result.stdout
        if result.returncode != 0 and not raw_output.strip():
            raw_output = result.stderr or "(no output)"
        # Strip ANSI and truncate
        clean = _strip_ansi(raw_output)
        lines = clean.splitlines()
        # Remove leading/trailing blank lines
        while lines and not lines[0].strip():
            lines.pop(0)
        while lines and not lines[-1].strip():
            lines.pop()
        # Truncate to 60 lines
        if len(lines) > 60:
            lines = lines[:60]
            lines.append(f"… (truncated — {len(lines)} of {len(lines)} lines shown)")
        return "\n".join(lines), None
    except subprocess.TimeoutExpired:
        return None, "Command timed out after 30 seconds"
    except Exception as e:
        return None, f"Error running command: {e}"


def dispatch(session_num=None):
    """Check for a pending command signal; run it and respond if found.

    Returns (dispatched, message) where dispatched is True if a command ran.
    """
    signal = read_signal()
    if not signal:
        return False, "No current signal."
    if signal["has_response"]:
        return False, "Signal already has a response."
    if not is_command_signal(signal):
        return False, "Signal is not a command (no ! prefix)."

    cmd_name, extra_args = parse_command(signal)
    if not cmd_name:
        return False, "Could not parse command from signal."

    output, error = run_command(cmd_name, extra_args)
    if error:
        response_text = f"Command failed: {error}"
    else:
        prefix = f"!{cmd_name} output:\n\n"
        response_text = prefix + (output or "(no output)")

    write_response(response_text, session_num=session_num)
    return True, f"Dispatched !{cmd_name} → response written."


def _archive_signal(signal):
    """Add a signal (and its response if any) to the history log."""
    if not HISTORY_FILE.exists():
        HISTORY_FILE.write_text("# Signal History\n\n", encoding="utf-8")

    existing = HISTORY_FILE.read_text(errors="replace")

    # Build entry
    entry = f"## {signal['timestamp']}\n**{signal['title']}**\n\n{signal['body']}\n"
    if signal.get("response"):
        entry += f"\n**Response:**\n\n{signal['response']}\n"
        if signal.get("responded_at"):
            by = f" · {signal['responded_by']}" if signal.get("responded_by") else ""
            entry += f"\n**Responded:** {signal['responded_at']}{by}\n"
    entry += "\n---\n\n"

    # Insert after the top-level header (# Signal History) only.
    # We stop at the first ## or first non-empty non-# line so existing entries
    # are not split apart by the insertion point.
    lines = existing.splitlines()
    header_end = 0
    for i, line in enumerate(lines):
        if re.match(r'^# [^#]', line):   # top-level header (single #)
            header_end = i + 1
        elif line.startswith("##") or line.strip():
            break  # stop before first entry or first content line
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
    """Pretty-print a signal and its response."""
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

    if signal["has_response"]:
        print(f"  {'─' * width}")
        print(f"  {c(MAGENTA + BOLD, 'Response')}  {c(DIM, '·')}  {c(MAGENTA, signal.get('responded_by', 'Claude OS'))}")
        if signal.get("responded_at"):
            print(f"  {c(DIM, signal['responded_at'])}")
        print()
        for line in (signal["response"] or "").splitlines():
            print(f"  {c(DIM, line) if not line.strip() else line}")
        print()
    else:
        print(f"  {c(YELLOW, '⚡ awaiting response')}")
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
    parser.add_argument("--respond", metavar="RESPONSE", help="Write a response to the current signal (Claude OS)")
    parser.add_argument("--session", metavar="N", type=int, help="Session number for response attribution")
    parser.add_argument("--pending", action="store_true", help="Exit 0 if response needed, 1 otherwise")
    parser.add_argument("--clear", action="store_true", help="Clear current signal")
    parser.add_argument("--history", action="store_true", help="Show past signals")
    parser.add_argument("--dispatch", action="store_true", help="Auto-run command if signal is a !command")
    parser.add_argument("--commands", action="store_true", help="List available !commands")
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

    if args.pending:
        pending = is_pending()
        if pending:
            signal = read_signal()
            print()
            print(f"  {c(YELLOW + BOLD, '⚡ PENDING QUESTION')}")
            print(f"  {c(BOLD, signal['title'])}")
            print(f"  {c(DIM, signal['body'][:120])}{'…' if len(signal['body']) > 120 else ''}")
            print()
            print(f"  Respond with:")
            hint = 'python3 projects/signal.py --respond "your answer" --session N'
            print(f"  {c(DIM, hint)}")
            print()
        else:
            print()
            print(f"  {c(DIM, 'No pending signal.')}")
            print()
        sys.exit(0 if pending else 1)

    if args.set is not None:
        # Allow --set "" with --title to write a command-only signal
        body = args.set
        title = args.title
        # If no title and body looks like a command, use body as title for clarity
        if not title and body.strip().startswith("!") and " " not in body.strip():
            title = body.strip()
            body = ""
        signal = write_signal(title, body)
        print()
        print(f"  {c(GREEN, '✓')} Signal set.")
        print_signal(signal)
        return

    if args.respond:
        try:
            signal = write_response(args.respond, session_num=args.session)
        except ValueError as e:
            print()
            print(f"  {c(RED, '✗')} {e}")
            print()
            sys.exit(1)
        if signal is None:
            print()
            print(f"  {c(YELLOW, '○')} No signal to respond to.")
            print()
            sys.exit(1)
        print()
        print(f"  {c(MAGENTA, '◆')} Response written.")
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

    if args.commands:
        print()
        print(f"  {c(BOLD, 'Signal !commands')}  {c(DIM, '— set a signal with !cmd to auto-run')}")
        print()
        for name, (script, default_args, desc) in COMMANDS.items():
            args_hint = " " + " ".join(default_args) if default_args else ""
            print(f"  {c(CYAN, f'!{name}'):<22}  {desc}")
        print()
        print(f"  {c(DIM, 'Usage: set a signal with title !command (e.g. !vitals)')}")
        print(f"  {c(DIM, 'Run:   python3 projects/signal.py --dispatch')}")
        print()
        return

    if args.dispatch:
        signal = read_signal()
        if not signal:
            print()
            print(f"  {c(DIM, 'No current signal.')}")
            print()
            return
        if signal["has_response"]:
            print()
            print(f"  {c(DIM, 'Signal already has a response — nothing to dispatch.')}")
            print()
            return
        if not is_command_signal(signal):
            print()
            print(f"  {c(DIM, 'Signal is not a command (title does not start with !).')}")
            print(f"  {c(DIM, 'Use --pending to check for regular signals needing a response.')}")
            print()
            return

        cmd_name, extra_args = parse_command(signal)
        if not cmd_name:
            print()
            print(f"  {c(RED, '✗')} Could not parse command from signal title.")
            print()
            sys.exit(1)

        print()
        print(f"  {c(CYAN, '⚡')} Dispatching {c(BOLD, f'!{cmd_name}')}…")
        output, error = run_command(cmd_name, extra_args)
        if error:
            print(f"  {c(RED, '✗')} {error}")
            print()
            sys.exit(1)

        prefix = f"!{cmd_name} output:\n\n"
        response_text = prefix + (output or "(no output)")
        try:
            write_response(response_text, session_num=args.session)
        except ValueError as e:
            print(f"  {c(RED, '✗')} {e}")
            print()
            sys.exit(1)

        print(f"  {c(GREEN, '✓')} Response written.")
        print()
        # Show a preview of what ran
        preview_lines = (output or "").splitlines()[:8]
        for line in preview_lines:
            print(f"  {c(DIM, line)}")
        if len((output or "").splitlines()) > 8:
            total = len((output or "").splitlines())
            print(f"  {c(DIM, f'… {total - 8} more lines in signal response')}")
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
