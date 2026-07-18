"""SC11 amendment Phase 1 — the written-verdict mirror, against real Postgres.

The four properties that decide whether a cache is safe to trust:

  1. It RECONCILES, not patches — a re-run over correct state writes nothing (idempotent), and a
     stale/out-of-order delivery cannot corrupt it.
  2. It CLEARS. A deleted scene makes its spec node unwritten. A mirror that only ever SETS keeps
     claiming prose that no longer exists — worse than not having the column, because a stale
     "written" is a confident lie.
  3. It is a REGENERABLE CACHE, not a second authored anchor — book-service always wins. (DA-3/SC2:
     "the index points at the spec, never the reverse." A back-pointer LOOKS like a violation and
     is not; this test is what stops the next agent from deleting it.)
  4. A DEGRADED READ NEVER CLEARS IT. "I could not reach book-service" must never be written down
     as "there is no prose".
"""
from __future__ import annotations

import os
import uuid

import asyncpg
import pytest

from app.db.migrate import run_migrations
from app.db.repositories.written_verdict import WrittenVerdictRepo, links_from_scenes

_DSN = os.environ.get("TEST_COMPOSITION_DB_URL")

pytestmark = [
    pytest.mark.skipif(not _DSN, reason="set TEST_COMPOSITION_DB_URL to a throwaway DB to run"),
    pytest.mark.xdist_group("pg"),
]

_TABLES = [
    "plan_bootstrap_proposal", "plan_artifact", "plan_run",
    "outbox_events", "generation_correction", "generation_job", "narrative_thread",
    "canon_rule", "scene_link", "outline_node", "structure_node", "structure_template",
    "entity_override", "divergence_spec", "composition_work",
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


async def _node(pool, book_id, project_id, user, chapter_id, kind="scene"):
    async with pool.acquire() as c:
        return await c.fetchval(
            """
            INSERT INTO outline_node (created_by, project_id, book_id, kind, rank, chapter_id)
            VALUES ($1,$2,$3,$4,'m',$5) RETURNING id
            """,
            user, project_id, book_id, kind, chapter_id,
        )


async def _written(pool, node_id):
    async with pool.acquire() as c:
        return await c.fetchrow(
            "SELECT written_scene_id, written_at FROM outline_node WHERE id=$1", node_id)


async def test_reconcile_sets_the_link_and_is_IDEMPOTENT(pool):
    """A re-run over already-correct state must write ZERO rows. That is what makes the sweeper
    cheap enough to run often — and running it often is the only reason a cache is safe."""
    repo = WrittenVerdictRepo(pool)
    user, project, book = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    chapter = uuid.uuid4()
    n1 = await _node(pool, book, project, user, chapter)
    scene = uuid.uuid4()

    r1 = await repo.reconcile_chapter(book, chapter, [(n1, scene)])
    assert r1 == {"linked": 1, "cleared": 0}
    row = await _written(pool, n1)
    assert row["written_scene_id"] == scene and row["written_at"] is not None

    # …and again. Nothing changed, so nothing is written — and `written_at` does NOT move, because
    # it means "when the prose appeared", not "when the sweeper last ran".
    stamped = row["written_at"]
    r2 = await repo.reconcile_chapter(book, chapter, [(n1, scene)])
    assert r2 == {"linked": 0, "cleared": 0}, "an idempotent reconcile must write nothing"
    assert (await _written(pool, n1))["written_at"] == stamped


async def test_reconcile_CLEARS_a_node_whose_scene_is_GONE(pool):
    """THE half that is easy to forget. The author deletes the prose; the spec node survives (IX-13).
    If the mirror only ever SET, that node would claim prose that no longer exists — and the Plan
    Hub would render a deleted chapter as written."""
    repo = WrittenVerdictRepo(pool)
    user, project, book = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    chapter = uuid.uuid4()
    n1 = await _node(pool, book, project, user, chapter)
    scene = uuid.uuid4()

    await repo.reconcile_chapter(book, chapter, [(n1, scene)])
    assert (await _written(pool, n1))["written_scene_id"] == scene

    # The prose is deleted: book-service now returns NO scenes for this chapter.
    res = await repo.reconcile_chapter(book, chapter, [])
    assert res == {"linked": 0, "cleared": 1}
    row = await _written(pool, n1)
    assert row["written_scene_id"] is None and row["written_at"] is None


async def test_clear_chapter_IS_reconcile_with_an_empty_truth_set(pool):
    """`chapter.trashed`/`chapter.deleted` (spec §5.2b). Deliberately the SAME code path as
    reconcile, so the delete case cannot drift away from the reconcile case."""
    repo = WrittenVerdictRepo(pool)
    user, project, book = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    chapter = uuid.uuid4()
    n1 = await _node(pool, book, project, user, chapter)
    n2 = await _node(pool, book, project, user, chapter)
    await repo.reconcile_chapter(book, chapter, [(n1, uuid.uuid4()), (n2, uuid.uuid4())])

    assert await repo.clear_chapter(book, chapter) == 2
    assert (await _written(pool, n1))["written_scene_id"] is None
    assert (await _written(pool, n2))["written_scene_id"] is None


async def test_a_MOVED_anchor_moves_the_mirror(pool):
    """A re-parse re-resolves anchors, so a scene can change WHICH node it backs. The mirror must
    follow — and the node it left must be cleared, not silently left claiming prose."""
    repo = WrittenVerdictRepo(pool)
    user, project, book = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    chapter = uuid.uuid4()
    n1 = await _node(pool, book, project, user, chapter)
    n2 = await _node(pool, book, project, user, chapter)
    scene = uuid.uuid4()

    await repo.reconcile_chapter(book, chapter, [(n1, scene)])
    assert (await _written(pool, n1))["written_scene_id"] == scene

    # The re-parse re-anchored that scene onto n2.
    res = await repo.reconcile_chapter(book, chapter, [(n2, scene)])
    assert res["linked"] == 1 and res["cleared"] == 1
    assert (await _written(pool, n1))["written_scene_id"] is None, "the abandoned node must be cleared"
    assert (await _written(pool, n2))["written_scene_id"] == scene


async def test_the_reconcile_is_BOOK_scoped_and_chapter_scoped(pool):
    """Tenancy. Another book's node with the same chapter_id (they are cross-DB soft refs, so a
    collision is not impossible) must not be touched — and neither must a SIBLING chapter's nodes,
    which the CLEAR half could easily over-reach into."""
    repo = WrittenVerdictRepo(pool)
    user, project = uuid.uuid4(), uuid.uuid4()
    book_a, book_b = uuid.uuid4(), uuid.uuid4()
    ch1, ch2 = uuid.uuid4(), uuid.uuid4()

    a1 = await _node(pool, book_a, project, user, ch1)
    a2 = await _node(pool, book_a, project, user, ch2)   # sibling CHAPTER, same book
    b1 = await _node(pool, book_b, project, user, ch1)   # other BOOK, same chapter id

    s = uuid.uuid4()
    await repo.reconcile_chapter(book_a, ch1, [(a1, s)])
    await repo.reconcile_chapter(book_a, ch2, [(a2, uuid.uuid4())])
    await repo.reconcile_chapter(book_b, ch1, [(b1, uuid.uuid4())])

    # Now clear book_a / ch1 only.
    await repo.reconcile_chapter(book_a, ch1, [])
    assert (await _written(pool, a1))["written_scene_id"] is None
    assert (await _written(pool, a2))["written_scene_id"] is not None, "a sibling CHAPTER was cleared"
    assert (await _written(pool, b1))["written_scene_id"] is not None, "another BOOK was cleared"


async def test_written_map_is_what_the_hub_renders(pool):
    repo = WrittenVerdictRepo(pool)
    user, project, book = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    ch = uuid.uuid4()
    n1 = await _node(pool, book, project, user, ch)
    n2 = await _node(pool, book, project, user, ch)
    s1 = uuid.uuid4()
    await repo.reconcile_chapter(book, ch, [(n1, s1)])

    m = await repo.written_map(book)
    assert m == {str(n1): str(s1)}, "an unwritten node is ABSENT from the map, not present-and-null"
    assert str(n2) not in m


def test_links_from_scenes_ignores_a_scene_with_no_anchor():
    """Prose with no spec node is NOT 'unwritten' — it is the PH21 unplanned tray's business. It
    must not produce a link, and it must not be mistaken for one."""
    ch, node, scene = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    out = links_from_scenes([
        {"id": scene, "chapter_id": ch, "source_scene_id": node},
        {"id": uuid.uuid4(), "chapter_id": ch, "source_scene_id": None},   # unplanned prose
    ])
    assert out == {ch: [(node, scene)]}


def test_a_chapter_with_ONLY_unanchored_scenes_still_appears_as_an_EMPTY_truth_set():
    """The subtle one. If such a chapter were dropped from the map entirely, `reconcile_book` would
    never visit it — and a node that USED to be written would keep its stale link forever. It must
    appear with an EMPTY list, which is what drives the CLEAR."""
    ch = uuid.uuid4()
    out = links_from_scenes([{"id": uuid.uuid4(), "chapter_id": ch, "source_scene_id": None}])
    assert out == {ch: []}


async def test_a_DEGRADED_read_NEVER_clears_the_mirror(pool, monkeypatch):
    """THE WORST THING THIS MODULE COULD DO.

    If book-service is unreachable we do NOT know whether the prose exists. "I could not look" must
    never be written down as "there is no prose" — that would take a fully written book and render
    it blank, on a transient network blip, with no error the user ever sees.

    `fetch_book_scenes` raises on any non-200 or partial read; `backfill_all` must let that SKIP the
    book (and COUNT it), leaving the mirror exactly as it was.
    """
    from app.engine.scene_decompile import BookSceneFetchError
    from app.services import written_verdict_service as svc

    repo = WrittenVerdictRepo(pool)
    user, project, book = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    ch = uuid.uuid4()
    n1 = await _node(pool, book, project, user, ch)
    scene = uuid.uuid4()
    await repo.reconcile_chapter(book, ch, [(n1, scene)])

    async with pool.acquire() as c:
        await c.execute(
            "INSERT INTO composition_work (project_id, created_by, book_id) VALUES ($1,$2,$3)",
            project, user, book)

    async def _boom(*a, **kw):
        raise BookSceneFetchError("book-service is down")

    monkeypatch.setattr(svc, "fetch_scene_links", _boom)

    stats = await svc.backfill_all(pool, book_base_url="http://book", jwt_secret="s" * 32)

    assert stats["failed"] == 1, "an unreadable book must be COUNTED, not silently skipped"
    assert stats["books"] == 0
    # …and the mirror is UNTOUCHED. This is the whole test.
    assert (await _written(pool, n1))["written_scene_id"] == scene, \
        "a failed read CLEARED the mirror — a written book would render blank"


async def test_written_scene_id_is_a_REGENERABLE_CACHE_and_book_service_ALWAYS_WINS(pool, monkeypatch):
    """DA-3 / SC2 — READ THIS BEFORE DELETING THE COLUMN.

    DA-3 says: "the index points at the spec — `scenes.source_scene_id → outline_node.id`, NEVER the
    reverse." A back-pointer on `outline_node` therefore LOOKS like a violation, and a future agent
    doing the census I did will be tempted to "fix" it by deleting the column — which would silently
    restore the client-side derivation this amendment removed.

    It is not a violation, and this is the proof: the column is a REGENERABLE CACHE of the inverse
    (INV-FACTS' status for the EAV projection — "regenerable caches, never truth"). The authored
    anchor is still `scenes.source_scene_id`, owned solely by the index owner, and **whenever the
    two disagree, book-service wins and the mirror is rebuilt from it.**

    Corrupt the mirror three different ways; reconcile against book-service; all three are gone.
    That is what "regenerable" means, and it is why this can never become a second source of truth.

    (It also covers `reconcile_book` — which had NO test until this review, and shipped a bug because
    of it: it read scenes through `fetch_book_scenes`, whose ParsedScene DROPS the scene id, so it
    would have stored nothing at all.)
    """
    from app.services import written_verdict_service as svc

    user, project, book = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    ch = uuid.uuid4()
    n_written = await _node(pool, book, project, user, ch)      # genuinely written
    n_lying = await _node(pool, book, project, user, ch)        # claims prose that does not exist
    n_orphan = await _node(pool, book, project, user, None)     # claims prose owned by NO chapter
    real_scene = uuid.uuid4()

    async with pool.acquire() as c:
        # three separate corruptions of the mirror
        await c.execute("UPDATE outline_node SET written_scene_id=$2, written_chapter_id=$3, written_at=now() WHERE id=$1",
                        n_lying, uuid.uuid4(), ch)
        await c.execute("UPDATE outline_node SET written_scene_id=$2, written_at=now() WHERE id=$1",
                        n_orphan, uuid.uuid4())   # NO written_chapter_id -> unreachable by any chapter CLEAR

    # book-service's truth: ONLY n_written is written.
    async def _truth(*a, **kw):
        return [{"id": real_scene, "chapter_id": ch, "source_scene_id": n_written}]
    monkeypatch.setattr(svc, "fetch_scene_links", _truth)

    res = await svc.reconcile_book(pool, book, book_base_url="http://book", bearer="b")

    assert (await _written(pool, n_written))["written_scene_id"] == real_scene, "book-service's truth did not win"
    assert (await _written(pool, n_lying))["written_scene_id"] is None,         "a fabricated link survived — the mirror is NOT regenerable, it is a second truth"
    assert (await _written(pool, n_orphan))["written_scene_id"] is None,         "an ORPHAN link (no owning chapter) survived — no chapter CLEAR can reach it, so it would be PERMANENT"
    assert res["cleared"] == 2 and res["linked"] == 1


async def test_the_backfill_is_RESUMABLE_by_keyset_not_offset(pool):
    """A crash mid-backfill must resume from the last book it FINISHED, not start over — and a book
    inserted during the walk must not shift the page under it (which OFFSET would allow, silently
    skipping a book forever)."""
    repo = WrittenVerdictRepo(pool)
    user, project = uuid.uuid4(), uuid.uuid4()
    books = sorted(uuid.uuid4() for _ in range(5))
    for b in books:
        await _node(pool, b, project, user, uuid.uuid4())

    page1 = await repo.books_with_spec(after=None, limit=2)
    assert page1 == books[:2], "the cursor must be ORDERED, or a resume skips books"

    page2 = await repo.books_with_spec(after=page1[-1], limit=2)
    assert page2 == books[2:4], "resume-from-last-finished must not re-do or skip"

    page3 = await repo.books_with_spec(after=page2[-1], limit=2)
    assert page3 == books[4:]
    assert await repo.books_with_spec(after=page3[-1], limit=2) == []


# ── /review-impl HIGH — the CLEAR was scoped by the WRONG column ─────────────────────────────
# I keyed the CLEAR on `outline_node.chapter_id` (which chapter the node BELONGS to) instead of
# `written_chapter_id` (which chapter's PROSE backs it). Two facts I had assumed away, both false:
#   * NOTHING constrains a scene's source_scene_id to a node of its own chapter.
#   * chapter_id is NULL on a PLANNED node — 7 of 7 in the live DB when this was written.

async def test_a_CROSS_CHAPTER_anchor_does_not_make_the_mirror_FLAP(pool):
    """Copy prose (carrying its `data-scene-id`) from chapter B into chapter A. Now a scene of
    chapter A backs a node whose SPEC chapter is B.

    With the CLEAR keyed on `chapter_id`, reconciling B wiped the link and reconciling A restored
    it — set, clear, set, clear. The mirror NEVER CONVERGED, and which answer you got depended on
    which chapter published last. Keyed on `written_chapter_id`, B has no claim on it and leaves it
    alone."""
    repo = WrittenVerdictRepo(pool)
    user, project, book = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    ch_a, ch_b = uuid.uuid4(), uuid.uuid4()

    # The node's OWN chapter is B…
    node = await _node(pool, book, project, user, ch_b)
    # …but the prose that backs it lives in chapter A.
    scene_in_a = uuid.uuid4()
    r = await repo.reconcile_chapter(book, ch_a, [(node, scene_in_a)])
    assert r["linked"] == 1

    # Chapter B is published/re-parsed. It has no scenes pointing at this node.
    r = await repo.reconcile_chapter(book, ch_b, [])
    assert r["cleared"] == 0, "chapter B wiped a link that chapter A's prose owns — the mirror flaps"
    assert (await _written(pool, node))["written_scene_id"] == scene_in_a

    # And chapter A can still clear it, because A is the chapter that actually backs it.
    assert (await repo.reconcile_chapter(book, ch_a, []))["cleared"] == 1
    assert (await _written(pool, node))["written_scene_id"] is None


async def test_a_PLANNED_node_with_a_NULL_chapter_id_can_still_be_CLEARED(pool):
    """`chapter_id` is NULL on a planned node — which is MOST of them. A chapter-scoped CLEAR could
    never reach one, and `reconcile_book` skipped NULLs too, so a stale link on a planned node was
    PERMANENT: nothing in the system could ever heal it.

    `written_chapter_id` needs no `chapter_id` at all."""
    repo = WrittenVerdictRepo(pool)
    user, project, book = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    ch = uuid.uuid4()

    node = await _node(pool, book, project, user, None)   # PLANNED: no chapter yet
    scene = uuid.uuid4()

    assert (await repo.reconcile_chapter(book, ch, [(node, scene)]))["linked"] == 1
    assert (await _written(pool, node))["written_scene_id"] == scene

    # The prose is deleted. The node has NO chapter_id — the old CLEAR could not have touched it.
    assert (await repo.reconcile_chapter(book, ch, []))["cleared"] == 1
    assert (await _written(pool, node))["written_scene_id"] is None
