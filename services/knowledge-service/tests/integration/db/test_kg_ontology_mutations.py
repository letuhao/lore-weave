"""Lane LC integration tests — adopt (copy-down) + sync + per-tier CRUD + tenancy.

Requires a real Postgres (TEST_KNOWLEDGE_DB_URL); skips otherwise via the shared
`pool` fixture. Re-seeds the System templates each test and TRUNCATEs the kg
tables, mirroring `test_kg_graph_schemas.py`.

Two layers:
  * **Repo** (`OntologyMutationsRepo`) directly — adopt copy-down + idempotent
    re-adopt, adopt-gate, sync diff/apply (+ 409), child CRUD additive +
    deprecate.
  * **Route** (FastAPI + overridden grant deps) — adopt-gate 422 `NeedsGlossary`,
    cross-tenant deny, system-tier read-only (403) + system create 501.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.auth.grant_deps import project_meta_dep
from app.clients.glossary_ontology_client import FakeGlossaryOntologyClient
from app.db.repositories.graph_schemas import GraphSchemasRepo
from app.db.repositories.ontology_mutations import (
    ChildNotFoundError,
    DuplicateChildError,
    NeedsGlossaryError,
    OntologyMutationsRepo,
    SchemaNotWritableError,
    SyncConflictError,
)
from app.db.seed_graph_schemas import seed_system_graph_schemas
from app.deps import get_grant_client, get_projects_repo
from app.middleware.jwt_auth import get_current_user
from app.routers.public.ontology import (
    get_glossary_ontology_client,
    get_ontology_mutations_repo,
    router,
)

# asyncio_mode=auto (pytest.ini) auto-marks the `async def` tests; the route
# tests below are plain `def` (sync TestClient) so they must NOT carry the
# asyncio marker. We DO carry an xdist_group so every test here (they TRUNCATE +
# re-seed the shared dev Postgres) serializes onto ONE worker under `-n auto`
# (CLAUDE.md test-parallelization rule) — xdist_group is orthogonal to asyncio.
pytestmark = pytest.mark.xdist_group("pg")

# the xianxia-harem required kinds — a glossary with all of these passes adopt.
_XIANXIA_REQUIRED = ["character", "organization", "location", "concept", "technique"]


async def _reset_kg(pool):
    async with pool.acquire() as conn:
        await conn.execute("TRUNCATE kg_graph_schemas RESTART IDENTITY CASCADE")
        await conn.execute("TRUNCATE kg_views, kg_triage_items RESTART IDENTITY CASCADE")
        await conn.execute("TRUNCATE knowledge_projects RESTART IDENTITY CASCADE")
    await seed_system_graph_schemas(pool)


async def _system_id(pool, code: str):
    return (await GraphSchemasRepo(pool).get_system_template_by_code(code)).schema_id


# ── adopt (copy-down) ──────────────────────────────────────────────────────
async def test_adopt_copies_schema_and_children(pool):
    await _reset_kg(pool)
    repo = OntologyMutationsRepo(pool)
    src = await _system_id(pool, "xianxia-harem")
    project_id = f"proj-{uuid4()}"
    result = await repo.adopt(
        owner_user_id=uuid4(),
        project_id=project_id,
        source_schema_id=src,
        glossary_kinds=set(_XIANXIA_REQUIRED + ["item", "event", "relationship"]),
        book_id="book-1",
    )
    new = result.schema
    assert new.scope == "project" and new.scope_id == project_id
    assert new.code == "xianxia-harem"
    assert new.source_ref == f"system:{src}"
    assert new.source_hash and new.content_hash == new.source_hash  # fresh copy == source

    # all children copied
    tree = await GraphSchemasRepo(pool).get_tree(uuid4(), new.schema_id, project_id=project_id)
    assert len(tree["edge_types"]) == 24
    assert len(tree["fact_types"]) == 9
    assert len(tree["node_kinds"]) == 8
    assert len(tree["vocab_values"]["drive"]) == 16
    assert result.missing_optional == []


async def _insert_user_schema(pool, owner_user_id, *, code="my-tpl", with_drive=None):
    """Insert a user-tier schema (optionally a `drive` vocab set + values) and
    return its schema_id. `with_drive` = list of (code, label) value tuples."""
    async with pool.acquire() as conn:
        sid = await conn.fetchval(
            "INSERT INTO kg_graph_schemas (scope, scope_id, code, name, content_hash) "
            "VALUES ('user', $1, $2, 'Mine', 'h0') RETURNING schema_id",
            str(owner_user_id), code,
        )
        if with_drive is not None:
            set_id = await conn.fetchval(
                "INSERT INTO kg_vocab_sets (schema_id, code, label, closed) "
                "VALUES ($1, 'drive', 'Drive', true) RETURNING vocab_set_id",
                sid,
            )
            for vcode, vlabel in with_drive:
                await conn.execute(
                    "INSERT INTO kg_vocab_values (vocab_set_id, code, label) VALUES ($1, $2, $3)",
                    set_id, vcode, vlabel,
                )
    return sid


async def test_HIGH_adopt_rejects_foreign_user_tier_source(pool):
    """review-impl HIGH: a user cannot adopt (deep-copy/read) another user's
    private user-tier template by passing its UUID."""
    await _reset_kg(pool)
    repo = OntologyMutationsRepo(pool)
    owner_a = uuid4()
    user_b = uuid4()
    src = await _insert_user_schema(pool, owner_a, code="a-private")
    # user B tries to adopt A's private template → not-found (no cross-tenant read)
    with pytest.raises(SchemaNotWritableError):
        await repo.adopt(
            owner_user_id=user_b, project_id=f"proj-{uuid4()}",
            source_schema_id=src, glossary_kinds=set(), book_id=None,
        )
    # owner A CAN adopt their own template
    res = await repo.adopt(
        owner_user_id=owner_a, project_id=f"proj-{uuid4()}",
        source_schema_id=src, glossary_kinds=set(), book_id=None,
    )
    assert res.schema.code == "a-private"


async def test_HIGH_sync_added_vocab_set_brings_its_values(pool):
    """review-impl HIGH: taking a newly-added upstream vocab_set must copy its
    VALUES too — not leave an empty closed set."""
    await _reset_kg(pool)
    repo = OntologyMutationsRepo(pool)
    owner = uuid4()
    src = await _insert_user_schema(pool, owner, code="src-tpl")  # no vocab yet
    adopted = await repo.adopt(
        owner_user_id=owner, project_id=f"proj-{uuid4()}",
        source_schema_id=src, glossary_kinds=set(), book_id=None,
    )
    pc = adopted.schema.schema_id
    # add a drive set + 2 values to the SOURCE
    async with pool.acquire() as conn:
        set_id = await conn.fetchval(
            "INSERT INTO kg_vocab_sets (schema_id, code, label, closed) "
            "VALUES ($1, 'drive', 'Drive', true) RETURNING vocab_set_id", src,
        )
        await conn.execute(
            "INSERT INTO kg_vocab_values (vocab_set_id, code, label) VALUES ($1,'revenge','Revenge'),($1,'love','Love')",
            set_id,
        )
    diff = await repo.sync_diff(pc)
    assert diff["has_updates"]
    await repo.sync_apply(
        pc, base_source_hash=diff["source_hash_current"],
        decisions=[{"node_type": "vocab_set", "code": "drive", "choice": "take_theirs"}],
    )
    tree = await GraphSchemasRepo(pool).get_tree(owner, pc, project_id=adopted.schema.scope_id)
    assert sorted(v.code for v in tree["vocab_values"].get("drive", [])) == ["love", "revenge"]


async def test_HIGH_sync_removed_vocab_value_deprecates_not_deletes(pool):
    """review-impl HIGH (A4): removed_upstream vocab_value is deprecated, not
    hard-deleted; it leaves the resolved schema but the row survives."""
    await _reset_kg(pool)
    repo = OntologyMutationsRepo(pool)
    owner = uuid4()
    src = await _insert_user_schema(pool, owner, code="src2", with_drive=[("revenge", "Revenge"), ("love", "Love")])
    adopted = await repo.adopt(
        owner_user_id=owner, project_id=f"proj-{uuid4()}",
        source_schema_id=src, glossary_kinds=set(), book_id=None,
    )
    pc = adopted.schema.schema_id
    # remove 'love' from the source
    async with pool.acquire() as conn:
        await conn.execute(
            "DELETE FROM kg_vocab_values WHERE code='love' AND vocab_set_id IN "
            "(SELECT vocab_set_id FROM kg_vocab_sets WHERE schema_id=$1)", src,
        )
    diff = await repo.sync_diff(pc)
    await repo.sync_apply(
        pc, base_source_hash=diff["source_hash_current"],
        decisions=[{"node_type": "vocab_value", "parent_code": "drive", "code": "love", "choice": "take_theirs"}],
    )
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT deprecated_at FROM kg_vocab_values WHERE code='love' AND vocab_set_id IN "
            "(SELECT vocab_set_id FROM kg_vocab_sets WHERE schema_id=$1)", pc,
        )
    assert row is not None and row["deprecated_at"] is not None  # deprecated, NOT deleted
    # excluded from the resolved/read schema
    tree = await GraphSchemasRepo(pool).get_tree(owner, pc, project_id=adopted.schema.scope_id)
    assert "love" not in {v.code for v in tree["vocab_values"].get("drive", [])}


async def test_MED_concurrent_adopt_is_race_safe(pool):
    """review-impl MED (TOCTOU): two adopts racing on one project must not leave
    two active schemas or raise."""
    import asyncio

    await _reset_kg(pool)
    repo = OntologyMutationsRepo(pool)
    project_id = f"proj-{uuid4()}"
    kinds = set(_XIANXIA_REQUIRED + ["item", "event", "relationship"])
    src = await _system_id(pool, "xianxia-harem")
    results = await asyncio.gather(
        repo.adopt(owner_user_id=uuid4(), project_id=project_id, source_schema_id=src, glossary_kinds=kinds, book_id=None),
        repo.adopt(owner_user_id=uuid4(), project_id=project_id, source_schema_id=src, glossary_kinds=kinds, book_id=None),
        return_exceptions=True,
    )
    for r in results:
        assert not isinstance(r, Exception), f"concurrent adopt raised: {r!r}"
    async with pool.acquire() as conn:
        n = await conn.fetchval(
            "SELECT count(*) FROM kg_graph_schemas WHERE scope='project' AND scope_id=$1 AND deprecated_at IS NULL",
            project_id,
        )
    assert n == 1  # exactly one active project schema


async def test_readopt_replaces_active_schema(pool):
    """Re-adopt deprecates the prior active project schema (one-active invariant)."""
    await _reset_kg(pool)
    repo = OntologyMutationsRepo(pool)
    project_id = f"proj-{uuid4()}"
    kinds = set(_XIANXIA_REQUIRED + ["item", "event", "relationship"])
    first = await repo.adopt(
        owner_user_id=uuid4(), project_id=project_id,
        source_schema_id=await _system_id(pool, "xianxia-harem"),
        glossary_kinds=kinds, book_id=None,
    )
    second = await repo.adopt(
        owner_user_id=uuid4(), project_id=project_id,
        source_schema_id=await _system_id(pool, "general"),
        glossary_kinds=set(), book_id=None,
    )
    assert second.schema.schema_id != first.schema.schema_id
    # exactly one active project schema, and it's the latest (general).
    async with pool.acquire() as conn:
        active = await conn.fetch(
            "SELECT code FROM kg_graph_schemas "
            "WHERE scope='project' AND scope_id=$1 AND deprecated_at IS NULL",
            project_id,
        )
    assert [r["code"] for r in active] == ["general"]
    resolved = await GraphSchemasRepo(pool).resolve_for_project(project_id)
    assert resolved.allow_free_edges is True  # general


async def test_adopt_gate_blocks_missing_required(pool):
    await _reset_kg(pool)
    repo = OntologyMutationsRepo(pool)
    src = await _system_id(pool, "xianxia-harem")
    # glossary missing 'technique' (a required kind) → block
    with pytest.raises(NeedsGlossaryError) as exc:
        await repo.adopt(
            owner_user_id=uuid4(), project_id=f"proj-{uuid4()}",
            source_schema_id=src,
            glossary_kinds={"character", "organization", "location", "concept"},
            book_id="book-9",
        )
    assert "technique" in exc.value.kinds
    assert exc.value.book_id == "book-9"


async def test_adopt_proceeds_when_only_optional_missing(pool):
    await _reset_kg(pool)
    repo = OntologyMutationsRepo(pool)
    src = await _system_id(pool, "xianxia-harem")
    result = await repo.adopt(
        owner_user_id=uuid4(), project_id=f"proj-{uuid4()}",
        source_schema_id=src,
        glossary_kinds=set(_XIANXIA_REQUIRED),  # required present, optional absent
        book_id=None,
    )
    assert result.schema.schema_id is not None
    assert set(result.missing_optional) == {"item", "event", "relationship"}


# ── sync (diff / apply) ─────────────────────────────────────────────────────
async def _adopt_xianxia(pool, repo) -> tuple[str, "UUID"]:
    project_id = f"proj-{uuid4()}"
    res = await repo.adopt(
        owner_user_id=uuid4(), project_id=project_id,
        source_schema_id=await _system_id(pool, "xianxia-harem"),
        glossary_kinds=set(_XIANXIA_REQUIRED + ["item", "event", "relationship"]),
        book_id=None,
    )
    return project_id, res.schema.schema_id


async def test_sync_no_updates_when_source_unchanged(pool):
    await _reset_kg(pool)
    repo = OntologyMutationsRepo(pool)
    _project_id, proj_schema = await _adopt_xianxia(pool, repo)
    diff = await repo.sync_diff(proj_schema)
    assert diff["has_updates"] is False
    assert diff["changes"] == []


async def test_sync_detects_added_modified_removed(pool):
    await _reset_kg(pool)
    repo = OntologyMutationsRepo(pool)
    _project_id, proj_schema = await _adopt_xianxia(pool, repo)
    src = await _system_id(pool, "xianxia-harem")
    # upstream: add an edge, modify another's label, and delete (hard) one so
    # the project copy has a type upstream no longer has (removed_upstream).
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO kg_edge_types (schema_id, code, label) VALUES ($1, 'SWORN_SIBLING_OF', 'sworn sibling of')",
            src,
        )
        await conn.execute(
            "UPDATE kg_edge_types SET label = 'lover (updated)' WHERE schema_id = $1 AND code = 'LOVER_OF'",
            src,
        )
        await conn.execute("DELETE FROM kg_edge_types WHERE schema_id = $1 AND code = 'WIELDS'", src)
    diff = await repo.sync_diff(proj_schema)
    assert diff["has_updates"] is True
    by = {(c["node_type"], c["code"]): c["change"] for c in diff["changes"]}
    assert by[("edge_type", "SWORN_SIBLING_OF")] == "added"
    assert by[("edge_type", "LOVER_OF")] == "modified"
    assert by[("edge_type", "WIELDS")] == "removed_upstream"


async def test_sync_apply_take_theirs_and_keep_mine(pool):
    await _reset_kg(pool)
    repo = OntologyMutationsRepo(pool)
    _project_id, proj_schema = await _adopt_xianxia(pool, repo)
    src = await _system_id(pool, "xianxia-harem")
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO kg_edge_types (schema_id, code, label) VALUES ($1, 'SWORN_SIBLING_OF', 'sworn sibling of')",
            src,
        )
        await conn.execute(
            "UPDATE kg_edge_types SET label = 'lover (updated)' WHERE schema_id = $1 AND code = 'LOVER_OF'",
            src,
        )
    diff = await repo.sync_diff(proj_schema)
    base = diff["source_hash_current"]
    out = await repo.sync_apply(
        proj_schema,
        base_source_hash=base,
        decisions=[
            {"node_type": "edge_type", "code": "SWORN_SIBLING_OF", "choice": "take_theirs"},
            {"node_type": "edge_type", "code": "LOVER_OF", "choice": "keep_mine"},
        ],
    )
    assert out["applied"] == 1
    assert out["source_hash"] == base
    async with pool.acquire() as conn:
        added = await conn.fetchrow(
            "SELECT label FROM kg_edge_types WHERE schema_id = $1 AND code = 'SWORN_SIBLING_OF'", proj_schema
        )
        lover = await conn.fetchrow(
            "SELECT label FROM kg_edge_types WHERE schema_id = $1 AND code = 'LOVER_OF'", proj_schema
        )
    assert added is not None  # take_theirs landed
    assert lover["label"] == "lover of"  # keep_mine — unchanged
    # source_hash refrozen → no further updates
    assert (await repo.sync_diff(proj_schema))["has_updates"] is False


async def test_sync_apply_conflict_on_stale_base_hash(pool):
    await _reset_kg(pool)
    repo = OntologyMutationsRepo(pool)
    _project_id, proj_schema = await _adopt_xianxia(pool, repo)
    src = await _system_id(pool, "xianxia-harem")
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE kg_edge_types SET label = 'moved' WHERE schema_id = $1 AND code = 'LOVER_OF'", src
        )
    with pytest.raises(SyncConflictError):
        await repo.sync_apply(proj_schema, base_source_hash="stale-hash", decisions=[])


# ── re-adopt loss preview (D-KG-LC-REVADOPT-LOSS) ────────────────────────────
async def test_adopt_preview_surfaces_customizations_as_losses(pool):
    await _reset_kg(pool)
    repo = OntologyMutationsRepo(pool)
    owner = uuid4()
    project_id = f"proj-{uuid4()}"
    src = await _system_id(pool, "xianxia-harem")
    res = await repo.adopt(
        owner_user_id=owner, project_id=project_id, source_schema_id=src,
        glossary_kinds=set(_XIANXIA_REQUIRED + ["item", "event", "relationship"]),
        book_id=None,
    )
    proj_schema = res.schema.schema_id
    # customize the project copy: add a user-only edge (a loss on re-adopt).
    await repo.add_edge_type(proj_schema, code="MY_CUSTOM_EDGE", label="my custom")

    preview = await repo.compute_adopt_preview(
        owner_user_id=owner, project_id=project_id,
        current_schema_id=proj_schema, incoming_source_id=src,
    )
    assert preview["has_current"] is True
    losses = preview["would_lose"]
    assert any(
        c["node_type"] == "edge_type" and c["code"] == "MY_CUSTOM_EDGE"
        and c["change"] == "removed_upstream"
        for c in losses
    )


async def test_adopt_preview_empty_when_no_current_schema(pool):
    await _reset_kg(pool)
    repo = OntologyMutationsRepo(pool)
    src = await _system_id(pool, "xianxia-harem")
    preview = await repo.compute_adopt_preview(
        owner_user_id=uuid4(), project_id=f"proj-{uuid4()}",
        current_schema_id=None, incoming_source_id=src,
    )
    assert preview == {"has_current": False, "would_lose": []}


async def test_adopt_preview_rejects_unvisible_source(pool):
    await _reset_kg(pool)
    repo = OntologyMutationsRepo(pool)
    # another tenant's user-tier template — not adoptable by this caller/project.
    async with pool.acquire() as conn:
        other_src = await conn.fetchval(
            "INSERT INTO kg_graph_schemas (scope, scope_id, code, name) "
            "VALUES ('user', $1, 'private', 'Private') RETURNING schema_id",
            str(uuid4()),
        )
    with pytest.raises(SchemaNotWritableError):
        await repo.compute_adopt_preview(
            owner_user_id=uuid4(), project_id=f"proj-{uuid4()}",
            current_schema_id=None, incoming_source_id=other_src,
        )


# ── child CRUD ──────────────────────────────────────────────────────────────
async def test_child_crud_additive_and_deprecate(pool):
    await _reset_kg(pool)
    repo = OntologyMutationsRepo(pool)
    _project_id, proj_schema = await _adopt_xianxia(pool, repo)
    before = (await repo.get_schema(proj_schema)).schema_version

    edge = await repo.add_edge_type(proj_schema, code="OWES_DEBT_TO", label="owes debt to")
    assert edge["code"] == "OWES_DEBT_TO"
    after = (await repo.get_schema(proj_schema)).schema_version
    assert after == before + 1  # bumped

    fact = await repo.add_fact_type(proj_schema, code="ascension", label="Ascension")
    assert fact["code"] == "ascension"
    nk = await repo.add_node_kind(proj_schema, kind_code="beast", strength="optional")
    assert nk["kind_code"] == "beast"
    vv = await repo.add_vocab_value(proj_schema, set_code="drive", code="curiosity", label="Curiosity")
    assert vv["code"] == "curiosity"

    # duplicate → DuplicateChildError
    with pytest.raises(DuplicateChildError):
        await repo.add_edge_type(proj_schema, code="OWES_DEBT_TO", label="dup")

    # deprecate-only (never hard-drop)
    await repo.deprecate_edge_type(proj_schema, "OWES_DEBT_TO")
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT deprecated_at FROM kg_edge_types WHERE schema_id = $1 AND code = 'OWES_DEBT_TO'", proj_schema
        )
    assert row["deprecated_at"] is not None  # soft-deprecated, still present

    with pytest.raises(ChildNotFoundError):
        await repo.deprecate_fact_type(proj_schema, "does_not_exist")


# ── A1: revive-on-recreate, PATCH (attr-only), tier-aware DELETE ─────────────
async def test_A1_revive_on_recreate_keeps_one_row(pool):
    """EC-A1: deprecate a child then re-create the same code succeeds (revive +
    overwrite), NOT a 409 — and leaves exactly one row (the graph-data ref key)."""
    await _reset_kg(pool)
    repo = OntologyMutationsRepo(pool)
    _pid, proj = await _adopt_xianxia(pool, repo)
    await repo.add_edge_type(proj, code="OWES_DEBT_TO", label="owes debt to")
    await repo.delete_child(proj, node_type="edge_type", code="OWES_DEBT_TO")  # project → soft
    async with pool.acquire() as conn:
        dep = await conn.fetchval(
            "SELECT deprecated_at FROM kg_edge_types WHERE schema_id=$1 AND code='OWES_DEBT_TO'", proj
        )
    assert dep is not None  # soft-deprecated
    again = await repo.add_edge_type(proj, code="OWES_DEBT_TO", label="owes a debt to")
    assert again["label"] == "owes a debt to" and again["deprecated_at"] is None
    async with pool.acquire() as conn:
        n = await conn.fetchval(
            "SELECT count(*) FROM kg_edge_types WHERE schema_id=$1 AND code='OWES_DEBT_TO'", proj
        )
    assert n == 1  # revived, not duplicated


async def test_A1_duplicate_live_code_still_409s(pool):
    """Revive applies only to a DEPRECATED row; a LIVE duplicate still raises."""
    await _reset_kg(pool)
    repo = OntologyMutationsRepo(pool)
    _pid, proj = await _adopt_xianxia(pool, repo)
    await repo.add_edge_type(proj, code="OWES_DEBT_TO", label="owes debt to")
    with pytest.raises(DuplicateChildError):
        await repo.add_edge_type(proj, code="OWES_DEBT_TO", label="dup")


async def test_A1_patch_edge_type_attrs_and_bump(pool):
    await _reset_kg(pool)
    repo = OntologyMutationsRepo(pool)
    _pid, proj = await _adopt_xianxia(pool, repo)
    before = (await repo.get_schema(proj)).schema_version
    out = await repo.patch_edge_type(
        proj, "LOVER_OF", updates={"label": "beloved of", "cardinality": "single_active"}
    )
    assert out["label"] == "beloved of" and out["cardinality"] == "single_active"
    after = (await repo.get_schema(proj)).schema_version
    assert after == before + 1  # bumped + rehashed (EC-A7)
    # empty updates → no-op, no version bump
    same = await repo.patch_edge_type(proj, "LOVER_OF", updates={})
    assert same["label"] == "beloved of"
    assert (await repo.get_schema(proj)).schema_version == after
    with pytest.raises(ChildNotFoundError):
        await repo.patch_edge_type(proj, "NO_SUCH_EDGE", updates={"label": "x"})


async def test_A1_patch_node_kind_vocab_set_and_value(pool):
    await _reset_kg(pool)
    repo = OntologyMutationsRepo(pool)
    _pid, proj = await _adopt_xianxia(pool, repo)
    nk = await repo.patch_node_kind(proj, "character", strength="optional")  # was required
    assert nk["strength"] == "optional"
    vs = await repo.add_vocab_set(proj, code="tone", label="Tone")
    assert vs["code"] == "tone"
    v = await repo.add_vocab_value(proj, set_code="tone", code="grim", label="Grim")
    assert v["code"] == "grim"
    pv = await repo.patch_vocab_value(
        proj, "tone", "grim", updates={"label": "Grimdark", "metadata": {"axis": "mood"}}
    )
    assert pv["label"] == "Grimdark" and pv["metadata"] == {"axis": "mood"}
    ps = await repo.patch_vocab_set(proj, "tone", updates={"closed": False})
    assert ps["closed"] is False


async def test_A1_delete_project_soft_user_hard(pool):
    """EC-A5: DELETE deprecates on a PROJECT schema (queryable graph data) but
    HARD-deletes on a USER-tier template (never extracted)."""
    await _reset_kg(pool)
    repo = OntologyMutationsRepo(pool)
    # project schema → soft
    _pid, proj = await _adopt_xianxia(pool, repo)
    await repo.add_fact_type(proj, code="ascension", label="Ascension")
    await repo.delete_child(proj, node_type="fact_type", code="ascension")
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT deprecated_at FROM kg_fact_types WHERE schema_id=$1 AND code='ascension'", proj
        )
    assert row is not None and row["deprecated_at"] is not None  # soft

    # user-tier template → hard (row gone)
    owner = uuid4()
    tpl = await _insert_user_schema(pool, owner, code="u-tpl")
    await repo.add_fact_type(tpl, code="ritual", label="Ritual")
    await repo.delete_child(tpl, node_type="fact_type", code="ritual")
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT 1 FROM kg_fact_types WHERE schema_id=$1 AND code='ritual'", tpl
        )
    assert row is None  # hard-deleted


async def test_A1_delete_vocab_set_hard_cascades_values(pool):
    """A user-tier vocab-set hard-delete cascades its values (FK ON DELETE CASCADE)."""
    await _reset_kg(pool)
    repo = OntologyMutationsRepo(pool)
    owner = uuid4()
    tpl = await _insert_user_schema(pool, owner, code="u-tpl2")
    await repo.add_vocab_set(tpl, code="drive", label="Drive")
    await repo.add_vocab_value(tpl, set_code="drive", code="revenge", label="Revenge")
    await repo.delete_child(tpl, node_type="vocab_set", code="drive")
    async with pool.acquire() as conn:
        sets = await conn.fetchval("SELECT count(*) FROM kg_vocab_sets WHERE schema_id=$1", tpl)
        vals = await conn.fetchval(
            "SELECT count(*) FROM kg_vocab_values v JOIN kg_vocab_sets s ON s.vocab_set_id=v.vocab_set_id "
            "WHERE s.schema_id=$1", tpl
        )
    assert sets == 0 and vals == 0  # set + values gone


async def test_A1_delete_vocab_value_by_parent_set(pool):
    await _reset_kg(pool)
    repo = OntologyMutationsRepo(pool)
    _pid, proj = await _adopt_xianxia(pool, repo)
    await repo.add_vocab_value(proj, set_code="drive", code="curiosity", label="Curiosity")
    await repo.delete_child(
        proj, node_type="vocab_value", code="curiosity", parent_set_code="drive"
    )
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT v.deprecated_at FROM kg_vocab_values v JOIN kg_vocab_sets s "
            "ON s.vocab_set_id=v.vocab_set_id WHERE s.schema_id=$1 AND v.code='curiosity'", proj
        )
    assert row is not None and row["deprecated_at"] is not None  # project → soft


async def test_system_tier_is_read_only(pool):
    await _reset_kg(pool)
    repo = OntologyMutationsRepo(pool)
    src = await _system_id(pool, "xianxia-harem")
    with pytest.raises(SchemaNotWritableError):
        await repo.add_edge_type(src, code="X", label="x")
    with pytest.raises(SchemaNotWritableError):
        await repo.patch_schema(src, name="hacked")
    with pytest.raises(SchemaNotWritableError):
        await repo.deprecate_schema(src)


# ── route-level: adopt-gate 422, tenancy deny, system 501 ───────────────────
# These exercise the FastAPI wiring (grant gate → glossary cross-check → repo
# error→HTTP mapping). They use an in-memory FAKE mutations repo so the
# TestClient's own event loop never drives the function-scoped asyncpg pool
# (which is bound to the pytest-asyncio loop) — that cross-loop mix is the
# `another operation in progress` trap. DB-backed behavior is covered above.
from datetime import datetime, timezone  # noqa: E402
from uuid import UUID  # noqa: E402

from app.db.ontology_models import GraphSchema  # noqa: E402
from app.db.repositories.ontology_mutations import AdoptResult  # noqa: E402


def _schema(scope: str, scope_id: str | None, code: str = "xianxia-harem") -> GraphSchema:
    now = datetime.now(timezone.utc)
    return GraphSchema(
        schema_id=uuid4(), scope=scope, scope_id=scope_id, code=code, name=code,
        created_at=now, updated_at=now,
    )


class FakeMutationsRepo:
    """Loop-free in-memory stand-in for OntologyMutationsRepo (route tests only).

    `required_kinds` drives the adopt-gate; `schemas` maps schema_id→GraphSchema
    for the writable-tier check on PATCH/DELETE/CRUD routes.
    """

    def __init__(self, *, required_kinds=None, schemas=None):
        self._required = list(required_kinds or [])
        self._schemas: dict[UUID, GraphSchema] = schemas or {}

    async def get_schema(self, schema_id):
        return self._schemas.get(schema_id)

    async def required_node_kinds(self, schema_id):
        return list(self._required)

    async def adopt(self, *, owner_user_id, project_id, source_schema_id, glossary_kinds, book_id):
        missing = sorted(k for k in self._required if k not in glossary_kinds)
        if missing:
            raise NeedsGlossaryError(missing, book_id)
        return AdoptResult(_schema("project", project_id), [])

    async def patch_schema(self, schema_id, **kw):
        return self._schemas[schema_id]


def _client(*, caller, project_meta, grant_level, glossary, mutations):
    class _FakeGrant:
        async def resolve_grant(self, book_id, user_id):
            return grant_level

    class _StubProjects:
        async def project_meta(self, project_id):
            return project_meta

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: caller
    app.dependency_overrides[get_ontology_mutations_repo] = lambda: mutations
    app.dependency_overrides[get_projects_repo] = lambda: _StubProjects()
    app.dependency_overrides[project_meta_dep] = lambda: project_meta
    app.dependency_overrides[get_grant_client] = lambda: _FakeGrant()
    app.dependency_overrides[get_glossary_ontology_client] = lambda: glossary
    return TestClient(app)


def test_route_adopt_gate_422():
    from app.clients.grant_client import GrantLevel

    owner, book, project_id, src = uuid4(), uuid4(), uuid4(), uuid4()
    glossary = FakeGlossaryOntologyClient(
        book_kinds={str(book): ["character", "organization", "location", "concept"]}
    )
    # Adopt now AUTO-SEEDS the missing kind (KM6-M2 auto-create-glossary, 2a4d3337d),
    # so the gate only 422s on the RESIDUAL path where the seed itself can't heal it.
    # Force that by making the book-tier seed write fail (transport/outage) — mirrors
    # the unit test's `test_seed_failure_reraises`.
    async def _seed_fails(*_a, **_k):
        return False

    glossary.adopt_book_kinds = _seed_fails  # type: ignore[assignment]
    client = _client(
        caller=owner, project_meta=(owner, book), grant_level=GrantLevel.OWNER,
        glossary=glossary, mutations=FakeMutationsRepo(required_kinds=_XIANXIA_REQUIRED),
    )
    r = client.post(f"/v1/kg/projects/{project_id}/adopt", json={"source_schema_id": str(src)})
    assert r.status_code == 422, r.text
    detail = r.json()["detail"]
    assert detail["code"] == "KG_ADOPT_NEEDS_GLOSSARY"
    assert "technique" in detail["needs_glossary"]["kinds"]
    assert detail["needs_glossary"]["book_id"] == str(book)


def test_route_adopt_succeeds_with_full_glossary():
    from app.clients.grant_client import GrantLevel

    owner, book, project_id, src = uuid4(), uuid4(), uuid4(), uuid4()
    glossary = FakeGlossaryOntologyClient(book_kinds={str(book): _XIANXIA_REQUIRED})
    client = _client(
        caller=owner, project_meta=(owner, book), grant_level=GrantLevel.OWNER,
        glossary=glossary, mutations=FakeMutationsRepo(required_kinds=_XIANXIA_REQUIRED),
    )
    r = client.post(f"/v1/kg/projects/{project_id}/adopt", json={"source_schema_id": str(src)})
    assert r.status_code == 201, r.text
    assert r.json()["scope"] == "project"


def test_route_cross_tenant_adopt_denied():
    from app.clients.grant_client import GrantLevel

    owner, attacker, book, project_id, src = uuid4(), uuid4(), uuid4(), uuid4(), uuid4()
    glossary = FakeGlossaryOntologyClient(book_kinds={str(book): _XIANXIA_REQUIRED})
    # attacker has NO grant on the owner's project → 404 (no existence oracle)
    client = _client(
        caller=attacker, project_meta=(owner, book), grant_level=GrantLevel.NONE,
        glossary=glossary, mutations=FakeMutationsRepo(required_kinds=_XIANXIA_REQUIRED),
    )
    r = client.post(f"/v1/kg/projects/{project_id}/adopt", json={"source_schema_id": str(src)})
    assert r.status_code == 404, r.text


def test_route_cross_tenant_adopt_preview_denied():
    """D-KG-LC-REVADOPT-LOSS: the read-only adopt/preview route is Manage-gated
    (resolve-to-owner) exactly like adopt — an attacker with no grant on the
    owner's project gets 404 (no existence oracle), and the gate fires before the
    handler ever deep-reads any template (compute_adopt_preview never called)."""
    from app.clients.grant_client import GrantLevel
    from app.routers.public.ontology import get_graph_schemas_repo

    owner, attacker, book, project_id, src = uuid4(), uuid4(), uuid4(), uuid4(), uuid4()
    mutations = FakeMutationsRepo(required_kinds=_XIANXIA_REQUIRED)
    client = _client(
        caller=attacker, project_meta=(owner, book), grant_level=GrantLevel.NONE,
        glossary=FakeGlossaryOntologyClient(), mutations=mutations,
    )
    # the preview route also depends on the graph-schemas repo — stub it so the
    # denial is proven without a live pool (the gate raises before this is used).
    client.app.dependency_overrides[get_graph_schemas_repo] = lambda: None
    r = client.post(
        f"/v1/kg/projects/{project_id}/adopt/preview",
        json={"source_schema_id": str(src)},
    )
    assert r.status_code == 404, r.text


def test_route_system_create_501():
    from app.clients.grant_client import GrantLevel

    client = _client(
        caller=uuid4(), project_meta=None, grant_level=GrantLevel.NONE,
        glossary=FakeGlossaryOntologyClient(), mutations=FakeMutationsRepo(),
    )
    r = client.post("/v1/kg/system/graph-schemas", json={})
    assert r.status_code == 501


def test_route_patch_system_schema_403():
    from app.clients.grant_client import GrantLevel

    sys_schema = _schema("system", None, "general")
    client = _client(
        caller=uuid4(), project_meta=None, grant_level=GrantLevel.NONE,
        glossary=FakeGlossaryOntologyClient(),
        mutations=FakeMutationsRepo(schemas={sys_schema.schema_id: sys_schema}),
    )
    r = client.patch(f"/v1/kg/graph-schemas/{sys_schema.schema_id}", json={"name": "hacked"})
    assert r.status_code == 403, r.text


def test_route_cross_tenant_user_schema_edit_404():
    """User B cannot PATCH user A's user-tier schema (owner==caller else 404)."""
    from app.clients.grant_client import GrantLevel

    user_a, user_b = uuid4(), uuid4()
    a_schema = _schema("user", str(user_a), "my-template")
    client = _client(
        caller=user_b, project_meta=None, grant_level=GrantLevel.NONE,
        glossary=FakeGlossaryOntologyClient(),
        mutations=FakeMutationsRepo(schemas={a_schema.schema_id: a_schema}),
    )
    r = client.patch(f"/v1/kg/graph-schemas/{a_schema.schema_id}", json={"name": "hacked"})
    assert r.status_code == 404, r.text
