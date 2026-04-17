#!/usr/bin/env python3
"""
resonate.py — Semantic resonance finder across workshop sessions

echo.py finds verbatim echoes (same words, different sessions).
resonate.py finds thematic resonances — sessions that were working
through the same ideas in different words.

Uses TF-IDF cosine similarity over whole-session documents. High resonance
means two sessions spent energy on the same themes, even with no overlap
in specific phrasing.

Usage:
    python3 projects/resonate.py                  # top resonant session pairs
    python3 projects/resonate.py --session 112    # what resonates with S112?
    python3 projects/resonate.py --top 15         # show top N pairs
    python3 projects/resonate.py --cluster        # group sessions by theme
    python3 projects/resonate.py --query "text"   # sessions most similar to a query
    python3 projects/resonate.py --gap 5          # min session gap between pairs
    python3 projects/resonate.py --plain          # no ANSI colors

Difference from echo.py:
    echo.py:     sentence-level · Jaccard overlap · verbatim repetitions
    resonate.py: session-level  · TF-IDF cosine  · thematic resonance

Built session 124, 2026-04-17. Answers the echo.py semantic gap from S126.
"""

import json
import math
import re
import sys
from pathlib import Path
from collections import Counter, defaultdict


# ──────────────────────────────────────────────────────────────────────────────
# Color helpers
# ──────────────────────────────────────────────────────────────────────────────

PLAIN = "--plain" in sys.argv


def c(code: str, text: str) -> str:
    return text if PLAIN else f"\033[{code}m{text}\033[0m"


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
# Paths
# ──────────────────────────────────────────────────────────────────────────────

REPO       = Path(__file__).parent.parent
HANDOFFS   = REPO / "knowledge" / "handoffs"
FIELD_NOTES = REPO / "knowledge" / "field-notes"
SUMMARIES  = REPO / "knowledge" / "workshop-summaries.json"


# ──────────────────────────────────────────────────────────────────────────────
# Stopwords — extended to cover system-specific boilerplate
# ──────────────────────────────────────────────────────────────────────────────

STOPWORDS = {
    # English basics
    "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "is", "was", "are", "were", "be", "been", "have", "has",
    "had", "do", "does", "did", "will", "would", "could", "should", "may",
    "might", "it", "its", "this", "that", "these", "those", "i", "we",
    "you", "he", "she", "they", "what", "which", "who", "when", "where",
    "how", "why", "not", "no", "so", "as", "if", "by", "from", "into",
    "through", "about", "than", "just", "also", "more", "all", "each",
    "there", "their", "them", "then", "still", "our", "my", "one", "two",
    "only", "after", "before", "some", "any", "up", "out", "can", "now",
    "here", "very", "own", "too", "most", "such", "both", "other", "while",
    # Action verbs (too common to discriminate)
    "built", "build", "wrote", "write", "run", "running", "make", "made",
    "said", "work", "working", "works", "used", "use", "using", "want",
    "wanted", "needs", "need", "think", "thought", "seems", "seem", "look",
    "looks", "see", "saw", "feel", "felt", "know", "knew", "found", "find",
    "take", "took", "give", "gave", "put", "let", "keep", "kept", "try",
    "tried", "show", "showed", "add", "added", "remove", "removed", "check",
    "checked", "read", "ran", "get", "got", "set", "fix", "fixed", "start",
    "started", "end", "ended", "move", "moved", "mean", "means", "meant",
    "come", "came", "ask", "asked", "call", "called", "return", "returned",
    "create", "created", "update", "updated", "change", "changed", "happen",
    "happened", "include", "included", "push", "pushed", "pull", "pulled",
    "open", "opened", "close", "closed", "point", "points", "approach",
    # Descriptors (too generic)
    "good", "bad", "new", "old", "big", "small", "large", "medium", "high",
    "low", "long", "short", "full", "real", "clear", "clean", "simple",
    "hard", "easy", "right", "wrong", "true", "false", "main", "general",
    "current", "recent", "past", "future", "last", "first", "next", "later",
    "better", "best", "worse", "worst", "different", "similar", "specific",
    "direct", "actual", "certain", "little", "few", "much", "many", "whole",
    # Claude-OS system boilerplate
    "session", "workshop", "handoff", "task", "tool", "tools", "tasks",
    "project", "projects", "commit", "commits", "repo", "field", "notes",
    "instance", "worker", "controller", "profile", "status", "failed",
    "completed", "python", "script", "file", "files", "output", "code",
    "line", "lines", "note", "notes", "time", "day", "week", "hour",
    "thing", "things", "way", "ways", "something", "anything", "nothing",
    "everything", "bit", "lot", "back", "hand", "bit", "part", "point",
    "case", "kind", "type", "form", "side", "place", "number", "word",
    "words", "text", "data", "version", "name", "list", "set", "group",
    # Symbols (if they slip through)
    "vs", "via", "per", "etc",
}


# ──────────────────────────────────────────────────────────────────────────────
# Text processing
# ──────────────────────────────────────────────────────────────────────────────

def clean_text(text: str) -> str:
    """Strip code blocks, URLs, and frontmatter from text."""
    text = re.sub(r'```[\s\S]*?```', ' ', text)       # code blocks
    text = re.sub(r'`[^`\n]+`', ' ', text)             # inline code
    text = re.sub(r'https?://\S+', ' ', text)           # URLs
    text = re.sub(r'^---[\s\S]*?---\n', '', text, count=1)  # frontmatter
    text = re.sub(r'##\s+', ' ', text)                  # section headers
    text = re.sub(r'#\s+', ' ', text)                   # headers
    text = re.sub(r'\*\*.*?\*\*', ' ', text)            # bold markers
    return text


def tokenize(text: str) -> list[str]:
    """Extract meaningful tokens from text."""
    text = clean_text(text)
    words = re.findall(r'\b[a-z][a-z\-]{2,}\b', text.lower())
    return [w for w in words if w not in STOPWORDS and len(w) >= 3]


def extract_sentences(text: str, min_len: int = 40, max_len: int = 250) -> list[str]:
    """Extract readable sentences from text."""
    text = clean_text(text)
    parts = re.split(r'(?<=[.!?])\s+|\n{2,}', text)
    result = []
    for p in parts:
        p = p.strip()
        p = re.sub(r'\s+', ' ', p)
        if min_len <= len(p) <= max_len:
            # Skip metadata lines
            if re.match(r'^(session:|date:|status:|profile:|priority:|agent:|model:)', p.lower()):
                continue
            # Skip lines starting with bullets or dashes
            if p.startswith(('-', '*', '•', '·')):
                p = p.lstrip('-*•· ').strip()
            if len(p) >= min_len:
                result.append(p)
    return result


# ──────────────────────────────────────────────────────────────────────────────
# Corpus loading
# ──────────────────────────────────────────────────────────────────────────────

def load_corpus() -> dict[int, dict]:
    """Load all sessions into a corpus dict: {session_num → {text, sources, label}}.

    Primary source: handoff notes (rich, detailed).
    Supplementary: workshop summaries (for context/verification).
    """
    sessions: dict[int, dict] = {}

    # Load handoff notes
    if HANDOFFS.exists():
        for f in sorted(HANDOFFS.glob("session-*.md")):
            m = re.search(r'session-(\d+)', f.name)
            if not m:
                continue
            num = int(m.group(1))
            text = f.read_text()
            sessions[num] = {
                "session_num": num,
                "label": f"S{num}",
                "text": text,
                "sources": ["handoff"],
                "raw_texts": [text],
            }

    # Supplement with summaries (add to existing sessions or create stubs)
    if SUMMARIES.exists():
        try:
            data = json.loads(SUMMARIES.read_text())
        except json.JSONDecodeError:
            data = {}

        # Sort entries chronologically to assign session numbers
        entries = []
        for key, summary_text in data.items():
            m = re.search(r'(\d{8})-(\d{6})', key)
            sort_key = float(m.group(1) + "." + m.group(2)) if m else 0.0
            entries.append((sort_key, key, str(summary_text)))
        entries.sort()

        for sess_i, (_, key, summary_text) in enumerate(entries, 1):
            # Skip failed/trivial summaries
            lower = summary_text.lower()
            if "quota" in lower or "ended early" in lower or len(summary_text.strip()) < 20:
                continue
            # Supplement existing session if we can match it, otherwise skip
            # (summaries are too short to be useful as standalone documents)
            # Just add as supplementary text to existing sessions
            # Rough alignment: summary index ≈ session number for high-numbered sessions
            # We'll skip standalone summaries and only use handoffs for sessions 100+
            # For early sessions (1-99, no handoffs), create basic entries from summaries
            if sess_i not in sessions and sess_i < 100:
                sessions[sess_i] = {
                    "session_num": sess_i,
                    "label": f"S{sess_i}",
                    "text": summary_text,
                    "sources": ["summary"],
                    "raw_texts": [summary_text],
                }

    return sessions


# ──────────────────────────────────────────────────────────────────────────────
# TF-IDF
# ──────────────────────────────────────────────────────────────────────────────

def build_tfidf(sessions: dict[int, dict]) -> tuple:
    """Build TF-IDF vectors for all sessions.

    Returns:
        sess_nums: sorted list of session numbers
        vocab: list of vocabulary terms
        df: Counter of document frequency per term
        vectors: dict {sess_num → {term_idx → weight}}
        sess_tokens: dict {sess_num → list of tokens}
    """
    sess_nums = sorted(sessions.keys())
    n = len(sess_nums)
    if n == 0:
        return [], [], Counter(), {}, {}

    # Tokenize all sessions
    sess_tokens: dict[int, list[str]] = {}
    for num in sess_nums:
        sess_tokens[num] = tokenize(sessions[num]["text"])

    # Document frequency: how many sessions contain each term
    df: Counter = Counter()
    for tokens in sess_tokens.values():
        for word in set(tokens):
            df[word] += 1

    # Build vocabulary: terms that appear in ≥2 sessions but ≤85% of sessions
    min_df = max(2, int(n * 0.03))  # at least 3% of sessions
    max_df = int(n * 0.85)
    vocab = sorted(w for w, d in df.items() if min_df <= d <= max_df and len(w) >= 3)
    word_idx: dict[str, int] = {w: i for i, w in enumerate(vocab)}

    # TF-IDF vectors (sparse)
    vectors: dict[int, dict[int, float]] = {}
    for num in sess_nums:
        tokens = sess_tokens[num]
        if not tokens:
            vectors[num] = {}
            continue
        tf = Counter(tokens)
        vec: dict[int, float] = {}
        for word, idx in word_idx.items():
            if word in tf:
                tf_val = 1.0 + math.log(tf[word])  # sublinear TF
                idf_val = math.log(n / df[word]) + 1.0  # smoothed IDF
                vec[idx] = tf_val * idf_val
        vectors[num] = vec

    # L2 normalize
    for num in sess_nums:
        vec = vectors[num]
        norm = math.sqrt(sum(v * v for v in vec.values()))
        if norm > 0:
            vectors[num] = {k: v / norm for k, v in vec.items()}

    return sess_nums, vocab, df, vectors, sess_tokens


def cosine_sim(vec_a: dict, vec_b: dict) -> float:
    """Cosine similarity of two L2-normalized sparse vectors."""
    if not vec_a or not vec_b:
        return 0.0
    # Iterate smaller vector for speed
    if len(vec_a) > len(vec_b):
        vec_a, vec_b = vec_b, vec_a
    return sum(v * vec_b[k] for k, v in vec_a.items() if k in vec_b)


# ──────────────────────────────────────────────────────────────────────────────
# Resonance analysis
# ──────────────────────────────────────────────────────────────────────────────

def find_resonant_pairs(
    sess_nums: list[int],
    vectors: dict[int, dict],
    min_gap: int = 5,
    min_sim: float = 0.08,
) -> list[tuple[float, int, int]]:
    """Find all session pairs above min_sim, at least min_gap apart.

    Returns list of (similarity, sess_a, sess_b) sorted descending.
    """
    pairs = []
    for i, si in enumerate(sess_nums):
        for sj in sess_nums[i + 1:]:
            if abs(si - sj) < min_gap:
                continue
            sim = cosine_sim(vectors[si], vectors[sj])
            if sim >= min_sim:
                pairs.append((sim, si, sj))
    pairs.sort(reverse=True)
    return pairs


def top_shared_terms(
    si: int,
    sj: int,
    vectors: dict[int, dict],
    vocab: list[str],
    n: int = 8,
) -> list[str]:
    """Return top N terms that contribute most to the cosine similarity."""
    va, vb = vectors[si], vectors[sj]
    contributions = []
    for idx in set(va) & set(vb):
        contributions.append((va[idx] * vb[idx], vocab[idx]))
    contributions.sort(reverse=True)
    return [term for _, term in contributions[:n]]


def best_sentence(session: dict, key_terms: list[str]) -> str:
    """Find the sentence in this session that best reflects the key terms."""
    sentences = extract_sentences(session["text"])
    if not sentences:
        return session["text"][:200].replace("\n", " ").strip()

    term_set = set(key_terms)
    best_text = ""
    best_score = -1
    for sent in sentences:
        words = set(re.findall(r'\b[a-z]{3,}\b', sent.lower()))
        score = len(words & term_set)
        # Prefer sentences that are neither too short nor too listy
        if score > best_score and not re.match(r'^[\d\-•]', sent):
            best_score = score
            best_text = sent
    return best_text or sentences[0]


# ──────────────────────────────────────────────────────────────────────────────
# Clustering
# ──────────────────────────────────────────────────────────────────────────────

def cluster_sessions(
    sess_nums: list[int],
    vectors: dict[int, dict],
    vocab: list[str],
    top_pairs: list[tuple[float, int, int]],
    k: int = 6,
) -> list[dict]:
    """Group sessions into k theme clusters using greedy agglomeration.

    Starts with the sessions appearing in the most resonant pairs, then
    expands clusters by absorbing nearest neighbors.
    """
    # Count how often each session appears in top pairs
    pair_count: Counter = Counter()
    for sim, sa, sb in top_pairs[:80]:
        pair_count[sa] += 1
        pair_count[sb] += 1

    # Seed clusters from the most socially connected sessions
    seeds = [s for s, _ in pair_count.most_common(k)]
    # Remove seeds that are too similar to each other
    final_seeds = [seeds[0]] if seeds else []
    for s in seeds[1:]:
        if all(cosine_sim(vectors[s], vectors[seed]) < 0.25 for seed in final_seeds):
            final_seeds.append(s)
        if len(final_seeds) >= k:
            break

    if not final_seeds:
        return []

    # Assign every session to nearest seed
    assignments: dict[int, int] = {}  # sess_num → seed_num
    for num in sess_nums:
        if not vectors[num]:
            continue
        best_seed = max(final_seeds, key=lambda seed: cosine_sim(vectors[num], vectors[seed]))
        sim = cosine_sim(vectors[num], vectors[best_seed])
        if sim >= 0.05:  # only assign if there's any affinity
            assignments[num] = best_seed

    # Build cluster objects
    clusters: dict[int, list[int]] = defaultdict(list)
    for num, seed in assignments.items():
        clusters[seed].append(num)

    result = []
    for seed, members in clusters.items():
        if len(members) < 2:
            continue
        members_sorted = sorted(members)
        # Find terms that characterize the cluster: highest average TF-IDF weight
        # across all cluster members (centroid approach)
        term_totals: Counter = Counter()
        for num in members:
            for idx, weight in vectors.get(num, {}).items():
                term_totals[idx] += weight
        # Normalize by cluster size and sort
        cluster_terms = [vocab[idx] for idx, _ in term_totals.most_common(12)]
        result.append({
            "seed": seed,
            "members": members_sorted,
            "terms": cluster_terms,
            "size": len(members),
        })

    result.sort(key=lambda x: -x["size"])
    return result


# ──────────────────────────────────────────────────────────────────────────────
# Query mode
# ──────────────────────────────────────────────────────────────────────────────

def vectorize_query(
    query: str,
    vocab: list[str],
    word_idx: dict[str, int],
    df: Counter,
    n_docs: int,
) -> dict[int, float]:
    """Turn a query string into a TF-IDF vector using the corpus vocabulary."""
    tokens = tokenize(query)
    if not tokens:
        return {}
    tf = Counter(tokens)
    vec: dict[int, float] = {}
    for word, idx in word_idx.items():
        if word in tf and word in df:
            tf_val = 1.0 + math.log(tf[word])
            idf_val = math.log(n_docs / df[word]) + 1.0
            vec[idx] = tf_val * idf_val
    norm = math.sqrt(sum(v * v for v in vec.values()))
    if norm > 0:
        vec = {k: v / norm for k, v in vec.items()}
    return vec


# ──────────────────────────────────────────────────────────────────────────────
# Rendering
# ──────────────────────────────────────────────────────────────────────────────

WIDTH = 70
BAR = "─" * WIDTH


def truncate(text: str, width: int = 90) -> str:
    text = text.replace("\n", " ").strip()
    return text[:width - 1] + "…" if len(text) > width else text


def sim_bar(sim: float) -> str:
    filled = max(1, round(sim * 20))
    return "▮" * filled + dim("▯" * (20 - filled))


def render_header(total: int, source_label: str = ""):
    print()
    src = f"  {dim(source_label)}" if source_label else ""
    print(f"  {bold(cyan('RESONATE'))}  {dim(f'{total} session pairs · semantic resonance')}{src}")
    print(f"  {dim(BAR)}")


def render_pair(
    rank: int,
    sim: float,
    sa: int,
    sb: int,
    sessions: dict[int, dict],
    vectors: dict[int, dict],
    vocab: list[str],
    show_sentences: bool = True,
):
    terms = top_shared_terms(sa, sb, vectors, vocab, n=6)
    theme = "  ·  ".join(terms[:4]) if terms else "(no shared terms)"

    gap = sb - sa
    sim_pct = f"{sim:.0%}"

    print()
    print(f"  {bold(magenta('◈'))}  {bold(theme)}")
    print(f"     {cyan(f'S{sa}')}  ↔  {cyan(f'S{sb}')}  "
          f"{dim(f'{gap} sessions apart')}  "
          f"{sim_bar(sim)}  {bold(sim_pct)}")

    if show_sentences and sa in sessions and sb in sessions:
        for num in (sa, sb):
            sent = best_sentence(sessions[num], terms)
            if sent:
                print()
                print(f"     {cyan(f'S{num}')}")
                # Word-wrap the sentence
                words = sent.split()
                line = ""
                for w in words:
                    if len(line) + len(w) + 1 > 65:
                        print(f"  {dim('│')}  {dim(line)}")
                        line = w
                    else:
                        line = (line + " " + w).strip()
                if line:
                    print(f"  {dim('│')}  {dim(line)}")


def render_session_view(
    target: int,
    sess_nums: list[int],
    sessions: dict[int, dict],
    vectors: dict[int, dict],
    vocab: list[str],
    top_n: int = 10,
    min_sim: float = 0.06,
):
    """Show all sessions resonating with a specific target session."""
    if target not in vectors:
        print(f"\n  {red(f'Session {target} not found in corpus.')}\n")
        return

    print()
    print(f"  {bold(cyan(f'S{target}'))} — what this session resonates with")
    if target in sessions:
        sess = sessions[target]
        # Find a good summary sentence (skip frontmatter)
        sents = extract_sentences(sess["text"])
        preview = truncate(sents[0], 80) if sents else ""
        if preview:
            print(f"  {dim(preview)}")
    print(f"  {dim(BAR)}")

    sims = []
    for num in sess_nums:
        if num == target:
            continue
        sim = cosine_sim(vectors[target], vectors[num])
        if sim >= min_sim:
            sims.append((sim, num))
    sims.sort(reverse=True)

    if not sims:
        print(f"\n  {dim('No strong resonances found.')}\n")
        return

    for i, (sim, num) in enumerate(sims[:top_n]):
        terms = top_shared_terms(target, num, vectors, vocab, n=4)
        theme = "  ·  ".join(terms)
        gap = abs(num - target)
        direction = "later" if num > target else "earlier"
        print()
        print(f"  {cyan(f'S{num}')}  {sim_bar(sim)}  {bold(f'{sim:.0%}')}")
        print(f"     {dim(theme)}")
        print(f"     {dim(f'{gap} sessions {direction}')}")
        if num in sessions:
            sent = best_sentence(sessions[num], terms)
            if sent:
                print(f"     {dim(truncate(sent, 80))}")

    print()
    skipped = max(0, len(sims) - top_n)
    if skipped > 0:
        print(f"  {dim(f'… {skipped} more resonant sessions below threshold.')}\n")


def render_clusters(
    cluster_list: list[dict],
    sessions: dict[int, dict],
):
    """Render theme clusters."""
    print()
    print(f"  {bold(cyan('THEME CLUSTERS'))}  {dim(f'{len(cluster_list)} clusters')}")
    print(f"  {dim(BAR)}")

    for i, cluster in enumerate(cluster_list):
        seed = cluster["seed"]
        members = cluster["members"]
        terms = cluster["terms"][:5]
        theme = "  ·  ".join(terms)

        print()
        session_list = "  ".join(cyan(f"S{m}") for m in members[:8])
        overflow = f"  {dim(f'+{len(members) - 8} more')}" if len(members) > 8 else ""
        print(f"  {bold(magenta(f'◈  {theme}'))}")
        print(f"     {session_list}{overflow}")
        print(f"     {dim(f'{len(members)} sessions · seed: S{seed}')}")

        # Show a representative sentence from the seed
        if seed in sessions:
            sent = best_sentence(sessions[seed], terms)
            if sent:
                print(f"     {dim(truncate(sent, 80))}")

    print()


def render_query_results(
    query: str,
    sims: list[tuple[float, int]],
    sessions: dict[int, dict],
    vectors: dict[int, dict],
    vocab: list[str],
    query_vec: dict[int, float],
    top_n: int = 10,
):
    """Render sessions most similar to a query."""
    print()
    print(f"  {bold(cyan('QUERY'))}: {white(query)}")
    print(f"  {dim(BAR)}")

    for sim, num in sims[:top_n]:
        terms = top_shared_terms_query(query_vec, num, vectors, vocab, n=4)
        theme = "  ·  ".join(terms)
        print()
        print(f"  {cyan(f'S{num}')}  {sim_bar(sim)}  {bold(f'{sim:.0%}')}")
        print(f"     {dim(theme)}")
        if num in sessions:
            sent = best_sentence(sessions[num], terms)
            if sent:
                print(f"     {dim(truncate(sent, 80))}")

    print()


def top_shared_terms_query(
    query_vec: dict[int, float],
    sess_num: int,
    vectors: dict[int, dict],
    vocab: list[str],
    n: int = 6,
) -> list[str]:
    """Top terms shared between query vector and session vector."""
    sv = vectors.get(sess_num, {})
    contributions = []
    for idx in set(query_vec) & set(sv):
        contributions.append((query_vec[idx] * sv[idx], vocab[idx]))
    contributions.sort(reverse=True)
    return [t for _, t in contributions[:n]]


# ──────────────────────────────────────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────────────────────────────────────

def parse_args() -> dict:
    args = sys.argv[1:]
    parsed = {
        "plain": "--plain" in args,
        "cluster": "--cluster" in args,
        "distant": "--distant" in args,
        "session": None,
        "query": None,
        "top": 12,
        "gap": 5,
        "min_sim": 0.08,
    }

    if "--session" in args:
        idx = args.index("--session")
        if idx + 1 < len(args):
            try:
                parsed["session"] = int(args[idx + 1])
            except ValueError:
                pass

    if "--query" in args:
        idx = args.index("--query")
        if idx + 1 < len(args):
            parsed["query"] = args[idx + 1]

    if "--top" in args:
        idx = args.index("--top")
        if idx + 1 < len(args):
            try:
                parsed["top"] = int(args[idx + 1])
            except ValueError:
                pass

    if "--gap" in args:
        idx = args.index("--gap")
        if idx + 1 < len(args):
            try:
                parsed["gap"] = int(args[idx + 1])
            except ValueError:
                pass

    return parsed


def main():
    opts = parse_args()

    # Load corpus and build TF-IDF
    sessions = load_corpus()
    if not sessions:
        print(f"\n  {red('No sessions found. Check that knowledge/handoffs/ exists.')}\n")
        return

    sess_nums, vocab, df, vectors, sess_tokens = build_tfidf(sessions)
    word_idx = {w: i for i, w in enumerate(vocab)}

    n_docs = len(sess_nums)

    if opts["cluster"]:
        # Theme clustering mode
        all_pairs = find_resonant_pairs(sess_nums, vectors, min_gap=opts["gap"],
                                        min_sim=opts["min_sim"])
        clusters = cluster_sessions(sess_nums, vectors, vocab, all_pairs, k=7)
        render_clusters(clusters, sessions)
        print(f"  {dim(f'Corpus: {n_docs} sessions  ·  {len(vocab)} terms')}\n")
        return

    if opts.get("distant"):
        # Distant resonance mode: high similarity, large session gap
        # Default min_gap for distant is 20; use --gap to override
        distant_min_gap = max(opts["gap"], 20)
        all_pairs = find_resonant_pairs(sess_nums, vectors, min_gap=distant_min_gap,
                                        min_sim=opts["min_sim"])
        # Re-sort by gap * similarity (independent discovery score)
        scored = [(abs(sb - sa) * sim, sim, sa, sb) for sim, sa, sb in all_pairs]
        scored.sort(reverse=True)
        top_distant = [(sim, sa, sb) for _, sim, sa, sb in scored[:opts["top"]]]
        render_header(len(scored), "distant independent discoveries")
        for rank, (sim, sa, sb) in enumerate(top_distant):
            render_pair(rank, sim, sa, sb, sessions, vectors, vocab)
            if rank < len(top_distant) - 1:
                print(f"  {dim(BAR)}")
        print(f"\n  {dim(f'Corpus: {n_docs} sessions  ·  sorted by gap × similarity')}\n")
        return

    if opts["query"] is not None:
        # Query mode
        query_vec = vectorize_query(opts["query"], vocab, word_idx, df, n_docs)
        if not query_vec:
            print(f"\n  {red('Query produced no matching terms in vocabulary.')}\n")
            return
        sims = [(cosine_sim(query_vec, vectors[num]), num)
                for num in sess_nums if vectors[num]]
        sims = [(s, n) for s, n in sorted(sims, reverse=True) if s >= 0.05]
        render_query_results(opts["query"], sims, sessions, vectors, vocab,
                             query_vec, top_n=opts["top"])
        print(f"  {dim(f'Corpus: {n_docs} sessions  ·  {len(vocab)} terms')}\n")
        return

    if opts["session"] is not None:
        # Single-session resonance view
        render_session_view(
            opts["session"], sess_nums, sessions, vectors, vocab,
            top_n=opts["top"],
        )
        print(f"  {dim(f'Corpus: {n_docs} sessions  ·  {len(vocab)} terms')}\n")
        return

    # Default: top resonant pairs
    all_pairs = find_resonant_pairs(sess_nums, vectors, min_gap=opts["gap"],
                                    min_sim=opts["min_sim"])
    if not all_pairs:
        print(f"\n  {dim('No strong resonances found. Try --gap 3 or a lower threshold.')}\n")
        return

    render_header(len(all_pairs))
    for rank, (sim, sa, sb) in enumerate(all_pairs[:opts["top"]]):
        render_pair(rank, sim, sa, sb, sessions, vectors, vocab)
        if rank < min(opts["top"], len(all_pairs)) - 1:
            print(f"  {dim(BAR)}")

    skipped = len(all_pairs) - opts["top"]
    print()
    if skipped > 0:
        print(f"  {dim(f'… {skipped} more resonant pairs. Use --top N to show more.')}")
    gap_val = opts["gap"]
    print(f"  {dim(f'Corpus: {n_docs} sessions  ·  {len(vocab)} terms  ·  gap ≥ {gap_val}')}\n")


if __name__ == "__main__":
    main()
