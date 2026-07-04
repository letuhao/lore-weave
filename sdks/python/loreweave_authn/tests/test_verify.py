"""Adversarial matrix for loreweave_authn — mirrors contracts/platformjwt Go tests.

Covers: round-trip, alg:none, RS-downgrade / alg confusion, expired, missing exp,
tampered signature, wrong secret, empty secret, malformed, non-UUID sub, empty sub.
Plus the FastAPI dependency behavior (401 vs None for optional).
"""

from __future__ import annotations

import datetime as dt

import jwt
import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from loreweave_authn import (
    AccessClaims,
    InvalidAccessToken,
    build_get_current_user,
    get_bearer_token,
    verify_access_token,
)

SECRET = "shared-platform-jwt-secret-for-tests"
SUBJECT = "11111111-1111-1111-1111-111111111111"


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _good_payload(**over) -> dict:
    payload = {
        "sub": SUBJECT,
        "iat": _now(),
        "exp": _now() + dt.timedelta(minutes=10),
    }
    payload.update(over)
    return payload


def _encode(payload: dict, *, secret: str = SECRET, algorithm: str = "HS256", key=None) -> str:
    return jwt.encode(payload, key if key is not None else secret, algorithm=algorithm)


# ── verify_access_token ──────────────────────────────────────────────────────


def test_round_trip():
    claims = verify_access_token(_encode(_good_payload()), SECRET)
    assert isinstance(claims, AccessClaims)
    assert str(claims.user_id) == SUBJECT
    assert claims.subject == SUBJECT
    assert claims.expires_at is not None


def test_rejects_alg_none():
    # alg:none — unsigned token. PyJWT requires an explicit empty key for none.
    tok = jwt.encode(_good_payload(), key="", algorithm="none")
    with pytest.raises(InvalidAccessToken):
        verify_access_token(tok, SECRET)


def test_rejects_rs_downgrade():
    # A token minted with RS256 must be rejected: the verifier pins HS256 and
    # must never treat an asymmetric token as HMAC.
    from cryptography.hazmat.primitives.asymmetric import rsa

    priv = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    tok = jwt.encode(_good_payload(), priv, algorithm="RS256")
    with pytest.raises(InvalidAccessToken):
        verify_access_token(tok, SECRET)


def test_rejects_expired():
    tok = _encode(_good_payload(exp=_now() - dt.timedelta(minutes=1)))
    with pytest.raises(InvalidAccessToken):
        verify_access_token(tok, SECRET)


def test_requires_exp():
    payload = _good_payload()
    del payload["exp"]
    tok = _encode(payload)
    with pytest.raises(InvalidAccessToken):
        verify_access_token(tok, SECRET)


def test_rejects_tampered_signature():
    tok = _encode(_good_payload())
    tampered = tok[:-1] + ("A" if tok[-1] != "A" else "B")
    with pytest.raises(InvalidAccessToken):
        verify_access_token(tampered, SECRET)


def test_rejects_wrong_secret():
    tok = _encode(_good_payload())
    with pytest.raises(InvalidAccessToken):
        verify_access_token(tok, "a-different-secret")


def test_rejects_empty_secret():
    tok = _encode(_good_payload())
    with pytest.raises(InvalidAccessToken):
        verify_access_token(tok, "")


@pytest.mark.parametrize("tok", ["", "not-a-jwt", "only.two", "aaa.bbb.ccc"])
def test_rejects_malformed(tok):
    with pytest.raises(InvalidAccessToken):
        verify_access_token(tok, SECRET)


def test_rejects_non_uuid_sub():
    tok = _encode(_good_payload(sub="not-a-uuid"))
    with pytest.raises(InvalidAccessToken):
        verify_access_token(tok, SECRET)


def test_rejects_empty_sub():
    tok = _encode(_good_payload(sub=""))
    with pytest.raises(InvalidAccessToken):
        verify_access_token(tok, SECRET)


def test_rejects_non_string_sub():
    tok = _encode(_good_payload(sub=12345))
    with pytest.raises(InvalidAccessToken):
        verify_access_token(tok, SECRET)


# ── FastAPI dependency shims ─────────────────────────────────────────────────


def _creds(token: str) -> HTTPAuthorizationCredentials:
    return HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)


def test_dependency_returns_uuid():
    dep = build_get_current_user(lambda: SECRET)
    out = dep(credentials=_creds(_encode(_good_payload())))
    assert str(out) == SUBJECT


def test_dependency_return_subject_shape():
    dep = build_get_current_user(lambda: SECRET, return_subject=True)
    out = dep(credentials=_creds(_encode(_good_payload())))
    assert out == SUBJECT  # str, chat-service shape


def test_dependency_401_on_missing():
    dep = build_get_current_user(lambda: SECRET)
    with pytest.raises(HTTPException) as exc:
        dep(credentials=None)
    assert exc.value.status_code == 401


def test_dependency_401_on_invalid():
    dep = build_get_current_user(lambda: SECRET)
    with pytest.raises(HTTPException) as exc:
        dep(credentials=_creds("garbage"))
    assert exc.value.status_code == 401


def test_optional_dependency_none_on_missing():
    dep = build_get_current_user(lambda: SECRET, optional=True)
    assert dep(credentials=None) is None


def test_optional_dependency_none_on_invalid():
    dep = build_get_current_user(lambda: SECRET, optional=True)
    assert dep(credentials=_creds("garbage")) is None


def test_optional_dependency_returns_uuid_when_valid():
    dep = build_get_current_user(lambda: SECRET, optional=True)
    out = dep(credentials=_creds(_encode(_good_payload())))
    assert str(out) == SUBJECT


def test_get_bearer_token_returns_raw():
    tok = _encode(_good_payload())
    assert get_bearer_token(credentials=_creds(tok)) == tok


def test_get_bearer_token_401_on_missing():
    with pytest.raises(HTTPException) as exc:
        get_bearer_token(credentials=None)
    assert exc.value.status_code == 401
