"""E2E test configuration and fixtures.

Provides Docker Compose stack detection, automatic skip when the stack is
unavailable, and core fixtures (authenticated HTTP client, direct DB session)
for end-to-end tests against the real running services.

Usage:
    Mark any E2E test with ``@pytest.mark.e2e``. When the Docker Compose stack
    is not running, all e2e-marked tests are automatically skipped (exit 0).
"""

from __future__ import annotations

import os

import httpx
import jwt
import pytest

# ---------------------------------------------------------------------------
# Stack availability detection
# ---------------------------------------------------------------------------

_STACK_AVAILABLE: bool | None = None

_DEFAULT_API_URL = "http://localhost:8000"
_DEFAULT_DATABASE_URL = "postgresql://postgres:postgres@localhost:5432/app"


def _check_stack() -> bool:
    """Check whether the Docker Compose stack (API + PostgreSQL) is reachable."""
    api_url = os.getenv("E2E_API_URL", _DEFAULT_API_URL)
    try:
        resp = httpx.get(f"{api_url}/health", timeout=3.0)
        if resp.status_code != 200:
            return False
    except (httpx.ConnectError, httpx.TimeoutException, Exception):
        return False

    # Also verify PostgreSQL is reachable
    try:
        from sqlalchemy import create_engine, text

        db_url = os.getenv("E2E_DATABASE_URL", _DEFAULT_DATABASE_URL)
        engine = create_engine(db_url, connect_args={"connect_timeout": 3})
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        engine.dispose()
    except Exception:
        return False

    return True


def _wants_e2e(config: pytest.Config) -> bool:
    """Return True only if the user explicitly requested e2e tests.

    This guard prevents the health-check from adding latency to regular
    ``uv run pytest`` invocations that do not target E2E tests.
    """
    # Check -m flag for e2e marker expression
    markexpr: str = config.getoption("-m", default="")
    if markexpr and "e2e" in markexpr:
        return True

    # Check if any explicit test path is under tests/e2e/
    args: list[str] = config.getoption("file_or_dir", default=[]) or []
    for arg in args:
        if "tests/e2e" in str(arg) or "tests\\e2e" in str(arg):
            return True

    return False


# ---------------------------------------------------------------------------
# Pytest hooks
# ---------------------------------------------------------------------------


def pytest_configure(config: pytest.Config) -> None:
    """Detect Docker Compose availability once per session (if e2e requested)."""
    global _STACK_AVAILABLE
    if _wants_e2e(config):
        _STACK_AVAILABLE = _check_stack()
    else:
        # Don't waste time checking -- no e2e tests requested
        _STACK_AVAILABLE = False


def pytest_collection_modifyitems(
    config: pytest.Config, items: list[pytest.Item]
) -> None:
    """Auto-skip all ``@pytest.mark.e2e`` tests when the stack is unavailable."""
    if _STACK_AVAILABLE:
        return

    skip_marker = pytest.mark.skip(
        reason=(
            "Docker Compose stack not running "
            "(API at localhost:8000 or PostgreSQL at localhost:5432 unreachable)"
        )
    )
    for item in items:
        if "e2e" in item.keywords:
            item.add_marker(skip_marker)


# ---------------------------------------------------------------------------
# Session-scoped fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def e2e_api_url() -> str:
    """Base URL for the running API service.

    Reads from ``E2E_API_URL`` env var, defaulting to ``http://localhost:8000``.
    """
    return os.getenv("E2E_API_URL", _DEFAULT_API_URL)


# ---------------------------------------------------------------------------
# Function-scoped fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def e2e_db_session():
    """Provide a SQLModel Session connected to the real Docker Compose PostgreSQL.

    The session targets the database specified by ``E2E_DATABASE_URL`` (default:
    ``postgresql://postgres:postgres@localhost:5432/app``).

    .. note::
        This session does NOT auto-rollback. E2E tests operate on the real
        database; cleanup is handled by dedicated cleanup fixtures in later
        plans.
    """
    from sqlalchemy import create_engine
    from sqlmodel import Session

    db_url = os.getenv("E2E_DATABASE_URL", _DEFAULT_DATABASE_URL)
    engine = create_engine(db_url)
    with Session(engine) as session:
        yield session
    engine.dispose()


@pytest.fixture()
def e2e_api_client(e2e_api_url: str) -> httpx.Client:
    """Provide an authenticated ``httpx.Client`` pointed at the running API.

    The client includes a ``Bearer`` JWT in the ``Authorization`` header,
    signed with the same secret the API uses (``JWT_SECRET_KEY`` env var,
    default: ``dev-secret-key-change-in-production``).

    The test JWT contains claims for a synthetic E2E test user.
    """
    secret = os.getenv("JWT_SECRET_KEY", "dev-secret-key-change-in-production")
    token = jwt.encode(
        {"sub": "e2e-test-user", "email": "e2e@test.com", "name": "E2E Test"},
        secret,
        algorithm="HS256",
    )
    client = httpx.Client(
        base_url=e2e_api_url,
        headers={"Authorization": f"Bearer {token}"},
        timeout=30.0,
    )
    yield client
    client.close()
