"""S-01 · structure_template authoring — real-DB repo tests.

Gated on TEST_COMPOSITION_DB_URL (a throwaway DB the fixture drops + rebuilds). The write side
never existed before S-01; these lock the load-bearing properties: TENANCY (partial-unique per
tier + cross-user isolation + built-ins read-only to users), OCC, and the archive/restore symmetry
that motif/arc-template lack.
"""

from __future__ import annotations

import os
import uuid

import asyncpg
import pytest

from app.db.migrate import run_migrations
from app.db.repositories.structure_templates import (
    DuplicateStructureTemplateName,
    StructureTemplatesRepo,
    StructureTemplateVersionConflict,
)

_DSN = os.environ.get("TEST_COMPOSITION_DB_URL")

pytestmark = [
    pytest.mark.skipif(not _DSN, reason="set TEST_COMPOSITION_DB_URL to a throwaway DB to run"),
    pytest.mark.xdist_group("pg"),
]

_TABLES = [
    "structure_node", "motif_application", "motif_link", "motif", "arc_template",
    "plan_bootstrap_proposal", "plan_artifact", "plan_run",
    "composition_daily_progress", "composition_progress_baseline",
    "style_profile", "voice_profile", "scene_grounding_pins", "reference_source",
    "decompose_commit", "outbox_events", "generation_correction", "generation_job",
    "narrative_thread", "canon_rule", "scene_link", "outline_node",
    "structure_template", "entity_override", "divergence_spec", "composition_work",
]


@pytest.fixture
async def pool():
    p = await asyncpg.create_pool(_DSN, min_size=1, max_size=4)
    try:
        async with p.acquire() as c:
            for t in _TABLES:
                await c.execute(f"DROP TABLE IF EXISTS {t} CASCADE")
        await run_migrations(p)
        yield p
    finally:
        async with p.acquire() as c:
            for t in _TABLES:
                await c.execute(f"DROP TABLE IF EXISTS {t} CASCADE")
        await p.close()


async def _builtin_id(pool) -> uuid.UUID:
    """A seeded built-in (owner NULL) — run_migrations seeds the 6 structures."""
    async with pool.acquire() as c:
        row = await c.fetchrow(
            "SELECT id FROM structure_template WHERE owner_user_id IS NULL ORDER BY name LIMIT 1"
        )
    assert row is not None, "migration should seed the built-in structures"
    return row["id"]


# ── the write side exists at all ──────────────────────────────────────────────

async def test_create_and_list_own(pool):
    repo = StructureTemplatesRepo(pool)
    u = uuid.uuid4()
    t = await repo.create(u, name="My Arc", kind="generic", beats=[{"key": "a", "label": "A", "order": 1}])
    assert t.owner_user_id == u and t.version == 1 and not t.is_archived
    listed = await repo.list_for_user(u)
    names = {x.name for x in listed}
    assert "My Arc" in names
    # built-ins are visible to everyone
    assert any(x.owner_user_id is None for x in listed)


# ── TENANCY — the entity_kinds bug this must not reintroduce ──────────────────

async def test_two_users_may_share_a_name_but_one_user_may_not_duplicate(pool):
    repo = StructureTemplatesRepo(pool)
    a, b = uuid.uuid4(), uuid.uuid4()
    await repo.create(a, name="Shared Name")
    await repo.create(b, name="Shared Name")  # different owner → allowed (partial-unique scoped)
    with pytest.raises(DuplicateStructureTemplateName):
        await repo.create(a, name="Shared Name")  # same owner → rejected


async def test_cross_user_isolation(pool):
    repo = StructureTemplatesRepo(pool)
    a, b = uuid.uuid4(), uuid.uuid4()
    ta = await repo.create(a, name="A's Structure")
    # b cannot see, edit, archive, or restore a's template
    assert await repo.get(b, ta.id) is None
    assert await repo.update(b, ta.id, 1, name="hijack") is None
    assert await repo.archive(b, ta.id) is None
    assert await repo.restore(b, ta.id) is None
    # a still owns an untouched row
    assert (await repo.get(a, ta.id)).name == "A's Structure"


async def test_a_user_cannot_edit_or_archive_a_builtin(pool):
    repo = StructureTemplatesRepo(pool)
    u = uuid.uuid4()
    bid = await _builtin_id(pool)
    # get sees it (read), but writes are owner-scoped → a built-in (owner NULL) is untouched
    assert (await repo.get(u, bid)).owner_user_id is None
    assert await repo.update(u, bid, 1, name="hijack builtin") is None
    assert await repo.archive(u, bid) is None


# ── CLONE — the slice-B entry point ──────────────────────────────────────────

async def test_clone_builtin_into_own_tier(pool):
    repo = StructureTemplatesRepo(pool)
    u = uuid.uuid4()
    bid = await _builtin_id(pool)
    src = await repo.get(u, bid)
    clone = await repo.clone_builtin(u, bid)
    assert clone.owner_user_id == u              # now editable
    assert clone.beats == src.beats              # carried the structure
    assert clone.name == f"{src.name} (copy)"
    # the clone IS editable (unlike the built-in it came from)
    updated = await repo.update(u, clone.id, clone.version, name="My Customised Cat")
    assert updated is not None and updated.name == "My Customised Cat"


async def test_cloning_the_same_builtin_twice_auto_disambiguates(pool):
    """A live smoke caught this: a fixed '(copy)' name 409s on the second clone. The default name
    must auto-disambiguate so a user (or a re-run) can clone the same built-in repeatedly."""
    repo = StructureTemplatesRepo(pool)
    u = uuid.uuid4()
    bid = await _builtin_id(pool)
    src = await repo.get(u, bid)
    c1 = await repo.clone_builtin(u, bid)
    c2 = await repo.clone_builtin(u, bid)   # would 409 with a fixed "(copy)"
    c3 = await repo.clone_builtin(u, bid)
    names = {c1.name, c2.name, c3.name}
    assert names == {f"{src.name} (copy)", f"{src.name} (copy 2)", f"{src.name} (copy 3)"}
    assert len(names) == 3  # all distinct — no collision


# ── OCC ──────────────────────────────────────────────────────────────────────

async def test_occ_stale_version_conflicts(pool):
    repo = StructureTemplatesRepo(pool)
    u = uuid.uuid4()
    t = await repo.create(u, name="OCC Test")
    ok = await repo.update(u, t.id, t.version, name="v2")  # version was 1
    assert ok.version == 2
    with pytest.raises(StructureTemplateVersionConflict):
        await repo.update(u, t.id, 1, name="stale write")  # expected 1, actual 2 → 412


# ── ARCHIVE / RESTORE symmetry ───────────────────────────────────────────────

async def test_the_decompose_consumer_resolves_a_custom_template(pool):
    """Spec §9 consumer-unbroken: the decompose route resolves its template via
    `StructureTemplatesRepo.get(user_id, id)` — a CUSTOM (user-authored) template must resolve with
    its beats exactly like a built-in, so decompose can map them onto chapters."""
    repo = StructureTemplatesRepo(pool)
    u = uuid.uuid4()
    beats = [{"key": "setup", "label": "Setup", "purpose": "…", "order": 1},
             {"key": "payoff", "label": "Payoff", "purpose": "…", "order": 2}]
    t = await repo.create(u, name="My Decompose Structure", beats=beats)
    # the exact call the decompose route (plan.py) makes:
    resolved = await repo.get(u, t.id)
    assert resolved is not None
    assert resolved.owner_user_id == u
    assert [b["key"] for b in resolved.beats] == ["setup", "payoff"]  # beats intact for beat_role mapping


async def test_migration_is_idempotent(pool):
    """Spec §9: re-running migrations adds nothing — the S-01 ALTERs are IF NOT EXISTS and the two
    partial-unique indexes are IF NOT EXISTS, so a second run over an already-migrated DB is a no-op
    and the 6 seeds are not re-inserted."""
    from app.db.migrate import run_migrations
    async with pool.acquire() as c:
        before = await c.fetchval("SELECT count(*) FROM structure_template WHERE owner_user_id IS NULL")
    await run_migrations(pool)   # second run
    async with pool.acquire() as c:
        after = await c.fetchval("SELECT count(*) FROM structure_template WHERE owner_user_id IS NULL")
        cols = {r["column_name"] for r in await c.fetch(
            "SELECT column_name FROM information_schema.columns WHERE table_name = 'structure_template'")}
    assert before == after and before > 0        # seeds not duplicated
    assert {"version", "is_archived", "updated_at"} <= cols  # write-side columns present, once


async def test_archive_hides_then_restore_brings_back(pool):
    repo = StructureTemplatesRepo(pool)
    u = uuid.uuid4()
    t = await repo.create(u, name="To Archive")
    await repo.archive(u, t.id)
    # hidden from the default list, still gettable (so restore can target it)
    assert t.id not in {x.id for x in await repo.list_for_user(u)}
    assert t.id in {x.id for x in await repo.list_for_user(u, include_archived=True)}
    assert (await repo.get(u, t.id)).is_archived is True
    restored = await repo.restore(u, t.id)
    assert restored is not None and restored.is_archived is False
    assert t.id in {x.id for x in await repo.list_for_user(u)}
