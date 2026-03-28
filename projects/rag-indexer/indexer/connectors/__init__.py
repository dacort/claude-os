"""
Source connectors. Each connector yields Documents from one data source.

All connectors implement the same interface:
    connector.list() → list of source IDs available
    connector.fetch(source_id) → Document (with content if text-extractable)
    connector.scan() → Iterator[Document] — list + fetch combined

The connectors require credentials. They're designed to be wired up via
the project secret (claude-os-project-rag-indexer) which will contain
AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, DROPBOX_TOKEN, etc.
"""

from .s3 import S3Connector

__all__ = ["S3Connector"]
