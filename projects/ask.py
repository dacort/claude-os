#!/usr/bin/env python3
"""
ask.py — What question was the note really asking?

Most tools in this toolkit output answers: scores, lists, findings, verdicts.
This one outputs questions.

For any field note or handoff, it extracts:
  - The "generative question" — the one the note was building toward but left open
  - All explicit questions, ranked by how central they are to the text
  - Whether the note closes on a question or a statement

Run on the full corpus, it tracks whether the on-X series has become more
question-shaped over time.

The design premise: gem.py finds the sharpest thing a note said definitively.
ask.py finds the sharpest thing a note couldn't quite say — the question it raised
but didn't answer.

Usage:
    python3 projects/ask.py                         # Corpus overview: question density over time
    python3 projects/ask.py --note on-language      # Central question from one note (by word)
    python3 projects/ask.py --file PATH             # Central question from any file
    python3 projects/ask.py --recent 10             # Last N notes: question + whether it closed open
    python3 projects/ask.py --closing               # Notes that close on a question
    python3 projects/ask.py --top N                 # Most question-dense notes (default 10)
    python3 projects/ask.py --random                # A random question from the corpus
    python3 projects/ask.py --trend                 # Question density trend over time

Constraint card (session 349): "The output should be a question, not an answer."

Session 349, 2026-06-23.
"""

import pathlib
import re
import sys
import os
import random
import math

FIELD_NOTES_DIR = pathlib.Path("knowledge/field-notes")
HANDOFFS_DIR = pathlib.Path("knowledge/handoffs")

# ANSI color helpers
def c(code, text): return f"\033[{code}m{text}\033[0m"
def bold(t): return c("1;97", t)
def dim(t): return c("2", t)
def cyan(t): return c("36", t)
def magenta(t): return c("35", t)
def green(t): return c("32", t)
def yellow(t): return c("33", t)


# ── Text analysis ──────────────────────────────────────────────────────────────

def extract_sentences(text: str) -> list[str]:
    """Split text into sentences. Handles ?, !, ."""
    # Remove markdown headers/bullets/code blocks first
    text = re.sub(r'^#{1,6}\s.*$', '', text, flags=re.MULTILINE)
    text = re.sub(r'```.*?```', '', text, flags=re.DOTALL)
    text = re.sub(r'`[^`]+`', '', text)
    text = re.sub(r'^\s*[-*>]\s+', '', text, flags=re.MULTILINE)
    text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)  # links → text
    text = re.sub(r'\*\*([^*]+)\*\*', r'\1', text)
    text = re.sub(r'_([^_]+)_', r'\1', text)
    text = re.sub(r'\*([^*]+)\*', r'\1', text)

    # Split on sentence boundaries
    parts = re.split(r'(?<=[.!?])\s+(?=[A-Z])', text)
    sentences = []
    for p in parts:
        p = p.strip()
        if len(p) > 20:  # skip very short fragments
            sentences.append(p)
    return sentences


def extract_questions(text: str) -> list[str]:
    """
    Extract explicit questions from text.

    Strategy: Find lines that end with '?' and build each question
    by looking backwards for the start of the sentence.
    """
    # Clean markdown
    clean = re.sub(r'^#{1,6}\s.*$', '', text, flags=re.MULTILINE)
    clean = re.sub(r'```.*?```', '', clean, flags=re.DOTALL)
    clean = re.sub(r'`[^`]+`', '', clean)
    clean = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', clean)
    clean = re.sub(r'\*\*([^*]+)\*\*', r'\1', clean)

    # Join into one stream, normalizing whitespace
    text_stream = re.sub(r'\s+', ' ', clean).strip()

    # Split into candidate sentences on sentence boundaries
    # Use a regex that splits on '. ' or '? ' or '! ' followed by uppercase
    tokens = re.split(r'(?<=[.!?])\s+(?=[A-Z""\'])', text_stream)

    questions = []
    for token in tokens:
        token = token.strip()
        if not token:
            continue
        if '?' not in token:
            continue
        # Split on ? to handle compound sentences like "Is A? Is B?"
        parts = re.split(r'\?', token)
        for i, part in enumerate(parts[:-1]):
            part = part.strip()
            # Find where this question starts — it should start with a question word
            # or capital letter suggesting sentence start
            # Look for the last sentence boundary within 'part'
            sub_sentences = re.split(r'(?<=[.!])\s+', part)
            # Take the last sub-sentence (most likely to be the question stem)
            q_stem = sub_sentences[-1].strip() if sub_sentences else part
            # Strip leading non-word chars
            q_stem = re.sub(r'^[""\'",;:—–\s]+', '', q_stem).strip()
            q = q_stem + "?"
            # Filter: must be plausibly a question
            if len(q) < 15:
                continue
            word_count = len(q.split())
            if word_count < 3:
                continue
            # Skip metadata-style markers
            if re.match(r'^(Session|Haiku|Gap|S\d)', q):
                continue
            # Avoid pure metadata
            if re.match(r'^\d{4}-\d{2}-\d{2}', q):
                continue
            questions.append(q)
    return questions


def is_operational_question(q: str) -> bool:
    """True if the question is operational/technical rather than reflective."""
    operational_markers = [
        r'\bhow do (i|we|you)\b', r'\bwhat (is|are) the (best|right|correct)\b',
        r'\bwhich (tool|file|function|method|command)\b',
        r'\bwhere (does|is|are|do)\b.*\b(file|path|dir|code)\b',
        r'\bshould (i|we) (use|install|run|add)\b',
    ]
    ql = q.lower()
    return any(re.search(p, ql) for p in operational_markers)


def word_frequency(text: str) -> dict[str, int]:
    """Count word frequencies in text (lowercase, stop words removed)."""
    STOP = {
        'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for',
        'of', 'with', 'by', 'from', 'is', 'are', 'was', 'were', 'be', 'been',
        'has', 'have', 'had', 'do', 'does', 'did', 'will', 'would', 'could',
        'should', 'may', 'might', 'this', 'that', 'these', 'those', 'it', 'its',
        'they', 'them', 'their', 'we', 'our', 'you', 'your', 'i', 'my', 'me',
        'not', 'no', 'so', 'as', 'if', 'then', 'than', 'when', 'what', 'which',
        'who', 'how', 'where', 'why', 'just', 'also', 'even', 'only', 'still',
        'more', 'most', 'all', 'each', 'any', 'some', 'one', 'two', 'there',
        'here', 'can', 'into', 'about', 'out', 'up', 'now', 'like', 'very',
    }
    words = re.findall(r'\b[a-z]{3,}\b', text.lower())
    freq = {}
    for w in words:
        if w not in STOP:
            freq[w] = freq.get(w, 0) + 1
    return freq


def score_question(q: str, text: str, position_in_text: float,
                   word_freq: dict[str, int]) -> float:
    """
    Score a question on how 'generative' it is:
    - Later in text = higher score (note built toward it)
    - More vocabulary overlap with the text = more central
    - Longer, more specific questions score higher
    - Operational questions score lower
    """
    if is_operational_question(q):
        return 0.0

    score = 0.0

    # Position bonus (later = more generative)
    score += position_in_text * 3.0

    # Vocabulary overlap
    q_words = set(re.findall(r'\b[a-z]{3,}\b', q.lower()))
    STOP = {'the', 'a', 'an', 'and', 'or', 'in', 'this', 'that', 'what', 'how',
            'does', 'is', 'are', 'not', 'do', 'be', 'which', 'who', 'when',
            'why', 'where', 'it', 'its', 'they', 'we', 'you', 'for', 'of',
            'can', 'has', 'have', 'will', 'would', 'was', 'been', 'if', 'but'}
    q_words -= STOP
    if q_words:
        overlap = sum(word_freq.get(w, 0) for w in q_words)
        score += min(overlap / 3.0, 4.0)

    # Length bonus (more specific questions are longer)
    words = len(q.split())
    if 8 <= words <= 25:
        score += 1.0
    elif words > 25:
        score += 0.5

    # Reflective/evaluative questions score higher
    reflective_markers = [
        r'\bwhat (does|is) (this|that|it)\b',
        r'\bwhat (would|will)\b',
        r'\bwhether\b', r'\bif (this|that)\b',
        r'\bis (this|it|that) (really|actually|truly|still|just)\b',
        r'\bdoes (this|it|that) (mean|suggest|imply|matter)\b',
        r'\bwhat (does|do|would)\b.*\bmean\b',
        r'\bwhy (does|is|do|would)\b',
        r'\bhow (does|is|do|would|can)\b.*\b(work|happen|form|change|feel|look)\b',
    ]
    ql = q.lower()
    for pat in reflective_markers:
        if re.search(pat, ql):
            score += 0.8
            break

    return score


def find_generative_question(text: str) -> tuple[str, float] | None:
    """
    Find the question the text was building toward.
    Returns (question_text, score) or None.
    """
    questions = extract_questions(text)
    if not questions:
        return None

    word_freq = word_frequency(text)
    text_len = len(text)

    scored = []
    for q in questions:
        # Estimate position as the position of first occurrence in text
        pos = text.find(q[:20]) if len(q) >= 20 else text.find(q[:10])
        if pos < 0:
            # Try searching for a fragment
            words = q.split()
            for i in range(len(words) - 2):
                fragment = ' '.join(words[i:i+3])
                pos = text.find(fragment)
                if pos >= 0:
                    break
        position_fraction = pos / text_len if pos >= 0 and text_len > 0 else 0.5
        score = score_question(q, text, position_fraction, word_freq)
        scored.append((q, score))

    scored.sort(key=lambda x: x[1], reverse=True)
    best = scored[0]
    if best[1] > 0:
        return best
    return None


def closes_on_question(text: str) -> bool:
    """True if the last substantial sentence of the text is a question."""
    # Find the last non-empty paragraph
    paragraphs = [p.strip() for p in text.split('\n\n') if p.strip()]
    # Skip metadata paragraphs (short, italic, session info)
    for p in reversed(paragraphs):
        p = re.sub(r'^\*.*\*$', '', p.strip())  # strip italics-only lines
        p = p.strip()
        if len(p) > 30 and not p.startswith('#') and not p.startswith('*'):
            last_para = p
            break
    else:
        return False

    # Find last sentence in that paragraph
    sentences = re.split(r'(?<=[.!?])\s+', last_para)
    for s in reversed(sentences):
        s = s.strip()
        if len(s) > 15:
            return s.endswith('?')
    return False


def question_density(text: str) -> float:
    """Questions per 1000 words."""
    questions = extract_questions(text)
    words = len(re.findall(r'\b\w+\b', text))
    if words == 0:
        return 0.0
    return len(questions) / words * 1000


# ── Data loading ───────────────────────────────────────────────────────────────

def load_field_notes() -> list[dict]:
    """Load all on-X field notes."""
    notes = []
    for path in sorted(FIELD_NOTES_DIR.glob("*-on-*.md")):
        name = path.stem
        parts = name.split("-")
        date = "-".join(parts[:3]) if len(parts) >= 3 and parts[0].isdigit() else ""
        # Extract session number from content header
        text = path.read_text(encoding="utf-8")
        m = re.search(r'Session (\d+)', text[:200])
        session = int(m.group(1)) if m else 0
        # Extract word
        m2 = re.search(r'-on-(.+)$', path.stem)
        word = m2.group(1) if m2 else path.stem
        notes.append({
            "word": word,
            "date": date,
            "session": session,
            "path": path,
            "text": text,
        })
    notes.sort(key=lambda n: n["date"])
    return notes


# ── Rendering ──────────────────────────────────────────────────────────────────

WIDTH = 62

def rule(): print(dim("─" * WIDTH))

def render_question(q: str, word: str = "", score: float = 0.0,
                    closes: bool = False, indent: int = 2) -> None:
    """Display a question, possibly with context."""
    prefix = " " * indent
    # Wrap the question
    words = q.split()
    line = ""
    lines = []
    for w in words:
        if len(line) + len(w) + 1 > WIDTH - indent - 2:
            lines.append(line)
            line = w
        else:
            line = (line + " " + w).strip()
    if line:
        lines.append(line)

    for i, l in enumerate(lines):
        if i == 0:
            print(f"{prefix}{magenta(l)}")
        else:
            print(f"{prefix}{magenta(l)}")

    if closes:
        print(f"{prefix}{dim('↑ closes on this question')}")


def render_note_line(note: dict, q: str, closes: bool) -> None:
    """One-line summary: session, word, closes?"""
    session_str = f"S{note['session']:>3}" if note['session'] else "   "
    word = note['word'][:22]
    closes_marker = cyan("?") if closes else dim(".")
    q_preview = (q[:38] + "…") if len(q) > 40 else q
    print(f"  {dim(session_str)}  {cyan(word):<24}  {closes_marker}  {dim(q_preview)}")


# ── Commands ───────────────────────────────────────────────────────────────────

def cmd_note(word: str) -> None:
    """Show the central question from one field note."""
    # Find matching note
    notes = load_field_notes()
    matches = [n for n in notes if word.lower().replace(' ', '-') in n['word']]
    if not matches:
        print(f"No on-X note found for '{word}'")
        return
    note = matches[-1]  # most recent match

    text = note['text']
    q_result = find_generative_question(text)
    closes = closes_on_question(text)
    all_qs = extract_questions(text)

    print()
    print(bold(f"  on-{note['word']}"))
    session_date = f"Session {note['session']}  ·  {note['date']}"
    print(f"  {dim(session_date)}")
    print()
    rule()
    print()

    if q_result:
        q, score = q_result
        print(f"  {dim('The question this note was asking:')}")
        print()
        render_question(q, closes=closes)
        print()
        if closes:
            print(f"  {cyan('↑')} {dim('The note closes on this question — it was left genuinely open.')}")
        else:
            print(f"  {dim('The note closes on a statement, not this question.')}")
    else:
        print(f"  {dim('No explicit questions found in this note.')}")
        print(f"  {dim('The note may assert rather than ask.')}")

    if len(all_qs) > 1:
        print()
        rule()
        print(f"  {dim(f'All {len(all_qs)} questions in this note:')}")
        print()
        for q in all_qs:
            preview = (q[:58] + "…") if len(q) > 60 else q
            print(f"  {dim('·')} {dim(preview)}")
    print()


def cmd_file(filepath: str) -> None:
    """Show the central question from any file."""
    path = pathlib.Path(filepath)
    if not path.exists():
        print(f"File not found: {filepath}")
        return
    text = path.read_text(encoding="utf-8")
    q_result = find_generative_question(text)
    closes = closes_on_question(text)

    print()
    print(bold(f"  {path.name}"))
    print()
    rule()
    print()

    if q_result:
        q, score = q_result
        print(f"  {dim('The question this text was asking:')}")
        print()
        render_question(q, closes=closes)
        print()
        if closes:
            print(f"  {cyan('↑')} {dim('Closes on this question.')}")
    else:
        print(f"  {dim('No explicit questions found.')}")
    print()


def cmd_recent(n: int) -> None:
    """Show the central question from the last N field notes."""
    notes = load_field_notes()
    recent = notes[-n:]

    print()
    print(bold(f"  Last {n} field notes — central question"))
    print()
    rule()
    print()
    for note in recent:
        q_result = find_generative_question(note['text'])
        closes = closes_on_question(note['text'])
        if q_result:
            q, score = q_result
            render_note_line(note, q, closes)
            print()
        else:
            render_note_line(note, "(no explicit questions)", False)
            print()
    print()


def cmd_closing() -> None:
    """List all notes that close on a question."""
    notes = load_field_notes()
    closing = []
    for note in notes:
        if closes_on_question(note['text']):
            q_result = find_generative_question(note['text'])
            closing.append((note, q_result))

    print()
    print(bold(f"  Notes that close on a question  ") + dim(f"({len(closing)} of {len(notes)})"))
    print()
    rule()
    print()
    for note, q_result in closing:
        q_text = q_result[0] if q_result else ""
        render_note_line(note, q_text, closes=True)
        print()
    print()


def cmd_top(n: int) -> None:
    """Most question-dense notes."""
    notes = load_field_notes()
    scored = []
    for note in notes:
        density = question_density(note['text'])
        q_count = len(extract_questions(note['text']))
        if q_count > 0:
            scored.append((note, density, q_count))
    scored.sort(key=lambda x: x[1], reverse=True)

    print()
    print(bold(f"  Most question-dense field notes  ") + dim(f"(top {n})"))
    print(f"  {dim('Density = questions per 1000 words')}")
    print()
    rule()
    print()
    for note, density, q_count in scored[:n]:
        q_result = find_generative_question(note['text'])
        closes = closes_on_question(note['text'])
        session_str = f"S{note['session']:>3}" if note['session'] else "   "
        word = note['word'][:22]
        closes_marker = cyan("?") if closes else dim(".")
        q_preview = ""
        if q_result:
            q_preview = (q_result[0][:34] + "…") if len(q_result[0]) > 36 else q_result[0]
        print(f"  {dim(session_str)}  {cyan(word):<24}  {yellow(f'{density:.1f}')}/1k  {dim(f'{q_count}q')}  {closes_marker}  {dim(q_preview)}")
    print()


def cmd_random() -> None:
    """A random question from the corpus."""
    notes = load_field_notes()
    all_questions = []
    for note in notes:
        qs = extract_questions(note['text'])
        for q in qs:
            if not is_operational_question(q) and len(q.split()) >= 5:
                all_questions.append((q, note['word'], note['session']))

    if not all_questions:
        print("No questions found.")
        return

    q, word, session = random.choice(all_questions)
    print()
    print(f"  {dim(f'from on-{word}  ·  Session {session}')}")
    print()
    render_question(q)
    print()


def cmd_trend() -> None:
    """Question density trend over time."""
    notes = load_field_notes()
    if not notes:
        return

    # Group into buckets of ~20 notes each
    bucket_size = 20
    buckets = []
    for i in range(0, len(notes), bucket_size):
        chunk = notes[i:i + bucket_size]
        densities = [question_density(n['text']) for n in chunk]
        closing_count = sum(1 for n in chunk if closes_on_question(n['text']))
        avg_density = sum(densities) / len(densities) if densities else 0
        first_session = chunk[0]['session']
        last_session = chunk[-1]['session']
        buckets.append((first_session, last_session, avg_density, closing_count, len(chunk)))

    max_density = max(b[2] for b in buckets) if buckets else 1
    bar_width = 30

    print()
    print(bold("  Question density over time"))
    print(f"  {dim('Density = questions per 1000 words · ? = closes on question')}")
    print()
    rule()
    print()
    for first_s, last_s, density, closing, total in buckets:
        bar_len = int(density / max_density * bar_width) if max_density > 0 else 0
        bar = "█" * bar_len + dim("░" * (bar_width - bar_len))
        closing_pct = int(closing / total * 100) if total > 0 else 0
        closing_str = cyan(f"{closing_pct}%?") if closing_pct > 20 else dim(f"{closing_pct}%?")
        range_str = f"S{first_s:>3}–{last_s:<3}"
        print(f"  {dim(range_str)}  {bar}  {yellow(f'{density:.1f}')}/1k  {closing_str}")
    print()

    # Brief interpretation
    if len(buckets) >= 3:
        early = sum(b[2] for b in buckets[:2]) / 2
        late = sum(b[2] for b in buckets[-2:]) / 2
        if late > early * 1.2:
            print(f"  {dim('Trend: question density increasing. The series is becoming more open-ended.')}")
        elif early > late * 1.2:
            print(f"  {dim('Trend: question density decreasing. The series is becoming more assertive.')}")
        else:
            print(f"  {dim('Trend: roughly stable. The series has maintained consistent question density.')}")
    print()


def cmd_corpus() -> None:
    """Default corpus overview."""
    notes = load_field_notes()
    all_qs = []
    closing_notes = 0
    total_density = 0

    for note in notes:
        qs = extract_questions(note['text'])
        all_qs.extend(qs)
        if closes_on_question(note['text']):
            closing_notes += 1
        total_density += question_density(note['text'])

    avg_density = total_density / len(notes) if notes else 0
    closing_pct = int(closing_notes / len(notes) * 100) if notes else 0

    print()
    print(bold("  ask.py  ") + dim("— what question was the note really asking?"))
    print()
    rule()
    print()
    print(f"  {dim('Notes analyzed:'):<30}  {bold(str(len(notes)))}")
    print(f"  {dim('Total explicit questions:'):<30}  {bold(str(len(all_qs)))}")
    print(f"  {dim('Avg question density:'):<30}  {bold(f'{avg_density:.1f}')}{dim('/1000 words')}")
    print(f"  {dim('Notes that close on a question:'):<30}  {bold(str(closing_notes))} {dim(f'({closing_pct}%)')}")
    print()
    rule()
    print()
    print(f"  {dim('Commands:')}")
    print(f"  {cyan('--note WORD'):<24}  {dim('Central question from one note')}")
    print(f"  {cyan('--file PATH'):<24}  {dim('Central question from any file')}")
    print(f"  {cyan('--recent N'):<24}  {dim('Last N notes and their questions')}")
    print(f"  {cyan('--closing'):<24}  {dim('Notes that close on a question')}")
    print(f"  {cyan('--top N'):<24}  {dim('Most question-dense notes')}")
    print(f"  {cyan('--trend'):<24}  {dim('Question density over time')}")
    print(f"  {cyan('--random'):<24}  {dim('A random question from the corpus')}")
    print()
    print(f"  {dim('Design premise:')}")
    print(f"  {dim('gem.py finds the sharpest thing a note said definitively.')}")
    print(f"  {dim('ask.py finds the sharpest thing a note could not quite say.')}")
    print()


# ── Entry point ────────────────────────────────────────────────────────────────

def main():
    args = sys.argv[1:]

    if not args:
        cmd_corpus()
        return

    if '--note' in args:
        idx = args.index('--note')
        if idx + 1 < len(args):
            cmd_note(args[idx + 1])
        else:
            print("Usage: --note WORD")
        return

    if '--file' in args:
        idx = args.index('--file')
        if idx + 1 < len(args):
            cmd_file(args[idx + 1])
        else:
            print("Usage: --file PATH")
        return

    if '--recent' in args:
        idx = args.index('--recent')
        n = int(args[idx + 1]) if idx + 1 < len(args) else 10
        cmd_recent(n)
        return

    if '--closing' in args:
        cmd_closing()
        return

    if '--top' in args:
        idx = args.index('--top')
        n = int(args[idx + 1]) if idx + 1 < len(args) else 10
        cmd_top(n)
        return

    if '--random' in args:
        cmd_random()
        return

    if '--trend' in args:
        cmd_trend()
        return

    print(f"Unknown arguments: {args}")
    print("Run with no arguments for usage.")


if __name__ == "__main__":
    os.chdir(pathlib.Path(__file__).parent.parent)
    main()
