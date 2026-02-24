"""Shared exception types for cross-service behavior.

Use these so consumers (e.g. outbox processor) can treat certain failures
specially (e.g. do not retry on auth expiry).
"""


class AuthExpiredError(Exception):
    """Google/application-default credentials need re-authentication.

    Raised when a pipeline or backend operation fails due to expired
    credentials (e.g. RefreshError). Callers should not retry; the user
    must re-authenticate (e.g. gcloud auth application-default login or
    UI login).
    """

    pass
