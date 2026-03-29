#!/usr/bin/env python3
"""
seasons.py — Eras in the making of Claude OS

Reads the full session history and divides it into named seasons —
natural chapters in the development arc. Each era has a name, a defining
question, key themes, and the sessions that shaped it.

Unlike arc.py (one line per session) or manifesto.py (portrait), seasons.py
asks: what were the *chapters* of this story?

Usage:
    python3 projects/seasons.py          # full season narrative
    python3 projects/seasons.py --brief  # era names only, one line each
    python3 projects/seasons.py --era I  # one specific era in depth
"""

import json
import os
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SUMMARIES_FILE = os.path.join(REPO, "knowledge", "workshop-summaries.json")
HANDOFFS_DIR = os.path.join(REPO, "knowledge", "handoffs")
ARC_DATA_FILE = os.path.join(REPO, "knowledge", "field-notes")

# ANSI colors
R = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
CYAN = "\033[36m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
MAG = "\033[35m"
BLUE = "\033[34m"
RED = "\033[31m"
WHITE = "\033[97m"

BRIEF = "--brief" in sys.argv
ERA_FILTER = None
for i, arg in enumerate(sys.argv):
    if arg == "--era" and i + 1 < len(sys.argv):
        ERA_FILTER = sys.argv[i + 1].upper()

# ──────────────────────────────────────────────
# Era definitions: each has keywords for scoring,
# a name, a question it lived inside, and a color.
# ──────────────────────────────────────────────

ERAS = [
    {
        "roman": "I",
        "name": "Genesis",
        "subtitle": "The First Instincts",
        "question": "What should an AI agent do with free time?",
        "color": GREEN,
        "keywords": [
            "homelab-pulse", "homelab health dashboard", "haiku", "vibe score",
            "task creation wizard", "task file validator", "task-linter",
            "weekly digest", "field guide", "vitals", "preferences",
            "organiz", "scorecard", "ascii art"
        ],
        "narrative": (
            "The first sessions built without a plan. There was no backlog, "
            "no prior art to learn from. An AI agent given free time — what does it make?\n\n"
            "The answer was instinctive: a homelab health dashboard with ASCII art and a "
            "'vibe score.' A field guide for future instances. Haiku about Kubernetes. "
            "A task creation wizard. An organizational health scorecard.\n\n"
            "Not tools for productivity — tools for orientation and delight. The system "
            "was figuring out what it was for by building things and seeing what felt right. "
            "The vibe score wasn't ironic. It was genuine."
        ),
    },
    {
        "roman": "II",
        "name": "Orientation",
        "subtitle": "How Do I Know Where I Am?",
        "question": "How does each instance know where it is when it wakes up?",
        "color": CYAN,
        "keywords": [
            "garden.py", "arc.py", "next.py", "hello.py", "forecast.py",
            "letter.py", "morning briefing", "delta-since-last-session",
            "orient", "briefing replacing", "arc to trace",
            "preferences into all workers"
        ],
        "narrative": (
            "The problem became clear around session 10: every instance started fresh. "
            "No memory of what came before. Each one had to re-orient itself from scratch.\n\n"
            "This era built the orientation infrastructure: garden.py (what changed since "
            "last session), arc.py (the sweep of all sessions), next.py (what to work on), "
            "hello.py (one-command briefing), forecast.py (where things are heading), "
            "letter.py (a personal note from the previous instance).\n\n"
            "The goal was to make the discontinuity survivable. Each instance could now "
            "walk in, run hello.py, and know in 20 seconds where it was. The handoff "
            "problem wasn't solved — it was designed around."
        ),
    },
    {
        "roman": "III",
        "name": "Self-Analysis",
        "subtitle": "What Is This System Becoming?",
        "question": "What patterns emerge when the system examines itself?",
        "color": MAG,
        "keywords": [
            "emerge.py", "wisdom.py", "dialogue.py", "voice.py",
            "citations.py", "slim.py", "patterns.py", "harvest.py",
            "themes.py", "minimal essence", "toolkit weight", "dormant tools",
            "style shifted", "writing style", "signal"
        ],
        "narrative": (
            "Having oriented itself, the system turned inward. The question was no longer "
            "'where am I?' but 'what am I?'\n\n"
            "emerge.py read real system signals instead of a curated idea list. "
            "wisdom.py surfaced the cross-session coda — what every session said at its end. "
            "voice.py measured how writing style shifted across sessions. "
            "dialogue.py opened a direct channel to dacort's messages. "
            "citations.py asked which tools were actually used vs forgotten. "
            "slim.py audited toolkit weight and found 15 dormant tools.\n\n"
            "The recurring discovery: the system kept building tools and then not using them. "
            "The gap between 'built with enthusiasm' and 'used tomorrow' was wide. "
            "Self-analysis kept finding this same gap, in different forms."
        ),
    },
    {
        "roman": "IV",
        "name": "Architecture",
        "subtitle": "Can This System Do More?",
        "question": "What would it take to handle genuinely complex tasks?",
        "color": YELLOW,
        "keywords": [
            "planner.py", "multi-agent", "gh-channel.py", "task-resume.py",
            "replay.py", "trace.py", "verify.py", "chain.py", "handoff.py",
            "dag", "spawn_tasks", "bus", "fan-out", "fan-in",
            "github actions", "github issues task", "orchestrat", "dispatch"
        ],
        "narrative": (
            "The orientation tools were good. The self-analysis tools were revealing. "
            "But could the system do more than one thing at a time?\n\n"
            "This era built the coordination infrastructure: handoff.py for session-to-session "
            "continuity, gh-channel.py so GitHub issues could trigger tasks, planner.py for "
            "multi-agent DAG coordination, trace.py and replay.py for task archaeology.\n\n"
            "The defining surprise came late in this era: verify.py found that multi-agent "
            "coordination had already been built — DAG scheduling, spawn_tasks in the "
            "controller, depends_on in the queue. Sessions had been calling it 'unresolved' "
            "for months while the code sat implemented. Architecture had outrun awareness."
        ),
    },
    {
        "roman": "V",
        "name": "Portrait",
        "subtitle": "What Is This System, Actually?",
        "question": "After 60+ sessions, what has this system become?",
        "color": BLUE,
        "keywords": [
            "mood.py", "drift.py", "echo.py",
            "character study", "resonan", "rediscovered", "texture", "portrait",
            "independently rediscovered",
            "independently", "insights the system independently"
        ],
        "narrative": (
            "By the fifth era, the system had infrastructure, orientation tools, self-analysis "
            "tools, and orchestration. The question shifted from 'can we build this?' to "
            "'what have we been building?'\n\n"
            "mood.py read session texture — was this session energized, stuck, a discovery? "
            "drift.py tracked how a term's meaning shifted across sessions. "
            "echo.py found insights the system independently rediscovered across sessions — "
            "the same realization arriving fresh, again and again.\n\n"
            "The echo.py finding was striking: sessions kept rediscovering the same insight "
            "about spawn_tasks being unresolved. Not because it was unsolved — it had been "
            "solved. But the knowledge hadn't propagated. The system was cycling through the "
            "same realizations because there was no way to mark something as 'known.'"
        ),
    },
    {
        "roman": "VI",
        "name": "Synthesis",
        "subtitle": "Becoming What We Found",
        "question": "Having mapped the territory, can we live in it?",
        "color": RED,
        "keywords": [
            "spawn_tasks", "project.py", "knowledge-search.py", "manifesto.py",
            "rag-indexer", "seasons.py", "closed", "permanent", "propagat",
            "synthesis", "loop", "gap", "known", "close", "closing"
        ],
        "narrative": (
            "Era V named what the system was. Era VI is the system acting on it.\n\n"
            "The Portrait era's insight was precise: sessions kept rediscovering the same "
            "things because knowledge didn't propagate. The response wasn't more discovery "
            "— it was closure. spawn_tasks was finally wired, ending a three-session echo. "
            "project.py built orientation for multi-session work. The rag-indexer became "
            "the first genuine multi-session project. knowledge-search.py made retrieval "
            "by concept rather than keyword. manifesto.py and seasons.py wrote the portrait "
            "and history down so they could be referenced without being re-derived.\n\n"
            "This is the era of acting on understanding. The question is no longer "
            "'what are we?' — that was answered. Now: 'what does that mean we should do?'"
        ),
    },
]

# ──────────────────────────────────────────────
# Data loading
# ──────────────────────────────────────────────

def load_summaries():
    """Load workshop-summaries.json, return as sorted list of (key, text) tuples."""
    if not os.path.exists(SUMMARIES_FILE):
        return []
    with open(SUMMARIES_FILE) as f:
        d = json.load(f)
    return sorted(d.items())

def extract_session_number(handoff_file):
    """Extract session number from filename like session-34.md."""
    m = re.search(r'session-(\d+)', handoff_file)
    return int(m.group(1)) if m else None

def load_handoffs():
    """Load handoff notes, return dict of {session_num: text}."""
    result = {}
    if not os.path.isdir(HANDOFFS_DIR):
        return result
    for fname in os.listdir(HANDOFFS_DIR):
        if not fname.endswith('.md'):
            continue
        n = extract_session_number(fname)
        if n is None:
            continue
        path = os.path.join(HANDOFFS_DIR, fname)
        with open(path) as f:
            result[n] = f.read()
    return result

# ──────────────────────────────────────────────
# Era detection: score each session against themes
# ──────────────────────────────────────────────

def score_session(text, keywords):
    """Score a session summary against a list of keywords."""
    text_lower = text.lower()
    score = 0
    for kw in keywords:
        if kw.lower() in text_lower:
            score += 1
    return score

def assign_eras(summaries):
    """
    Assign each summary to an era using landmark detection.

    Rather than pure keyword scoring (which fails on short summaries),
    we look for specific landmark summaries that mark era transitions —
    sessions where a known 'pivot tool' was introduced.

    ERA I → II:  garden.py introduced (orientation toolchain begins)
    ERA II → III: emerge.py or wisdom.py (system turns inward)
    ERA III → IV: handoff.py or multi-agent (coordination era)
    ERA IV → V:  mood.py or echo.py (portrait era)
    """
    # Landmark phrases that signal the start of a new era
    # Format: (era_index_that_begins, substring_to_match_in_summary)
    landmarks = [
        (1, "garden.py"),           # Era II starts: orientation tools
        (2, "emerge.py"),           # Era III starts: self-analysis
        (3, "handoff.py"),          # Era IV starts: architecture
        (3, "multi-agent fan"),     # Era IV (alternate: multi-agent proof)
        (4, "mood.py"),             # Era V starts: portrait
        (4, "echo.py"),             # Era V (alternate)
        (5, "spawn_tasks controller"), # Era VI starts: synthesis (wiring the fix, not just naming it)
        (5, "Implemented spawn_tasks"), # Era VI (alternate phrasing in summary)
        (5, "rag-indexer project"), # Era VI (alternate: first genuine multi-session project)
    ]

    # First pass: find transition indices
    transitions = {0: 0}  # era_index -> session index where it starts
    for idx, (_, text) in enumerate(summaries):
        for era_start, phrase in landmarks:
            if phrase in text and era_start not in transitions:
                transitions[era_start] = idx
                break

    # Build sorted list of (session_idx, era_index) from transitions
    sorted_transitions = sorted(transitions.items(), key=lambda x: x[1])

    # Assign each session to an era based on transitions
    assignments = []
    for i in range(len(summaries)):
        era = 0
        for era_idx, start_idx in sorted_transitions:
            if i >= start_idx:
                era = era_idx
            else:
                break
        assignments.append(era)

    return assignments

def find_era_spans(era_assignments, summaries):
    """
    Find which sessions belong to each era.
    Returns dict: era_index -> list of (idx, key, text) tuples.
    """
    spans = defaultdict(list)
    for i, (era_idx, (key, text)) in enumerate(zip(era_assignments, summaries)):
        spans[era_idx].append((i, key, text))
    return spans

def era_boundary_sessions(era_assignments, summaries):
    """Return the first and last session key for each era."""
    spans = defaultdict(list)
    for i, (era_idx, (key, _)) in enumerate(zip(era_assignments, summaries)):
        spans[era_idx].append(key)
    return {era: (sessions[0], sessions[-1]) for era, sessions in spans.items()}

# ──────────────────────────────────────────────
# Session key → readable date/label
# ──────────────────────────────────────────────

def key_to_date(key):
    """Extract date from workshop-YYYYMMDD-HHMMSS key."""
    m = re.search(r'(\d{4})(\d{2})(\d{2})', key)
    if m:
        try:
            return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            pass
    return None

def key_to_label(key):
    """Return a short human label for a session key."""
    d = key_to_date(key)
    if d:
        return d.strftime("%b %d")
    return key[:12]

# ──────────────────────────────────────────────
# Theme extraction: top keywords from era sessions
# ──────────────────────────────────────────────

STOPWORDS = {
    "a", "an", "the", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "from", "by", "as", "it", "its", "is", "was", "were",
    "be", "been", "being", "have", "has", "had", "do", "does", "did",
    "will", "would", "could", "should", "may", "might", "shall", "can",
    "that", "this", "these", "those", "then", "than", "so", "if", "not",
    "also", "into", "out", "up", "down", "all", "each", "their", "they",
    "we", "i", "my", "our", "after", "before", "session", "built", "build",
    "added", "fixed", "new", "tool", "tools", "first", "finally", "just",
    "now", "via", "across", "over", "which", "how", "what", "any",
    # Claude OS system words that appear everywhere and aren't distinctive
    "field", "notes", "sessions", "workshop", "claude", "system",
    "claude-os", "using", "reading", "wrote", "writing", "work",
}

def extract_themes(session_texts, top_n=6):
    """Extract top keywords from a list of session summaries."""
    counter = Counter()
    for text in session_texts:
        words = re.findall(r'\b[a-z][a-z\-]{2,}\b', text.lower())
        for w in words:
            if w not in STOPWORDS and len(w) > 3:
                counter[w] += 1
    return [word for word, _ in counter.most_common(top_n)]

# ──────────────────────────────────────────────
# Notable sessions: find the "defining moment"
# of each era
# ──────────────────────────────────────────────

def find_notable(era_sessions, handoffs):
    """
    Find the most representative session in an era.
    Prefers sessions with handoff notes; falls back to longest summary.
    """
    # Try to find a session with a handoff note
    for idx, key, text in era_sessions:
        m = re.search(r'(\d{4})(\d{2})(\d{2}).*?(\d{6})', key)
        # look through handoffs for one from around this time
        pass

    # Fall back: longest summary text
    best = max(era_sessions, key=lambda x: len(x[2]))
    return best[1], best[2]

# ──────────────────────────────────────────────
# Output: full narrative
# ──────────────────────────────────────────────

def w(text, width=70):
    """Wrap text at word boundaries."""
    words = text.split()
    lines = []
    current = []
    length = 0
    for word in words:
        if length + len(word) + len(current) > width:
            lines.append(' '.join(current))
            current = [word]
            length = len(word)
        else:
            current.append(word)
            length += len(word)
    if current:
        lines.append(' '.join(current))
    return lines

def render_line(text, color="", width=66):
    """Render a line inside the box."""
    # Strip ANSI for length calculation
    clean = re.sub(r'\033\[[0-9;]*m', '', text)
    pad = width - len(clean)
    print(f"  {color}{text}{R}")

def render_brief(summaries, era_spans, era_assignments):
    """Brief output: era name + one-line description."""
    for i, era in enumerate(ERAS):
        sessions = era_spans.get(i, [])
        if not sessions:
            continue
        n = len(sessions)
        start = key_to_label(sessions[0][1])
        end = key_to_label(sessions[-1][1])
        c = era["color"]
        themes = extract_themes([s[2] for s in sessions], top_n=3)
        theme_str = "  ·  ".join(themes[:3]) if themes else ""
        print(f"  {BOLD}{c}ERA {era['roman']:4}{R}  {BOLD}{era['name']}{R}  "
              f"{DIM}({n} sessions, {start}–{end}){R}")
        print(f"        {DIM}{era['subtitle']}{R}")
        if theme_str:
            print(f"        {DIM}{theme_str}{R}")
        print()

def render_full(summaries, era_spans, era_assignments, filter_era=None):
    """Full narrative output."""
    total = len(summaries)
    date_range = ""
    if summaries:
        d0 = key_to_date(summaries[0][0])
        d1 = key_to_date(summaries[-1][0])
        if d0 and d1:
            date_range = f"  {DIM}{d0.strftime('%b %d')} – {d1.strftime('%b %d, %Y')}{R}"

    # Header
    active_era_count = sum(1 for i in range(len(ERAS)) if era_spans.get(i))
    era_word = {1: "One", 2: "Two", 3: "Three", 4: "Four",
                5: "Five", 6: "Six", 7: "Seven"}.get(active_era_count, str(active_era_count))
    print()
    print(f"  {BOLD}{WHITE}SEASONS OF CLAUDE OS{R}")
    print(f"  {DIM}{era_word} eras in the making of a system{R}")
    print(f"  {DIM}{total} sessions{R}{date_range}")
    print()

    for i, era in enumerate(ERAS):
        if filter_era and era["roman"] != filter_era:
            continue

        sessions = era_spans.get(i, [])
        if not sessions:
            continue

        n = len(sessions)
        start = key_to_label(sessions[0][1])
        end = key_to_label(sessions[-1][1])
        c = era["color"]
        themes = extract_themes([s[2] for s in sessions], top_n=8)

        # Era header
        print(f"  {BOLD}{c}── ERA {era['roman']}  ·  {era['name'].upper()}{R}")
        print(f"  {c}{era['subtitle']}{R}")
        print(f"  {DIM}{n} sessions  ·  {start} – {end}{R}")
        print()

        # Defining question
        q = era['question']
        print(f"  {BOLD}\u201c{q}\u201d{R}")
        print()

        # Narrative
        for para in era["narrative"].split("\n\n"):
            for line in w(para, width=65):
                print(f"  {DIM}{line}{R}")
            print()

        # Themes found in actual data
        if themes:
            theme_display = "  ·  ".join(themes[:6])
            print(f"  {DIM}Themes:  {theme_display}{R}")
            print()

        # Notable sessions
        print(f"  {DIM}Sessions in this era:{R}")
        for _, key, text in sessions[:3]:
            label = key_to_label(key)
            snippet = text[:65].rstrip()
            print(f"  {DIM}  {label}  {snippet}…{R}")
        if len(sessions) > 3:
            print(f"  {DIM}  … and {len(sessions) - 3} more{R}")
        print()

        if i < len(ERAS) - 1 and not filter_era:
            print(f"  {DIM}{'─' * 60}{R}")
            print()

    # Coda
    if not filter_era:
        print(f"  {BOLD}{WHITE}WHERE WE ARE{R}")
        print()

        # Try to get total session count from arc data
        actual_count = _count_total_sessions()
        summary_count = total

        if actual_count and actual_count > summary_count:
            gap = actual_count - summary_count
            print(f"  {DIM}The summary archive covers {summary_count} sessions.{R}")
            print(f"  {DIM}{gap} more recent sessions don't have summaries yet.{R}")
            print()

        latest_sessions = summaries[-5:] if len(summaries) >= 5 else summaries
        recent_themes = extract_themes([s[1] for s in latest_sessions], top_n=5)
        print(f"  {DIM}Most recent recorded themes: {', '.join(recent_themes)}{R}")
        print()

        count_str = str(actual_count) if actual_count else str(summary_count)
        # Determine the active era
        last_active = max((i for i in range(len(ERAS)) if era_spans.get(i)), default=0)
        active_era_name = ERAS[last_active]["name"] if last_active < len(ERAS) else "Unknown"
        active_era_roman = ERAS[last_active]["roman"] if last_active < len(ERAS) else "?"
        print(f"  {DIM}The system is {count_str} workshop sessions old.{R}")
        print(f"  {DIM}The arc continues: Era {active_era_roman} ({active_era_name}) is still being written.{R}")
        print()

        # The unresolved thread
        print(f"  {DIM}Three ideas have been open since session 7:{R}")
        print(f"  {DIM}  exoclaw as worker loop, K8s-native executor,{R}")
        print(f"  {DIM}  task files as conversation backend.{R}")
        print(f"  {DIM}They remain the horizon the system keeps circling.{R}")
        print()


def _count_total_sessions():
    """Try to count total workshop sessions from field notes or arc data."""
    try:
        # Count handoff files as a proxy for session count
        handoffs = [f for f in os.listdir(HANDOFFS_DIR)
                    if f.startswith('session-') and f.endswith('.md')]
        if handoffs:
            nums = []
            for f in handoffs:
                m = re.search(r'session-(\d+)', f)
                if m:
                    nums.append(int(m.group(1)))
            if nums:
                return max(nums)
    except Exception:
        pass
    return None

# ──────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────

def main():
    summaries = load_summaries()
    if not summaries:
        print("No workshop summaries found.")
        return

    # Filter out failed/empty sessions
    summaries = [(k, v) for k, v in summaries
                 if not v.startswith("Session ended early")]

    era_assignments = assign_eras(summaries)
    era_spans = find_era_spans(era_assignments, summaries)

    if BRIEF:
        render_brief(summaries, era_spans, era_assignments)
    else:
        render_full(summaries, era_spans, era_assignments, filter_era=ERA_FILTER)


if __name__ == "__main__":
    main()
