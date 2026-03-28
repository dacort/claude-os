"""
Qdrant vector store backend.

Requires: pip install qdrant-client
Requires environment variable: QDRANT_URL (e.g. http://qdrant.rag-indexer.svc:6333)

Collection schema:
    - Each chunk is one point
    - Vector: 1536-dim (Claude embedding) or 384-dim (sentence-transformers)
    - Payload: source_id, source, chunk_index, text, char_start, char_end, metadata
"""

from __future__ import annotations
import os
from typing import Optional
from ..base import EmbeddedChunk, Chunk, SearchResult

COLLECTION_NAME = "dacort_life"
VECTOR_SIZE = 1536  # Claude text-embedding-3-small compatible


class QdrantStore:
    """
    Wraps the Qdrant client for upsert and search operations.

    Usage:
        store = QdrantStore()
        store.ensure_collection()
        store.upsert(embedded_chunks)
        results = store.search(query_vector, top_k=5)
    """

    def __init__(
        self,
        url: str = None,
        collection: str = COLLECTION_NAME,
        vector_size: int = VECTOR_SIZE,
    ):
        self.url = url or os.environ.get("QDRANT_URL", "http://localhost:6333")
        self.collection = collection
        self.vector_size = vector_size
        self._client = None

    def _get_client(self):
        if self._client is None:
            try:
                from qdrant_client import QdrantClient
            except ImportError:
                raise RuntimeError("qdrant-client is required: pip install qdrant-client")
            self._client = QdrantClient(url=self.url)
        return self._client

    def ensure_collection(self, recreate: bool = False) -> None:
        """Create the collection if it doesn't exist. Set recreate=True to wipe and rebuild."""
        from qdrant_client.models import Distance, VectorParams
        client = self._get_client()

        collections = [c.name for c in client.get_collections().collections]
        if self.collection in collections:
            if recreate:
                client.delete_collection(self.collection)
            else:
                return  # Already exists

        client.create_collection(
            collection_name=self.collection,
            vectors_config=VectorParams(size=self.vector_size, distance=Distance.COSINE),
        )

    def upsert(self, chunks: list[EmbeddedChunk]) -> int:
        """
        Insert or update embedded chunks in the store.
        Returns number of points upserted.
        """
        from qdrant_client.models import PointStruct
        client = self._get_client()

        points = []
        for i, ec in enumerate(chunks):
            # Use a deterministic ID from source_id + chunk_index
            point_id = _stable_id(ec.chunk.document_id, ec.chunk.chunk_index)
            payload = {
                "source_id": ec.chunk.document_id,
                "source": ec.chunk.source,
                "chunk_index": ec.chunk.chunk_index,
                "text": ec.chunk.text,
                "char_start": ec.chunk.char_start,
                "char_end": ec.chunk.char_end,
                "model": ec.model,
                **ec.chunk.metadata,
            }
            points.append(PointStruct(id=point_id, vector=ec.embedding, payload=payload))

        if points:
            client.upsert(collection_name=self.collection, points=points)

        return len(points)

    def search(
        self,
        query_vector: list[float],
        top_k: int = 10,
        source_filter: Optional[str] = None,
    ) -> list[SearchResult]:
        """
        Semantic search. Returns top_k results sorted by cosine similarity.

        source_filter: if set, restrict to one source ("s3", "dropbox", etc.)
        """
        from qdrant_client.models import Filter, FieldCondition, MatchValue
        client = self._get_client()

        query_filter = None
        if source_filter:
            query_filter = Filter(
                must=[FieldCondition(key="source", match=MatchValue(value=source_filter))]
            )

        hits = client.search(
            collection_name=self.collection,
            query_vector=query_vector,
            limit=top_k,
            query_filter=query_filter,
        )

        results = []
        for rank, hit in enumerate(hits):
            p = hit.payload
            chunk = Chunk(
                document_id=p["source_id"],
                source=p["source"],
                chunk_index=p["chunk_index"],
                text=p["text"],
                char_start=p.get("char_start", 0),
                char_end=p.get("char_end", 0),
            )
            results.append(SearchResult(chunk=chunk, score=hit.score, rank=rank))

        return results

    def count(self) -> int:
        """Total number of indexed chunks."""
        client = self._get_client()
        return client.count(collection_name=self.collection).count


def _stable_id(source_id: str, chunk_index: int) -> int:
    """
    Generate a stable integer ID from source_id + chunk_index.
    Qdrant requires integer or UUID IDs for points.
    """
    import hashlib
    key = f"{source_id}:{chunk_index}"
    digest = hashlib.sha256(key.encode()).hexdigest()
    # Take first 15 hex chars (60 bits) to stay safely within int64
    return int(digest[:15], 16)
