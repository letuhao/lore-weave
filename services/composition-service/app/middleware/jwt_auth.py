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

__all__ = [
    "get_current_user",
    "get_optional_current_user",
    "get_bearer_token",
    "bearer_scheme",
]

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
    if not isinstance(sub, str) or not sub:
        # Type check first, then truthiness — keeps the condition
        # easy to read for non-string `sub` values (int, bool, None).
        raise _unauthorized("missing sub claim")

    try:
        return UUID(sub)
    except (ValueError, TypeError):
        raise _unauthorized("invalid sub claim")


def get_optional_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> UUID | None:
    """Return the JWT `sub` user id when a VALID Bearer token is present, else None.

    Unlike :func:`get_current_user` this NEVER raises — it is for routes that accept
    EITHER a user JWT (the FE path) OR an internal-token + X-User-Id service envelope
    (the MCP/gateway path), so a missing or malformed JWT must fall through to the
    service path rather than 401. Identity is still taken ONLY from the `sub` claim
    (never body/query). An invalid/expired/forged token reads as "no JWT identity"
    (None) — the caller then falls back to the internal-token path, which is the
    higher-trust credential anyway."""
    if credentials is None:
        return None
    try:
        data = jwt.decode(credentials.credentials, settings.jwt_secret, algorithms=["HS256"])
    except jwt.InvalidTokenError:
        return None
    sub = data.get("sub")
    if not isinstance(sub, str) or not sub:
        return None
    try:
        return UUID(sub)
    except (ValueError, TypeError):
        return None


def get_bearer_token(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> str:
    """Return the raw JWT string for FORWARDING to book/knowledge public routes.

    The clients re-add the `Bearer ` scheme. Use this alongside
    `get_current_user` when an endpoint both authorizes locally (user_id) AND
    proxies to a downstream service that does its own JWT ownership check
    (prose → book-service; resolve → knowledge-service)."""
    if credentials is None:
        raise _unauthorized("missing bearer token")
    return credentials.credentials
