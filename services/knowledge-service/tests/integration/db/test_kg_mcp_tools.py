"""Lane LF — live-PG integration of the KG ontology MCP tools.

Drives the W (write) tool HANDLERS end-to-end through `execute_tool` against a
real Postgres so the `kg_*` table reads/writes (views CRUD, triage park +
resolve, pending-facts inbox) are exercised, not just mocked. Requires
TEST_KNOWLEDGE_DB_URL (the shared `pool` fixture skips otherwise).

The project is seeded book-less + owned by the caller, so the grant gate passes
via owner==caller WITHOUT consulting a grant client (resolve-to-owner). This is
the proof that `kg_propose_edge` parks to the triage inbox (never Neo4j),
`kg_triage_resolve` transitions PG state, and the view tools are owner-scoped.
"""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from app.clients.glossary_ontology_client import FakeGlossaryOntologyClient
from app.db.repositories.graph_schemas import GraphSchemasRepo
from app.db.repositories.graph_views import GraphViewsRepo
from app.db.repositories.ontology_mutations import OntologyMutationsRepo
from app.db.repositories.pending_facts import PendingFactsRepo
from app.db.repositories.projects import ProjectsRepo
from app.db.repositories.triage import TriageRepo
from app.ontology.resolver import OntologyResolver
from app.tools.executor import ToolContext, execute_tool

pytestmark = pytest.mark.asyncio


async def _seed_project(pool, *, owner, book_id=None) -> str:
    """Insert a minimal knowledge_projects row owned by `owner`; return its id."""
    async with pool.acquire() as conn:
        pid = await conn.fetchval(
            """
            INSERT INTO knowledge_projects (user_id, name, project_type, book_id)
            VALUES ($1, 'lf-mcp-test', 'general', $2)
            RETURNING project_id
            """,
            owner, book_id,
        )
    return str(pid)


def _ctx(pool, *, owner, project_id) -> ToolContext:
    """A real-pool-backed ToolContext. grant_client is a stub that should NEVER
    be called for an owner==caller request (owner-only project)."""
    projects_repo = ProjectsRepo(pool)
    return ToolContext(
        user_id=owner,
        project_id=UUID(project_id),
        session_id="sess-lf-int",
        projects_repo=projects_repo,
        pending_facts_repo=PendingFactsRepo(pool),
        embedding_client=None,
        redis=None,
        grant_client=None,  # owner==caller path never touches it
        graph_views_repo=GraphViewsRepo(pool),
        graph_schemas_repo=GraphSchemasRepo(pool),
        triage_repo=TriageRepo(pool),
        ontology_resolver=OntologyResolver(
            schemas=GraphSchemasRepo(pool),
            projects=projects_repo,
            # resolve() never reads glossary (only resolve_node_kinds does),
            # so a bare fake suffices for these tools.
            glossary=FakeGlossaryOntologyClient(),
        ),
        ontology_mutations_repo=OntologyMutationsRepo(pool),
    )


async def test_view_upsert_read_delete_roundtrip_live(pool):
    owner = uuid4()
    project_id = await _seed_project(pool, owner=owner)
    ctx = _ctx(pool, owner=owner, project_id=project_id)

    up = await execute_tool(
        ctx, "kg_view_upsert",
        {"code": "drives", "name": "Drives", "edge_type_codes": ["pursues"]},
    )
    assert up.success and up.result["created"] is True

    read = await execute_tool(ctx, "kg_view_read", {})
    assert read.success
    assert read.result["count"] == 1
    assert read.result["views"][0]["code"] == "drives"

    deleted = await execute_tool(ctx, "kg_view_delete", {"code": "drives"})
    assert deleted.success and deleted.result["deleted"] is True

    read2 = await execute_tool(ctx, "kg_view_read", {})
    assert read2.result["count"] == 0


async def test_propose_edge_parks_to_triage_then_resolve_live(pool):
    owner = uuid4()
    project_id = await _seed_project(pool, owner=owner)
    ctx = _ctx(pool, owner=owner, project_id=project_id)

    # No project schema adopted → resolves to the seeded `general` template (or
    # degenerate allow_free_edges). With free edges allowed, an unknown edge is
    # on-schema → parks as edge_cardinality_conflict (still inbox, never Neo4j).
    res = await execute_tool(
        ctx, "kg_propose_edge",
        {
            "source_entity_id": "ent-a",
            "target_entity_id": "ent-b",
            "edge_type": "allies_with",
            "valid_from": 7,
        },
    )
    assert res.success, res.error
    assert res.result["parked"] is True
    signature = res.result["signature"]

    # The parked proposal shows up in the triage queue.
    listed = await execute_tool(ctx, "kg_triage_list", {})
    assert listed.success
    sigs = {g["signature"] for g in listed.result["groups"]}
    assert signature in sigs

    # Resolve it with a KG-local action valid for its item_type. The parked
    # item_type drives which actions are legal; pick the first suggested one.
    group = next(g for g in listed.result["groups"] if g["signature"] == signature)
    kg_local = {"map", "re_target", "drop_edge", "close_previous", "dismiss"}
    action = next(a for a in group["suggested_actions"] if a in kg_local)
    resolved = await execute_tool(
        ctx, "kg_triage_resolve", {"signature": signature, "action": action},
    )
    assert resolved.success, resolved.error
    assert resolved.result["status"] == "resolved"
    assert resolved.result["affected"] >= 1

    # It is gone from the pending queue (transitioned to 'resolved').
    listed2 = await execute_tool(ctx, "kg_triage_list", {})
    assert signature not in {g["signature"] for g in listed2.result["groups"]}


async def test_propose_fact_queues_into_pending_inbox_live(pool):
    owner = uuid4()
    project_id = await _seed_project(pool, owner=owner)
    ctx = _ctx(pool, owner=owner, project_id=project_id)

    res = await execute_tool(
        ctx, "kg_propose_fact",
        {"fact_text": "The protagonist is left-handed", "fact_type": "milestone"},
    )
    assert res.success, res.error
    assert res.result["queued"] is True

    # The draft is visible in the owner's pending-facts inbox (never the graph).
    pending = await PendingFactsRepo(pool).list_for_user(owner)
    assert len(pending) == 1
    assert pending[0].fact_type == "milestone"


async def test_propose_edge_temporal_required_rejected_live(pool):
    """A temporal edge type without valid_from is rejected at mint — nothing
    parks. We assert via the absence of any triage row for the project."""
    owner = uuid4()
    project_id = await _seed_project(pool, owner=owner)

    # Adopt a tiny project schema with one temporal edge so resolve sees it.
    async with pool.acquire() as conn:
        schema_id = await conn.fetchval(
            """
            INSERT INTO kg_graph_schemas (scope, scope_id, code, name, allow_free_edges)
            VALUES ('project', $1, 'lf_int', 'lf int', false)
            RETURNING schema_id
            """,
            project_id,
        )
        await conn.execute(
            """
            INSERT INTO kg_edge_types (schema_id, code, label, temporal)
            VALUES ($1, 'loves', 'Loves', true)
            """,
            schema_id,
        )

    ctx = _ctx(pool, owner=owner, project_id=project_id)
    res = await execute_tool(
        ctx, "kg_propose_edge",
        {"source_entity_id": "a", "target_entity_id": "b", "edge_type": "loves"},
    )
    assert not res.success
    assert "temporal" in res.error.lower()

    listed = await execute_tool(ctx, "kg_triage_list", {})
    assert listed.result["groups"] == []
