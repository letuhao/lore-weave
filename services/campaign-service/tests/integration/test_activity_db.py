"""D-FACTORY-INFLIGHT-LOG — BEHAVIORAL test of the campaign_activity trigger + read
against a REAL Postgres. The trigger fires only in a real DB (a fake pool can't run
plpgsql), so the "one row per stage-status transition / nothing on a no-status UPDATE"
invariant is verifiable ONLY here. Skips when no TEST_CAMPAIGN_DB_URL (see conftest).
"""

from uuid import UUID, uuid4

import pytest

from app import repositories as repo

pytestmark = pytest.mark.asyncio


async def _campaign(pool) -> UUID:
    return await pool.fetchval(
        "INSERT INTO campaigns (owner_user_id, book_id, name, status) "
        "VALUES ($1,$2,'activity-test','running') RETURNING campaign_id",
        uuid4(), uuid4(),
    )


async def _seed_chapter(pool, cid, sort) -> UUID:
    chid = uuid4()
    # INSERT (all stages 'pending') — the trigger is UPDATE-only, so this logs nothing.
    await pool.execute(
        "INSERT INTO campaign_chapters (campaign_id, chapter_id, chapter_sort) VALUES ($1,$2,$3)",
        cid, chid, sort,
    )
    return chid


async def _set(pool, cid, chid, col, value, *, last_error=None):
    await pool.execute(
        f"UPDATE campaign_chapters SET {col} = $3, last_error = $4 "
        f"WHERE campaign_id = $1 AND chapter_id = $2",
        cid, chid, value, last_error,
    )


async def test_trigger_logs_one_row_per_status_transition(pool):
    cid = await _campaign(pool)
    chid = await _seed_chapter(pool, cid, 5)

    # the seed INSERT logged nothing
    assert await repo.get_campaign_activity(pool, cid) == []

    await _set(pool, cid, chid, "knowledge_status", "dispatched")
    await _set(pool, cid, chid, "knowledge_status", "done")
    await _set(pool, cid, chid, "translation_status", "dispatched")
    await _set(pool, cid, chid, "translation_status", "failed", last_error="HTTP 429 rate limit")

    rows = await repo.get_campaign_activity(pool, cid)
    # recent-first → translation failed, translation dispatched, knowledge done, knowledge dispatched
    assert [(r["stage"], r["status"]) for r in rows] == [
        ("translation", "failed"), ("translation", "dispatched"),
        ("knowledge", "done"), ("knowledge", "dispatched"),
    ]
    # detail carries last_error ONLY on the failed transition
    assert rows[0]["detail"] == "HTTP 429 rate limit"
    assert rows[1]["detail"] is None
    assert all(r["chapter_sort"] == 5 for r in rows)


async def test_trigger_logs_eval_and_skipped_transitions(pool):
    # review-impl #1: the eval branch + the 'skipped' status are load-bearing trigger
    # paths the happy-path test missed. eval_status pending→done and translation→skipped
    # are real consumer transitions.
    cid = await _campaign(pool)
    chid = await _seed_chapter(pool, cid, 3)
    await _set(pool, cid, chid, "translation_status", "skipped")
    await _set(pool, cid, chid, "eval_status", "done")

    rows = await repo.get_campaign_activity(pool, cid)
    assert [(r["stage"], r["status"]) for r in rows] == [("eval", "done"), ("translation", "skipped")]
    assert all(r["detail"] is None for r in rows)  # neither is a failure


async def test_trigger_ignores_non_status_updates(pool):
    cid = await _campaign(pool)
    chid = await _seed_chapter(pool, cid, 1)
    await _set(pool, cid, chid, "knowledge_status", "dispatched")  # 1 row
    # an attempts-only bump (no status change) must NOT log
    await pool.execute(
        "UPDATE campaign_chapters SET knowledge_attempts = knowledge_attempts + 1 "
        "WHERE campaign_id = $1 AND chapter_id = $2", cid, chid,
    )
    # re-setting the SAME status is also a no-op (IS DISTINCT FROM)
    await _set(pool, cid, chid, "knowledge_status", "dispatched")

    rows = await repo.get_campaign_activity(pool, cid)
    assert len(rows) == 1 and rows[0]["status"] == "dispatched"


async def test_activity_keyset_paging_and_scope(pool):
    cid = await _campaign(pool)
    other = await _campaign(pool)
    chid = await _seed_chapter(pool, cid, 1)
    # 4 transitions → 4 rows
    for s in ("dispatched", "done"):
        await _set(pool, cid, chid, "knowledge_status", s)
    for s in ("dispatched", "done"):
        await _set(pool, cid, chid, "translation_status", s)
    # noise on another campaign must not appear
    ochid = await _seed_chapter(pool, other, 1)
    await _set(pool, other, ochid, "knowledge_status", "dispatched")

    page1 = await repo.get_campaign_activity(pool, cid, limit=2)
    assert len(page1) == 2
    page2 = await repo.get_campaign_activity(pool, cid, limit=2, before_id=page1[-1]["id"])
    assert len(page2) == 2
    # strictly older, no overlap, still campaign-scoped
    assert page2[0]["id"] < page1[-1]["id"]
    ids = {r["id"] for r in page1} | {r["id"] for r in page2}
    assert len(ids) == 4
