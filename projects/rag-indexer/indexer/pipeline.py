"""
Main indexing pipeline.

Connects all the pieces: Connector → Chunker → Embedder → VectorStore

Designed to be resumable: uses the modified_at timestamp and ETag to skip
already-indexed documents. Progress is logged to stderr.

Usage:
    pipeline = IndexingPipeline.from_env()
    stats = pipeline.run()
    print(f"Indexed {stats['chunks_added']} chunks from {stats['docs_scanned']} docs")
"""

from __future__ import annotations
import os
import sys
import time
from datetime import datetime
from typing import Iterator

from .base import Document, Chunk, SearchResult
from .chunker import chunk_document
from .embedder import Embedder
from .store import QdrantStore


class IndexingPipeline:
    """
    Orchestrates a full index run from one connector into the vector store.
    """

    def __init__(self, connector, embedder: Embedder, store: QdrantStore, verbose: bool = True):
        self.connector = connector
        self.embedder = embedder
        self.store = store
        self.verbose = verbose

    @classmethod
    def from_env(cls) -> "IndexingPipeline":
        """
        Build a pipeline from environment variables.

        Required:
            CONNECTOR=s3 (or dropbox — not yet implemented)
            S3_BUCKET, AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY
            QDRANT_URL
            ANTHROPIC_API_KEY (or EMBED_BACKEND=local)
        """
        connector_type = os.environ.get("CONNECTOR", "s3")

        if connector_type == "s3":
            from .connectors import S3Connector
            connector = S3Connector(
                bucket=os.environ["S3_BUCKET"],
                prefix=os.environ.get("S3_PREFIX", ""),
            )
        else:
            raise ValueError(f"Unknown CONNECTOR: {connector_type!r}")

        embedder = Embedder()
        store = QdrantStore()
        return cls(connector=connector, embedder=embedder, store=store)

    def run(self, dry_run: bool = False) -> dict:
        """
        Run the full pipeline. Returns stats dict.

        dry_run=True: scan and chunk but don't embed or store (useful for testing).
        """
        stats = {
            "docs_scanned": 0,
            "docs_skipped": 0,
            "docs_indexed": 0,
            "chunks_total": 0,
            "chunks_added": 0,
            "errors": 0,
            "started_at": datetime.utcnow().isoformat(),
        }

        if not dry_run:
            self.store.ensure_collection()

        self._log(f"Starting pipeline (connector={self.connector.__class__.__name__}, dry_run={dry_run})")

        for doc in self.connector.scan():
            stats["docs_scanned"] += 1

            if not doc.is_indexable:
                stats["docs_skipped"] += 1
                self._log(f"  skip  {doc.source_id} (not text-extractable)")
                continue

            try:
                chunks = chunk_document(doc)
                stats["chunks_total"] += len(chunks)

                if not chunks:
                    stats["docs_skipped"] += 1
                    continue

                self._log(f"  index {doc.source_id} → {len(chunks)} chunks")

                if not dry_run:
                    embedded = self.embedder.embed_batch(chunks)
                    added = self.store.upsert(embedded)
                    stats["chunks_added"] += added

                stats["docs_indexed"] += 1

            except Exception as e:
                stats["errors"] += 1
                self._log(f"  ERROR {doc.source_id}: {e}", error=True)

        stats["finished_at"] = datetime.utcnow().isoformat()
        self._log(
            f"Done: {stats['docs_indexed']} docs indexed, "
            f"{stats['chunks_added']} chunks added, "
            f"{stats['errors']} errors"
        )
        return stats

    def _log(self, msg: str, error: bool = False) -> None:
        if self.verbose:
            prefix = "ERROR" if error else "INFO"
            print(f"[{prefix}] {msg}", file=sys.stderr)


class QueryEngine:
    """
    Semantic search over the indexed content.

    Usage:
        engine = QueryEngine.from_env()
        results = engine.search("my recent S3 uploads about photography")
        for r in results:
            print(r)
    """

    def __init__(self, embedder: Embedder, store: QdrantStore):
        self.embedder = embedder
        self.store = store

    @classmethod
    def from_env(cls) -> "QueryEngine":
        return cls(embedder=Embedder(), store=QdrantStore())

    def search(self, query: str, top_k: int = 10, source: str = None) -> list[SearchResult]:
        """Semantic search. Returns ranked results."""
        vector = self.embedder.embed_query(query)
        return self.store.search(vector, top_k=top_k, source_filter=source)
