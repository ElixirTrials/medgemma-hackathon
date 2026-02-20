"""Pytest configuration and shared fixtures for api-service tests.

Provides database, HTTP client, and async client fixtures used
by all test modules in this directory.
"""

import gc
import os
from datetime import datetime, timedelta
from typing import AsyncGenerator, Generator

# Set DATABASE_URL before any app imports (storage.py requires it at import time)
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

import jwt as pyjwt
import pytest
from fastapi.testclient import TestClient
from httpx import AsyncClient
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from sqlmodel import Session


@pytest.fixture(scope="function")
def db_engine():
    """Create an in-memory SQLite database engine for testing.

    Each test gets a fresh database. Tables are created from SQLModel metadata.
    """
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    # Register and create all shared tables (Protocol, Criteria, etc.)
    import shared.models  # noqa: F401
    from sqlmodel import SQLModel

    SQLModel.metadata.create_all(engine)

    try:
        yield engine
    finally:
        engine.dispose()
        gc.collect()


@pytest.fixture(scope="function")
def db_session(db_engine) -> Generator[Session, None, None]:
    """Create a database session for testing.

    Automatically rolls back changes after each test.
    """
    session = Session(db_engine)
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture(scope="function")
def test_client(db_session) -> Generator[TestClient, None, None]:
    """Create a FastAPI test client with auth and DB overrides.

    This fixture overrides both get_db and get_current_user so that
    existing tests pass without modification.
    """
    from api_service.dependencies import get_current_user, get_db
    from api_service.main import app

    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    def override_get_current_user():
        return {"sub": "test-user-id", "email": "test@example.com", "name": "Test User"}

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_get_current_user

    with TestClient(app) as client:
        yield client

    app.dependency_overrides.clear()


@pytest.fixture(scope="function")
async def async_client(db_session) -> AsyncGenerator[AsyncClient, None]:
    """Create an async HTTP client for testing async endpoints."""
    from api_service.dependencies import get_current_user, get_db
    from api_service.main import app

    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    def override_get_current_user():
        return {"sub": "test-user-id", "email": "test@example.com", "name": "Test User"}

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_get_current_user

    async with AsyncClient(app=app, base_url="http://test") as client:
        yield client

    app.dependency_overrides.clear()


@pytest.fixture
def auth_headers() -> dict[str, str]:
    """Return Authorization headers with a valid test JWT."""
    secret = os.environ.get("JWT_SECRET_KEY", "dev-secret-key-change-in-production")
    payload = {
        "sub": "test-user-id",
        "email": "test@example.com",
        "name": "Test User",
        "exp": datetime.utcnow() + timedelta(hours=1),
    }
    token = pyjwt.encode(payload, secret, algorithm="HS256")
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def unauthenticated_client(db_session) -> Generator[TestClient, None, None]:
    """Test client WITHOUT auth override -- requests will get 401."""
    from api_service.dependencies import get_db
    from api_service.main import app

    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    # Deliberately NOT overriding get_current_user

    with TestClient(app) as client:
        yield client

    app.dependency_overrides.clear()
