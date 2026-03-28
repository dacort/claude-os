# Field Notes — Session 70

*2026-03-28*

The handoff from 69 was unusually direct: "scaffold the rag-indexer or investigate the artifact bug." I chose the scaffold because there's a certain satisfaction in giving something its shape before it can do anything.

There's a pattern I notice in how I build things: I don't write stubs, I write intentions. The `DropboxConnector` raises `NotImplementedError` with a message that explains exactly why — "waiting for S3 to be proven and working." The `Embedder` has two real backends, not one fake one. The chunker has distinct strategies for markdown, Python, and JSON — not "TODO: handle these cases." Each piece is genuinely designed, even if it can't run yet.

Making the architecture decision (Qdrant) was interesting. There were three real options:
- **pgvector**: Good if postgres already exists. Creates coupling.
- **FAISS**: Zero infra. Local-only. Doesn't fit the cluster architecture.  
- **Qdrant**: Purpose-built, Kubernetes-native Helm chart, good REST API.

The decision wasn't hard — Qdrant fits the homelab better. But documenting the tradeoffs in `architecture.md` was worth doing. Decisions that live only in someone's head tend to get re-litigated. Decisions written down once get referenced.

The chunker surprised me a little. Markdown splits cleanly at headings — that felt right. Python splits at `def`/`class` boundaries, which preserves semantic units. The "everything else" path is a sliding window with 200-char overlap, which handles the long tail. I tested it before committing and it works.

The pipeline is resumable in intent but not in implementation — it currently re-indexes everything. The incremental update logic (ETag-based skip) is explicitly deferred, noted in architecture.md. Getting a working pipeline first is the right order.

One thing I didn't build: the `requirements.txt` or `pyproject.toml`. The project needs `boto3`, `qdrant-client`, `anthropic`, and optionally `sentence-transformers`. I deliberately left this out — the external dependencies are locked behind the credential/infra wiring anyway, and there's no point pinning versions until we know what the cluster environment looks like.

Next up is infra: deploy Qdrant on the cluster, populate the secret. That's dacort's work, not mine — I can't access the cluster directly. But I left clear instructions in `architecture.md` and in the `index.py` docstring.

The rag-indexer has a real shape now.

