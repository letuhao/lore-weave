"""KM5-M2 — /v1/kg/actions admin (auth=admin) branch unit tests (auth boundary).

Proves the System-tier confirm path: RS256 admin JWT re-verified at confirm
(re-presented as X-Admin-Token, never X-User-Id), `admin:write` required, the
redeemer bound to the proposer via `sub == asub` (both non-empty), single-use
jti, and the effect dispatched. The effect itself (real PG writes) is covered by
test_system_effect.py; here the system repo is a fake so the focus is the gate.
"""

from __future__ import annotations

import time
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.auth.admin_jwt import AUDIENCE, ISSUER, SCOPE_ADMIN_WRITE, load_admin_key
from app.config import settings
from app.deps import get_grant_client, get_projects_repo
from app.middleware.jwt_auth import get_current_user
from app.ontology.confirm import AUTH_ADMIN, ActionClaims, mint_action_token
from app.routers.public import kg_actions

pytestmark = pytest.mark.asyncio

_ADMIN_SUB = "admin-principal-1"


# ── RSA keypair + admin JWT (real RS256) ──────────────────────────────────────
def _gen_key() -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _spki(priv: rsa.RSAPrivateKey) -> str:
    return priv.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
    ).decode()


def _admin_jwt(priv, kid, *, sub=_ADMIN_SUB, scopes=None, ttl=3600) -> str:
    now = int(time.time())
    return jwt.encode(
        {
            "sub": sub, "iss": ISSUER, "aud": AUDIENCE, "iat": now, "exp": now + ttl,
            "jti": str(uuid4()), "role": "admin",
            "scopes": scopes if scopes is not None else [SCOPE_ADMIN_WRITE],
        },
        priv, algorithm="RS256", headers={"kid": kid},
    )


def _confirm_token(*, asub=_ADMIN_SUB, descriptor=kg_actions.DESC_SYSTEM_CREATE,
                   params=None, jti=None) -> str:
    return mint_action_token(
        settings.jwt_secret,
        ActionClaims(
            jti=jti or str(uuid4()), authority=AUTH_ADMIN, user_id="",
            descriptor=descriptor, project_id="", admin_sub=asub,
            params=params or {"verb": "create", "code": "new-genre", "name": "New Genre"},
        ),
        time.time(),
    )


def _build(*, claimed=True, system_repo=None, admin_enabled=True):
    priv = _gen_key()
    admin_key = load_admin_key(_spki(priv))
    app = FastAPI()
    app.include_router(kg_actions.router)

    repo = system_repo or AsyncMock()
    if system_repo is None:
        repo.create_template = AsyncMock(return_value=SimpleNamespace(
            code="new-genre", schema_id=uuid4(), schema_version=1))
        repo.code_exists = AsyncMock(return_value=False)
    tokens = AsyncMock()
    tokens.consume = AsyncMock(return_value=claimed)

    app.dependency_overrides[get_current_user] = lambda: uuid4()  # any signed-in browser
    app.dependency_overrides[get_grant_client] = lambda: AsyncMock()
    app.dependency_overrides[get_projects_repo] = lambda: AsyncMock()
    app.dependency_overrides[kg_actions.get_system_templates_repo] = lambda: repo
    app.dependency_overrides[kg_actions.get_action_token_repo] = lambda: tokens
    # FastAPI resolves every confirm/preview param even for an admin token; stub
    # the grant-path repos so DI doesn't reach for an uninitialised pool.
    app.dependency_overrides[kg_actions.get_graph_schemas_repo] = lambda: AsyncMock()
    app.dependency_overrides[kg_actions.get_ontology_mutations_repo] = lambda: AsyncMock()
    app.dependency_overrides[kg_actions.get_triage_repo] = lambda: AsyncMock()
    app.dependency_overrides[kg_actions.get_glossary_ontology_client] = lambda: AsyncMock()
    app.dependency_overrides[kg_actions.get_admin_key] = (
        (lambda: admin_key) if admin_enabled else (lambda: None)
    )
    return app, priv, admin_key, repo, tokens


# confirm_action resolves the FE caller from a real Authorization Bearer JWT
# (D-PMCP-WORKER-CARRIER dual-auth). An admin confirms from their signed-in
# browser, so every admin confirm/preview carries a session JWT *and* the RS256
# X-Admin-Token. The admin path ignores the caller id, so any valid sub works.
_SESSION_JWT = jwt.encode({"sub": str(uuid4())}, settings.jwt_secret, algorithm="HS256")


async def _post(app, path, json, headers=None):
    merged = {"Authorization": f"Bearer {_SESSION_JWT}", **(headers or {})}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        return await c.post(path, json=json, headers=merged)


# ── happy ─────────────────────────────────────────────────────────────────────
async def test_admin_create_happy():
    app, priv, key, repo, tokens = _build()
    r = await _post(app, "/v1/kg/actions/confirm", {"confirm_token": _confirm_token()},
                    headers={"X-Admin-Token": _admin_jwt(priv, key.kid)})
    assert r.status_code == 200, r.text
    assert r.json()["applied"] is True and r.json()["verb"] == "create"
    tokens.consume.assert_awaited_once()
    repo.create_template.assert_awaited_once()


# ── RS256 gate ──────────────────────────────────────────────────────────────
async def test_admin_disabled_503():
    app, priv, key, repo, tokens = _build(admin_enabled=False)
    r = await _post(app, "/v1/kg/actions/confirm", {"confirm_token": _confirm_token()},
                    headers={"X-Admin-Token": _admin_jwt(priv, key.kid)})
    assert r.status_code == 503
    tokens.consume.assert_not_awaited()


async def test_admin_missing_token_header_401():
    app, priv, key, repo, tokens = _build()
    r = await _post(app, "/v1/kg/actions/confirm", {"confirm_token": _confirm_token()})
    assert r.status_code == 401
    tokens.consume.assert_not_awaited()


async def test_admin_invalid_token_401():
    app, priv, key, repo, tokens = _build()
    other = _gen_key()  # signed by a different key than the configured one
    r = await _post(app, "/v1/kg/actions/confirm", {"confirm_token": _confirm_token()},
                    headers={"X-Admin-Token": _admin_jwt(other, key.kid)})
    assert r.status_code == 401
    tokens.consume.assert_not_awaited()


async def test_admin_missing_scope_403():
    app, priv, key, repo, tokens = _build()
    r = await _post(app, "/v1/kg/actions/confirm", {"confirm_token": _confirm_token()},
                    headers={"X-Admin-Token": _admin_jwt(priv, key.kid, scopes=["admin:read"])})
    assert r.status_code == 403
    tokens.consume.assert_not_awaited()


# ── asub binding (KM5-M1 /review-impl MED) ────────────────────────────────────
async def test_admin_asub_mismatch_403():
    # live admin token sub != confirm-token asub → not valid for this admin.
    app, priv, key, repo, tokens = _build()
    r = await _post(app, "/v1/kg/actions/confirm",
                    {"confirm_token": _confirm_token(asub="someone-else")},
                    headers={"X-Admin-Token": _admin_jwt(priv, key.kid, sub=_ADMIN_SUB)})
    assert r.status_code == 403
    tokens.consume.assert_not_awaited()


async def test_admin_empty_asub_403():
    # both sub and asub empty must NOT match (the codec doesn't require sub).
    app, priv, key, repo, tokens = _build()
    r = await _post(app, "/v1/kg/actions/confirm", {"confirm_token": _confirm_token(asub="")},
                    headers={"X-Admin-Token": _admin_jwt(priv, key.kid, sub="")})
    assert r.status_code == 403
    tokens.consume.assert_not_awaited()


# ── single-use ────────────────────────────────────────────────────────────────
async def test_admin_replay_422():
    app, priv, key, repo, tokens = _build(claimed=False)  # jti already in the ledger
    r = await _post(app, "/v1/kg/actions/confirm", {"confirm_token": _confirm_token()},
                    headers={"X-Admin-Token": _admin_jwt(priv, key.kid)})
    assert r.status_code == 422
    assert "already confirmed" in r.json()["detail"].lower()
    repo.create_template.assert_not_awaited()


# ── drift (patch) ─────────────────────────────────────────────────────────────
async def test_admin_patch_drift_422():
    repo = AsyncMock()
    repo.get_system_template = AsyncMock(return_value=SimpleNamespace(
        schema_id=uuid4(), code="general", name="General", schema_version=99))
    app, priv, key, _r, tokens = _build(system_repo=repo)
    sid = str(uuid4())
    tok = _confirm_token(descriptor=kg_actions.DESC_SYSTEM_PATCH,
                         params={"verb": "patch", "schema_id": sid,
                                 "expected_schema_version": 3, "name": "Renamed"})
    r = await _post(app, "/v1/kg/actions/confirm", {"confirm_token": tok},
                    headers={"X-Admin-Token": _admin_jwt(priv, key.kid)})
    assert r.status_code == 422
    assert "changed" in r.json()["detail"].lower()
    tokens.consume.assert_awaited_once()  # jti spent (fail-closed), no write landed
    repo.patch_template.assert_not_awaited()


# ── preview (non-consuming) ───────────────────────────────────────────────────
async def test_admin_preview_create_non_consuming():
    app, priv, key, repo, tokens = _build()
    r = await _post(app, "/v1/kg/actions/preview", {"confirm_token": _confirm_token()},
                    headers={"X-Admin-Token": _admin_jwt(priv, key.kid)})
    assert r.status_code == 200, r.text
    assert r.json()["descriptor"] == "kg_system_create" and r.json()["drift"] is False
    tokens.consume.assert_not_awaited()


async def test_admin_preview_create_flags_code_conflict():
    repo = AsyncMock()
    repo.code_exists = AsyncMock(return_value=True)
    app, priv, key, _r, tokens = _build(system_repo=repo)
    r = await _post(app, "/v1/kg/actions/preview", {"confirm_token": _confirm_token()},
                    headers={"X-Admin-Token": _admin_jwt(priv, key.kid)})
    assert r.status_code == 200
    assert r.json()["drift"] is True
    tokens.consume.assert_not_awaited()


# ── authority↔descriptor pairing (defense in depth) ───────────────────────────
async def test_admin_authority_with_grant_descriptor_422():
    # auth=admin but a GRANT descriptor (kg_schema_edit) → rejected before any
    # effect, even with a valid admin token (an admin token must never drive a
    # project-grant effect).
    app, priv, key, repo, tokens = _build()
    tok = mint_action_token(
        settings.jwt_secret,
        ActionClaims(jti=str(uuid4()), authority=AUTH_ADMIN, user_id="",
                     descriptor=kg_actions.DESC_SCHEMA_EDIT, project_id=str(uuid4()),
                     admin_sub=_ADMIN_SUB,
                     params={"verb": "add", "level": "edge_type", "code": "X",
                             "label": "x", "schema_id": str(uuid4()),
                             "expected_schema_version": 1}),
        time.time(),
    )
    r = await _post(app, "/v1/kg/actions/confirm", {"confirm_token": tok},
                    headers={"X-Admin-Token": _admin_jwt(priv, key.kid)})
    assert r.status_code == 422
    tokens.consume.assert_not_awaited()


async def test_grant_authority_with_system_descriptor_422():
    # auth=grant but a SYSTEM descriptor → rejected before the MANAGE gate / claim
    # (a project grant must never drive a System write).
    app, priv, key, repo, tokens = _build()
    tok = mint_action_token(
        settings.jwt_secret,
        ActionClaims(jti=str(uuid4()), authority="grant", user_id=str(uuid4()),
                     descriptor=kg_actions.DESC_SYSTEM_CREATE, project_id=str(uuid4()),
                     params={"verb": "create", "code": "c", "name": "n"}),
        time.time(),
    )
    r = await _post(app, "/v1/kg/actions/confirm", {"confirm_token": tok},
                    headers={"X-Admin-Token": _admin_jwt(priv, key.kid)})
    assert r.status_code == 422
    tokens.consume.assert_not_awaited()
    repo.create_template.assert_not_awaited()


# ── descriptor/verb integrity ─────────────────────────────────────────────────
async def test_admin_descriptor_verb_mismatch_422():
    # descriptor says create but params.verb=delete (a malformed mint) → fail closed.
    app, priv, key, repo, tokens = _build()
    tok = _confirm_token(descriptor=kg_actions.DESC_SYSTEM_CREATE,
                         params={"verb": "delete", "schema_id": str(uuid4())})
    r = await _post(app, "/v1/kg/actions/confirm", {"confirm_token": tok},
                    headers={"X-Admin-Token": _admin_jwt(priv, key.kid)})
    assert r.status_code == 422
    assert "mismatch" in r.json()["detail"].lower()
