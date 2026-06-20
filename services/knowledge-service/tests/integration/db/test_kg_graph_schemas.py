"""L1 integration tests — kg_* tables create, seed, idempotency, resolution, tenancy.

Requires a real Postgres (TEST_KNOWLEDGE_DB_URL); skips otherwise via the
shared `pool` fixture. Exercises the DDL + seed_system_graph_schemas +
GraphSchemasRepo reads end-to-end.
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from app.db.repositories.graph_schemas import GraphSchemasRepo
from app.db.seed_graph_schemas import seed_system_graph_schemas

pytestmark = pytest.mark.asyncio


async def _reset_kg(pool):
    async with pool.acquire() as conn:
        await conn.execute("TRUNCATE kg_graph_schemas RESTART IDENTITY CASCADE")
        await conn.execute("TRUNCATE kg_views, kg_triage_items RESTART IDENTITY CASCADE")


async def test_seed_inserts_then_is_idempotent(pool):
    await _reset_kg(pool)
    first = await seed_system_graph_schemas(pool)
    assert first == {"general": "insert", "xianxia-harem": "insert"}
    # second run: hash unchanged → skip (no churn).
    second = await seed_system_graph_schemas(pool)
    assert second == {"general": "skip", "xianxia-harem": "skip"}


async def test_concurrent_seed_is_race_safe(pool):
    """Multi-replica cold start: two seeders racing on an empty table must NOT
    crash with a unique-violation (review-impl HIGH). Exactly one row per code."""
    import asyncio

    await _reset_kg(pool)
    results = await asyncio.gather(
        seed_system_graph_schemas(pool),
        seed_system_graph_schemas(pool),
        return_exceptions=True,
    )
    for r in results:
        assert not isinstance(r, Exception), f"concurrent seed raised: {r!r}"
    async with pool.acquire() as conn:
        n = await conn.fetchval("SELECT count(*) FROM kg_graph_schemas WHERE scope = 'system'")
    assert n == 2  # general + xianxia-harem, exactly once each


async def test_seeded_xianxia_children_counts(pool):
    await _reset_kg(pool)
    await seed_system_graph_schemas(pool)
    repo = GraphSchemasRepo(pool)
    tpl = await repo.get_system_template_by_code("xianxia-harem")
    assert tpl is not None
    assert tpl.scope == "system" and tpl.scope_id is None
    assert tpl.allow_free_edges is True
    tree = await repo.get_tree(uuid4(), tpl.schema_id)  # system visible to anyone
    assert tree is not None
    assert len(tree["fact_types"]) == 9
    assert len(tree["edge_types"]) == 24
    assert len(tree["node_kinds"]) == 8
    required = {k.kind_code for k in tree["node_kinds"] if k.strength == "required"}
    assert required == {"character", "organization", "location", "concept", "technique"}
    assert "drive" in tree["vocab_values"]
    assert len(tree["vocab_values"]["drive"]) == 16
    # closed vocab value carries metadata
    drive_vals = {v.code: v.metadata for v in tree["vocab_values"]["drive"]}
    assert "axis" in drive_vals["revenge"]


async def test_resolution_falls_back_to_general_for_unadopted_project(pool):
    await _reset_kg(pool)
    await seed_system_graph_schemas(pool)
    repo = GraphSchemasRepo(pool)
    resolved = await repo.resolve_for_project(f"proj-{uuid4()}")
    # un-adopted → general (the additive-first fallback)
    assert resolved.allow_free_edges is True
    fact_codes = {f.code for f in resolved.fact_types}
    assert fact_codes == {"description", "attribute", "negation", "temporal", "causal"}
    assert resolved.edge_types == []  # general is free-edge


async def test_adopted_project_schema_wins_resolution(pool):
    await _reset_kg(pool)
    await seed_system_graph_schemas(pool)
    project_id = f"proj-{uuid4()}"
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO kg_graph_schemas (scope, scope_id, code, name, allow_free_edges)
            VALUES ('project', $1, 'xianxia-harem', 'Adopted', false)
            """,
            project_id,
        )
    repo = GraphSchemasRepo(pool)
    resolved = await repo.resolve_for_project(project_id)
    assert resolved.allow_free_edges is False  # the project row, not general


async def test_user_tier_visibility_is_owner_scoped(pool):
    await _reset_kg(pool)
    await seed_system_graph_schemas(pool)
    owner = uuid4()
    other = uuid4()
    async with pool.acquire() as conn:
        sid = await conn.fetchval(
            """
            INSERT INTO kg_graph_schemas (scope, scope_id, code, name)
            VALUES ('user', $1, 'my-template', 'Mine') RETURNING schema_id
            """,
            str(owner),
        )
    repo = GraphSchemasRepo(pool)
    # owner sees it; other user does not.
    assert await repo.get_tree(owner, sid) is not None
    assert await repo.get_tree(other, sid) is None
    owner_list = {s.code for s in await repo.list_visible(owner)}
    other_list = {s.code for s in await repo.list_visible(other)}
    assert "my-template" in owner_list
    assert "my-template" not in other_list
    # both see the system templates
    assert "general" in owner_list and "general" in other_list


async def test_scope_keyed_unique_allows_same_code_across_tiers(pool):
    """The kinds-bug guard: same code in different scopes must NOT collide."""
    await _reset_kg(pool)
    await seed_system_graph_schemas(pool)  # system 'general'
    async with pool.acquire() as conn:
        # a user may have their own 'general' — different scope, no conflict
        await conn.execute(
            "INSERT INTO kg_graph_schemas (scope, scope_id, code, name) VALUES ('user', $1, 'general', 'User general')",
            str(uuid4()),
        )
    # no exception = scope-keyed uniqueness holds
