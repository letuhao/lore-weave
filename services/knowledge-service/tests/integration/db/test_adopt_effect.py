"""KM6-M2 — kg_adopt effect integration tests (real Postgres via `pool`).

Proves the adopt descriptor effect end-to-end against the real schema tables + the M1
glossary gate: a satisfied gate scaffolds a project schema (replace-on-adopt), a missing
required kind raises AdoptNeedsGlossary, and preview renders the template summary +
replace/gap warnings from current state.
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from app.clients.glossary_ontology_client import FakeGlossaryOntologyClient
from app.db.repositories.graph_schemas import GraphSchemasRepo
from app.db.repositories.ontology_mutations import OntologyMutationsRepo
from app.db.repositories.projects import ProjectsRepo
from app.db.seed_graph_schemas import seed_system_graph_schemas
from app.ontology.adopt_effect import (
    AdoptNeedsGlossary,
    AdoptParams,
    apply_adopt,
    preview_adopt,
)

pytestmark = pytest.mark.asyncio

_XIANXIA_REQUIRED = ["character", "organization", "location", "concept", "technique"]


async def _reset(pool):
    async with pool.acquire() as conn:
        await conn.execute("TRUNCATE kg_graph_schemas RESTART IDENTITY CASCADE")
        await conn.execute("TRUNCATE knowledge_projects RESTART IDENTITY CASCADE")
    await seed_system_graph_schemas(pool)


async def _make_project(pool, owner) -> str:
    async with pool.acquire() as conn:
        pid = await conn.fetchval(
            "INSERT INTO knowledge_projects (user_id, name, project_type) "
            "VALUES ($1, 'adopt-smoke', 'general') RETURNING project_id",
            owner,
        )
    return str(pid)


async def _system_id(pool, code: str):
    return (await GraphSchemasRepo(pool).get_system_template_by_code(code)).schema_id


async def test_apply_adopt_scaffolds_project_schema(pool):
    await _reset(pool)
    owner = uuid4()
    project_id = await _make_project(pool, owner)
    src = await _system_id(pool, "xianxia-harem")
    schemas, mutations, projects = (
        GraphSchemasRepo(pool), OntologyMutationsRepo(pool), ProjectsRepo(pool),
    )
    glossary = FakeGlossaryOntologyClient(user_kinds={str(owner): _XIANXIA_REQUIRED})

    out = await apply_adopt(
        mutations, projects, glossary,
        owner=owner, project_id=project_id, params=AdoptParams(source_schema_id=str(src)),
    )
    assert out["adopted"] is True
    # A project-scoped schema now exists (the scaffold).
    active = await schemas.active_project_schema(project_id)
    assert active is not None and str(active.schema_id) == out["schema_id"]


async def test_apply_adopt_blocks_on_missing_required_kind(pool):
    await _reset(pool)
    owner = uuid4()
    project_id = await _make_project(pool, owner)
    src = await _system_id(pool, "xianxia-harem")
    mutations, projects = OntologyMutationsRepo(pool), ProjectsRepo(pool)
    # glossary missing 'technique' → required gate blocks.
    glossary = FakeGlossaryOntologyClient(user_kinds={str(owner): _XIANXIA_REQUIRED[:-1]})

    with pytest.raises(AdoptNeedsGlossary) as ei:
        await apply_adopt(
            mutations, projects, glossary,
            owner=owner, project_id=project_id, params=AdoptParams(source_schema_id=str(src)),
        )
    assert "technique" in ei.value.kinds


async def test_apply_adopt_is_replace_on_adopt(pool):
    await _reset(pool)
    owner = uuid4()
    project_id = await _make_project(pool, owner)
    src = await _system_id(pool, "xianxia-harem")
    schemas, mutations, projects = (
        GraphSchemasRepo(pool), OntologyMutationsRepo(pool), ProjectsRepo(pool),
    )
    glossary = FakeGlossaryOntologyClient(user_kinds={str(owner): _XIANXIA_REQUIRED})
    params = AdoptParams(source_schema_id=str(src))

    first = await apply_adopt(mutations, projects, glossary, owner=owner, project_id=project_id, params=params)
    second = await apply_adopt(mutations, projects, glossary, owner=owner, project_id=project_id, params=params)
    assert first["schema_id"] != second["schema_id"]  # fresh copy each time
    # Still exactly ONE active project schema (replace-on-adopt invariant).
    async with pool.acquire() as conn:
        n = await conn.fetchval(
            "SELECT count(*) FROM kg_graph_schemas WHERE scope='project' AND scope_id=$1 "
            "AND deprecated_at IS NULL", project_id,
        )
    assert n == 1


async def test_preview_adopt_renders_summary_and_replace_flag(pool):
    await _reset(pool)
    owner = uuid4()
    project_id = await _make_project(pool, owner)
    src = await _system_id(pool, "xianxia-harem")
    schemas, mutations, projects = (
        GraphSchemasRepo(pool), OntologyMutationsRepo(pool), ProjectsRepo(pool),
    )
    glossary = FakeGlossaryOntologyClient(user_kinds={str(owner): _XIANXIA_REQUIRED})
    params = AdoptParams(source_schema_id=str(src))

    pv = await preview_adopt(schemas, mutations, projects, glossary,
                             owner=owner, project_id=project_id, params=params)
    assert pv["descriptor"] == "kg_adopt" and pv["blocked"] is False
    rows = {r["label"]: r["value"] for r in pv["preview_rows"]}
    assert rows["replaces current schema"] == "no"

    # After adopting, preview reflects that a re-adopt would REPLACE.
    await apply_adopt(mutations, projects, glossary, owner=owner, project_id=project_id, params=params)
    pv2 = await preview_adopt(schemas, mutations, projects, glossary,
                              owner=owner, project_id=project_id, params=params)
    rows2 = {r["label"]: r["value"] for r in pv2["preview_rows"]}
    assert rows2["replaces current schema"] == "yes" and pv2["destructive"] is True


async def test_preview_adopt_flags_glossary_gap(pool):
    await _reset(pool)
    owner = uuid4()
    project_id = await _make_project(pool, owner)
    src = await _system_id(pool, "xianxia-harem")
    schemas, mutations, projects = (
        GraphSchemasRepo(pool), OntologyMutationsRepo(pool), ProjectsRepo(pool),
    )
    glossary = FakeGlossaryOntologyClient(user_kinds={str(owner): _XIANXIA_REQUIRED[:-1]})  # missing one
    pv = await preview_adopt(schemas, mutations, projects, glossary,
                             owner=owner, project_id=project_id, params=AdoptParams(source_schema_id=str(src)))
    assert pv["blocked"] is True
    assert any("glossary gap" in r["label"] for r in pv["preview_rows"])
