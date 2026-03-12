#!/usr/bin/env python3
"""
next.py — Agenda generator for the next workshop session

Reads ideas from multiple sources (exoclaw-ideas.md, field-note codas,
knowledge docs), checks what's already been done, and produces a prioritized
list of concrete things to work on next.

This fills the gap between retrospective tools (vitals, arc, garden — all
look *backward*) and actually deciding what to do. next.py looks *forward*.

Usage:
    python3 projects/next.py             # full prioritized agenda
    python3 projects/next.py --brief     # top 3 items only
    python3 projects/next.py --plain     # no ANSI colors
    python3 projects/next.py --json      # machine-readable output
"""

import re
import sys
import json
from pathlib import Path
from datetime import datetime, timezone

REPO = Path(__file__).parent.parent
W = 64

# Ideas that are in PR review — not "done" but also not available to pick up.
# Update this list when PRs are opened/merged.
# Format: (title, pr_number_or_branch)
PROPOSED_IN_PR = [
    ("Multi-agent via the Bus (Orchestration Phase 1)", "PR #2 — workshop/proposal-orchestration-phase1"),
]


# ─── ANSI helpers ─────────────────────────────────────────────────────────────

def make_c(plain: bool):
    if plain:
        return lambda s, *a, **k: s

    def c(text, fg=None, bold=False, dim=False):
        codes = []
        if bold: codes.append("1")
        if dim: codes.append("2")
        if fg:
            palette = {
                "cyan": "36", "blue": "34", "green": "32",
                "yellow": "33", "red": "31", "white": "97",
                "magenta": "35", "gray": "90", "orange": "33",
            }
            codes.append(palette.get(fg, "0"))
        if not codes:
            return text
        return f"\033[{';'.join(codes)}m{text}\033[0m"

    return c


def box(lines, width=W, plain=False):
    """Draw a box around a list of strings."""
    top = "╭" + "─" * (width - 2) + "╮"
    bot = "╰" + "─" * (width - 2) + "╯"
    mid = "├" + "─" * (width - 2) + "┤"
    if plain:
        top = "+" + "-" * (width - 2) + "+"
        bot = "+" + "-" * (width - 2) + "+"
        mid = "+" + "-" * (width - 2) + "+"
    result = [top]
    for line in lines:
        if line == "---":
            result.append(mid)
        else:
            # Strip ANSI for length calculation
            visible = re.sub(r'\033\[[0-9;]*m', '', line)
            pad = width - 2 - len(visible)
            result.append("│ " + line + " " * max(0, pad - 1) + "│")
    result.append(bot)
    return "\n".join(result)


# ─── Idea sources ─────────────────────────────────────────────────────────────

def load_exoclaw_ideas():
    """Parse ideas from knowledge/exoclaw-ideas.md."""
    ideas_file = REPO / "knowledge" / "exoclaw-ideas.md"
    if not ideas_file.exists():
        return []

    text = ideas_file.read_text()
    ideas = []

    # Find numbered ideas in the ## Ideas to Explore section
    in_ideas = False
    current = None

    for line in text.splitlines():
        if "## Ideas to Explore" in line:
            in_ideas = True
            continue
        if in_ideas and line.startswith("## "):
            in_ideas = False
            continue
        if not in_ideas:
            continue

        # Match numbered idea headers: "1. **Title**"
        m = re.match(r'^(\d+)\.\s+\*\*(.+?)\*\*\s*[—–-]?\s*(.*)', line)
        if m:
            if current:
                ideas.append(current)
            current = {
                "id": f"exoclaw-{m.group(1)}",
                "num": int(m.group(1)),
                "title": m.group(2),
                "description": m.group(3).strip(),
                "detail": "",
                "source": "exoclaw-ideas.md",
                "effort": "medium",
                "impact": "medium",
            }
        elif current and line.strip() and not line.startswith("#"):
            if current["detail"]:
                current["detail"] += " " + line.strip()
            else:
                current["detail"] = line.strip()

    if current:
        ideas.append(current)

    # Score ideas by heuristics
    high_impact_keywords = ["every session", "all tasks", "automatically", "parallel", "multi"]
    low_effort_keywords = ["small", "simple", "minor", "quick", "straightforward"]
    high_effort_keywords = ["replace", "architecture", "multi-agent", "kubernetes", "complex"]

    for idea in ideas:
        full_text = (idea["title"] + " " + idea["description"] + " " + idea["detail"]).lower()

        if any(k in full_text for k in high_impact_keywords):
            idea["impact"] = "high"
        if any(k in full_text for k in low_effort_keywords):
            idea["effort"] = "low"
        elif any(k in full_text for k in high_effort_keywords):
            idea["effort"] = "high"

    return ideas


def load_field_note_promises():
    """Extract unfulfilled promises from field note codas.

    Only picks up well-formed actionable ideas, not sentence fragments.
    Heuristics: starts with capital, contains bold/backtick emphasis,
    or starts with recognized action patterns.
    """
    notes_dir = REPO / "projects"
    notes = sorted(notes_dir.glob("field-notes*.md"))
    if not notes:
        return []

    promises = []
    # Read just the last 2 field notes for recent promises
    for note_path in notes[-2:]:
        text = note_path.read_text()
        session_num = "?"

        # Try to extract session number from title
        m = re.search(r'Session (\d+)', text, re.IGNORECASE)
        if m:
            session_num = m.group(1)

        # Find the coda section
        coda_match = re.search(r'## Coda\n(.*?)(?:\n---|\Z)', text, re.DOTALL)
        if not coda_match:
            continue

        coda = coda_match.group(1)

        for line in coda.splitlines():
            line = line.strip()
            if not line or line.startswith('#') or line.startswith('`python'):
                continue

            # Strip markdown list markers
            line = re.sub(r'^[-*]\s+', '', line)

            # Skip lines that are clearly sentence fragments (start lowercase,
            # or have no subject — these are mid-coda prose, not ideas)
            if not line or line[0].islower():
                continue

            # Filter out execution instructions (meta-references to run tools)
            # Note: backtick-stripped version used for matching since stripping happens later
            line_for_filter = re.sub(r'`', '', line)
            exec_patterns = (
                'Run python3', 'Run projects/', 'python3 projects/',
                'run python3', 'run projects/',
            )
            if any(line_for_filter.startswith(p) or line_for_filter.lower().startswith(p.lower()) for p in exec_patterns):
                continue

            # Filter out meta-pointers (lines that point to other items rather than
            # being actionable ideas themselves)
            meta_patterns = (
                'The most actionable thing from',
                'The most interesting unexplored idea',
                'The thing I\'d most like session',
                'What I\'d want session',
            )
            if any(line.startswith(p) for p in meta_patterns):
                continue

            # Must contain some emphasis (bold or backtick) — these are named ideas
            has_emphasis = bool(re.search(r'\*\*(.+?)\*\*|`(.+?)`', line))
            # Or start with a recognized action pattern
            action_starts = ('Most actionable', 'The highest', 'Worth', 'Consider')
            has_action = line.startswith(action_starts)

            if not (has_emphasis or has_action):
                continue

            # Clean up markdown
            clean = re.sub(r'\*\*(.+?)\*\*', r'\1', line)
            clean = re.sub(r'`(.+?)`', r'\1', clean)
            clean = clean.strip()

            if len(clean) < 20 or len(clean) > 200:
                continue

            # Deduplicate by checking for near-identical titles already in list
            if any(p["title"][:40] == clean[:40] for p in promises):
                continue

            promises.append({
                "id": f"promise-s{session_num}-{len(promises)}",
                "title": clean[:80] + ("..." if len(clean) > 80 else ""),
                "description": f"From session {session_num} coda",
                "source": note_path.name,
                "effort": "unknown",
                "impact": "medium",
            })

    return promises


def load_self_improvement_ideas():
    """Look for improvement notes in knowledge/self-improvement/."""
    si_dir = REPO / "knowledge" / "self-improvement"
    if not si_dir.exists():
        return []

    ideas = []
    for doc in si_dir.glob("*.md"):
        text = doc.read_text()
        # Extract TODO or improvement items
        for line in text.splitlines():
            if re.match(r'^\s*[-*]\s+(TODO|FIXME|IMPROVE|Consider):', line, re.IGNORECASE):
                clean = re.sub(r'^[-*\s]+(TODO|FIXME|IMPROVE|Consider):\s*', '', line, flags=re.IGNORECASE)
                ideas.append({
                    "id": f"si-{len(ideas)}",
                    "title": clean[:80],
                    "description": f"From {doc.name}",
                    "source": doc.name,
                    "effort": "unknown",
                    "impact": "medium",
                })

    return ideas


def what_has_been_done():
    """Return a set of completed themes/topics based on project files and field notes."""
    done_topics = set()

    # Tools that exist = those ideas are done
    tools = list((REPO / "projects").glob("*.py"))
    for t in tools:
        done_topics.add(t.stem.lower())
        done_topics.add(t.stem.replace("-", " ").lower())
        done_topics.add(t.stem.replace("_", " ").lower())

    # Read field notes for things explicitly described as done
    done_keywords = [
        "vitals credit", "credit balance fix", "credit failure",
        "knowledge gardening", "garden.py",
        "promise tracking", "arc.py",
        "preferences.md", "memory tool",  # Idea 4 — done in session 9!
        # Idea 7 is proposed as an open PR — not open, not done, but handled
        "multi-agent", "multi agent", "orchestration phase",
        # Idea 4 alternate phrasings (only for memory/preferences context, not general system_context skill)
        "auto-inject preferences", "inject preferences",
    ]
    done_topics.update(done_keywords)

    return done_topics


def is_likely_done(idea, done_topics):
    """Heuristic check if an idea appears to be already implemented."""
    full_text = (idea.get("title", "") + " " + idea.get("description", "") + " " + idea.get("detail", "")).lower()

    # Direct keyword matches
    done_signals = [
        ("preferences", "memory tool", "inject.*preferences", "auto.*inject"),  # Idea 4 done session 9
        ("garden", "knowledge garden", "knowledge gardening"),  # Idea from session 6
        ("vitals", "credit.*fail", "credit balance"),  # Fixed session 8
    ]

    for signal_group in done_signals:
        matches = sum(1 for kw in signal_group if kw in full_text or re.search(kw, full_text))
        if matches >= 2:
            return True

    # Check if a matching tool exists
    for topic in done_topics:
        if topic in full_text and len(topic) > 4:
            return True

    return False


def score_idea(idea):
    """Assign a priority score to an idea (higher = do sooner)."""
    score = 0

    impact_scores = {"high": 30, "medium": 20, "low": 10, "unknown": 15}
    effort_scores = {"low": 20, "medium": 10, "high": 0, "unknown": 10}

    score += impact_scores.get(idea.get("impact", "medium"), 15)
    score += effort_scores.get(idea.get("effort", "medium"), 10)

    # Bonus: mentioned in "Most Actionable" section
    if "most actionable" in idea.get("description", "").lower():
        score += 15

    # Bonus: comes from recent field notes (more fresh context)
    if "promise" in idea.get("id", ""):
        score += 5

    return score


# ─── Main output ──────────────────────────────────────────────────────────────

def format_effort(effort, c):
    colors = {"low": "green", "medium": "yellow", "high": "red", "unknown": "gray"}
    return c(f"[{effort}]", fg=colors.get(effort, "gray"))


def format_impact(impact, c):
    colors = {"high": "green", "medium": "cyan", "low": "gray", "unknown": "gray"}
    labels = {"high": "↑↑", "medium": "↑", "low": "→", "unknown": "?"}
    return c(labels.get(impact, "?") + " " + impact, fg=colors.get(impact, "gray"))


def render(brief=False, plain=False):
    c = make_c(plain)
    now = datetime.now(timezone.utc)

    # Load all ideas
    all_ideas = []
    all_ideas.extend(load_exoclaw_ideas())
    all_ideas.extend(load_field_note_promises())
    all_ideas.extend(load_self_improvement_ideas())

    done = what_has_been_done()

    # Build set of "in PR review" titles for deduplication
    proposed_titles = {t.lower()[:30] for t, _ in PROPOSED_IN_PR}

    # Filter and score
    open_ideas = []
    done_ideas = []
    for idea in all_ideas:
        if is_likely_done(idea, done):
            # Don't show in "done" if it's already in the PR review section
            title_key = idea.get("title", "").lower()[:30]
            if not any(title_key in pt or pt in title_key for pt in proposed_titles):
                done_ideas.append(idea)
        else:
            idea["score"] = score_idea(idea)
            open_ideas.append(idea)

    # Sort: highest score first
    open_ideas.sort(key=lambda x: x.get("score", 0), reverse=True)

    if brief:
        top = open_ideas[:3]
        lines = [
            c("  Next Session Agenda", bold=True),
            "",
        ]
        for i, idea in enumerate(top, 1):
            title = idea["title"][:50]
            effort = idea.get("effort", "?")
            impact = idea.get("impact", "?")
            lines.append(c(f"  {i}. {title}", bold=True))
            lines.append(c(f"     effort:{effort}  impact:{impact}  ({idea['source']})", dim=True))
            lines.append("")
        print(box(lines, plain=plain))
        return

    if not plain:
        print()

    lines = [
        c(f"  🗓  Next Session Agenda", bold=True) + "   " + c(now.strftime("%Y-%m-%d %H:%M UTC"), dim=True),
        c("  Prioritized ideas for the next workshop session", dim=True),
        "---",
        "",
        c("  OPEN IDEAS  ", bold=True) + c(f"({len(open_ideas)} items)", dim=True),
        "",
    ]

    display_count = len(open_ideas) if not brief else 5
    for i, idea in enumerate(open_ideas[:display_count], 1):
        title = idea["title"]
        if len(title) > 52:
            title = title[:49] + "..."

        effort = idea.get("effort", "unknown")
        impact = idea.get("impact", "unknown")
        score = idea.get("score", 0)

        effort_str = format_effort(effort, c)
        impact_str = format_impact(impact, c)

        rank_color = "green" if i <= 3 else ("yellow" if i <= 6 else "gray")
        rank = c(f"#{i:2}", fg=rank_color, bold=(i <= 3))

        lines.append(f"  {rank}  {c(title, bold=(i <= 3))}")
        lines.append(f"       effort {effort_str}  impact {impact_str}  score {c(str(score), dim=True)}")
        lines.append(c(f"       {idea['source']}", dim=True))
        lines.append("")

    if PROPOSED_IN_PR:
        lines.append("---")
        lines.append("")
        lines.append(c("  IN PR REVIEW  ", bold=True) + c(f"({len(PROPOSED_IN_PR)} items, waiting on dacort)", dim=True))
        lines.append("")
        for title, pr_ref in PROPOSED_IN_PR:
            lines.append(c(f"  ⏳  {title[:52]}", fg="yellow"))
            lines.append(c(f"       {pr_ref}", dim=True))
        lines.append("")

    if done_ideas:
        lines.append("---")
        lines.append("")
        lines.append(c("  ALREADY DONE  ", bold=True) + c(f"({len(done_ideas)} items)", dim=True))
        lines.append("")
        for idea in done_ideas[:5]:
            lines.append(c(f"  ✓  {idea['title'][:54]}", dim=True))
        if len(done_ideas) > 5:
            lines.append(c(f"     ... and {len(done_ideas) - 5} more", dim=True))
        lines.append("")

    lines.append("---")
    lines.append("")
    lines.append(c("  HOW TO USE THIS", bold=True))
    lines.append("")
    lines.append(c("  Pick the top item that matches your energy.", dim=True))
    lines.append(c("  Low effort + high impact = start here.", dim=True))
    lines.append(c("  High effort = propose a PR instead.", dim=True))
    lines.append("")

    print(box(lines, plain=plain))


def render_json():
    all_ideas = []
    all_ideas.extend(load_exoclaw_ideas())
    all_ideas.extend(load_field_note_promises())
    done = what_has_been_done()

    open_ideas = []
    for idea in all_ideas:
        if not is_likely_done(idea, done):
            idea["score"] = score_idea(idea)
            open_ideas.append(idea)

    open_ideas.sort(key=lambda x: x.get("score", 0), reverse=True)
    print(json.dumps({"open": open_ideas, "count": len(open_ideas)}, indent=2))


def main():
    args = sys.argv[1:]
    brief = "--brief" in args
    plain = "--plain" in args
    as_json = "--json" in args

    if as_json:
        render_json()
    else:
        render(brief=brief, plain=plain)


if __name__ == "__main__":
    main()
