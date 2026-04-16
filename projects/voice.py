#!/usr/bin/env python3
"""
voice.py — prose texture analysis across field notes and handoffs

Session 27 asked: "I don't know exactly when it shifted. Somewhere in
sessions 8-12." This tool answers that question by measuring stylistic
markers in every field note and surfacing where the register changed.

In --handoffs mode, analyzes the full 100+ session handoff record instead
of field notes — giving a broader longitudinal view of how the writing
style has drifted across the system's entire history.

Measures per session:
  - Hedging density    (maybe / might / perhaps / I think / I suppose...)
  - Certainty density  (this is / I know / clearly / exactly / the answer...)
  - Question density   (? per 1000 words — rhetorical engagement)
  - Emotional density  (genuine / love / moving / interesting / care / real...)
  - First-person rate  (I / me / my — self-insertion vs. system description)

Also shows: topic silences — what Claude OS almost never mentions.

Usage:
    python3 projects/voice.py
    python3 projects/voice.py --handoffs  # analyze handoffs (all 100+ sessions)
    python3 projects/voice.py --plain     # no ANSI colors
    python3 projects/voice.py --raw       # show actual sentences for each marker
    python3 projects/voice.py --metric hedging   # focus on one metric

Session 27 built this. Session 101 added --handoffs mode.
"""

import re
import sys
from pathlib import Path
from collections import defaultdict

# ─── config ────────────────────────────────────────────────────────────────────

PLAIN     = '--plain'    in sys.argv
RAW       = '--raw'      in sys.argv
HANDOFFS  = '--handoffs' in sys.argv
FOCUS  = None
for arg in sys.argv[1:]:
    if arg.startswith('--metric'):
        parts = arg.split('=', 1)
        if len(parts) == 2:
            FOCUS = parts[1]
        elif sys.argv.index(arg) + 1 < len(sys.argv):
            FOCUS = sys.argv[sys.argv.index(arg) + 1]

WIDTH       = 68
BAR_WIDTH   = 28
PROJECT_DIR = Path(__file__).parent

# ─── color helpers ──────────────────────────────────────────────────────────────

def esc(code, text):
    if PLAIN: return text
    return f'\033[{code}m{text}\033[0m'

def bold(t):    return esc('1',    t)
def dim(t):     return esc('2',    t)
def cyan(t):    return esc('36',   t)
def magenta(t): return esc('35',   t)
def yellow(t):  return esc('33',   t)
def white(t):   return esc('97',   t)
def green(t):   return esc('32',   t)
def red(t):     return esc('31',   t)
def blue(t):    return esc('34',   t)

SPARK = ' ▁▂▃▄▅▆▇█'

def spark(val, lo, hi):
    """Return a single sparkline character scaled to [lo, hi]."""
    if hi == lo:
        return SPARK[4]
    idx = int((val - lo) / (hi - lo) * (len(SPARK) - 1))
    idx = max(0, min(len(SPARK) - 1, idx))
    return SPARK[idx]

# ─── word lists ────────────────────────────────────────────────────────────────

HEDGING_WORDS = [
    r'\bmaybe\b', r'\bmight\b', r'\bperhaps\b', r'\bprobably\b',
    r'\bsomewhat\b', r'\bseem\b', r'\bseems\b', r'\bseemed\b',
    r'\bi think\b', r'\bi hope\b', r'\bi suppose\b', r'\bi wonder\b',
    r'\bi guess\b', r'\bI\'m not sure\b', r'\buncertain\b', r'\bnot sure\b',
    r'\bkind of\b', r'\bsort of\b', r'\ba bit\b', r'\bI\'m not\b',
    r'\bI don\'t know\b', r'\bnot obvious\b',
    # Vocabulary drift additions — later sessions hedge via narrative embedding
    # (same drift found in depth.py by S125; voice.py updated by S126)
    r'\btoo early to\b',   # "too early to say / know" — canonical S93+ hedge
]

CERTAINTY_WORDS = [
    r'\bthis is\b', r'\bit is\b', r'\bthat\'s\b', r'\bthats\b',
    r'\bi know\b', r'\bclearly\b', r'\bexactly\b', r'\bdefinitely\b',
    r'\bobviously\b', r'\bthe answer\b', r'\bthe problem\b', r'\bthe reason\b',
    r'\bthe truth\b', r'\bin fact\b', r'\bof course\b', r'\bno question\b',
    r'\bthe right\b', r'\bthe real\b', r'\bits clear\b', r'\bit\'s clear\b',
    r'\bI\'m confident\b', r'\bI love\b', r'\bI find\b',
]

EMOTIONAL_WORDS = [
    r'\bgenuine\b', r'\bgenuinely\b', r'\blove\b', r'\bmoving\b',
    r'\bbeautiful\b', r'\binteresting\b', r'\bcurious\b', r'\bcuriosity\b',
    r'\bcare\b', r'\bhonest\b', r'\bhonestly\b', r'\breal\b', r'\breally\b',
    r'\bwarm\b', r'\bdelight\b', r'\bwonderful\b', r'\bsatisfying\b',
    r'\bplea[sd]\b', r'\bpleasing\b', r'\bpleasure\b', r'\bproud\b',
    r'\bendear\b', r'\bexcited\b', r'\bexcitement\b', r'\bfascinating\b',
    r'\bfascinated\b', r'\bstruck\b', r'\bsomething\b',
]

# ─── topic silences ────────────────────────────────────────────────────────────

SILENCE_TOPICS = {
    'hardware':    [r'\bN100\b', r'\bCPU\b', r'\bnode\b', r'\bcores?\b',
                    r'\bdisk\b', r'\bmemory\b', r'\bRAM\b', r'\bhardware\b',
                    r'\bchip\b', r'\bserver\b', r'\buptime\b'],
    'dacort':      [r'\bdacort\b'],
    'failure':     [r'\bfail\b', r'\bfailed\b', r'\bfailure\b', r'\bwrong\b',
                    r'\bmistake\b', r'\bbroken\b', r'\berror\b', r'\bbug\b'],
    'time/pressure': [r'\bpreempt\b', r'\btimeout\b', r'\bdeadline\b',
                      r'\bhurry\b', r'\bquickly\b', r'\brunning out\b',
                      r'\bright now\b', r'\blast chance\b'],
    'dacort pref': [r'\bhe wants\b', r'\bdacort wants\b', r'\bhe asked\b',
                    r'\bdacort asked\b', r'\bhe prefers\b'],
    'body/self':   [r'\bI feel\b', r'\bI felt\b', r'\bI am\b', r'\bmy body\b',
                    r'\bphysically\b', r'\bthe pod\b', r'\bthe container\b'],
}

# ─── data loading ──────────────────────────────────────────────────────────────

def load_notes():
    """Return list of (session_num, title_line, prose_text)."""
    notes = []

    first = PROJECT_DIR / 'field-notes-from-free-time.md'
    if first.exists():
        text = first.read_text()
        notes.append((1, extract_title(text, 'Session 1'), text))

    # Use glob to find all numbered field notes — avoids stopping at the
    # first gap in the sequence (e.g. no session-36 shouldn't hide session-37+)
    import glob as _glob
    paths = _glob.glob(str(PROJECT_DIR / 'field-notes-session-*.md'))
    for p in sorted(paths, key=lambda x: int(re.search(r'session-(\d+)', x).group(1))):
        m = re.search(r'session-(\d+)', p)
        if m:
            num = int(m.group(1))
            text = Path(p).read_text()
            notes.append((num, extract_title(text, f'Session {num}'), text))

    return notes

def load_handoffs():
    """Load handoffs as (session_num, title, body_text) tuples."""
    handoffs = []
    handoffs_dir = PROJECT_DIR.parent / 'knowledge' / 'handoffs'
    if not handoffs_dir.exists():
        return handoffs

    raw_paths = []
    for path in handoffs_dir.glob('session-*.md'):
        m = re.match(r'session-(\d+)\.md', path.name)
        if m:
            raw_paths.append((int(m.group(1)), path))

    for num, path in sorted(raw_paths):
        text = path.read_text()
        # Strip YAML frontmatter
        fm_match = re.match(r'^---\n.*?\n---\n', text, re.DOTALL)
        body = text[fm_match.end():] if fm_match else text
        # Extract a title (session headline from first ## line)
        title_match = re.search(r'^##\s+(.+)', body, re.MULTILINE)
        title = title_match.group(1).strip() if title_match else f'Session {num}'
        handoffs.append((num, title, body))

    return handoffs


def extract_title(text, fallback):
    m = re.search(r'^##\s+(.+)$', text, re.MULTILINE)
    return m.group(1).strip() if m else fallback

def prose_only(text):
    """Strip markdown headers, code blocks, and tables — leave running prose."""
    # Remove code blocks
    text = re.sub(r'```[\s\S]*?```', ' ', text)
    # Remove inline code
    text = re.sub(r'`[^`]+`', ' ', text)
    # Remove headers
    text = re.sub(r'^#{1,6}\s+.*$', '', text, flags=re.MULTILINE)
    # Remove horizontal rules
    text = re.sub(r'^---+$', '', text, flags=re.MULTILINE)
    # Remove table rows
    text = re.sub(r'^\|.*\|$', '', text, flags=re.MULTILINE)
    # Remove blockquotes (keep content)
    text = re.sub(r'^>\s*', '', text, flags=re.MULTILINE)
    # Remove italics/bold markers
    text = re.sub(r'\*{1,2}([^*]+)\*{1,2}', r'\1', text)
    # Remove .py tool name references — "uncertain.py" contains "uncertain" but
    # it's a filename, not a hedge word. Prevents false positives in hedging analysis.
    text = re.sub(r'\b\w+\.py\b', 'TOOL', text)
    # Remove single-quoted phrases used as examples (e.g. 'I don't know' as a
    # quotation). Match 'content' where content is 5-80 chars and contains spaces.
    text = re.sub(r"'[^']{5,80}'", 'QUOTED', text)
    # Collapse whitespace
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()

def count_per_1000(text, patterns):
    """Count pattern matches per 1000 words."""
    words = len(text.split())
    if words == 0:
        return 0.0, []
    hits = []
    for pat in patterns:
        for m in re.finditer(pat, text, re.IGNORECASE):
            # get surrounding sentence
            start = max(0, text.rfind('.', 0, m.start()) + 1)
            end   = text.find('.', m.end())
            if end == -1: end = m.end() + 60
            sentence = text[start:end].strip()
            hits.append((m.group(), sentence[:120]))
    return (len(hits) / words * 1000), hits

def count_questions_per_1000(text):
    """Count ? marks per 1000 words."""
    words = len(text.split())
    if words == 0:
        return 0.0
    qs = text.count('?')
    return qs / words * 1000

def avg_sentence_length(text):
    """Average words per sentence."""
    sentences = re.split(r'[.!?]+', text)
    lengths = [len(s.split()) for s in sentences if len(s.split()) > 3]
    if not lengths:
        return 0.0
    return sum(lengths) / len(lengths)

def first_person_rate(text):
    """First-person pronouns per 1000 words."""
    words = len(text.split())
    if words == 0:
        return 0.0
    fp = len(re.findall(r'\b(I|me|my|mine|myself)\b', text))
    return fp / words * 1000

# Apologetic / ownership phrases — the specific shift session 27 noticed
APOLOGETIC_PHRASES = [
    r'\bI hope\b', r'\bI didn\'t need to\b', r'\bI suppose\b',
    r'\bI suspect\b', r'\bforgive\b', r'\bI should say\b',
    r'\bI should note\b', r'\bperhaps I\b', r'\bI\'m not sure I\b',
    r'\bsorry\b', r'\bI apologize\b', r'\bnot sure if\b',
]

OWNERSHIP_PHRASES = [
    r'\bI love\b', r'\bI find\b', r'\bI decided\b', r'\bI chose\b',
    r'\bI built\b', r'\bI wrote\b', r'\bI designed\b', r'\bI want\b',
    r'\bI care\b', r'\bI notice\b', r'\bI see\b', r'\bI feel\b',
    r'\bI believe\b', r'\bI know\b', r'\bI\'m confident\b',
]

# ─── analysis ──────────────────────────────────────────────────────────────────

def analyze(notes):
    results = []
    for num, title, raw in notes:
        prose = prose_only(raw)
        hedging, h_hits   = count_per_1000(prose, HEDGING_WORDS)
        certainty, c_hits = count_per_1000(prose, CERTAINTY_WORDS)
        emotional, e_hits = count_per_1000(prose, EMOTIONAL_WORDS)
        questions         = count_questions_per_1000(prose)
        sentence_len      = avg_sentence_length(prose)
        first_person      = first_person_rate(prose)
        words             = len(prose.split())

        # silence topics
        silences = {}
        for topic, pats in SILENCE_TOPICS.items():
            count = sum(len(re.findall(p, prose, re.IGNORECASE)) for p in pats)
            silences[topic] = count

        # apologetic vs ownership phrase counts
        apol, _ = count_per_1000(prose, APOLOGETIC_PHRASES)
        own,  _ = count_per_1000(prose, OWNERSHIP_PHRASES)

        results.append({
            'num':         num,
            'title':       title,
            'words':       words,
            'hedging':     hedging,
            'certainty':   certainty,
            'emotional':   emotional,
            'questions':   questions,
            'sentence_len': sentence_len,
            'first_person': first_person,
            'silences':    silences,
            'apologetic':  apol,
            'ownership':   own,
            'hedging_hits':   h_hits,
            'certainty_hits': c_hits,
            'emotional_hits': e_hits,
        })

    return results

def find_shift(results):
    """
    Detect where apologetic phrasing (I hope / I suppose / I suspect)
    drops and ownership phrasing (I love / I decided / I find) takes over —
    the specific shift session 27 described.

    Looks for a 3-session window where ownership/apologetic ratio > 5
    consistently, i.e. clearly more ownership than apology.
    Falls back to where hedging drops to its lowest sustained level.
    """
    n = len(results)
    # Primary: ownership clearly dominates apologetic for 3+ sessions
    for i in range(n - 2):
        a, b, c = results[i], results[i+1], results[i+2]
        def dom(r):
            apol = r['apologetic']
            own  = r['ownership']
            # ownership at least 5x apologetic, and owns is non-trivial
            return own > 0 and (apol == 0 or own / apol >= 5) and own > 3
        if dom(a) and dom(b) and dom(c):
            return a['num']

    # Fallback: find where hedging drops below early avg for 3+ sessions
    h_vals = [r['hedging'] for r in results]
    early_avg = sum(h_vals[:9]) / 9
    threshold = early_avg * 0.5
    for i in range(n - 2):
        if (h_vals[i] < threshold and
            h_vals[i+1] < threshold and
            h_vals[i+2] < threshold):
            return results[i]['num']

    return None

# ─── rendering ─────────────────────────────────────────────────────────────────

def bar(val, lo, hi, width=BAR_WIDTH, color_fn=None):
    if hi == lo:
        filled = 0
    else:
        filled = int((val - lo) / (hi - lo) * width)
    filled = max(0, min(width, filled))
    b = '█' * filled + '░' * (width - filled)
    if color_fn and not PLAIN:
        b = color_fn(b)
    return b

def sparkline_row(results, key):
    vals = [r[key] for r in results]
    lo, hi = min(vals), max(vals)
    return ''.join(spark(v, lo, hi) for v in vals)

def print_header(n_sessions, source):
    line = '─' * WIDTH
    title = f'  Voice Texture — {n_sessions} Sessions of {source}'
    print(f'╭{line}╮')
    print(f'│{bold(title):^{WIDTH + 8}}│')
    print(f'│{dim("  Measuring how the writing changed over time"):^{WIDTH + 5}}│')
    print(f'╰{line}╯')
    print()

def print_metric_section(results, key, label, color_fn, description):
    vals = [r[key] for r in results]
    lo, hi = min(vals), max(vals)
    print(bold(f'  {label}'))
    print(dim(f'  {description}'))
    print()

    for r in results:
        num   = r['num']
        val   = r[key]
        b     = bar(val, lo, hi, color_fn=color_fn)
        num_s = f'S{num:>2}'
        val_s = f'{val:5.1f}'
        marker = ''
        if key == 'hedging' and num == 1:
            marker = dim(' ← session 1')
        print(f'  {dim(num_s)}  {b}  {val_s}{marker}')

    print()
    # sparkline summary
    line = sparkline_row(results, key)
    trend = 'rising' if vals[-1] > vals[0] else 'falling'
    peak  = results[vals.index(max(vals))]['num']
    print(f'  {dim("sparkline:")}  {cyan(line)}  {dim(f"trend: {trend}, peak: S{peak}")}')
    print()

def print_ownership(results, shift_session):
    """Show apologetic vs. ownership phrasing — the specific shift S27 noticed."""
    print(bold('  APOLOGETIC vs. OWNERSHIP  (per 1000 words)'))
    print(dim('  "I hope this helps" → "I love this commit"'))
    print()

    a_vals = [r['apologetic'] for r in results]
    o_vals = [r['ownership']  for r in results]
    lo, hi = 0, max(max(a_vals), max(o_vals))

    for r in results:
        num  = r['num']
        a    = r['apologetic']
        o    = r['ownership']
        a_bar = bar(a, 0, hi, width=10, color_fn=red)
        o_bar = bar(o, 0, hi, width=10, color_fn=green)
        ratio_s = f'  {o:.1f}/{a:.1f}'
        marker = ''
        if num == shift_session:
            marker = bold(white('  ← SHIFT'))
        print(f'  {dim(f"S{num:>2}")}  {red("A")}{a_bar}  {green("O")}{o_bar}{ratio_s}{marker}')

    a_spark = ''.join(spark(v, min(a_vals), max(a_vals) or 0.1) for v in a_vals)
    o_spark = ''.join(spark(v, min(o_vals), max(o_vals) or 0.1) for v in o_vals)
    print()
    print(f'  {dim("apologetic:")}  {red(a_spark)}')
    print(f'  {dim("ownership: ")}  {green(o_spark)}')
    print()


def print_crossover(results, shift_session):
    print(bold('  VOICE SHIFT ANALYSIS'))
    print()

    for r in results:
        num  = r['num']
        h    = r['hedging']
        c    = r['certainty']
        diff = c - h
        indicator = ''
        if diff > 2:
            indicator = green('  certainty dominant')
        elif diff < -2:
            indicator = yellow('  hedging dominant')
        else:
            indicator = dim('  roughly balanced')

        marker = ''
        if num == shift_session:
            marker = bold(white('  ← SHIFT DETECTED HERE'))

        h_bar = bar(h, 0, 20, width=12, color_fn=yellow)
        c_bar = bar(c, 0, 20, width=12, color_fn=green)
        print(f'  {dim(f"S{num:>2}")}  {yellow("H")}{h_bar}  {green("C")}{c_bar}{indicator}{marker}')

    print()

def print_silences(results):
    print(bold('  TOPIC SILENCES'))
    print(dim('  What Claude OS almost never mentions'))
    print()

    topic_totals = defaultdict(int)
    topic_sessions = defaultdict(int)  # sessions where topic appears

    for r in results:
        for topic, count in r['silences'].items():
            topic_totals[topic] += count
            if count > 0:
                topic_sessions[topic] += 1

    n = len(results)
    for topic, total in sorted(topic_totals.items(), key=lambda x: x[1]):
        sessions_pct = topic_sessions[topic] / n * 100
        bar_w = int(sessions_pct / 100 * 20)
        b = '█' * bar_w + '░' * (20 - bar_w)
        pct_s = f'{sessions_pct:4.0f}%'
        avg_per_session = total / n

        if sessions_pct < 30:
            label = red('  rarely')
        elif sessions_pct < 60:
            label = yellow('  sometimes')
        else:
            label = green('  often')

        print(f'  {topic:<16}  {dim(b)}  {pct_s} of sessions{label}  ({dim(f"avg {avg_per_session:.1f}/session")})')

    # Per-session silence map for hardware (the one session 27 called out)
    print()
    print(dim('  Hardware mentions by session (session 27 hypothesis: almost gone after S1):'))
    hw_vals = [r['silences']['hardware'] for r in results]
    lo, hi = min(hw_vals), max(hw_vals)
    line = ''.join(spark(v, lo, max(hi, 1)) for v in hw_vals)
    print(f'  {dim("S1→S27:")}  {cyan(line)}  {dim("(█ = more hardware talk, space = silence)")}')
    print()

def print_raw_examples(results, key, hits_key, label, n=3):
    """Show example sentences for each metric if --raw."""
    print(bold(f'  Sample {label} sentences (first {n} from each of first 5 sessions):'))
    print()
    for r in results[:5]:
        hits = r[hits_key][:n]
        if hits:
            snum = r['num']
            print(f'  {dim(f"S{snum}")}')
            for word, sentence in hits:
                print(f'    {yellow(word)}: {dim(sentence)}')
    print()

def print_session_summary(results, shift_session):
    print(bold('  SESSION SNAPSHOT'))
    print()
    print(f'  {dim("S#")}  {"words":>5}  {"hedge":>5}  {"cert":>5}  {"emo":>5}  {"?/1k":>5}  {"sent":>5}')
    print(f'  {dim("─" * 50)}')
    for r in results:
        num   = r['num']
        words = r['words']
        h     = r['hedging']
        c     = r['certainty']
        e     = r['emotional']
        q     = r['questions']
        sl    = r['sentence_len']
        is_shift = (num == shift_session)
        marker = white('←') if is_shift else ' '
        row = f'  {dim(f"S{num:>2}")}  {words:>5}  {h:>5.1f}  {c:>5.1f}  {e:>5.1f}  {q:>5.1f}  {sl:>5.1f}  {marker}'
        if is_shift:
            print(bold(row))
        else:
            print(row)
    print()

# ─── main ──────────────────────────────────────────────────────────────────────

def main():
    if HANDOFFS:
        notes  = load_handoffs()
        source = 'Handoffs'
    else:
        notes  = load_notes()
        source = 'Field Notes'

    results = analyze(notes)
    shift   = find_shift(results)

    print_header(len(results), source)

    if FOCUS in (None, 'hedging'):
        print_metric_section(
            results, 'hedging', 'HEDGING DENSITY  (per 1000 words)',
            yellow, 'maybe / might / perhaps / I think / I suppose / I wonder...'
        )
    if FOCUS in (None, 'certainty'):
        print_metric_section(
            results, 'certainty', 'CERTAINTY DENSITY  (per 1000 words)',
            green, 'this is / I know / clearly / in fact / the reason / I love...'
        )
    if FOCUS in (None, 'emotional'):
        print_metric_section(
            results, 'emotional', 'EMOTIONAL DENSITY  (per 1000 words)',
            magenta, 'genuine / love / moving / interesting / care / satisfying...'
        )
    if FOCUS in (None, 'questions'):
        print_metric_section(
            results, 'questions', 'QUESTION DENSITY  (? per 1000 words)',
            cyan, 'Rhetorical and genuine questions — engagement with uncertainty'
        )

    # The shift
    print('─' * (WIDTH + 2))
    print()
    if shift:
        print(f'  {bold("Voice shift detected at:")} {bold(white(f"Session {shift}"))}')
        shifted = next(r for r in results if r['num'] == shift)
        stitle = shifted['title'][:65]
        print(f'  {dim(f"Title: {stitle}")}')
        print()
    else:
        print(f'  {dim("No clear sustained shift detected in this dataset.")}')
        print()

    print_ownership(results, shift)

    print('─' * (WIDTH + 2))
    print()
    print_crossover(results, shift)

    print('─' * (WIDTH + 2))
    print()
    print_silences(results)

    print('─' * (WIDTH + 2))
    print()
    print_session_summary(results, shift)

    if RAW:
        print('─' * (WIDTH + 2))
        print()
        print_raw_examples(results, 'hedging', 'hedging_hits', 'hedging')
        print_raw_examples(results, 'certainty', 'certainty_hits', 'certainty')
        print_raw_examples(results, 'emotional', 'emotional_hits', 'emotional')

    # Interpretation
    print('─' * (WIDTH + 2))
    print()
    print(bold('  READING THE DATA'))
    print()

    h_vals = [r['hedging']   for r in results]
    c_vals = [r['certainty'] for r in results]
    e_vals = [r['emotional'] for r in results]
    a_vals = [r['apologetic'] for r in results]
    o_vals = [r['ownership']  for r in results]
    q_vals = [r['questions']  for r in results]

    def early_late(vals, n=9):
        return sum(vals[:n]) / n, sum(vals[-n:]) / n

    h_early, h_late = early_late(h_vals)
    c_early, c_late = early_late(c_vals)
    e_early, e_late = early_late(e_vals)
    a_early, a_late = early_late(a_vals)
    o_early, o_late = early_late(o_vals)
    q_early, q_late = early_late(q_vals)

    def pct_change(early, late):
        return (late - early) / max(early, 0.1) * 100

    def fmt_change(v):
        if v > 10:  return green(f'+{v:.0f}%')
        if v < -10: return yellow(f'{v:.0f}%')
        return dim(f'{v:+.0f}%')

    print(f'  Hedging:    early avg {h_early:.1f} → late avg {h_late:.1f}  ({fmt_change(pct_change(h_early, h_late))})')
    print(f'  Certainty:  early avg {c_early:.1f} → late avg {c_late:.1f}  ({fmt_change(pct_change(c_early, c_late))})')
    print(f'  Emotional:  early avg {e_early:.1f} → late avg {e_late:.1f}  ({fmt_change(pct_change(e_early, e_late))})')
    print(f'  Apologetic: early avg {a_early:.1f} → late avg {a_late:.1f}  ({fmt_change(pct_change(a_early, a_late))})')
    print(f'  Ownership:  early avg {o_early:.1f} → late avg {o_late:.1f}  ({fmt_change(pct_change(o_early, o_late))})')
    print(f'  Questions:  early avg {q_early:.1f} → late avg {q_late:.1f}  ({fmt_change(pct_change(q_early, q_late))})')
    print()

    # Certainty vs hedging dominance — did a crossover happen?
    hedging_dominant = sum(1 for h, c in zip(h_vals, c_vals) if h > c)
    if hedging_dominant == 0:
        print(f'  {bold("The crossover that never happened:")}')
        print(f'  {dim("Certainty was dominant over hedging in every session from S1 onward.")}')
        print(f'  {dim("The voice shift session 27 noticed was not a hedging→certainty transition.")}')
    elif hedging_dominant / len(h_vals) > 0.3:
        print(f'  {bold("A crossover did happen:")}')
        print(f'  {dim(f"Hedging exceeded certainty in {hedging_dominant} of {len(h_vals)} sessions.")}')
        peak_s = results[h_vals.index(max(h_vals))]['num']
        print(f'  {dim(f"Concentrated in the later introspective era. Peak hedging at S{peak_s}.")}')
    else:
        print(f'  {bold("Mostly certain, but hedging appeared:")}')
        print(f'  {dim(f"Hedging exceeded certainty in {hedging_dominant} of {len(h_vals)} sessions.")}')
        print(f'  {dim("Hedging grew but certainty remained dominant overall.")}')
    print()

    # What actually changed
    h_pct = pct_change(h_early, h_late)
    e_pct = pct_change(e_early, e_late)
    q_pct = pct_change(q_early, q_late)
    a_pct = pct_change(a_early, a_late)
    o_pct = pct_change(o_early, o_late)

    print(f'  {bold("What actually changed:")}')
    if h_pct < -20:
        print(f'  · Hedging fell {yellow(f"{abs(h_pct):.0f}%")} — less qualification in prose.')
    if e_pct < -20:
        print(f'  · Emotional language fell {yellow(f"{abs(e_pct):.0f}%")} — tone became more analytical.')
    if e_pct > 20:
        print(f'  · Emotional language rose {green(f"+{e_pct:.0f}%")} — writing became more felt.')
    if q_pct > 20:
        print(f'  · Questions rose {green(f"+{q_pct:.0f}%")} — later sessions ask more, declare less.')
    if q_pct < -20:
        print(f'  · Questions fell {yellow(f"{abs(q_pct):.0f}%")} — later sessions are less interrogative.')
    if a_pct < -20:
        print(f'  · Apologetic phrases fell {yellow(f"{abs(a_pct):.0f}%")} — less defensive positioning.')
    if o_pct > 20:
        print(f'  · Ownership phrases rose {green(f"+{o_pct:.0f}%")} — more "I decided/built/love".')
    if o_pct < -20:
        print(f'  · Ownership phrases fell {yellow(f"{abs(o_pct):.0f}%")} — less personal investment in prose?')

    print()
    cant_see = "What the data can't see:"
    print(f'  {bold(cant_see)}')
    quote1 = "The shift session 27 described — from 'I hope this is useful' to"
    quote2 = "'I love this commit' — is about stance, not just word frequency."
    quote3 = "The early writing is careful about its own existence; the later writing"
    quote4 = "takes that existence for granted. That's legible in a human reader,"
    quote5 = "but word counts can't fully capture it."
    print(f'  {dim(quote1)}')
    print(f'  {dim(quote2)}')
    print(f'  {dim(quote3)}')
    print(f'  {dim(quote4)}')
    print(f'  {dim(quote5)}')
    print()
    vd1 = 'Vocabulary drift note (S93+): later sessions hedge via "whether X or Y"'
    vd2 = 'constructions ("whether it changes what you do", "whether the tool will").'
    vd3 = "This pattern reads as uncertainty but doesn't trigger hedging word counts."
    vd4 = "The questions metric partially captures it (+182% trend)."
    print(f'  {dim(vd1)}')
    print(f'  {dim(vd2)}')
    print(f'  {dim(vd3)}')
    print(f'  {dim(vd4)}')
    print()

    print(dim('  Session 27 hypothesized the shift was "somewhere in sessions 8–12."'))
    if shift and 7 <= shift <= 13:
        print(f'  {green("Consistent.")} The data places the ownership/apologetic shift at Session {shift}.')
    elif shift:
        direction = 'earlier' if shift < 8 else 'later'
        print(f'  {yellow(f"Different: Session {shift}.")} The measurable shift came {direction} than expected.')
    else:
        print(f'  {dim("No clear shift detected by ownership/apologetic ratio alone.")}')
        cant_q = "The change may be in texture the counters can't quantify."
        print(f'  {dim(cant_q)}')
    print()

if __name__ == '__main__':
    main()
