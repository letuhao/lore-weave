"""KM6 — /v1/kg/actions/{confirm,preview} router unit tests (auth boundary).

FastAPI dependency-override harness with fakes. Proves the §13.5 confirm flow:
decode (400/422) → authority re-check BEFORE claim (403 wrong-user, 501 admin) →
single-use claim (422 replay) → re-validate drift (422) → effect. Plus the
non-consuming preview.
"""

from __future__ import annotations

import time
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.clients.grant_client import GrantLevel
from app.config import settings
from app.deps import get_grant_client, get_projects_repo
from app.middleware.jwt_auth import get_current_user
from app.db.repositories.ontology_mutations import NeedsGlossaryError, SyncConflictError
from app.ontology.confirm import (
    ACTION_TOKEN_TTL_S,
    AUTH_ADMIN,
    AUTH_GRANT,
    DESC_ADOPT,
    DESC_SCHEMA_EDIT,
    DESC_SYNC,
    ActionClaims,
    mint_action_token,
)
from app.routers.public import kg_actions

pytestmark = pytest.mark.asyncio

_CALLER = uuid4()
_OTHER = uuid4()
_OWNER = uuid4()
_PROJECT = uuid4()
_BOOK = uuid4()
_SID = uuid4()


def _params(**over) -> dict:
    p = {
        "verb": "add", "level": "edge_type", "code": "WORSHIPS", "label": "Worships",
        "schema_id": str(_SID), "expected_schema_version": 3,
    }
    p.update(over)
    return p


def _token(*, user_id=_CALLER, project_id=_PROJECT, authority=AUTH_GRANT,
           descriptor=DESC_SCHEMA_EDIT, params=None, now=None, jti=None) -> str:
    return mint_action_token(
        settings.jwt_secret,
        ActionClaims(
            jti=jti or str(uuid4()), authority=authority, user_id=str(user_id),
            descriptor=descriptor, project_id=str(project_id), params=params or _params(),
        ),
        now if now is not None else time.time(),
    )


def _build(*, caller=_CALLER, meta=(_CALLER, _BOOK), grant=GrantLevel.OWNER,
           schema="default", claimed=True, triage=None):
    """Assemble an app + the fakes, with sensible owner==caller defaults (gate passes
    without consulting the grant client). Returns (app, mutations, tokens, schemas).
    Pass a configured `triage` AsyncMock to exercise the Lane-E triage descriptors."""
    app = FastAPI()
    app.include_router(kg_actions.router)

    gc = AsyncMock()
    gc.resolve_grant = AsyncMock(return_value=grant)
    projects = AsyncMock()
    projects.project_meta = AsyncMock(return_value=meta)
    schemas = AsyncMock()
    schema_obj = (
        SimpleNamespace(schema_id=_SID, schema_version=3) if schema == "default" else schema
    )
    schemas.active_project_schema = AsyncMock(return_value=schema_obj)
    mutations = AsyncMock()
    mutations.required_node_kinds = AsyncMock(return_value=[])  # adopt fail-open default
    tokens = AsyncMock()
    tokens.consume = AsyncMock(return_value=claimed)
    glossary = AsyncMock()
    glossary.get_book_ontology = AsyncMock(return_value=None)   # fail-open
    glossary.get_user_standards = AsyncMock(return_value=None)

    app.dependency_overrides[get_current_user] = lambda: caller
    app.dependency_overrides[get_grant_client] = lambda: gc
    app.dependency_overrides[get_projects_repo] = lambda: projects
    app.dependency_overrides[kg_actions.get_graph_schemas_repo] = lambda: schemas
    app.dependency_overrides[kg_actions.get_ontology_mutations_repo] = lambda: mutations
    app.dependency_overrides[kg_actions.get_action_token_repo] = lambda: tokens
    app.dependency_overrides[kg_actions.get_glossary_ontology_client] = lambda: glossary
    # KM5-M2 added a system-templates dep to confirm/preview; FastAPI resolves
    # every param regardless of descriptor, so the grant-path tests must stub it too.
    app.dependency_overrides[kg_actions.get_system_templates_repo] = lambda: AsyncMock()
    # Lane E added a triage-repo dep to confirm/preview — stub it for all paths;
    # tests that exercise the triage descriptors pass a configured fake.
    app.dependency_overrides[kg_actions.get_triage_repo] = lambda: triage or AsyncMock()
    return app, mutations, tokens, schemas


async def _post(app, path, json):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://t") as c:
        return await c.post(path, json=json)


# ── decode ────────────────────────────────────────────────────────────────
async def test_confirm_missing_token_400():
    app, *_ = _build()
    r = await _post(app, "/v1/kg/actions/confirm", {"confirm_token": "   "})
    assert r.status_code == 400


async def test_confirm_garbage_token_422():
    app, *_ = _build()
    r = await _post(app, "/v1/kg/actions/confirm", {"confirm_token": "not.a.token"})
    assert r.status_code == 422
    assert "invalid" in r.json()["detail"].lower()


async def test_confirm_expired_token_422():
    app, _m, tokens, _s = _build()
    stale = _token(now=time.time() - ACTION_TOKEN_TTL_S - 10)
    r = await _post(app, "/v1/kg/actions/confirm", {"confirm_token": stale})
    assert r.status_code == 422
    assert "expired" in r.json()["detail"].lower()
    tokens.consume.assert_not_awaited()  # never reached the claim


# ── authority (checked BEFORE the claim) ────────────────────────────────────
async def test_confirm_wrong_user_403_before_claim():
    app, _m, tokens, _s = _build(caller=_CALLER)
    # token minted for a DIFFERENT proposing user
    tok = _token(user_id=_OTHER)
    r = await _post(app, "/v1/kg/actions/confirm", {"confirm_token": tok})
    assert r.status_code == 403
    tokens.consume.assert_not_awaited()  # a stranger cannot burn the jti


async def test_confirm_admin_authority_503_when_admin_disabled():
    # KM5-M2: admin authority is wired, but with no ADMIN_JWT_PUBLIC_KEY_PEM the
    # default `get_admin_key` resolves to None → 503 (disabled), before any claim.
    # (The full admin path — RS256 re-verify, asub bind, effect — is exercised in
    # test_kg_actions_admin.py with a configured key.)
    app, _m, tokens, _s = _build()
    tok = _token(
        authority=AUTH_ADMIN, descriptor=kg_actions.DESC_SYSTEM_CREATE,
        params={"verb": "create", "code": "c", "name": "n"},
    )
    r = await _post(app, "/v1/kg/actions/confirm", {"confirm_token": tok})
    assert r.status_code == 503
    tokens.consume.assert_not_awaited()


async def test_confirm_manage_grant_required_grantee_under_tier_403():
    # caller != owner; grantee holds EDIT (< MANAGE) → 403, before claim.
    app, _m, tokens, _s = _build(
        caller=_CALLER, meta=(_OWNER, _BOOK), grant=GrantLevel.EDIT,
    )
    tok = _token(user_id=_CALLER)
    r = await _post(app, "/v1/kg/actions/confirm", {"confirm_token": tok})
    assert r.status_code == 403
    tokens.consume.assert_not_awaited()


# ── single-use + re-validate + effect ───────────────────────────────────────
async def test_confirm_happy_applies_edit():
    app, mutations, tokens, _s = _build()
    r = await _post(app, "/v1/kg/actions/confirm", {"confirm_token": _token()})
    assert r.status_code == 200, r.text
    assert r.json()["applied"] is True
    tokens.consume.assert_awaited_once()
    mutations.add_edge_type.assert_awaited_once()
    assert mutations.add_edge_type.await_args.kwargs["code"] == "WORSHIPS"


async def test_confirm_replay_422_already_confirmed():
    app, mutations, _t, _s = _build(claimed=False)  # jti already in the ledger
    r = await _post(app, "/v1/kg/actions/confirm", {"confirm_token": _token()})
    assert r.status_code == 422
    assert "already confirmed" in r.json()["detail"].lower()
    mutations.add_edge_type.assert_not_awaited()  # effect never runs on a replay


async def test_confirm_schema_version_drift_422():
    # the live schema moved to v99 since the token captured v3 → re-proposable.
    app, mutations, tokens, _s = _build(
        schema=SimpleNamespace(schema_id=_SID, schema_version=99),
    )
    r = await _post(app, "/v1/kg/actions/confirm", {"confirm_token": _token()})
    assert r.status_code == 422
    assert "changed" in r.json()["detail"].lower()
    # Fail-closed: the jti WAS consumed (claim precedes the effect) but no write ran.
    tokens.consume.assert_awaited_once()
    mutations.add_edge_type.assert_not_awaited()


async def test_confirm_schema_replaced_drift_422():
    app, mutations, _t, _s = _build(
        schema=SimpleNamespace(schema_id=uuid4(), schema_version=3),  # different schema_id
    )
    r = await _post(app, "/v1/kg/actions/confirm", {"confirm_token": _token()})
    assert r.status_code == 422
    mutations.add_edge_type.assert_not_awaited()


async def test_confirm_no_active_schema_drift_422():
    app, mutations, _t, _s = _build(schema=None)
    r = await _post(app, "/v1/kg/actions/confirm", {"confirm_token": _token()})
    assert r.status_code == 422
    mutations.add_edge_type.assert_not_awaited()


# ── preview (non-consuming) ─────────────────────────────────────────────────
async def test_preview_happy_non_consuming():
    app, _m, tokens, _s = _build()
    r = await _post(app, "/v1/kg/actions/preview", {"confirm_token": _token()})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["descriptor"] == DESC_SCHEMA_EDIT
    assert body["drift"] is False
    assert any(row["label"] == "will bump to" for row in body["preview_rows"])
    tokens.consume.assert_not_awaited()  # preview NEVER consumes


async def test_preview_flags_drift():
    app, *_ = _build(schema=SimpleNamespace(schema_id=_SID, schema_version=42))
    r = await _post(app, "/v1/kg/actions/preview", {"confirm_token": _token()})
    assert r.status_code == 200
    assert r.json()["drift"] is True


async def test_preview_wrong_user_403():
    app, *_ = _build()
    r = await _post(app, "/v1/kg/actions/preview", {"confirm_token": _token(user_id=_OTHER)})
    assert r.status_code == 403


# ── KM6-M2 — kg_adopt descriptor dispatch ───────────────────────────────────
def _adopt_token(*, user_id=_CALLER, project_id=_PROJECT, source_id=None, now=None) -> str:
    return mint_action_token(
        settings.jwt_secret,
        ActionClaims(
            jti=str(uuid4()), authority=AUTH_GRANT, user_id=str(user_id),
            descriptor=DESC_ADOPT, project_id=str(project_id),
            params={"source_schema_id": str(source_id or uuid4())},
        ),
        now if now is not None else time.time(),
    )


async def test_confirm_adopt_happy():
    app, mutations, tokens, _s = _build()
    mutations.adopt = AsyncMock(return_value=SimpleNamespace(
        schema=SimpleNamespace(schema_id=uuid4(), code="xianxia", name="Xianxia", schema_version=1),
        missing_optional=[],
    ))
    r = await _post(app, "/v1/kg/actions/confirm", {"confirm_token": _adopt_token()})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["adopted"] is True and body["name"] == "Xianxia"
    tokens.consume.assert_awaited_once()
    mutations.adopt.assert_awaited_once()


async def test_confirm_adopt_needs_glossary_422():
    app, mutations, _t, _s = _build()
    mutations.adopt = AsyncMock(side_effect=NeedsGlossaryError(["bloodline"], "book-1"))
    r = await _post(app, "/v1/kg/actions/confirm", {"confirm_token": _adopt_token()})
    assert r.status_code == 422
    detail = r.json()["detail"]
    assert detail["code"] == "KG_ADOPT_NEEDS_GLOSSARY"
    assert detail["needs_glossary"]["kinds"] == ["bloodline"]


async def test_preview_adopt_renders_template_summary():
    app, _m, tokens, schemas = _build(schema=None)  # no existing project schema
    src = uuid4()
    schemas.template_summary = AsyncMock(return_value={
        "schema_id": str(src), "code": "xianxia", "name": "Xianxia", "scope": "system",
        "edge_type_count": 7, "node_kind_count": 5, "fact_type_count": 3,
    })
    r = await _post(app, "/v1/kg/actions/preview", {"confirm_token": _adopt_token(source_id=src)})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["descriptor"] == DESC_ADOPT
    assert body["blocked"] is False
    assert any("Xianxia" in str(row["value"]) for row in body["preview_rows"])
    tokens.consume.assert_not_awaited()  # preview never consumes


async def test_preview_adopt_missing_template():
    app, _m, _t, schemas = _build()
    schemas.template_summary = AsyncMock(return_value=None)
    r = await _post(app, "/v1/kg/actions/preview", {"confirm_token": _adopt_token()})
    assert r.status_code == 200
    assert r.json()["blocked"] is True


# ── KM6-M3 — kg_sync_apply descriptor dispatch ──────────────────────────────
def _sync_token(*, user_id=_CALLER, project_id=_PROJECT, base_hash="h0", decisions=None) -> str:
    return mint_action_token(
        settings.jwt_secret,
        ActionClaims(
            jti=str(uuid4()), authority=AUTH_GRANT, user_id=str(user_id),
            descriptor=DESC_SYNC, project_id=str(project_id),
            params={"base_source_hash": base_hash, "decisions": decisions or []},
        ),
        time.time(),
    )


async def test_confirm_sync_happy():
    app, mutations, tokens, _s = _build()  # default schema present
    mutations.sync_apply = AsyncMock(return_value={"applied": 3, "schema_version": 5})
    r = await _post(app, "/v1/kg/actions/confirm", {"confirm_token": _sync_token(
        decisions=[{"node_type": "edge_type", "code": "X", "choice": "take_theirs"}])})
    assert r.status_code == 200, r.text
    tokens.consume.assert_awaited_once()
    mutations.sync_apply.assert_awaited_once()


async def test_confirm_sync_drift_422():
    app, mutations, tokens, _s = _build()
    mutations.sync_apply = AsyncMock(side_effect=SyncConflictError())
    r = await _post(app, "/v1/kg/actions/confirm", {"confirm_token": _sync_token()})
    assert r.status_code == 422
    assert "moved" in r.json()["detail"].lower()
    tokens.consume.assert_awaited_once()  # jti spent (fail-closed), no apply succeeded


async def test_confirm_sync_no_schema_422():
    app, mutations, _t, _s = _build(schema=None)  # project never adopted
    r = await _post(app, "/v1/kg/actions/confirm", {"confirm_token": _sync_token()})
    assert r.status_code == 422
    mutations.sync_apply.assert_not_awaited()


async def test_preview_sync_renders_diff():
    app, mutations, tokens, _s = _build()
    mutations.sync_diff = AsyncMock(return_value={
        "source_ref": "system:abc", "source_hash_current": "h9", "has_updates": True, "changes": [],
    })
    r = await _post(app, "/v1/kg/actions/preview", {"confirm_token": _sync_token(
        base_hash="h0", decisions=[{"node_type": "edge_type", "code": "X", "choice": "take_theirs"}])})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["descriptor"] == DESC_SYNC
    assert body["drift"] is True  # base_hash h0 != current h9
    tokens.consume.assert_not_awaited()


# ── E2 — kg_triage_proposed_edge descriptor dispatch ────────────────────────
def _pe_token(*, user_id=_CALLER, project_id=_PROJECT, triage_id=None, now=None) -> str:
    from app.ontology.confirm import DESC_TRIAGE_PROPOSED_EDGE

    return mint_action_token(
        settings.jwt_secret,
        ActionClaims(
            jti=str(uuid4()), authority=AUTH_GRANT, user_id=str(user_id),
            descriptor=DESC_TRIAGE_PROPOSED_EDGE, project_id=str(project_id),
            params={"triage_id": str(triage_id or uuid4())},
        ),
        now if now is not None else time.time(),
    )


def _pending_proposed_edge(tid):
    from datetime import datetime, timezone

    from app.db.ontology_models import TriageItem

    return TriageItem(
        triage_id=tid, user_id=_OWNER, project_id=str(_PROJECT), source={},
        item_type="proposed_edge",
        payload={"source_entity_id": "a", "target_entity_id": "b", "predicate": "ALLIES"},
        signature="propose_edge:ALLIES:a->b", status="pending", resolution=None,
        schema_version=None, created_at=datetime.now(timezone.utc),
        resolved_at=None, resolved_by=None,
    )


async def test_confirm_proposed_edge_happy(monkeypatch):
    tid = uuid4()
    triage = AsyncMock()
    triage.get_item = AsyncMock(return_value=_pending_proposed_edge(tid))
    triage.resolve_item = AsyncMock(return_value=True)
    app, _m, tokens, _s = _build(triage=triage)

    # Stub the central write path so no real Neo4j is needed.
    from app.ontology import triage_apply, triage_proposed_edge_effect

    monkeypatch.setattr(triage_apply, "create_relation", AsyncMock(return_value=object()))

    class _FakeSession:
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False

    monkeypatch.setattr(triage_proposed_edge_effect, "neo4j_session", lambda: _FakeSession(), raising=False)
    # the effect imports neo4j_session lazily from app.db.neo4j — patch there too.
    import app.db.neo4j as _neo4j
    monkeypatch.setattr(_neo4j, "neo4j_session", lambda: _FakeSession())

    r = await _post(app, "/v1/kg/actions/confirm", {"confirm_token": _pe_token(triage_id=tid)})
    assert r.status_code == 200, r.text
    assert r.json()["applied"] is True
    tokens.consume.assert_awaited_once()
    triage.resolve_item.assert_awaited_once()


async def test_confirm_proposed_edge_drift_already_resolved_422(monkeypatch):
    tid = uuid4()
    item = _pending_proposed_edge(tid)
    item = item.model_copy(update={"status": "resolved"})
    triage = AsyncMock()
    triage.get_item = AsyncMock(return_value=item)
    app, _m, tokens, _s = _build(triage=triage)
    r = await _post(app, "/v1/kg/actions/confirm", {"confirm_token": _pe_token(triage_id=tid)})
    assert r.status_code == 422
    tokens.consume.assert_awaited_once()  # jti spent (fail-closed), no write


async def test_confirm_proposed_edge_missing_404(monkeypatch):
    tid = uuid4()
    triage = AsyncMock()
    triage.get_item = AsyncMock(return_value=None)
    app, *_ = _build(triage=triage)
    r = await _post(app, "/v1/kg/actions/confirm", {"confirm_token": _pe_token(triage_id=tid)})
    assert r.status_code == 404


async def test_confirm_proposed_edge_wrong_user_403():
    app, _m, tokens, _s = _build()
    r = await _post(app, "/v1/kg/actions/confirm",
                    {"confirm_token": _pe_token(user_id=_OTHER)})
    assert r.status_code == 403
    tokens.consume.assert_not_awaited()


async def test_preview_proposed_edge_renders_edge(monkeypatch):
    tid = uuid4()
    triage = AsyncMock()
    triage.get_item = AsyncMock(return_value=_pending_proposed_edge(tid))
    app, _m, tokens, _s = _build(triage=triage)
    r = await _post(app, "/v1/kg/actions/preview", {"confirm_token": _pe_token(triage_id=tid)})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["descriptor"] == "kg_triage_proposed_edge"
    assert body["drift"] is False
    assert any(row["label"] == "predicate" for row in body["preview_rows"])
    tokens.consume.assert_not_awaited()


# ── E3 — kg_triage_schema_write descriptor dispatch ─────────────────────────
def _sw_token(*, user_id=_CALLER, project_id=_PROJECT, action="add_to_vocab",
              schema_id=None, version=3, now=None) -> str:
    from app.ontology.confirm import DESC_TRIAGE_SCHEMA_WRITE

    return mint_action_token(
        settings.jwt_secret,
        ActionClaims(
            jti=str(uuid4()), authority=AUTH_GRANT, user_id=str(user_id),
            descriptor=DESC_TRIAGE_SCHEMA_WRITE, project_id=str(project_id),
            params={
                "action": action, "signature": "drive:curiosity",
                "schema_id": str(schema_id or _SID), "expected_schema_version": version,
                "code": "curiosity", "label": "Curiosity", "set_code": "drive",
                "add_kinds": [],
            },
        ),
        now if now is not None else time.time(),
    )


async def test_confirm_schema_write_add_to_vocab_happy():
    triage = AsyncMock()
    triage.stamp_schema_version = AsyncMock(return_value=2)
    app, mutations, tokens, _s = _build(triage=triage)  # default schema v3
    # apply bumps to v4 → active_project_schema returns v4 after the mutation.
    mutations.add_vocab_value = AsyncMock(return_value={})
    schemas = app.dependency_overrides[kg_actions.get_graph_schemas_repo]()
    schemas.active_project_schema = AsyncMock(side_effect=[
        SimpleNamespace(schema_id=_SID, schema_version=3),  # _revalidate
        SimpleNamespace(schema_id=_SID, schema_version=4),  # after-bump read
    ])
    r = await _post(app, "/v1/kg/actions/confirm", {"confirm_token": _sw_token()})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["applied"] is True
    assert body["schema_version"] == 4
    tokens.consume.assert_awaited_once()
    mutations.add_vocab_value.assert_awaited_once()
    triage.stamp_schema_version.assert_awaited_once()


async def test_confirm_schema_write_drift_422():
    triage = AsyncMock()
    app, mutations, tokens, _s = _build(
        triage=triage, schema=SimpleNamespace(schema_id=_SID, schema_version=99),
    )
    r = await _post(app, "/v1/kg/actions/confirm", {"confirm_token": _sw_token(version=3)})
    assert r.status_code == 422
    tokens.consume.assert_awaited_once()  # jti spent, no mutation
    mutations.add_vocab_value.assert_not_awaited()


async def test_confirm_schema_write_set_multi_active_calls_repo():
    triage = AsyncMock()
    triage.stamp_schema_version = AsyncMock(return_value=1)
    app, mutations, _t, _s = _build(triage=triage)
    mutations.set_edge_cardinality = AsyncMock(return_value={})
    schemas = app.dependency_overrides[kg_actions.get_graph_schemas_repo]()
    schemas.active_project_schema = AsyncMock(side_effect=[
        SimpleNamespace(schema_id=_SID, schema_version=3),
        SimpleNamespace(schema_id=_SID, schema_version=4),
    ])
    r = await _post(app, "/v1/kg/actions/confirm",
                    {"confirm_token": _sw_token(action="set_multi_active")})
    assert r.status_code == 200, r.text
    mutations.set_edge_cardinality.assert_awaited_once()
    assert mutations.set_edge_cardinality.await_args.kwargs["cardinality"] == "multi_active"


async def test_preview_schema_write_renders_bump():
    triage = AsyncMock()
    app, *_ = _build(triage=triage)  # default schema v3
    r = await _post(app, "/v1/kg/actions/preview", {"confirm_token": _sw_token()})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["descriptor"] == "kg_triage_schema_write"
    assert body["drift"] is False
    assert any(row["label"] == "will bump to" for row in body["preview_rows"])


async def test_confirm_schema_write_wrong_user_403():
    app, _m, tokens, _s = _build()
    r = await _post(app, "/v1/kg/actions/confirm", {"confirm_token": _sw_token(user_id=_OTHER)})
    assert r.status_code == 403
    tokens.consume.assert_not_awaited()


async def test_every_live_descriptor_is_dispatched():
    """Tripwire (/review-impl LOW-1): the codec's live-descriptor set must EXACTLY
    match the descriptors the confirm/preview router dispatches. If someone adds a
    descriptor to `_LIVE_DESCRIPTORS` but forgets a dispatch branch, a verified token
    would consume its jti then 422 'unknown action' — this test fails first instead.
    Adding a descriptor MUST update both the codec set and this assertion (+ branch)."""
    from app.ontology import confirm as _confirm

    assert _confirm._LIVE_DESCRIPTORS == {
        DESC_SCHEMA_EDIT, _confirm.DESC_ADOPT, _confirm.DESC_SYNC,
        _confirm.DESC_SYSTEM_CREATE, _confirm.DESC_SYSTEM_PATCH, _confirm.DESC_SYSTEM_DELETE,
        _confirm.DESC_TRIAGE_PROPOSED_EDGE, _confirm.DESC_TRIAGE_SCHEMA_WRITE,
        _confirm.DESC_BUILD_GRAPH,
    }, (
        "a new live descriptor must also get a confirm + preview dispatch branch in "
        "kg_actions.py and be added here"
    )
