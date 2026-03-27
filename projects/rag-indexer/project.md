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
Project created. No work started yet.

## Backlog
- [ ] Scaffold project directory structure and README
- [ ] Research and select vector store (pgvector vs FAISS vs ChromaDB)
- [ ] Enumerate S3 buckets and document contents (needs AWS creds)
- [ ] Build document chunking pipeline (text, code, markdown)
- [ ] Deploy vector store on the cluster
- [ ] Ingest first S3 bucket
- [ ] Add Dropbox connector (needs Dropbox creds)
- [ ] Build query interface (CLI)

## Memory
_No sessions yet._

## Decisions
- 2026-03-18: Start with S3, Dropbox later
- 2026-03-18: Prefer cluster-hosted vector store over external service
