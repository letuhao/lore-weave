"""LH unit tests -- triage router (grant-gating, needs_glossary hand-off shape,
422 invalid-action) + the triage_apply Neo4j re-apply seam.

Mocks TriageRepo + the grant primitives (project_meta_dep / get_grant_client /
get_current_user) so the routes run without a DB or book-service. The
grouping/signature batch logic itself is covered live in
tests/integration/db/test_kg_triage.py.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
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
    from app.routers.public.triage import get_triage_repo

    repo = repo or MagicMock()

    grant = MagicMock()
    grant.resolve_grant = AsyncMock(return_value=grant_level)

    app.dependency_overrides[get_current_user] = lambda: caller
    app.dependency_overrides[project_meta_dep] = lambda: meta
    app.dependency_overrides[get_grant_client] = lambda: grant
    app.dependency_overrides[get_triage_repo] = lambda: repo
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


def test_resolve_schema_mutating_manage_grantee_ok():
    repo = MagicMock()
    repo.list_pending_for_signature = AsyncMock(return_value=[_item()])
    repo.resolve_signature = AsyncMock(return_value=1)
    other = uuid4()
    client, _, _ = _make_client(caller=other, grant_level=GrantLevel.MANAGE, repo=repo)
    r = client.post(
        f"/v1/kg/projects/{_PROJECT}/triage/drive:curiosity/resolve",
        json={"action": "add_to_vocab", "params": {"value": "curiosity"}},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "resolved"
    # schema write deferred to LC -> schema_version stays None (intent recorded)
    assert body["schema_version"] is None


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
