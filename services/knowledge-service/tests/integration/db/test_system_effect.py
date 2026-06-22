"""KM5-M2 — System-tier template write effect integration tests (real Postgres).

Proves SystemTemplatesRepo + system_effect end-to-end: create lands a scope=system
row, duplicate code (incl. a seeded code) is rejected, patch bumps schema_version,
a stale expected_schema_version drifts, delete soft-deprecates, and the inverse
tenancy guard (`_load_system`) refuses to address a non-system row.
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from app.db.repositories.system_templates import (
    DuplicateSystemTemplate,
    SystemTemplateNotFound,
    SystemTemplatesRepo,
)
from app.db.seed_graph_schemas import seed_system_graph_schemas
from app.ontology.system_effect import (
    SystemEffectDrift,
    SystemTemplateParams,
    apply_system_template,
    preview_system_template,
)

pytestmark = pytest.mark.asyncio


async def _reset(pool):
    async with pool.acquire() as conn:
        await conn.execute("TRUNCATE kg_graph_schemas RESTART IDENTITY CASCADE")
        await conn.execute("TRUNCATE knowledge_projects RESTART IDENTITY CASCADE")
    await seed_system_graph_schemas(pool)


async def _create(repo, code="new-genre", name="New Genre"):
    return await apply_system_template(
        repo, SystemTemplateParams(verb="create", code=code, name=name, description="d"),
    )


# ── create ────────────────────────────────────────────────────────────────────
async def test_create_lands_system_row(pool):
    await _reset(pool)
    repo = SystemTemplatesRepo(pool)
    res = await _create(repo)
    assert res["applied"] is True and res["verb"] == "create"
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT scope, scope_id, name FROM kg_graph_schemas WHERE schema_id = $1",
            res["schema_id"],
        )
    assert row["scope"] == "system" and row["scope_id"] is None and row["name"] == "New Genre"


async def test_create_duplicate_code_rejected(pool):
    await _reset(pool)
    repo = SystemTemplatesRepo(pool)
    await _create(repo, code="dup")
    with pytest.raises(DuplicateSystemTemplate):
        await _create(repo, code="dup")


async def test_create_collides_with_seeded_code(pool):
    await _reset(pool)
    repo = SystemTemplatesRepo(pool)
    with pytest.raises(DuplicateSystemTemplate):
        await _create(repo, code="general")  # a code-seeded bootstrap template


# ── patch ─────────────────────────────────────────────────────────────────────
async def test_patch_bumps_version_and_renames(pool):
    await _reset(pool)
    repo = SystemTemplatesRepo(pool)
    created = await _create(repo)
    sid = created["schema_id"]
    res = await apply_system_template(
        repo,
        SystemTemplateParams(verb="patch", schema_id=sid, expected_schema_version=1, name="Renamed"),
    )
    assert res["schema_version"] == 2
    async with pool.acquire() as conn:
        name = await conn.fetchval("SELECT name FROM kg_graph_schemas WHERE schema_id = $1", sid)
    assert name == "Renamed"


async def test_patch_stale_version_drifts(pool):
    await _reset(pool)
    repo = SystemTemplatesRepo(pool)
    created = await _create(repo)
    with pytest.raises(SystemEffectDrift):
        await apply_system_template(
            repo,
            SystemTemplateParams(
                verb="patch", schema_id=created["schema_id"],
                expected_schema_version=99, name="X",
            ),
        )


async def test_patch_vanished_target_drifts(pool):
    await _reset(pool)
    repo = SystemTemplatesRepo(pool)
    with pytest.raises(SystemEffectDrift):
        await apply_system_template(
            repo,
            SystemTemplateParams(verb="patch", schema_id=str(uuid4()), expected_schema_version=1),
        )


# ── delete ──────────────────────────────────────────────────────────────────
async def test_delete_soft_deprecates(pool):
    await _reset(pool)
    repo = SystemTemplatesRepo(pool)
    created = await _create(repo)
    sid = created["schema_id"]
    res = await apply_system_template(repo, SystemTemplateParams(verb="delete", schema_id=sid))
    assert res["verb"] == "delete"
    async with pool.acquire() as conn:
        dep = await conn.fetchval(
            "SELECT deprecated_at FROM kg_graph_schemas WHERE schema_id = $1", sid
        )
    assert dep is not None


# ── inverse tenancy guard ─────────────────────────────────────────────────────
async def test_cannot_address_non_system_row(pool):
    await _reset(pool)
    repo = SystemTemplatesRepo(pool)
    # Insert a project-scope schema directly; the admin repo must NOT see/touch it.
    async with pool.acquire() as conn:
        proj_sid = await conn.fetchval(
            """
            INSERT INTO kg_graph_schemas (scope, scope_id, code, name, allow_free_edges)
            VALUES ('project', $1, 'p', 'Proj', true) RETURNING schema_id
            """,
            f"proj-{uuid4()}",
        )
    assert await repo.get_system_template(proj_sid) is None
    with pytest.raises(SystemTemplateNotFound):
        await repo.patch_template(proj_sid, name="hijack")
    with pytest.raises(SystemTemplateNotFound):
        await repo.deprecate_template(proj_sid)


# ── preview ────────────────────────────────────────────────────────────────
async def test_preview_create_flags_taken_code(pool):
    await _reset(pool)
    repo = SystemTemplatesRepo(pool)
    fresh = await preview_system_template(
        repo, SystemTemplateParams(verb="create", code="free-code", name="N"))
    assert fresh["drift"] is False
    taken = await preview_system_template(
        repo, SystemTemplateParams(verb="create", code="general", name="N"))
    assert taken["drift"] is True


async def test_preview_patch_flags_drift(pool):
    await _reset(pool)
    repo = SystemTemplatesRepo(pool)
    created = await _create(repo)
    stale = await preview_system_template(
        repo,
        SystemTemplateParams(verb="patch", schema_id=created["schema_id"],
                             expected_schema_version=99, name="X"),
    )
    assert stale["drift"] is True
