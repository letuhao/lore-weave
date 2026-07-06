"""Public-API JWT authentication dependency (K7.1).

Thin wrapper over the shared platform user-JWT verifier
(``loreweave_authn`` — the single HS256 verifier that replaces the ~6
copy-pasted ``jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])``
blocks across the Python services). This module binds the SDK factory to
composition-service's own secret source (``settings.jwt_secret``) and
re-exports the resulting dependencies under the names callers already import.

Security invariants (KSA §6.1 and the K7 doc) — all now enforced by the SDK:
  - `user_id` is NEVER accepted from query string or body — the ONLY
    source of truth is the JWT `sub` claim. Every public /v1/composition/*
    endpoint takes `user_id: UUID = Depends(get_current_user)`.
  - 401 is returned uniformly for every failure mode (missing header,
    malformed header, expired, invalid signature, missing sub, sub that
    isn't a UUID). The response body is deliberately terse so a bad
    actor can't distinguish "no header" from "bad secret".
  - `HTTPBearer(auto_error=False)` so we own the 401 path uniformly;
    FastAPI's default auto-raise returns 403 for missing creds which
    would be inconsistent with the other failure modes.
  - HS256-pinned, `exp` REQUIRED, `sub` MUST parse as a UUID.

Pattern mirrors chat-service's `app/middleware/auth.py` — kept close so
a reader sees the same shape on both sides of the wire.
"""

from __future__ import annotations

from loreweave_authn import (
    bearer_scheme,
    build_get_current_user,
    get_bearer_token,
)

from app.config import settings

__all__ = [
    "get_current_user",
    "get_optional_current_user",
    "get_bearer_token",
    "bearer_scheme",
]

# Returns the authenticated user's id as a `UUID` from the JWT `sub` claim;
# raises 401 uniformly on any failure mode. Callers must never bypass this by
# reading user_id from request body or query parameters.
get_current_user = build_get_current_user(lambda: settings.jwt_secret)

# Returns the `sub` user id when a VALID Bearer token is present, else None
# (NEVER raises). For routes that accept EITHER a user JWT (the FE path) OR an
# internal-token + X-User-Id service envelope (the MCP/gateway path): a missing
# or malformed JWT falls through to the service path rather than 401. An
# invalid/expired/forged token reads as "no JWT identity" (None) — the caller
# then falls back to the internal-token path, the higher-trust credential.
get_optional_current_user = build_get_current_user(
    lambda: settings.jwt_secret, optional=True
)
