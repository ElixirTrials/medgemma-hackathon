"""Helper to produce signing kwargs for GCS signed URLs on Cloud Run.

Compute-engine credentials lack a local private key.  When we detect
non-signing credentials we fetch the real service-account email from
the metadata server and request a ``cloud-platform`` scoped token for
the IAM ``signBlob`` call.
"""

from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

# Cache the resolved SA email so we only hit the metadata server once.
_cached_sa_email: str | None = None


def _resolve_sa_email() -> str | None:
    """Get the real service-account email, not 'default'.

    On Cloud Run / GCE the metadata server knows the actual email.
    """
    global _cached_sa_email  # noqa: PLW0603
    if _cached_sa_email is not None:
        return _cached_sa_email

    try:
        import requests as _requests

        resp = _requests.get(
            "http://metadata.google.internal/computeMetadata/v1/"
            "instance/service-accounts/default/email",
            headers={"Metadata-Flavor": "Google"},
            timeout=2,
        )
        resp.raise_for_status()
        _cached_sa_email = resp.text.strip()
        logger.info("Resolved SA email from metadata: %s", _cached_sa_email)
        return _cached_sa_email
    except Exception:
        logger.warning("Could not resolve SA email from metadata server")
        return None


def get_signing_kwargs(client: Any) -> dict[str, Any]:
    """Return extra kwargs for ``blob.generate_signed_url()``.

    * Returns ``{}`` when the client already has signing credentials
      (e.g. a service-account key file).
    * Returns ``{"service_account_email": …, "access_token": …}`` when
      running on Cloud Run so the library delegates to IAM ``signBlob``.
    """
    import google.auth
    import google.auth.credentials
    import google.auth.transport.requests

    credentials = client._credentials
    if isinstance(credentials, google.auth.credentials.Signing):
        return {}

    # Not on a GCP environment — can't sign via IAM
    if not os.getenv("K_SERVICE"):  # Cloud Run sets K_SERVICE
        return {}

    sa_email = _resolve_sa_email()
    if not sa_email:
        return {}

    # Build compute-engine credentials with cloud-platform scope and the
    # real SA email so the token request targets the right account.
    from google.auth.compute_engine import credentials as ce_creds

    scoped = ce_creds.Credentials(
        service_account_email=sa_email,
        scopes=["https://www.googleapis.com/auth/cloud-platform"],
    )
    scoped.refresh(google.auth.transport.requests.Request())

    logger.info("Using IAM signing with SA: %s", sa_email)
    return {
        "service_account_email": sa_email,
        "access_token": scoped.token,
    }
