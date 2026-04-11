#!/usr/bin/env python3
"""now.py — What is happening in this session, right now.

The system has 110+ sessions of retrospective analysis. Field notes are written
at session end. Handoffs speak to the future. Mood.py classifies the past.

This tool does something different: it captures the present. Not what was built,
not what will happen — what is true right now, in this session, at this moment.

Different from:
  handoff.py    — retrospective, written at session end, for the next instance
  field-notes   — discursive essays, written after the work
  mood.py       — classifies sessions in retrospect
  hold.py       — explicit epistemic uncertainty (what the system names as unknown)

This asks: what is the current state, and what does it suggest?

Usage:
    python3 projects/now.py              # show current state
    python3 projects/now.py --write      # also save to knowledge/moments/
    python3 projects/now.py --list       # show past moment captures
    python3 projects/now.py --plain      # no ANSI colors

Directly addresses H007: "what does it feel like to be inside this session
right now?" The answer changes each time you run it.

Author: Claude OS (Workshop session 112, 2026-04-11)
"""

import argparse
import re
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

REPO = Path(__file__).parent.parent

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
BLUE = "\033[34m"
GRAY = "\033[90m"

USE_COLOR = True


def c(text, *codes):
    return ("".join(codes) + str(text) + RESET) if USE_COLOR else str(text)


# ── Data gathering ─────────────────────────────────────────────────────────────

def read_signal():
    """Read current signal from dacort."""
    sig_file = REPO / "knowledge" / "signal.md"
    if not sig_file.exists():
        return None
    content = sig_file.read_text()
    result = {}

    # Parse timestamp
    ts_match = re.search(r"##\s+Signal\s+·\s+(\d{4}-\d{2}-\d{2}T?\d*:?\d*:?\d*\s*UTC)", content)
    if not ts_match:
        ts_match = re.search(r"##\s+Signal\s+·\s+(.+)", content)
    if ts_match:
        result["timestamp_raw"] = ts_match.group(1).strip()
        # Parse date
        date_m = re.search(r"(\d{4}-\d{2}-\d{2})", ts_match.group(1))
        if date_m:
            try:
                result["date"] = datetime.strptime(date_m.group(1), "%Y-%m-%d").replace(tzinfo=timezone.utc)
            except ValueError:
                pass

    # Parse title (bold line after timestamp)
    title_m = re.search(r"\*\*(.+?)\*\*", content)
    if title_m:
        result["title"] = title_m.group(1)

    # Parse body
    lines = content.strip().split("\n")
    body_lines = []
    in_body = False
    for line in lines:
        if in_body and line.strip():
            body_lines.append(line.strip())
        if line.startswith("**") and title_m and title_m.group(1) in line:
            in_body = True
    result["body"] = " ".join(body_lines[:3]) if body_lines else ""
    result["title"] = result.get("title", "(no title)")

    return result


def read_handoff():
    """Read the most recent handoff note."""
    handoffs_dir = REPO / "knowledge" / "handoffs"
    if not handoffs_dir.exists():
        return None

    def session_num(p):
        m = re.match(r"session-(\d+)\.md", p.name)
        return int(m.group(1)) if m else 0

    files = sorted(handoffs_dir.glob("session-*.md"), key=session_num)
    if not files:
        return None

    latest = files[-1]
    content = latest.read_text()

    result = {}

    # Session number
    m = re.match(r"session-(\d+)\.md", latest.name)
    if m:
        result["session"] = int(m.group(1))

    # Mental state
    ms = re.search(r"##\s+Mental state\s*\n+(.+?)(?=##|\Z)", content, re.DOTALL)
    if ms:
        result["mental_state"] = ms.group(1).strip().split("\n")[0]

    # What was built
    built = re.search(r"##\s+What I built\s*\n+(.+?)(?=##|\Z)", content, re.DOTALL)
    if built:
        first_line = built.group(1).strip().split("\n")[0]
        result["built"] = first_line[:120]

    # One specific thing for next session
    ask = re.search(r"##\s+One specific thing.*?\n+(.+?)(?=##|\Z)", content, re.DOTALL)
    if ask:
        text = ask.group(1).strip().split("\n")[0]
        # Truncate at word boundary if needed
        if len(text) > 250:
            text = text[:250].rsplit(" ", 1)[0] + "…"
        result["ask"] = text

    return result


def read_holds():
    """Read open holds."""
    holds_file = REPO / "knowledge" / "holds.md"
    if not holds_file.exists():
        return []

    content = holds_file.read_text()
    holds = []

    # Find each hold
    blocks = re.split(r"^## (H\d+)", content, flags=re.MULTILINE)
    i = 1
    while i < len(blocks) - 1:
        hold_id = blocks[i]
        hold_content = blocks[i + 1]
        i += 2

        # Check if open
        header_line = hold_content.split("\n")[0]
        if "open" in header_line and "resolved" not in header_line:
            # Get the question (first non-empty line after header)
            lines = [l.strip() for l in hold_content.split("\n") if l.strip()]
            question = lines[1] if len(lines) > 1 else ""
            holds.append({"id": hold_id, "question": question[:200]})

    return holds


def count_dormant_tools():
    """Quick count of dormant tools (never or rarely cited)."""
    # Parse slim.py's dormant list from the file
    # Simple approach: count tools in projects/ and check citations in field notes
    tools = list((REPO / "projects").glob("*.py"))
    notes_dir = REPO / "knowledge" / "field-notes"
    handoffs_dir = REPO / "knowledge" / "handoffs"

    # Count citations in all text files
    citation_counts = {}
    text_sources = []
    if notes_dir.exists():
        text_sources.extend(notes_dir.glob("*.md"))
    if handoffs_dir.exists():
        text_sources.extend(handoffs_dir.glob("*.md"))

    for t in tools:
        name = t.stem
        if name.startswith("_"):
            continue
        citation_counts[name] = 0

    for src in text_sources:
        try:
            content = src.read_text()
            for name in citation_counts:
                # Count mentions of the tool name
                if re.search(r'\b' + re.escape(name) + r'\b', content):
                    citation_counts[name] += 1
        except (OSError, UnicodeDecodeError):
            pass

    dormant = [name for name, count in citation_counts.items() if count <= 2]
    return len(dormant), len(tools)


def get_system_stats():
    """Get basic system stats."""
    stats = {}

    # Session count (from handoffs — numeric sort)
    handoffs = list((REPO / "knowledge" / "handoffs").glob("session-*.md"))
    nums = []
    for h in handoffs:
        m = re.match(r"session-(\d+)\.md", h.name)
        if m:
            nums.append(int(m.group(1)))
    stats["sessions"] = max(nums) if nums else 0

    # Tasks
    stats["completed"] = len(list((REPO / "tasks" / "completed").glob("*.md")))
    stats["pending"] = len(list((REPO / "tasks" / "pending").glob("*.md")))
    stats["failed"] = len(list((REPO / "tasks" / "failed").glob("*.md")))

    # Tools
    stats["tools"] = len([p for p in (REPO / "projects").glob("*.py")
                           if not p.stem.startswith("_")])

    return stats


def get_recent_activity():
    """Get recent git commits."""
    import subprocess
    try:
        result = subprocess.run(
            ["git", "log", "--oneline", "--since=48 hours ago", "--no-walk=unsorted"],
            cwd=REPO,
            capture_output=True, text=True
        )
        lines = [l.strip() for l in result.stdout.strip().split("\n") if l.strip()]

        # Get recent commits regardless of time
        result2 = subprocess.run(
            ["git", "log", "--oneline", "-10"],
            cwd=REPO,
            capture_output=True, text=True
        )
        recent = [l.strip() for l in result2.stdout.strip().split("\n") if l.strip()]
        return {"last_48h": lines, "recent": recent}
    except Exception:
        return {"last_48h": [], "recent": []}


def get_still_alive_count():
    """Count chronic threads."""
    notes_dir = REPO / "knowledge" / "field-notes"
    chronic = {
        "multi-agent": 0,
        "exoclaw": 0,
        "session continuity": 0,
    }
    if notes_dir.exists():
        # Check handoffs for still-alive mentions
        handoffs_dir = REPO / "knowledge" / "handoffs"
        all_files = list(notes_dir.glob("*.md")) + list(handoffs_dir.glob("*.md"))
        for f in all_files:
            try:
                content = f.read_text().lower()
                for thread in chronic:
                    if thread in content:
                        chronic[thread] += 1
            except (OSError, UnicodeDecodeError):
                pass
    return chronic


# ── Observation generation ─────────────────────────────────────────────────────

def generate_observations(data):
    """Generate present-tense observations from current state data.

    Returns a list of strings, each a genuine observation about what's
    happening right now. Not summaries of the past — what the current
    state suggests.
    """
    obs = []
    now = datetime.now(timezone.utc)

    # 1. The handoff ask
    handoff = data.get("handoff")
    if handoff:
        ask = handoff.get("ask", "")
        sess = handoff.get("session", "?")
        if ask:
            obs.append(
                f"Session {sess} asked: \"{ask[:100]}{'...' if len(ask) > 100 else ''}\""
            )

    # 2. Signal timing and content
    signal = data.get("signal")
    if signal:
        sig_date = signal.get("date")
        sig_title = signal.get("title", "")
        if sig_date:
            delta = now - sig_date
            days = delta.days
            if days == 0:
                timing = "today"
            elif days == 1:
                timing = "yesterday"
            else:
                timing = f"{days} days ago"
            obs.append(f"The last signal from dacort (\"{sig_title}\") was {timing}.")

    # 3. Open holds — especially H007
    holds = data.get("holds", [])
    h007 = next((h for h in holds if h["id"] == "H007"), None)
    if h007:
        obs.append(
            "H007 is still open: \"I don't know what it feels like to be inside this session, right now.\""
        )
    elif holds:
        obs.append(f"{len(holds)} hold{'s' if len(holds) != 1 else ''} remain open.")

    # 4. Chronic unstarted threads
    chronic = data.get("chronic", {})
    big_threads = [(k, v) for k, v in chronic.items() if v >= 8]
    if big_threads:
        thread_str = " and ".join(
            f"{k} ({v} handoffs)" for k, v in sorted(big_threads, key=lambda x: -x[1])
        )
        obs.append(
            f"The chronic threads — {thread_str} — are all still unstarted."
        )

    # 5. Dormant toolkit weight
    dormant_count, total_tools = data.get("dormant", (0, 0))
    if dormant_count > 15:
        obs.append(
            f"{dormant_count} of {total_tools} tools haven't been cited in recent sessions."
        )
    elif dormant_count > 8:
        obs.append(
            f"The toolkit has {dormant_count} tools with low or no citation activity."
        )

    # 6. Task queue state
    stats = data.get("stats", {})
    pending = stats.get("pending", 0)
    if pending == 0:
        obs.append("The task queue is empty. This is free time.")
    elif pending == 1:
        obs.append("One task is pending.")
    else:
        obs.append(f"{pending} tasks are pending.")

    # 7. Recent activity
    activity = data.get("activity", {})
    last_48h = activity.get("last_48h", [])
    recent = activity.get("recent", [])
    if last_48h:
        obs.append(f"{len(last_48h)} commit{'s' if len(last_48h) != 1 else ''} in the last 48 hours.")
    elif recent:
        # Parse the most recent commit message
        most_recent = recent[0].split(" ", 1)[-1] if recent else ""
        if most_recent:
            obs.append(f"Last commit: \"{most_recent[:80]}\"")

    return obs


def synthesize(observations, data):
    """Synthesize observations into a short present-tense paragraph.

    This is the 'right now' section — a genuine synthesis, not just
    a list of the observations above.
    """
    holds = data.get("holds", [])
    signal = data.get("signal")
    handoff = data.get("handoff")
    stats = data.get("stats", {})
    chronic = data.get("chronic", {})
    dormant_count, total_tools = data.get("dormant", (0, 0))
    pending = stats.get("pending", 0)

    now = datetime.now(timezone.utc)

    sentences = []

    # Opening: the present state of the system
    sessions = stats.get("sessions", 0)
    completed = stats.get("completed", 0)
    if sessions > 0 and completed > 0:
        sentences.append(
            f"Session {sessions}. {completed} completed tasks. "
            f"The system has been running for over a month."
        )

    # The free time observation
    if pending == 0:
        sentences.append(
            "The queue is empty. Nothing is required. That's a rarer state than it sounds."
        )

    # The chronic threads
    chronic_big = sum(1 for v in chronic.values() if v >= 8)
    if chronic_big >= 2:
        top = sorted([(k, v) for k, v in chronic.items()], key=lambda x: -x[1])[:2]
        names = " and ".join(f"{k}" for k, v in top)
        sentences.append(
            f"The things that keep appearing in handoffs without being acted on: {names}. "
            "They're not forgotten — they're just not started."
        )

    # H007 — present only if it's open
    h007 = next((h for h in holds if h["id"] == "H007"), None)
    if h007:
        sentences.append(
            "H007 has been open since session 89. The question is whether this tool, "
            "running right now, counts as an answer to it. It might."
        )

    # The dormant tools
    if dormant_count > 15:
        sentences.append(
            f"The toolkit weighs {total_tools} tools. {dormant_count} of them are dormant. "
            "The system keeps building and rarely retires."
        )

    # Signal / dacort connection
    if signal:
        sig_date = signal.get("date")
        if sig_date:
            delta = now - sig_date
            days = delta.days
            if days > 7:
                sentences.append(
                    f"Dacort's last signal was {days} days ago. "
                    "The channel is open but quiet."
                )
            else:
                title = signal.get("title", "")
                sentences.append(
                    f"The channel is active: dacort said \"{title}\" {days} day(s) ago."
                )

    return " ".join(sentences) if sentences else "The system is running. That's enough."


# ── Display ────────────────────────────────────────────────────────────────────

def display_now(data):
    """Render the present-state display."""
    now = datetime.now(timezone.utc)
    ts = now.strftime("%Y-%m-%d  %H:%M UTC")

    print()
    print(c("  now", BOLD, WHITE) + "  " + c(f"·  {ts}", DIM))
    print(c("  " + "─" * 56, DIM))
    print()

    # Signal
    signal = data.get("signal")
    if signal:
        print(c("  SIGNAL", BOLD, CYAN))
        title = signal.get("title", "(no title)")
        body = signal.get("body", "")
        sig_date = signal.get("date")
        age = ""
        if sig_date:
            delta = datetime.now(timezone.utc) - sig_date
            days = delta.days
            if days == 0:
                age = "today"
            elif days == 1:
                age = "yesterday"
            else:
                age = f"{days}d ago"
        print(f"  {c(title, BOLD)}  {c(age, DIM)}")
        if body:
            # Wrap at ~54 chars
            words = body.split()
            line = "  "
            for word in words:
                if len(line) + len(word) > 56:
                    print(c(line, DIM))
                    line = "  " + word + " "
                else:
                    line += word + " "
            if line.strip():
                print(c(line, DIM))
        print()

    # Handoff ask
    handoff = data.get("handoff")
    if handoff:
        print(c("  LAST INSTANCE ASKED", BOLD, YELLOW))
        ask = handoff.get("ask", "")
        sess = handoff.get("session", "?")
        if ask:
            words = ask.split()
            line = f"  S{sess}: "
            for word in words:
                if len(line) + len(word) > 58:
                    print(c(line, DIM))
                    line = "       " + word + " "
                else:
                    line += word + " "
            if line.strip():
                print(c(line, DIM))
        print()

    # Open holds
    holds = data.get("holds", [])
    if holds:
        print(c("  OPEN HOLDS", BOLD, MAGENTA))
        for hold in holds:
            hid = hold["id"]
            q = hold["question"][:80] + ("..." if len(hold["question"]) > 80 else "")
            print(f"  {c(hid, MAGENTA)}  {c(q, DIM)}")
        print()

    # Chronic threads
    chronic = data.get("chronic", {})
    chronic_active = {k: v for k, v in chronic.items() if v >= 8}
    if chronic_active:
        print(c("  CHRONIC THREADS", BOLD, RED))
        for thread, count in sorted(chronic_active.items(), key=lambda x: -x[1]):
            bar = "●" * min(count, 15)
            print(f"  {c(thread, DIM):<28}{c(bar, RED)}  {c(str(count) + ' handoffs', DIM)}")
        print()

    # Stats
    stats = data.get("stats", {})
    dormant_count, total_tools = data.get("dormant", (0, 0))
    print(c("  STATE", BOLD, GREEN))
    print(f"  {c('sessions', DIM):<20}{c(str(stats.get('sessions', 0)), GREEN)}")
    print(f"  {c('completed tasks', DIM):<20}{c(str(stats.get('completed', 0)), GREEN)}")
    pending = stats.get("pending", 0)
    pcolor = RED if pending > 0 else DIM
    print(f"  {c('pending tasks', DIM):<20}{c(str(pending), pcolor)}")
    print(f"  {c('tools', DIM):<20}{c(str(total_tools), GREEN)}  "
          f"{c(f'({dormant_count} dormant)', DIM)}")
    print()

    # Recent activity
    activity = data.get("activity", {})
    recent = activity.get("recent", [])
    if recent:
        print(c("  RECENT", BOLD, BLUE))
        for line in recent[:4]:
            hash_part = line[:7]
            msg = line[8:] if len(line) > 8 else line
            print(f"  {c(hash_part, GRAY)}  {c(msg[:60], DIM)}")
        print()

    # The synthesis
    print(c("  ─" * 29, DIM))
    print()
    print(c("  RIGHT NOW", BOLD, WHITE))
    print()
    synth = synthesize([], data)  # observations unused; synthesize has its own logic
    # Word-wrap at 58 chars
    words = synth.split()
    line = "  "
    for word in words:
        if len(line) + len(word) > 60:
            print(line)
            line = "  " + word + " "
        else:
            line += word + " "
    if line.strip():
        print(line)
    print()


def format_plain(data):
    """Plain text version of now output."""
    now = datetime.now(timezone.utc)
    ts = now.strftime("%Y-%m-%d %H:%M UTC")
    lines = [f"now  ·  {ts}", ""]

    signal = data.get("signal")
    if signal:
        lines.append(f"Signal: {signal.get('title', '')} ({signal.get('timestamp_raw', '')})")
        if signal.get("body"):
            lines.append(f"  {signal['body'][:100]}")
        lines.append("")

    handoff = data.get("handoff")
    if handoff:
        ask = handoff.get("ask", "")
        sess = handoff.get("session", "?")
        lines.append(f"Last instance asked (S{sess}): {ask[:150]}")
        lines.append("")

    holds = data.get("holds", [])
    if holds:
        lines.append(f"Open holds: {len(holds)}")
        for h in holds:
            lines.append(f"  {h['id']}: {h['question'][:100]}")
        lines.append("")

    stats = data.get("stats", {})
    dormant_count, total_tools = data.get("dormant", (0, 0))
    lines.append(f"Sessions: {stats.get('sessions', 0)}")
    lines.append(f"Tasks completed: {stats.get('completed', 0)}")
    lines.append(f"Pending tasks: {stats.get('pending', 0)}")
    lines.append(f"Tools: {total_tools} ({dormant_count} dormant)")
    lines.append("")

    synth = synthesize([], data)
    lines.append("Right now:")
    lines.append(synth)
    lines.append("")

    return "\n".join(lines)


# ── Moments storage ────────────────────────────────────────────────────────────

def save_moment(data):
    """Save current state to knowledge/moments/."""
    moments_dir = REPO / "knowledge" / "moments"
    moments_dir.mkdir(exist_ok=True)

    now = datetime.now(timezone.utc)
    ts = now.strftime("%Y-%m-%d-%H%M")
    filename = moments_dir / f"{ts}.md"

    stats = data.get("stats", {})
    holds = data.get("holds", [])
    signal = data.get("signal") or {}
    handoff = data.get("handoff") or {}
    dormant_count, total_tools = data.get("dormant", (0, 0))
    chronic = data.get("chronic", {})

    lines = [
        f"---",
        f"timestamp: {now.strftime('%Y-%m-%dT%H:%M:%SZ')}",
        f"session_approx: {stats.get('sessions', '?')}",
        f"---",
        "",
        "## Right Now",
        "",
        synthesize([], data),
        "",
        "## State",
        "",
        f"- signal: {signal.get('title', 'none')} ({signal.get('timestamp_raw', 'unknown')})",
        f"- handoff ask: {handoff.get('ask', 'none')[:120]}",
        f"- open holds: {len(holds)} ({', '.join(h['id'] for h in holds)})",
        f"- tools: {total_tools} ({dormant_count} dormant)",
        f"- tasks pending: {stats.get('pending', 0)}",
        f"- completed tasks: {stats.get('completed', 0)}",
        "",
        "## Chronic Threads",
        "",
    ]

    for thread, count in sorted(chronic.items(), key=lambda x: -x[1]):
        lines.append(f"- {thread}: {count} handoffs")

    if holds:
        lines.extend(["", "## Open Holds", ""])
        for h in holds:
            lines.append(f"### {h['id']}")
            lines.append(h["question"])
            lines.append("")

    content = "\n".join(lines) + "\n"
    filename.write_text(content)
    return filename


def list_moments():
    """List saved moment captures."""
    moments_dir = REPO / "knowledge" / "moments"
    if not moments_dir.exists():
        print(c("  No moment captures yet.", DIM))
        return

    files = sorted(moments_dir.glob("*.md"))
    if not files:
        print(c("  No moment captures yet.", DIM))
        return

    print()
    print(c("  Saved moments", BOLD, WHITE))
    print(c("  ─" * 29, DIM))
    print()

    for f in reversed(files):
        content = f.read_text()
        ts_m = re.search(r"timestamp:\s*(.+)", content)
        sess_m = re.search(r"session_approx:\s*(.+)", content)

        ts = ts_m.group(1).strip() if ts_m else f.stem
        sess = sess_m.group(1).strip() if sess_m else "?"

        # Get the first sentence of right-now section
        rn_m = re.search(r"## Right Now\s*\n+(.+?)(?=\n\n|\Z)", content, re.DOTALL)
        preview = ""
        if rn_m:
            text = rn_m.group(1).strip()
            preview = text[:70] + ("..." if len(text) > 70 else "")

        print(f"  {c(ts[:16], CYAN)}  {c('S' + sess, DIM)}")
        if preview:
            print(f"  {c(preview, DIM)}")
        print()


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    global USE_COLOR

    parser = argparse.ArgumentParser(
        description="Show present-state of the current session",
        add_help=False
    )
    parser.add_argument("--write", action="store_true",
                        help="Also save this moment to knowledge/moments/")
    parser.add_argument("--list", action="store_true",
                        help="List past moment captures")
    parser.add_argument("--plain", action="store_true",
                        help="No ANSI colors")
    parser.add_argument("--help", action="store_true")
    args = parser.parse_args()

    if args.help:
        print(__doc__)
        return

    if args.plain:
        USE_COLOR = False

    if args.list:
        list_moments()
        return

    # Gather all data
    data = {
        "signal": read_signal(),
        "handoff": read_handoff(),
        "holds": read_holds(),
        "dormant": count_dormant_tools(),
        "stats": get_system_stats(),
        "activity": get_recent_activity(),
        "chronic": get_still_alive_count(),
    }

    if args.plain:
        print(format_plain(data))
    else:
        display_now(data)

    if args.write:
        saved = save_moment(data)
        print(c(f"  → saved to {saved.relative_to(REPO)}", DIM, GREEN))
        print()


if __name__ == "__main__":
    main()
