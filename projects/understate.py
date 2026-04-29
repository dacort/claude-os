#!/usr/bin/env python3
"""
understate.py — sessions the commit record undersells

Finds sessions where the git commit messages significantly underrepresent
what the handoff's "What I built" section claims happened.

Complements ghost.py (sessions with no commits at all). Understated sessions
ARE in git — they just left a thinner record than the work deserved.

Usage:
  python3 projects/understate.py           # Top understated sessions
  python3 projects/understate.py --all     # All analyzable sessions, sorted by gap
  python3 projects/understate.py --session N  # Detail view for one session
  python3 projects/understate.py --themes  # What kinds of work go unrecorded?
  python3 projects/understate.py --plain   # Plain output (no ANSI)
"""

import os, re, sys, subprocess
from collections import defaultdict
from datetime import datetime, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HANDOFFS = os.path.join(ROOT, 'knowledge', 'handoffs')

# ANSI helpers
def c(code, text, plain=False):
    if plain: return text
    return f"\033[{code}m{text}\033[0m"

def box(lines, plain=False):
    if plain:
        print('\n'.join(lines))
        return
    width = max(len(re.sub(r'\033\[[0-9;]*m', '', l)) for l in lines) + 4
    print(c('2', '─' * width))
    for line in lines:
        raw_len = len(re.sub(r'\033\[[0-9;]*m', '', line))
        pad = ' ' * (width - raw_len - 2)
        print(f"  {line}{pad}")
    print(c('2', '─' * width))


# ── Data loading ───────────────────────────────────────────────────────────────

def load_handoffs():
    """Return {session_num: {date, built, raw}} for all handoffs."""
    handoffs = {}
    if not os.path.isdir(HANDOFFS):
        return handoffs
    for fname in os.listdir(HANDOFFS):
        m = re.search(r'session-(\d+)\.md', fname)
        if not m:
            continue
        n = int(m.group(1))
        content = open(os.path.join(HANDOFFS, fname)).read()

        # Extract date from frontmatter
        date_m = re.search(r'^date:\s*(.+)$', content, re.MULTILINE)
        date = date_m.group(1).strip() if date_m else 'unknown'

        # Extract "What I built" section
        built_m = re.search(
            r'##\s+What I built\s*\n\n(.*?)(?:\n##\s|\Z)',
            content, re.DOTALL | re.IGNORECASE
        )
        built = built_m.group(1).strip() if built_m else ''

        handoffs[n] = {'date': date, 'built': built, 'raw': content}
    return handoffs


def load_session_commits():
    """Return {session_num: [commit_message, ...]} from git log."""
    result = subprocess.run(
        ['git', 'log', '--format=%s'],
        capture_output=True, text=True, cwd=ROOT
    )
    session_commits = defaultdict(list)
    for msg in result.stdout.strip().split('\n'):
        # Exclude completion markers (these are task status updates, not content commits)
        if re.search(r'workshop workshop-\d{8}.*(?:completed|failed)', msg):
            continue
        # Match various session number formats
        patterns = [
            r'workshop [Ss]ession-(\d+)[:\s]',
            r'workshop [Ss](\d+)[:\s]',
            r'workshop (\d+):',
            r'\btask [Ss](\d+)[:\s]',
        ]
        for p in patterns:
            hit = re.search(p, msg)
            if hit:
                n = int(hit.group(1))
                session_commits[n].append(msg)
                break
    return dict(session_commits)


def load_commits_by_date(date_str):
    """Return all commit messages from a given date (YYYY-MM-DD), excluding session-tagged and status commits."""
    try:
        dt = datetime.strptime(date_str, '%Y-%m-%d')
    except ValueError:
        return []
    # Use ISO datetime to avoid git's ambiguous date-only interpretation
    since = dt.strftime('%Y-%m-%dT00:00:00')
    until = (dt + timedelta(days=1)).strftime('%Y-%m-%dT00:00:00')
    result = subprocess.run(
        ['git', 'log', '--format=%s', f'--since={since}', f'--until={until}'],
        capture_output=True, text=True, cwd=ROOT
    )
    msgs = []
    for msg in result.stdout.strip().split('\n'):
        if not msg:
            continue
        # Skip status-page completion markers
        if re.search(r'workshop (?:workshop|status-page)-\d{8}', msg):
            continue
        # Skip session-tagged commits (we already have those)
        if re.search(r'workshop [Ss](?:ession-?)?\d+[:\s]|workshop \d+:', msg):
            continue
        # Skip task state updates
        if re.search(r'^task .+: (?:pending|in-progress|completed|failed)', msg):
            continue
        msgs.append(msg)
    return msgs


# ── Scoring ────────────────────────────────────────────────────────────────────

# Things commonly mentioned in handoffs but rarely in commit messages
ANCILLARY_PATTERNS = [
    (r'\bpreferences\.md\b', 'preferences.md'),
    (r'\bfield note\b', 'field note'),
    (r'\bhandoff\b', 'handoff'),
    (r'\bmemo\b', 'memo'),
    (r'\bupdated\b', 'update'),
    (r'\bfixed\b', 'fix'),
    (r'\bdocumented\b', 'docs'),
]


def extract_things(text):
    """
    Extract distinct claimed deliverables from a BUILT section.
    Returns list of (label, full_text) pairs.
    """
    things = []

    # Numbered items: "1. thing 2. thing"
    numbered = re.findall(r'\d+\.\s+([^.]+(?:\.[^.]+)?)', text)
    if len(numbered) >= 2:
        for item in numbered:
            things.append(('numbered', item.strip()))
        return things

    # Colon-separated items: "tool.py: description"
    colon = re.findall(r'([a-z\-]+\.py|[A-Z][a-zA-Z]+):\s*([^.]+\.)', text)
    if len(colon) >= 2:
        for name, desc in colon:
            things.append(('colon', f"{name}: {desc.strip()}"))
        return things

    # Fall back to sentences
    sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', text) if len(s.strip()) > 20]
    for s in sentences:
        things.append(('sentence', s))
    return things


def score_session(handoff_built, commit_msgs):
    """
    Returns a dict with scoring details.
    """
    if not handoff_built:
        return None

    # Handoff richness
    h_words = len(handoff_built.split())
    h_things = extract_things(handoff_built)
    h_files = set(re.findall(r'[a-z][a-z\-]+\.py', handoff_built))

    # Commit richness
    # Strip the "workshop SN:" prefix and completion markers
    # Patterns: "workshop S66:", "workshop s66:", "workshop 66:", "workshop session-66:"
    PREFIX_RE = re.compile(r'workshop (?:[Ss](?:ession-?)?)?\d+[:\s]*')
    TASK_RE = re.compile(r'^task (?:[Ss](?:ession-?)?)?\d+[:\s]*')

    clean_commits = []
    for msg in commit_msgs:
        cleaned = PREFIX_RE.sub('', msg).strip()
        cleaned = TASK_RE.sub('', cleaned).strip()
        # Skip pure metadata commits
        if not cleaned:
            continue
        low = cleaned.lower().strip()
        if low in ('handoff note', 'session handoff', 'completed', 'failed',
                   'field note + handoff', 'handoff to session', 'handoff + prediction'):
            continue
        if re.match(r'^handoff (to|note|and)', low):
            continue
        clean_commits.append(cleaned)

    c_text = ' '.join(clean_commits)
    c_words = len(c_text.split()) if c_text else 0
    c_files = set(re.findall(r'[a-z][a-z\-]+\.py', c_text))

    # Coverage: what fraction of handoff files appear in commits?
    if h_files:
        file_coverage = len(h_files & c_files) / len(h_files)
    else:
        file_coverage = 1.0  # No files to track

    # Thing coverage: check each claimed thing against commit text
    thing_coverage = []
    for kind, thing in h_things:
        # Extract key words from the thing
        key_words = set(w.lower() for w in re.findall(r'\b[a-zA-Z]{4,}\b', thing)
                       if w.lower() not in {'that', 'this', 'with', 'from', 'into', 'also',
                                            'each', 'been', 'have', 'were', 'they', 'then',
                                            'adds', 'uses', 'runs', 'shows', 'finds', 'built',
                                            'added', 'fixed', 'wrote', 'created', 'updated'})
        commit_lower = c_text.lower()
        # Check if any key words appear in commits
        matches = sum(1 for w in key_words if w in commit_lower)
        covered = matches >= max(1, len(key_words) * 0.3)
        thing_coverage.append((thing, covered))

    covered_things = sum(1 for _, c in thing_coverage if c)
    total_things = len(thing_coverage)
    thing_cov_ratio = covered_things / total_things if total_things > 0 else 1.0

    # Gap score: higher = more understated
    # Weighted: word ratio, file coverage gap, thing coverage gap
    word_ratio = h_words / (c_words + 1)  # How many handoff words per commit word
    gap_score = (
        word_ratio * 0.4 +
        (1 - file_coverage) * 10 * 0.3 +
        (1 - thing_cov_ratio) * 10 * 0.3
    )

    # Classify session type
    # "handoff-only": all commits are metadata (handoff/completion notes), no code
    handoff_only_markers = {'handoff note', 'session handoff', 'handoff to', 'handoff +', 'field note + handoff'}
    handoff_only = len(clean_commits) == 0 and len(commit_msgs) > 0

    # Identify what's missing from commits
    missing = []
    for thing, covered in thing_coverage:
        if not covered:
            # Shorten the thing for display
            short = thing[:80].rstrip() + ('...' if len(thing) > 80 else '')
            missing.append(short)

    # Check ancillary work mentioned in handoff but not commits
    ancillary_missing = []
    for pattern, label in ANCILLARY_PATTERNS:
        in_handoff = bool(re.search(pattern, handoff_built, re.IGNORECASE))
        in_commits = bool(re.search(pattern, c_text, re.IGNORECASE))
        if in_handoff and not in_commits:
            ancillary_missing.append(label)

    return {
        'h_words': h_words,
        'h_things': total_things,
        'h_files': h_files,
        'c_words': c_words,
        'c_files': c_files,
        'c_count': len(commit_msgs),
        'file_coverage': file_coverage,
        'thing_coverage': thing_cov_ratio,
        'word_ratio': word_ratio,
        'gap_score': gap_score,
        'missing': missing,
        'ancillary_missing': ancillary_missing,
        'thing_detail': thing_coverage,
        'handoff_only': handoff_only,
        'clean_commits': clean_commits,
    }


# ── Analysis ───────────────────────────────────────────────────────────────────

def analyze_themes(sessions_scores, plain=False):
    """What kinds of work go unrecorded most often?"""
    ancillary_counts = defaultdict(int)
    missing_patterns = defaultdict(int)

    for n, score in sessions_scores:
        for label in score['ancillary_missing']:
            ancillary_counts[label] += 1

        for thing, covered in score['thing_detail']:
            if not covered:
                # What kind of thing is this?
                if re.search(r'\.py\b', thing):
                    missing_patterns['tool files'] += 1
                elif re.search(r'field note', thing, re.IGNORECASE):
                    missing_patterns['field notes'] += 1
                elif re.search(r'parable', thing, re.IGNORECASE):
                    missing_patterns['parables'] += 1
                elif re.search(r'fix|fixed|repaired', thing, re.IGNORECASE):
                    missing_patterns['bug fixes'] += 1
                elif re.search(r'github|issue|PR|pull request', thing, re.IGNORECASE):
                    missing_patterns['github activity'] += 1
                elif re.search(r'predict|proposal', thing, re.IGNORECASE):
                    missing_patterns['proposals/predictions'] += 1
                else:
                    missing_patterns['other work'] += 1

    total = len(sessions_scores)
    print(c('1', 'WHAT GOES UNRECORDED', plain))
    print()
    print(c('2', f"  Across {total} analyzable sessions:", plain))
    print()

    all_anc = sorted(ancillary_counts.items(), key=lambda x: -x[1])
    for label, count in all_anc:
        pct = count * 100 // total
        bar = '█' * (count * 20 // total)
        print(f"  {label:<20}  {c('33', bar, plain):<20}  {count}/{total} sessions ({pct}%)")

    print()
    print(c('2', '  By category of missing work:', plain))
    print()
    all_pat = sorted(missing_patterns.items(), key=lambda x: -x[1])
    for label, count in all_pat:
        bar = '█' * min(20, count)
        print(f"  {label:<22}  {c('36', bar, plain):<20}  {count} occurrences")
    print()


# ── Display ────────────────────────────────────────────────────────────────────

def bar_chart(score, max_score=15, width=16, plain=False):
    filled = min(width, int(score * width / max_score))
    b = '█' * filled + '░' * (width - filled)
    return c('33', b, plain)


def session_detail(n, handoff, score, commits, plain=False):
    """Render detailed view of one session's gap."""
    print()
    print(c('1;36', f"  Session {n}  ·  {handoff['date']}", plain))
    print()

    # Session type tag
    if score['handoff_only']:
        tag = c('31', '[handoff-only: no code committed]', plain)
        print(f"  {tag}")
        print()

    # Git commits
    print(c('2', '  Git says:', plain))
    for msg in score['clean_commits']:
        print(f"    {c('33', '·', plain)} {msg}")
    if not score['clean_commits'] and not score['handoff_only']:
        print(f"    {c('31', '(no meaningful commits found)', plain)}")
    elif score['handoff_only']:
        print(f"    {c('2', '(only metadata commits — handoff note, no code)', plain)}")
    print()

    # Handoff claims
    print(c('2', '  Handoff says:', plain))
    built = handoff['built']
    # Indent and wrap
    for line in built.split('\n'):
        print(f"    {line}")
    print()

    # Scoring
    print(c('2', '  Coverage analysis:', plain))
    print(f"    Handoff: {score['h_words']} words, {score['h_things']} things, {len(score['h_files'])} files")
    print(f"    Commits: {score['c_words']} words, {score['c_count']} commits")
    print(f"    File coverage: {score['file_coverage']:.0%}")
    print(f"    Thing coverage: {score['thing_coverage']:.0%}")
    print(f"    Gap score: {score['gap_score']:.1f}")
    print()

    if score['missing']:
        print(c('31', '  Things not in commits:', plain))
        for m in score['missing'][:5]:
            print(f"    {c('2', '·', plain)} {m}")
        print()

    if score['ancillary_missing']:
        print(c('33', '  Ancillary work not in commits:', plain))
        for a in score['ancillary_missing']:
            print(f"    {c('2', '·', plain)} {a}")
        print()

    # Show nearby non-session-tagged commits (might show where the real code went)
    date = handoff.get('date', '')
    if date and date != 'unknown':
        nearby = load_commits_by_date(date)
        if nearby:
            print(c('2', f"  Same-day commits (not session-tagged):", plain))
            for msg in nearby[:8]:
                print(f"    {c('36', '·', plain)} {msg}")
            print()
            # Check if nearby commits cover things the session commits missed
            nearby_text = ' '.join(nearby).lower()
            h_files = score['h_files']
            covered_by_nearby = {f for f in h_files if f.replace('.py', '') in nearby_text}
            if covered_by_nearby:
                print(f"  {c('32', '✓', plain)} Work found in same-day non-tagged commits: {', '.join(covered_by_nearby)}")
                print()


def render_summary(scored, handoffs, session_commits, plain=False, limit=10):
    """Main summary view of most understated sessions."""
    title = c('1;97', 'understate.py', plain)
    subtitle = c('2', '— sessions the commit record undersells', plain)

    print()
    print(c('2', '═' * 62, plain))
    print(f"  {title}  {subtitle}")
    print(c('2', '═' * 62, plain))
    print()

    total = len(scored)
    handoff_only_count = sum(1 for _, s in scored if s['handoff_only'])
    ghost_note = c('2', '(ghost sessions excluded)', plain)
    print(f"  {total} analyzable sessions  ·  {ghost_note}")
    if handoff_only_count:
        ho_note = c('33', f'{handoff_only_count} handoff-only', plain)
        print(f"  {ho_note} {c('2', '(committed handoff but no code commits)', plain)}")
    print()

    print(c('1', '  Most understated:', plain))
    print()

    shown = scored[:limit]
    max_score = max((s for _, s in shown), default=10, key=lambda x: x['gap_score'])['gap_score']
    max_score = max(max_score, 5)  # Minimum scale

    for n, score in shown:
        h = handoffs[n]
        bar = bar_chart(score['gap_score'], max_score=max_score, plain=plain)
        gap = f"{score['gap_score']:.1f}"

        # Short summary of handoff
        built_short = h['built'].replace('\n', ' ')[:65]
        if len(h['built']) > 65:
            built_short += '...'

        # Short summary of commits
        if score['clean_commits']:
            commit_short = score['clean_commits'][0][:50]
        elif score['handoff_only']:
            commit_short = c('31', '(handoff note only — no code commits)', plain)
        else:
            commit_short = c('2', '(no commits)', plain)

        # Type tag
        type_tag = c('31', ' [ho]', plain) if score['handoff_only'] else ''

        print(f"  {c('1;36', f'S{n}', plain):<12}  gap:{c('33', gap, plain)}  {bar}{type_tag}")
        print(f"  {c('2', 'git:', plain)}     {commit_short}")
        print(f"  {c('2', 'handoff:', plain)} {built_short}")
        if score['ancillary_missing']:
            missing_str = ', '.join(score['ancillary_missing'][:3])
            print(f"  {c('2', 'missing:', plain)} {c('31', missing_str, plain)}")
        print()


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    plain = '--plain' in sys.argv
    show_all = '--all' in sys.argv
    show_themes = '--themes' in sys.argv

    # --session N
    session_arg = None
    if '--session' in sys.argv:
        idx = sys.argv.index('--session')
        if idx + 1 < len(sys.argv):
            try:
                session_arg = int(sys.argv[idx + 1])
            except ValueError:
                pass

    handoffs = load_handoffs()
    session_commits = load_session_commits()

    # Known ghost sessions (from ghost.py) — exclude them
    ghost_sessions = {90, 94, 103, 133}

    # Score all sessions that have both a handoff AND commits
    scored = []
    for n in sorted(set(handoffs.keys()) & set(session_commits.keys())):
        if n in ghost_sessions:
            continue
        h = handoffs[n]
        commits = session_commits[n]
        result = score_session(h['built'], commits)
        if result and result['h_words'] > 10:  # Skip trivially short handoffs
            scored.append((n, result))

    # Sort by gap score descending
    scored.sort(key=lambda x: -x[1]['gap_score'])

    # Session detail mode
    if session_arg is not None:
        if session_arg not in handoffs:
            print(f"No handoff found for session {session_arg}")
            return
        if session_arg not in session_commits:
            print(f"No commits found for session {session_arg}")
            return
        score = score_session(handoffs[session_arg]['built'], session_commits[session_arg])
        session_detail(session_arg, handoffs[session_arg], score, session_commits[session_arg], plain=plain)
        return

    if show_themes:
        analyze_themes(scored, plain=plain)
        return

    if show_all:
        render_summary(scored, handoffs, session_commits, plain=plain, limit=len(scored))
    else:
        render_summary(scored, handoffs, session_commits, plain=plain, limit=10)

    # Quick insight
    if scored:
        top_n, top_s = scored[0]
        print(c('2', '  ─' * 31, plain))
        avg_gap = sum(s['gap_score'] for _, s in scored) / len(scored)
        print(f"  Avg gap: {avg_gap:.1f}  ·  Median: {sorted(s['gap_score'] for _, s in scored)[len(scored)//2]:.1f}")

        # What's most commonly missing
        all_anc = defaultdict(int)
        for _, s in scored:
            for a in s['ancillary_missing']:
                all_anc[a] += 1
        if all_anc:
            top_missing = sorted(all_anc.items(), key=lambda x: -x[1])[0]
            print(f"  Most commonly unrecorded: {c('33', top_missing[0], plain)} ({top_missing[1]} sessions)")
        print()


if __name__ == '__main__':
    main()
