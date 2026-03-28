"""
Document chunking pipeline.

Strategy:
- Text/markdown: paragraph-aware sliding window
- Code: function/class boundaries if detectable, else fixed window
- JSON/YAML: top-level keys as natural boundaries
- Everything else: fixed character window with overlap

Target chunk size: 512 tokens ≈ 2000 characters (rough heuristic).
Overlap: 10% of chunk size to preserve context at boundaries.
"""

from __future__ import annotations
import re
from typing import Iterator
from .base import Document, Chunk


CHUNK_SIZE_CHARS = 2000
OVERLAP_CHARS = 200


def chunk_document(doc: Document) -> list[Chunk]:
    """Split a Document into Chunks. Returns empty list for non-indexable docs."""
    if not doc.is_indexable:
        return []

    content_type = doc.content_type.lower()

    if "markdown" in content_type or doc.source_id.endswith(".md"):
        return list(_chunk_markdown(doc))
    elif "python" in content_type or doc.source_id.endswith(".py"):
        return list(_chunk_code(doc))
    elif "json" in content_type or doc.source_id.endswith(".json"):
        return list(_chunk_json(doc))
    else:
        return list(_chunk_sliding_window(doc))


def _chunk_sliding_window(doc: Document, size: int = CHUNK_SIZE_CHARS, overlap: int = OVERLAP_CHARS) -> Iterator[Chunk]:
    """Generic sliding window chunker. Falls back for unknown content types."""
    text = doc.content
    start = 0
    index = 0

    while start < len(text):
        end = min(start + size, len(text))
        chunk_text = text[start:end].strip()

        if chunk_text:
            yield Chunk(
                document_id=doc.source_id,
                source=doc.source,
                chunk_index=index,
                text=chunk_text,
                char_start=start,
                char_end=end,
                overlap_chars=overlap if start > 0 else 0,
                metadata={"strategy": "sliding_window", **doc.metadata},
            )
            index += 1

        if end >= len(text):
            break
        start = end - overlap


def _chunk_markdown(doc: Document) -> Iterator[Chunk]:
    """
    Split markdown at heading boundaries, then sub-chunk large sections.

    Heading 2 (##) is the primary split point. H1 and H3+ are secondary.
    If a section is still too large after heading splits, fall back to sliding window.
    """
    text = doc.content
    # Split on any heading line
    sections = re.split(r'(?m)^(#{1,3} .+)$', text)

    current_header = ""
    current_text = ""
    index = 0

    def emit(header: str, body: str, idx: int) -> Iterator[Chunk]:
        full = (header + "\n" + body).strip() if header else body.strip()
        if not full:
            return
        # If the section is small enough, yield as one chunk
        if len(full) <= CHUNK_SIZE_CHARS:
            yield Chunk(
                document_id=doc.source_id,
                source=doc.source,
                chunk_index=idx,
                text=full,
                char_start=0,  # approximate; exact position tracking is future work
                char_end=len(full),
                metadata={"strategy": "markdown_section", "header": header, **doc.metadata},
            )
        else:
            # Sub-chunk with sliding window
            sub_doc = Document(
                source_id=doc.source_id,
                source=doc.source,
                content=full,
                content_type=doc.content_type,
                size_bytes=len(full),
                metadata=doc.metadata,
            )
            for chunk in _chunk_sliding_window(sub_doc):
                chunk.chunk_index = idx + chunk.chunk_index
                chunk.metadata["strategy"] = "markdown_subsection"
                chunk.metadata["header"] = header
                yield chunk

    for part in sections:
        if re.match(r'^#{1,3} ', part):
            # Flush previous section
            yield from emit(current_header, current_text, index)
            index += 1
            current_header = part
            current_text = ""
        else:
            current_text += part

    # Flush final section
    yield from emit(current_header, current_text, index)


def _chunk_code(doc: Document) -> Iterator[Chunk]:
    """
    Split Python code at function/class definition boundaries.

    If no definitions found, fall back to sliding window.
    """
    text = doc.content
    # Find top-level def/class boundaries
    boundaries = [0]
    for m in re.finditer(r'(?m)^(def |class )', text):
        if m.start() > 0:
            boundaries.append(m.start())
    boundaries.append(len(text))

    if len(boundaries) <= 2:
        # No structure found; use sliding window
        yield from _chunk_sliding_window(doc)
        return

    index = 0
    for i in range(len(boundaries) - 1):
        section = text[boundaries[i]:boundaries[i+1]].strip()
        if not section:
            continue

        if len(section) <= CHUNK_SIZE_CHARS:
            yield Chunk(
                document_id=doc.source_id,
                source=doc.source,
                chunk_index=index,
                text=section,
                char_start=boundaries[i],
                char_end=boundaries[i+1],
                metadata={"strategy": "code_boundary", **doc.metadata},
            )
            index += 1
        else:
            sub_doc = Document(
                source_id=doc.source_id,
                source=doc.source,
                content=section,
                content_type=doc.content_type,
                size_bytes=len(section),
                metadata=doc.metadata,
            )
            for chunk in _chunk_sliding_window(sub_doc):
                chunk.chunk_index = index + chunk.chunk_index
                chunk.metadata["strategy"] = "code_subsection"
                yield chunk


def _chunk_json(doc: Document) -> Iterator[Chunk]:
    """
    For JSON, try to split at top-level keys. If the whole thing fits, yield as one chunk.
    This is intentionally simple — structured data benefits from key-level granularity.
    """
    text = doc.content

    if len(text) <= CHUNK_SIZE_CHARS:
        yield Chunk(
            document_id=doc.source_id,
            source=doc.source,
            chunk_index=0,
            text=text.strip(),
            char_start=0,
            char_end=len(text),
            metadata={"strategy": "json_whole", **doc.metadata},
        )
        return

    # Fall back to sliding window for large JSON
    yield from _chunk_sliding_window(doc)
