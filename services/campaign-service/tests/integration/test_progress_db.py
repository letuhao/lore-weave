"""S6 — BEHAVIORAL test of get_campaign_progress against a REAL Postgres.

The route test mocks the aggregate, so the actual COUNT(*) FILTER (WHERE
<stage>_status = ...) SQL + the kn/tr/ev column mapping are only verified here.
A status-string typo or wrong-column slip survives the mock; this catches it.
Skips when no TEST_CAMPAIGN_DB_URL (see conftest). Addresses review-impl S6 #1.
"""

from uuid import UUID, uuid4

import pytest

from app import repositories as repo

pytestmark = pytest.mark.asyncio


async def _make_campaign(pool) -> UUID:
    return await pool.fetchval(
        "INSERT INTO campaigns (owner_user_id, book_id, name, status) "
        "VALUES ($1,$2,'progress-test','running') RETURNING campaign_id",
        uuid4(), uuid4(),
    )


async def _chapter(pool, cid, sort, *, kn, tr, ev):
    await pool.execute(
        """
        INSERT INTO campaign_chapters
          (campaign_id, chapter_id, chapter_sort, ingest_status,
           knowledge_status, translation_status, eval_status)
        VALUES ($1,$2,$3,'done',$4,$5,$6)
        """,
        cid, uuid4(), sort, kn, tr, ev,
    )


async def test_progress_counts_each_stage_by_real_status(pool):
    cid = await _make_campaign(pool)
    # knowledge: 2 done, 1 failed, 1 skipped, 1 pending(=in_progress) → total 5
    await _chapter(pool, cid, 1, kn='done',       tr='done',       ev='done')
    await _chapter(pool, cid, 2, kn='done',       tr='dispatched', ev='pending')
    await _chapter(pool, cid, 3, kn='failed',     tr='pending',    ev='pending')
    await _chapter(pool, cid, 4, kn='skipped',    tr='done',       ev='done')
    await _chapter(pool, cid, 5, kn='pending',    tr='pending',    ev='pending')

    agg = await repo.get_campaign_progress(pool, cid)
    assert agg["total"] == 5
    # knowledge — proves the column mapping + status strings
    assert agg["kn_done"] == 2
    assert agg["kn_failed"] == 1
    assert agg["kn_skipped"] == 1
    # translation — done=2 (ch1, ch4), dispatched(=in_progress) ch2, pending ch3/ch5
    assert agg["tr_done"] == 2
    assert agg["tr_failed"] == 0
    assert agg["tr_skipped"] == 0
    # eval — done=2 (ch1, ch4)
    assert agg["ev_done"] == 2
    # in_progress is derived in the route: total - done - failed - skipped
    kn_in_progress = agg["total"] - agg["kn_done"] - agg["kn_failed"] - agg["kn_skipped"]
    assert kn_in_progress == 1  # only ch5 knowledge is pending


async def test_list_progress_done_counts_translation_settled(pool):
    # #2 polish — list_campaigns' correlated subquery counts translation done+skipped.
    owner = await pool.fetchval(
        "INSERT INTO campaigns (owner_user_id, book_id, name, status) "
        "VALUES ($1,$2,'list-test','running') RETURNING owner_user_id",
        __import__('uuid').uuid4(), __import__('uuid').uuid4(),
    )
    cid = await pool.fetchval(
        "SELECT campaign_id FROM campaigns WHERE owner_user_id=$1", owner)
    await _chapter(pool, cid, 1, kn='done', tr='done', ev='done')      # counts
    await _chapter(pool, cid, 2, kn='done', tr='skipped', ev='pending')  # counts (skipped)
    await _chapter(pool, cid, 3, kn='done', tr='dispatched', ev='pending')  # not yet
    rows = await repo.list_campaigns(pool, owner)
    assert len(rows) == 1
    assert rows[0]["progress_done"] == 2


async def test_chapters_page_attention_filter_and_paging(pool):
    # D-S6-CHAPTER-PAGING — attention filter excludes fully-settled rows; total +
    # LIMIT/OFFSET behave.
    cid = await _make_campaign(pool)
    await _chapter(pool, cid, 1, kn='done', tr='done', ev='done')        # settled → excluded
    await _chapter(pool, cid, 2, kn='done', tr='failed', ev='pending')   # attention
    await _chapter(pool, cid, 3, kn='failed', tr='pending', ev='pending')  # attention
    await _chapter(pool, cid, 4, kn='done', tr='dispatched', ev='pending')  # attention (in-progress)

    rows, total = await repo.get_campaign_chapters_page(pool, cid, status='attention', limit=10, offset=0)
    assert total == 3 and len(rows) == 3
    assert [r["chapter_sort"] for r in rows] == [2, 3, 4]

    # 'all' includes the settled one
    _, total_all = await repo.get_campaign_chapters_page(pool, cid, status='all', limit=10, offset=0)
    assert total_all == 4

    # paging: limit 2 offset 1 over the attention set → chapters 3, 4
    page2, total2 = await repo.get_campaign_chapters_page(pool, cid, status='attention', limit=2, offset=1)
    assert total2 == 3 and [r["chapter_sort"] for r in page2] == [3, 4]


async def test_progress_scopes_to_the_campaign(pool):
    a = await _make_campaign(pool)
    b = await _make_campaign(pool)
    await _chapter(pool, a, 1, kn='done', tr='done', ev='done')
    await _chapter(pool, b, 1, kn='failed', tr='pending', ev='pending')
    agg_a = await repo.get_campaign_progress(pool, a)
    assert agg_a["total"] == 1 and agg_a["kn_done"] == 1 and agg_a["kn_failed"] == 0
