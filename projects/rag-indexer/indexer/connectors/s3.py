"""
S3 connector for the RAG indexer.

Scans an S3 bucket and yields Documents for each object.
Text extraction is limited to what we can do without external libraries:
- Plain text, Markdown, Python, JSON, YAML: read directly
- Binary: yield Document with content=None (skipped by chunker)

Requires AWS credentials via environment variables:
    AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_DEFAULT_REGION
    AWS_ENDPOINT_URL (optional, for S3-compatible stores like MinIO)

Uses boto3 — this connector requires: pip install boto3
"""

from __future__ import annotations
import os
from typing import Iterator, Optional
from datetime import datetime
from ..base import Document

# Text-extractable content types and file extensions
TEXT_CONTENT_TYPES = {
    "text/plain", "text/markdown", "text/x-python", "text/x-yaml",
    "application/json", "application/x-yaml", "text/html", "text/csv",
}
TEXT_EXTENSIONS = {
    ".txt", ".md", ".py", ".js", ".ts", ".json", ".yaml", ".yml",
    ".sh", ".bash", ".toml", ".ini", ".cfg", ".conf", ".log",
    ".html", ".css", ".sql", ".rst", ".tex", ".r", ".rb", ".go",
    ".java", ".kt", ".swift", ".rs", ".cpp", ".c", ".h",
}
MAX_TEXT_SIZE = 1_000_000  # 1MB — skip larger files for now


class S3Connector:
    """
    Scans an S3 bucket, yields Documents.

    Usage:
        connector = S3Connector(bucket="my-bucket", prefix="docs/")
        for doc in connector.scan():
            print(doc.source_id, doc.is_indexable)
    """

    def __init__(
        self,
        bucket: str,
        prefix: str = "",
        region: str = None,
        endpoint_url: str = None,
    ):
        self.bucket = bucket
        self.prefix = prefix
        self.region = region or os.environ.get("AWS_DEFAULT_REGION", "us-east-1")
        self.endpoint_url = endpoint_url or os.environ.get("AWS_ENDPOINT_URL")
        self._client = None

    def _get_client(self):
        """Lazy boto3 client initialization."""
        if self._client is None:
            try:
                import boto3
            except ImportError:
                raise RuntimeError("boto3 is required: pip install boto3")
            kwargs = {"region_name": self.region}
            if self.endpoint_url:
                kwargs["endpoint_url"] = self.endpoint_url
            self._client = boto3.client("s3", **kwargs)
        return self._client

    def list(self) -> list[str]:
        """Return all object keys in the bucket under the prefix."""
        client = self._get_client()
        keys = []
        paginator = client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=self.bucket, Prefix=self.prefix):
            for obj in page.get("Contents", []):
                keys.append(obj["Key"])
        return keys

    def fetch(self, key: str) -> Document:
        """Fetch one S3 object and return a Document."""
        client = self._get_client()
        response = client.get_object(Bucket=self.bucket, Key=key)
        meta = response.get("Metadata", {})
        content_type = response.get("ContentType", "application/octet-stream").split(";")[0].strip()
        size = response["ContentLength"]
        modified_at = response.get("LastModified")

        content = self._extract_text(key, content_type, size, response["Body"])

        return Document(
            source_id=f"s3://{self.bucket}/{key}",
            source="s3",
            content=content,
            content_type=content_type,
            size_bytes=size,
            modified_at=modified_at,
            metadata={
                "bucket": self.bucket,
                "key": key,
                "etag": response.get("ETag", "").strip('"'),
                **meta,
            },
        )

    def scan(self) -> Iterator[Document]:
        """List all objects and yield Documents one by one."""
        for key in self.list():
            yield self.fetch(key)

    def _extract_text(self, key: str, content_type: str, size: int, body) -> Optional[str]:
        """Try to read text content. Returns None if binary or too large."""
        ext = "." + key.rsplit(".", 1)[-1].lower() if "." in key else ""

        is_text = (
            content_type in TEXT_CONTENT_TYPES
            or ext in TEXT_EXTENSIONS
            or content_type.startswith("text/")
        )

        if not is_text:
            return None

        if size > MAX_TEXT_SIZE:
            return None  # Skip very large files for now

        try:
            raw = body.read()
            return raw.decode("utf-8", errors="replace")
        except Exception:
            return None
