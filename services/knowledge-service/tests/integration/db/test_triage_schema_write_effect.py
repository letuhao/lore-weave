"""E3 (D-KG-LH-LC-SCHEMA-WRITE) integration — schema-mutating triage resolution
through ontology_mutations via the confirm spine, against real Postgres.

Proves add_to_vocab confirm bumps schema_version + the value appears; drift→422;
the additive widen/set_multi_active repo methods land. Requires
TEST_KNOWLEDGE_DB_URL (skips otherwise via the shared `pool` fixture).

Spec: docs/specs/2026-06-21-kg-deferred-clearance.md §5 (E3).
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from app.db.repositories.graph_schemas import GraphSchemasRepo
from app.db.repositories.ontology_mutations import OntologyMutationsRepo
from app.db.repositories.triage import TriageRepo
from app.ontology.triage_schema_write_effect import (
    TriageSchemaWriteDrift,
    TriageSchemaWriteParams,
    apply_triage_schema_write,
)

pytestmark = pytest.mark.asyncio


async def _seed(pool, *, version: int = 1):
    """Project schema with a drive vocab set + an edge type; return (proj, schema_id)."""
    project_id = f"proj-{uuid4()}"
    async with pool.acquire() as conn:
        schema_id = await conn.fetchval(
            """
            INSERT INTO kg_graph_schemas (scope, scope_id, code, name, schema_version, allow_free_edges)
            VALUES ('project', $1, 'sw-smoke', 'SW Smoke', $2, false)
            RETURNING schema_id
            """,
            project_id, version,
        )
        set_id = await conn.fetchval(
            "INSERT INTO kg_vocab_sets (schema_id, code, label, closed) "
            "VALUES ($1, 'drive', 'Drive', true) RETURNING vocab_set_id",
            schema_id,
        )
        await conn.execute(
            "INSERT INTO kg_edge_types (schema_id, code, label, target_node_kinds, cardinality) "
            "VALUES ($1, 'CURRENT_SECT', 'Current sect', ARRAY['organization'], 'single_active')",
            schema_id,
        )
    return project_id, str(schema_id), set_id


async def test_e3_add_to_vocab_bumps_version_and_value_appears(pool):
    schemas = GraphSchemasRepo(pool)
    mutations = OntologyMutationsRepo(pool)
    triage = TriageRepo(pool)
    project_id, schema_id, _set = await _seed(pool, version=5)

    params = TriageSchemaWriteParams(
        action="add_to_vocab", signature="drive:curiosity",
        schema_id=schema_id, expected_schema_version=5,
        code="curiosity", label="Curiosity", set_code="drive",
    )
    result = await apply_triage_schema_write(schemas, mutations, triage, project_id, params)
    assert result["applied"] is True
    assert result["schema_version"] == 6  # _bump_and_rehash

    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT 1 FROM kg_vocab_values vv
            JOIN kg_vocab_sets vs ON vs.vocab_set_id = vv.vocab_set_id
            WHERE vs.schema_id = $1 AND vs.code = 'drive' AND vv.code = 'curiosity'
              AND vv.deprecated_at IS NULL
            """,
            schema_id,
        )
    assert row is not None


async def test_e3_rejects_version_drift(pool):
    schemas = GraphSchemasRepo(pool)
    mutations = OntologyMutationsRepo(pool)
    triage = TriageRepo(pool)
    project_id, schema_id, _set = await _seed(pool, version=5)

    # First write bumps to v6.
    await apply_triage_schema_write(
        schemas, mutations, triage, project_id,
        TriageSchemaWriteParams(action="add_to_vocab", signature="drive:a",
                                schema_id=schema_id, expected_schema_version=5,
                                code="a", set_code="drive"),
    )
    # A second proposal still believing it's v5 → drift.
    with pytest.raises(TriageSchemaWriteDrift):
        await apply_triage_schema_write(
            schemas, mutations, triage, project_id,
            TriageSchemaWriteParams(action="add_to_vocab", signature="drive:b",
                                    schema_id=schema_id, expected_schema_version=5,
                                    code="b", set_code="drive"),
        )


async def test_e3_set_multi_active_flips_cardinality(pool):
    schemas = GraphSchemasRepo(pool)
    mutations = OntologyMutationsRepo(pool)
    triage = TriageRepo(pool)
    project_id, schema_id, _set = await _seed(pool, version=1)

    await apply_triage_schema_write(
        schemas, mutations, triage, project_id,
        TriageSchemaWriteParams(action="set_multi_active", signature="edge_card:CURRENT_SECT",
                                schema_id=schema_id, expected_schema_version=1,
                                code="CURRENT_SECT"),
    )
    async with pool.acquire() as conn:
        card = await conn.fetchval(
            "SELECT cardinality FROM kg_edge_types WHERE schema_id = $1 AND code = 'CURRENT_SECT'",
            schema_id,
        )
    assert card == "multi_active"


async def test_e3_widen_target_kinds_unions(pool):
    schemas = GraphSchemasRepo(pool)
    mutations = OntologyMutationsRepo(pool)
    triage = TriageRepo(pool)
    project_id, schema_id, _set = await _seed(pool, version=1)

    await apply_triage_schema_write(
        schemas, mutations, triage, project_id,
        TriageSchemaWriteParams(action="widen_target_kinds", signature="edge_kind:CURRENT_SECT",
                                schema_id=schema_id, expected_schema_version=1,
                                code="CURRENT_SECT", add_kinds=["faction", "organization"]),
    )
    async with pool.acquire() as conn:
        kinds = await conn.fetchval(
            "SELECT target_node_kinds FROM kg_edge_types WHERE schema_id = $1 AND code = 'CURRENT_SECT'",
            schema_id,
        )
    assert set(kinds) == {"organization", "faction"}  # union, idempotent on existing
