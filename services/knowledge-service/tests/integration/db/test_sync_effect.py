"""KM6-M3 — kg_sync_apply effect integration tests (real Postgres via `pool`).

Proves the sync descriptor effect end-to-end: take_theirs brings an upstream-added
edge into the project copy, a stale base_source_hash is rejected (SyncDrift /
optimistic-concurrency), a never-adopted project raises SyncNoSchema, and preview
renders the live diff + drift flag.
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from app.db.repositories.graph_schemas import GraphSchemasRepo
from app.db.repositories.ontology_mutations import OntologyMutationsRepo
from app.db.seed_graph_schemas import seed_system_graph_schemas
from app.ontology.sync_effect import (
    SyncApplyParams,
    SyncDecisionParam,
    SyncDrift,
    SyncNoSchema,
    apply_sync,
    preview_sync,
)

pytestmark = pytest.mark.asyncio

_XIANXIA_REQUIRED = ["character", "organization", "location", "concept", "technique"]


async def _reset(pool):
    async with pool.acquire() as conn:
        await conn.execute("TRUNCATE kg_graph_schemas RESTART IDENTITY CASCADE")
        await conn.execute("TRUNCATE knowledge_projects RESTART IDENTITY CASCADE")
    await seed_system_graph_schemas(pool)


async def _system_id(pool, code: str):
    return (await GraphSchemasRepo(pool).get_system_template_by_code(code)).schema_id


async def _adopt(pool, mutations) -> tuple[str, object]:
    project_id = f"proj-{uuid4()}"
    res = await mutations.adopt(
        owner_user_id=uuid4(), project_id=project_id,
        source_schema_id=await _system_id(pool, "xianxia-harem"),
        glossary_kinds=set(_XIANXIA_REQUIRED + ["item", "event", "relationship"]),
        book_id=None,
    )
    return project_id, res.schema.schema_id


async def _add_upstream_edge(pool, src, code="SWORN_SIBLING_OF"):
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO kg_edge_types (schema_id, code, label) VALUES ($1, $2, 'sworn')", src, code,
        )


async def test_apply_sync_take_theirs_brings_upstream_edge(pool):
    await _reset(pool)
    schemas, mutations = GraphSchemasRepo(pool), OntologyMutationsRepo(pool)
    project_id, proj_schema = await _adopt(pool, mutations)
    src = await _system_id(pool, "xianxia-harem")
    await _add_upstream_edge(pool, src)

    diff = await mutations.sync_diff(proj_schema)
    assert diff["has_updates"] is True
    await apply_sync(
        schemas, mutations, project_id,
        SyncApplyParams(
            base_source_hash=diff["source_hash_current"],
            decisions=[SyncDecisionParam(node_type="edge_type", code="SWORN_SIBLING_OF", choice="take_theirs")],
        ),
    )
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT 1 FROM kg_edge_types WHERE schema_id=$1 AND code='SWORN_SIBLING_OF' AND deprecated_at IS NULL",
            proj_schema,
        )
    assert row is not None


async def test_apply_sync_rejects_stale_base_hash(pool):
    await _reset(pool)
    schemas, mutations = GraphSchemasRepo(pool), OntologyMutationsRepo(pool)
    project_id, _proj = await _adopt(pool, mutations)
    src = await _system_id(pool, "xianxia-harem")
    await _add_upstream_edge(pool, src)
    with pytest.raises(SyncDrift):
        await apply_sync(
            schemas, mutations, project_id,
            SyncApplyParams(base_source_hash="stale-hash-not-current", decisions=[]),
        )


async def test_apply_sync_no_adopted_schema(pool):
    await _reset(pool)
    schemas, mutations = GraphSchemasRepo(pool), OntologyMutationsRepo(pool)
    with pytest.raises(SyncNoSchema):
        await apply_sync(
            schemas, mutations, f"proj-{uuid4()}",
            SyncApplyParams(base_source_hash="h", decisions=[]),
        )


async def test_preview_sync_renders_diff_and_drift(pool):
    await _reset(pool)
    schemas, mutations = GraphSchemasRepo(pool), OntologyMutationsRepo(pool)
    project_id, _proj = await _adopt(pool, mutations)
    src = await _system_id(pool, "xianxia-harem")
    await _add_upstream_edge(pool, src)
    diff = await mutations.sync_diff(_proj)
    current = diff["source_hash_current"]

    fresh = await preview_sync(
        schemas, mutations, project_id,
        SyncApplyParams(base_source_hash=current,
                        decisions=[SyncDecisionParam(node_type="edge_type", code="SWORN_SIBLING_OF", choice="take_theirs")]),
    )
    assert fresh["descriptor"] == "kg_sync_apply" and fresh["drift"] is False
    rows = {r["label"]: r["value"] for r in fresh["preview_rows"]}
    assert rows["upstream has updates"] == "yes" and rows["take-theirs decisions"] == "1"

    stale = await preview_sync(
        schemas, mutations, project_id,
        SyncApplyParams(base_source_hash="old-hash", decisions=[]),
    )
    assert stale["drift"] is True
