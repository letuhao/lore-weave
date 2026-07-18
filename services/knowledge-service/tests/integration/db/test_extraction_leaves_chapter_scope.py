"""WS-0.1 — chapter-scoped extraction-cache invalidation, proven against real SQL.

Spec: docs/specs/2026-07-11-publish-independent-kg-indexing.md §3.3 (red-team P0-4)
Acceptance §5.4: "index chapter 1 of a 200-chapter book → assert the other 199
chapters' extraction_leaves survive".

WHY THIS FILE EXISTS AS AN INTEGRATION TEST
-------------------------------------------
The unit test (tests/unit/test_scenes_reparsed_handler.py) proves the handler CALLS
delete_by_chapter. It cannot prove the SQL actually spares the other chapters' rows —
a mocked repo returns whatever we tell it to. The claim "the other 199 chapters
survive" is a claim about a DELETE's WHERE clause, so only real SQL can settle it.
(Repo lesson: `mocked-client-hides-server-side-default-filters`.)

Before WS-0.1, `chapter.scenes_reparsed` → `delete_by_book` wiped ALL 200 chapters'
cached leaves. Under publish-independent indexing, "add to knowledge" becomes a
frequent per-chapter click, so that would re-pay the whole book's LLM extraction cost
on every single click. These tests are the regression lock on that.

Uses the shared dev Postgres via the `pool` fixture. Every row is written under a
freshly-generated book_id and deleted in a finally, so it is safe against the shared
dev DB (repo lesson: `shared-dev-db-not-clean-fixture-e2e`).
"""

from __future__ import annotations

from uuid import UUID, uuid4

import asyncpg
import pytest

from app.db.repositories.extraction_leaves import ExtractionLeavesRepo

# These hit the shared dev Postgres — serialize them onto one xdist worker.
pytestmark = pytest.mark.xdist_group("pg")

_OPS = ("entity", "relation", "event", "fact")


async def _seed_chapter(repo: ExtractionLeavesRepo, book_id: UUID, chapter_id: UUID) -> None:
    """Claim one leaf per op for a chapter — mirrors what the extractor does."""
    for op in _OPS:
        await repo.claim_pending(
            book_id=book_id,
            chapter_id=chapter_id,
            scene_id=chapter_id,  # today's placeholder, as production writes it
            leaf_path=f"book/legacy/chapter-{chapter_id}/scene-1",
            op=op,
            task_id=f"task-{chapter_id}-{op}",
            parse_version=1,
            extractor_version="v1-test0001",
            model_ref="m-test",
        )


async def _leaf_count(pool: asyncpg.Pool, book_id: UUID) -> int:
    return await pool.fetchval(
        "SELECT count(*) FROM extraction_leaves WHERE book_id = $1", book_id
    )


async def _chapters_present(pool: asyncpg.Pool, book_id: UUID) -> set[UUID]:
    rows = await pool.fetch(
        "SELECT DISTINCT chapter_id FROM extraction_leaves WHERE book_id = $1", book_id
    )
    return {r["chapter_id"] for r in rows}


@pytest.mark.asyncio
async def test_delete_by_chapter_spares_the_other_199_chapters(pool):
    """THE headline acceptance (spec §5.4 / P0-4).

    A 200-chapter book, every chapter cached. Invalidate ONE chapter.
    Assert: that chapter's 4 leaves are gone, and all 199 others' 796 leaves survive.
    """
    book_id = uuid4()
    repo = ExtractionLeavesRepo(pool)
    chapters = [uuid4() for _ in range(200)]

    try:
        for ch in chapters:
            await _seed_chapter(repo, book_id, ch)

        assert await _leaf_count(pool, book_id) == 800  # 200 chapters × 4 ops

        target = chapters[0]
        deleted_leaves, deleted_raw = await repo.delete_by_chapter(target)

        # Only the target chapter's leaves were deleted.
        assert deleted_leaves == 4, f"expected 4 leaves for one chapter, got {deleted_leaves}"
        assert deleted_raw == 0  # no raw rows seeded

        # The other 199 chapters' cache SURVIVES — the whole point of WS-0.1.
        surviving = await _leaf_count(pool, book_id)
        assert surviving == 796, (
            f"expected 796 surviving leaves (199 chapters × 4 ops), got {surviving} — "
            "a chapter-scoped invalidation must NOT wipe the book's cache"
        )

        present = await _chapters_present(pool, book_id)
        assert target not in present, "the target chapter's leaves must be gone"
        assert present == set(chapters[1:]), "exactly the other 199 chapters must remain"
    finally:
        await pool.execute("DELETE FROM extraction_leaves WHERE book_id = $1", book_id)


@pytest.mark.asyncio
async def test_delete_by_book_still_wipes_everything(pool):
    """Regression lock on the OTHER scope: `/invalidate-cache/{book_id}` must keep
    its book-wide semantics. WS-0.1 narrows the EVENT's scope, not this route's."""
    book_id = uuid4()
    repo = ExtractionLeavesRepo(pool)
    chapters = [uuid4() for _ in range(3)]

    try:
        for ch in chapters:
            await _seed_chapter(repo, book_id, ch)
        assert await _leaf_count(pool, book_id) == 12

        deleted_leaves, _ = await repo.delete_by_book(book_id)

        assert deleted_leaves == 12
        assert await _leaf_count(pool, book_id) == 0
    finally:
        await pool.execute("DELETE FROM extraction_leaves WHERE book_id = $1", book_id)


@pytest.mark.asyncio
async def test_delete_by_chapter_does_not_leak_across_books(pool):
    """chapter_id is a UUID so a cross-book collision is not realistic, but the
    delete must be provably keyed on the chapter, and must not touch a sibling book."""
    book_a, book_b = uuid4(), uuid4()
    ch_a, ch_b = uuid4(), uuid4()
    repo = ExtractionLeavesRepo(pool)

    try:
        await _seed_chapter(repo, book_a, ch_a)
        await _seed_chapter(repo, book_b, ch_b)

        await repo.delete_by_chapter(ch_a)

        assert await _leaf_count(pool, book_a) == 0
        assert await _leaf_count(pool, book_b) == 4, "a sibling book must be untouched"
    finally:
        await pool.execute(
            "DELETE FROM extraction_leaves WHERE book_id = ANY($1::uuid[])",
            [book_a, book_b],
        )


@pytest.mark.asyncio
async def test_delete_by_chapter_is_idempotent_on_replay(pool):
    """At-least-once delivery: a redelivered chapter.scenes_reparsed deletes 0 the
    second time — a clean no-op, never an error."""
    book_id = uuid4()
    chapter_id = uuid4()
    repo = ExtractionLeavesRepo(pool)

    try:
        await _seed_chapter(repo, book_id, chapter_id)

        first, _ = await repo.delete_by_chapter(chapter_id)
        second, _ = await repo.delete_by_chapter(chapter_id)  # replay

        assert first == 4
        assert second == 0, "replay must be a clean no-op"
    finally:
        await pool.execute("DELETE FROM extraction_leaves WHERE book_id = $1", book_id)


@pytest.mark.asyncio
async def test_delete_by_chapter_respects_op_filter(pool):
    """The ops filter narrows the delete, matching delete_by_book's contract."""
    book_id = uuid4()
    chapter_id = uuid4()
    repo = ExtractionLeavesRepo(pool)

    try:
        await _seed_chapter(repo, book_id, chapter_id)

        deleted, _ = await repo.delete_by_chapter(chapter_id, ops=["entity"])

        assert deleted == 1
        remaining = await pool.fetch(
            "SELECT op FROM extraction_leaves WHERE chapter_id = $1", chapter_id
        )
        assert {r["op"] for r in remaining} == {"relation", "event", "fact"}
    finally:
        await pool.execute("DELETE FROM extraction_leaves WHERE book_id = $1", book_id)


@pytest.mark.asyncio
async def test_migration_backfills_chapter_id_from_scene_id_on_legacy_rows(pool):
    """The BACKFILL, proven — not asserted.

    The dev DB's extraction_leaves happens to be empty, so "0 rows with a NULL
    chapter_id" proves nothing. This test reconstructs the pre-WS-0.1 shape (drop the
    column, insert a legacy row that has only scene_id), runs the REAL migration text
    (`migrate.DDL`, imported — not a hand-copied paraphrase that could drift from what
    actually ships), and asserts the legacy row came out with chapter_id == scene_id.

    That equality is correct by construction: every pre-WS-0.1 writer set
    scene_id := chapter_id (pass2_orchestrator's "placeholder until per-scene fanout").

    Runs inside a transaction that is ALWAYS rolled back, so the shared dev DB is left
    untouched even though the test briefly drops a column (repo lesson:
    `shared-dev-db-not-clean-fixture-e2e`). Postgres DDL is transactional, so this is
    safe; lock_timeout keeps it from wedging a concurrent session.
    """
    from app.db.migrate import DDL

    class _Rollback(Exception):
        pass

    book_id, scene_id = uuid4(), uuid4()

    async with pool.acquire() as conn:
        try:
            async with conn.transaction():
                await conn.execute("SET LOCAL lock_timeout = '5s'")

                # 1. Recreate the legacy (pre-WS-0.1) shape.
                await conn.execute("ALTER TABLE extraction_leaves DROP COLUMN chapter_id")

                # 2. A legacy row: scene_id carries the chapter id; no chapter_id column.
                await conn.execute(
                    """
                    INSERT INTO extraction_leaves
                      (book_id, scene_id, leaf_path, op, task_id, status,
                       parse_version, extractor_version, model_ref)
                    VALUES ($1, $2, 'book/legacy/chapter-x/scene-1', 'entity',
                            'task-legacy-backfill', 'completed', 1, 'v1', 'm')
                    """,
                    book_id, scene_id,
                )

                # 3. Run the REAL migration (idempotent; only the new block does work).
                await conn.execute(DDL)

                # 4. The legacy row must now be reachable by a chapter-scoped delete.
                got = await conn.fetchrow(
                    "SELECT chapter_id, scene_id FROM extraction_leaves WHERE book_id = $1",
                    book_id,
                )
                assert got["chapter_id"] == scene_id, (
                    "backfill must set chapter_id := scene_id on legacy rows, else those "
                    "leaves are unreachable by delete_by_chapter — a permanently-stale cache"
                )

                # ...and NOT NULL must be back on, so no new writer can skip it.
                nullable = await conn.fetchval(
                    "SELECT is_nullable FROM information_schema.columns "
                    "WHERE table_name = 'extraction_leaves' AND column_name = 'chapter_id'"
                )
                assert nullable == "NO", "migration must re-assert NOT NULL after backfill"

                raise _Rollback  # leave the shared DB exactly as we found it
        except _Rollback:
            pass

    # Prove the rollback really happened: the live column is still there and NOT NULL.
    nullable = await pool.fetchval(
        "SELECT is_nullable FROM information_schema.columns "
        "WHERE table_name = 'extraction_leaves' AND column_name = 'chapter_id'"
    )
    assert nullable == "NO"
    assert await _leaf_count(pool, book_id) == 0, "the legacy row must not have persisted"


@pytest.mark.asyncio
async def test_chapter_id_is_not_null_so_a_forgetful_writer_fails_loudly(pool):
    """WS-0.1 fail-loud guard.

    A leaf written WITHOUT a chapter_id could never be reached by any chapter-scoped
    invalidation — it would be a permanently-stale cache entry, silently. The NOT NULL
    constraint turns that latent corruption into an immediate, loud failure at the
    write. This asserts the constraint is really on the live schema (a migration that
    silently no-ops is a bug class this repo has shipped: `add-column-if-not-exists-
    never-revisits-a-bad-default`).
    """
    book_id = uuid4()
    with pytest.raises(asyncpg.NotNullViolationError):
        await pool.execute(
            """
            INSERT INTO extraction_leaves
              (book_id, scene_id, leaf_path, op, task_id, status,
               parse_version, extractor_version, model_ref)
            VALUES ($1, $2, 'p', 'entity', 'task-nullch', 'running', 1, 'v1', 'm')
            """,
            book_id, uuid4(),
        )
