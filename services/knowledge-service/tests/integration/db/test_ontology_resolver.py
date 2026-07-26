"""Live-PG integration tests for lane LA (resolver + validation over the seed).

Requires a real Postgres (TEST_KNOWLEDGE_DB_URL); skips otherwise via the
shared `pool` fixture. Resolves real seeded schemas and validates against them:
  * un-adopted project → general (allow_free_edges True, free edges OK);
  * an adopted xianxia-harem project → off-vocab drive value → unknown_vocab_value.
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from app.db.repositories.graph_schemas import GraphSchemasRepo
from app.db.repositories.projects import ProjectsRepo
from app.db.seed_graph_schemas import seed_system_graph_schemas
from app.clients.glossary_ontology_client import FakeGlossaryOntologyClient
from app.ontology.resolver import OntologyResolver
from app.ontology.validation import validate_edge, validate_vocab_value

pytestmark = pytest.mark.asyncio


async def _reset_and_seed(pool):
    async with pool.acquire() as conn:
        await conn.execute("TRUNCATE kg_graph_schemas RESTART IDENTITY CASCADE")
        await conn.execute("TRUNCATE kg_views, kg_triage_items RESTART IDENTITY CASCADE")
    await seed_system_graph_schemas(pool)


def _resolver(pool, glossary=None) -> OntologyResolver:
    return OntologyResolver(
        schemas=GraphSchemasRepo(pool),
        projects=ProjectsRepo(pool),
        glossary=glossary or FakeGlossaryOntologyClient(),
    )


async def test_unadopted_project_resolves_to_general_with_free_edges(pool):
    await _reset_and_seed(pool)
    r = _resolver(pool)
    project_id = f"proj-{uuid4()}"
    schema = await r.resolve(project_id)
    # general fallback → free edges, no closed edge vocab.
    assert schema.allow_free_edges is True
    assert schema.edge_types == []
    # a free-string predicate validates OK under general.
    assert validate_edge(schema, predicate="WHISPERS_TO") is None


async def test_resolve_is_cached(pool):
    await _reset_and_seed(pool)
    r = _resolver(pool)
    project_id = f"proj-{uuid4()}"
    a = await r.resolve(project_id)
    b = await r.resolve(project_id)
    assert a is b  # served from the in-process cache
    r.invalidate(project_id)
    c = await r.resolve(project_id)
    assert c is not a  # fresh object after invalidate


async def test_offvocab_drive_against_xianxia_template_parks_unknown_vocab_value(pool):
    await _reset_and_seed(pool)
    # adopt the seeded xianxia-harem template into a project (closed-vocab path).
    project_id = f"proj-{uuid4()}"
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO kg_graph_schemas (scope, scope_id, code, name, allow_free_edges)
            VALUES ('project', $1, 'xianxia-harem', 'Adopted', false)
            RETURNING schema_id
            """,
            project_id,
        )
        # copy-down the drive vocab set + its values so the project schema is closed.
        sys_set = await conn.fetchrow(
            """
            SELECT vs.vocab_set_id FROM kg_vocab_sets vs
            JOIN kg_graph_schemas s ON s.schema_id = vs.schema_id
            WHERE s.scope = 'system' AND s.code = 'xianxia-harem' AND vs.code = 'drive'
            """
        )
        proj_schema_id = await conn.fetchval(
            "SELECT schema_id FROM kg_graph_schemas WHERE scope='project' AND scope_id=$1",
            project_id,
        )
        proj_set_id = await conn.fetchval(
            """
            INSERT INTO kg_vocab_sets (schema_id, code, label, description, closed)
            VALUES ($1, 'drive', 'Drive', '', true) RETURNING vocab_set_id
            """,
            proj_schema_id,
        )
        rows = await conn.fetch(
            "SELECT code, label, metadata FROM kg_vocab_values WHERE vocab_set_id = $1",
            sys_set["vocab_set_id"],
        )
        for row in rows:
            await conn.execute(
                "INSERT INTO kg_vocab_values (vocab_set_id, code, label, metadata) VALUES ($1, $2, $3, $4)",
                proj_set_id, row["code"], row["label"], row["metadata"],
            )

    r = _resolver(pool)
    schema = await r.resolve(project_id)
    assert schema.allow_free_edges is False
    assert "drive" in {s.code for s in schema.vocab_sets}
    # a known drive value validates OK.
    assert validate_vocab_value(schema, set_code="drive", value="revenge") is None
    # an off-vocab value parks unknown_vocab_value with signature drive:<value>.
    issue = validate_vocab_value(schema, set_code="drive", value="curiosity")
    assert issue is not None
    assert issue.item_type == "unknown_vocab_value"
    assert issue.signature == "drive:curiosity"
    assert issue.is_triage is True
