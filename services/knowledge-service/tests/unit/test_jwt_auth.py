"""Unit tests for K7.1 JWT middleware.

Covers every failure mode named in the K7 acceptance criteria
(missing, malformed, expired, invalid signature, missing sub,
invalid sub) plus the happy path. Also asserts the security
invariant that user_id is NEVER read from query/body — we do that
by mounting a tiny router that ignores request body entirely and
relies only on the Depends(get_current_user) return value.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import jwt
import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.config import settings
from app.middleware.jwt_auth import get_current_user


def _make_app() -> FastAPI:
    app = FastAPI()

    @app.get("/whoami")
    def whoami(user_id: UUID = Depends(get_current_user)) -> dict:
        return {"user_id": str(user_id)}

    return app


def _encode(payload: dict, secret: str | None = None) -> str:
    # The shared SDK verifier REQUIRES `exp`, so default a valid one unless the
    # test supplies its own (e.g. the expired case) or explicitly opts out with
    # `exp=None` (the missing-exp rejection case).
    if "exp" not in payload:
        payload = {**payload, "exp": datetime.now(timezone.utc) + timedelta(minutes=5)}
    elif payload["exp"] is None:
        payload = {k: v for k, v in payload.items() if k != "exp"}
    return jwt.encode(
        payload, secret or settings.jwt_secret, algorithm="HS256"
    )


# ── happy path ────────────────────────────────────────────────────────────


def test_valid_token_returns_user_id():
    uid = uuid4()
    token = _encode({"sub": str(uid), "exp": datetime.now(timezone.utc) + timedelta(minutes=5)})

    client = TestClient(_make_app())
    resp = client.get("/whoami", headers={"Authorization": f"Bearer {token}"})

    assert resp.status_code == 200
    assert UUID(resp.json()["user_id"]) == uid


def test_token_without_exp_rejected():
    """SDK migration: `exp` is now REQUIRED (loreweave_authn / Go platformjwt
    parity). A user token without it is rejected uniformly. This reverses the
    pre-SDK behavior where a missing `exp` was accepted."""
    uid = uuid4()
    token = _encode({"sub": str(uid), "exp": None})

    client = TestClient(_make_app())
    resp = client.get("/whoami", headers={"Authorization": f"Bearer {token}"})

    assert resp.status_code == 401


# ── failure modes ─────────────────────────────────────────────────────────


def test_missing_header_returns_401():
    client = TestClient(_make_app())
    resp = client.get("/whoami")
    assert resp.status_code == 401
    assert resp.headers.get("WWW-Authenticate") == "Bearer"


def test_malformed_header_returns_401():
    client = TestClient(_make_app())
    # Missing "Bearer " scheme entirely.
    resp = client.get("/whoami", headers={"Authorization": "notbearer xxx"})
    assert resp.status_code == 401


def test_expired_token_returns_401():
    uid = uuid4()
    token = _encode(
        {
            "sub": str(uid),
            "exp": datetime.now(timezone.utc) - timedelta(minutes=5),
        }
    )

    client = TestClient(_make_app())
    resp = client.get("/whoami", headers={"Authorization": f"Bearer {token}"})

    assert resp.status_code == 401
    # SDK maps every failure mode to a uniform terse 401 (no mode leak).
    assert resp.json()["detail"] == "invalid token"


def test_wrong_signature_returns_401():
    uid = uuid4()
    token = _encode({"sub": str(uid)}, secret="not-the-real-secret")

    client = TestClient(_make_app())
    resp = client.get("/whoami", headers={"Authorization": f"Bearer {token}"})

    assert resp.status_code == 401


def test_missing_sub_claim_returns_401():
    token = _encode({"not_sub": "whatever"})

    client = TestClient(_make_app())
    resp = client.get("/whoami", headers={"Authorization": f"Bearer {token}"})

    assert resp.status_code == 401
    assert resp.json()["detail"] == "invalid token"


def test_empty_sub_claim_returns_401():
    token = _encode({"sub": ""})

    client = TestClient(_make_app())
    resp = client.get("/whoami", headers={"Authorization": f"Bearer {token}"})

    assert resp.status_code == 401


def test_non_uuid_sub_claim_returns_401():
    token = _encode({"sub": "not-a-uuid"})

    client = TestClient(_make_app())
    resp = client.get("/whoami", headers={"Authorization": f"Bearer {token}"})

    assert resp.status_code == 401
    assert resp.json()["detail"] == "invalid token"


def test_non_string_sub_claim_returns_401():
    token = _encode({"sub": 12345})

    client = TestClient(_make_app())
    resp = client.get("/whoami", headers={"Authorization": f"Bearer {token}"})

    assert resp.status_code == 401


def test_empty_bearer_token_returns_401():
    """K7a-I1: `Authorization: Bearer ` with no token after the space.

    HTTPBearer parses this as credentials="" and we forward the empty
    string to jwt.decode, which raises InvalidTokenError. Easy probe
    for an attacker; assert we reject it cleanly.
    """
    client = TestClient(_make_app())
    resp = client.get("/whoami", headers={"Authorization": "Bearer "})
    assert resp.status_code == 401


def test_alg_none_token_rejected():
    """K7a-I2: regression guard for the classic `alg=none` JWT attack.

    A token signed with the `none` algorithm must never be accepted —
    it would let any client forge any user_id. PyJWT enforces this via
    the `algorithms=["HS256"]` whitelist passed to jwt.decode. If a
    future refactor weakens that whitelist, this test fails loudly.
    """
    uid = uuid4()
    # PyJWT requires key=None when alg='none'.
    forged = jwt.encode({"sub": str(uid)}, key=None, algorithm="none")

    client = TestClient(_make_app())
    resp = client.get("/whoami", headers={"Authorization": f"Bearer {forged}"})

    assert resp.status_code == 401


def test_wrong_algorithm_token_rejected():
    """K7a-I2: a token signed with HS512 (or any non-HS256 alg) must be
    rejected even if signed with the correct secret. The whitelist
    pins the algorithm so an attacker can't trick us into validating
    with a weaker primitive.
    """
    uid = uuid4()
    forged = jwt.encode(
        {"sub": str(uid)}, settings.jwt_secret, algorithm="HS512"
    )

    client = TestClient(_make_app())
    resp = client.get("/whoami", headers={"Authorization": f"Bearer {forged}"})

    assert resp.status_code == 401


# ── security invariant: user_id is NOT read from body ─────────────────────


def test_user_id_in_body_is_ignored(monkeypatch):
    """Security: the only source of user_id is the JWT. Even if the
    body contains a user_id field, the middleware must ignore it."""
    authenticated_uid = uuid4()
    attacker_uid = uuid4()
    token = _encode({"sub": str(authenticated_uid)})

    app = FastAPI()

    @app.post("/whoami")
    def whoami(
        body: dict,
        user_id: UUID = Depends(get_current_user),
    ) -> dict:
        return {"user_id": str(user_id), "body_user_id": body.get("user_id")}

    client = TestClient(app)
    resp = client.post(
        "/whoami",
        headers={"Authorization": f"Bearer {token}"},
        json={"user_id": str(attacker_uid)},
    )

    assert resp.status_code == 200
    data = resp.json()
    assert UUID(data["user_id"]) == authenticated_uid
    assert UUID(data["body_user_id"]) == attacker_uid  # still echoed in the body field
    assert UUID(data["user_id"]) != attacker_uid  # but the dep used the JWT
