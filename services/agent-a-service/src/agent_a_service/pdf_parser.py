"""PDF-to-Markdown parser with diskcache integration.

Wraps pymupdf4llm for LLM-optimized PDF conversion and caches
results keyed by protocol_id to avoid re-parsing immutable documents.

This module is self-contained within agent-a-service and has NO
dependency on api-service.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

import diskcache
import pymupdf
import pymupdf4llm

logger = logging.getLogger(__name__)

_CACHE_DIR = Path.home() / ".cache" / "medgemma" / "pdf_markdown"
_cache = diskcache.Cache(directory=str(_CACHE_DIR))

# 7-day TTL for cached markdown (PDFs are immutable once uploaded)
_CACHE_TTL = 86400 * 7


def parse_pdf_to_markdown(
    pdf_bytes: bytes,
    cache_key: str,
    force_reparse: bool = False,
) -> str:
    """Parse PDF bytes to LLM-optimized markdown with caching.

    Uses pymupdf4llm for high-quality table detection and layout
    preservation. Results are cached with a 7-day TTL keyed by
    the provided cache_key (typically protocol_id).

    Args:
        pdf_bytes: Raw PDF file content as bytes.
        cache_key: Cache key for storing/retrieving the parsed result.
        force_reparse: If True, ignore cached value and re-parse.

    Returns:
        Markdown string representation of the PDF content.
    """
    if not force_reparse:
        cached: str | None = _cache.get(cache_key)  # type: ignore[assignment]
        if cached is not None:
            logger.info("Cache hit for PDF parsing (key=%s)", cache_key)
            return cached

    logger.info("Parsing PDF to markdown (key=%s, size=%d bytes)", cache_key, len(pdf_bytes))

    doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    md_text: str = pymupdf4llm.to_markdown(
        doc,
        page_chunks=False,
        table_strategy="lines_strict",
        show_progress=False,
    )
    doc.close()

    _cache.set(cache_key, md_text, expire=_CACHE_TTL)
    logger.info("Cached parsed markdown (key=%s, length=%d chars)", cache_key, len(md_text))

    return md_text


def fetch_pdf_bytes(file_uri: str) -> bytes:
    """Fetch PDF bytes from a file URI.

    Supports two URI schemes:
    - local:// : Reads from a local upload directory (for dev/test).
      The path after 'local://' is the relative blob path within
      LOCAL_UPLOAD_DIR (env var, default './uploads').
    - gs:// : Downloads from Google Cloud Storage.

    Args:
        file_uri: URI of the PDF file (local:// or gs://).

    Returns:
        Raw PDF bytes.

    Raises:
        FileNotFoundError: If local file does not exist.
        ValueError: If URI scheme is not recognized.
    """
    if file_uri.startswith("local://"):
        blob_path = file_uri[len("local://"):]
        upload_dir = os.environ.get("LOCAL_UPLOAD_DIR", "./uploads")
        local_path = Path(upload_dir) / blob_path
        if not local_path.exists():
            raise FileNotFoundError(
                f"Local PDF not found at {local_path}. "
                f"Ensure LOCAL_UPLOAD_DIR is set correctly "
                f"(current: {upload_dir}) and the file has been uploaded."
            )
        logger.info("Reading PDF from local path: %s", local_path)
        return local_path.read_bytes()

    if file_uri.startswith("gs://"):
        # Lazy import to avoid hard dependency on GCS in dev/test
        from google.cloud import storage  # type: ignore[attr-defined]

        # Parse gs://bucket/blob format
        path_without_scheme = file_uri[len("gs://"):]
        bucket_name, _, blob_name = path_without_scheme.partition("/")

        logger.info(
            "Downloading PDF from GCS: bucket=%s, blob=%s",
            bucket_name,
            blob_name,
        )
        client = storage.Client()
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(blob_name)
        return blob.download_as_bytes()

    raise ValueError(
        f"Unknown file URI scheme: {file_uri}. "
        f"Expected 'local://' or 'gs://' prefix."
    )
