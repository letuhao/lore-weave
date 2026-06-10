"""G1 — BEHAVIORAL test of the report queries against a REAL Postgres.

The route test mocks the repo, so the actual SQL — `get_report_row`'s
EXTRACT(EPOCH …) duration + est-band columns, and `get_failed_error_strings`'
failed-stage filter + GROUP BY — is only verified here. Skips without
TEST_CAMPAIGN_DB_URL (see conftest).
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID, uuid4

import pytest

from app import repositories as repo

pytestmark = pytest.mark.asyncio


async def _make_campaign(pool, owner: UUID) -> UUID:
    started = datetime(2026, 6, 10, 0, 0, tzinfo=timezone.utc)
    finished = started + timedelta(hours=1)
    return await pool.fetchval(
        """
        INSERT INTO campaigns
          (owner_user_id, book_id, name, status, total_chapters, spent_usd,
           budget_usd, est_usd_low, est_usd_high, started_at, finished_at)
        VALUES ($1,$2,'report-test','completed',3,$3,$4,$5,$6,$7,$8)
        RETURNING campaign_id
        """,
        owner, uuid4(), Decimal("8.50"), Decimal("12.00"),
        Decimal("7.00"), Decimal("11.00"), started, finished,
    )


async def _chapter(pool, cid, sort, *, kn, tr, ev, last_error=None):
    await pool.execute(
        """
        INSERT INTO campaign_chapters
          (campaign_id, chapter_id, chapter_sort, ingest_status,
           knowledge_status, translation_status, eval_status, last_error)
        VALUES ($1,$2,$3,'done',$4,$5,$6,$7)
        """,
        cid, uuid4(), sort, kn, tr, ev, last_error,
    )


async def test_report_row_duration_est_and_owner_scope(pool):
    owner = uuid4()
    cid = await _make_campaign(pool, owner)
    row = await repo.get_report_row(pool, cid, owner)
    assert row is not None
    assert row["status"] == "completed"
    assert row["duration_seconds"] == 3600          # EXTRACT(EPOCH FROM finished-started)
    assert row["est_usd_low"] == Decimal("7.00")
    assert row["est_usd_high"] == Decimal("11.00")
    assert row["spent_usd"] == Decimal("8.50")
    # owner-scoped → a different owner sees nothing
    assert await repo.get_report_row(pool, cid, uuid4()) is None


async def test_failed_error_strings_filters_failed_and_groups(pool):
    owner = uuid4()
    cid = await _make_campaign(pool, owner)
    # 2 failed-with-same-error, 1 failed-other-error, 1 all-done (excluded)
    await _chapter(pool, cid, 1, kn='done', tr='failed', ev='pending', last_error='429 rate limit')
    await _chapter(pool, cid, 2, kn='failed', tr='pending', ev='pending', last_error='429 rate limit')
    await _chapter(pool, cid, 3, kn='done', tr='failed', ev='pending', last_error='empty body')
    await _chapter(pool, cid, 4, kn='done', tr='done', ev='done', last_error=None)

    rows = await repo.get_failed_error_strings(pool, cid)
    by_err = {r["last_error"]: r["n"] for r in rows}
    assert by_err == {"429 rate limit": 2, "empty body": 1}  # all-done row excluded
