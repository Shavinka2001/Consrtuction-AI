"""
JWT authentication dependency for FastAPI.

Validates the Bearer token on every protected route via FastAPI's
dependency injection system.

Expected env vars (set in .env):
    JWT_SECRET_KEY   – secret used to sign tokens (must match the issuer)
    JWT_ALGORITHM    – defaults to HS256
"""

from __future__ import annotations

import os
from typing import Annotated

import jwt
from dotenv import load_dotenv
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

load_dotenv()

# ── Configuration ──────────────────────────────────────────────────────────────

JWT_SECRET_KEY: str = os.getenv("JWT_SECRET_KEY", "")
JWT_ALGORITHM: str = os.getenv("JWT_ALGORITHM", "HS256")

if not JWT_SECRET_KEY:
    raise RuntimeError(
        "JWT_SECRET_KEY environment variable is not set. "
        "Add it to backend/.env before starting the server."
    )

# ── Bearer scheme (auto-injects into OpenAPI / Swagger UI) ────────────────────

_bearer_scheme = HTTPBearer(auto_error=True)

# ── Dependency ─────────────────────────────────────────────────────────────────


def require_auth(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(_bearer_scheme)],
) -> dict:
    """
    FastAPI dependency — decodes and validates the JWT supplied in the
    'Authorization: Bearer <token>' header.

    Returns the decoded token payload so downstream routes can inspect
    claims (e.g. ``user_id``, ``role``) without repeating decode logic.

    Raises:
        HTTP 401  – token missing, expired, or signature invalid.
        HTTP 403  – token is structurally valid but claims are insufficient
                    (extend this check as needed for role-based access).
    """
    token = credentials.credentials

    try:
        payload: dict = jwt.decode(
            token,
            JWT_SECRET_KEY,
            algorithms=[JWT_ALGORITHM],
        )
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return payload
