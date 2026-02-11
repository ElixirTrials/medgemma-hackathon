"""GCS client wrapper for signed URL generation and metadata operations.

Provides utilities for:
- Generating signed upload URLs for direct browser-to-GCS uploads
- Generating signed download URLs for reading stored PDFs
- Setting custom metadata on GCS blobs

Falls back to mock URLs when GCS_BUCKET_NAME is not configured,
allowing local development without GCS credentials.
"""

from __future__ import annotations

import logging
import os
from datetime import timedelta
from uuid import uuid4

logger = logging.getLogger(__name__)

# Module-level singleton for GCS client
_gcs_client = None


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
                "GCS operations will use mock fallback."
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
    """Generate a signed URL for uploading a file to GCS.

    Creates a unique blob path and returns a signed PUT URL that
    allows direct browser upload to GCS without proxying through
    the server.

    Args:
        filename: Original filename of the upload.
        content_type: MIME type for the upload (default: application/pdf).
        expiration_minutes: URL validity in minutes (default: 15).

    Returns:
        Tuple of (signed_url, gcs_path) where gcs_path is
        gs://bucket/protocols/{uuid}/{filename}.
    """
    blob_path = f"protocols/{uuid4()}/{filename}"

    # Check if GCS is configured
    bucket_name = os.getenv("GCS_BUCKET_NAME")
    if not bucket_name:
        mock_path = f"local://protocols/{uuid4()}/{filename}"
        logger.warning(
            "GCS_BUCKET_NAME not set. Returning mock upload URL "
            "for local development. File: %s",
            filename,
        )
        return ("http://localhost:8000/mock-upload", mock_path)

    client = get_gcs_client()
    if client is None:
        mock_path = f"local://protocols/{uuid4()}/{filename}"
        logger.warning(
            "GCS client unavailable. Returning mock upload URL "
            "for local development. File: %s",
            filename,
        )
        return ("http://localhost:8000/mock-upload", mock_path)

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


def set_blob_metadata(gcs_path: str, metadata: dict[str, str]) -> None:
    """Set custom metadata on a GCS blob.

    Args:
        gcs_path: GCS URI (gs://bucket/path/to/blob).
        metadata: Dict of string key-value pairs for custom metadata.

    Raises:
        ValueError: If GCS URI is invalid.
    """
    if gcs_path.startswith("local://"):
        logger.warning("Skipping metadata set for local path: %s", gcs_path)
        return

    bucket_name, blob_path = _parse_gcs_uri(gcs_path)
    client = get_gcs_client()
    if client is None:
        logger.warning(
            "GCS client unavailable. Skipping metadata set for: %s",
            gcs_path,
        )
        return

    bucket = client.bucket(bucket_name)
    blob = bucket.blob(blob_path)
    blob.metadata = metadata
    blob.patch()
    logger.info("Set metadata on %s: %s", gcs_path, metadata)


def generate_download_url(gcs_path: str, expiration_minutes: int = 60) -> str:
    """Generate a signed URL for downloading a file from GCS.

    Args:
        gcs_path: GCS URI (gs://bucket/path/to/blob).
        expiration_minutes: URL validity in minutes (default: 60).

    Returns:
        Signed GET URL for reading the PDF.

    Raises:
        ValueError: If GCS URI is invalid.
    """
    if gcs_path.startswith("local://"):
        logger.warning(
            "Returning mock download URL for local path: %s",
            gcs_path,
        )
        return "http://localhost:8000/mock-download"

    bucket_name, blob_path = _parse_gcs_uri(gcs_path)
    client = get_gcs_client()
    if client is None:
        logger.warning(
            "GCS client unavailable. Returning mock download URL for: %s",
            gcs_path,
        )
        return "http://localhost:8000/mock-download"

    bucket = client.bucket(bucket_name)
    blob = bucket.blob(blob_path)

    signed_url = blob.generate_signed_url(
        version="v4",
        expiration=timedelta(minutes=expiration_minutes),
        method="GET",
    )
    return signed_url
