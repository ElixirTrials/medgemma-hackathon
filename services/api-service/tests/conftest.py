"""Pytest configuration and shared fixtures for api-service tests.

Provides database, HTTP client, and async client fixtures used
by all test modules in this directory.
"""

import os
from typing import AsyncGenerator, Generator

# Set DATABASE_URL before any app imports (storage.py requires it at import time)
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

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


@pytest.fixture(scope="function")
def db_session(db_engine) -> Generator[Session, None, None]:
    """Create a database session for testing.

    Automatically rolls back changes after each test.
    """
    with Session(db_engine) as session:
        try:
            yield session
        finally:
            session.rollback()


@pytest.fixture(scope="function")
def test_client(db_session) -> Generator[TestClient, None, None]:
    """Create a FastAPI test client with a test database session."""
    from api_service.dependencies import get_db
    from api_service.main import app

    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as client:
        yield client

    app.dependency_overrides.clear()


@pytest.fixture(scope="function")
async def async_client(db_session) -> AsyncGenerator[AsyncClient, None]:
    """Create an async HTTP client for testing async endpoints."""
    from api_service.dependencies import get_db
    from api_service.main import app

    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db

    async with AsyncClient(app=app, base_url="http://test") as client:
        yield client

    app.dependency_overrides.clear()
