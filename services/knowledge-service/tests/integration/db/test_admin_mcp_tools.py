"""KM5-M3 — /mcp/admin tool integration tests (real Postgres).

kg_admin_template_read lists the seeded System templates; kg_admin_propose_template
MINTS a valid auth=admin confirm-token (asub bound to the RS256 subject, descriptor
matching the verb) + a preview, and writes NOTHING (the write happens only when the
human redeems the token at /v1/kg/actions/confirm — KM5-M2).
"""

from __future__ import annotations

import time
from types import SimpleNamespace
from uuid import uuid4

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from app.auth.admin_jwt import AUDIENCE, ISSUER, SCOPE_ADMIN_WRITE, load_admin_key
from app.config import settings
from app.db.seed_graph_schemas import seed_system_graph_schemas
from app.mcp import admin_server
from app.mcp.admin_server import kg_admin_propose_template, kg_admin_template_read
from app.ontology.confirm import AUTH_ADMIN, verify_action_token

pytestmark = pytest.mark.asyncio
_ADMIN_SUB = "smoke-admin"


async def _reset(pool):
    async with pool.acquire() as conn:
        await conn.execute("TRUNCATE kg_graph_schemas RESTART IDENTITY CASCADE")
    await seed_system_graph_schemas(pool)


def _wire(monkeypatch, pool):
    priv = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = priv.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
    ).decode()
    key = load_admin_key(pem)
    monkeypatch.setattr(admin_server, "get_admin_key", lambda: key)
    monkeypatch.setattr(admin_server, "get_knowledge_pool", lambda: pool)
    now = int(time.time())
    tok = jwt.encode(
        {"sub": _ADMIN_SUB, "iss": ISSUER, "aud": AUDIENCE, "iat": now, "exp": now + 600,
         "jti": str(uuid4()), "scopes": [SCOPE_ADMIN_WRITE]},
        priv, algorithm="RS256", headers={"kid": key.kid},
    )
    ctx = SimpleNamespace(
        request_context=SimpleNamespace(request=SimpleNamespace(headers={"x-admin-token": tok}))
    )
    return ctx


async def test_admin_read_lists_seeded_templates(pool, monkeypatch):
    await _reset(pool)
    ctx = _wire(monkeypatch, pool)
    out = await kg_admin_template_read(ctx)
    codes = {t["code"] for t in out["templates"]}
    assert {"general", "xianxia-harem"} <= codes


async def test_admin_propose_create_mints_token_without_writing(pool, monkeypatch):
    await _reset(pool)
    ctx = _wire(monkeypatch, pool)
    code = f"proposed-{uuid4().hex[:6]}"
    out = await kg_admin_propose_template(ctx, verb="create", code=code, name="Proposed")

    assert out["confirm_token"] and out["preview"]["descriptor"] == "kg_system_create"
    # the minted token is a valid auth=admin confirm-token bound to the RS256 sub.
    claims = verify_action_token(settings.jwt_secret, out["confirm_token"], time.time())
    assert claims.authority == AUTH_ADMIN
    assert claims.descriptor == "kg_system_create"
    assert claims.admin_sub == _ADMIN_SUB
    assert claims.params["verb"] == "create" and claims.params["code"] == code

    # NOTHING was written — propose only mints; the write is the confirm step.
    async with pool.acquire() as conn:
        exists = await conn.fetchval(
            "SELECT 1 FROM kg_graph_schemas WHERE scope='system' AND code=$1", code
        )
    assert exists is None


async def test_admin_propose_patch_descriptor_matches_verb(pool, monkeypatch):
    await _reset(pool)
    ctx = _wire(monkeypatch, pool)
    out = await kg_admin_propose_template(
        ctx, verb="patch", schema_id=str(uuid4()), expected_schema_version=1, name="X")
    claims = verify_action_token(settings.jwt_secret, out["confirm_token"], time.time())
    assert claims.descriptor == "kg_system_patch" and claims.params["verb"] == "patch"
