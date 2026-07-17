"""LH unit tests -- triage router (grant-gating, needs_glossary hand-off shape,
422 invalid-action) + the triage_apply Neo4j re-apply seam.

Mocks TriageRepo + the grant primitives (project_meta_dep / get_grant_client /
get_current_user) so the routes run without a DB or book-service. The
grouping/signature batch logic itself is covered live in
tests/integration/db/test_kg_triage.py.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.clients.grant_client import GrantLevel
from app.db.ontology_models import TriageItem
from app.db.repositories.triage import TriageGroup

_OWNER = uuid4()
_PROJECT = uuid4()
_BOOK = uuid4()


@pytest.fixture(autouse=True)
def _clear_overrides():
    from app.main import app
    yield
    app.dependency_overrides.clear()


def _group(signature="drive:curiosity", item_type="unknown_vocab_value", count=3):
    return TriageGroup(
        signature=signature, item_type=item_type, count=count, status="pending",
        sample_payload={"value": "curiosity"},
        suggested_actions=["map", "add_to_vocab", "dismiss"],
    )


def _item(item_type="unknown_vocab_value", signature="drive:curiosity", payload=None):
    from datetime import datetime, timezone

    return TriageItem(
        triage_id=uuid4(), user_id=_OWNER, project_id=str(_PROJECT),
        source={}, item_type=item_type, payload=payload or {}, signature=signature,
        status="pending", resolution=None, schema_version=None,
        created_at=datetime.now(timezone.utc), resolved_at=None, resolved_by=None,
    )


def _make_client(
    *, caller=_OWNER, meta=(_OWNER, _BOOK), grant_level=GrantLevel.OWNER, repo=None
):
    """Override the grant primitives + repo. ``meta`` is (owner, book_id) or None;
    ``grant_level`` is what the (mocked) book-service returns for a non-owner caller."""
    from app.main import app
    from app.middleware.jwt_auth import get_current_user
    from app.auth.grant_deps import project_meta_dep
    from app.deps import get_grant_client
    from app.routers.public.triage import (
        get_triage_repo,
        get_graph_schemas_repo,
        get_ontology_mutations_repo,
    )

    repo = repo or MagicMock()

    grant = MagicMock()
    grant.resolve_grant = AsyncMock(return_value=grant_level)

    # S-05 — resolve_triage now DI's the schema + mutations repos (for the schema
    # write). Override them with mocks so unit tests don't hit get_knowledge_pool.
    # active_project_schema defaults to None (non-schema actions never call it;
    # schema-write tests override it to a real schema).
    schemas = MagicMock()
    schemas.active_project_schema = AsyncMock(return_value=None)
    mutations = MagicMock()

    app.dependency_overrides[get_current_user] = lambda: caller
    app.dependency_overrides[project_meta_dep] = lambda: meta
    app.dependency_overrides[get_grant_client] = lambda: grant
    app.dependency_overrides[get_triage_repo] = lambda: repo
    app.dependency_overrides[get_graph_schemas_repo] = lambda: schemas
    app.dependency_overrides[get_ontology_mutations_repo] = lambda: mutations
    return TestClient(app, raise_server_exceptions=False), repo, grant


# ── GET list (View-gated) ────────────────────────────────────────────────────
def test_list_returns_groups():
    repo = MagicMock()
    repo.list_grouped = AsyncMock(return_value=([_group()], False))
    client, _, _ = _make_client(repo=repo)
    r = client.get(f"/v1/kg/projects/{_PROJECT}/triage")
    assert r.status_code == 200
    body = r.json()
    assert len(body["groups"]) == 1
    g = body["groups"][0]
    assert g["signature"] == "drive:curiosity"
    assert g["count"] == 3
    assert g["suggested_actions"] == ["map", "add_to_vocab", "dismiss"]
    assert body["next_cursor"] is None


def test_list_paginates_with_cursor():
    repo = MagicMock()
    repo.list_grouped = AsyncMock(return_value=([_group()], True))  # has_more
    client, _, _ = _make_client(repo=repo)
    r = client.get(f"/v1/kg/projects/{_PROJECT}/triage?limit=1")
    assert r.status_code == 200
    assert r.json()["next_cursor"] == "1"


def test_list_cross_tenant_non_grantee_404():
    """A non-owner with NO grant on the book -> 404 (no existence oracle)."""
    repo = MagicMock()
    repo.list_grouped = AsyncMock(return_value=([], False))
    other = uuid4()
    client, _, _ = _make_client(caller=other, grant_level=GrantLevel.NONE, repo=repo)
    r = client.get(f"/v1/kg/projects/{_PROJECT}/triage")
    assert r.status_code == 404
    repo.list_grouped.assert_not_called()  # gate denied before repo


def test_list_missing_project_404():
    client, repo, _ = _make_client(meta=None)
    r = client.get(f"/v1/kg/projects/{_PROJECT}/triage")
    assert r.status_code == 404


# ── GET per-item drill-in (S-05, View-gated) ─────────────────────────────────
def test_list_items_returns_pending_items():
    repo = MagicMock()
    repo.list_pending_for_signature = AsyncMock(return_value=[_item(), _item()])
    client, _, _ = _make_client(repo=repo)
    r = client.get(f"/v1/kg/projects/{_PROJECT}/triage/drive:curiosity/items")
    assert r.status_code == 200, r.json()
    body = r.json()
    assert len(body["items"]) == 2
    assert body["items"][0]["item_type"] == "unknown_vocab_value"
    assert "triage_id" in body["items"][0]


def test_list_items_cross_tenant_non_grantee_404():
    """A non-owner with NO grant -> 404 in the View gate before the repo runs."""
    repo = MagicMock()
    repo.list_pending_for_signature = AsyncMock(return_value=[])
    other = uuid4()
    client, _, _ = _make_client(caller=other, grant_level=GrantLevel.NONE, repo=repo)
    r = client.get(f"/v1/kg/projects/{_PROJECT}/triage/sig-x/items")
    assert r.status_code == 404
    repo.list_pending_for_signature.assert_not_called()


# ── POST resolve (KG-local Edit-gated) ───────────────────────────────────────
def test_resolve_kg_local_marks_resolved():
    repo = MagicMock()
    repo.list_pending_for_signature = AsyncMock(return_value=[_item()])
    repo.resolve_signature = AsyncMock(return_value=3)
    client, _, _ = _make_client(repo=repo)
    r = client.post(
        f"/v1/kg/projects/{_PROJECT}/triage/drive:curiosity/resolve",
        json={"action": "map", "params": {"map_to": "uncover_truth"}},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "resolved"
    assert body["affected"] == 3
    # repo called with new_status='resolved'
    _, kwargs = repo.resolve_signature.call_args
    assert kwargs["new_status"] == "resolved"
    assert kwargs["user_id"] == _OWNER


@patch("app.routers.public.triage.apply_triage_schema_write", new_callable=AsyncMock)
def test_resolve_add_to_schema_writes_and_resolves(mock_apply):
    """S-05 — add_to_schema (Manage) now WRITES the schema via the resolve route:
    derive code from the parked predicate, apply the mutation, then mark resolved
    with the new schema_version (no more 'records intent')."""
    from types import SimpleNamespace
    from app.routers.public.triage import get_graph_schemas_repo

    repo = MagicMock()
    repo.list_pending_for_signature = AsyncMock(return_value=[
        _item(item_type="unknown_edge_type", signature="edge:rules_over",
              payload={"predicate": "rules_over"}),
    ])
    repo.resolve_signature = AsyncMock(return_value=2)
    mock_apply.return_value = {"applied": True, "schema_version": 4}
    schemas = MagicMock()
    schemas.active_project_schema = AsyncMock(
        return_value=SimpleNamespace(schema_id=uuid4(), schema_version=3)
    )
    client, _, _ = _make_client(repo=repo)
    from app.main import app
    app.dependency_overrides[get_graph_schemas_repo] = lambda: schemas
    r = client.post(
        f"/v1/kg/projects/{_PROJECT}/triage/edge:rules_over/resolve",
        json={"action": "add_to_schema"},
    )
    assert r.status_code == 200, r.json()
    assert r.json()["schema_version"] == 4
    mock_apply.assert_awaited_once()
    # code was DERIVED from the parked payload predicate (one-click, no form)
    params = mock_apply.call_args.args[4]
    assert params.action == "add_to_schema" and params.code == "rules_over"
    # marked resolved WITH the new version
    _, kwargs = repo.resolve_signature.call_args
    assert kwargs["new_status"] == "resolved" and kwargs["schema_version"] == 4


def test_resolve_add_to_schema_no_active_schema_422():
    """No adopted schema → 422 BEFORE anything is marked resolved."""
    from app.routers.public.triage import get_graph_schemas_repo

    repo = MagicMock()
    repo.list_pending_for_signature = AsyncMock(return_value=[
        _item(item_type="unknown_edge_type", signature="edge:x", payload={"predicate": "x"}),
    ])
    repo.resolve_signature = AsyncMock()
    schemas = MagicMock()
    schemas.active_project_schema = AsyncMock(return_value=None)
    client, _, _ = _make_client(repo=repo)
    from app.main import app
    app.dependency_overrides[get_graph_schemas_repo] = lambda: schemas
    r = client.post(
        f"/v1/kg/projects/{_PROJECT}/triage/edge:x/resolve",
        json={"action": "add_to_schema"},
    )
    assert r.status_code == 422
    repo.resolve_signature.assert_not_called()


def test_resolve_invalid_action_for_item_type_422():
    repo = MagicMock()
    repo.list_pending_for_signature = AsyncMock(return_value=[_item(item_type="unknown_vocab_value")])
    repo.resolve_signature = AsyncMock()
    client, _, _ = _make_client(repo=repo)
    # promote_to_glossary_kind is only valid for unknown_node_kind
    r = client.post(
        f"/v1/kg/projects/{_PROJECT}/triage/drive:curiosity/resolve",
        json={"action": "promote_to_glossary_kind"},
    )
    assert r.status_code == 422
    repo.resolve_signature.assert_not_called()


def test_resolve_unknown_signature_404():
    repo = MagicMock()
    repo.list_pending_for_signature = AsyncMock(return_value=[])
    client, _, _ = _make_client(repo=repo)
    r = client.post(
        f"/v1/kg/projects/{_PROJECT}/triage/nope/resolve",
        json={"action": "map"},
    )
    assert r.status_code == 404


# ── POST resolve (glossary hand-off -> pending_glossary + needs_glossary) ────
def test_resolve_promote_returns_needs_glossary():
    repo = MagicMock()
    repo.list_pending_for_signature = AsyncMock(
        return_value=[_item(item_type="unknown_node_kind", signature="kind:bloodline",
                            payload={"proposed_kind": "bloodline"})]
    )
    repo.resolve_signature = AsyncMock(return_value=2)
    client, _, _ = _make_client(repo=repo)
    r = client.post(
        f"/v1/kg/projects/{_PROJECT}/triage/kind:bloodline/resolve",
        json={"action": "promote_to_glossary_kind"},
    )
    assert r.status_code == 422  # contract: action needs glossary work first
    body = r.json()
    assert body["status"] == "pending_glossary"
    assert body["affected"] == 2
    assert body["needs_glossary"]["kinds"] == ["bloodline"]
    assert body["needs_glossary"]["book_id"] == str(_BOOK)
    _, kwargs = repo.resolve_signature.call_args
    assert kwargs["new_status"] == "pending_glossary"


def test_resolve_promote_explicit_kinds_param_wins():
    repo = MagicMock()
    repo.list_pending_for_signature = AsyncMock(
        return_value=[_item(item_type="unknown_node_kind", signature="kind:x")]
    )
    repo.resolve_signature = AsyncMock(return_value=1)
    client, _, _ = _make_client(repo=repo)
    r = client.post(
        f"/v1/kg/projects/{_PROJECT}/triage/kind:x/resolve",
        json={"action": "demote_to_attribute", "params": {"kinds": ["realm_rank"]}},
    )
    assert r.status_code == 422
    assert r.json()["needs_glossary"]["kinds"] == ["realm_rank"]


# ── POST resolve (schema-mutating -> Manage-gated) ───────────────────────────
def test_resolve_schema_mutating_requires_manage():
    """An EDIT-only grantee attempting add_to_vocab -> 403."""
    repo = MagicMock()
    repo.list_pending_for_signature = AsyncMock(return_value=[_item()])
    repo.resolve_signature = AsyncMock(return_value=1)
    other = uuid4()
    client, _, _ = _make_client(caller=other, grant_level=GrantLevel.EDIT, repo=repo)
    r = client.post(
        f"/v1/kg/projects/{_PROJECT}/triage/drive:curiosity/resolve",
        json={"action": "add_to_vocab", "params": {"value": "curiosity"}},
    )
    assert r.status_code == 403
    repo.resolve_signature.assert_not_called()


@patch("app.routers.public.triage.apply_triage_schema_write", new_callable=AsyncMock)
def test_resolve_schema_mutating_manage_grantee_ok(mock_apply):
    """A MANAGE grantee's add_to_vocab now WRITES the schema (S-05) — the write runs
    for the direct human path, and the response carries the new schema_version
    (no longer None / 'intent recorded'). set_code + code derive from the payload."""
    from types import SimpleNamespace
    from app.routers.public.triage import get_graph_schemas_repo

    repo = MagicMock()
    repo.list_pending_for_signature = AsyncMock(return_value=[
        _item(item_type="unknown_vocab_value", signature="drive:curiosity",
              payload={"set_code": "drive", "value": "curiosity"}),
    ])
    repo.resolve_signature = AsyncMock(return_value=1)
    mock_apply.return_value = {"applied": True, "schema_version": 7}
    other = uuid4()
    client, _, _ = _make_client(caller=other, grant_level=GrantLevel.MANAGE, repo=repo)
    from app.main import app
    schemas = MagicMock()
    schemas.active_project_schema = AsyncMock(
        return_value=SimpleNamespace(schema_id=uuid4(), schema_version=6)
    )
    app.dependency_overrides[get_graph_schemas_repo] = lambda: schemas
    r = client.post(
        f"/v1/kg/projects/{_PROJECT}/triage/drive:curiosity/resolve",
        json={"action": "add_to_vocab"},
    )
    assert r.status_code == 200, r.json()
    assert r.json()["schema_version"] == 7
    params = mock_apply.call_args.args[4]
    assert params.set_code == "drive" and params.code == "curiosity"


# ── POST dismiss (Edit-gated) ────────────────────────────────────────────────
def test_dismiss_ok_204():
    repo = MagicMock()
    repo.dismiss = AsyncMock(return_value=True)
    client, _, _ = _make_client(repo=repo)
    tid = uuid4()
    r = client.post(f"/v1/kg/projects/{_PROJECT}/triage/{tid}/dismiss")
    assert r.status_code == 204


def test_dismiss_not_found_404():
    repo = MagicMock()
    repo.dismiss = AsyncMock(return_value=False)
    client, _, _ = _make_client(repo=repo)
    tid = uuid4()
    r = client.post(f"/v1/kg/projects/{_PROJECT}/triage/{tid}/dismiss")
    assert r.status_code == 404


def test_dismiss_cross_tenant_non_grantee_404():
    repo = MagicMock()
    repo.dismiss = AsyncMock(return_value=False)
    other = uuid4()
    client, _, _ = _make_client(caller=other, grant_level=GrantLevel.NONE, repo=repo)
    tid = uuid4()
    r = client.post(f"/v1/kg/projects/{_PROJECT}/triage/{tid}/dismiss")
    assert r.status_code == 404
    repo.dismiss.assert_not_called()


# ── triage_apply Neo4j re-apply seam ─────────────────────────────────────────
@pytest.mark.asyncio
async def test_apply_resolved_reapply_action_delegates_to_writer():
    from app.ontology.triage_apply import apply_resolved

    writer = MagicMock()
    writer.reapply = AsyncMock()
    item = _item()
    did = await apply_resolved(item, "map", {"map_to": "uncover_truth"}, writer=writer)
    assert did is True
    writer.reapply.assert_awaited_once()
    _, kwargs = writer.reapply.call_args
    assert kwargs["action"] == "map"


@pytest.mark.asyncio
async def test_apply_resolved_no_reapply_for_dismiss():
    from app.ontology.triage_apply import apply_resolved

    writer = MagicMock()
    writer.reapply = AsyncMock()
    did = await apply_resolved(_item(), "dismiss", {}, writer=writer)
    assert did is False
    writer.reapply.assert_not_called()


@pytest.mark.asyncio
async def test_apply_resolved_default_writer_raises_not_implemented_seam():
    """D-KG-LH-NEO4J-REAPPLY: the un-wired seam is LOUD, never silently faked."""
    from app.ontology.triage_apply import apply_resolved

    with pytest.raises(NotImplementedError):
        await apply_resolved(_item(), "map", {})


@pytest.mark.asyncio
async def test_apply_resolved_glossary_handoff_is_no_reapply():
    from app.ontology.triage_apply import apply_resolved

    writer = MagicMock()
    writer.reapply = AsyncMock()
    did = await apply_resolved(_item(), "promote_to_glossary_kind", {}, writer=writer)
    assert did is False
    writer.reapply.assert_not_called()


# ── E1 — Neo4jReapplyWriter dispatch (over a spied create_relation) ───────────
def _edge_item(item_type="proposed_edge", **payload):
    base = {
        "source_entity_id": "ent-a",
        "target_entity_id": "ent-b",
        "predicate": "ALLIES",
    }
    base.update(payload)
    return _item(item_type=item_type, signature="propose_edge:ALLIES:ent-a->ent-b",
                 payload=base)


@pytest.mark.asyncio
async def test_neo4j_reapply_writer_map_writes_edge(monkeypatch):
    from app.ontology import triage_apply

    spy = AsyncMock(return_value=object())  # non-None → write succeeded
    monkeypatch.setattr(triage_apply, "create_relation", spy)
    writer = triage_apply.Neo4jReapplyWriter(object(), owner_user_id=str(_OWNER))
    await writer.reapply(_edge_item(), action="map", params={})
    spy.assert_awaited_once()
    kwargs = spy.await_args.kwargs
    assert kwargs["user_id"] == str(_OWNER)  # owner-scoped, not caller
    assert kwargs["subject_id"] == "ent-a"
    assert kwargs["object_id"] == "ent-b"
    assert kwargs["predicate"] == "ALLIES"
    assert kwargs["cardinality"] is None  # map ≠ single_active


@pytest.mark.asyncio
async def test_neo4j_reapply_writer_close_previous_uses_single_active(monkeypatch):
    from app.ontology import triage_apply

    spy = AsyncMock(return_value=object())
    monkeypatch.setattr(triage_apply, "create_relation", spy)
    writer = triage_apply.Neo4jReapplyWriter(object(), owner_user_id=str(_OWNER))
    await writer.reapply(
        _edge_item(item_type="edge_cardinality_conflict"),
        action="close_previous", params={},
    )
    assert spy.await_args.kwargs["cardinality"] == "single_active"


@pytest.mark.asyncio
async def test_neo4j_reapply_writer_re_target_overrides_object(monkeypatch):
    from app.ontology import triage_apply

    spy = AsyncMock(return_value=object())
    monkeypatch.setattr(triage_apply, "create_relation", spy)
    writer = triage_apply.Neo4jReapplyWriter(object(), owner_user_id=str(_OWNER))
    await writer.reapply(
        _edge_item(item_type="edge_kind_mismatch"),
        action="re_target", params={"target_entity_id": "ent-c"},
    )
    assert spy.await_args.kwargs["object_id"] == "ent-c"


@pytest.mark.asyncio
async def test_neo4j_reapply_writer_map_recodes_predicate(monkeypatch):
    from app.ontology import triage_apply

    spy = AsyncMock(return_value=object())
    monkeypatch.setattr(triage_apply, "create_relation", spy)
    writer = triage_apply.Neo4jReapplyWriter(object(), owner_user_id=str(_OWNER))
    await writer.reapply(_edge_item(), action="map", params={"map_to": "FRIENDS_WITH"})
    assert spy.await_args.kwargs["predicate"] == "FRIENDS_WITH"


@pytest.mark.asyncio
async def test_neo4j_reapply_writer_handles_extraction_payload_keys(monkeypatch):
    """Off-schema extraction parks use subject_id/object_id (not source/target)."""
    from app.ontology import triage_apply

    spy = AsyncMock(return_value=object())
    monkeypatch.setattr(triage_apply, "create_relation", spy)
    item = _item(item_type="unknown_edge_type", signature="edge:ALLIES",
                 payload={"subject_id": "s1", "object_id": "o1", "predicate": "ALLIES"})
    writer = triage_apply.Neo4jReapplyWriter(object(), owner_user_id=str(_OWNER))
    await writer.reapply(item, action="map", params={})
    kwargs = spy.await_args.kwargs
    assert kwargs["subject_id"] == "s1" and kwargs["object_id"] == "o1"


@pytest.mark.asyncio
async def test_neo4j_reapply_writer_missing_fields_raises(monkeypatch):
    from app.ontology import triage_apply
    from app.ontology.triage_apply import TriageApplyError

    spy = AsyncMock(return_value=object())
    monkeypatch.setattr(triage_apply, "create_relation", spy)
    item = _item(item_type="unknown_edge_type", payload={"predicate": "ALLIES"})  # no ids
    writer = triage_apply.Neo4jReapplyWriter(object(), owner_user_id=str(_OWNER))
    with pytest.raises(TriageApplyError):
        await writer.reapply(item, action="map", params={})
    spy.assert_not_awaited()  # never reached the write


@pytest.mark.asyncio
async def test_neo4j_reapply_writer_missing_endpoint_raises(monkeypatch):
    from app.ontology import triage_apply
    from app.ontology.triage_apply import TriageApplyError

    spy = AsyncMock(return_value=None)  # create_relation → endpoint absent
    monkeypatch.setattr(triage_apply, "create_relation", spy)
    writer = triage_apply.Neo4jReapplyWriter(object(), owner_user_id=str(_OWNER))
    with pytest.raises(TriageApplyError):
        await writer.reapply(_edge_item(), action="map", params={})


# ── E1 — the resolve route injects the REAL writer, not NotWired ──────────────
def test_resolve_map_injects_real_writer_not_notwired(monkeypatch):
    """A `map` resolve must drive the real re-apply batch (owner-scoped), never the
    un-wired seam. We spy `_reapply_batch` to assert it ran with the resolved owner
    + the pending list (the Neo4j write itself is covered by the writer unit + the
    live integration test)."""
    from app.routers.public import triage as triage_router

    seen = {}

    async def _spy_reapply(owner, action, params, pending):
        seen["owner"] = owner
        seen["action"] = action
        seen["count"] = len(pending)

    monkeypatch.setattr(triage_router, "_reapply_batch", _spy_reapply)

    repo = MagicMock()
    # map is valid for unknown_edge_type (its payload carries subject/object/pred).
    repo.list_pending_for_signature = AsyncMock(
        return_value=[
            _edge_item(item_type="unknown_edge_type"),
            _edge_item(item_type="unknown_edge_type"),
        ]
    )
    repo.resolve_signature = AsyncMock(return_value=2)
    client, _, _ = _make_client(repo=repo)
    r = client.post(
        f"/v1/kg/projects/{_PROJECT}/triage/edge:ALLIES/resolve",
        json={"action": "map", "params": {}},
    )
    assert r.status_code == 200, r.text
    assert seen["action"] == "map"
    assert seen["owner"] == _OWNER
    assert seen["count"] == 2


def test_resolve_dismiss_does_not_reapply(monkeypatch):
    from app.routers.public import triage as triage_router

    called = {"n": 0}

    async def _spy_reapply(owner, action, params, pending):
        called["n"] += 1

    monkeypatch.setattr(triage_router, "_reapply_batch", _spy_reapply)
    repo = MagicMock()
    # drop_edge is valid for edge_kind_mismatch.
    repo.list_pending_for_signature = AsyncMock(
        return_value=[_edge_item(item_type="edge_kind_mismatch")]
    )
    repo.resolve_signature = AsyncMock(return_value=1)
    client, _, _ = _make_client(repo=repo)
    r = client.post(
        f"/v1/kg/projects/{_PROJECT}/triage/edge_kind:LOVER_OF/resolve",
        json={"action": "drop_edge", "params": {}},
    )
    assert r.status_code == 200, r.text
    assert called["n"] == 0  # drop_edge is not a REAPPLY action
