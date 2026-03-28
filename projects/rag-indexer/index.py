"""
RAG Indexer ingestion CLI.

Usage:
    python3 index.py                    (run full index from env config)
    python3 index.py --dry-run          (scan and chunk, no embedding/storage)
    python3 index.py --bucket my-bucket (override S3 bucket)
    python3 index.py --prefix docs/     (only index objects under prefix)

Environment:
    CONNECTOR            "s3" (default)
    S3_BUCKET            S3 bucket name
    S3_PREFIX            optional key prefix (default: "")
    QDRANT_URL           vector store URL
    ANTHROPIC_API_KEY    for Claude embeddings
    EMBED_BACKEND        "claude" (default) or "local"

These come from the project secret: claude-os-project-rag-indexer
"""

import sys
import os
import json
import argparse


def main():
    parser = argparse.ArgumentParser(
        description="Index dacort's digital life into the RAG vector store"
    )
    parser.add_argument("--dry-run", action="store_true",
                        help="Scan and chunk without embedding or storing")
    parser.add_argument("--bucket", help="S3 bucket name (overrides S3_BUCKET env var)")
    parser.add_argument("--prefix", help="S3 key prefix filter")
    parser.add_argument("--stats-json", action="store_true",
                        help="Print final stats as JSON to stdout")
    args = parser.parse_args()

    if args.bucket:
        os.environ["S3_BUCKET"] = args.bucket
    if args.prefix:
        os.environ["S3_PREFIX"] = args.prefix

    # Validate required env vars
    required = ["S3_BUCKET"]
    if not args.dry_run:
        required += ["QDRANT_URL"]

    missing = [v for v in required if not os.environ.get(v)]
    if missing:
        print(f"Missing environment variables: {', '.join(missing)}", file=sys.stderr)
        print("These should be in the project secret: claude-os-project-rag-indexer", file=sys.stderr)
        sys.exit(1)

    try:
        from indexer.pipeline import IndexingPipeline
    except ImportError as e:
        print(f"Import error: {e}", file=sys.stderr)
        print("Make sure boto3, qdrant-client, and anthropic are installed.", file=sys.stderr)
        sys.exit(1)

    pipeline = IndexingPipeline.from_env()
    stats = pipeline.run(dry_run=args.dry_run)

    if args.stats_json:
        print(json.dumps(stats, indent=2))
    else:
        print(f"\nDone: {stats['docs_indexed']} docs indexed, "
              f"{stats['chunks_added']} chunks added, "
              f"{stats['errors']} errors")

    if stats["errors"] > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
