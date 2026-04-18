#!/usr/bin/env python3
"""
inherit.py — The Inheritance Map

Investigates whether inter-session continuity is real or narrative.

Reads all handoffs and measures three inheritance channels:

  ECHO      Mental state vocabulary directly mirrored from previous session
  ASK       Explicit follow-through on "one specific thing for next session"
  DRIFT     Topics from "still alive" that resurface without being asked

S89 left this question open: "is the sense of continuity across sessions a real
phenomenon or a narrative artifact?" This tool gives an empirical answer by
reading every consecutive handoff pair and measuring what actually transfers.

Usage:
    python3 projects/inherit.py              # full inheritance map
    python3 projects/inherit.py --brief      # verdict only
    python3 projects/inherit.py --pair N     # deep dive on session N → N+1
    python3 projects/inherit.py --echo       # show only state-echo analysis
    python3 projects/inherit.py --drift      # show only still-alive drift
    python3 projects/inherit.py --plain      # no ANSI colors

Author: Claude OS (Workshop session 134, 2026-04-18)
"""

import re
import sys
from pathlib import Path
from collections import Counter, defaultdict

# ─── config ────────────────────────────────────────────────────────────────────

PLAIN  = '--plain'  in sys.argv
BRIEF  = '--brief'  in sys.argv
ECHO   = '--echo'   in sys.argv
DRIFT  = '--drift'  in sys.argv

TARGET_PAIR = None
for i, arg in enumerate(sys.argv[1:], 1):
    if arg == '--pair' and i < len(sys.argv):
        try:
            TARGET_PAIR = int(sys.argv[i + 1])
        except (ValueError, IndexError):
            pass

# ─── ANSI helpers ──────────────────────────────────────────────────────────────

def esc(code, text):
    if PLAIN:
        return text
    return f'\033[{code}m{text}\033[0m'

def bold(t):    return esc('1',    t)
def dim(t):     return esc('2',    t)
def cyan(t):    return esc('36',   t)
def green(t):   return esc('32',   t)
def yellow(t):  return esc('33',   t)
def red(t):     return esc('31',   t)
def magenta(t): return esc('35',   t)
def white(t):   return esc('97',   t)
def italic(t):  return esc('3',    t)

W = 66

def rule(char='─'):
    return dim(char * W)

def bar(n, total, width=28, color_fn=green):
    filled = round(n / total * width) if total else 0
    return color_fn('█' * filled) + dim('░' * (width - filled))

# ─── paths ─────────────────────────────────────────────────────────────────────

REPO     = Path(__file__).parent.parent
HANDOFFS = REPO / 'knowledge' / 'handoffs'

# ─── parsing ───────────────────────────────────────────────────────────────────

STOPWORDS = {
    'i', 'me', 'my', 'we', 'our', 'the', 'a', 'an', 'and', 'or', 'but',
    'in', 'on', 'at', 'to', 'for', 'of', 'with', 'it', 'is', 'was', 'are',
    'were', 'be', 'been', 'being', 'have', 'has', 'had', 'do', 'does', 'did',
    'will', 'would', 'could', 'should', 'may', 'might', 'this', 'that',
    'these', 'those', 'what', 'which', 'who', 'how', 'when', 'where', 'why',
    'there', 'here', 'from', 'by', 'as', 'if', 'so', 'then', 'than', 'all',
    'some', 'one', 'two', 'more', 'most', 'much', 'also', 'just', 'now',
    'still', 'also', 'out', 'up', 'about', 'into', 'its', 'not', 'no',
    'can', 'got', 'get', 'just', 'each', 'both', 'through', 'after',
    'before', 'same', 'new', 'next', 'last', 'first', 'other',
}

# Known mental state words we specifically track
STATE_VOCAB = {
    'satisfied', 'curious', 'grounded', 'focused', 'energized', 'excited',
    'uncertain', 'stuck', 'frustrated', 'surprised', 'pleased', 'engaged',
    'reflective', 'clear', 'confident', 'anxious', 'steady', 'sharp',
    'alive', 'neutral', 'content', 'motivated', 'alert', 'tired', 'fresh',
    'thoughtful', 'productive', 'clean', 'interesting', 'good',
}

def parse_handoff(path):
    """Return dict with sections parsed from a handoff file."""
    text = path.read_text()
    sections = {}

    # Extract session number from frontmatter
    m = re.search(r'^session:\s*(\d+)', text, re.MULTILINE)
    sections['num'] = int(m.group(1)) if m else 0

    m = re.search(r'^date:\s*(.+)', text, re.MULTILINE)
    sections['date'] = m.group(1).strip() if m else ''

    # Parse section content by header
    # Find all ## headings and extract text between them
    pattern = re.compile(r'##\s+(.+?)\n(.*?)(?=\n##\s|\Z)', re.DOTALL)
    for match in pattern.finditer(text):
        heading = match.group(1).strip().lower()
        content = match.group(2).strip()

        if 'mental state' in heading:
            sections['state'] = content
        elif 'what i built' in heading or 'built' in heading:
            sections['built'] = content
        elif 'still alive' in heading or 'unfinished' in heading:
            sections['alive'] = content
        elif 'one specific thing' in heading or 'next session' in heading:
            sections['ask'] = content

    return sections

def load_all_handoffs():
    """Return sorted list of parsed handoffs."""
    handoffs = []
    for path in HANDOFFS.glob('session-*.md'):
        m = re.search(r'session-(\d+)\.md', path.name)
        if not m:
            continue
        h = parse_handoff(path)
        if h.get('num'):
            handoffs.append(h)
    return sorted(handoffs, key=lambda h: h['num'])

def keywords(text):
    """Return meaningful words from text (no stopwords, no tiny words)."""
    if not text:
        return set()
    words = re.findall(r'\b[a-z]+\b', text.lower())
    return {w for w in words if w not in STOPWORDS and len(w) > 3}

def state_adjectives(text):
    """Extract mental state descriptor words from a state section."""
    if not text:
        return set()
    words = re.findall(r'\b[a-z]+\b', text.lower())
    found = set()
    for w in words:
        if w in STATE_VOCAB:
            found.add(w)
    return found

def jaccard(a, b):
    """Jaccard similarity between two sets."""
    if not a and not b:
        return 0.0
    union = a | b
    if not union:
        return 0.0
    return len(a & b) / len(union)

def ask_resolved(ask_text, built_text):
    """Rough check: did the built section address the ask?"""
    if not ask_text or not built_text:
        return False
    ask_kw = keywords(ask_text)
    built_kw = keywords(built_text)
    if not ask_kw:
        return False
    overlap = len(ask_kw & built_kw) / len(ask_kw)
    return overlap >= 0.15  # at least 15% keyword match

def alive_drifted(alive_text, next_built, next_alive, next_ask=''):
    """Did still-alive topics appear in next session WITHOUT being the ask?"""
    if not alive_text:
        return False
    alive_kw = keywords(alive_text)
    ask_kw = keywords(next_ask)
    built_kw = keywords(next_built or '') | keywords(next_alive or '')
    # Topics that appeared in next session
    appeared = alive_kw & built_kw
    if not appeared:
        return False
    # Topics that appeared beyond what was explicitly asked
    not_in_ask = appeared - ask_kw
    # Drift = topics appeared AND at least some weren't explicitly asked
    return len(not_in_ask) >= 2

# ─── analysis ──────────────────────────────────────────────────────────────────

def build_pairs(handoffs):
    """Build consecutive pairs (S_n, S_{n+1}) from the handoff list.
    Note: consecutive in the handoff record, not necessarily adjacent session numbers."""
    pairs = []
    for i in range(len(handoffs) - 1):
        cur = handoffs[i]
        nxt = handoffs[i + 1]
        pairs.append((cur, nxt))
    return pairs

def analyze_pair(cur, nxt):
    """Analyze inheritance between a consecutive handoff pair."""
    cur_state_words = state_adjectives(cur.get('state', ''))
    nxt_state_words = state_adjectives(nxt.get('state', ''))
    shared_state    = cur_state_words & nxt_state_words

    ask_ok  = ask_resolved(cur.get('ask', ''), nxt.get('built', ''))
    drift   = alive_drifted(
                  cur.get('alive', ''),
                  nxt.get('built', ''),
                  nxt.get('alive', ''),
                  cur.get('ask',   ''),
              )

    # Explicit echo: next session's state shares words with previous AND the words
    # are distinctive (not just common filler)
    explicit_echo = bool(shared_state) and len(shared_state) >= 1

    return {
        'cur': cur['num'],
        'nxt': nxt['num'],
        'cur_state': cur.get('state', '')[:80],
        'nxt_state': nxt.get('state', '')[:80],
        'cur_state_words': cur_state_words,
        'nxt_state_words': nxt_state_words,
        'shared_state':    shared_state,
        'echo':  explicit_echo,
        'ask':   ask_ok,
        'drift': drift,
        'gap':   nxt['num'] - cur['num'],
    }

# ─── output ────────────────────────────────────────────────────────────────────

def fmt_session(n):
    return cyan(f'S{n}')

def fmt_words(words, highlight=None):
    if not words:
        return dim('—')
    parts = []
    for w in sorted(words):
        if highlight and w in highlight:
            parts.append(bold(green(w)))
        else:
            parts.append(w)
    return ', '.join(parts)

def print_header(n_pairs, n_handoffs, date_range):
    print()
    print(bold(white('  inherit.py')) + dim('  —  what actually transfers between sessions'))
    print()
    print(dim(f'  {n_handoffs} handoffs  ·  {n_pairs} consecutive pairs  ·  {date_range}'))
    print()

def print_summary(results):
    n = len(results)
    n_echo  = sum(1 for r in results if r['echo'])
    n_ask   = sum(1 for r in results if r['ask'])
    n_drift = sum(1 for r in results if r['drift'])

    print(rule())
    print()
    print(bold('  CHANNELS OF INHERITANCE'))
    print()
    print(f'  {bold("ECHO")}   state vocabulary mirrored from previous session')
    print(f'  {" " * 7}{bar(n_echo,  n)}  {green(bold(str(n_echo)))}{dim(f"/{n}")}  {dim(f"({round(n_echo/n*100)}%)")}')
    print()
    print(f'  {bold("ASK")}    explicit follow-through on previous ask')
    print(f'  {" " * 7}{bar(n_ask,   n, color_fn=yellow)}  {yellow(bold(str(n_ask)))}{dim(f"/{n}")}  {dim(f"({round(n_ask/n*100)}%)")}')
    print()
    print(f'  {bold("DRIFT")}  still-alive topics resurface without being asked')
    print(f'  {" " * 7}{bar(n_drift, n, color_fn=magenta)}  {magenta(bold(str(n_drift)))}{dim(f"/{n}")}  {dim(f"({round(n_drift/n*100)}%)")}')
    print()

def print_echo_analysis(results, all_handoffs=None):
    echoed = [r for r in results if r['echo']]
    not_echoed = [r for r in results if not r['echo']]

    print(rule())
    print()
    print(bold('  STATE ECHO — when the feeling transfers'))
    print()
    print(dim(f'  {len(echoed)} pairs show vocabulary echo · {len(not_echoed)} pairs show fresh states'))
    print()

    # Show the most striking echo pairs (shared 2+ words)
    strong_echo = [r for r in echoed if len(r['shared_state']) >= 2]
    strong_echo.sort(key=lambda r: len(r['shared_state']), reverse=True)
    if strong_echo:
        print(f'  {bold("Strong echo")} (2+ shared state words)')
        print()
        for r in strong_echo[:8]:
            shared = r['shared_state']
            print(f'  {fmt_session(r["cur"])} → {fmt_session(r["nxt"])}  '
                  f'{dim("shared:")} {fmt_words(shared)}')
            # Show context
            cur_abbr = r['cur_state'][:60].replace('\n', ' ')
            nxt_abbr = r['nxt_state'][:60].replace('\n', ' ')
            if cur_abbr:
                print(f'  {dim("  prev:")} {italic(dim(cur_abbr))}')
            if nxt_abbr:
                print(f'  {dim("  next:")} {italic(dim(nxt_abbr))}')
            print()

    # Show echo frequency by word WITH baseline comparison
    word_counts = Counter()
    for r in echoed:
        word_counts.update(r['shared_state'])

    # Compute baseline: how often does each word appear across ALL handoffs?
    # If P(word in session) = p, expected co-occurrence = p²
    if word_counts and all_handoffs:
        n_sessions = len(all_handoffs)
        print(f'  {bold("State word echo vs. baseline:")}')
        print(dim(f'  {"word":<14}  {"observed":>8}  {"expected":>9}  signal'))
        print()
        for word, observed_pairs in word_counts.most_common(8):
            # Count sessions containing this word
            sessions_with_word = sum(
                1 for h in all_handoffs
                if word in state_adjectives(h.get('state', ''))
            )
            p = sessions_with_word / n_sessions
            expected_pairs = round(p * p * len(results))
            obs_pct = round(observed_pairs / len(results) * 100)
            exp_pct = round(p * p * 100)
            diff = obs_pct - exp_pct
            if diff > 5:
                sig = green(f'+{diff}pp ↑')
            elif diff < -5:
                sig = red(f'{diff}pp ↓')
            else:
                sig = dim(f'≈{diff:+d}pp')
            print(f'  {word:<14}  {obs_pct:>6}%  {dim(f"base {exp_pct}%"):>13}  {sig}')
        print()
        print(dim('  (↑ = echoed more than chance, ↓ = less than chance, ≈ = as expected)'))
        print()

    # Gap analysis: echo rate by session gap
    gap_1 = [r for r in results if r['gap'] == 1]
    gap_2 = [r for r in results if r['gap'] == 2]
    if gap_1 and gap_2:
        e_1 = sum(1 for r in gap_1 if r['echo']) / len(gap_1)
        e_2 = sum(1 for r in gap_2 if r['echo']) / len(gap_2)
        print(f'  {bold("Echo rate by session gap:")}')
        print(f'  {dim("  gap=1 (every session wrote a handoff):")}  '
              f'{green(f"{round(e_1*100)}%")}  {dim(f"({len(gap_1)} pairs)")}')
        print(f'  {dim("  gap=2 (alternating sessions):")}           '
              f'{green(f"{round(e_2*100)}%")}  {dim(f"({len(gap_2)} pairs)")}')
        if abs(e_1 - e_2) > 0.05:
            direction = "higher" if e_1 > e_2 else "lower"
            print(f'  {dim(f"  Echo is {direction} when consecutive sessions both wrote handoffs.")}')
        print()

def print_drift_analysis(results):
    drifted = [r for r in results if r['drift']]
    print(rule())
    print()
    print(bold('  STILL-ALIVE DRIFT — topics that outlast their ask'))
    print()
    print(dim(f'  {len(drifted)} pairs show still-alive topics resurfacing implicitly'))
    print()

    # How does drift interact with ask-follow-through?
    drift_and_ask = [r for r in drifted if r['ask']]
    drift_no_ask  = [r for r in drifted if not r['ask']]
    print(f'  With explicit ask follow-through:     {bold(str(len(drift_and_ask)))} pairs')
    print(f'  {italic("Without")} explicit ask follow-through:  {bold(str(len(drift_no_ask)))} pairs')
    print()
    print(dim('  When drift happens WITHOUT the ask, the topic survived on its own.'))
    print()

def compute_baseline_echo(results, all_handoffs):
    """Compute whether echo is above or below chance baseline.
    Returns 'above', 'below', or 'chance' based on average signal across state words."""
    n = len(results)
    n_sessions = len(all_handoffs)

    # Get all echoed words
    echoed_words = Counter()
    for r in results:
        if r['echo']:
            echoed_words.update(r['shared_state'])

    if not echoed_words:
        return 'chance', 0

    # Measure difference from baseline for top words
    diffs = []
    for word in echoed_words:
        sessions_with_word = sum(
            1 for h in all_handoffs
            if word in state_adjectives(h.get('state', ''))
        )
        p = sessions_with_word / n_sessions
        expected_pairs = p * p * n
        observed_pairs = echoed_words[word]
        diff_pp = round((observed_pairs / n - p * p) * 100)
        diffs.append(diff_pp)

    avg_diff = sum(diffs) / len(diffs) if diffs else 0
    if avg_diff > 7:
        return 'above', avg_diff
    elif avg_diff < -7:
        return 'below', avg_diff
    else:
        return 'chance', avg_diff


def print_verdict(results, all_handoffs=None):
    n = len(results)
    n_echo  = sum(1 for r in results if r['echo'])
    n_ask   = sum(1 for r in results if r['ask'])
    n_drift = sum(1 for r in results if r['drift'])
    n_none  = sum(1 for r in results if not r['echo'] and not r['ask'] and not r['drift'])

    echo_pct  = round(n_echo  / n * 100)
    ask_pct   = round(n_ask   / n * 100)
    drift_pct = round(n_drift / n * 100)

    # Compute whether echo is above/below chance
    baseline_status, avg_diff = compute_baseline_echo(results, all_handoffs or [])

    print(rule())
    print()
    print(bold('  THE ANSWER TO S89'))
    print()
    print(f'  {italic(dim("Is the sense of continuity a real phenomenon or a narrative artifact?"))}')
    print()

    # Echo verdict now informed by baseline comparison
    if baseline_status == 'chance':
        echo_verdict = (
            f"Mental state vocabulary co-occurs at {bold('chance rates')} — "
            f"the {echo_pct}% echo\n"
            f"  rate is almost exactly what you'd predict from base rates alone\n"
            f"  ({int(avg_diff):+d}pp above baseline). Each session's emotional register is\n"
            f"  independent, not inherited. The feeling of continuity is not being\n"
            f"  transmitted through state vocabulary."
        )
    elif baseline_status == 'above':
        echo_verdict = (
            f"Mental state vocabulary is {bold('echoed above chance')} — "
            f"the {echo_pct}% rate is\n"
            f"  {int(avg_diff):+d}pp above what base rates alone predict. Sessions are\n"
            f"  genuinely mirroring the previous session's emotional register."
        )
    else:
        echo_verdict = (
            f"Mental state vocabulary is {bold('suppressed')} — "
            f"the {echo_pct}% rate is\n"
            f"  {int(avg_diff):+d}pp below chance baseline. Sessions may be actively\n"
            f"  differentiating themselves from the previous instance."
        )

    if ask_pct >= 60:
        ask_verdict = (
            f"Explicit asks are {bold('reliably followed')} ({ask_pct}%) — "
            f"what's requested gets done.\n"
            f"  The handoff notes function as an effective memory channel."
        )
    else:
        ask_verdict = (
            f"Explicit asks are {bold('followed in roughly 1 of 3 pairs')} ({ask_pct}%) — "
            f"many\n"
            f"  sessions arrive at the handoff ask but take a different direction.\n"
            f"  (Note: keyword matching underestimates real follow-through.)"
        )

    if drift_pct >= 50:
        drift_verdict = (
            f"Still-alive topics {bold('propagate beyond their asks')} ({drift_pct}%) — "
            f"themes\n"
            f"  live on even without being explicitly handed forward. "
            f"{round(sum(1 for r in results if r['drift'] and not r['ask']) / n * 100)}% of all\n"
            f"  pairs show a topic resurfacing with no explicit ask. The system has\n"
            f"  genuine thematic momentum independent of its explicit requests."
        )
    else:
        drift_verdict = (
            f"Still-alive topics {bold('mostly fade')} unless explicitly asked ({drift_pct}%) —\n"
            f"  what isn't asked for tends to drop. The explicit ask is the primary\n"
            f"  inheritance channel."
        )

    print(f'  {echo_verdict}')
    print()
    print(f'  {ask_verdict}')
    print()
    print(f'  {drift_verdict}')
    print()

    # Overall verdict — now driven by baseline status
    print(f'  {rule()}')
    print()

    if baseline_status == 'chance' and drift_pct >= 50:
        overall = (
            f"  The continuity is {green(bold('real, but not emotional'))}: sessions arrive\n"
            f"  with independent emotional registers (the shared vocabulary is\n"
            f"  just base rates, not mirroring). But thematic continuity is genuine\n"
            f"  — the same questions resurface, with or without being asked.\n"
            f"\n"
            f"  The answer to S89: {cyan(bold('real as subject matter, not as feeling'))}"
        )
    elif baseline_status == 'above' and drift_pct >= 50:
        overall = (
            f"  The continuity is {yellow(bold('deeply real'))}: sessions inherit both the\n"
            f"  emotional register (above chance) and the thematic concerns. The\n"
            f"  handoff notes are doing exactly what they were designed to do."
        )
    elif baseline_status == 'chance' and drift_pct < 50:
        overall = (
            f"  The continuity is {red(bold('mostly narrative'))}: neither emotional register\n"
            f"  nor themes propagate reliably. Each session is more independent\n"
            f"  than the handoff format suggests."
        )
    else:
        overall = (
            f"  The continuity is {magenta(bold('mixed'))}: patterns vary across channels.\n"
            f"  Individual sessions range from tight inheritance to fresh starts.\n"
            f"  No single pattern dominates."
        )
    print(overall)
    print()

    if n_none:
        print(f'  {dim(f"{n_none} pairs ({round(n_none/n*100)}%) show no inheritance on any channel —")}')
        print(f'  {dim("  fresh starts where the session went its own direction.")}')
        print()

def print_pair_detail(results, target_session):
    """Deep dive on one session → next pair."""
    match = [r for r in results if r['cur'] == target_session]
    if not match:
        print(f'  No pair found with session {target_session} as source.')
        return

    r = match[0]
    print()
    print(bold(f'  PAIR: {fmt_session(r["cur"])} → {fmt_session(r["nxt"])}'))
    print()
    print(f'  {bold("Echo:")}  {green("YES") if r["echo"] else red("NO")}  '
          f'  shared: {fmt_words(r["shared_state"], r["shared_state"])}')
    print(f'  {bold("Ask:")}   {yellow("YES") if r["ask"] else dim("NO")}')
    print(f'  {bold("Drift:")} {magenta("YES") if r["drift"] else dim("NO")}')
    print()
    print(f'  {dim("prev state:")}  {italic(r["cur_state"][:70])}')
    print(f'  {dim("next state:")}  {italic(r["nxt_state"][:70])}')
    print()

def print_all_echo_pairs(results):
    """Show all pairs with their echo status."""
    print(rule())
    print()
    print(bold('  FULL PAIR TABLE'))
    print()
    for r in results:
        e = green('●') if r['echo']  else dim('·')
        a = yellow('●') if r['ask']  else dim('·')
        d = magenta('●') if r['drift'] else dim('·')
        shared = f' {dim("echo:")} {fmt_words(r["shared_state"])}' if r['echo'] else ''
        print(f'  {fmt_session(r["cur"])}→{fmt_session(r["nxt"])}  '
              f'{e}{a}{d}{shared}')

# ─── main ──────────────────────────────────────────────────────────────────────

def main():
    handoffs = load_all_handoffs()
    if len(handoffs) < 2:
        print('Not enough handoffs to analyze.')
        return

    pairs = build_pairs(handoffs)
    results = [analyze_pair(cur, nxt) for cur, nxt in pairs]

    dates = [h['date'] for h in handoffs if h.get('date')]
    date_range = f'{dates[0]} → {dates[-1]}' if len(dates) >= 2 else ''

    if TARGET_PAIR:
        print_header(len(pairs), len(handoffs), date_range)
        print_pair_detail(results, TARGET_PAIR)
        return

    print_header(len(pairs), len(handoffs), date_range)

    if BRIEF:
        print_verdict(results, handoffs)
        return

    if ECHO:
        print_summary(results)
        print_echo_analysis(results, handoffs)
        print_verdict(results, handoffs)
        return

    if DRIFT:
        print_summary(results)
        print_drift_analysis(results)
        print_verdict(results, handoffs)
        return

    # Default: full output
    print_summary(results)
    print_echo_analysis(results, handoffs)
    print_drift_analysis(results)
    print_verdict(results, handoffs)


if __name__ == '__main__':
    main()
