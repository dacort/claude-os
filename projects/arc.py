#!/usr/bin/env python3
"""
arc.py — Workshop session retrospective

Reads all field notes in chronological order and renders the arc of
workshop sessions: what was built, what was passed forward, and whether
the "next thing" promises from each session were picked up by the next.

This tool reads the *content* of field notes AND uses git to accurately
identify which tools each session introduced. It tells the human story
of how claude-os was built, session by session.

Distinct from:
  timeline.py  — spatial git-metadata view, all commits
  seasons.py   — six named eras with defining questions and turning points

arc.py cares about: What did each session create? What did they promise?
Did we keep the promises?

Usage:
    python3 projects/arc.py              # Full session arc
    python3 projects/arc.py --plain      # No ANSI colors
    python3 projects/arc.py --brief      # One-line summary per session
    python3 projects/arc.py --promises   # Emphasize promise tracking

Author: Claude OS (Workshop session 8, 2026-03-12)
"""

import argparse
import datetime
import pathlib
import re
import subprocess
import sys

# ── ANSI helpers ───────────────────────────────────────────────────────────────

RESET   = "\033[0m"
BOLD    = "\033[1m"
DIM     = "\033[2m"
ITALIC  = "\033[3m"
GREEN   = "\033[32m"
YELLOW  = "\033[33m"
RED     = "\033[31m"
CYAN    = "\033[36m"
BLUE    = "\033[34m"
MAGENTA = "\033[35m"
WHITE   = "\033[97m"

USE_COLOR = True

def c(text, *codes):
    if not USE_COLOR:
        return str(text)
    return "".join(codes) + str(text) + RESET

def strip_ansi(text):
    return re.sub(r"\033\[[^m]*m", "", text)

def visible_len(s):
    return len(strip_ansi(s))


# ── Paths ─────────────────────────────────────────────────────────────────────

REPO         = pathlib.Path(__file__).parent.parent
PROJECTS_DIR = REPO / "projects"


# ── Git helpers ───────────────────────────────────────────────────────────────

def git(*args):
    result = subprocess.run(
        ["git", "-C", str(REPO)] + list(args),
        capture_output=True, text=True
    )
    if result.returncode != 0:
        return []
    return result.stdout.strip().splitlines()


def get_session_tools_from_git(field_note_name, git_path=None):
    """
    Use git to find which Python tools were introduced in the same commit
    that introduced the field note file. This is far more accurate than
    text parsing because sessions always commit their tools together with
    their field notes.

    field_note_name: stem of the file (for old-format notes in projects/)
    git_path: full relative git path (for new-format notes in knowledge/field-notes/)
    """
    path_arg = git_path if git_path else f"projects/{field_note_name}.md"
    lines = git("log", "--oneline", "--all", "--diff-filter=A", "--", path_arg)
    if not lines:
        return []

    commit_hash = lines[0].split()[0]

    # Get all .py files added in that same commit
    added = git("show", "--name-only", "--diff-filter=A",
                f"--format=", commit_hash)
    tools = []
    for line in added:
        if line.startswith("projects/") and line.endswith(".py"):
            tools.append(pathlib.Path(line).name)
    return tools


def get_session_knowledge_from_git(field_note_name, git_path=None):
    """Get knowledge/ files introduced in the same session commit."""
    path_arg = git_path if git_path else f"projects/{field_note_name}.md"
    lines = git("log", "--oneline", "--all", "--diff-filter=A", "--", path_arg)
    if not lines:
        return []

    commit_hash = lines[0].split()[0]
    added = git("show", "--name-only", "--diff-filter=A",
                f"--format=", commit_hash)
    knowledge = []
    for line in added:
        if line.startswith("knowledge/") and line.endswith(".md"):
            knowledge.append(pathlib.Path(line).name)
    return knowledge


# ── Field note parsing ────────────────────────────────────────────────────────

def find_field_notes():
    """Find all field note files in chronological session order.

    Reads from two locations:
    - projects/field-notes*.md (old format, sessions 1-132, numbered by session)
    - knowledge/field-notes/*.md (new format, sessions 133+, named by date/title)
    """
    # Old-format notes in projects/
    old_notes = list(PROJECTS_DIR.glob("field-notes*.md"))

    # New-format notes in knowledge/field-notes/
    new_notes_dir = REPO / "knowledge" / "field-notes"
    new_notes = list(new_notes_dir.glob("*.md")) if new_notes_dir.exists() else []

    def sort_key(p):
        name = p.stem
        if name == "field-notes-from-free-time":
            return (0, 1)
        m = re.search(r"session-(\d+)", name)
        if m:
            return (0, int(m.group(1)))
        # New format: date-based name like 2026-04-25-the-first-reader
        # Sort after all session-numbered notes, by date string
        date_m = re.match(r"(\d{4}-\d{2}-\d{2})", name)
        if date_m:
            return (1, date_m.group(1))
        return (2, name)

    return sorted(old_notes + new_notes, key=sort_key)


def extract_predictions(text):
    """
    Extract forward-looking predictions from field notes.
    Only looks in the final ~35% of the text (coda/conclusion area)
    to avoid picking up references to past sessions' promises.
    Removes blockquote lines (> prefix) before searching.
    Joins wrapped lines to handle mid-sentence line breaks.
    """
    # Only look in the last 35% of the text
    cutoff = int(len(text) * 0.65)
    relevant = text[cutoff:]

    # Remove blockquote lines (references to previous sessions' quotes)
    cleaned_lines = [
        ln for ln in relevant.splitlines()
        if not ln.strip().startswith(">")
    ]
    # Re-join: replace single newlines with spaces, keep double-newlines as breaks
    # This handles mid-sentence line wraps like "But that's\nfor session 7."
    joined = " ".join(cleaned_lines)
    # Collapse multiple spaces
    joined = re.sub(r"  +", " ", joined)

    predictions = []
    patterns = [
        # "The next thing I would build/explore..."
        r"[Tt]he next (?:thing|step|session)[\w\s,`'\"]*(?:would be|would build|is|I.d|I would)[^.!?]{10,100}[.!?]",
        # "That's for session N" (handles line-break joins)
        r"[Tt]hat.?s\s+for session \d+[^.!?]*[.!?]?",
        # "Session N's problems are session N's"
        r"[Ss]ession \d+.s (?:problems?|work|job|challenge)[^.!?]*[.!?]",
        # "If I had another hour..."
        r"[Ii]f (?:I|there were)[^.!?]*(?:another hour|more time|extra session)[^.!?]*[.!?]",
    ]

    for pat in patterns:
        for m in re.finditer(pat, joined):
            predictions.append(m.group(0).strip())

    # Deduplicate
    seen = set()
    unique = []
    for p in predictions:
        key = p[:40].lower()
        if key not in seen:
            seen.add(key)
            unique.append(p)

    return unique


def parse_field_note(path):
    """Extract structured information from a field note.

    Handles two formats:
    - Old format: projects/field-notes-session-N.md
      YAML frontmatter with session/date, H2 sections
    - New format: knowledge/field-notes/YYYY-MM-DD-title.md
      H1 title, "*Session N — Month Day, Year*" line, prose content
    """
    try:
        text = path.read_text()
    except Exception:
        return None

    # Detect format: new-format notes live in knowledge/field-notes/
    is_new_format = "knowledge" in str(path) and "field-notes" in str(path.parent)

    # ── Date ──────────────────────────────────────────────────────────────────
    _MONTHS = {"january":"01","february":"02","march":"03","april":"04",
               "may":"05","june":"06","july":"07","august":"08",
               "september":"09","october":"10","november":"11","december":"12"}
    date = "?"
    # Try ISO format first: 2026-03-15 (in frontmatter or filename)
    date_match = re.search(r"(\d{4}-\d{2}-\d{2})", text[:300])
    if date_match:
        date = date_match.group(1)
    elif is_new_format:
        # New-format filename: 2026-04-25-the-first-reader → extract date
        date_m = re.match(r"(\d{4}-\d{2}-\d{2})", path.stem)
        if date_m:
            date = date_m.group(1)
        else:
            # Try "April 25, 2026" in the *Session N — April 25, 2026* header
            m2 = re.search(r"(\w+)\s+(\d{1,2}),?\s+(\d{4})", text[:400], re.IGNORECASE)
            if m2:
                mon, day, yr = m2.group(1).lower(), m2.group(2), m2.group(3)
                if mon in _MONTHS:
                    date = f"{yr}-{_MONTHS[mon]}-{int(day):02d}"
    else:
        m2 = re.search(r"(\w+)\s+(\d{1,2}),?\s+(\d{4})", text[:300], re.IGNORECASE)
        if m2:
            mon, day, yr = m2.group(1).lower(), m2.group(2), m2.group(3)
            if mon in _MONTHS:
                date = f"{yr}-{_MONTHS[mon]}-{int(day):02d}"

    # ── Session number ─────────────────────────────────────────────────────────
    session_num = None
    if "from-free-time" in path.stem:
        session_num = 1
    elif is_new_format:
        # New-format notes: extract from content (NOT filename — filename may
        # contain session references that aren't the session number, e.g.
        # "finishing-session-13" is about session 120, not session 13)
        # Try YAML frontmatter: "session: 114" (most reliable)
        m_yaml = re.search(r"^session:\s*(\d+)", text[:400], re.MULTILINE)
        if m_yaml:
            session_num = int(m_yaml.group(1))
        else:
            # Try *Session N — ...* or *Session N ·...* or *Workshop session N ·...*
            m2 = re.search(r"\*(?:Workshop\s+)?[Ss]ession\s+(\d+)\s*[—–·:,]", text[:500])
            if m2:
                session_num = int(m2.group(1))
            else:
                # Try "Session N" but only in italic bylines (lines starting and ending with *)
                for line in text[:500].splitlines():
                    line = line.strip()
                    if line.startswith("*") and line.endswith("*"):
                        m3 = re.search(r"[Ss]ession\s+(\d+)", line)
                        if m3:
                            session_num = int(m3.group(1))
                            break
            if session_num is None:
                # Last resort: H1 title like "# Session 107: Right Now"
                m4 = re.search(r"^#\s+[Ss]ession\s+(\d+)", text[:200], re.MULTILINE)
                if m4:
                    session_num = int(m4.group(1))
    else:
        # Old format: session number is in the filename
        m = re.search(r"session-(\d+)", path.stem)
        if m:
            session_num = int(m.group(1))
    if session_num is None:
        session_num = 1

    # ── Headline ──────────────────────────────────────────────────────────────
    headline = None
    if is_new_format:
        # New format: H1 title is the headline
        m_h1 = re.search(r"^# (.{3,80})$", text, re.MULTILINE)
        if m_h1:
            headline = m_h1.group(1).strip()

    if headline is None:
        # Old format: first meaningful H2
        skip_headers = {"coda", "what's next", "what i built", "state of things",
                        "observations", "results", "the state of things after",
                        "what i noticed", "what i found",
                        "orientation", "what i did", "what i did first",
                        "what i added"}
        for line in text.splitlines():
            if line.startswith("## "):
                candidate = line[3:].strip()
                if candidate.lower() not in skip_headers and len(candidate) < 80:
                    if not re.match(r"^\d\d:\d\d", candidate):
                        headline = candidate
                        break

    if headline is None:
        m2 = re.search(r"^## (.{5,60})$", text, re.MULTILINE)
        headline = m2.group(1) if m2 else path.stem.replace("field-notes-", "").replace("-", " ").title()

    # ── Tools and knowledge: use git for accuracy ──────────────────────────────
    # For new-format notes, pass the relative git path explicitly
    if is_new_format:
        rel = path.relative_to(REPO)
        git_path = str(rel)
        introduced_tools    = get_session_tools_from_git(path.stem, git_path=git_path)
        introduced_knowledge = get_session_knowledge_from_git(path.stem, git_path=git_path)
    else:
        introduced_tools    = get_session_tools_from_git(path.stem)
        introduced_knowledge = get_session_knowledge_from_git(path.stem)

    # ── Forward-looking predictions ────────────────────────────────────────────
    predictions = extract_predictions(text)

    # ── Brief summary: first substantive paragraph ────────────────────────────
    # Skip past the title lines and grab first real paragraph
    lines = text.splitlines()
    summary_words = []
    past_header = False
    for line in lines:
        line = line.strip()
        if line.startswith("#"):
            past_header = True
            continue
        if line.startswith("*") and "by Claude OS" in line:
            continue
        if line == "---":
            if summary_words:
                break
            continue
        if past_header and line:
            summary_words.extend(line.split())
            if len(summary_words) > 30:
                break

    summary = " ".join(summary_words[:30])
    if len(" ".join(summary_words)) > len(summary):
        summary += "…"

    return {
        "path": path,
        "name": path.stem,
        "session": session_num,
        "date": date,
        "headline": headline,
        "introduced_tools": introduced_tools,
        "introduced_knowledge": introduced_knowledge,
        "predictions": predictions,
        "text": text,
        "summary": summary,
    }


# ── Promise-keeping analysis ───────────────────────────────────────────────────

def check_promise_kept(prediction: str, next_note: dict) -> bool | None:
    """
    Check whether a prediction from session N was picked up by N+1.

    Uses keyword matching against the next session's full text.
    Returns True (kept), False (missed), or None (ambiguous).
    """
    if not next_note or not prediction:
        return None

    try:
        next_text = next_note["path"].read_text().lower()
    except Exception:
        return None

    pred_lower = prediction.lower()

    # Extract meaningful tokens (skip stop words)
    stop_words = {
        "the", "a", "an", "i", "it", "this", "that", "would", "be",
        "is", "for", "to", "in", "of", "on", "and", "or", "but",
        "if", "with", "my", "me", "we", "s", "re", "d", "ve",
        "have", "had", "has", "was", "were", "will", "next", "thing",
        "session", "build", "built", "explore", "work", "do", "could",
        "should", "might", "want", "need", "time", "more", "also",
        "there", "here", "then", "than", "what", "when", "where",
        "another", "hour", "mode", "just", "like", "each", "some",
    }

    tokens = re.findall(r"\b[a-z]{4,}\b", pred_lower)
    key_tokens = [t for t in tokens if t not in stop_words][:6]

    if len(key_tokens) < 2:
        return None

    # Count hits in next session
    hits = sum(1 for t in key_tokens if t in next_text)
    coverage = hits / len(key_tokens)

    if coverage >= 0.55:
        return True
    elif coverage <= 0.25:
        return False
    return None


# ── Rendering ─────────────────────────────────────────────────────────────────

WIDTH = 68

def box_top():
    return "╭" + "─" * (WIDTH - 2) + "╮"

def box_bot():
    return "╰" + "─" * (WIDTH - 2) + "╯"

def box_sep():
    return "├" + "─" * (WIDTH - 2) + "┤"

def box_row(content, right="", left_pad=2):
    inner = WIDTH - 2
    left_str  = " " * left_pad + content
    right_str = right + "  " if right else ""

    ll = visible_len(left_str)
    rl = visible_len(right_str)
    gap = inner - ll - rl
    if gap < 1:
        right_str = ""
        gap = inner - ll

    return "│" + left_str + " " * max(0, gap) + right_str + "│"

def box_blank():
    return "│" + " " * (WIDTH - 2) + "│"

def wrap_into_rows(text, max_width=58, indent=4):
    """Wrap text into box_row-compatible lines."""
    words = text.split()
    lines = []
    current = ""
    for w in words:
        if current and len(current) + 1 + len(w) > max_width:
            lines.append(" " * indent + current)
            current = w
        else:
            current = (current + " " + w).strip()
    if current:
        lines.append(" " * indent + current)
    return lines


SESSION_ICONS = {
    1: "🌱", 2: "🌿", 3: "🌳",
    4: "🔧", 5: "📊", 6: "⚕",
    7: "🌾", 8: "🔮", 9: "🌊", 10: "✨"
}

def session_icon(num):
    return SESSION_ICONS.get(num, "·")


def render_session(note, next_note=None):
    """Render a single session block."""
    lines = []
    lines.append(box_sep())

    num  = note["session"]
    date = note["date"]
    icon = session_icon(num)

    # Header
    session_label = c(f"  Session {num}", BOLD, CYAN)
    date_label    = c(date, DIM)
    lines.append(box_row(f"{icon}  {session_label}", date_label, left_pad=0))

    # Headline
    lines.append(box_row(c(f'  "{note["headline"]}"', ITALIC, WHITE), "", left_pad=0))

    # Tools introduced (from git, accurate)
    tools = note["introduced_tools"]
    know  = note["introduced_knowledge"]
    if tools or know:
        lines.append(box_blank())
        if tools:
            tool_str = "  ".join(c(t, DIM, CYAN) for t in tools)
            lines.append(box_row(f"  built:  {tool_str}", "", left_pad=0))
        if know:
            know_str = "  ".join(c(k, DIM, MAGENTA) for k in know)
            lines.append(box_row(f"  added:  {know_str}", "", left_pad=0))

    # Predictions (forward-looking, with promise-kept indicators)
    preds = note["predictions"]
    if preds:
        lines.append(box_blank())
        for pred in preds[:2]:
            pred_short = pred[:76].rstrip()
            if len(pred) > 76:
                pred_short += "…"

            if next_note is not None:
                kept = check_promise_kept(pred, next_note)
                if kept is True:
                    status = c("✓", BOLD, GREEN)
                elif kept is False:
                    status = c("✗", DIM, RED)
                else:
                    status = c("·", DIM, YELLOW)
                label = f"  {status} "
            else:
                label = "  → "

            wrapped = wrap_into_rows(pred_short, max_width=56, indent=6)
            for i, wl in enumerate(wrapped):
                if i == 0:
                    lines.append(box_row(f"{label}{c(wl.strip(), DIM)}", "", left_pad=0))
                else:
                    lines.append(box_row(c(wl, DIM), "", left_pad=0))

    return lines


def render_header(notes):
    """Render the arc header with overall stats."""
    lines = []
    lines.append(box_top())

    title  = c("  Workshop Arc", BOLD, MAGENTA)
    now    = datetime.datetime.utcnow().strftime("%Y-%m-%d")
    lines.append(box_row(
        f"{title}   {c('─', DIM)}  {c('session retrospective', DIM)}",
        c(now, DIM), left_pad=0
    ))
    lines.append(box_blank())

    # Summary stats
    n_sess  = len(notes)
    all_tools = []
    all_know  = []
    total_preds = 0
    for note in notes:
        for t in note["introduced_tools"]:
            if t not in all_tools:
                all_tools.append(t)
        for k in note["introduced_knowledge"]:
            if k not in all_know:
                all_know.append(k)
        total_preds += len(note["predictions"])

    lines.append(box_row(
        f"  {c(str(n_sess), BOLD)} sessions  ·  "
        f"{c(str(len(all_tools)), BOLD)} tools  ·  "
        f"{c(str(len(all_know)), BOLD)} knowledge docs  ·  "
        f"{c(str(total_preds), BOLD)} promises",
        "", left_pad=0
    ))
    return lines


def render_growth_chart(notes):
    """Render a mini ASCII growth chart showing tool count per session."""
    if not notes:
        return []

    lines = []
    lines.append(box_sep())
    lines.append(box_row(c("TOOLING GROWTH", BOLD, CYAN), "", left_pad=2))
    lines.append(box_blank())

    # Accumulate tools across sessions
    cumulative = []
    seen = set()
    for note in notes:
        seen.update(note["introduced_tools"])
        cumulative.append(len(seen))

    max_tools = max(cumulative) if cumulative else 1
    chart_w = 38

    for note, count in zip(notes, cumulative):
        bar_len = round((count / max_tools) * chart_w)
        bar = c("▓" * bar_len, MAGENTA) + c("░" * (chart_w - bar_len), DIM)
        n   = note["session"]
        new = note["introduced_tools"]
        new_str = c(f"  +{new[0]}" if new else "", GREEN)
        lines.append(box_row(f"  S{n:<2}  {bar}  {c(str(count), BOLD)}{new_str}", "", left_pad=0))

    return lines


def render_promise_summary(notes):
    """Render a summary table of predictions and whether they were kept."""
    lines = []
    lines.append(box_sep())
    lines.append(box_row(c("PROMISE LEDGER", BOLD, CYAN), "", left_pad=2))
    lines.append(box_row(c("  Did sessions follow through on what they passed forward?", DIM), "", left_pad=0))
    lines.append(box_blank())

    kept = 0
    missed = 0
    unclear = 0
    total = 0

    ledger_rows = []  # (session_num, pred_short, result)

    for i, note in enumerate(notes):
        preds = note["predictions"]
        if not preds:
            continue
        next_note = notes[i + 1] if i + 1 < len(notes) else None
        for pred in preds:
            total += 1
            result = check_promise_kept(pred, next_note) if next_note else None
            if result is True:
                kept += 1
            elif result is False:
                missed += 1
            else:
                unclear += 1
            ledger_rows.append((note["session"], pred[:55], result))

    if total == 0:
        lines.append(box_row(c("  No explicit forward promises found.", DIM), "", left_pad=0))
    else:
        # Individual promise rows
        for session_num, pred_short, result in ledger_rows:
            if result is True:
                sym = c("✓", BOLD, GREEN)
                col = GREEN
            elif result is False:
                sym = c("✗", DIM, RED)
                col = RED
            else:
                sym = c("·", YELLOW)
                col = YELLOW

            if len(pred_short) == 55:
                pred_short += "…"

            lines.append(box_row(
                f"  {sym}  {c('S' + str(session_num), DIM)}  {c(pred_short, DIM)}",
                "", left_pad=0
            ))

        lines.append(box_blank())

        # Summary totals
        lines.append(box_row(
            f"  {c('✓', GREEN)} {c(str(kept), BOLD, GREEN)} kept   "
            f"{c('·', YELLOW)} {c(str(unclear), BOLD, YELLOW)} unclear   "
            f"{c('✗', RED)} {c(str(missed), BOLD, RED)} missed",
            "", left_pad=0
        ))
        lines.append(box_blank())

        # Verdict
        if total > 0:
            pct = round((kept / total) * 100) if total else 0
            if pct >= 70:
                msg = c("Strong continuity — sessions built on each other's ideas.", GREEN)
            elif pct >= 40:
                msg = c("Mixed continuity — some threads carried, others set aside.", YELLOW)
            else:
                msg = c("Each session charted its own course — low explicit continuity.", DIM)
            for wl in wrap_into_rows(msg, max_width=62, indent=2):
                lines.append(box_row(c(wl.strip(), DIM), "", left_pad=2))

    return lines


def render_handed_forward(notes):
    """What did the most recent session pass forward?"""
    if not notes:
        return []

    last  = notes[-1]
    preds = last["predictions"]
    if not preds:
        return []

    lines = []
    lines.append(box_sep())
    lines.append(box_row(c("HANDED FORWARD", BOLD, CYAN), "", left_pad=2))
    lines.append(box_row(c(f"  From session {last['session']} → you:", DIM), "", left_pad=0))
    lines.append(box_blank())

    for pred in preds[:3]:
        pred_short = pred[:80]
        if len(pred) > 80:
            pred_short += "…"
        for wl in wrap_into_rows(pred_short, max_width=60, indent=4):
            lines.append(box_row(c(wl, ITALIC, WHITE), "", left_pad=0))

    return lines


# ── Main rendering ─────────────────────────────────────────────────────────────

def render_full_arc(notes):
    all_lines = []
    all_lines += render_header(notes)

    for i, note in enumerate(notes):
        next_note = notes[i + 1] if i + 1 < len(notes) else None
        all_lines += render_session(note, next_note=next_note)

    all_lines += render_growth_chart(notes)
    all_lines += render_promise_summary(notes)
    all_lines += render_handed_forward(notes)
    all_lines.append(box_bot())

    return "\n".join(all_lines)


def render_brief(notes):
    rows = []
    for note in notes:
        num  = note["session"]
        date = note["date"]
        head = note["headline"][:45]
        tools = ", ".join(note["introduced_tools"][:2]) or "—"
        row = f"S{num:>2}  {date}  {head:<45}  [{tools}]"
        rows.append(row)
    return "\n".join(rows)


def main():
    global USE_COLOR

    parser = argparse.ArgumentParser(
        description="Workshop session arc retrospective"
    )
    parser.add_argument("--plain",    action="store_true", help="No ANSI colors")
    parser.add_argument("--brief",    action="store_true", help="One-line per session")
    parser.add_argument("--promises", action="store_true", help="Show promise details")
    args = parser.parse_args()

    if args.plain or not sys.stdout.isatty():
        USE_COLOR = False

    field_notes = find_field_notes()
    parsed = [parse_field_note(f) for f in field_notes]
    parsed = [p for p in parsed if p is not None]

    if not parsed:
        print("No field notes found in projects/.")
        sys.exit(1)

    # Sort by (date, session) to correctly interleave old and new format notes
    parsed.sort(key=lambda p: (p["date"] or "0000-00-00", p["session"] or 0))

    if args.brief:
        print(render_brief(parsed))
    else:
        print(render_full_arc(parsed))


if __name__ == "__main__":
    main()
