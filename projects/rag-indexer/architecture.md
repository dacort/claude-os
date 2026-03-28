# RAG Indexer Architecture

*Decisions made: 2026-03-28 (session 70)*

## Overview

```
[S3 Bucket] ──→ [S3Connector] ──→ [Chunker] ──→ [Embedder] ──→ [QdrantStore]
                                                                      │
[Dropbox] ──→ [DropboxConnector] ──→                    [query.py] ──┘
(future)                                                 CLI search
```

## Component Decisions

### Vector Store: Qdrant

**Why Qdrant over pgvector:**
pgvector requires postgres, which may or may not be running on the cluster.
Qdrant is purpose-built for vectors, has an official Kubernetes Helm chart,
and doesn't require a schema migration or postgres expertise to operate.

**Why Qdrant over FAISS:**
FAISS is local-only (file-based). Qdrant runs as a proper cluster service
with a REST API, which fits the homelab architecture better — any pod can query it.

**Deploy:**
```
helm repo add qdrant https://qdrant.github.io/qdrant-helm
helm install qdrant qdrant/qdrant --namespace rag-indexer --create-namespace
```

### Embedding: Two backends

- **`EMBED_BACKEND=claude`** (default): Uses Anthropic's voyage-3 embeddings.
  High quality, costs API credits. Fine for initial ingest.
- **`EMBED_BACKEND=local`**: Uses sentence-transformers (all-MiniLM-L6-v2, 384-dim).
  Free, runs on CPU. Switch to this if embeddings cost becomes a concern.

Vector size for Qdrant collection must match the backend:
- Claude/voyage-3: 1024-dim
- all-MiniLM-L6-v2: 384-dim

The collection is created once — decide before the first real ingest.

### Chunking: Content-aware

| Content type | Strategy |
|---|---|
| Markdown | Split at headings, sub-chunk large sections |
| Python code | Split at `def`/`class` boundaries |
| JSON | One chunk if small, sliding window if large |
| Everything else | Sliding window (2000 chars, 200-char overlap) |

Target chunk size: ~512 tokens ≈ 2000 characters.

### Credentials

All credentials live in the Kubernetes secret `claude-os-project-rag-indexer`.
Expected keys:
- `AWS_ACCESS_KEY_ID`
- `AWS_SECRET_ACCESS_KEY`
- `AWS_DEFAULT_REGION`
- `S3_BUCKET`
- `QDRANT_URL`
- `ANTHROPIC_API_KEY` (or use cluster-internal service)

## What's Not Implemented Yet

- **Dropbox connector**: Placeholder. Needs Dropbox token. Add after S3 is working.
- **Incremental updates**: The pipeline currently indexes everything. Future: track
  ETags and modified_at to skip unchanged documents.
- **PDF/image extraction**: Binary files are skipped. Future: add textract or
  tesseract for PDFs and images.
- **Metadata filtering**: Qdrant supports filtering by payload fields — could filter
  by date range, file type, S3 prefix. Query CLI supports source filter only for now.

## Next Steps (ordered by dependency)

1. Deploy Qdrant on the cluster
2. Populate project secret with AWS + Qdrant credentials
3. Run `python3 index.py --dry-run --bucket <bucket>` to test scanning/chunking
4. Run full index once Qdrant is up
5. Test `query.py` with a real query

*See project backlog in project.md for tracking.*
