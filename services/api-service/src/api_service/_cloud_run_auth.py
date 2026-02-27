"""Helpers for Cloud Run service-to-service authentication.

On Cloud Run, services behind IAM require an ID token for invocation.
This module fetches ID tokens from the metadata server and configures
MLflow to use them via MLFLOW_TRACKING_TOKEN.
"""

from __future__ import annotations

import logging
import os
import threading
import time

logger = logging.getLogger(__name__)

# Cache token and its expiry to avoid hitting metadata server on every call.
_token_lock = threading.Lock()
_cached_token: str | None = None
_token_expiry: float = 0.0  # epoch seconds
_TOKEN_REFRESH_MARGIN = 600  # refresh 10 min before expiry


def _is_cloud_run() -> bool:
    """Check if we're running on Cloud Run."""
    return bool(os.getenv("K_SERVICE"))


def get_id_token(audience: str) -> str | None:
    """Fetch an ID token for the given audience from the metadata server.

    Returns None if not running on Cloud Run or if the fetch fails.
    Caches the token and refreshes it when close to expiry.
    """
    global _cached_token, _token_expiry  # noqa: PLW0603

    if not _is_cloud_run():
        return None

    with _token_lock:
        now = time.time()
        if _cached_token and now < _token_expiry - _TOKEN_REFRESH_MARGIN:
            return _cached_token

        try:
            import requests as _requests

            resp = _requests.get(
                "http://metadata.google.internal/computeMetadata/v1/"
                f"instance/service-accounts/default/identity?audience={audience}",
                headers={"Metadata-Flavor": "Google"},
                timeout=3,
            )
            resp.raise_for_status()
            token = resp.text.strip()

            # ID tokens from metadata server are valid for ~1 hour
            _cached_token = token
            _token_expiry = now + 3600
            logger.info("Fetched Cloud Run ID token for audience: %s", audience)
            return token
        except Exception:
            logger.warning(
                "Could not fetch ID token for %s from metadata server",
                audience,
                exc_info=True,
            )
            # Trip MLflow circuit breaker -- metadata server unreachable means
            # we cannot authenticate to MLflow. Skip MLflow entirely.
            try:
                from shared.resilience import mlflow_breaker

                mlflow_breaker.open()
            except Exception:
                pass
            return None


def configure_mlflow_auth() -> None:
    """Set MLFLOW_TRACKING_TOKEN for Cloud Run service-to-service auth.

    Must be called before any MLflow client operations. Safe to call
    multiple times -- refreshes the token if needed.
    """
    tracking_uri = os.getenv("MLFLOW_TRACKING_URI")
    if not tracking_uri or not _is_cloud_run():
        return

    token = get_id_token(tracking_uri)
    if token:
        os.environ["MLFLOW_TRACKING_TOKEN"] = token
        logger.info("Set MLFLOW_TRACKING_TOKEN for Cloud Run auth")
