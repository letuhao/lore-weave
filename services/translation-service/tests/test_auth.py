"""Unit tests for auth.py — JWT minting and verification."""
import time
import jwt
import pytest

from app.auth import mint_user_jwt, verify_request_jwt

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


def test_verify_valid_token_returns_sub():
    token = mint_user_jwt(USER_ID, SECRET)
    result = verify_request_jwt(token, SECRET)
    assert result == USER_ID


def test_verify_expired_token_raises():
    token = mint_user_jwt(USER_ID, SECRET, ttl_seconds=-1)
    with pytest.raises(jwt.ExpiredSignatureError):
        verify_request_jwt(token, SECRET)


def test_verify_wrong_secret_raises():
    token = mint_user_jwt(USER_ID, SECRET)
    with pytest.raises(jwt.InvalidTokenError):
        verify_request_jwt(token, "wrong_secret_completely_different!!")


def test_verify_garbage_raises():
    with pytest.raises(jwt.InvalidTokenError):
        verify_request_jwt("not.a.token", SECRET)
