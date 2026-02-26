"""Helper to produce signing kwargs for GCS signed URLs on Cloud Run.

Compute-engine credentials lack a local private key.  When we detect
non-signing credentials we create a fresh ``Credentials`` object with
the ``cloud-platform`` scope (which Cloud Run provides by default) and
use that token for the IAM ``signBlob`` call.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


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

    # Resolve service-account email
    sa_email = getattr(credentials, "service_account_email", None)
    if not sa_email:
        default_creds, _ = google.auth.default()
        sa_email = getattr(default_creds, "service_account_email", None)
    if not sa_email:
        logger.warning(
            "Cannot determine service account email for URL signing. "
            "Credentials type: %s",
            type(credentials).__name__,
        )
        return {}

    # Build a fresh compute-engine Credentials with cloud-platform scope.
    # The default metadata-server token on Cloud Run has cloud-platform,
    # which is sufficient for IAM signBlob.
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
