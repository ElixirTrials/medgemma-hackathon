"""Pytest configuration for umls-mcp-server tests."""

import os
from pathlib import Path

from dotenv import load_dotenv

# Load repo root .env so UMLS_API_KEY is set when running integration tests.
# Path: .../repo/services/umls-mcp-server/tests/conftest.py -> repo is parents[3].
_repo_root = Path(__file__).resolve().parents[3]
load_dotenv(_repo_root / ".env")
load_dotenv()
os.environ.setdefault("UMLS_API_KEY", "test-key-for-unit-tests")
