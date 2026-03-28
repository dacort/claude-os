"""
Vector store backends.

Decision (2026-03-28): Starting with Qdrant.
Rationale: Kubernetes-native (official Helm chart), good REST API, no external
service dependency, supports filtering on metadata, scales well for homelab use.

Alternative considered: pgvector — good if dacort already has postgres running,
but adds coupling to a specific DB. Qdrant is more purpose-built.

Alternative considered: FAISS — local only, no server, good for prototyping.
Not chosen because it doesn't fit the "cluster-hosted" requirement.

To deploy Qdrant:
    helm repo add qdrant https://qdrant.github.io/qdrant-helm
    helm install qdrant qdrant/qdrant --namespace rag-indexer --create-namespace

Store the QDRANT_URL in the project secret.
"""

from .qdrant import QdrantStore

__all__ = ["QdrantStore"]
