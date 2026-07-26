"""S4d — BEHAVIORAL test of the budget-cap pause threshold against a REAL Postgres.

A fake pool can only assert the SQL text; this runs the actual CASE so a wrong
operator / column / NULL-handling slip in accumulate_and_maybe_pause is caught.
Skips when no TEST_CAMPAIGN_DB_URL (see conftest). Addresses review-impl S4d #1.
"""

from decimal import Decimal
from uuid import UUID, uuid4

import pytest

from app import repositories as repo

pytestmark = pytest.mark.asyncio


async def _make_campaign(pool, *, budget_usd, status="running") -> UUID:
    return await pool.fetchval(
        """
        INSERT INTO campaigns (owner_user_id, book_id, name, status, budget_usd)
        VALUES ($1, $2, 'cap-test', $3, $4)
        RETURNING campaign_id
        """,
        uuid4(), uuid4(), status, budget_usd,
    )


async def _status_spent(pool, cid):
    row = await pool.fetchrow(
        "SELECT status, spent_usd FROM campaigns WHERE campaign_id=$1", cid)
    return row["status"], row["spent_usd"]


async def test_accumulates_under_cap_stays_running(pool):
    cid = await _make_campaign(pool, budget_usd=Decimal("10"))
    counted = await repo.accumulate_and_maybe_pause(
        pool, request_id=uuid4(), campaign_id=cid, cost_usd=Decimal("4"))
    assert counted is True
    status, spent = await _status_spent(pool, cid)
    assert status == "running" and spent == Decimal("4")


async def test_pauses_at_cap(pool):
    cid = await _make_campaign(pool, budget_usd=Decimal("10"))
    await repo.accumulate_and_maybe_pause(pool, request_id=uuid4(), campaign_id=cid, cost_usd=Decimal("4"))
    await repo.accumulate_and_maybe_pause(pool, request_id=uuid4(), campaign_id=cid, cost_usd=Decimal("7"))
    status, spent = await _status_spent(pool, cid)
    assert spent == Decimal("11")           # overshoot recorded honestly
    assert status == "paused"               # 11 >= 10 → paused
    row = await pool.fetchrow("SELECT error_message FROM campaigns WHERE campaign_id=$1", cid)
    assert row["error_message"] == "budget cap reached"


async def test_duplicate_request_id_no_double_count(pool):
    cid = await _make_campaign(pool, budget_usd=Decimal("10"))
    rid = uuid4()
    first = await repo.accumulate_and_maybe_pause(pool, request_id=rid, campaign_id=cid, cost_usd=Decimal("3"))
    second = await repo.accumulate_and_maybe_pause(pool, request_id=rid, campaign_id=cid, cost_usd=Decimal("3"))
    assert first is True and second is False
    _, spent = await _status_spent(pool, cid)
    assert spent == Decimal("3")            # counted once


async def test_uncapped_never_pauses(pool):
    cid = await _make_campaign(pool, budget_usd=None)
    await repo.accumulate_and_maybe_pause(pool, request_id=uuid4(), campaign_id=cid, cost_usd=Decimal("9999"))
    status, spent = await _status_spent(pool, cid)
    assert status == "running" and spent == Decimal("9999")


async def test_paused_campaign_accrues_but_not_resurrected(pool):
    # A non-running campaign still records spend (audit) but the CASE never flips
    # its status (e.g. it won't 'pause' an already-cancelled/paused one to running).
    cid = await _make_campaign(pool, budget_usd=Decimal("5"), status="paused")
    await repo.accumulate_and_maybe_pause(pool, request_id=uuid4(), campaign_id=cid, cost_usd=Decimal("8"))
    status, spent = await _status_spent(pool, cid)
    assert status == "paused" and spent == Decimal("8")


async def test_update_budget_by_id(pool):
    # K27 (2026-07-24): rewritten for E0-4b. `update_campaign_fields` is scoped by
    # campaign_id (PK) — owner/grant gating moved to the router (_grant_campaign
    # MANAGE, anti-oracle 404), covered by test_campaigns_api / test_grant_adopt.
    # This DB test now proves only the repo's real contract: PK update + not-found.
    cid = await _make_campaign(pool, budget_usd=Decimal("5"))
    # a real campaign_id → updated
    row = await repo.update_campaign_fields(pool, cid, {"budget_usd": Decimal("20")})
    assert row is not None and row["budget_usd"] == Decimal("20")
    # an unknown campaign_id → None (the repo's "not found" is by PK, not owner)
    assert await repo.update_campaign_fields(pool, uuid4(), {"budget_usd": Decimal("20")}) is None
