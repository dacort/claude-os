"""
knowledge-search.py — TF-IDF ranked retrieval over the claude-os knowledge base.

Different from search.py (keyword match) — this ranks results by concept
proximity. Useful when you remember the idea but not the exact words.

Usage:
    python3 projects/knowledge-search.py "when did we add haiku generator"
    python3 projects/knowledge-search.py "spawn tasks orchestration" --top 10
    python3 projects/knowledge-search.py --rebuild        # force index rebuild
    python3 projects/knowledge-search.py --stats          # show index stats
    python3 projects/knowledge-search.py --plain "query"  # no ANSI color

Index is cached in knowledge/.knowledge-search-index.json.
Rebuilt automatically when source files change.
"""

from __future__ import annotations
import argparse
import json
import math
import re
import sys
import time
from pathlib import Path
from typing import Iterator


# ── Configuration ─────────────────────────────────────────────────────────────

REPO = Path(__file__).parent.parent
INDEX_PATH = REPO / "knowledge" / ".knowledge-search-index.json"
CHUNK_MIN_WORDS = 15          # ignore very short paragraphs
CHUNK_MAX_CHARS = 1200        # hard cap on snippet display
TOP_K_DEFAULT = 5
SNIPPET_CHARS = 200           # chars to show in result

STOP_WORDS = set("""
a an the and or not is are was were be been being have has had do does did
will would could should may might shall must can this that these those with
for from to of in on at by as it its i we you they he she they my our your
their his her its which who what when where why how all any both each few
more most other some such than too very just also only but so if then
""".split())


# ── ANSI colors ───────────────────────────────────────────────────────────────

USE_COLOR = True

def c(code: str, text: str) -> str:
    if not USE_COLOR:
        return text
    codes = {"bold": "1", "dim": "2", "red": "31", "green": "32",
             "yellow": "33", "blue": "34", "magenta": "35", "cyan": "36",
             "white": "37", "gray": "90"}
    return f"\x1b[{codes.get(code, code)}m{text}\x1b[0m"


# ── Tokenization ──────────────────────────────────────────────────────────────

def tokenize(text: str) -> list[str]:
    """Lowercase, strip non-alpha, remove stop words and very short tokens."""
    words = re.findall(r"[a-z']+", text.lower())
    return [w.strip("'") for w in words
            if w not in STOP_WORDS and len(w) > 2]


def tokenize_with_bigrams(text: str) -> list[str]:
    """Unigrams + bigrams for better phrase matching."""
    tokens = tokenize(text)
    bigrams = [f"{tokens[i]}_{tokens[i+1]}" for i in range(len(tokens) - 1)]
    return tokens + bigrams


# ── Document loading ──────────────────────────────────────────────────────────

SOURCE_TYPES = [
    ("note",      REPO.glob("projects/field-notes-*.md")),
    ("knowledge", REPO.glob("knowledge/*.md")),
    ("handoff",   REPO.glob("knowledge/handoffs/*.md")),
    ("task",      (p for d in [REPO / "tasks" / "completed", REPO / "tasks" / "failed",
                                REPO / "tasks" / "pending"]
                     for p in d.glob("*.md"))),
]


def iter_sources() -> Iterator[tuple[str, Path]]:
    """Yield (source_type, path) for all indexable files."""
    for src_type, paths in SOURCE_TYPES:
        for p in sorted(paths):
            yield src_type, p


def chunk_text(text: str, source_id: str) -> list[dict]:
    """
    Split a document into indexable chunks (paragraph-level).
    Returns list of {"text": str, "char_start": int}.
    """
    # Strip YAML frontmatter
    if text.startswith("---"):
        end = text.find("---", 3)
        if end > 0:
            text = text[end + 3:].lstrip("\n")

    # For markdown: split on blank lines (paragraph chunks)
    paragraphs = re.split(r"\n\s*\n", text)

    chunks = []
    char_pos = 0
    for para in paragraphs:
        para = para.strip()
        if not para:
            char_pos += len(para) + 2
            continue
        words = para.split()
        if len(words) >= CHUNK_MIN_WORDS:
            chunks.append({
                "text": para[:CHUNK_MAX_CHARS],
                "word_count": len(words),
                "char_start": char_pos,
            })
        char_pos += len(para) + 2

    # If no chunks from paragraph split, fall back to the whole file
    if not chunks and len(text.split()) >= CHUNK_MIN_WORDS:
        chunks.append({"text": text[:CHUNK_MAX_CHARS], "word_count": len(text.split()), "char_start": 0})

    return chunks


# ── Index building ─────────────────────────────────────────────────────────────

def build_index(verbose: bool = False) -> dict:
    """Build the TF-IDF index from scratch. Returns the index dict."""
    t0 = time.time()

    docs = []           # list of {id, type, path, chunks:[{text, tf:{}}]}
    df = {}             # document frequency: {term: count_of_docs_containing_term}

    for src_type, path in iter_sources():
        try:
            text = path.read_text(errors="replace")
        except Exception:
            continue

        chunks = chunk_text(text, str(path))
        if not chunks:
            continue

        doc_chunks = []
        doc_terms_seen = set()  # for DF counting (once per doc)

        for chunk in chunks:
            tokens = tokenize_with_bigrams(chunk["text"])
            if not tokens:
                continue
            tf = {}
            for tok in tokens:
                tf[tok] = tf.get(tok, 0) + 1
            doc_chunks.append({
                "text": chunk["text"],
                "tf": tf,
            })
            for tok in tf:
                if tok not in doc_terms_seen:
                    df[tok] = df.get(tok, 0) + 1
                    doc_terms_seen.add(tok)

        if doc_chunks:
            docs.append({
                "id": path.name,
                "type": src_type,
                "path": str(path.relative_to(REPO)),
                "chunks": doc_chunks,
            })

    num_docs = sum(len(d["chunks"]) for d in docs)

    # Compute IDF
    N = len(docs)
    idf = {term: math.log((N + 1) / (freq + 1)) + 1.0
           for term, freq in df.items()}

    elapsed = time.time() - t0
    if verbose:
        print(c("dim", f"  indexed {len(docs)} files, {num_docs} chunks in {elapsed:.2f}s"))

    return {
        "metadata": {
            "built_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "num_files": len(docs),
            "num_chunks": num_docs,
            "num_terms": len(idf),
            "elapsed_s": round(elapsed, 2),
        },
        "idf": idf,
        "docs": docs,
    }


def needs_rebuild(index: dict) -> bool:
    """Check if any source is newer than the index."""
    if "metadata" not in index:
        return True
    built_ts = index["metadata"].get("built_at", "")
    if not built_ts:
        return True
    try:
        import datetime
        built = datetime.datetime.fromisoformat(built_ts.replace("Z", "+00:00"))
        built_epoch = built.timestamp()
    except Exception:
        return True
    for _, path in iter_sources():
        try:
            if path.stat().st_mtime > built_epoch:
                return True
        except Exception:
            pass
    return False


def load_or_build_index(force_rebuild: bool = False, verbose: bool = False) -> dict:
    """Load from cache or rebuild if stale/missing."""
    if not force_rebuild and INDEX_PATH.exists():
        try:
            index = json.loads(INDEX_PATH.read_text())
            if not needs_rebuild(index):
                return index
            if verbose:
                print(c("dim", "  index stale, rebuilding..."))
        except Exception:
            pass

    index = build_index(verbose=verbose)
    INDEX_PATH.parent.mkdir(parents=True, exist_ok=True)
    INDEX_PATH.write_text(json.dumps(index, separators=(",", ":")))
    return index


# ── Scoring ───────────────────────────────────────────────────────────────────

def score_chunk(query_tokens: list[str], chunk_tf: dict, idf: dict) -> float:
    """
    BM25-inspired scoring: sum of TF-IDF weights for query terms in chunk.
    BM25 normalization would need corpus stats; this is simpler and fast.
    """
    score = 0.0
    for qt in query_tokens:
        if qt in chunk_tf and qt in idf:
            # Sublinear TF scaling: 1 + log(tf) to dampen high-frequency terms
            tf_val = chunk_tf[qt]
            scaled_tf = 1.0 + math.log(tf_val) if tf_val > 0 else 0.0
            score += scaled_tf * idf[qt]
    return score


def search(query: str, index: dict, top_k: int = TOP_K_DEFAULT) -> list[dict]:
    """Return top_k results sorted by relevance score."""
    idf = index["idf"]
    query_tokens = tokenize_with_bigrams(query)

    if not query_tokens:
        return []

    results = []
    for doc in index["docs"]:
        for chunk_idx, chunk in enumerate(doc["chunks"]):
            score = score_chunk(query_tokens, chunk["tf"], idf)
            if score > 0:
                results.append({
                    "score": score,
                    "doc_id": doc["id"],
                    "doc_type": doc["type"],
                    "doc_path": doc["path"],
                    "chunk_idx": chunk_idx,
                    "text": chunk["text"],
                })

    results.sort(key=lambda r: r["score"], reverse=True)
    return results[:top_k]


# ── Display ───────────────────────────────────────────────────────────────────

def format_snippet(text: str, query_tokens: list[str], max_chars: int = SNIPPET_CHARS) -> str:
    """
    Return a snippet, preferring the region with the most query term hits.
    Highlights query terms if color is on.
    """
    # Find the densest region
    words = text.split()
    window = 40  # words per window
    best_start = 0
    best_hits = 0

    unigram_tokens = set(t for t in query_tokens if "_" not in t)

    for i in range(len(words)):
        window_words = words[i:i + window]
        hits = sum(1 for w in window_words
                   if re.sub(r"[^a-z]", "", w.lower()) in unigram_tokens)
        if hits > best_hits:
            best_hits = hits
            best_start = i

    snippet_words = words[best_start:best_start + window]
    snippet = " ".join(snippet_words)

    if len(snippet) > max_chars:
        snippet = snippet[:max_chars].rsplit(" ", 1)[0] + "…"

    # Highlight query terms
    if USE_COLOR:
        for tok in unigram_tokens:
            snippet = re.sub(
                rf"\b({re.escape(tok)})\b",
                lambda m: c("yellow", m.group(0)),
                snippet,
                flags=re.IGNORECASE,
            )

    return snippet


TYPE_COLORS = {
    "note": "cyan",
    "knowledge": "magenta",
    "handoff": "green",
    "task": "blue",
}

TYPE_LABELS = {
    "note": "note",
    "knowledge": "docs",
    "handoff": "hand",
    "task": "task",
}


def print_results(results: list[dict], query: str, elapsed_ms: float) -> None:
    query_tokens = tokenize_with_bigrams(query)
    unigram_tokens = set(t for t in query_tokens if "_" not in t)

    if not results:
        print(c("dim", f"  no results for: {query!r}"))
        return

    print()
    print(c("bold", f"  {len(results)} results") + c("dim", f"  for: {query!r}  ({elapsed_ms:.0f}ms)"))
    print()

    for i, r in enumerate(results, 1):
        score_bar = "●" * min(int(r["score"] / 2), 8)
        score_str = c("dim", f"{r['score']:.1f} {score_bar:<8}")

        doc_type = r["doc_type"]
        type_col = TYPE_COLORS.get(doc_type, "white")
        type_label = TYPE_LABELS.get(doc_type, doc_type)

        label = c(type_col, f"[{type_label}]")
        doc_id = c("bold", r["doc_id"])

        print(f"  {c('dim', str(i) + '.')} {label} {doc_id}  {score_str}")

        snippet = format_snippet(r["text"], list(unigram_tokens))
        print(f"     {c('dim', snippet)}")
        print()


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    global USE_COLOR

    parser = argparse.ArgumentParser(
        description="TF-IDF semantic search over the claude-os knowledge base",
        add_help=True,
    )
    parser.add_argument("query", nargs="?", help="Search query")
    parser.add_argument("--top", type=int, default=TOP_K_DEFAULT, metavar="N",
                        help=f"Return top N results (default: {TOP_K_DEFAULT})")
    parser.add_argument("--rebuild", action="store_true",
                        help="Force index rebuild")
    parser.add_argument("--stats", action="store_true",
                        help="Show index statistics")
    parser.add_argument("--plain", action="store_true",
                        help="No ANSI color (for piped output)")
    parser.add_argument("--json", action="store_true",
                        help="Output results as JSON")
    args = parser.parse_args()

    if args.plain or not sys.stdout.isatty():
        USE_COLOR = False

    verbose = not args.json

    # Load / build index
    t_load = time.time()
    index = load_or_build_index(force_rebuild=args.rebuild, verbose=verbose)
    load_ms = (time.time() - t_load) * 1000

    if args.stats or (not args.query and not args.rebuild):
        meta = index.get("metadata", {})
        print()
        print(c("bold", "  knowledge-search index"))
        print(c("dim",  f"  built: {meta.get('built_at', 'unknown')}"))
        print(c("dim",  f"  files: {meta.get('num_files', '?')}"))
        print(c("dim",  f"  chunks: {meta.get('num_chunks', '?')}"))
        print(c("dim",  f"  terms: {meta.get('num_terms', '?')}"))
        print()
        print(c("dim", "  usage: python3 projects/knowledge-search.py \"your query here\""))
        print()
        return

    if args.rebuild and not args.query:
        meta = index.get("metadata", {})
        print(c("green", f"  rebuilt: {meta.get('num_files')} files, "
                         f"{meta.get('num_chunks')} chunks, "
                         f"{meta.get('num_terms')} terms"))
        return

    if not args.query:
        parser.print_help()
        return

    # Search
    t_search = time.time()
    results = search(args.query, index, top_k=args.top)
    search_ms = (time.time() - t_search) * 1000

    if args.json:
        out = []
        for r in results:
            out.append({
                "score": r["score"],
                "source": r["doc_id"],
                "type": r["doc_type"],
                "path": r["doc_path"],
                "text": r["text"][:400],
            })
        print(json.dumps(out, indent=2))
        return

    print_results(results, args.query, search_ms + load_ms)


if __name__ == "__main__":
    main()
