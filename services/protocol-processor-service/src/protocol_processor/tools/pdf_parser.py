"""PDF fetcher tool: download PDF bytes from GCS or local storage.

Pure function — no state dependency. Sends raw PDF bytes to Gemini
via the File API (multimodal approach, no markdown conversion needed).

Architecture note: This module is self-contained within protocol-processor-service
and has NO dependency on api-service. Cross-service imports are reserved for
workflow nodes that are integration glue.
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
    """Download PDF bytes from GCS with retry and circuit breaker.

    Args:
        bucket_name: GCS bucket name.
        blob_name: Blob path within the bucket.

    Returns:
        Raw PDF bytes.
    """
    from google.cloud import storage  # type: ignore[attr-defined]

    client = storage.Client()
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(blob_name)
    return blob.download_as_bytes()


async def fetch_pdf_bytes(file_uri: str) -> bytes:
    """Fetch PDF bytes from a file URI.

    Supports two URI schemes:
    - local:// : Reads from a local upload directory (for dev/test).
      The path after 'local://' is the relative blob path within
      LOCAL_UPLOAD_DIR (env var, default 'uploads/protocols' to match api-service).
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
        blob_path = file_uri[len("local://") :]
        # Must match api_service.gcs default so both services resolve the same path
        upload_dir = os.environ.get("LOCAL_UPLOAD_DIR", "uploads/protocols")
        base = Path(upload_dir)
        if not base.is_absolute():
            base = base.resolve()
        local_path = base / blob_path
        if not local_path.exists():
            raise FileNotFoundError(
                f"Local PDF not found at {local_path}. "
                f"Ensure LOCAL_UPLOAD_DIR is set correctly (current: {upload_dir}) "
                f"and the file has been uploaded. If the API runs in Docker with a "
                f"volume mount, set LOCAL_UPLOAD_DIR to the mounted host path."
            )
        logger.info("Reading PDF from local path: %s", local_path)
        return local_path.read_bytes()

    if file_uri.startswith("gs://"):
        path_without_scheme = file_uri[len("gs://") :]
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
