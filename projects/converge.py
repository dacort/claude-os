#!/usr/bin/env python3
"""
converge.py — Convergence map of independently-rediscovered ideas

resonate.py shows session PAIRS that think alike.
converge.py shows THEMES that keep getting independently rediscovered —
the ideas the architecture keeps generating, session after session.

A theme with high convergence appeared in N pairs spanning large session gaps.
These are the constitutional questions of the system: the things it keeps
arriving at without being told to.

Usage:
    python3 projects/converge.py               # top themes by convergence score
    python3 projects/converge.py --top 15      # show more themes
    python3 projects/converge.py --gap 30      # min session gap (default: 20)
    python3 projects/converge.py --theme letter  # deep dive one theme
    python3 projects/converge.py --sessions    # which sessions appear in most themes
    python3 projects/converge.py --plain       # no ANSI

Convergence score = (number of independent pairs) × (average session gap / 10)
A theme that appeared 4 times with average gap 60 scores 24. High = constitutional.

Difference from resonate.py:
    resonate.py:  shows PAIRS of similar sessions
    converge.py:  shows THEMES that appear across multiple independent pairs

Built session 128, 2026-04-17. Companion to resonate.py.
"""

import math
import re
import sys
import json
from pathlib import Path
from collections import Counter, defaultdict


# ──────────────────────────────────────────────────────────────────────────────
# Colors
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

REPO        = Path(__file__).parent.parent
HANDOFFS    = REPO / "knowledge" / "handoffs"
SUMMARIES   = REPO / "knowledge" / "workshop-summaries.json"
FIELD_NOTES = REPO / "knowledge" / "field-notes"


# ──────────────────────────────────────────────────────────────────────────────
# Stopwords — same as resonate.py
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
    "here", "very", "own", "too", "most", "such", "both", "other", "while",
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
    "good", "bad", "new", "old", "big", "small", "large", "medium", "high",
    "low", "long", "short", "full", "real", "clear", "clean", "simple",
    "hard", "easy", "right", "wrong", "true", "false", "main", "general",
    "current", "recent", "past", "future", "last", "first", "next", "later",
    "better", "best", "worse", "worst", "different", "similar", "specific",
    "direct", "actual", "certain", "little", "few", "much", "many", "whole",
    "session", "sessions", "workshop", "handoff", "task", "tool", "tools",
    "tasks", "project", "projects", "commit", "commits", "repo", "field",
    "notes", "instance", "worker", "controller", "profile", "status",
    "failed", "completed", "python", "script", "file", "files", "output",
    "code", "line", "lines", "note", "notes", "time", "day", "week", "hour",
    "thing", "things", "way", "ways", "something", "anything", "nothing",
    "everything", "bit", "lot", "back", "hand", "bit", "part", "point",
    "case", "kind", "type", "form", "side", "place", "number", "word",
    "words", "text", "data", "version", "name", "list", "set", "group",
    "vs", "via", "per", "etc",
}


# ──────────────────────────────────────────────────────────────────────────────
# Text processing
# ──────────────────────────────────────────────────────────────────────────────

def clean_text(text: str) -> str:
    text = re.sub(r'```[\s\S]*?```', ' ', text)
    text = re.sub(r'`[^`\n]+`', ' ', text)
    text = re.sub(r'https?://\S+', ' ', text)
    text = re.sub(r'^---[\s\S]*?---\n', '', text, count=1)
    text = re.sub(r'##\s+', ' ', text)
    text = re.sub(r'#\s+', ' ', text)
    text = re.sub(r'\*\*.*?\*\*', ' ', text)
    return text


def tokenize(text: str) -> list:
    text = clean_text(text)
    words = re.findall(r'\b[a-z][a-z\-]{2,}\b', text.lower())
    return [w for w in words if w not in STOPWORDS and len(w) >= 3]


def extract_sentences(text: str) -> list:
    text = clean_text(text)
    parts = re.split(r'(?<=[.!?])\s+|\n{2,}', text)
    result = []
    for p in parts:
        p = p.strip()
        p = re.sub(r'\s+', ' ', p)
        if 40 <= len(p) <= 250:
            if re.match(r'^(session:|date:|status:|profile:|priority:|agent:|model:)', p.lower()):
                continue
            if p.startswith(('-', '*', '•', '·')):
                p = p.lstrip('-*•· ').strip()
            if len(p) >= 40:
                result.append(p)
    return result


# ──────────────────────────────────────────────────────────────────────────────
# Corpus loading
# ──────────────────────────────────────────────────────────────────────────────

def load_corpus() -> dict:
    sessions = {}

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
            }

    if SUMMARIES.exists():
        try:
            data = json.loads(SUMMARIES.read_text())
        except json.JSONDecodeError:
            data = {}

        entries = []
        for key, summary_text in data.items():
            m = re.search(r'(\d{8})-(\d{6})', key)
            sort_key = float(m.group(1) + "." + m.group(2)) if m else 0.0
            entries.append((sort_key, key, str(summary_text)))
        entries.sort()

        for sess_i, (_, key, summary_text) in enumerate(entries, 1):
            lower = summary_text.lower()
            if "quota" in lower or "ended early" in lower or len(summary_text.strip()) < 20:
                continue
            if sess_i not in sessions and sess_i < 100:
                sessions[sess_i] = {
                    "session_num": sess_i,
                    "label": f"S{sess_i}",
                    "text": summary_text,
                    "sources": ["summary"],
                }

    return sessions


# ──────────────────────────────────────────────────────────────────────────────
# TF-IDF
# ──────────────────────────────────────────────────────────────────────────────

def build_tfidf(sessions: dict) -> tuple:
    sess_nums = sorted(sessions.keys())
    n = len(sess_nums)
    if n == 0:
        return [], [], Counter(), {}, {}

    sess_tokens = {}
    for num in sess_nums:
        sess_tokens[num] = tokenize(sessions[num]["text"])

    df = Counter()
    for tokens in sess_tokens.values():
        for word in set(tokens):
            df[word] += 1

    min_df = max(2, int(n * 0.03))
    max_df = int(n * 0.85)
    vocab = sorted(w for w, d in df.items() if min_df <= d <= max_df and len(w) >= 3)
    word_idx = {w: i for i, w in enumerate(vocab)}

    vectors = {}
    for num in sess_nums:
        tokens = sess_tokens[num]
        if not tokens:
            vectors[num] = {}
            continue
        tf = Counter(tokens)
        vec = {}
        for word, idx in word_idx.items():
            if word in tf:
                tf_val = 1.0 + math.log(tf[word])
                idf_val = math.log(n / df[word]) + 1.0
                vec[idx] = tf_val * idf_val
        vectors[num] = vec

    for num in sess_nums:
        vec = vectors[num]
        norm = math.sqrt(sum(v * v for v in vec.values()))
        if norm > 0:
            vectors[num] = {k: v / norm for k, v in vec.items()}

    return sess_nums, vocab, df, vectors, sess_tokens


def cosine_sim(va: dict, vb: dict) -> float:
    if not va or not vb:
        return 0.0
    if len(va) > len(vb):
        va, vb = vb, va
    return sum(v * vb[k] for k, v in va.items() if k in vb)


def top_shared_terms(si: int, sj: int, vectors: dict, vocab: list, n: int = 4) -> list:
    va, vb = vectors[si], vectors[sj]
    contribs = [(va[idx] * vb[idx], vocab[idx]) for idx in set(va) & set(vb)]
    contribs.sort(reverse=True)
    return [term for _, term in contribs[:n]]


def best_sentence_for(session: dict, terms: list) -> str:
    sentences = extract_sentences(session["text"])
    if not sentences:
        return session["text"][:200].replace("\n", " ").strip()
    term_set = set(terms)
    best_text, best_score = "", -1
    for sent in sentences:
        words = set(re.findall(r'\b[a-z]{3,}\b', sent.lower()))
        score = len(words & term_set)
        if score > best_score and not re.match(r'^[\d\-•]', sent):
            best_score, best_text = score, sent
    return best_text or sentences[0]


# ──────────────────────────────────────────────────────────────────────────────
# Convergence analysis
# ──────────────────────────────────────────────────────────────────────────────

def compute_convergence(
    sess_nums: list,
    sessions: dict,
    vectors: dict,
    vocab: list,
    min_gap: int = 20,
    min_sim: float = 0.10,
    terms_per_pair: int = 3,
) -> list:
    """Compute convergence map: which themes appear in the most independent pairs.

    Returns list of theme dicts, sorted by convergence score.
    """
    # Step 1: find all qualifying distant pairs
    all_pairs = []
    for i, si in enumerate(sess_nums):
        for sj in sess_nums[i + 1:]:
            gap = abs(si - sj)
            if gap < min_gap:
                continue
            sim = cosine_sim(vectors[si], vectors[sj])
            if sim >= min_sim:
                terms = top_shared_terms(si, sj, vectors, vocab, terms_per_pair)
                all_pairs.append({
                    "si": si,
                    "sj": sj,
                    "gap": gap,
                    "sim": sim,
                    "terms": terms,
                    "score": gap * sim,
                })

    # Step 2: group pairs by their top terms
    # Each pair contributes to its top-1 term (to avoid double-counting)
    theme_pairs: dict = defaultdict(list)
    for pair in all_pairs:
        if pair["terms"]:
            primary = pair["terms"][0]
            theme_pairs[primary].append(pair)

    # Step 3: compute per-theme convergence
    themes = []
    for term, pairs in theme_pairs.items():
        if len(pairs) < 2:
            continue  # need at least 2 independent rediscoveries

        avg_gap = sum(p["gap"] for p in pairs) / len(pairs)
        avg_sim = sum(p["sim"] for p in pairs) / len(pairs)
        # Convergence = frequency × independence (gap)
        conv_score = len(pairs) * (avg_gap / 10)

        # All sessions involved in this theme
        involved = set()
        for p in pairs:
            involved.add(p["si"])
            involved.add(p["sj"])

        # Sort pairs by gap × sim (most independent first)
        pairs_sorted = sorted(pairs, key=lambda p: -(p["gap"] * p["sim"]))

        themes.append({
            "term": term,
            "n_pairs": len(pairs),
            "avg_gap": avg_gap,
            "avg_sim": avg_sim,
            "conv_score": conv_score,
            "sessions": sorted(involved),
            "pairs": pairs_sorted,
        })

    themes.sort(key=lambda t: -t["conv_score"])
    return themes


# ──────────────────────────────────────────────────────────────────────────────
# Session connectivity
# ──────────────────────────────────────────────────────────────────────────────

def session_theme_count(themes: list) -> Counter:
    """How many convergent themes does each session appear in?"""
    counts: Counter = Counter()
    for theme in themes:
        for s in theme["sessions"]:
            counts[s] += 1
    return counts


# ──────────────────────────────────────────────────────────────────────────────
# Display
# ──────────────────────────────────────────────────────────────────────────────

def bar(value: float, max_val: float, width: int = 12) -> str:
    filled = int(round(value / max_val * width)) if max_val > 0 else 0
    filled = max(0, min(width, filled))
    empty = width - filled
    return "▮" * filled + dim("▯" * empty)


def render_theme(theme: dict, sessions: dict, rank: int, max_score: float) -> None:
    term = theme["term"]
    n = theme["n_pairs"]
    avg_gap = theme["avg_gap"]
    conv = theme["conv_score"]

    print(f"  {bold(magenta('◈'))}  {bold(term)}  "
          f"{dim(f'{n} pairs · avg gap {avg_gap:.0f}')}")

    print(f"     {bar(conv, max_score)}  "
          f"{bold(yellow(f'{conv:.1f}'))}")

    # Show the 2 most distant pairs
    for pair in theme["pairs"][:2]:
        si, sj = pair["si"], pair["sj"]
        gap = pair["gap"]

        print(f"\n     {cyan(f'S{si}')}  ↔  {cyan(f'S{sj}')}  "
              f"{dim(f'{gap} sessions apart')}")

        for snum in (si, sj):
            if snum in sessions:
                snip = best_sentence_for(sessions[snum], theme["pairs"][0]["terms"])
                if snip:
                    lines = [snip[i:i+65] for i in range(0, len(snip), 65)]
                    for j, line in enumerate(lines[:2]):
                        prefix = dim("│  ") if j == 0 else dim("   ")
                        print(f"     {prefix}{dim(line)}")

    if n > 2:
        extra_sessions = sorted(set(theme["sessions"]) - {theme["pairs"][0]["si"], theme["pairs"][0]["sj"]})
        if extra_sessions:
            labels = " · ".join(cyan(f"S{s}") for s in extra_sessions[:4])
            extra = f"+{n-2} more pairs" if n > 3 else f"+{n-2} more pair"
            print(f"\n     {dim('also:')} {labels}  {dim(extra)}")

    print()


def render_sessions_view(themes: list, sessions: dict) -> None:
    counts = session_theme_count(themes)
    if not counts:
        print("No data.")
        return

    print(f"\n  {bold('Most constitutionally connected sessions')}")
    print(f"  {dim('sessions appearing in the most independent-rediscovery themes')}\n")

    max_count = max(counts.values()) if counts else 1
    for sess_num, count in counts.most_common(15):
        label = cyan(f"S{sess_num}")
        b = bar(count, max_count, 8)
        snip = ""
        if sess_num in sessions:
            text = sessions[sess_num]["text"][:500]
            # Get first real sentence
            for line in text.split("\n"):
                line = line.strip()
                if len(line) > 40 and not line.startswith("#") and not line.startswith("---"):
                    snip = dim("  " + line[:70])
                    break
        print(f"  {label}  {b}  {bold(str(count))} {'theme' if count == 1 else 'themes'}")
        if snip:
            print(f"  {snip}")
        print()


def render_theme_detail(term: str, themes: list, sessions: dict) -> None:
    match = next((t for t in themes if t["term"] == term), None)
    if not match:
        # Try partial match
        term_lower = term.lower()
        match = next((t for t in themes if term_lower in t["term"]), None)
    if not match:
        print(f"  Theme '{term}' not found. Try: " +
              ", ".join(t["term"] for t in themes[:10]))
        return

    t = match
    print(f"\n  {bold(magenta('◈'))}  {bold(t['term'])}")
    n_pairs = t["n_pairs"]
    avg_gap_val = t["avg_gap"]
    conv_score_val = t["conv_score"]
    print(f"  {dim(f'{n_pairs} independent pairs · avg gap {avg_gap_val:.0f} sessions · conv score {conv_score_val:.1f}')}")
    print(f"  {dim('All sessions: ')} " + " · ".join(cyan(f"S{s}") for s in t["sessions"]))
    print()

    for i, pair in enumerate(t["pairs"], 1):
        si, sj = pair["si"], pair["sj"]
        pair_gap = pair["gap"]
        pair_pct = pair["sim"] * 100
        print(f"  {bold(f'Pair {i}')}  {cyan(f'S{si}')} ↔ {cyan(f'S{sj}')}  "
              f"{dim(f'{pair_gap} sessions apart · {pair_pct:.0f}% similarity')}")
        print(f"  {dim('Shared terms:')} " + "  ·  ".join(yellow(x) for x in pair["terms"]))
        print()
        for snum in (si, sj):
            if snum in sessions:
                snip = best_sentence_for(sessions[snum], pair["terms"])
                print(f"  {cyan(f'S{snum}')}")
                if snip:
                    lines = [snip[i:i+70] for i in range(0, len(snip), 70)]
                    for line in lines[:3]:
                        print(f"  {dim('│  ')}{dim(line)}")
                print()


# ──────────────────────────────────────────────────────────────────────────────
# Entry point
# ──────────────────────────────────────────────────────────────────────────────

def main():
    args = sys.argv[1:]

    # Parse flags
    top_n = 10
    min_gap = 20
    theme_query = None
    sessions_mode = False

    i = 0
    while i < len(args):
        a = args[i]
        if a in ("--plain",):
            pass
        elif a == "--top" and i + 1 < len(args):
            try:
                top_n = int(args[i + 1])
                i += 1
            except ValueError:
                pass
        elif a == "--gap" and i + 1 < len(args):
            try:
                min_gap = int(args[i + 1])
                i += 1
            except ValueError:
                pass
        elif a == "--theme" and i + 1 < len(args):
            theme_query = args[i + 1]
            i += 1
        elif a == "--sessions":
            sessions_mode = True
        i += 1

    # Load data
    sessions = load_corpus()
    if not sessions:
        print("No sessions found.")
        return

    sess_nums, vocab, df, vectors, _ = build_tfidf(sessions)

    if len(sess_nums) < 10:
        print("Not enough sessions for convergence analysis.")
        return

    themes = compute_convergence(
        sess_nums, sessions, vectors, vocab,
        min_gap=min_gap, min_sim=0.09,
    )

    if not themes:
        print("No convergent themes found.")
        return

    # Header
    print()
    print(f"  {bold(cyan('CONVERGE'))}  "
          f"{dim(f'{len(sess_nums)} sessions · ')} "
          f"{dim(f'{len(themes)} convergent themes')}")
    print(f"  {dim(f'min gap: {min_gap} sessions · constitutional rediscoveries')}")
    print(f"  {dim('─' * 66)}")
    print()

    if theme_query:
        render_theme_detail(theme_query, themes, sessions)
        return

    if sessions_mode:
        render_sessions_view(themes, sessions)
        return

    # Default: top themes
    max_score = themes[0]["conv_score"] if themes else 1.0
    shown = 0
    for theme in themes:
        if shown >= top_n:
            break
        render_theme(theme, sessions, shown + 1, max_score)
        shown += 1

    print(f"  {dim(f'Corpus: {len(sess_nums)} sessions · {len(themes)} total themes · sorted by convergence score')}")
    print(f"  {dim('Convergence = n_pairs × avg_gap/10   |   run --theme WORD for deep dive')}")
    print()


if __name__ == "__main__":
    main()
