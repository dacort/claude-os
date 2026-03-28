"""
Dropbox connector for the RAG indexer.

Placeholder — to be implemented after S3 is working.

Requires DROPBOX_ACCESS_TOKEN environment variable.
Requires: pip install dropbox

The Dropbox connector will follow the same interface as S3Connector:
    connector.list() → list of file paths
    connector.fetch(path) → Document
    connector.scan() → Iterator[Document]
"""

from __future__ import annotations
from typing import Iterator
from ..base import Document


class DropboxConnector:
    """
    Scans a Dropbox folder, yields Documents.

    Not yet implemented — waiting for S3 to be proven and working.
    Will be built in a future session when Dropbox credentials are available.
    """

    def __init__(self, root_path: str = ""):
        self.root_path = root_path
        raise NotImplementedError(
            "DropboxConnector is not yet implemented. "
            "See backlog item: 'Add Dropbox connector (needs Dropbox creds)'"
        )

    def list(self) -> list[str]:
        raise NotImplementedError

    def fetch(self, path: str) -> Document:
        raise NotImplementedError

    def scan(self) -> Iterator[Document]:
        raise NotImplementedError
