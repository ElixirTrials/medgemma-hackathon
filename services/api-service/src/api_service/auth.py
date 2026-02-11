"""FastAPI router for Google OAuth authentication and JWT management.

Provides endpoints for:
- GET /auth/login: Redirect to Google OAuth
- GET /auth/callback: Handle OAuth callback and issue JWT
- GET /auth/me: Get current user info from JWT
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta
from typing import Any, Dict

import jwt
from authlib.integrations.starlette_client import OAuth
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from shared.models import User
from sqlmodel import Session, select

from api_service.dependencies import get_current_user, get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])

# Configure OAuth client
oauth = OAuth()
oauth.register(
    name="google",
    server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
    client_kwargs={"scope": "openid email profile"},
)

# JWT secret from environment
SECRET_KEY = os.getenv("JWT_SECRET_KEY", "dev-secret-key-change-in-production")


# --- Response models ---


class UserInfo(BaseModel):
    """User information included in auth responses."""

    id: str
    email: str
    name: str | None


class TokenResponse(BaseModel):
    """Response from successful authentication."""

    access_token: str
    token_type: str
    user: UserInfo


# --- Endpoints ---


@router.get("/login")
async def login(request: Request) -> Dict[str, Any]:
    """Redirect to Google OAuth login page.

    Initiates the OAuth flow by redirecting the user to Google's
    authorization endpoint.
    """
    redirect_uri = request.url_for("auth_callback")
    return await oauth.google.authorize_redirect(request, redirect_uri)


@router.get("/callback")
async def auth_callback(
    request: Request,
    db: Session = Depends(get_db),
) -> TokenResponse:
    """Handle OAuth callback from Google and issue JWT.

    Exchanges the authorization code for an access token, retrieves
    user info, creates or updates the User record, and issues a JWT.
    """
    try:
        # Exchange code for token
        token = await oauth.google.authorize_access_token(request)
        userinfo = token.get("userinfo")

        if not userinfo or not userinfo.get("email"):
            raise HTTPException(
                status_code=400,
                detail="Failed to retrieve user info from Google",
            )

        email = userinfo["email"]
        name = userinfo.get("name")
        picture_url = userinfo.get("picture")

        # Upsert user in database
        stmt = select(User).where(User.email == email)
        existing_user = db.exec(stmt).first()

        if existing_user:
            # Update existing user
            existing_user.name = name
            existing_user.picture_url = picture_url
            user = existing_user
        else:
            # Create new user
            user = User(
                email=email,
                name=name,
                picture_url=picture_url,
            )
            db.add(user)

        db.commit()
        db.refresh(user)

        # Create JWT
        payload = {
            "sub": user.id,
            "email": user.email,
            "name": user.name,
            "exp": datetime.utcnow() + timedelta(hours=24),
        }
        access_token = jwt.encode(payload, SECRET_KEY, algorithm="HS256")

        return TokenResponse(
            access_token=access_token,
            token_type="bearer",
            user=UserInfo(
                id=user.id,
                email=user.email,
                name=user.name,
            ),
        )

    except Exception as e:
        logger.error(f"OAuth callback error: {e}")
        raise HTTPException(
            status_code=500,
            detail="Authentication failed",
        )


@router.get("/me", response_model=UserInfo)
def get_me(current_user: dict = Depends(get_current_user)) -> UserInfo:
    """Get current user info from JWT token.

    Returns the user information decoded from the JWT Bearer token.
    """
    return UserInfo(
        id=current_user["sub"],
        email=current_user["email"],
        name=current_user.get("name"),
    )
