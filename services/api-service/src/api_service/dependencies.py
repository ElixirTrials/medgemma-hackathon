"""Dependency injection for FastAPI endpoints."""

import os
from collections.abc import Generator

import jwt
from fastapi import Header, HTTPException
from sqlmodel import Session

from api_service.storage import engine


def get_db() -> Generator[Session, None, None]:
    """Provide a database session for dependency injection.

    Yields:
        Database session that automatically commits or rolls back.
    """
    with Session(engine) as session:
        yield session


def get_current_user(authorization: str | None = Header(default=None)) -> dict:
    """Extract and validate JWT from Authorization header.

    Expected format: Bearer <token>

    Returns:
        Dict with user claims: sub, email, name.

    Raises:
        HTTPException: 401 if token is missing, expired, or invalid.
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid auth header")

    token = authorization[7:]
    try:
        secret = os.getenv("JWT_SECRET_KEY", "dev-secret-key-change-in-production")
        payload = jwt.decode(token, secret, algorithms=["HS256"])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")
