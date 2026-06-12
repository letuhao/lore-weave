"""mui #1c K-sync — unit tests for handle_glossary_entity_merged (no Neo4j/PG).

Mocks the project lookup (pool.fetchrow), the Neo4j session + entity repos, and
the alias-map repo. Verifies the orchestration: clear loser anchor → merge
loser into winner → register loser names in entity_alias_map. Plus the no-op
paths (unmerged / no-project / absent nodes / same_entity idempotency).
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

import app.config as config_mod
import app.db.neo4j as neo4j_mod
import app.db.neo4j_repos.canonical as canon_mod
import app.db.neo4j_repos.entities as entities_mod
import app.db.repositories.entity_alias_map as alias_mod
from app.db.neo4j_repos.entities import MergeEntitiesError
from app.events.handlers import handle_glossary_entity_merged

BOOK = uuid4()
WINNER_GID = uuid4()
LOSER_GID = uuid4()
USER = uuid4()
PROJECT = uuid4()


class _FakeSession:
    async def __aenter__(self):
        return MagicMock()

    async def __aexit__(self, *a):
        return False


def _event(op="merged", **over):
    payload = {
        "book_id": str(BOOK), "winner_glossary_id": str(WINNER_GID),
        "loser_glossary_id": str(LOSER_GID), "op": op,
    }
    payload.update(over)
    return SimpleNamespace(payload=payload, message_id="m1", aggregate_id=str(WINNER_GID), event_type="glossary.entity_merged")


def _pool(project_found=True):
    pool = MagicMock()
    pool.fetchrow = AsyncMock(
        return_value=({"project_id": PROJECT, "user_id": USER} if project_found else None)
    )
    return pool


def _wire(monkeypatch, *, loser, winner, merge_exc=None):
    """Patch the inline-imported deps so the handler runs without infra."""
    monkeypatch.setattr(config_mod.settings, "neo4j_uri", "bolt://x", raising=False)
    monkeypatch.setattr(neo4j_mod, "neo4j_session", lambda: _FakeSession())
    monkeypatch.setattr(canon_mod, "canonicalize_entity_name", lambda s: (s or "").lower().strip())

    async def fake_get(session, *, user_id, glossary_entity_id):
        if glossary_entity_id == str(LOSER_GID):
            return loser
        if glossary_entity_id == str(WINNER_GID):
            return winner
        return None

    unlink = AsyncMock()
    relink = AsyncMock()
    merge = AsyncMock(side_effect=merge_exc) if merge_exc else AsyncMock()
    monkeypatch.setattr(entities_mod, "get_entity_by_glossary_id", fake_get)
    monkeypatch.setattr(entities_mod, "unlink_from_glossary", unlink)
    monkeypatch.setattr(entities_mod, "link_to_glossary", relink)
    monkeypatch.setattr(entities_mod, "merge_entities", merge)

    repo = MagicMock()
    repo.record_merge = AsyncMock()
    monkeypatch.setattr(alias_mod, "EntityAliasMapRepo", lambda pool: repo)
    return SimpleNamespace(unlink=unlink, relink=relink, merge=merge, repo=repo)


def _entity(cid, canon, aliases, kind="character"):
    return SimpleNamespace(id=cid, name=canon, canonical_name=canon, aliases=aliases, kind=kind, project_id=str(PROJECT))


@pytest.mark.asyncio
async def test_consolidates_kg_and_records_aliases(monkeypatch):
    loser = _entity("c-loser", "太公望", ["子牙"])
    winner = _entity("c-winner", "姜子牙", [])
    m = _wire(monkeypatch, loser=loser, winner=winner)

    await handle_glossary_entity_merged(_event(), pool=_pool())

    m.unlink.assert_awaited_once()  # loser anchor cleared (bypass glossary_conflict)
    assert m.unlink.await_args.kwargs["canonical_id"] == "c-loser"
    m.merge.assert_awaited_once()
    assert m.merge.await_args.kwargs["source_id"] == "c-loser"
    assert m.merge.await_args.kwargs["target_id"] == "c-winner"
    m.relink.assert_not_awaited()  # no failure → no compensation
    # alias-map: loser canon + each alias → winner, scoped to the node's project
    recorded = {c.kwargs["canonical_alias"] for c in m.repo.record_merge.await_args_list}
    assert "太公望" in recorded and "子牙" in recorded
    for c in m.repo.record_merge.await_args_list:
        assert c.kwargs["target_entity_id"] == "c-winner"
        assert c.kwargs["project_scope"] == str(PROJECT)  # MED-2: entity project


@pytest.mark.asyncio
async def test_unmerged_is_noop(monkeypatch):
    m = _wire(monkeypatch, loser=_entity("l", "L", []), winner=_entity("w", "W", []))
    await handle_glossary_entity_merged(_event(op="unmerged"), pool=_pool())
    m.merge.assert_not_awaited()
    m.repo.record_merge.assert_not_awaited()


@pytest.mark.asyncio
async def test_no_project_is_noop(monkeypatch):
    m = _wire(monkeypatch, loser=_entity("l", "L", []), winner=_entity("w", "W", []))
    await handle_glossary_entity_merged(_event(), pool=_pool(project_found=False))
    m.merge.assert_not_awaited()


@pytest.mark.asyncio
async def test_absent_nodes_no_merge(monkeypatch):
    # loser node missing → nothing to consolidate
    m = _wire(monkeypatch, loser=None, winner=_entity("w", "W", []))
    await handle_glossary_entity_merged(_event(), pool=_pool())
    m.merge.assert_not_awaited()
    m.repo.record_merge.assert_not_awaited()


@pytest.mark.asyncio
async def test_same_entity_is_idempotent_noop(monkeypatch):
    m = _wire(
        monkeypatch, loser=_entity("c", "X", []), winner=_entity("c", "X", []),
        merge_exc=MergeEntitiesError("same_entity", "already one"),
    )
    # must NOT raise (swallowed as idempotent), and no compensation re-link
    await handle_glossary_entity_merged(_event(), pool=_pool())
    m.merge.assert_awaited_once()
    m.relink.assert_not_awaited()


@pytest.mark.asyncio
async def test_merge_failure_relinks_loser_and_raises(monkeypatch):
    # MED-1: a non-same_entity merge failure must re-link the loser (the unlink
    # already committed) so a redelivery can find + retry it, then propagate.
    m = _wire(
        monkeypatch, loser=_entity("c-loser", "L", ["la"]), winner=_entity("c-winner", "W", []),
        merge_exc=MergeEntitiesError("entity_not_found", "transient"),
    )
    with pytest.raises(MergeEntitiesError):
        await handle_glossary_entity_merged(_event(), pool=_pool())
    m.relink.assert_awaited_once()
    assert m.relink.await_args.kwargs["canonical_id"] == "c-loser"
    assert m.relink.await_args.kwargs["glossary_entity_id"] == str(LOSER_GID)
    m.repo.record_merge.assert_not_awaited()  # alias-map not written on failure
