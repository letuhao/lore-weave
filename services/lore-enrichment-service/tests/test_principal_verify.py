"""P3 SDK-first — regression lock for the LE acting-principal JWT verification.

Before P3, `app/api/principal.py` decoded the bearer with
`verify_signature=False`, so a FORGED token (any `sub`, any secret) was accepted
— letting a caller act as any user on the real user-scoped routes (compose does
BYOK model resolution → PAID calls; book_profile/gaps do user-scoped data). This
locks the fix: the signature (HS256) + `exp` are now verified via the shared
`loreweave_authn`, and a forged/expired token resolves to an ANONYMOUS principal
(user_id=None) instead of impersonating the claimed `sub`.
"""
from __future__ import annotations

import jwt as pyjwt
from uuid import UUID

from app.api.principal import _extract_user_id

_SECRET = "test_jwt_secret"  # matches conftest JWT_SECRET
_USER = "019d5e3c-7cc5-7e6a-8b27-1344e148bf7c"
_FAR = 4102444800  # 2100-01-01


def _tok(claims: dict, secret: str = _SECRET) -> str:
    return pyjwt.encode(claims, secret, algorithm="HS256")


def test_valid_token_resolves_uuid():
    uid = _extract_user_id(_tok({"sub": _USER, "exp": _FAR}))
    assert uid == UUID(_USER)  # a UUID, not a str — owner-checks compare UUIDs


def test_forged_signature_is_rejected():
    # The core security fix: a token signed with the WRONG secret (a forgery)
    # MUST NOT authenticate — pre-fix this returned UUID(_USER), impersonating.
    assert _extract_user_id(_tok({"sub": _USER, "exp": _FAR}, secret="attacker")) is None


def test_expired_token_is_rejected():
    assert _extract_user_id(_tok({"sub": _USER, "exp": 1})) is None


def test_missing_exp_is_rejected():
    # The verifier requires `exp` (stricter, correct posture).
    assert _extract_user_id(_tok({"sub": _USER})) is None


def test_non_uuid_sub_is_rejected():
    assert _extract_user_id(_tok({"sub": "not-a-uuid", "exp": _FAR})) is None


def test_garbage_token_is_anonymous():
    assert _extract_user_id("not.a.jwt") is None
