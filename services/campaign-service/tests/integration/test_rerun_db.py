"""G2 — BEHAVIORAL test of reset_failed_stages against a REAL Postgres.

The route test mocks the repo, so the actual UPDATE (per-stage CASE reset +
attempts zeroing + the optional chapter_ids ANY filter + the failed-only WHERE)
is only verified here. Skips without TEST_CAMPAIGN_DB_URL.
"""

from uuid import UUID, uuid4

import pytest

from app import repositories as repo

pytestmark = pytest.mark.asyncio


async def _make_campaign(pool) -> UUID:
    return await pool.fetchval(
        "INSERT INTO campaigns (owner_user_id, book_id, name, status) "
        "VALUES ($1,$2,'rerun-test','failed') RETURNING campaign_id",
        uuid4(), uuid4(),
    )


async def _chapter(pool, cid, sort, *, kn, tr, ev='pending', ka=3, ta=3, err='boom') -> UUID:
    chid = uuid4()
    await pool.execute(
        """
        INSERT INTO campaign_chapters
          (campaign_id, chapter_id, chapter_sort, ingest_status,
           knowledge_status, translation_status, eval_status,
           knowledge_attempts, translation_attempts, last_error)
        VALUES ($1,$2,$3,'done',$4,$5,$6,$7,$8,$9)
        """,
        cid, chid, sort, kn, tr, ev, ka, ta, err,
    )
    return chid


async def _row(pool, cid, chid):
    return await pool.fetchrow(
        "SELECT knowledge_status, translation_status, eval_status, "
        "knowledge_attempts, translation_attempts, last_error "
        "FROM campaign_chapters WHERE campaign_id=$1 AND chapter_id=$2", cid, chid)


async def test_reset_all_failed_clears_and_zeros(pool):
    cid = await _make_campaign(pool)
    a = await _chapter(pool, cid, 1, kn='done', tr='failed')      # translation failed
    b = await _chapter(pool, cid, 2, kn='failed', tr='pending')   # knowledge failed
    c = await _chapter(pool, cid, 3, kn='done', tr='done', err=None)  # no failure (untouched)

    n = await repo.reset_failed_stages(pool, cid, None)
    assert n == 2  # only the two failed chapters

    ra = await _row(pool, cid, a)
    assert ra["translation_status"] == 'pending' and ra["translation_attempts"] == 0
    assert ra["knowledge_status"] == 'done'  # done stage untouched
    assert ra["last_error"] is None
    rb = await _row(pool, cid, b)
    assert rb["knowledge_status"] == 'pending' and rb["knowledge_attempts"] == 0
    rc = await _row(pool, cid, c)
    assert rc["translation_status"] == 'done'  # not-failed row untouched


async def test_reset_scoped_to_chapter_ids(pool):
    cid = await _make_campaign(pool)
    a = await _chapter(pool, cid, 1, kn='failed', tr='pending')
    b = await _chapter(pool, cid, 2, kn='failed', tr='pending')

    n = await repo.reset_failed_stages(pool, cid, [a])  # only chapter a
    assert n == 1
    assert (await _row(pool, cid, a))["knowledge_status"] == 'pending'
    assert (await _row(pool, cid, b))["knowledge_status"] == 'failed'  # b untouched
