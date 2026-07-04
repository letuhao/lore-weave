"""Pure verification core for the LoreWeave platform *user* JWT.

No FastAPI import here on purpose: ``verify_access_token`` is usable from any
context (a worker, a script, a non-HTTP path). The FastAPI dependency shims live
in ``fastapi_deps`` and build on this.

The rules mirror ``contracts/platformjwt.Verify`` (Go) exactly so the two-language
contract cannot drift:
  - HS256 ONLY (alg-pinned — rejects ``alg:none`` and any RS/EC/PS token).
  - ``exp`` REQUIRED and enforced.
  - ``sub`` MUST be present and parse as a UUID; the UUID is returned.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

import jwt

__all__ = ["AccessClaims", "InvalidAccessToken", "verify_access_token"]


class InvalidAccessToken(Exception):
    """Raised for every verification failure mode.

    Deliberately a single exception type with a terse message: callers (the
    FastAPI dependency) map ALL failures to a uniform 401 so a bad actor cannot
    distinguish "no header" from "bad secret" from "expired". The message is for
    server-side logs, not the client response body.
    """


@dataclass(frozen=True)
class AccessClaims:
    """The verified claims of a platform user access token.

    ``user_id`` is the parsed ``sub`` claim — the single field every consumer
    needs. ``raw`` exposes the full decoded payload for the rare caller that
    needs another standard claim (e.g. ``iat``) without re-decoding.
    """

    user_id: UUID
    subject: str
    expires_at: int | None = None
    raw: dict[str, Any] = field(default_factory=dict)


def verify_access_token(token: str, secret: str) -> AccessClaims:
    """Verify an HS256 platform user JWT and return its claims.

    Raises :class:`InvalidAccessToken` on any failure (empty secret, malformed
    token, wrong secret, tampered signature, ``alg:none``/RS downgrade, expired,
    missing ``exp``, missing/non-UUID ``sub``).
    """
    if not secret:
        # An unconfigured secret must never fall through to a permissive verify.
        raise InvalidAccessToken("empty secret")

    try:
        data = jwt.decode(
            token,
            secret,
            algorithms=["HS256"],
            # `verify_aud=False` for Go parity: contracts/platformjwt.Verify never
            # inspects `aud`. PyJWT's default (`verify_aud=True` with no `audience`
            # passed) REJECTS a token that merely CARRIES an `aud` claim — so an
            # auth-service token with `aud` set would be accepted by Go but 401'd by
            # Python. Neither side pins `iss` (PyJWT only checks it when `issuer=` is
            # given), so `iss` is already parity. Keep the two verifiers identical.
            options={"require": ["exp"], "verify_aud": False},
        )
    except jwt.ExpiredSignatureError as exc:
        raise InvalidAccessToken("token expired") from exc
    except jwt.InvalidTokenError as exc:
        # Covers alg:none / algorithm mismatch (RS downgrade), signature
        # mismatch, malformed token, and missing required exp.
        raise InvalidAccessToken("invalid token") from exc

    sub = data.get("sub")
    if not isinstance(sub, str) or not sub:
        # Type check first, then truthiness — keeps it correct for non-string
        # sub values (int, bool, None).
        raise InvalidAccessToken("missing sub claim")

    try:
        user_id = UUID(sub)
    except (ValueError, TypeError) as exc:
        raise InvalidAccessToken("invalid sub claim") from exc

    # `exp` may be an int or a float (RFC 7519 allows a NumericDate with a
    # fractional second); PyJWT already enforced expiry, so this is purely the
    # informational copy. Coerce a numeric exp to int; anything else → None.
    exp = data.get("exp")
    expires_at = int(exp) if isinstance(exp, (int, float)) and not isinstance(exp, bool) else None
    return AccessClaims(
        user_id=user_id,
        subject=sub,
        expires_at=expires_at,
        raw=data,
    )
