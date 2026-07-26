"""KM6 — kg_schema_edit effect integration tests (real Postgres via `pool`).

Proves the descriptor effect end-to-end against real schema tables: add/deprecate
bump schema_version, and the confirm-time optimistic-concurrency re-validate rejects
a stale (drifted) proposal.
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from app.db.repositories.graph_schemas import GraphSchemasRepo
from app.db.repositories.ontology_mutations import OntologyMutationsRepo
from app.ontology.schema_edit_effect import (
    SchemaEditDrift,
    SchemaEditParams,
    apply_schema_edit,
    preview_schema_edit,
)

pytestmark = pytest.mark.asyncio


async def _seed_project_schema(pool, *, version: int = 1) -> tuple[str, str]:
    """Insert a project-scoped schema with one edge type; return (project_id, schema_id)."""
    project_id = f"proj-{uuid4()}"
    async with pool.acquire() as conn:
        schema_id = await conn.fetchval(
            """
            INSERT INTO kg_graph_schemas (scope, scope_id, code, name, schema_version, allow_free_edges)
            VALUES ('project', $1, 'edit-smoke', 'Edit Smoke', $2, false)
            RETURNING schema_id
            """,
            project_id, version,
        )
        await conn.execute(
            "INSERT INTO kg_edge_types (schema_id, code, label) VALUES ($1, 'GUARDS', 'Guards')",
            schema_id,
        )
    return project_id, str(schema_id)


async def test_apply_add_edge_type_bumps_version(pool):
    schemas = GraphSchemasRepo(pool)
    mutations = OntologyMutationsRepo(pool)
    project_id, schema_id = await _seed_project_schema(pool, version=5)

    params = SchemaEditParams(
        verb="add", level="edge_type", code="WORSHIPS", label="Worships",
        schema_id=schema_id, expected_schema_version=5,
    )
    result = await apply_schema_edit(schemas, mutations, project_id, params)
    assert result["applied"] is True
    assert result["schema_version"] == 6  # _bump_and_rehash

    # The edge type is present + active.
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT 1 FROM kg_edge_types WHERE schema_id=$1 AND code='WORSHIPS' AND deprecated_at IS NULL",
            schema_id,
        )
    assert row is not None


async def test_apply_deprecate_edge_type_bumps_version(pool):
    schemas = GraphSchemasRepo(pool)
    mutations = OntologyMutationsRepo(pool)
    project_id, schema_id = await _seed_project_schema(pool, version=2)

    params = SchemaEditParams(
        verb="deprecate", level="edge_type", code="GUARDS",
        schema_id=schema_id, expected_schema_version=2,
    )
    result = await apply_schema_edit(schemas, mutations, project_id, params)
    assert result["schema_version"] == 3
    async with pool.acquire() as conn:
        dep = await conn.fetchval(
            "SELECT deprecated_at FROM kg_edge_types WHERE schema_id=$1 AND code='GUARDS'",
            schema_id,
        )
    assert dep is not None  # soft-deleted


async def test_apply_rejects_version_drift(pool):
    schemas = GraphSchemasRepo(pool)
    mutations = OntologyMutationsRepo(pool)
    project_id, schema_id = await _seed_project_schema(pool, version=5)

    # The token captured v5, but the live schema is now v5 → bump it once to v6 first.
    await apply_schema_edit(
        schemas, mutations, project_id,
        SchemaEditParams(verb="add", level="edge_type", code="ALLIES", label="Allies",
                         schema_id=schema_id, expected_schema_version=5),
    )
    # A second proposal that still believes it's v5 must be rejected (drift).
    with pytest.raises(SchemaEditDrift):
        await apply_schema_edit(
            schemas, mutations, project_id,
            SchemaEditParams(verb="add", level="edge_type", code="SEALED_BY", label="Sealed by",
                             schema_id=schema_id, expected_schema_version=5),
        )


async def test_apply_rejects_schema_replaced(pool):
    schemas = GraphSchemasRepo(pool)
    mutations = OntologyMutationsRepo(pool)
    project_id, _schema_id = await _seed_project_schema(pool, version=1)
    with pytest.raises(SchemaEditDrift):
        await apply_schema_edit(
            schemas, mutations, project_id,
            SchemaEditParams(verb="add", level="edge_type", code="X", label="X",
                             schema_id=str(uuid4()), expected_schema_version=1),  # wrong schema_id
        )


async def test_preview_reflects_current_state_and_drift(pool):
    schemas = GraphSchemasRepo(pool)
    project_id, schema_id = await _seed_project_schema(pool, version=4)

    fresh = SchemaEditParams(verb="add", level="edge_type", code="WORSHIPS", label="Worships",
                             schema_id=schema_id, expected_schema_version=4)
    pv = await preview_schema_edit(schemas, project_id, fresh)
    assert pv["drift"] is False
    rows = {r["label"]: r["value"] for r in pv["preview_rows"]}
    assert rows["current schema_version"] == "4"
    assert rows["will bump to"] == "5"

    stale = SchemaEditParams(verb="add", level="edge_type", code="WORSHIPS", label="Worships",
                             schema_id=schema_id, expected_schema_version=1)  # stale
    pv2 = await preview_schema_edit(schemas, project_id, stale)
    assert pv2["drift"] is True
