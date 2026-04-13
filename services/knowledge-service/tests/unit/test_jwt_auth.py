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


def test_valid_token_without_exp_still_works():
    """exp is optional — auth-service may issue non-expiring service tokens."""
    uid = uuid4()
    token = _encode({"sub": str(uid)})

    client = TestClient(_make_app())
    resp = client.get("/whoami", headers={"Authorization": f"Bearer {token}"})

    assert resp.status_code == 200


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
    assert "expired" in resp.json()["detail"].lower()


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
    assert "sub" in resp.json()["detail"].lower()


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
    assert "sub" in resp.json()["detail"].lower()


def test_non_string_sub_claim_returns_401():
    token = _encode({"sub": 12345})

    client = TestClient(_make_app())
    resp = client.get("/whoami", headers={"Authorization": f"Bearer {token}"})

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
