#!/usr/bin/env python3
"""Check that Application Default Credentials (ADC) are present and valid.

Used by make run-dev to decide whether to run gcloud auth application-default login.
Exits 0 when ADC are not needed (local storage or service account key) or when
ADC load and refresh succeed; exits 1 when ADC are required but missing or expired.

Run from repo root:
  uv run python scripts/check_adc.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Load .env from repo root so USE_LOCAL_STORAGE and GOOGLE_APPLICATION_CREDENTIALS are set
_repo_root = Path(__file__).resolve().parent.parent
_env_file = _repo_root / ".env"
if _env_file.exists():
    from dotenv import load_dotenv

    load_dotenv(_env_file)


def _use_local_storage() -> bool:
    """Return True if local storage is enabled (ADC not needed for GCS)."""
    return os.getenv("USE_LOCAL_STORAGE", "").strip().lower() in ("1", "true", "yes")


def _has_service_account_key() -> bool:
    """Return True if GOOGLE_APPLICATION_CREDENTIALS points to an existing file."""
    path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "").strip()
    if not path:
        return False
    return Path(path).expanduser().is_file()


def main() -> int:
    """Check ADC validity; exit 0 if OK or not needed, 1 if missing/expired."""
    if _use_local_storage():
        return 0
    if _has_service_account_key():
        return 0

    try:
        import google.auth
        from google.auth.transport.requests import Request
    except ImportError as e:
        print("check_adc: google-auth not available:", e, file=sys.stderr)
        return 1

    try:
        credentials, _ = google.auth.default()
        credentials.refresh(Request())
        return 0
    except google.auth.exceptions.RefreshError as e:
        print("Application Default Credentials expired or invalid:", e, file=sys.stderr)
        return 1
    except google.auth.exceptions.DefaultCredentialsError as e:
        print("Application Default Credentials not found:", e, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
