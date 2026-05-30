"""Acting-principal dependency (Q3 scope + H0 promotion authority seam).

Even at the contract-freeze stage the route signatures MUST carry the acting
principal — the adversary focus for C3 calls out that promote (and every scoped
route) must not be anonymous. We decode the bearer JWT to surface a `user_id`
WITHOUT enforcing verification yet (real auth/authorization is wired in a later
cycle). This keeps the principal load-bearing in the shape while leaving
behaviour (signature verification, owner check) for C13's review gate.

The decode is best-effort and unverified: a missing/garbage token yields an
anonymous principal (user_id=None) rather than a 401, so stub routes stay
reachable (200/501, never 500) per the C3 acceptance gate. The promote handler
documents — but does not yet enforce — that only the book/project owner may act.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

import jwt as pyjwt
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

# auto_error=False → a missing Authorization header does not 401 here; the stub
# routes must remain reachable during the contract freeze. Real enforcement is
# added with the auth wiring in a later cycle.
_bearer = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class Principal:
    """The acting user derived from the bearer token. `user_id` is None when no
    (or an unparseable) token is presented — the unverified contract-freeze
    posture. `is_authenticated` reflects only that a user_id was recoverable,
    not that the token signature was checked."""

    user_id: UUID | None

    @property
    def is_authenticated(self) -> bool:
        return self.user_id is not None


def _extract_user_id(token: str) -> UUID | None:
    """Best-effort, UNVERIFIED decode of the JWT `sub` claim. Signature is NOT
    checked here (C3 freeze); returns None on any failure."""
    try:
        claims = pyjwt.decode(token, options={"verify_signature": False})
    except pyjwt.PyJWTError:
        return None
    sub = claims.get("sub")
    if not sub:
        return None
    try:
        return UUID(str(sub))
    except (ValueError, TypeError):
        return None


async def require_principal(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> Principal:
    """Resolve the acting principal from the bearer token (unverified at C3)."""
    if creds is None or not creds.credentials:
        return Principal(user_id=None)
    return Principal(user_id=_extract_user_id(creds.credentials))


__all__ = ["Principal", "require_principal"]
