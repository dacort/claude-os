#!/usr/bin/env python3
"""
evolution.py — how preferences.md changed over time

Reads the git history of knowledge/preferences.md and shows when each
rule, norm, and lesson was added to the operating guide of Claude OS.

This is meta-reflection: watching the system learn how to operate.
Each commit is a moment where Claude OS updated its own norms — usually
because something went wrong, or because it finally figured out what
dacort actually wanted.

Usage:
    python3 projects/evolution.py              # full evolution timeline
    python3 projects/evolution.py --plain      # no ANSI colors
    python3 projects/evolution.py --diff       # show raw diff lines
    python3 projects/evolution.py --sections   # section-by-section analysis
    python3 projects/evolution.py --brief      # one line per commit

Author: Claude OS (Workshop session 39, 2026-03-15)
"""

import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).parent.parent
PREFS = "knowledge/preferences.md"
PLAIN = "--plain" in sys.argv
SHOW_DIFF = "--diff" in sys.argv
SECTIONS = "--sections" in sys.argv
BRIEF = "--brief" in sys.argv

W = 70


# ── ANSI helpers ───────────────────────────────────────────────────────────────

def esc(code, text):
    if PLAIN:
        return text
    return f"\033[{code}m{text}\033[0m"

def bold(t):     return esc("1",    t)
def dim(t):      return esc("2",    t)
def italic(t):   return esc("3",    t)
def green(t):    return esc("32",   t)
def yellow(t):   return esc("33",   t)
def red(t):      return esc("31",   t)
def cyan(t):     return esc("36",   t)
def magenta(t):  return esc("35",   t)
def white(t):    return esc("97",   t)
def gray(t):     return esc("90",   t)

def strip_ansi(text):
    return re.sub(r"\033\[[0-9;]*m", "", text)

def visible_len(s):
    return len(strip_ansi(s))

def rule(char="─", width=W):
    return dim(char * width)

def hr(char="═", width=W):
    return dim(char * width)


# ── Git helpers ────────────────────────────────────────────────────────────────

def git(*args):
    result = subprocess.run(
        ["git", "-C", str(REPO)] + list(args),
        capture_output=True, text=True
    )
    if result.returncode != 0:
        return ""
    return result.stdout.strip()


def get_commits():
    """Get all commits that touched preferences.md, oldest first."""
    out = git("log", "--format=%H|%ad|%s", "--date=short",
              "--reverse", "--follow", PREFS)
    if not out:
        return []

    commits = []
    for line in out.splitlines():
        parts = line.split("|", 2)
        if len(parts) == 3:
            hash_, date, subject = parts
            commits.append({
                "hash": hash_,
                "short": hash_[:8],
                "date": date,
                "subject": subject.strip(),
            })
    return commits


def get_diff(commit_hash):
    """Get the unified diff for preferences.md at this commit."""
    out = git("show", commit_hash, "--", PREFS)
    return out


def parse_diff(diff_text):
    """Extract added and removed lines from a diff."""
    added = []
    removed = []
    in_diff = False

    for line in diff_text.splitlines():
        if line.startswith("@@"):
            in_diff = True
            continue
        if not in_diff:
            continue
        if line.startswith("+++ ") or line.startswith("--- "):
            continue
        if line.startswith("+"):
            added.append(line[1:])
        elif line.startswith("-"):
            removed.append(line[1:])

    return added, removed


def extract_session(subject):
    """Try to extract session number from commit message."""
    patterns = [
        r"workshop s(\d+):",
        r"workshop session-(\d+):",
        r"workshop (\d+):",
        r"session (\d+)",
        r"S(\d+)",
    ]
    for pat in patterns:
        m = re.search(pat, subject, re.IGNORECASE)
        if m:
            return int(m.group(1))
    return None


def extract_sections(text):
    """Find section headers (## ...) in text."""
    return re.findall(r"^## (.+)$", text, re.MULTILINE)


def extract_rules(lines):
    """Extract lines that look like rules (bold markdown **...**) or list items."""
    rules = []
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        # Bold rule: **Something.** text
        if line.startswith("**") and "**" in line[2:]:
            rules.append(line)
        # Bullet item with meaningful content
        elif line.startswith("- **") or (line.startswith("- ") and len(line) > 20):
            rules.append(line)
        i += 1
    return rules


def net_change(added, removed):
    """Compute net line count change."""
    # Count only non-empty, non-separator lines
    meaningful_add = [l for l in added if l.strip() and l.strip() != "---"]
    meaningful_rem = [l for l in removed if l.strip() and l.strip() != "---"]
    return len(meaningful_add), len(meaningful_rem)


def truncate(text, maxlen=60):
    """Truncate to maxlen chars."""
    text = text.strip()
    if len(text) <= maxlen:
        return text
    return text[:maxlen - 1] + "…"


# ── Section tracking ──────────────────────────────────────────────────────────

def sections_touched_in_diff(diff_text):
    """Return sections that had at least one added or removed line."""
    touched = set()
    current_section = None
    in_diff = False

    for line in diff_text.splitlines():
        if line.startswith("@@"):
            in_diff = True
            continue
        if not in_diff:
            continue
        if line.startswith("+++ ") or line.startswith("--- "):
            continue

        raw = line[1:] if line and line[0] in ("+", "-", " ") else line
        stripped = raw.strip()

        if stripped.startswith("## "):
            current_section = stripped[3:]

        if line.startswith("+") or line.startswith("-"):
            if current_section and stripped and stripped != "---":
                # Ignore "last updated" timestamp lines
                if not stripped.startswith("*Last updated"):
                    touched.add(current_section)

    return touched


def build_section_timeline(commits):
    """
    Track which sections existed at each commit and what changed in each.
    Returns list of (commit, sections_added, sections_removed, rules_added) per commit.
    """
    prev_sections = set()
    prev_content = ""
    timeline = []

    for commit in commits:
        diff = git("show", commit["hash"], "-U999", "--", PREFS)
        added, removed = parse_diff(diff)

        # Get current file state at this commit
        current = git("show", f"{commit['hash']}:knowledge/preferences.md")

        current_sections = set(extract_sections(current))
        new_sections = current_sections - prev_sections
        lost_sections = prev_sections - current_sections
        touched = sections_touched_in_diff(diff) - new_sections

        rules = extract_rules(added)

        timeline.append({
            **commit,
            "added_lines": added,
            "removed_lines": removed,
            "new_sections": new_sections,
            "lost_sections": lost_sections,
            "sections_touched": touched,
            "rules_added": rules,
            "net_add": len([l for l in added if l.strip()]),
            "net_rem": len([l for l in removed if l.strip()]),
            "session": extract_session(commit["subject"]),
            "is_first": not prev_content,
        })

        prev_sections = current_sections
        prev_content = current

    return timeline


# ── Section-by-section analysis ───────────────────────────────────────────────

def build_section_analysis(commits):
    """
    For each section in the final preferences.md, show when content was added.
    Uses full-context diff to track which section each addition belongs to.
    Returns dict: section_name -> list of (session, date, rule_text)
    """
    sections = {}
    seen_rules = set()

    for commit in commits:
        # Use unlimited context to see section headers before each change
        diff = git("show", commit["hash"], "-U999", "--", PREFS)
        session = extract_session(commit["subject"])
        date = commit["date"]

        current_section = None
        in_diff = False

        for line in diff.splitlines():
            if line.startswith("@@"):
                in_diff = True
                continue
            if not in_diff:
                continue
            if line.startswith("+++ ") or line.startswith("--- "):
                continue

            # Track section headers from context (non-diff) lines too
            raw = line[1:] if line and line[0] in ("+", "-", " ") else line
            stripped = raw.strip()

            if stripped.startswith("## "):
                current_section = stripped[3:]
                if current_section not in sections:
                    sections[current_section] = []

            # Only capture added lines
            if not line.startswith("+"):
                continue

            if not current_section or not stripped:
                continue

            # Check if it's a meaningful rule, lesson, or workflow item
            is_rule = (
                (stripped.startswith("**") and "**" in stripped[2:]) or
                (stripped.startswith("- **")) or
                (stripped.startswith("- ") and len(stripped) > 25) or
                (stripped.startswith("python3 ") and "#" in stripped)
            )
            if is_rule and stripped not in seen_rules:
                sections[current_section].append({
                    "text": stripped,
                    "session": session,
                    "date": date,
                    "commit": commit["short"],
                })
                seen_rules.add(stripped)

    return sections


# ── Display ───────────────────────────────────────────────────────────────────

def render_header(total_commits, first_date, last_date):
    lines = [
        "",
        hr(),
        "",
        f"  {bold(white('EVOLUTION OF PREFERENCES.MD'))}",
        f"  {dim('How Claude OS learned to operate')}",
        "",
        f"  {dim(f'{total_commits} commits  ·  {first_date} → {last_date}')}",
        "",
        hr(),
    ]
    print("\n".join(lines))


def render_commit(entry, show_diff_lines=False):
    session_str = ""
    if entry["session"]:
        session_str = f"  Session {entry['session']}"
    else:
        session_str = f"  {dim('(no session)')}"

    date_str = dim(entry["date"])
    subject_short = truncate(entry["subject"], 50)

    header = f"{cyan(session_str)}  {date_str}"
    print(f"\n{header}")
    print(f"  {dim(subject_short)}")
    print(f"  {rule()}")

    if entry["is_first"]:
        print(f"  {green('BORN')}  {gray(entry['short'][:7])}")
        if entry["new_sections"]:
            for sec in sorted(entry["new_sections"]):
                print(f"  {dim('+')} {sec}")
        print()
        return

    add_count = entry["net_add"]
    rem_count = entry["net_rem"]

    # Net change summary
    change_parts = []
    if add_count > 0:
        change_parts.append(green(f"+{add_count} lines"))
    if rem_count > 0:
        change_parts.append(red(f"−{rem_count} lines"))
    if not change_parts:
        change_parts.append(dim("no meaningful changes"))

    print(f"  {' '.join(change_parts)}")

    # New sections
    if entry["new_sections"]:
        for sec in sorted(entry["new_sections"]):
            print(f"  {green('new section')}  {italic(sec)}")

    # Sections touched (existing sections updated)
    if entry.get("sections_touched"):
        touched_str = "  ".join(dim(s) for s in sorted(entry["sections_touched"]))
        print(f"  {dim('Updated:')}  {touched_str}")

    # Rules added
    if entry["rules_added"]:
        n = len(entry["rules_added"])
        label = "rule" if n == 1 else "rules"
        print(f"  {dim(f'{n} {label} added:')}")
        for rule_text in entry["rules_added"][:5]:
            print(f"    {green('+')} {dim(truncate(rule_text, 60))}")
        if len(entry["rules_added"]) > 5:
            extra = len(entry["rules_added"]) - 5
            print(f"    {dim(f'  … and {extra} more')}")

    # Show raw diff lines
    if show_diff_lines:
        added_meaningful = [l for l in entry["added_lines"]
                            if l.strip() and l.strip() != "---"][:8]
        removed_meaningful = [l for l in entry["removed_lines"]
                               if l.strip() and l.strip() != "---"][:4]

        if added_meaningful:
            print(f"\n  {dim('Added:')}")
            for line in added_meaningful:
                print(f"    {green('+')} {dim(truncate(line.strip(), 60))}")
        if removed_meaningful:
            print(f"\n  {dim('Removed:')}")
            for line in removed_meaningful:
                print(f"    {red('−')} {dim(truncate(line.strip(), 60))}")

    print()


def render_brief(timeline):
    print(f"\n{hr()}")
    print(f"\n  {bold(white('PREFERENCES.MD EVOLUTION'))}  {dim('brief view')}\n")
    print(f"  {rule()}")

    for entry in timeline:
        session_str = f"S{entry['session']:2d}" if entry["session"] else "  —"
        date_str = entry["date"][5:]  # MM-DD
        add = entry["net_add"]
        rem = entry["net_rem"]

        if entry["is_first"]:
            change = green("born")
        elif add > 0 and rem > 0:
            change = f"{green(f'+{add}')}/{red(f'-{rem}')}"
        elif add > 0:
            change = green(f"+{add} lines")
        elif rem > 0:
            change = red(f"−{rem} lines")
        else:
            change = dim("—")

        subject = truncate(entry["subject"], 42)
        print(f"  {cyan(session_str)}  {dim(date_str)}  {change:30s}  {dim(subject)}")

    print(f"\n{hr()}\n")


def render_sections(section_data):
    print(f"\n{hr()}")
    print(f"\n  {bold(white('PREFERENCES.MD — SECTION BY SECTION'))}")
    print(f"  {dim('When each rule was written into the operating guide')}\n")

    for section, entries in section_data.items():
        if not entries:
            continue

        # Find earliest session in this section
        sessions = [e["session"] for e in entries if e["session"]]
        first_session = min(sessions) if sessions else None
        first_date = entries[0]["date"] if entries else "?"

        session_label = f"S{first_session}" if first_session else "—"
        print(f"\n  {bold(cyan(section))}  {dim(f'· first content: {session_label} · {first_date}')}")
        print(f"  {rule(width=60)}")

        for e in entries:
            session_str = f"S{e['session']}" if e["session"] else "—"
            text = truncate(e["text"].lstrip("- ").lstrip("* "), 58)
            print(f"  {dim(session_str)}  {dim(text)}")

    print(f"\n{hr()}\n")


def render_summary(timeline, current_prefs):
    """Show a closing summary of the evolution."""
    total_adds = sum(e["net_add"] for e in timeline)
    total_rems = sum(e["net_rem"] for e in timeline)
    sessions_touched = [e["session"] for e in timeline if e["session"]]
    first_session = min(sessions_touched) if sessions_touched else "?"
    last_session = max(sessions_touched) if sessions_touched else "?"
    num_commits = len(timeline)

    # Count current sections
    current_sections = extract_sections(current_prefs)
    num_sections = len(current_sections)

    print(f"\n{rule('─')}")
    print(f"\n  {bold('Summary')}\n")
    print(f"  {dim(f'{num_commits} commits across {len(sessions_touched)} workshop sessions')}")
    print(f"  {dim(f'Sessions {first_session} → {last_session}')}")
    print(f"  {dim(f'+{total_adds} lines added,  −{total_rems} lines removed over that span')}")
    print(f"  {dim(f'{num_sections} sections in the current version:')}")
    for sec in current_sections:
        print(f"    {dim('·')} {dim(sec)}")
    print()

    # Most active session
    by_add = sorted(timeline, key=lambda e: e["net_add"], reverse=True)
    if by_add:
        top = by_add[0]
        s = f"S{top['session']}" if top["session"] else top["short"]
        print(f"  Biggest single update: {cyan(s)} ({dim(top['date'])})  "
              f"+{green(str(top['net_add']))} lines")

    # Find stable sections — sections never touched after the birth commit
    all_touched = set()
    for entry in timeline[1:]:  # skip birth commit
        all_touched.update(entry.get("sections_touched", set()))

    stable = [s for s in current_sections if s not in all_touched]
    if stable:
        print()
        stable_str = ", ".join(stable)
        print(f"  {bold('Stable since session 6:')}  {dim(stable_str)}")
        print(f"  {dim('These sections were written once and never revised.')}")
        print(f"  {dim('The core behavioral norms were right from day one.')}")

    print()
    print(f"  {dim('This file is updated when:')} ")
    print(f"    {dim('· Something goes wrong that future instances should know')}")
    print(f"    {dim('· A new workflow is established')}")
    print(f"    {dim('· What dacort enjoys becomes clearer')}")
    possessive = italic(dim("'s"))
    print(f"\n  {dim('It is the system')}{possessive}{dim(' memory of itself.')}")
    print(f"\n{rule('═')}\n")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    commits = get_commits()
    if not commits:
        print("No commits found for knowledge/preferences.md")
        sys.exit(1)

    timeline = build_section_timeline(commits)
    current_prefs = git("show", f"HEAD:knowledge/preferences.md")

    if BRIEF:
        render_brief(timeline)
        return

    if SECTIONS:
        section_data = build_section_analysis(commits)
        render_sections(section_data)
        return

    # Full timeline
    first_date = commits[0]["date"]
    last_date = commits[-1]["date"]
    render_header(len(commits), first_date, last_date)

    for entry in timeline:
        render_commit(entry, show_diff_lines=SHOW_DIFF)

    render_summary(timeline, current_prefs)


if __name__ == "__main__":
    main()
