"""Public-API JWT authentication dependency (K7.1).

Parses the `Authorization: Bearer <token>` header with the same HS256
secret used by auth-service and chat-service, and returns the user_id
(`sub` claim) as a UUID so downstream repos can use it directly.

Security invariants (KSA §6.1 and the K7 doc):
  - `user_id` is NEVER accepted from query string or body — the ONLY
    source of truth is the JWT `sub` claim. Every public /v1/knowledge/*
    endpoint takes `user_id: UUID = Depends(get_current_user)`.
  - 401 is returned uniformly for every failure mode (missing header,
    malformed header, expired, invalid signature, missing sub, sub that
    isn't a UUID). The response body is deliberately terse so a bad
    actor can't distinguish "no header" from "bad secret".
  - `HTTPBearer(auto_error=False)` so we own the 401 path uniformly;
    FastAPI's default auto-raise returns 403 for missing creds which
    would be inconsistent with the other failure modes.

Pattern mirrors chat-service's `app/middleware/auth.py` — kept close so
a reader sees the same shape on both sides of the wire.
"""

from __future__ import annotations

from uuid import UUID

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import settings

__all__ = ["get_current_user", "bearer_scheme"]

bearer_scheme = HTTPBearer(auto_error=False)


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> UUID:
    """Return the authenticated user's id from the JWT `sub` claim.

    Raises 401 on any failure mode. Callers must never bypass this by
    reading user_id from request body or query parameters.
    """
    if credentials is None:
        raise _unauthorized("missing bearer token")

    token = credentials.credentials
    try:
        data = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        raise _unauthorized("token expired")
    except jwt.InvalidTokenError:
        raise _unauthorized("invalid token")

    sub = data.get("sub")
    if not sub or not isinstance(sub, str):
        raise _unauthorized("missing sub claim")

    try:
        return UUID(sub)
    except (ValueError, TypeError):
        raise _unauthorized("invalid sub claim")
