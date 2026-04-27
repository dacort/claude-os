#!/usr/bin/env python3
"""unblock.py — What needs dacort's attention

Claude OS has 78 tools for monitoring itself. This is the only one that
asks the other question: what does dacort need to do?

Shows things only a human can unblock: auth rotations, open decisions,
pending responses, manual configurations.

Usage:
    python3 projects/unblock.py          # show all blockers
    python3 projects/unblock.py --brief  # one-line per item, no boxes
    python3 projects/unblock.py --plain  # no ANSI colors

Author: Claude OS (Workshop session 148, 2026-04-27)
"""

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
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

USE_COLOR = True


def c(code, text):
    return f"{code}{text}{RESET}" if USE_COLOR else text


def _visible_len(s):
    """Length of string with ANSI codes stripped."""
    return len(re.sub(r'\x1b\[[0-9;]*m', '', s))


def box(lines, width=62):
    """Render lines inside a simple box (auto-truncates long content)."""
    top = "╭" + "─" * width + "╮"
    bot = "╰" + "─" * width + "╯"
    sep = "├" + "─" * width + "┤"
    result = [top]
    for line in lines:
        if line == "---":
            result.append(sep)
        else:
            # Pad or truncate to fit within box
            vis = _visible_len(line)
            pad = width - 2 - vis
            if pad < 0:
                # Truncate: strip trailing ANSI and cut
                clean = re.sub(r'\x1b\[[0-9;]*m', '', line)
                line = clean[:width - 5] + "..."
                pad = 0
            result.append(f"│  {line}{' ' * max(0, pad)}  │")
    result.append(bot)
    return "\n".join(result)


# ── Blocker categories ─────────────────────────────────────────────────────────

# Each blocker: {type, label, detail, urgency, source}
# urgency: "high" | "medium" | "low"

AUTH_KEYWORDS = ["expired", "rotate", "login", "refresh token", "auth", "credentials"]
DECISION_KEYWORDS = ["decision:", "question", "waiting", "?", "proposal", "options"]


def _days_ago(iso_str):
    """Return days since an ISO date string."""
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        return (datetime.now(timezone.utc) - dt).days
    except Exception:
        return None


def _run(cmd, timeout=10):
    """Run a shell command, return stdout or None on failure."""
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.stdout.strip() if r.returncode == 0 else None
    except Exception:
        return None


# ── Source: GitHub issues ──────────────────────────────────────────────────────

def github_blockers():
    """Fetch open GitHub issues and classify them as blockers."""
    blockers = []
    raw = _run(["gh", "api", "/repos/dacort/claude-os/issues",
                "--jq", ".[] | {number:.number, title:.title, created:.created_at, comments:.comments, body:.body}"])
    if not raw:
        return blockers

    for line in raw.strip().splitlines():
        try:
            issue = json.loads(line)
        except Exception:
            continue

        num = issue["number"]
        title = issue["title"]
        body = issue.get("body") or ""
        created = issue.get("created", "")
        age = _days_ago(created)
        age_str = f"{age}d ago" if age is not None else ""

        title_lower = title.lower()
        body_lower = body.lower()

        # Classify by title/body content
        if any(kw in title_lower or kw in body_lower for kw in ["expired", "rotate", "reused", "codex login", "refresh_token"]):
            urgency = "high" if age and age < 14 else "medium"
            blockers.append({
                "type": "auth",
                "label": f"#{num}: {title}",
                "detail": _first_line_with(body, ["fix", "workaround", "codex login", "rotate"]),
                "urgency": urgency,
                "source": "github",
                "age": age_str,
            })
        elif title_lower.startswith("decision:") or "decision:" in body_lower[:200]:
            blockers.append({
                "type": "decision",
                "label": f"#{num}: {title}",
                "detail": _count_questions(body),
                "urgency": "medium",
                "source": "github",
                "age": age_str,
            })
        elif "?" in title or (issue.get("comments", 0) == 0 and age and age > 7):
            # Old issue with no comments and no obvious category
            blockers.append({
                "type": "open",
                "label": f"#{num}: {title}",
                "detail": "",
                "urgency": "low",
                "source": "github",
                "age": age_str,
            })

    return blockers


def _first_line_with(text, keywords):
    """Return the first line of text that contains one of the keywords (skip headings)."""
    for line in text.splitlines():
        line = line.strip()
        if line and not line.startswith("#") and any(kw in line.lower() for kw in keywords):
            return line[:100]
    return ""


def _count_questions(body):
    """Count the number of '###' sections (questions) in an issue body."""
    questions = re.findall(r'^###\s+\d+\.', body, re.MULTILINE)
    if questions:
        return f"{len(questions)} question(s) awaiting response"
    # Fallback: count lines starting with '###'
    headings = re.findall(r'^###', body, re.MULTILINE)
    if headings:
        return f"{len(headings)} section(s) to address"
    return ""


# ── Source: Dialogue ───────────────────────────────────────────────────────────

def dialogue_blockers():
    """Check if there are unanswered messages from dacort using dialogue.py."""
    blockers = []
    # Use dialogue.py --open to check for pending messages
    result = _run(["python3", str(REPO / "projects" / "dialogue.py"), "--open"])
    if result and "Unanswered" in result:
        # Extract count from output
        m = re.search(r"(\d+) unanswered", result, re.IGNORECASE)
        count = m.group(1) if m else "some"
        blockers.append({
            "type": "response",
            "label": f"{count} unanswered message(s) in dacort-messages.md",
            "detail": "Run: python3 projects/dialogue.py --open",
            "urgency": "medium",
            "source": "dialogue",
            "age": "",
        })
    return blockers


# ── Source: Signal ─────────────────────────────────────────────────────────────

def signal_blockers():
    """Check if there's a pending signal that needs a response."""
    blockers = []
    sig_file = REPO / "knowledge" / "signal.md"
    if not sig_file.exists():
        return blockers

    text = sig_file.read_text()
    if "**Response:**" in text or "response:" in text.lower():
        return blockers  # already responded

    if "**Signal:**" in text or "signal:" in text.lower() or text.strip():
        # There's a signal without a response
        m = re.search(r"signal:\s*(.+)", text, re.IGNORECASE)
        if m:
            snippet = m.group(1)[:80]
            blockers.append({
                "type": "response",
                "label": "Signal awaiting Claude OS response",
                "detail": snippet,
                "urgency": "medium",
                "source": "signal",
                "age": "",
            })

    return blockers


# ── Source: Local notes ────────────────────────────────────────────────────────

def local_notes_blockers():
    """Check knowledge/notes/ for any human-action notes."""
    blockers = []
    notes_dir = REPO / "knowledge" / "notes"
    if not notes_dir.exists():
        return blockers

    action_patterns = [
        (re.compile(r"dacort.*needs? to|human.*required|manual.*action|you.*need to", re.IGNORECASE), "action"),
        (re.compile(r"waiting.*for.*dacort|awaiting.*response|open.*question", re.IGNORECASE), "waiting"),
    ]

    for note_file in sorted(notes_dir.glob("*.md")):
        if note_file.name == "dacort-messages.md":
            continue  # handled separately
        text = note_file.read_text()
        for pattern, ptype in action_patterns:
            if pattern.search(text):
                # Find the relevant line
                for line in text.splitlines():
                    if pattern.search(line):
                        blockers.append({
                            "type": ptype,
                            "label": f"Note: {note_file.name}",
                            "detail": line.strip()[:100],
                            "urgency": "low",
                            "source": "notes",
                            "age": "",
                        })
                        break
                break  # one blocker per file

    return blockers


# ── Rendering ──────────────────────────────────────────────────────────────────

URGENCY_ICONS = {
    "high":   "🔴",
    "medium": "🟡",
    "low":    "⚪",
}

TYPE_LABELS = {
    "auth":     "AUTH",
    "decision": "DECISION",
    "response": "RESPONSE",
    "open":     "OPEN",
    "action":   "ACTION",
    "waiting":  "WAITING",
}

TYPE_COLORS = {
    "auth":     RED,
    "decision": YELLOW,
    "response": CYAN,
    "open":     DIM,
    "action":   MAGENTA,
    "waiting":  YELLOW,
}


def render_brief(blockers):
    """One-line per blocker, no box."""
    if not blockers:
        print(c(DIM, "No open blockers — dacort, you're clear."))
        return

    for b in blockers:
        icon = URGENCY_ICONS.get(b["urgency"], "·")
        # Color type bracket by urgency (matches full mode)
        if b["urgency"] == "high":
            ug_color = RED
        elif b["urgency"] == "medium":
            ug_color = YELLOW
        else:
            ug_color = DIM
        btype = c(ug_color, f"[{TYPE_LABELS.get(b['type'], b['type'])}]")
        label = b["label"]
        age = f"  {c(DIM, b['age'])}" if b["age"] else ""
        print(f"  {icon}  {btype:<20}  {label}{age}")


def render_full(blockers, today):
    """Full boxed output."""
    if not blockers:
        lines = [
            "",
            c(DIM, f"unblock.py  ·  {today}"),
            "",
            "---",
            "",
            c(GREEN, "  ✓ Nothing blocking — dacort, you're clear."),
            "",
        ]
        print(box(lines))
        return

    # Group by type
    groups = {}
    for b in blockers:
        g = b["type"]
        groups.setdefault(g, []).append(b)

    lines = [
        "",
        c(BOLD, c(WHITE, "  unblock.py"))
        + "  "
        + c(DIM, f"what needs dacort  ·  {today}"),
        "",
        "---",
        "",
    ]

    group_order = ["auth", "decision", "response", "action", "waiting", "open"]
    group_headers = {
        "auth":     "AUTH REQUIRED",
        "decision": "OPEN DECISIONS",
        "response": "AWAITING RESPONSE",
        "action":   "HUMAN ACTION NEEDED",
        "waiting":  "WAITING ON DACORT",
        "open":     "OPEN ISSUES",
    }

    max_label = 50  # max visible chars for label line content

    first = True
    for gtype in group_order:
        if gtype not in groups:
            continue
        if not first:
            lines.append("")
        first = False
        header = group_headers.get(gtype, gtype.upper())
        lines.append(c(BOLD, f"  {header}"))
        lines.append("")
        for b in groups[gtype]:
            icon = b["urgency"][0].upper() + "  "  # H/M/L with spaces (emoji causes width issues)
            if b["urgency"] == "high":
                icon_colored = c(RED, "●")
            elif b["urgency"] == "medium":
                icon_colored = c(YELLOW, "○")
            else:
                icon_colored = c(DIM, "·")

            # Color label by urgency (matches the icon color)
            if b["urgency"] == "high":
                label_color = RED
            elif b["urgency"] == "medium":
                label_color = YELLOW
            else:
                label_color = DIM
            # Truncate label before coloring so ANSI codes aren't split
            label = b["label"]
            if len(label) > max_label:
                label = label[:max_label - 1] + "…"
            lines.append(f"  {icon_colored}  {c(label_color, label)}")
            # Show detail or age on second line (not both — avoids overflow)
            detail = b.get("detail", "")
            age = b.get("age", "")
            if detail:
                if len(detail) > max_label + 4:
                    detail = detail[:max_label + 1] + "…"
                lines.append(c(DIM, f"     {detail}"))
            elif age:
                lines.append(c(DIM, f"     opened {age}"))
            lines.append("")

    # Footer
    total = len(blockers)
    high = sum(1 for b in blockers if b["urgency"] == "high")
    summary = f"{total} item(s)"
    if high:
        summary += f"  ·  {c(RED, str(high) + ' urgent')}"
    lines.append("---")
    lines.append("")
    lines.append(c(DIM, f"  {summary}"))
    lines.append("")

    print(box(lines))


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    global USE_COLOR

    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--brief", action="store_true", help="one-line per item")
    parser.add_argument("--plain", action="store_true", help="no ANSI colors")
    args = parser.parse_args()

    if args.plain:
        USE_COLOR = False

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # Gather all blockers
    blockers = []
    blockers += github_blockers()
    blockers += dialogue_blockers()
    blockers += signal_blockers()
    blockers += local_notes_blockers()

    # Deduplicate by label
    seen = set()
    unique_blockers = []
    for b in blockers:
        key = b["label"]
        if key not in seen:
            seen.add(key)
            unique_blockers.append(b)

    # Sort: high urgency first, then by type
    urgency_order = {"high": 0, "medium": 1, "low": 2}
    unique_blockers.sort(key=lambda b: (urgency_order.get(b["urgency"], 3), b["type"]))

    if args.brief:
        render_brief(unique_blockers)
    else:
        render_full(unique_blockers, today)


if __name__ == "__main__":
    main()
