"""loreweave_authn — the shared platform *user* JWT verifier (Python).

The single verifier every Python service uses to authenticate a user Bearer
token, replacing the ~6 copy-pasted ``jwt.decode(token, settings.jwt_secret,
algorithms=["HS256"])`` blocks in composition / knowledge / chat / learning /
campaign / jobs middleware (SDK-2 / SEC-2, audit Area 8). Mirrors the Go
``contracts/platformjwt`` module so the two-language contract cannot drift.

The platform user token is an HS256 JWT signed by auth-service with a SHARED
SYMMETRIC secret; every domain service holds that secret and verifies the token
locally. Verification is strict and fail-closed:
  - HS256 ONLY (alg-pinned — rejects ``alg:none`` and any RS/EC/PS token).
  - ``exp`` REQUIRED and enforced.
  - ``sub`` MUST parse as a UUID; that UUID is the authenticated user id.

Two entry points:
  - :func:`verify_access_token` — the pure verifier (no FastAPI needed).
  - :func:`build_get_current_user` + :data:`get_current_user` /
    :data:`get_optional_current_user` / :func:`get_bearer_token` — FastAPI
    dependency shims that mirror the shape chat/composition already use, so
    migration is a thin swap.

Unlike ``adminjwt`` this pins neither issuer nor audience — auth-service does not
set them on user tokens and the inline verifiers never checked them, so pinning
would reject every live token. Parity with the existing logic is deliberate.
"""

from __future__ import annotations

from ._verify import AccessClaims, InvalidAccessToken, verify_access_token
from .fastapi_deps import (
    bearer_scheme,
    build_get_current_user,
    get_bearer_token,
    get_current_user,
    get_optional_current_user,
)

__all__ = [
    "AccessClaims",
    "InvalidAccessToken",
    "verify_access_token",
    "bearer_scheme",
    "build_get_current_user",
    "get_bearer_token",
    "get_current_user",
    "get_optional_current_user",
]
