"""
Embedding interface for the RAG indexer.

Decision (2026-03-28): Support two backends, selectable by env var EMBED_BACKEND:
    - "claude": Use Claude's API (text-embedding via the Anthropic SDK)
    - "local": Use sentence-transformers (all-MiniLM-L6-v2, 384-dim, no API calls)

Claude embeddings are higher quality but cost API credits per batch.
Local embeddings are free but require a sentence-transformers install and GPU/CPU time.

For the first ingest, Claude is fine — batch size is manageable.
If cost becomes an issue, switch EMBED_BACKEND=local.

Requires ANTHROPIC_API_KEY for "claude" backend.
Requires: pip install sentence-transformers torch for "local" backend.
"""

from __future__ import annotations
import os
import time
from typing import Iterator
from .base import Chunk, EmbeddedChunk

EMBED_BACKEND = os.environ.get("EMBED_BACKEND", "claude")
BATCH_SIZE = 20        # chunks per embedding API call
RATE_LIMIT_DELAY = 0.5 # seconds between batches


class Embedder:
    """
    Embeds chunks using the configured backend.

    Usage:
        embedder = Embedder()
        embedded = embedder.embed_batch(chunks)
    """

    def __init__(self, backend: str = EMBED_BACKEND):
        self.backend = backend
        self._model = None

    def embed_batch(self, chunks: list[Chunk]) -> list[EmbeddedChunk]:
        """Embed a list of chunks. Returns EmbeddedChunk list in same order."""
        results = []
        for i in range(0, len(chunks), BATCH_SIZE):
            batch = chunks[i:i + BATCH_SIZE]
            embeddings = self._embed_texts([c.text for c in batch])
            for chunk, embedding in zip(batch, embeddings):
                results.append(EmbeddedChunk(chunk=chunk, embedding=embedding, model=self._model_name()))
            if i + BATCH_SIZE < len(chunks):
                time.sleep(RATE_LIMIT_DELAY)
        return results

    def embed_query(self, text: str) -> list[float]:
        """Embed a single query string for search."""
        return self._embed_texts([text])[0]

    def _embed_texts(self, texts: list[str]) -> list[list[float]]:
        if self.backend == "claude":
            return self._embed_claude(texts)
        elif self.backend == "local":
            return self._embed_local(texts)
        else:
            raise ValueError(f"Unknown EMBED_BACKEND: {self.backend!r}")

    def _model_name(self) -> str:
        if self.backend == "claude":
            return "claude-embedding"
        elif self.backend == "local":
            return "all-MiniLM-L6-v2"
        return "unknown"

    def _embed_claude(self, texts: list[str]) -> list[list[float]]:
        """
        Embed using Anthropic's API.

        Note: As of 2026, Anthropic's embedding endpoint is accessed via
        the standard SDK. Update the model name when new embedding models
        are released.
        """
        try:
            import anthropic
        except ImportError:
            raise RuntimeError("anthropic SDK required: pip install anthropic")

        client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

        # Anthropic embedding endpoint (may change with API updates)
        # Using voyage-3 for high quality embeddings
        response = client.embeddings.create(
            model="voyage-3",
            input=texts,
        )
        return [item.embedding for item in response.data]

    def _embed_local(self, texts: list[str]) -> list[list[float]]:
        """Embed using sentence-transformers (no API calls, no cost)."""
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError:
            raise RuntimeError("sentence-transformers required: pip install sentence-transformers")

        if self._model is None:
            self._model = SentenceTransformer("all-MiniLM-L6-v2")

        embeddings = self._model.encode(texts, convert_to_numpy=True)
        return [e.tolist() for e in embeddings]
