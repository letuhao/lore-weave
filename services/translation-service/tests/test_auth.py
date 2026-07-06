"""Unit tests for auth.py — the short-lived internal JWT minter.

(P3 SDK-first: the hand-rolled `verify_request_jwt` was removed — user-JWT VERIFY
now lives in the shared `loreweave_authn` SDK, tested in
`sdks/python/loreweave_authn/tests/test_verify.py`. Only the minter remains here.)
"""
import time
import jwt

from app.auth import mint_user_jwt

SECRET = "test_secret_for_unit_tests_32chars!!"
USER_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"


def test_mint_returns_decodable_token():
    token = mint_user_jwt(USER_ID, SECRET)
    data = jwt.decode(token, SECRET, algorithms=["HS256"])
    assert data["sub"] == USER_ID


def test_mint_includes_iat_and_exp():
    before = int(time.time())
    token = mint_user_jwt(USER_ID, SECRET, ttl_seconds=300)
    data = jwt.decode(token, SECRET, algorithms=["HS256"])
    assert data["iat"] >= before
    assert data["exp"] == data["iat"] + 300


def test_mint_respects_custom_ttl():
    token = mint_user_jwt(USER_ID, SECRET, ttl_seconds=60)
    data = jwt.decode(token, SECRET, algorithms=["HS256"])
    assert data["exp"] - data["iat"] == 60
