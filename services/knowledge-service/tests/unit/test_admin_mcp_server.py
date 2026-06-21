"""KM5-M3 — /mcp/admin server unit tests (transport gate + catalog isolation).

Proves INV-T6: the admin tool surface is a physically separate MCP endpoint,
RS256-gated at the transport BEFORE tools/list (no token = 401, can't enumerate),
and its tool names NEVER appear in the /mcp catalog. Plus the per-tool scope/sub
guards on the mint tool. The mint's PG-touching happy path is in
tests/integration/db/test_admin_mcp_tools.py.
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
from app.mcp import admin_server
from app.mcp.admin_server import kg_admin_propose_template, rs256_gate
from app.mcp.server import mcp_server

pytestmark = pytest.mark.asyncio


def _gen():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _spki(priv):
    return priv.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
    ).decode()


def _admin_jwt(priv, kid, *, sub="adm", scopes=None, ttl=600):
    now = int(time.time())
    return jwt.encode(
        {"sub": sub, "iss": ISSUER, "aud": AUDIENCE, "iat": now, "exp": now + ttl,
         "jti": str(uuid4()), "scopes": scopes if scopes is not None else [SCOPE_ADMIN_WRITE]},
        priv, algorithm="RS256", headers={"kid": kid},
    )


# ── INV-T6 catalog isolation ──────────────────────────────────────────────────
async def test_admin_tools_are_not_in_public_catalog():  # async: module mark is asyncio
    pub = set(mcp_server._tool_manager._tools.keys())
    adm = set(admin_server.mcp_admin_server._tool_manager._tools.keys())
    assert adm == {"kg_admin_template_read", "kg_admin_propose_template"}
    assert not (adm & pub), "admin tools must never appear in the /mcp catalog"
    assert not any(t.startswith("kg_admin") for t in pub)


async def test_admin_mount_is_registered_before_mcp():
    # INV-T6 routing: Starlette matches mounts by prefix in registration order, so
    # "/mcp/admin" MUST be registered before "/mcp" — otherwise "/mcp" greedily
    # captures "/mcp/admin/*" and the admin surface would route to the UNGATED
    # public app. A refactor that reorders the mounts breaks the gate; this catches it.
    from app.main import app

    order = [r.path for r in app.routes if getattr(r, "path", "") in ("/mcp", "/mcp/admin")]
    assert order.index("/mcp/admin") < order.index("/mcp"), (
        "/mcp/admin must mount before /mcp (more-specific prefix first)"
    )


# ── transport RS256 gate (runs before tools/list) ─────────────────────────────
class _Spy:
    def __init__(self):
        self.called = False

    async def __call__(self, scope, receive, send):
        self.called = True
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})


# conftest sets INTERNAL_SERVICE_TOKEN=default_test_token (settings.internal_service_token).
_INTERNAL = "default_test_token"


def _scope(token: str | None, *, internal: str | None = _INTERNAL):
    headers = [(b"host", b"t")]
    if internal is not None:
        headers.append((b"x-internal-token", internal.encode()))
    if token is not None:
        headers.append((b"x-admin-token", token.encode()))
    return {"type": "http", "headers": headers, "method": "POST", "path": "/"}


async def _drive(gated, scope):
    sent = []

    async def send(m):
        sent.append(m)

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    await gated(scope, receive, send)
    status = next(m["status"] for m in sent if m["type"] == "http.response.start")
    return status


async def test_gate_no_token_401_does_not_enumerate(monkeypatch):
    priv = _gen()
    monkeypatch.setattr(admin_server, "get_admin_key", lambda: load_admin_key(_spki(priv)))
    spy = _Spy()
    status = await _drive(rs256_gate(spy), _scope(None))
    assert status == 401
    assert spy.called is False  # inner (tools/list) never reached


async def test_gate_disabled_503(monkeypatch):
    monkeypatch.setattr(admin_server, "get_admin_key", lambda: None)
    spy = _Spy()
    status = await _drive(rs256_gate(spy), _scope("anything"))
    assert status == 503
    assert spy.called is False


async def test_gate_invalid_token_401(monkeypatch):
    priv, other = _gen(), _gen()
    key = load_admin_key(_spki(priv))
    monkeypatch.setattr(admin_server, "get_admin_key", lambda: key)
    spy = _Spy()
    status = await _drive(rs256_gate(spy), _scope(_admin_jwt(other, key.kid)))  # wrong signer
    assert status == 401
    assert spy.called is False


async def test_gate_valid_token_delegates(monkeypatch):
    priv = _gen()
    key = load_admin_key(_spki(priv))
    monkeypatch.setattr(admin_server, "get_admin_key", lambda: key)
    spy = _Spy()
    status = await _drive(rs256_gate(spy), _scope(_admin_jwt(priv, key.kid)))
    assert status == 200
    assert spy.called is True


async def test_gate_missing_internal_token_401(monkeypatch):
    # SO-1 (gate 1): no internal token → 401 BEFORE the admin token / disabled check,
    # so a caller without service trust can't even learn admin is configured, and
    # the inner surface is never reached even with an otherwise-valid admin token.
    priv = _gen()
    key = load_admin_key(_spki(priv))
    monkeypatch.setattr(admin_server, "get_admin_key", lambda: key)
    spy = _Spy()
    status = await _drive(rs256_gate(spy), _scope(_admin_jwt(priv, key.kid), internal=None))
    assert status == 401
    assert spy.called is False


async def test_gate_wrong_internal_token_401(monkeypatch):
    priv = _gen()
    key = load_admin_key(_spki(priv))
    monkeypatch.setattr(admin_server, "get_admin_key", lambda: key)
    spy = _Spy()
    status = await _drive(
        rs256_gate(spy), _scope(_admin_jwt(priv, key.kid), internal="wrong-token")
    )
    assert status == 401
    assert spy.called is False


# ── mint tool scope / sub guards (no PG needed — they reject first) ───────────
def _ctx(token: str | None):
    headers = {"x-admin-token": token} if token is not None else {}
    return SimpleNamespace(
        request_context=SimpleNamespace(request=SimpleNamespace(headers=headers))
    )


async def test_propose_missing_scope_rejected(monkeypatch):
    priv = _gen()
    key = load_admin_key(_spki(priv))
    monkeypatch.setattr(admin_server, "get_admin_key", lambda: key)
    tok = _admin_jwt(priv, key.kid, scopes=["admin:read"])  # no admin:write
    with pytest.raises(ValueError, match="admin:write"):
        await kg_admin_propose_template(_ctx(tok), verb="create", code="c", name="n")


async def test_propose_no_token_rejected(monkeypatch):
    priv = _gen()
    monkeypatch.setattr(admin_server, "get_admin_key", lambda: load_admin_key(_spki(priv)))
    with pytest.raises(ValueError, match="missing admin token"):
        await kg_admin_propose_template(_ctx(None), verb="create", code="c", name="n")


async def test_propose_admin_disabled_rejected(monkeypatch):
    monkeypatch.setattr(admin_server, "get_admin_key", lambda: None)
    with pytest.raises(ValueError, match="not configured"):
        await kg_admin_propose_template(_ctx("x"), verb="create", code="c", name="n")
