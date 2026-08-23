"""The version_num backfill must survive a SECOND startup. For a day it did not, and the service
crash-looped with translation's whole tool surface off the wire.

🔴 MEASURED 2026-08-23. infra-translation-service-1 was Restarting(3); its log ended:

    asyncpg.exceptions.UniqueViolationError: duplicate key value violates unique constraint
    "idx_ct_version"
    DETAIL:  Key (chapter_id, target_language, version_num)=(01a0291e-…, vi, 1) already exists.
    ERROR:    Application startup failed. Exiting.

and ai-gateway logged `provider 'translation' list-tools failed → PARTIAL`, federating 300 tools
instead of ~315. A tool under test (translation_job_control) was recorded blocked as "called 0/5"
when it was simply ABSENT FROM THE CATALOGUE — the service that owns it could not boot.

THE CLAIM THAT WAS FALSE, in the migration's own comment: "Safe to re-run (idempotent — ROW_NUMBER
is deterministic by created_at)." ROW_NUMBER is deterministic only under a TOTAL ordering, and
created_at is not one: 13 (chapter_id, target_language) groups in the live database hold rows whose
created_at match to the microsecond, because they are written by the same statement. On a tie the
order is arbitrary, so a re-run can hand row B the number row A still holds.

Two things are asserted here because the fix needs both, and the first without the second still
crashes:

  a total ORDER BY (created_at, id) — so the assignment is identical on every run; and
  a two-phase renumber through the negative space — because a single UPDATE that PERMUTES version
  numbers (A:1->2, B:2->1) violates the unique index MID-STATEMENT whatever the ordering. A plain
  unique index is checked per row and cannot be deferred.

Runs inside a rolled-back transaction against a real Postgres; skips when none is reachable.
"""
import os
import uuid

import asyncpg
import pytest

from app.migrate import VERSION_BACKFILL_SQL

_DSN = os.environ.get(
    "TRANSLATION_TEST_PG_DSN",
    "postgresql://loreweave:loreweave_dev@localhost:5555/loreweave_translation",
)

pytestmark = pytest.mark.xdist_group("pg")

_JOB = """INSERT INTO translation_jobs
            (job_id, owner_user_id, book_id, target_language, status,
             model_source, model_ref, system_prompt, user_prompt_tpl, chapter_ids)
          VALUES ($1, $2, $3, 'vi', 'completed', 'user', $4, '', '', ARRAY[]::uuid[])"""

_ROW = """INSERT INTO chapter_translations
            (id, job_id, chapter_id, book_id, owner_user_id, target_language,
             created_at, version_num, status)
          VALUES ($1, $2, $3, $4, $5, 'vi', $6, $7, 'completed')"""


async def _connect():
    try:
        return await asyncpg.connect(_DSN, timeout=5)
    except Exception as exc:  # noqa: BLE001 - any connect failure means "no PG here"
        pytest.skip(f"no Postgres at {_DSN}: {exc}")


async def _seed_a_tie(conn):
    """Two rows, identical created_at, numbered AGAINST the (created_at, id) order.

    This is the live shape: same-statement writes share a timestamp, and whichever tie-break the
    previous run happened to pick is not the one the next run picks. Numbering them in reverse is
    how a re-run's assignment differs from the stored one — the moment the old statement collides.
    """
    job = uuid.uuid4()
    owner, book, chapter = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    await conn.execute(_JOB, job, owner, book, uuid.uuid4())
    lo, hi = sorted([uuid.uuid4(), uuid.uuid4()], key=str)
    ts = await conn.fetchval("SELECT now()")
    # lo sorts FIRST by id, so a total order gives it rn=1 — but it is stored as version 2.
    await conn.execute(_ROW, lo, job, chapter, book, owner, ts, 2)
    await conn.execute(_ROW, hi, job, chapter, book, owner, ts, 1)
    return chapter, lo, hi


@pytest.mark.asyncio
async def test_the_backfill_survives_a_second_startup():
    """🔴 THE DEFECT. Against the original statement this raises UniqueViolationError — which in
    production is not an exception anyone sees, it is the service failing to start."""
    conn = await _connect()
    tx = conn.transaction()
    await tx.start()
    try:
        chapter, lo, hi = await _seed_a_tie(conn)
        await conn.execute(VERSION_BACKFILL_SQL)
        await conn.execute(VERSION_BACKFILL_SQL)  # the SECOND boot, which is the whole point

        rows = await conn.fetch(
            "SELECT id, version_num FROM chapter_translations WHERE chapter_id = $1"
            " ORDER BY version_num", chapter,
        )
        assert [r["version_num"] for r in rows] == [1, 2], (
            "the backfill left a gap or a duplicate rather than a dense 1..n sequence"
        )
        assert rows[0]["id"] == lo, (
            "version 1 did not go to the row the total ordering selects, so the assignment still "
            "depends on how Postgres broke the created_at tie"
        )
    finally:
        await tx.rollback()
        await conn.close()


@pytest.mark.asyncio
async def test_it_is_a_no_op_the_second_time():
    """Idempotence is the property the comment CLAIMED. Assert it rather than assert around it: a
    second run must leave every row exactly where the first put it."""
    conn = await _connect()
    tx = conn.transaction()
    await tx.start()
    try:
        chapter, _lo, _hi = await _seed_a_tie(conn)
        await conn.execute(VERSION_BACKFILL_SQL)
        first = dict(await conn.fetch(
            "SELECT id, version_num FROM chapter_translations WHERE chapter_id = $1", chapter))
        await conn.execute(VERSION_BACKFILL_SQL)
        second = dict(await conn.fetch(
            "SELECT id, version_num FROM chapter_translations WHERE chapter_id = $1", chapter))
        assert first == second, "a re-run moved rows, so the assignment is not stable"
    finally:
        await tx.rollback()
        await conn.close()


@pytest.mark.asyncio
async def test_it_leaves_no_row_in_the_negative_space():
    """THE CONTROL for the two-phase fix. Phase 1 parks every row at -version_num; if phase 2 ever
    misses a row, that row stays negative and every later read of it is silently wrong. Both
    statements ride one conn.execute (one implicit transaction), so this can only fail if the two
    phases stop covering the same rows."""
    conn = await _connect()
    tx = conn.transaction()
    await tx.start()
    try:
        chapter, _lo, _hi = await _seed_a_tie(conn)
        await conn.execute(VERSION_BACKFILL_SQL)
        stranded = await conn.fetchval(
            "SELECT count(*) FROM chapter_translations WHERE version_num <= 0")
        assert stranded == 0, f"{stranded} row(s) left parked in the negative space"
    finally:
        await tx.rollback()
        await conn.close()
