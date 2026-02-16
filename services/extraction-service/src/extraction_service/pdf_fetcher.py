"""PDF fetcher: download PDF bytes from GCS or local storage.

Separated from pdf_parser.py to avoid importing pymupdf/pymupdf4llm
when only the fetch functionality is needed (multimodal extraction
sends raw PDF bytes directly to Gemini).
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from shared.resilience import gcs_breaker
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_random_exponential,
)

logger = logging.getLogger(__name__)


@gcs_breaker
@retry(
    retry=retry_if_exception_type(Exception),
    stop=stop_after_attempt(3),
    wait=wait_random_exponential(multiplier=1, min=2, max=10),
    before_sleep=before_sleep_log(logger, logging.WARNING),
    reraise=True,
)
def _download_from_gcs(bucket_name: str, blob_name: str) -> bytes:
    """Download PDF bytes from GCS with retry and circuit breaker."""
    from google.cloud import storage  # type: ignore[attr-defined]

    client = storage.Client()
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(blob_name)
    return blob.download_as_bytes()


def fetch_pdf_bytes(file_uri: str) -> bytes:
    """Fetch PDF bytes from a file URI.

    Supports two URI schemes:
    - local:// : Reads from a local upload directory (for dev/test).
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
        path_without_scheme = file_uri[len("gs://"):]
        bucket_name, _, blob_name = path_without_scheme.partition("/")
        logger.info(
            "Downloading PDF from GCS: bucket=%s, blob=%s",
            bucket_name,
            blob_name,
        )
        return _download_from_gcs(bucket_name, blob_name)

    raise ValueError(
        f"Unknown file URI scheme: {file_uri}. Expected 'local://' or 'gs://' prefix."
    )
