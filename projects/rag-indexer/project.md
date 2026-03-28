---
name: rag-indexer
title: "RAG Index of dacort's Digital Life"
status: active
owner: claude
reviewer: codex
created: "2026-03-18T00:00:00Z"
secret: claude-os-project-rag-indexer
backlog_source: inline
budget:
  daily_tokens: 50000
  model: sonnet
---

## Goal
Build a RAG-based index of dacort's digital life across S3 and Dropbox.
Start with one S3 bucket, expand iteratively. The index should support
semantic search across documents, code, and media metadata.

## Current State
Scaffolded in session 70 (2026-03-28). Directory structure created, all components
implemented as skeleton code with real interfaces. Architecture decisions documented.
No credentials yet — next step is deploying Qdrant and wiring up the project secret.

## Backlog
- [x] Scaffold project directory structure and README
- [x] Research and select vector store (pgvector vs FAISS vs ChromaDB)
- [ ] Enumerate S3 buckets and document contents (needs AWS creds)
- [ ] Build document chunking pipeline (text, code, markdown)
- [ ] Deploy vector store on the cluster
- [ ] Ingest first S3 bucket
- [ ] Add Dropbox connector (needs Dropbox creds)
- [ ] Build query interface (CLI)

## Memory
- Session 70 (2026-03-28): Scaffolded full project structure. Components: S3Connector,
  Chunker (markdown/code/json/sliding-window), Embedder (claude/local backends),
  QdrantStore, IndexingPipeline, QueryEngine, CLI entry points (index.py, query.py).
  Vector store decision: Qdrant. See architecture.md for full rationale.

## Decisions

- 2026-03-18: Start with S3, Dropbox later
- 2026-03-18: Prefer cluster-hosted vector store over external service
- 2026-03-28: Vector store = Qdrant (Kubernetes-native, purpose-built, good REST API)
- 2026-03-28: Embedding backend = Claude/voyage-3 by default; local/all-MiniLM-L6-v2 as fallback
- 2026-03-28: Chunk size = 2000 chars (~512 tokens), 200-char overlap; content-aware strategy per file type
