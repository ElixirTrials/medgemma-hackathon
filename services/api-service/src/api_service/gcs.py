"""Storage client for protocol PDF files.

Supports two backends:
- GCS (production): Signed URLs for direct browser-to-GCS uploads
- Local (development): Files stored in uploads/ directory, served by the API

Set USE_LOCAL_STORAGE=1 for local development without GCP service account keys.
Otherwise requires GCS_BUCKET_NAME and valid GCP credentials.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from datetime import timedelta
from pathlib import Path
from uuid import uuid4

from shared.resilience import gcs_breaker
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception_type,
    retry_if_not_exception_type,
    stop_after_attempt,
    wait_random_exponential,
)

logger = logging.getLogger(__name__)

# Local storage directory (relative to repo root)
_LOCAL_UPLOAD_DIR = Path(os.getenv("LOCAL_UPLOAD_DIR", "uploads/protocols"))

# Shared retry decorator for GCS operations
# Retry on any Exception EXCEPT ValueError (config errors)
_gcs_retry = retry(
    retry=(
        retry_if_exception_type(Exception) & retry_if_not_exception_type(ValueError)
    ),
    stop=stop_after_attempt(3),
    wait=wait_random_exponential(multiplier=1, min=2, max=10),
    before_sleep=before_sleep_log(logger, logging.WARNING),
    reraise=True,
)

# Module-level singleton for GCS client
_gcs_client = None


def _use_local_storage() -> bool:
    """Check if local file storage is enabled."""
    return os.getenv("USE_LOCAL_STORAGE", "").strip() in ("1", "true", "yes")


def get_gcs_client():
    """Return a cached GCS storage client (singleton).

    Returns:
        google.cloud.storage.Client or None if unavailable.
    """
    global _gcs_client  # noqa: PLW0603
    if _gcs_client is None:
        try:
            from google.cloud import storage  # type: ignore[import-untyped]

            _gcs_client = storage.Client()
            logger.info("GCS client initialized successfully")
        except Exception:
            logger.warning(
                "Could not initialize GCS client. "
                "GCS operations will fail until GCP credentials are configured."
            )
            _gcs_client = None
    return _gcs_client


def get_bucket_name() -> str:
    """Read GCS_BUCKET_NAME from environment.

    Returns:
        The bucket name string.

    Raises:
        ValueError: If GCS_BUCKET_NAME is not set.
    """
    bucket_name = os.getenv("GCS_BUCKET_NAME")
    if not bucket_name:
        raise ValueError(
            "GCS_BUCKET_NAME environment variable is not set. "
            "Set it to your GCS bucket name for protocol storage."
        )
    return bucket_name


def _parse_gcs_uri(gcs_path: str) -> tuple[str, str]:
    """Parse a gs:// URI into (bucket_name, blob_path).

    Args:
        gcs_path: GCS URI in the form gs://bucket/path/to/blob.

    Returns:
        Tuple of (bucket_name, blob_path).

    Raises:
        ValueError: If the URI format is invalid.
    """
    if not gcs_path.startswith("gs://"):
        raise ValueError(f"Invalid GCS URI: {gcs_path}. Must start with gs://")
    path = gcs_path[5:]  # Remove "gs://"
    parts = path.split("/", 1)
    if len(parts) < 2 or not parts[1]:
        raise ValueError(
            f"Invalid GCS URI: {gcs_path}. Must be gs://bucket/path/to/blob"
        )
    return parts[0], parts[1]


def generate_upload_url(
    filename: str,
    content_type: str = "application/pdf",
    expiration_minutes: int = 15,
) -> tuple[str, str]:
    """Generate a URL for uploading a file.

    In local mode: returns a local API endpoint URL.
    In GCS mode: returns a signed GCS PUT URL.
    """
    if _use_local_storage():
        return _local_generate_upload_url(filename)
    return _gcs_generate_upload_url(filename, content_type, expiration_minutes)


def set_blob_metadata(gcs_path: str, metadata: dict[str, str]) -> None:
    """Set custom metadata on a stored blob."""
    if _use_local_storage() or gcs_path.startswith("local://"):
        logger.info("Local storage: skipping metadata for %s", gcs_path)
        return
    _gcs_set_blob_metadata(gcs_path, metadata)


def generate_download_url(gcs_path: str, expiration_minutes: int = 60) -> str:
    """Generate a URL for downloading a file."""
    if _use_local_storage() or gcs_path.startswith("local://"):
        return _local_generate_download_url(gcs_path)
    return _gcs_generate_download_url(gcs_path, expiration_minutes)


# --- Local storage backend ---


def _local_generate_upload_url(filename: str) -> tuple[str, str]:
    """Generate a local upload URL and file path."""
    blob_id = str(uuid4())
    blob_path = f"{blob_id}/{filename}"

    # Ensure directory exists
    upload_dir = _LOCAL_UPLOAD_DIR / blob_id
    upload_dir.mkdir(parents=True, exist_ok=True)

    api_port = os.getenv("API_PORT", "8000")
    upload_url = f"http://localhost:{api_port}/local-upload/{blob_path}"
    local_uri = f"local://protocols/{blob_path}"

    logger.info("Local storage: upload URL for %s -> %s", filename, local_uri)
    return (upload_url, local_uri)


def _local_generate_download_url(gcs_path: str) -> str:
    """Generate a local download URL from a local:// URI."""
    # local://protocols/{uuid}/{filename} -> /local-files/{uuid}/{filename}
    path = gcs_path.replace("local://protocols/", "")
    api_port = os.getenv("API_PORT", "8000")
    return f"http://localhost:{api_port}/local-files/{path}"


def _content_hash(data: bytes) -> str:
    """Compute SHA-256 hex digest of file content for deduplication.

    Args:
        data: Raw file bytes.

    Returns:
        SHA-256 hex digest string.
    """
    return hashlib.sha256(data).hexdigest()


def local_save_file(blob_path: str, data: bytes) -> None:
    """Save uploaded file to local storage with SHA-256 deduplication.

    Uses a hash-index file (.hash-index.json) in the upload directory to
    detect duplicate content. If an identical file already exists, creates a
    symlink to the original rather than storing duplicate bytes.

    Args:
        blob_path: Relative path within the local upload directory.
        data: Raw file bytes to store.
    """
    file_path = _LOCAL_UPLOAD_DIR / blob_path
    file_path.parent.mkdir(parents=True, exist_ok=True)

    content_hash = _content_hash(data)
    hash_index_path = _LOCAL_UPLOAD_DIR / ".hash-index.json"

    # Load existing hash index or create empty dict
    hash_index: dict[str, str] = {}
    if hash_index_path.exists():
        try:
            hash_index = json.loads(hash_index_path.read_text())
        except (json.JSONDecodeError, OSError):
            logger.warning("Could not read hash index — starting fresh")

    if content_hash in hash_index:
        existing_path = _LOCAL_UPLOAD_DIR / hash_index[content_hash]
        logger.info(
            "Dedup: content hash %s... already stored at %s",
            content_hash[:8],
            existing_path,
        )
        # Create symlink to existing file (saves disk space)
        if existing_path.exists() and not file_path.exists():
            file_path.symlink_to(existing_path)
        elif not file_path.exists():
            # Fallback: existing file gone, store normally and update index
            file_path.write_bytes(data)
            hash_index[content_hash] = blob_path
    else:
        # New content — store file and record in index
        file_path.write_bytes(data)
        hash_index[content_hash] = blob_path
        logger.info("Local storage: saved %d bytes to %s", len(data), file_path)

    # Write updated hash index back to disk
    try:
        hash_index_path.write_text(json.dumps(hash_index, indent=2))
    except OSError:
        logger.warning("Could not write hash index to %s", hash_index_path)


def local_get_file_path(blob_path: str) -> Path | None:
    """Get the local filesystem path for a stored file."""
    file_path = _LOCAL_UPLOAD_DIR / blob_path
    return file_path if file_path.exists() else None


# --- GCS backend ---


@gcs_breaker
@_gcs_retry
def _gcs_generate_upload_url(
    filename: str,
    content_type: str = "application/pdf",
    expiration_minutes: int = 15,
) -> tuple[str, str]:
    """Generate a signed URL for uploading a file to GCS."""
    blob_path = f"protocols/{uuid4()}/{filename}"

    bucket_name = get_bucket_name()
    client = get_gcs_client()
    if client is None:
        raise ValueError("GCS client initialization failed. Check GCP credentials.")

    bucket = client.bucket(bucket_name)
    blob = bucket.blob(blob_path)

    signed_url = blob.generate_signed_url(
        version="v4",
        expiration=timedelta(minutes=expiration_minutes),
        method="PUT",
        content_type=content_type,
    )

    gcs_path = f"gs://{bucket_name}/{blob_path}"
    return (signed_url, gcs_path)


@gcs_breaker
@_gcs_retry
def _gcs_set_blob_metadata(gcs_path: str, metadata: dict[str, str]) -> None:
    """Set custom metadata on a GCS blob."""
    bucket_name, blob_path = _parse_gcs_uri(gcs_path)
    client = get_gcs_client()
    if client is None:
        raise ValueError("GCS client unavailable. Cannot set metadata.")

    bucket = client.bucket(bucket_name)
    blob = bucket.blob(blob_path)
    blob.metadata = metadata
    blob.patch()
    logger.info("Set metadata on %s: %s", gcs_path, metadata)


@gcs_breaker
@_gcs_retry
def _gcs_generate_download_url(gcs_path: str, expiration_minutes: int = 60) -> str:
    """Generate a signed URL for downloading a file from GCS."""
    bucket_name, blob_path = _parse_gcs_uri(gcs_path)
    client = get_gcs_client()
    if client is None:
        raise ValueError("GCS client unavailable. Check GCP credentials.")

    bucket = client.bucket(bucket_name)
    blob = bucket.blob(blob_path)

    signed_url = blob.generate_signed_url(
        version="v4",
        expiration=timedelta(minutes=expiration_minutes),
        method="GET",
    )
    return signed_url
