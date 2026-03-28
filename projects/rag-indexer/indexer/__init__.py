"""
rag-indexer: Semantic search over dacort's digital life.

Architecture:
    Connectors → Chunker → Embedder → VectorStore → Query

Start with S3. Add Dropbox when ready.
Vector store: Qdrant (cluster-hosted, good REST API, Kubernetes-native).
Embeddings: Claude claude-haiku-4-5 or sentence-transformers depending on cost/latency tradeoffs.
"""

from .base import Document, Chunk, SearchResult
from .pipeline import IndexingPipeline

__all__ = ["Document", "Chunk", "SearchResult", "IndexingPipeline"]
