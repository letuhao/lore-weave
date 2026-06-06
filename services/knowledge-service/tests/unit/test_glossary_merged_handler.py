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
    merge = AsyncMock(side_effect=merge_exc) if merge_exc else AsyncMock()
    monkeypatch.setattr(entities_mod, "get_entity_by_glossary_id", fake_get)
    monkeypatch.setattr(entities_mod, "unlink_from_glossary", unlink)
    monkeypatch.setattr(entities_mod, "merge_entities", merge)

    repo = MagicMock()
    repo.record_merge = AsyncMock()
    monkeypatch.setattr(alias_mod, "EntityAliasMapRepo", lambda pool: repo)
    return unlink, merge, repo


def _entity(cid, canon, aliases, kind="character"):
    return SimpleNamespace(id=cid, canonical_name=canon, aliases=aliases, kind=kind, project_id=str(PROJECT))


@pytest.mark.asyncio
async def test_consolidates_kg_and_records_aliases(monkeypatch):
    loser = _entity("c-loser", "太公望", ["子牙"])
    winner = _entity("c-winner", "姜子牙", [])
    unlink, merge, repo = _wire(monkeypatch, loser=loser, winner=winner)

    await handle_glossary_entity_merged(_event(), pool=_pool())

    unlink.assert_awaited_once()  # loser anchor cleared (bypass glossary_conflict)
    assert unlink.await_args.kwargs["canonical_id"] == "c-loser"
    merge.assert_awaited_once()
    assert merge.await_args.kwargs["source_id"] == "c-loser"
    assert merge.await_args.kwargs["target_id"] == "c-winner"
    # alias-map: loser canon + each alias → winner
    recorded = {c.kwargs["canonical_alias"] for c in repo.record_merge.await_args_list}
    assert "太公望" in recorded and "子牙" in recorded
    for c in repo.record_merge.await_args_list:
        assert c.kwargs["target_entity_id"] == "c-winner"


@pytest.mark.asyncio
async def test_unmerged_is_noop(monkeypatch):
    unlink, merge, repo = _wire(monkeypatch, loser=_entity("l", "L", []), winner=_entity("w", "W", []))
    await handle_glossary_entity_merged(_event(op="unmerged"), pool=_pool())
    merge.assert_not_awaited()
    repo.record_merge.assert_not_awaited()


@pytest.mark.asyncio
async def test_no_project_is_noop(monkeypatch):
    unlink, merge, repo = _wire(monkeypatch, loser=_entity("l", "L", []), winner=_entity("w", "W", []))
    await handle_glossary_entity_merged(_event(), pool=_pool(project_found=False))
    merge.assert_not_awaited()


@pytest.mark.asyncio
async def test_absent_nodes_no_merge(monkeypatch):
    # loser node missing → nothing to consolidate
    unlink, merge, repo = _wire(monkeypatch, loser=None, winner=_entity("w", "W", []))
    await handle_glossary_entity_merged(_event(), pool=_pool())
    merge.assert_not_awaited()
    repo.record_merge.assert_not_awaited()


@pytest.mark.asyncio
async def test_same_entity_is_idempotent_noop(monkeypatch):
    loser = _entity("c", "X", [])
    winner = _entity("c", "X", [])
    unlink, merge, repo = _wire(
        monkeypatch, loser=loser, winner=winner,
        merge_exc=MergeEntitiesError("same_entity", "already one"),
    )
    # must NOT raise (swallowed as idempotent)
    await handle_glossary_entity_merged(_event(), pool=_pool())
    merge.assert_awaited_once()
