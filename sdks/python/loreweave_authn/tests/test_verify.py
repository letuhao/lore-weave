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
    # Mutate a char at the FRONT of the signature segment, NOT the last char:
    # the last base64url char of a 32-byte HS256 sig encodes only 4 significant
    # bits, so A/B/C/D decode to identical bytes and a last-char flip is a no-op
    # ~6% of the time (flaky). A front char contributes a full 6 bits → the
    # decoded signature always changes → verification must fail deterministically.
    head, _, sig = tok.rpartition(".")
    flipped = ("Z" if sig[0] != "Z" else "Y") + sig[1:]
    tampered = f"{head}.{flipped}"
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


def test_accepts_token_carrying_aud_go_parity():
    # Go's contracts/platformjwt.Verify never inspects `aud`. PyJWT's default
    # (verify_aud=True, no `audience` passed) would REJECT a token that merely
    # carries an `aud` claim — a real accept/reject drift vs Go. The verifier
    # disables aud verification, so an auth token with `aud` set is accepted by
    # BOTH languages. Guards against a silent two-language contract drift.
    tok = _encode(_good_payload(aud="loreweave-api"))
    claims = verify_access_token(tok, SECRET)
    assert str(claims.user_id) == SUBJECT

    tok_list = _encode(_good_payload(aud=["a", "b"]))
    assert str(verify_access_token(tok_list, SECRET).user_id) == SUBJECT


def test_accepts_token_carrying_iss_go_parity():
    # Go never pins `iss` either; PyJWT only checks it when `issuer=` is passed
    # (we never do), so an `iss`-bearing token is accepted by both.
    tok = _encode(_good_payload(iss="loreweave-auth"))
    assert str(verify_access_token(tok, SECRET).user_id) == SUBJECT


def test_float_exp_coerced_to_int():
    # RFC 7519 NumericDate may be fractional. PyJWT enforces expiry regardless;
    # the informational `expires_at` must still be an int (not dropped to None).
    exp_float = (_now() + dt.timedelta(minutes=10)).timestamp() + 0.5
    tok = _encode(_good_payload(exp=exp_float))
    claims = verify_access_token(tok, SECRET)
    assert isinstance(claims.expires_at, int)
    assert claims.expires_at == int(exp_float)


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
