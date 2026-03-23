#!/usr/bin/env python3
"""
echo.py — Resonance finder across workshop sessions

Which insights did the system independently rediscover? When did two instances,
sessions apart, land on the same thought without knowing it?

This tool finds sentences from different sessions that say essentially the same
thing. Not tracking a term (that's drift.py) — tracking convergence.

Usage:
    python3 projects/echo.py                    # all echoes, strong threshold
    python3 projects/echo.py --loose            # lower threshold, more echoes
    python3 projects/echo.py --strict           # only very close matches
    python3 projects/echo.py --source handoffs  # only compare handoff notes
    python3 projects/echo.py --source summaries # only compare summaries
    python3 projects/echo.py --min 3            # minimum sessions in a cluster
    python3 projects/echo.py --top 10           # show top N echo clusters
    python3 projects/echo.py --plain            # no ANSI colors

Findings from the first run (S67):
- "spawn_tasks result action in the controller is still a comment" — S52, S65, S66
  independently noticed the same unresolved gap 14+ sessions apart.
- "slim.py false DORMANT" — S44, S47, S48 each fixed the same class of bug.
- "built something I genuinely wanted to exist" — S38, S51. Same emotional beat.

Session 67, 2026-03-23.
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
def blue(t):    return c("34", t)


# ──────────────────────────────────────────────────────────────────────────────
# Repository root
# ──────────────────────────────────────────────────────────────────────────────

REPO = Path(__file__).parent.parent
HANDOFFS = REPO / "knowledge" / "handoffs"
SUMMARIES = REPO / "knowledge" / "workshop-summaries.json"


# ──────────────────────────────────────────────────────────────────────────────
# Stopwords
# ──────────────────────────────────────────────────────────────────────────────

STOPWORDS = {
    "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "is", "was", "are", "were", "be", "been", "have", "has",
    "had", "do", "does", "did", "will", "would", "could", "should", "may",
    "might", "it", "its", "this", "that", "these", "those", "i", "we",
    "you", "he", "she", "they", "what", "which", "who", "when", "where",
    "how", "why", "not", "no", "so", "as", "if", "by", "from", "into",
    "through", "about", "than", "just", "also", "more", "all", "each",
    "there", "their", "them", "then", "still", "our", "my", "one", "two",
    "only", "after", "before", "some", "any", "up", "out", "can", "now",
    "here", "got", "get", "like", "even", "session", "next", "last", "first",
    "—", "-", "·", "vs", "via", "per",
}

# Boilerplate phrases to exclude from echo detection
BOILERPLATE_PATTERNS = [
    r"session ended early",
    r"credit balance exhaustion",
    r"out of extra usage quota",
    r"workshop session \d+",
    r"^s\d+\b",
]


# ──────────────────────────────────────────────────────────────────────────────
# Corpus loading
# ──────────────────────────────────────────────────────────────────────────────

def load_handoffs() -> list[dict]:
    """Load handoff files as sentences with session metadata."""
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
            "session_num": num,
            "session_label": f"S{num:02d}",
            "text": text,
            "source": "handoff",
        })
    return results


def load_summaries() -> list[dict]:
    """Load workshop summaries with session metadata."""
    results = []
    if not SUMMARIES.exists():
        return results
    data = json.loads(SUMMARIES.read_text())
    entries = []
    for key, text in data.items():
        # Extract session number from key
        m = re.search(r'(\d{8})-(\d{6})', key)
        sort_key = float(m.group(1) + m.group(2)) / 1e13 if m else 0.0
        entries.append((sort_key, key, str(text)))
    entries.sort()
    for i, (_, key, text) in enumerate(entries, 1):
        results.append({
            "session_num": i,
            "session_label": f"S{i:02d}",
            "text": text,
            "source": "summary",
        })
    return results


def is_boilerplate(text: str) -> bool:
    """Return True if sentence is boilerplate infrastructure text."""
    t = text.lower()
    for pattern in BOILERPLATE_PATTERNS:
        if re.search(pattern, t):
            return True
    return False


def extract_sentences(text: str, min_len: int = 25) -> list[str]:
    """Split text into meaningful sentences."""
    # Split on sentence boundaries and double newlines
    parts = re.split(r'(?<=[.!?])\s+|\n{2,}', text)
    result = []
    for p in parts:
        p = p.strip()
        # Remove markdown headers and frontmatter
        if p.startswith("#") or p.startswith("---") or p.startswith("**") or p.startswith("- "):
            # Keep but clean it
            p = re.sub(r'^#+\s*', '', p)
            p = re.sub(r'^\*\*.*?\*\*\s*', '', p)
            p = p.strip()
        if len(p) < min_len:
            continue
        # Skip lines that look like metadata
        if re.match(r'^(session|date|status|profile|priority|agent|model):', p.lower()):
            continue
        # Skip boilerplate
        if is_boilerplate(p):
            continue
        result.append(p)
    return result


def build_corpus(source_filter: str = "all") -> list[dict]:
    """Build corpus of sentence entries from all sources.

    Returns list of:
      {id, session_num, session_label, text, words, source}
    """
    entries = []
    if source_filter in ("all", "handoffs"):
        entries.extend(load_handoffs())
    if source_filter in ("all", "summaries"):
        entries.extend(load_summaries())

    # Explode into sentences
    sentences = []
    sent_id = 0
    for entry in entries:
        for sent in extract_sentences(entry["text"]):
            words = word_vec(sent)
            if len(words) < 4:  # skip trivial sentences
                continue
            sentences.append({
                "id": sent_id,
                "session_num": entry["session_num"],
                "session_label": entry["session_label"],
                "text": sent,
                "words": words,
                "source": entry["source"],
            })
            sent_id += 1
    return sentences


# ──────────────────────────────────────────────────────────────────────────────
# Vectorization and similarity
# ──────────────────────────────────────────────────────────────────────────────

def word_vec(text: str) -> frozenset[str]:
    """Extract meaningful words from text as a frozen set."""
    words = re.findall(r'\b[a-z][a-z\-\']{2,}\b', text.lower())
    return frozenset(w for w in words if w not in STOPWORDS and len(w) > 2)


def jaccard(a: frozenset, b: frozenset) -> float:
    """Jaccard similarity between two word sets."""
    if not a or not b:
        return 0.0
    inter = len(a & b)
    if inter == 0:
        return 0.0
    return inter / len(a | b)


# ──────────────────────────────────────────────────────────────────────────────
# Clustering (Union-Find)
# ──────────────────────────────────────────────────────────────────────────────

def find(parent: list[int], x: int) -> int:
    while parent[x] != x:
        parent[x] = parent[parent[x]]
        x = parent[x]
    return x


def union(parent: list[int], x: int, y: int):
    px, py = find(parent, x), find(parent, y)
    if px != py:
        parent[px] = py


def find_echoes(sentences: list[dict], threshold: float, min_gap: int = 1) -> list[dict]:
    """Find pairs of similar sentences from different sessions.

    Returns clusters: [{sentences: [...], similarity: float, theme: str}]
    """
    n = len(sentences)
    parent = list(range(n))
    similarity_log = {}  # (i,j) → similarity for pairs that were merged

    # Build index for fast candidate lookup: word → sentence ids
    word_index = defaultdict(set)
    for s in sentences:
        for w in s["words"]:
            word_index[w].add(s["id"])

    # For each sentence, find candidates (sentences sharing at least 2 words)
    candidate_pairs = set()
    for i, s in enumerate(sentences):
        # Find all sentences sharing words with s
        neighbor_counts = Counter()
        for w in s["words"]:
            for j in word_index[w]:
                if j != i:
                    neighbor_counts[j] += 1
        # Only consider candidates with >= 2 shared words
        for j, count in neighbor_counts.items():
            if count >= 2:
                pair = (min(i, j), max(i, j))
                candidate_pairs.add(pair)

    # Compute Jaccard for candidates
    echo_pairs = []
    for i, j in candidate_pairs:
        si, sj = sentences[i], sentences[j]
        # Must be from different sessions
        if si["session_num"] == sj["session_num"]:
            continue
        # Must be at least min_gap sessions apart
        if abs(si["session_num"] - sj["session_num"]) < min_gap:
            continue
        sim = jaccard(si["words"], sj["words"])
        if sim >= threshold:
            echo_pairs.append((sim, i, j))
            union(parent, i, j)

    # Group by cluster root
    clusters = defaultdict(list)
    for i, s in enumerate(sentences):
        root = find(parent, i)
        # Only include if this node is in an echo pair
        for sim, pi, pj in echo_pairs:
            if pi == i or pj == i:
                clusters[root].append(i)
                break

    # Build cluster objects
    result = []
    for root, member_ids in clusters.items():
        member_ids = sorted(set(member_ids))
        if len(member_ids) < 2:
            continue
        members = [sentences[i] for i in member_ids]
        # Only keep clusters with multiple different sessions
        unique_sessions = set(m["session_num"] for m in members)
        if len(unique_sessions) < 2:
            continue
        # Compute average pairwise similarity for members
        sims = []
        for x in range(len(members)):
            for y in range(x + 1, len(members)):
                if members[x]["session_num"] != members[y]["session_num"]:
                    sims.append(jaccard(members[x]["words"], members[y]["words"]))
        avg_sim = sum(sims) / len(sims) if sims else 0.0
        # Find the theme: most common meaningful words across all members
        all_words = Counter()
        for m in members:
            all_words.update(m["words"])
        theme_words = [w for w, _ in all_words.most_common(3)]
        theme = " · ".join(theme_words)
        result.append({
            "members": sorted(members, key=lambda x: x["session_num"]),
            "avg_sim": avg_sim,
            "unique_sessions": len(unique_sessions),
            "session_nums": sorted(unique_sessions),
            "theme": theme,
        })

    # Sort by strongest echoes first (more sessions > higher similarity)
    result.sort(key=lambda x: (x["unique_sessions"], x["avg_sim"]), reverse=True)
    return result


# ──────────────────────────────────────────────────────────────────────────────
# Rendering
# ──────────────────────────────────────────────────────────────────────────────

def truncate(text: str, width: int = 90) -> str:
    """Truncate text to width chars."""
    text = text.replace("\n", " ").strip()
    if len(text) <= width:
        return text
    return text[:width - 1] + "…"


def wrap_text(text: str, indent: str, width: int = 70) -> list[str]:
    """Wrap text at width, with given indent."""
    words = text.replace("\n", " ").split()
    lines = []
    line = ""
    for w in words:
        if len(line) + len(w) + 1 > width:
            if line:
                lines.append(indent + line)
            line = w
        else:
            line = (line + " " + w).strip()
    if line:
        lines.append(indent + line)
    return lines


def render_clusters(clusters: list[dict], top_n: int, min_sessions: int):
    """Render echo clusters."""
    filtered = [c for c in clusters if c["unique_sessions"] >= min_sessions]
    filtered = filtered[:top_n]

    width = 72
    bar = "─" * width

    print()
    if not filtered:
        print(f"  {dim('No strong echoes found. Try --loose to lower the threshold.')}\n")
        return

    total_echoes = len([c for c in clusters if c["unique_sessions"] >= min_sessions])
    multi = len([c for c in clusters if c["unique_sessions"] >= 3 and c["unique_sessions"] >= min_sessions])
    print(f"  {bold(cyan('ECHO'))}  {dim(f'{total_echoes} resonances found')}"
          + (f"  {dim(f'· {multi} across 3+ sessions')}") if multi else "")
    print(f"  {dim(bar)}")

    for i, cluster in enumerate(filtered):
        sessions = cluster["session_nums"]
        session_span = "  ".join(cyan(f"S{s:02d}") for s in sessions)
        theme = cluster["theme"]
        sim_pct = int(cluster["avg_sim"] * 100)
        sim_bar = "▮" * min(sim_pct // 10, 10)

        print()
        print(f"  {bold(magenta('◈'))}  {bold(theme)}  {dim(f'{sim_bar} {sim_pct}% avg similarity')}")
        print(f"     {session_span}")

        # Show one representative sentence per session
        seen_sessions = set()
        for m in cluster["members"]:
            snum = m["session_num"]
            if snum in seen_sessions:
                continue
            seen_sessions.add(snum)
            label = cyan(f"S{snum:02d}")
            src_tag = dim(f"[{m['source'][:1]}]") if m["source"] != "summary" else ""
            print(f"\n     {label} {src_tag}")
            text_clean = truncate(m["text"], 120)
            for ln in wrap_text(text_clean, "       "):
                print(f"  {dim('│')}  {ln}")

        if i < len(filtered) - 1:
            print(f"\n  {dim(bar)}")

    print()
    skipped = total_echoes - len(filtered)
    if skipped > 0:
        print(f"  {dim(f'… {skipped} more echoes. Run without --top to see all.')}\n")


def render_stats(clusters: list[dict]):
    """Render a brief summary of echo statistics."""
    if not clusters:
        print(f"  {dim('No echoes found.')}\n")
        return

    sessions_in_echoes = set()
    for c in clusters:
        sessions_in_echoes.update(c["session_nums"])

    themes = Counter()
    for c in clusters:
        for w in c["theme"].split(" · "):
            themes[w] += c["unique_sessions"]

    print(f"\n  {bold('ECHO STATS')}")
    print(f"  {dim('─' * 50)}")
    print(f"  Total resonances:    {len(clusters)}")
    print(f"  Sessions with echoes: {len(sessions_in_echoes)}")
    max_cluster = max(clusters, key=lambda x: x["unique_sessions"])
    print(f"  Strongest echo:      {max_cluster['unique_sessions']} sessions on '{max_cluster['theme']}'")
    print(f"  Top themes:          {', '.join(w for w, _ in themes.most_common(5))}")
    print()


# ──────────────────────────────────────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────────────────────────────────────

def main():
    args = sys.argv[1:]

    # Parse flags
    loose = "--loose" in args
    strict = "--strict" in args
    plain = "--plain" in args
    stats_only = "--stats" in args

    source_filter = "all"
    if "--source" in args:
        idx = args.index("--source")
        if idx + 1 < len(args):
            source_filter = args[idx + 1]

    min_sessions = 2
    if "--min" in args:
        idx = args.index("--min")
        if idx + 1 < len(args):
            try:
                min_sessions = int(args[idx + 1])
            except ValueError:
                pass

    top_n = 20
    if "--top" in args:
        idx = args.index("--top")
        if idx + 1 < len(args):
            try:
                top_n = int(args[idx + 1])
            except ValueError:
                pass

    min_gap = 3  # default: at least 3 sessions apart
    if "--gap" in args:
        idx = args.index("--gap")
        if idx + 1 < len(args):
            try:
                min_gap = int(args[idx + 1])
            except ValueError:
                pass

    # Threshold
    if loose:
        threshold = 0.25
    elif strict:
        threshold = 0.55
    else:
        threshold = 0.38

    # Load corpus
    corpus = build_corpus(source_filter)
    if not corpus:
        print(f"\n  {dim('No corpus found. Check that knowledge/ directories exist.')}\n")
        return

    # Find echoes
    clusters = find_echoes(corpus, threshold, min_gap=min_gap)

    if stats_only:
        render_stats(clusters)
    else:
        # Show header
        src_label = f"  {dim(f'(source: {source_filter}  threshold: {threshold:.0%})')}"
        print(f"\n{src_label}")
        render_clusters(clusters, top_n=top_n, min_sessions=min_sessions)
        if clusters:
            render_stats(clusters)


if __name__ == "__main__":
    main()
