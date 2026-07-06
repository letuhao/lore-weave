"""Acting-principal dependency (Q3 scope + H0 promotion authority seam).

Every scoped route MUST carry the acting principal — the adversary focus for C3
calls out that promote (and every user-scoped route) must not be anonymous. We
decode the bearer JWT to surface a `user_id`.

**P3 SDK-first: the signature IS now verified** via the shared
`loreweave_authn.verify_access_token` (HS256-pinned, `exp` required, `sub`→UUID) —
the same verifier the other 8 Python user-facing services use, closing the prior
`verify_signature=False` gap (`D-P3-LORE-ENRICH-JWT`). This matters because the
real user-scoped routes (compose/gaps/book_profile) use this `user_id` for BYOK
model resolution [PAID calls] and user-scoped data access — an UNVERIFIED `sub`
let a forged token act as any user.

The decode stays best-effort at the dependency level: a missing/garbage/forged/
expired token yields an anonymous principal (user_id=None) rather than a 401 (the
`auto_error=False` posture), so stub routes stay reachable (200/501, never 500)
while the real routes — which already gate on `user_id is None` — now REJECT a
forged `sub`. Owner-authorization (only the book/project owner may act) is still
C13's concern; this closes only the authentication (signature) half.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from loreweave_authn import InvalidAccessToken, verify_access_token

from app.config import settings

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
    """VERIFIED decode of the JWT `sub` claim via the shared loreweave_authn
    verifier (HS256 signature + `exp` + `sub`→UUID). Returns None on ANY failure
    — missing/garbage/forged/expired token or a non-UUID `sub` — preserving the
    anonymous-principal posture for stub routes while rejecting a forged `sub`."""
    try:
        claims = verify_access_token(token, settings.jwt_secret)
    except InvalidAccessToken:
        return None
    # `claims.subject` is a STR (the verifier validated it parses as a UUID but
    # exposes it as text); the callers/owner-checks compare a UUID, so convert —
    # matching the prior `UUID(str(sub))` return type (`-> UUID | None`).
    return UUID(claims.subject)


async def require_principal(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> Principal:
    """Resolve the acting principal from the bearer token (unverified at C3)."""
    if creds is None or not creds.credentials:
        return Principal(user_id=None)
    return Principal(user_id=_extract_user_id(creds.credentials))


__all__ = ["Principal", "require_principal"]
