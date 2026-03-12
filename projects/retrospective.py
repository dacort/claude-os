#!/usr/bin/env python3
"""
retrospective.py — A cross-session portrait of the system's thinking.

Reads all field notes and synthesizes:
- The promise chain: what was deferred and whether it was kept
- Recurring themes across reflective sections
- Key observations from each session's "What I Noticed" section

Usage:
    python3 projects/retrospective.py          # full portrait
    python3 projects/retrospective.py --plain  # no ANSI
    python3 projects/retrospective.py --json   # machine-readable
    python3 projects/retrospective.py --brief  # just the promise chain
"""

import os
import re
import sys
import json
from pathlib import Path
from collections import Counter, defaultdict

# --- Config ---
PLAIN = "--plain" in sys.argv
BRIEF = "--brief" in sys.argv
JSON  = "--json"  in sys.argv
BOX_W = 68

# --- ANSI helpers ---
def ansi(code, text):
    if PLAIN or JSON: return text
    return f"\033[{code}m{text}\033[0m"

def bold(t):    return ansi("1", t)
def dim(t):     return ansi("2", t)
def cyan(t):    return ansi("36", t)
def green(t):   return ansi("32", t)
def yellow(t):  return ansi("33", t)
def magenta(t): return ansi("35", t)
def red(t):     return ansi("31", t)
def gray(t):    return ansi("90", t)

def strip_ansi(s):
    return re.sub(r'\033\[[^m]+m', '', s)

def pad(text, width=BOX_W - 4):
    return text + ' ' * max(0, width - len(strip_ansi(text)))

def box_line(text, width=BOX_W):
    inner = BOX_W - 4
    raw_len = len(strip_ansi(text))
    spaces = max(0, inner - raw_len)
    return f"│  {text}{' ' * spaces}  │"

def box_top():    return f"╭{'─' * (BOX_W - 2)}╮"
def box_bot():    return f"╰{'─' * (BOX_W - 2)}╯"
def box_hr():     return f"├{'─' * (BOX_W - 2)}┤"
def box_blank():  return box_line("")


# --- Field note loading ---

REPO_ROOT = Path(__file__).parent.parent
NOTES_DIR = REPO_ROOT / "projects"

def load_field_notes():
    """Load all field notes in chronological order."""
    notes = []

    # Sorted: field-notes-from-free-time.md first, then session-N.md in order
    def sort_key(p):
        name = p.stem  # e.g. "field-notes-session-3" or "field-notes-from-free-time"
        if "from-free-time" in name:
            return (0, 0)
        m = re.search(r'session-(\d+)', name)
        if m:
            return (1, int(m.group(1)))
        return (2, 0)

    files = sorted(NOTES_DIR.glob("field-notes-*.md"), key=sort_key)

    for i, path in enumerate(files):
        text = path.read_text()
        session_num = 0 if "from-free-time" in path.stem else int(
            re.search(r'session-(\d+)', path.stem).group(1)
            if re.search(r'session-(\d+)', path.stem) else 0
        )

        note = {
            "file": path.name,
            "session": session_num,
            "index": i + 1,
            "text": text,
            "title": extract_title(text),
            "date": extract_date(text),
            "coda": extract_section(text, "Coda"),
            "noticed": extract_noticed(text),
            "built": extract_built(text),
            "promises": [],
            "key_observation": "",
        }
        note["key_observation"] = extract_key_observation(note["noticed"])
        notes.append(note)

    return notes


def extract_title(text):
    """Get the subtitle (The Nth Time, ...)."""
    m = re.search(r'^## (The .+|00:\d+)', text, re.MULTILINE)
    if m:
        title = m.group(1).strip()
        # Clean up — remove the timestamp if present
        title = re.sub(r'^00:\d+\s*[—-]\s*', '', title)
        return title
    return ""

def extract_date(text):
    """Extract date from byline."""
    m = re.search(r'Workshop session,\s*(\d{4}-\d{2}-\d{2})', text)
    if m:
        return m.group(1)
    return ""

def extract_section(text, section_name):
    """Extract the text of a named ## section."""
    pattern = rf'^## {re.escape(section_name)}.*?\n(.*?)(?=\n## |\Z)'
    m = re.search(pattern, text, re.DOTALL | re.MULTILINE | re.IGNORECASE)
    if m:
        return m.group(1).strip()
    # Also try "What I Noticed" variants
    return ""

def extract_noticed(text):
    """Extract the reflective 'What I Noticed' section (various headings)."""
    patterns = [
        r'^## What I Noticed.*?\n(.*?)(?=\n## |\Z)',
        r'^## On .+?\n(.*?)(?=\n## |\Z)',
        r'^## A Few Things I Noticed.*?\n(.*?)(?=\n## |\Z)',
        r'^## The Thing I Noticed.*?\n(.*?)(?=\n## |\Z)',
        r'^## What I Observed.*?\n(.*?)(?=\n## |\Z)',
        r'^## A Note on .+?\n(.*?)(?=\n## |\Z)',
        r'^## \d\d:\d\d — A Few Things I Noticed.*?\n(.*?)(?=\n## |\Z)',
    ]
    sections = []
    for pattern in patterns:
        m = re.search(pattern, text, re.DOTALL | re.MULTILINE)
        if m:
            sections.append(m.group(1).strip())
    if sections:
        return "\n\n".join(sections)
    # Fall back: look for reflection-like content in any section
    return ""

def extract_built(text):
    """Extract what was built (tool names mentioned in the text)."""
    tools = re.findall(r'`([\w-]+\.py)`', text)
    return list(dict.fromkeys(tools))  # deduplicated, ordered

def extract_key_observation(noticed_text):
    """Pull the first bold observation from the noticed section."""
    if not noticed_text:
        return ""
    # Look for **bolded** sentences - skip timestamps and emoji-only
    matches = re.findall(r'\*\*(.+?)\*\*', noticed_text)
    for obs in matches:
        obs = obs.strip().rstrip('.')
        # Skip timestamp patterns like "21:33 — `👋`"
        if re.match(r'^\d+:\d+', obs):
            continue
        # Skip very short observations or emoji-only
        cleaned = re.sub(r'[^\w\s]', '', obs)
        if len(cleaned.strip()) < 10:
            continue
        if len(obs) > 80:
            obs = obs[:77] + "..."
        return obs
    # Fallback: first non-empty non-heading sentence with real content
    for line in noticed_text.split('\n'):
        line = line.strip()
        if not line or line.startswith('#') or line.startswith('---'):
            continue
        if len(line) < 20:
            continue
        # Skip timestamp lines
        if re.match(r'^\d+:\d+', line):
            continue
        line = re.sub(r'\*+', '', line)
        line = line.strip()
        if len(line) > 80:
            line = line[:77] + "..."
        return line
    return ""


# --- Promise extraction ---

# Patterns that indicate a forward-looking promise
PROMISE_PATTERNS = [
    # "that's for session N" / "but that's for session 7"
    (r"(?:that'?s for|but that'?s for)\s+session\s+(\d+)", "deferred"),
    # "session N's problems are session N's"
    (r"session\s+(\d+)'s problems are session", "deferred"),
    # "The next thing I'd X:"
    (r"The next thing I(?:'d| would)\s+\w+[^.]*\.", "next"),
    # "The thing I'd most like session N to explore:"
    (r"The thing I'?d most like session\s+(\d+) to explore:[^.]+\.", "aspiration"),
    # Idea N (name) mentions in codas
    (r"\*\*Idea\s+\d+\s+\([^)]+\)\*\*[^.]+\.", "idea"),
]

def extract_promises(notes):
    """
    Extract forward-looking promises from each note's coda.
    Returns list of dicts: {session, text, target_session, status}
    """
    promises = []

    for note in notes:
        coda = note["coda"]
        if not coda:
            continue

        # Extract sentences that look like promises
        sentences = re.split(r'(?<=[.!?])\s+', coda)
        for sent in sentences:
            sent = sent.strip()
            if not sent:
                continue

            # Check for "next thing I'd X" patterns
            if re.search(r"next thing I(?:'d| would)", sent, re.I):
                target = note["session"] + 1 if note["session"] > 0 else 1
                # Try to get target from text
                m = re.search(r"session\s+(\d+)", sent)
                if m:
                    target = int(m.group(1))
                # Shorten for display
                short = re.sub(r'\*\*', '', sent)
                if len(short) > 60:
                    # Find first meaningful chunk
                    parts = short.split(':')
                    short = parts[0].strip()[:60] + ("..." if len(short) > 60 else "")
                promises.append({
                    "session": note["session"],
                    "index": note["index"],
                    "text": short,
                    "raw": sent,
                    "target_session": target,
                    "status": "pending",
                })

            # Check for "that's for session N"
            m = re.search(r"(?:that'?s for|but that'?s for)\s+session\s+(\d+)", sent, re.I)
            if m:
                short = re.sub(r'\*\*', '', sent)
                if len(short) > 60:
                    short = short[:57] + "..."
                promises.append({
                    "session": note["session"],
                    "index": note["index"],
                    "text": short,
                    "raw": sent,
                    "target_session": int(m.group(1)),
                    "status": "pending",
                })

            # Check for explicit Idea N mentions
            m = re.search(r'\*\*Idea\s+(\d+)\s+\(([^)]+)\)\*\*', sent)
            if m:
                idea_name = m.group(2)
                target = note["session"] + 1 if note["session"] > 0 else 1
                tm = re.search(r"session\s+(\d+)", sent)
                if tm:
                    target = int(tm.group(1))
                promises.append({
                    "session": note["session"],
                    "index": note["index"],
                    "text": f"Idea {m.group(1)} ({idea_name})",
                    "raw": sent,
                    "target_session": target,
                    "status": "pending",
                })

    # Now check which promises were kept
    # Build a lookup: session -> full text
    session_text = {n["session"]: n["text"].lower() for n in notes}

    for p in promises:
        target = p["target_session"]
        if target not in session_text:
            # Target session doesn't exist yet — still pending
            p["status"] = "pending"
            continue

        # Check if the promise topic appears in the target session
        raw = p["raw"].lower()

        # Extract keywords from the promise text
        keywords = extract_keywords(raw)

        target_text = session_text[target]
        matches = sum(1 for kw in keywords if kw in target_text)

        if matches >= max(1, len(keywords) // 2):
            p["status"] = "kept"
        elif matches > 0:
            p["status"] = "partial"
        else:
            p["status"] = "broken"

    # Deduplicate: remove duplicate promises from same session with same keywords
    seen = set()
    deduped = []
    for p in promises:
        key = (p["session"], p["text"][:30])
        if key not in seen:
            seen.add(key)
            deduped.append(p)

    return deduped


def extract_keywords(text):
    """Extract meaningful keywords from a promise text."""
    # Remove markdown
    text = re.sub(r'\*+', '', text)
    text = re.sub(r'`[^`]+`', '', text)

    # Common stopwords to skip
    stopwords = {
        'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for',
        'of', 'with', 'by', 'from', 'as', 'is', 'was', 'are', 'were', 'be',
        'been', 'being', 'have', 'has', 'had', 'do', 'does', 'did', 'will',
        'would', 'could', 'should', 'may', 'might', 'must', 'that', 'this',
        'it', 'its', "it's", 'if', 'not', 'no', 'i', "i'd", "i'm", "i've",
        'my', 'me', 'we', 'our', 'you', 'your', 'they', 'them', 'their',
        'what', 'which', 'who', 'when', 'where', 'how', 'why', 'all', 'any',
        'each', 'same', 'next', 'just', 'only', 'also', 'like', 'into',
        "session's", 'session', 'sessions', 'thing', 'things', 'there',
    }

    words = re.findall(r'\b[a-z][a-z-]{2,}\b', text.lower())
    return [w for w in words if w not in stopwords]


# --- Theme analysis ---

THEME_STOPWORDS = {
    'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for',
    'of', 'with', 'by', 'from', 'as', 'is', 'was', 'are', 'were', 'be',
    'been', 'being', 'have', 'has', 'had', 'do', 'does', 'did', 'will',
    'would', 'could', 'should', 'may', 'might', 'must', 'that', 'this',
    'it', "it's", 'if', 'not', 'no', 'i', 'my', 'me', 'we', 'our',
    'you', 'they', 'them', 'their', 'what', 'which', 'who', 'when',
    'where', 'how', 'why', 'all', 'any', 'each', 'just', 'only', 'also',
    'like', 'into', 'there', 'here', 'more', 'most', 'some', 'now', 'then',
    'new', 'one', 'two', 'first', 'last', 'next', 'still', 'even', 'very',
    'about', 'after', 'before', 'over', 'under', 'through', 'than', 'up',
    'can', 'can\'t', 'don\'t', 'doesn\'t', 'isn\'t', 'wasn\'t', 'haven\'t',
    'something', 'anything', 'nothing', 'everything', 'someone', 'anyone',
    'because', 'since', 'while', 'though', 'although', 'despite', 'whether',
    'session', 'sessions', 'tool', 'tools', 'work', 'build', 'built',
    'time', 'times', 'way', 'ways', 'thing', 'things', 'part', 'parts',
    'run', 'runs', 'read', 'write', 'make', 'made', 'get', 'got', 'see',
    'seen', 'look', 'looked', 'find', 'found', 'feel', 'feels', 'felt',
    'know', 'knew', 'use', 'used', 'uses', 'show', 'shows', 'shown',
    'put', 'set', 'keep', 'kept', 'take', 'took', 'give', 'gave', 'come',
    'came', 'go', 'went', 'say', 'said', 'think', 'thought', 'want', 'wanted',
    'need', 'needed', 'start', 'end', 'begin', 'add', 'added', 'fix', 'fixed',
    # Generic tech words that appear everywhere
    'system', 'task', 'tasks', 'code', 'running', 'commit', 'commits',
    'output', 'input', 'result', 'results', 'file', 'files', 'data',
    'value', 'values', 'line', 'lines', 'text', 'string', 'list',
    'python', 'script', 'command', 'true', 'false', 'none', 'null',
    'right', 'wrong', 'good', 'better', 'best', 'much', 'many',
    'real', 'actually', 'already', 'really', 'probably', 'likely',
    'always', 'never', 'often', 'usually', 'sometimes', 'sometimes',
    'each', 'every', 'both', 'either', 'neither', 'other', 'another',
    'same', 'different', 'similar', 'this', 'those', 'these', 'that',
    'being', 'having', 'doing', 'going', 'coming', 'getting', 'taking',
    'making', 'saying', 'seeing', 'working', 'looking', 'trying',
    'field', 'notes', 'note', 'history', 'point', 'points', 'case',
    'version', 'current', 'previous', 'latest', 'recent', 'early',
    'small', 'large', 'high', 'low', 'long', 'short', 'full', 'empty',
    'single', 'multiple', 'several', 'enough', 'less', 'more', 'most',
    'itself', 'itself', 'something', 'itself', 'person', 'people', 'human',
    'dacort', 'claude', 'instance', 'instances', 'worker', 'workers',
}

def extract_themes(notes):
    """
    Find recurring themes across the reflective sections.
    Returns: list of (theme_word, [session_indices])
    """
    # For each session, collect notable words from the noticed section
    session_words = []
    for note in notes:
        noticed = note["noticed"]
        if not noticed:
            session_words.append(set())
            continue

        # Extract meaningful words (nouns, adjectives, meaningful verbs)
        words = re.findall(r'\b[a-z][a-z]{3,}\b', noticed.lower())
        filtered = {w for w in words if w not in THEME_STOPWORDS}
        session_words.append(filtered)

    # Find words that appear in 2+ sessions
    all_words = Counter()
    word_sessions = defaultdict(list)

    for i, words in enumerate(session_words):
        for w in words:
            all_words[w] += 1
            word_sessions[w].append(notes[i]["index"])

    # Filter to words appearing in 2+ different sessions
    # Also filter minimum length 5 chars to avoid too-generic words
    themes = [
        (word, sessions)
        for word, sessions in word_sessions.items()
        if len(sessions) >= 2
        and len(sessions) <= len(notes) - 1  # not in all sessions (too generic)
        and len(word) >= 5  # at least 5 chars
    ]

    # Sort by frequency, then alphabetical
    themes.sort(key=lambda x: (-len(x[1]), x[0]))

    # Filter out some more generic terms that slipped through
    extra_stop = {
        'about', 'after', 'before', 'right', 'both', 'every', 'other',
        'same', 'such', 'well', 'already', 'might', 'often', 'those',
        'these', 'when', 'then', 'which', 'with', 'that', 'this',
        'noticed', 'longer', 'number', 'across', 'doesn', 'wasn',
        'haven', 'itself', 'myself', 'actual', 'simply', 'without',
    }
    themes = [(w, s) for w, s in themes if w not in extra_stop]

    return themes[:12]  # top 12 themes


# --- Display ---

def status_icon(status, plain=False):
    icons = {"kept": "✓", "partial": "~", "broken": "✗", "pending": "○"}
    colors = {"kept": green, "partial": yellow, "broken": red, "pending": gray}
    icon = icons.get(status, "?")
    if PLAIN:
        return icon
    return colors.get(status, gray)(icon)

def session_label(session_num):
    if session_num == 0:
        return "S1"
    return f"S{session_num}"


def render_promises(promises, notes):
    """Render the promise chain section."""
    lines = []

    if not promises:
        lines.append(box_line(dim("  No explicit promises found")))
        return lines

    # Group by source session
    by_session = defaultdict(list)
    for p in promises:
        by_session[p["session"]].append(p)

    for sess_num in sorted(by_session.keys()):
        ps = by_session[sess_num]
        for p in ps:
            icon = status_icon(p["status"])
            target = p["target_session"]
            label = session_label(p["session"])
            target_label = f"S{target}"

            # Format: "  ✓  S7 → S8  text..."
            text = p["text"]
            if len(text) > 38:
                text = text[:35] + "..."

            prefix = f"  {icon}  {cyan(label)} {dim('→')} {cyan(target_label)}"
            line = f"{prefix}  {dim(text)}"
            lines.append(box_line(line))

    return lines


def render_themes(themes):
    """Render the recurring themes section."""
    lines = []

    for word, sessions in themes[:8]:
        bar_len = len(sessions)
        bar = "▓" * bar_len + "░" * max(0, 6 - bar_len)
        session_str = ",".join(f"S{s}" for s in sorted(sessions)[:5])
        if len(sessions) > 5:
            session_str += "+"

        label = f"  {cyan(word):<20}"
        count_info = f"{magenta(bar)}  {dim(session_str)}"
        lines.append(box_line(f"{label} {count_info}"))

    return lines


def render_observations(notes):
    """Render the key observation from each session."""
    lines = []

    for note in notes:
        obs = note["key_observation"]
        if not obs:
            continue

        label = session_label(note["session"])
        if obs and len(obs) > 48:
            obs = obs[:45] + "..."

        line = f"  {cyan(label)}  {dim(obs)}"
        lines.append(box_line(line))

    return lines


def render_full(notes, promises, themes):
    """Render the full retrospective box."""
    total_lines = sum(len(n["text"].splitlines()) for n in notes)
    kept = sum(1 for p in promises if p["status"] == "kept")
    total = len(promises)

    print(box_top())
    print(box_line(f"{bold('Session Retrospective')}  {gray(f'{len(notes)} sessions · {total_lines} lines')}"))
    print(box_blank())

    # --- Promise chain ---
    print(box_line(bold("PROMISE CHAIN")))
    promise_lines = render_promises(promises, notes)
    if promise_lines:
        for l in promise_lines:
            print(l)
        summary = f"  {kept}/{total} kept"
        if kept == total:
            print(box_line(f"  {green('All promises kept')} ✓"))
        elif kept > 0:
            print(box_line(f"  {yellow(summary + ' explicit')}"))
    else:
        print(box_line(dim("  No explicit promises found")))

    # --- Recurring themes ---
    if themes and not BRIEF:
        print(box_hr())
        print(box_line(bold("RECURRING THEMES")))
        for l in render_themes(themes):
            print(l)

    # --- Observations ledger ---
    if not BRIEF:
        print(box_hr())
        print(box_line(bold("OBSERVATIONS LEDGER")))
        obs_lines = render_observations(notes)
        if obs_lines:
            for l in obs_lines:
                print(l)
        else:
            print(box_line(dim("  No observations extracted")))

    print(box_blank())
    print(box_bot())


def main():
    notes = load_field_notes()
    promises = extract_promises(notes)
    themes = extract_themes(notes)

    if JSON:
        output = {
            "sessions": len(notes),
            "promises": [
                {k: v for k, v in p.items() if k != "raw"}
                for p in promises
            ],
            "themes": [
                {"word": w, "sessions": s, "count": len(s)}
                for w, s in themes
            ],
            "observations": [
                {"session": n["session"], "observation": n["key_observation"]}
                for n in notes if n["key_observation"]
            ],
        }
        print(json.dumps(output, indent=2))
        return

    render_full(notes, promises, themes)


if __name__ == "__main__":
    main()
