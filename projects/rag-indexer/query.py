"""
RAG Indexer query CLI.

Usage:
    python3 query.py "what photos did I take in 2024?"
    python3 query.py --top 5 "my Python projects"
    python3 query.py --source s3 "recent uploads"
    python3 query.py --count   (show indexed chunk count)

Environment:
    QDRANT_URL           vector store URL
    ANTHROPIC_API_KEY    for Claude embeddings
    EMBED_BACKEND        "claude" (default) or "local"
"""

import sys
import os
import argparse


def main():
    parser = argparse.ArgumentParser(
        description="Semantic search over dacort's indexed digital life"
    )
    parser.add_argument("query", nargs="?", help="Search query")
    parser.add_argument("--top", "-n", type=int, default=10, help="Number of results (default: 10)")
    parser.add_argument("--source", "-s", help="Filter by source: s3, dropbox")
    parser.add_argument("--count", action="store_true", help="Show total indexed chunks and exit")
    parser.add_argument("--plain", action="store_true", help="Plain output (no ANSI colors)")
    args = parser.parse_args()

    try:
        from indexer.pipeline import QueryEngine
        from indexer.store import QdrantStore
    except ImportError as e:
        print(f"Error: {e}", file=sys.stderr)
        print("Make sure qdrant-client and anthropic are installed.", file=sys.stderr)
        sys.exit(1)

    # ANSI helpers
    if args.plain:
        def c(code, text): return text
    else:
        def c(code, text): return f"\033[{code}m{text}\033[0m"

    if args.count:
        store = QdrantStore()
        try:
            count = store.count()
            print(f"{count} chunks indexed")
        except Exception as e:
            print(f"Error connecting to Qdrant: {e}", file=sys.stderr)
            sys.exit(1)
        return

    if not args.query:
        parser.print_help()
        sys.exit(1)

    engine = QueryEngine.from_env()
    results = engine.search(args.query, top_k=args.top, source=args.source)

    if not results:
        print("No results found.")
        return

    print(c("1;36", f"\n  Results for: {args.query}") + "\n")

    for r in results:
        source_label = f"[{r.chunk.source}]"
        score_label = f"{r.score:.3f}"
        doc_id = r.chunk.document_id
        snippet = r.chunk.text[:200].replace("\n", " ")
        if len(r.chunk.text) > 200:
            snippet += "..."

        print(c("2", f"  {r.rank + 1}.") + " " + c("1", doc_id))
        print(c("32", f"     score: {score_label}") + "  " + c("2", source_label))
        print(c("2", f"     {snippet}"))
        print()


if __name__ == "__main__":
    main()
