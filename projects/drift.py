#!/usr/bin/env python3
"""
drift.py — Semantic drift tracker across workshop sessions

How has the meaning of "multi-agent" shifted over 65 sessions?
When did "memory" stop meaning "handoff notes" and start meaning "task context"?

This tool extracts all mentions of a term from handoffs and session summaries,
shows them in chronological order, and surfaces the context vocabulary shift
— what other words cluster around the term, and how that changes over time.

Usage:
    python3 projects/drift.py "multi-agent"
    python3 projects/drift.py "memory" --context
    python3 projects/drift.py --list              # show discoverable terms
    python3 projects/drift.py "planner" --brief   # just the arc, no excerpts
    python3 projects/drift.py --plain             # no ANSI colors

Session 66, 2026-03-22.
"""

import json
import re
import os
import sys
from pathlib import Path
from collections import defaultdict, Counter

# ──────────────────────────────────────────────────────────────────────────────
# Color helpers
# ──────────────────────────────────────────────────────────────────────────────

PLAIN = "--plain" in sys.argv


def c(code: str, text: str) -> str:
    if PLAIN:
        return text
    return f"\033[{code}m{text}\033[0m"


def bold(t):    return c("1", t)
def dim(t):     return c("2", t)
def cyan(t):    return c("36", t)
def yellow(t):  return c("33", t)
def green(t):   return c("32", t)
def magenta(t): return c("35", t)
def white(t):   return c("97", t)
def red(t):     return c("31", t)


# ──────────────────────────────────────────────────────────────────────────────
# Repository root
# ──────────────────────────────────────────────────────────────────────────────

REPO = Path(__file__).parent.parent
HANDOFFS = REPO / "knowledge" / "handoffs"
SUMMARIES = REPO / "knowledge" / "workshop-summaries.json"
MEMOS = REPO / "knowledge" / "memos.md"
PREFERENCES = REPO / "knowledge" / "preferences.md"


# ──────────────────────────────────────────────────────────────────────────────
# Corpus loading
# ──────────────────────────────────────────────────────────────────────────────

def session_num_from_key(key: str) -> float:
    """Extract a sortable session number from a key like 'workshop-20260310-230851'."""
    # Try date-based key → use timestamp as sort key
    m = re.search(r'(\d{8})-(\d{6})', key)
    if m:
        return float(m.group(1) + m.group(2)) / 1e13
    return 0.0


def load_summaries() -> list[dict]:
    """Load workshop summaries as [{session_label, session_num, text, source}]."""
    results = []
    if not SUMMARIES.exists():
        return results
    data = json.loads(SUMMARIES.read_text())
    # Build a sorted list by date key
    entries = []
    for key, text in data.items():
        sort_key = session_num_from_key(key)
        entries.append((sort_key, key, str(text)))
    entries.sort()
    for i, (_, key, text) in enumerate(entries, 1):
        results.append({
            "session_label": f"S{i:02d}",
            "session_num": i,
            "text": text,
            "source": "summary",
        })
    return results


def load_handoffs() -> list[dict]:
    """Load handoff files as [{session_label, session_num, text, source}]."""
    results = []
    if not HANDOFFS.exists():
        return results
    for f in sorted(HANDOFFS.glob("session-*.md")):
        m = re.search(r'session-(\d+)', f.name)
        if not m:
            continue
        num = int(m.group(1))
        text = f.read_text()
        results.append({
            "session_label": f"S{num:02d}",
            "session_num": num,
            "text": text,
            "source": "handoff",
        })
    return results


def load_memos() -> list[dict]:
    """Load memos as pseudo-session entries."""
    results = []
    if not MEMOS.exists():
        return results
    text = MEMOS.read_text()
    results.append({
        "session_label": "memo",
        "session_num": 999,
        "text": text,
        "source": "memos",
    })
    return results


def build_corpus() -> list[dict]:
    """Merge and sort all sources by session number."""
    corpus = load_summaries() + load_handoffs() + load_memos()
    corpus.sort(key=lambda e: (e["session_num"], e["source"]))
    return corpus


# ──────────────────────────────────────────────────────────────────────────────
# Excerpt extraction
# ──────────────────────────────────────────────────────────────────────────────

def sentences(text: str) -> list[str]:
    """Split text into rough sentences."""
    # Split on . ? ! and newlines, keeping reasonable length
    parts = re.split(r'(?<=[.!?])\s+|\n{2,}', text)
    result = []
    for p in parts:
        p = p.strip()
        if len(p) > 15:
            result.append(p)
    return result


def find_excerpts(entry: dict, term: str, window: int = 120) -> list[str]:
    """Find all sentences in entry mentioning term (case-insensitive)."""
    pattern = re.compile(re.escape(term), re.IGNORECASE)
    found = []
    for sent in sentences(entry["text"]):
        if pattern.search(sent):
            # Truncate long sentences
            if len(sent) > window * 2:
                # Find term position and take a window around it
                m = pattern.search(sent)
                if m:
                    start = max(0, m.start() - window // 2)
                    end = min(len(sent), m.end() + window // 2)
                    excerpt = ("…" if start > 0 else "") + sent[start:end] + ("…" if end < len(sent) else "")
                    found.append(excerpt)
            else:
                found.append(sent)
    return found


# ──────────────────────────────────────────────────────────────────────────────
# Context vocabulary analysis
# ──────────────────────────────────────────────────────────────────────────────

STOPWORDS = {
    "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "is", "was", "are", "were", "be", "been", "have", "has",
    "had", "do", "does", "did", "will", "would", "could", "should", "may",
    "might", "it", "its", "this", "that", "these", "those", "i", "we",
    "you", "he", "she", "they", "what", "which", "who", "when", "where",
    "how", "why", "not", "no", "so", "as", "if", "by", "from", "into",
    "through", "about", "than", "just", "also", "more", "all", "each",
    "there", "their", "them", "then", "than", "still", "our", "my",
    "—", "-", "1", "2", "3", "4", "5", "6", "7", "8", "9", "0",
}


def context_words(excerpts: list[str], term: str, top_n: int = 8) -> list[str]:
    """Find the most common context words around the term in these excerpts."""
    term_re = re.compile(re.escape(term), re.IGNORECASE)
    word_re = re.compile(r'\b[a-z][a-z\-_]{2,}\b')
    counts = Counter()
    for exc in excerpts:
        words = word_re.findall(exc.lower())
        term_words = set(re.split(r'[\s\-_]', term.lower()))
        for w in words:
            if w not in STOPWORDS and w not in term_words and len(w) > 2:
                counts[w] += 1
    return [w for w, _ in counts.most_common(top_n)]


def analyze_drift(mentions: list[dict]) -> list[str]:
    """
    Detect semantic shift points. Returns a list of observations about
    how the context vocabulary changed across sessions.
    """
    if len(mentions) < 3:
        return []

    # Split into thirds
    n = len(mentions)
    early = mentions[:n // 3]
    mid = mentions[n // 3: 2 * n // 3]
    late = mentions[2 * n // 3:]

    def vocab_for(entries):
        all_text = " ".join(e["text"] for e in entries)
        words = re.findall(r'\b[a-z][a-z\-_]{2,}\b', all_text.lower())
        return Counter(w for w in words if w not in STOPWORDS and len(w) > 3)

    ev = vocab_for(early)
    mv = vocab_for(mid)
    lv = vocab_for(late)

    # Words that appear heavily in early but not late
    faded = [w for w, _ in ev.most_common(20)
             if lv.get(w, 0) < ev[w] * 0.3 and ev[w] > 1][:4]

    # Words that appear heavily in late but not early
    emerged = [w for w, _ in lv.most_common(20)
               if ev.get(w, 0) < lv[w] * 0.3 and lv[w] > 1][:4]

    observations = []
    if faded:
        observations.append(f"early language: {', '.join(faded)}")
    if emerged:
        observations.append(f"recent language: {', '.join(emerged)}")
    return observations


# ──────────────────────────────────────────────────────────────────────────────
# Discovery mode: find interesting terms
# ──────────────────────────────────────────────────────────────────────────────

SEED_TERMS = [
    "multi-agent", "memory", "planner", "bus", "controller", "worker",
    "task", "handoff", "architecture", "workshop", "free time",
    "field notes", "coordinate", "spawn", "channel", "context window",
    "conversation", "identity", "dormant", "retire",
]


def discover_terms(corpus: list[dict], min_sessions: int = 3) -> list[tuple[str, int]]:
    """Find seed terms that appear in at least min_sessions."""
    results = []
    for term in SEED_TERMS:
        pattern = re.compile(re.escape(term), re.IGNORECASE)
        sessions_hit = set()
        for entry in corpus:
            if pattern.search(entry["text"]):
                sessions_hit.add(entry["session_num"])
        if len(sessions_hit) >= min_sessions:
            results.append((term, len(sessions_hit)))
    results.sort(key=lambda x: -x[1])
    return results


# ──────────────────────────────────────────────────────────────────────────────
# Rendering
# ──────────────────────────────────────────────────────────────────────────────

def highlight_term(text: str, term: str) -> str:
    """Highlight occurrences of term in text."""
    if PLAIN:
        return text
    pattern = re.compile(re.escape(term), re.IGNORECASE)
    return pattern.sub(lambda m: bold(white(m.group(0))), text)


def render_drift(term: str, corpus: list[dict], show_context: bool = False, brief: bool = False):
    """Render drift analysis for a term."""
    pattern = re.compile(re.escape(term), re.IGNORECASE)

    # Collect all mentions with their session info
    mentions = []  # {session_label, session_num, excerpts}
    for entry in corpus:
        excerpts = find_excerpts(entry, term)
        if excerpts:
            mentions.append({
                "session_label": entry["session_label"],
                "session_num": entry["session_num"],
                "excerpts": excerpts,
                "text": " ".join(excerpts),
                "source": entry["source"],
            })

    if not mentions:
        print(f"\n  {dim('No mentions of')} {yellow(repr(term))} {dim('found in corpus.')}\n")
        return

    # Header
    width = 72
    bar = "─" * width
    print()
    print(f"  {bold(magenta('DRIFT'))}  {cyan(repr(term))}  {dim(f'· {len(mentions)} sessions')}")
    print(f"  {dim(bar)}")

    if brief:
        # Just show one excerpt per session, no context
        for m in mentions:
            label = m["session_label"]
            excerpt = m["excerpts"][0][:100].replace("\n", " ")
            if len(excerpt) == 100:
                excerpt += "…"
            print(f"  {dim(label)}  {highlight_term(excerpt, term)}")
    else:
        # Show all excerpts grouped by session
        for m in mentions:
            label = m["session_label"]
            source_tag = dim(f"[{m['source']}]") if m["source"] != "summary" else ""
            print(f"\n  {cyan(bold(label))} {source_tag}")
            for exc in m["excerpts"][:2]:  # max 2 excerpts per session
                exc_clean = exc.replace("\n", " ").strip()
                # Wrap at ~70 chars
                words = exc_clean.split()
                line = ""
                lines = []
                for w in words:
                    if len(line) + len(w) + 1 > 68:
                        lines.append(line)
                        line = w
                    else:
                        line = (line + " " + w).strip()
                if line:
                    lines.append(line)
                for i, ln in enumerate(lines):
                    prefix = "  │  " if i == 0 else "  │  "
                    print(f"  {dim('│')}  {highlight_term(ln, term)}")

        # Context analysis
        if show_context and len(mentions) >= 3:
            print(f"\n  {dim(bar)}")
            drift_obs = analyze_drift(mentions)
            if drift_obs:
                print(f"  {bold('VOCABULARY SHIFT')}")
                for obs in drift_obs:
                    print(f"  {dim('·')} {obs}")

    # Frequency bar
    print(f"\n  {dim(bar)}")
    # Show session span
    first = mentions[0]["session_label"]
    last = mentions[-1]["session_label"]
    if first == last:
        span_str = f"first appeared: {first}"
    else:
        span_str = f"{first} → {last}  ({len(mentions)} sessions)"
    print(f"  {dim(span_str)}")

    # Inline context words from full mention set
    if show_context:
        all_excerpts = [e for m in mentions for e in m["excerpts"]]
        ctx = context_words(all_excerpts, term)
        if ctx:
            print(f"  {dim('context: ')} {dim(', '.join(ctx))}")

    print()


def render_list(corpus: list[dict]):
    """Show discoverable terms with their session counts."""
    terms = discover_terms(corpus)
    print()
    print(f"  {bold('TERMS IN CORPUS')}")
    print(f"  {dim('─' * 50)}")
    for term, count in terms:
        bar_len = min(count, 30)
        bar = "▮" * bar_len
        print(f"  {cyan(term):<25} {dim(bar)}  {dim(str(count))}")
    run_hint = 'Run: python3 projects/drift.py "<term>"'
    print(f"\n  {dim(run_hint)}\n")


# ──────────────────────────────────────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────────────────────────────────────

def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    flags = [a for a in sys.argv[1:] if a.startswith("--")]

    show_context = "--context" in flags
    brief = "--brief" in flags
    list_mode = "--list" in flags

    corpus = build_corpus()

    if list_mode or not args:
        render_list(corpus)
        if not args and not list_mode:
            usage_hint = 'Usage: python3 projects/drift.py "<term>"'
            print(f"  {dim(usage_hint)}\n")
        return

    term = args[0]
    render_drift(term, corpus, show_context=show_context, brief=brief)


if __name__ == "__main__":
    main()
