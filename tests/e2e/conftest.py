"""E2E test configuration and fixtures.

Provides Docker Compose stack detection, automatic skip when the stack is
unavailable, and core fixtures (authenticated HTTP client, direct DB session,
PDF upload factory, database cleanup) for end-to-end tests against the real
running services.

Usage:
    Mark any E2E test with ``@pytest.mark.e2e``. When the Docker Compose stack
    is not running, all e2e-marked tests are automatically skipped (exit 0).
"""

from __future__ import annotations

import base64
import logging
import os
import time
from pathlib import Path
from typing import Callable

import httpx
import jwt
import pytest

logger = logging.getLogger(__name__)

# Default test PDF (smallest available at ~90K)
_DEFAULT_TEST_PDF = "data/protocols/crc_protocols/isrctn/48616-d8fc1476.pdf"

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


# ---------------------------------------------------------------------------
# Protocol tracking (for cleanup)
# ---------------------------------------------------------------------------


@pytest.fixture()
def _created_protocol_ids() -> list[str]:
    """Accumulate protocol IDs created during a single test function."""
    return []


# ---------------------------------------------------------------------------
# Upload fixture (factory pattern)
# ---------------------------------------------------------------------------


@pytest.fixture()
def upload_test_pdf(
    e2e_api_client: httpx.Client,
    _created_protocol_ids: list[str],
) -> Callable[..., str]:
    """Factory fixture: upload a real PDF through the API upload flow.

    Returns a callable ``upload_test_pdf(pdf_path=None) -> protocol_id``.
    The upload follows the same three-step flow the frontend uses:

    1. POST /api/protocols/upload  (get signed/local upload URL)
    2. PUT pdf bytes to the upload URL
    3. POST /api/protocols/{id}/confirm-upload

    Requires ``USE_LOCAL_STORAGE=1`` on the API container so that the
    upload URL points to the local-upload endpoint.
    """

    def _upload(pdf_path: str | None = None) -> str:
        path = Path(pdf_path or _DEFAULT_TEST_PDF)
        if not path.is_absolute():
            # Resolve relative to repo root
            repo_root = Path(__file__).resolve().parents[2]
            path = repo_root / path
        assert path.exists(), f"Test PDF not found: {path}"

        pdf_bytes = path.read_bytes()

        # Step 1: Request upload URL
        resp = e2e_api_client.post(
            "/api/protocols/upload",
            json={
                "filename": "test-e2e.pdf",
                "content_type": "application/pdf",
                "file_size_bytes": len(pdf_bytes),
            },
        )
        assert resp.status_code == 200, (
            f"Upload request failed ({resp.status_code}): {resp.text}"
        )
        data = resp.json()
        protocol_id = data["protocol_id"]
        upload_url = data["upload_url"]

        # Step 2: PUT the PDF bytes to the upload URL
        put_resp = httpx.put(
            upload_url,
            content=pdf_bytes,
            headers={"Content-Type": "application/pdf"},
            timeout=30.0,
        )
        assert put_resp.status_code == 200, (
            f"PUT to upload URL failed ({put_resp.status_code}): {put_resp.text}"
        )

        # Step 3: Confirm upload (with base64 PDF for quality scoring)
        pdf_b64 = base64.b64encode(pdf_bytes).decode("ascii")
        confirm_resp = e2e_api_client.post(
            f"/api/protocols/{protocol_id}/confirm-upload",
            json={"pdf_bytes_base64": pdf_b64},
        )
        assert confirm_resp.status_code == 200, (
            f"Confirm upload failed ({confirm_resp.status_code}): {confirm_resp.text}"
        )

        _created_protocol_ids.append(protocol_id)
        logger.info("Uploaded test PDF -> protocol_id=%s", protocol_id)
        return protocol_id

    return _upload


# ---------------------------------------------------------------------------
# Database cleanup (autouse for all tests in tests/e2e/)
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def e2e_cleanup(
    e2e_db_session,  # noqa: ANN001
    _created_protocol_ids: list[str],
):
    """Delete all test-created protocols and related data after each test.

    Deletion order respects foreign key constraints:
    entities -> reviews -> audit_log -> criteria -> criteria_batches ->
    outbox_events -> protocol
    """
    yield  # Run the test

    if not _created_protocol_ids:
        return

    from sqlmodel import col, delete, select

    from shared.models import (
        AuditLog,
        Criteria,
        CriteriaBatch,
        Entity,
        OutboxEvent,
        Protocol,
        Review,
    )

    session = e2e_db_session

    for protocol_id in _created_protocol_ids:
        # Gather batch IDs for this protocol
        batch_ids: list[str] = [
            row
            for row in session.exec(
                select(CriteriaBatch.id).where(
                    CriteriaBatch.protocol_id == protocol_id
                )
            ).all()
        ]

        # Gather criteria IDs across all batches
        criteria_ids: list[str] = []
        if batch_ids:
            criteria_ids = [
                row
                for row in session.exec(
                    select(Criteria.id).where(col(Criteria.batch_id).in_(batch_ids))
                ).all()
            ]

        # 1. Delete entities for these criteria
        if criteria_ids:
            session.exec(
                delete(Entity).where(col(Entity.criteria_id).in_(criteria_ids))  # type: ignore[arg-type]
            )

        # 2. Delete reviews for these criteria
        if criteria_ids:
            session.exec(
                delete(Review).where(col(Review.target_id).in_(criteria_ids))  # type: ignore[arg-type]
            )

        # 3. Delete audit log entries related to this protocol or its criteria
        target_ids = [protocol_id, *criteria_ids]
        session.exec(
            delete(AuditLog).where(col(AuditLog.target_id).in_(target_ids))  # type: ignore[arg-type]
        )

        # 4. Delete criteria
        if batch_ids:
            session.exec(
                delete(Criteria).where(col(Criteria.batch_id).in_(batch_ids))  # type: ignore[arg-type]
            )

        # 5. Delete criteria batches
        if batch_ids:
            session.exec(
                delete(CriteriaBatch).where(col(CriteriaBatch.id).in_(batch_ids))  # type: ignore[arg-type]
            )

        # 6. Delete outbox events for this protocol
        session.exec(
            delete(OutboxEvent).where(  # type: ignore[arg-type]
                OutboxEvent.aggregate_id == protocol_id
            )
        )

        # 7. Delete the protocol itself
        session.exec(
            delete(Protocol).where(Protocol.id == protocol_id)  # type: ignore[arg-type]
        )

    session.commit()
    logger.info(
        "E2E cleanup: deleted %d protocol(s) and related data",
        len(_created_protocol_ids),
    )


# ---------------------------------------------------------------------------
# Pipeline wait utility
# ---------------------------------------------------------------------------

_TERMINAL_STATUSES = frozenset(
    {
        "pending_review",
        "complete",
        "extraction_failed",
        "grounding_failed",
        "pipeline_failed",
        "dead_letter",
    }
)


def wait_for_pipeline(
    api_client: httpx.Client,
    protocol_id: str,
    timeout: int = 180,
    poll_interval: int = 5,
) -> dict:
    """Poll protocol status until it reaches a terminal state.

    Args:
        api_client: Authenticated httpx client.
        protocol_id: Protocol to monitor.
        timeout: Maximum seconds to wait.
        poll_interval: Seconds between polls.

    Returns:
        The final protocol response dict.

    Raises:
        TimeoutError: If timeout is exceeded before reaching terminal state.
    """
    deadline = time.monotonic() + timeout
    while True:
        resp = api_client.get(f"/api/protocols/{protocol_id}")
        resp.raise_for_status()
        data = resp.json()

        status = data.get("status", "")
        if status in _TERMINAL_STATUSES:
            logger.info(
                "Pipeline reached terminal status '%s' for %s",
                status,
                protocol_id,
            )
            return data

        if time.monotonic() > deadline:
            raise TimeoutError(
                f"Protocol {protocol_id} still in '{status}' after {timeout}s"
            )

        time.sleep(poll_interval)
