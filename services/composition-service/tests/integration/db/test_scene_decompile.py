"""22 SC6 / B4 — the scene DECOMPILER, driven against real Postgres.

Pins the four properties SC6 promises, by EFFECT on `outline_node`:
  1. one kind='scene' spec node per parse leaf, carrying the leaf's chapter_id +
     sort_order (as story_order) and the Work's book_id;
  2. IDEMPOTENT — a second run over the same index mints 0 (natural-key match on
     (project_id, chapter_id, story_order), since 26 D1's decompile_key column does
     not exist yet);
  3. a leaf already carrying `source_scene_id` (the index owner back-linked it —
     SC2) is MATCHED, never duplicated;
  4. a book with no canonical Work is guarded GRACEFULLY — reported, never a silent
     200-with-zero (`silent-success-is-a-bug-not-environment`).

The book client's scene list is "mocked" by driving `materialize_scenes` with a
seeded `ParsedScene[]` directly — no book-service round-trip, the pure core.

Gated on TEST_COMPOSITION_DB_URL (a throwaway DB — this drops tables).
"""

from __future__ import annotations

import os
import uuid

import asyncpg
import pytest

from app.db.migrate import run_migrations
from app.db.repositories.outline import OutlineRepo
from app.db.repositories.works import WorksRepo
from app.engine.scene_decompile import ParsedScene, materialize_scenes

_DSN = os.environ.get("TEST_COMPOSITION_DB_URL")

pytestmark = [
    pytest.mark.skipif(
        not _DSN, reason="set TEST_COMPOSITION_DB_URL to a throwaway DB to run",
    ),
    pytest.mark.xdist_group("pg"),
]

_TABLES = (
    "generation_correction", "generation_job", "decompose_commit", "scene_grounding_pins",
    "scene_link", "narrative_thread", "canon_rule", "style_profile", "voice_profile",
    "reference_source", "entity_override", "divergence_spec", "outline_node",
    "composition_work",
)


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


async def _canonical_work(pool) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    """A BACKED canonical Work (project_id set, source_work_id NULL) — the shape the
    decompiler resolves to host spec nodes. Returns (project_id, book_id, actor)."""
    actor, book, project = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    async with pool.acquire() as c:
        await c.execute(
            "INSERT INTO composition_work (project_id, created_by, book_id) VALUES ($1,$2,$3)",
            project, actor, book,
        )
    return project, book, actor


async def _scene_count(pool, project: uuid.UUID) -> int:
    async with pool.acquire() as c:
        return await c.fetchval(
            "SELECT count(*) FROM outline_node WHERE project_id=$1 AND kind='scene' AND NOT is_archived",
            project,
        )


async def test_one_spec_node_per_leaf_and_idempotent(pool):
    project, book, actor = await _canonical_work(pool)
    ch1, ch2 = uuid.uuid4(), uuid.uuid4()
    scenes = [
        ParsedScene(chapter_id=ch1, sort_order=0, title="Opening"),
        ParsedScene(chapter_id=ch1, sort_order=1, title="Rising"),
        ParsedScene(chapter_id=ch2, sort_order=0, title="Turn"),
    ]
    works, outline = WorksRepo(pool), OutlineRepo(pool)

    r1 = await materialize_scenes(
        pool, works, outline, book_id=book, scenes=scenes, created_by=actor,
    )
    assert r1.work_resolved is True
    assert (r1.created, r1.matched) == (3, 0)
    assert (r1.scenes_total, r1.chapters) == (3, 2)
    assert r1.project_id == project
    assert await _scene_count(pool, project) == 3

    # each minted node carries the leaf identity + the Work's book_id
    async with pool.acquire() as c:
        wrong_book = await c.fetchval(
            "SELECT count(*) FROM outline_node WHERE project_id=$1 AND book_id IS DISTINCT FROM $2",
            project, book,
        )
        assert wrong_book == 0
        rows = await c.fetch(
            "SELECT chapter_id, story_order, title FROM outline_node "
            "WHERE project_id=$1 AND kind='scene' ORDER BY chapter_id, story_order",
            project,
        )
    mapped = {(r["chapter_id"], r["story_order"]): r["title"] for r in rows}
    assert mapped[(ch1, 0)] == "Opening"
    assert mapped[(ch1, 1)] == "Rising"
    assert mapped[(ch2, 0)] == "Turn"

    # SC6 idempotency — a second run over the SAME index mints nothing, matches all
    r2 = await materialize_scenes(
        pool, works, outline, book_id=book, scenes=scenes, created_by=actor,
    )
    assert (r2.created, r2.matched) == (0, 3)
    assert await _scene_count(pool, project) == 3  # never duplicated


async def test_leaf_with_source_scene_id_is_matched_not_duplicated(pool):
    project, book, actor = await _canonical_work(pool)
    ch = uuid.uuid4()
    scenes = [
        # already back-linked by the index owner (SC2) → matched, no node minted
        ParsedScene(chapter_id=ch, sort_order=0, title="Anchored",
                    source_scene_id=uuid.uuid4()),
        ParsedScene(chapter_id=ch, sort_order=1, title="Fresh"),
    ]
    r = await materialize_scenes(
        pool, WorksRepo(pool), OutlineRepo(pool),
        book_id=book, scenes=scenes, created_by=actor,
    )
    assert (r.created, r.matched) == (1, 1)
    assert await _scene_count(pool, project) == 1
    # only the un-anchored leaf minted a node
    async with pool.acquire() as c:
        so = await c.fetchval(
            "SELECT story_order FROM outline_node WHERE project_id=$1 AND kind='scene'",
            project,
        )
    assert so == 1


async def test_scene_parents_under_existing_chapter_node(pool):
    project, book, actor = await _canonical_work(pool)
    ch = uuid.uuid4()
    outline = OutlineRepo(pool)
    chap_node = await outline.create_node(
        project, created_by=actor, kind="chapter", chapter_id=ch, title="Ch1",
    )
    r = await materialize_scenes(
        pool, WorksRepo(pool), outline,
        book_id=book, scenes=[ParsedScene(chapter_id=ch, sort_order=0, title="s")],
        created_by=actor,
    )
    assert r.created == 1
    async with pool.acquire() as c:
        parent = await c.fetchval(
            "SELECT parent_id FROM outline_node WHERE project_id=$1 AND kind='scene'",
            project,
        )
    assert parent == chap_node.id  # coherent lazy-tree: scene under its chapter


async def test_authored_scene_at_key_is_skipped_not_overwritten(pool):
    """26 IX-11 (D1): an authored scene at (chapter_id, story_order) is NEVER overwritten
    by a decompile of the same leaf, and it is reported DISTINCTLY as skipped_authored
    (not matched — matched is for a prior decompiled mint). This is the never-overwrite-
    authored safety the import-retry path depends on (a clobber would silently destroy
    hand authoring — the provenance-transposed tenancy bug class)."""
    project, book, actor = await _canonical_work(pool)
    ch = uuid.uuid4()
    outline = OutlineRepo(pool)
    authored = await outline.create_node(
        project, created_by=actor, kind="scene", chapter_id=ch, title="authored",
        story_order=0, status="drafting",
    )
    assert authored.source == "authored"  # provenance readable (the "mined" badge input)
    r = await materialize_scenes(
        pool, WorksRepo(pool), outline,
        book_id=book, scenes=[ParsedScene(chapter_id=ch, sort_order=0, title="leaf")],
        created_by=actor,
    )
    assert (r.created, r.matched, r.skipped_authored) == (0, 0, 1)
    assert await _scene_count(pool, project) == 1  # the authored node, untouched
    async with pool.acquire() as c:
        # unchanged: still authored, still the human's title (never clobbered to "leaf")
        row = await c.fetchrow(
            "SELECT source, title FROM outline_node WHERE id = $1", authored.id)
    assert row["source"] == "authored" and row["title"] == "authored"


async def test_decompiled_scene_re_run_matches_and_stamps_provenance(pool):
    """A decompiler mint stamps source='decompiled' + decompile_key; a re-run finds it
    and MATCHES (idempotent, not a duplicate, not skipped_authored)."""
    project, book, actor = await _canonical_work(pool)
    ch = uuid.uuid4()
    outline = OutlineRepo(pool)
    scenes = [ParsedScene(chapter_id=ch, sort_order=0, title="leaf")]
    r1 = await materialize_scenes(pool, WorksRepo(pool), outline, book_id=book,
                                  scenes=scenes, created_by=actor)
    assert (r1.created, r1.skipped_authored) == (1, 0)
    async with pool.acquire() as c:
        row = await c.fetchrow(
            "SELECT source, decompile_key FROM outline_node "
            "WHERE project_id = $1 AND kind = 'scene'", project)
    assert row["source"] == "decompiled" and row["decompile_key"] == f"{ch}:0"
    r2 = await materialize_scenes(pool, WorksRepo(pool), outline, book_id=book,
                                  scenes=scenes, created_by=actor)
    assert (r2.created, r2.matched, r2.skipped_authored) == (0, 1, 0)


async def test_archived_decompiled_node_rerun_does_not_collide(pool):
    """26 IX-11 regression: the partial unique index on (book_id, decompile_key) must
    share the decompiler's `NOT is_archived` probe predicate. A decompiled scene the
    user soft-DELETES (archives) keeps its decompile_key; because the idempotency probe
    skips archived rows, a re-run mints a FRESH node — which must NOT collide with the
    archived tombstone (an index without the archived exemption throws UniqueViolation and
    aborts the whole book's decompile). Pins: re-run after archive => created==1, no raise."""
    project, book, actor = await _canonical_work(pool)
    ch = uuid.uuid4()
    outline = OutlineRepo(pool)
    scenes = [ParsedScene(chapter_id=ch, sort_order=0, title="leaf")]
    r1 = await materialize_scenes(pool, WorksRepo(pool), outline, book_id=book,
                                  scenes=scenes, created_by=actor)
    assert r1.created == 1
    async with pool.acquire() as c:
        minted = await c.fetchval(
            "SELECT id FROM outline_node WHERE project_id=$1 AND kind='scene'", project)
        # soft-delete it (the composition_node_archive path), key retained
        await c.execute("UPDATE outline_node SET is_archived = true WHERE id = $1", minted)

    # re-run must re-mint a fresh LIVE node, not raise on the archived tombstone
    r2 = await materialize_scenes(pool, WorksRepo(pool), outline, book_id=book,
                                  scenes=scenes, created_by=actor)
    assert r2.created == 1, "a re-run after archive must re-mint, not collide"
    assert await _scene_count(pool, project) == 1  # one LIVE node; tombstone excluded
    async with pool.acquire() as c:
        # tombstone + fresh mint coexist, both keyed 'C:0' — the index permits it
        keyed = await c.fetchval(
            "SELECT count(*) FROM outline_node WHERE book_id=$1 AND decompile_key=$2",
            book, f"{ch}:0")
    assert keyed == 2


async def test_mappings_returned_for_minted_and_rematched_not_for_preset_or_authored(pool):
    """26 IX-12: materialize RETURNS the back-link map (the index owner writes it —
    composition never writes book-service's DB). A mapping entry is emitted for each leaf
    that now resolves to a decompiler-OWNED node: a fresh mint AND a re-matched prior
    decompiled node (so a retry after a failed write-back returns the SAME map). A leaf
    already carrying source_scene_id (skipped) and a human-AUTHORED node are NOT mapped."""
    project, book, actor = await _canonical_work(pool)
    ch = uuid.uuid4()
    outline = OutlineRepo(pool)
    authored = await outline.create_node(
        project, created_by=actor, kind="scene", chapter_id=ch, title="hand",
        story_order=0, status="drafting")
    scenes = [
        ParsedScene(chapter_id=ch, sort_order=0, title="authored-leaf"),                 # → skipped_authored, NOT mapped
        ParsedScene(chapter_id=ch, sort_order=1, title="mint-me"),                        # → created, mapped
        ParsedScene(chapter_id=ch, sort_order=2, title="already", source_scene_id=uuid.uuid4()),  # → matched, NOT mapped
    ]
    r1 = await materialize_scenes(pool, WorksRepo(pool), outline, book_id=book,
                                  scenes=scenes, created_by=actor)
    assert (r1.created, r1.matched, r1.skipped_authored) == (1, 1, 1)
    # exactly ONE mapping — the minted leaf; keyed to its new node
    assert len(r1.mappings) == 1
    m = r1.mappings[0]
    assert (m["chapter_id"], m["sort_order"]) == (str(ch), 1)
    async with pool.acquire() as c:
        minted_id = await c.fetchval(
            "SELECT id FROM outline_node WHERE project_id=$1 AND story_order=1 AND kind='scene'", project)
    assert m["outline_node_id"] == str(minted_id)
    assert m["outline_node_id"] != str(authored.id)  # never the authored node

    # a re-run: the minted node is now RE-MATCHED and must still map (idempotent write-back)
    r2 = await materialize_scenes(pool, WorksRepo(pool), outline, book_id=book,
                                  scenes=scenes, created_by=actor)
    assert (r2.created, r2.matched) == (0, 2)  # source_scene_id leaf + the re-matched mint
    keys = {(m["chapter_id"], m["sort_order"]) for m in r2.mappings}
    assert keys == {(str(ch), 1)}  # only the decompiled node re-maps; the preset leaf does not


async def test_no_canonical_work_is_guarded_gracefully(pool):
    book, actor = uuid.uuid4(), uuid.uuid4()  # NO composition_work for this book
    scenes = [ParsedScene(chapter_id=uuid.uuid4(), sort_order=0, title="orphan")]
    r = await materialize_scenes(
        pool, WorksRepo(pool), OutlineRepo(pool),
        book_id=book, scenes=scenes, created_by=actor,
    )
    assert r.work_resolved is False
    assert (r.created, r.matched) == (0, 0)
    assert r.scenes_total == 1
    assert r.detail  # non-silent: a reason is surfaced, not a bare 200-with-zero
    async with pool.acquire() as c:
        assert await c.fetchval("SELECT count(*) FROM outline_node") == 0


async def test_pending_work_is_refused_not_stranded(pool):
    """DECOMP-2 — a knowledge outage leaves a lazy Work (project_id NULL) with only a
    surrogate-id partition. `backfill_project` re-keys composition_work but NOT
    outline_node, so minting scene nodes on the surrogate would STRAND them off the real
    partition after backfill (empty rail + orphan rows + re-mint). The decompiler must
    therefore REFUSE to mint onto a pending Work — an honest work_resolved=False with a
    pending reason, minting nothing — never silently strand rows. The import tail re-runs
    after the Work is backed, and that run lands the scenes on the real partition."""
    actor, book = uuid.uuid4(), uuid.uuid4()
    async with pool.acquire() as c:
        await c.execute(
            "INSERT INTO composition_work (project_id, created_by, book_id, "
            "pending_project_backfill) VALUES (NULL,$1,$2,true)",
            actor, book,
        )
    r = await materialize_scenes(
        pool, WorksRepo(pool), OutlineRepo(pool),
        book_id=book, scenes=[ParsedScene(chapter_id=uuid.uuid4(), sort_order=0, title="s")],
        created_by=actor,
    )
    assert r.work_resolved is False, "a pending Work must be refused, not minted onto"
    assert r.created == 0
    assert "pending" in (r.detail or "").lower()
    async with pool.acquire() as c:
        # nothing was stranded on any partition
        assert await c.fetchval("SELECT count(*) FROM outline_node WHERE book_id = $1", book) == 0
