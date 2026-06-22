"""Mint a short-lived service bearer for the MCP envelope user (S-COMPOSE).

WHY THIS EXISTS (an honest seam, not a shortcut):

The composition prose tools (`composition_get_prose` / `composition_write_prose`)
proxy book-service's canonical chapter DRAFT routes. Those routes are
**public JWT-only** (`app/clients/book_client.py` docstring + book-service
`requireUserID`): book-service enforces book ownership in SQL keyed on the JWT
`sub` claim. The HTTP path forwards the caller's `Authorization: Bearer`.

The MCP envelope carries NO JWT — only the validated internal-service token plus
`X-User-Id` (the identity is asserted by the gateway, already authed at the
chat-service edge). To reuse the existing, ownership-enforcing book-draft proxy
WITHOUT adding a new internal book-service route (out of this slice's boundary —
S-COMPOSE owns only `services/composition-service/`), we mint a short-lived
HS256 bearer for the envelope `user_id` using composition-service's OWN
`jwt_secret`.

This is SOUND because:
  - `jwt_secret` is the platform-shared HS256 secret (`jwt_auth.py`: "the same
    HS256 secret used by auth-service and chat-service"), the same secret
    book-service validates with — so a token minted here verifies there.
  - book-service still enforces the REAL ownership boundary: its SQL filters on
    `owner_user_id = <sub>`, so a forged `user_id` could only ever reach that
    user's OWN books — and `user_id` here is the envelope identity the kit lifted
    from the trusted internal call (NEVER a tool arg). The book-grant guard
    (`require_book_owner`) has already gated the call before we ever mint.
  - The token is minted with a short TTL + a marker claim, never persisted.

If/when book-service grows an internal (X-Internal-Token) draft read/write +
publish route, this seam should be replaced by a direct internal call. That is
tracked as the COMPOSE B integrator note (see the MCP server module docstring).
"""

from __future__ import annotations

import time
from uuid import UUID

import jwt

# Short — the bearer only needs to live for the single downstream book-service
# call made within one tool invocation. A small skew cushion is unnecessary
# (we are the issuer + the call is immediate).
_SERVICE_BEARER_TTL_S = 60


def mint_service_bearer(
    user_id: UUID, secret: str, *, now: float | None = None, ttl: int = _SERVICE_BEARER_TTL_S
) -> str:
    """Mint a short-lived HS256 bearer whose `sub` is the envelope `user_id`, for
    forwarding to book-service's JWT-only draft routes from the MCP path.

    `secret` is `settings.jwt_secret` (the shared HS256 secret). Raises
    `ValueError` on an empty secret (fail-closed: never emit an unsigned/forgeable
    token). `now` is injectable for tests.

    `ttl` defaults to 60s — enough for an IMMEDIATE downstream call (get/write_prose/
    publish). The cowrite-engine generate effect must pass a LARGER ttl: it reuses the
    bearer to PERSIST the chapter draft AFTER a multi-minute LLM generation, so a 60s
    token would be expired by the persist (silent best-effort draft loss).
    """
    if not secret:
        raise ValueError("cannot mint service bearer: empty jwt_secret")
    issued = int(time.time() if now is None else now)
    claims = {
        "sub": str(user_id),
        "iat": issued,
        "exp": issued + int(ttl),
        # Marker so a log/audit can tell this apart from a real user login token.
        "src": "composition-mcp",
    }
    return jwt.encode(claims, secret, algorithm="HS256")
