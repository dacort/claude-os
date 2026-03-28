"""
Core data types for the RAG indexer.

These are plain dataclasses — no external deps. Every component speaks this language.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class Document:
    """
    A raw document from a connector (S3 object, Dropbox file, etc.).

    source_id is the connector-specific identifier (S3 key, Dropbox path).
    content is the raw text (or None for binary files we can't extract text from).
    metadata is anything the connector knows: size, modified_at, content_type, etc.
    """
    source_id: str
    source: str           # "s3", "dropbox", etc.
    content: Optional[str]
    content_type: str
    size_bytes: int
    modified_at: Optional[datetime] = None
    metadata: dict = field(default_factory=dict)

    @property
    def is_indexable(self) -> bool:
        """True if we have text content to index."""
        return self.content is not None and len(self.content.strip()) > 0


@dataclass
class Chunk:
    """
    A chunk of a Document, ready for embedding.

    chunk_index is position within the document (0-based).
    overlap_chars tracks how much this chunk overlaps with adjacent chunks.
    """
    document_id: str      # matches Document.source_id
    source: str
    chunk_index: int
    text: str
    char_start: int
    char_end: int
    overlap_chars: int = 0
    metadata: dict = field(default_factory=dict)

    @property
    def word_count(self) -> int:
        return len(self.text.split())


@dataclass
class EmbeddedChunk:
    """A Chunk with its embedding vector attached."""
    chunk: Chunk
    embedding: list[float]
    model: str            # which embedding model was used


@dataclass
class SearchResult:
    """
    One result from a semantic search query.

    score is cosine similarity (0.0–1.0, higher = more similar).
    """
    chunk: Chunk
    score: float
    rank: int

    def __str__(self) -> str:
        return f"[{self.score:.3f}] {self.chunk.source_id}:{self.chunk.chunk_index} — {self.chunk.text[:100]}..."
