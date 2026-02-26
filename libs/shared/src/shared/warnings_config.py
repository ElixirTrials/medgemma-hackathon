"""Centralized warning filters to keep console and logs clean."""

from __future__ import annotations

import warnings


def suppress_google_genai_deprecations() -> None:
    """Ignore known noisy deprecation warnings from the google-genai SDK.

    Call once at application or script startup so logs are not polluted by
    third-party warnings (e.g. AiohttpClientSession inheritance).
    """
    warnings.filterwarnings(
        "ignore",
        message=(
            "Inheritance class AiohttpClientSession from ClientSession is discouraged"
        ),
        category=DeprecationWarning,
    )
