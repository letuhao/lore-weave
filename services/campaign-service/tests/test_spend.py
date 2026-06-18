"""S4d — budget cap: accumulate/pause repo logic + spend consumer parsing."""

from decimal import Decimal
from unittest.mock import AsyncMock
from uuid import UUID

from app import repositories as repo
from app.events.spend_consumer import SpendConsumer
from tests.conftest import FakeRecord, TEST_USER

CAMP = "dddddddd-dddd-dddd-dddd-dddddddddddd"
REQ = "11111111-2222-3333-4444-555555555555"


# ── accumulate_and_maybe_pause ───────────────────────────────────────────────

async def test_accumulate_fresh_adds_and_can_pause(fake_pool, mocker):
    fake_pool.fetchval.return_value = UUID(REQ)  # ON CONFLICT RETURNING → fresh
    # The UPDATE now RETURNs the new state so the post-commit spend emit can carry it.
    fake_pool.fetchrow.return_value = FakeRecord(
        {"owner_user_id": UUID(TEST_USER), "spent_usd": Decimal("1.5"), "status": "running"})
    emit = mocker.patch("app.repositories.emit_job_event_safe", new_callable=AsyncMock)
    res = await repo.accumulate_and_maybe_pause(
        fake_pool, request_id=UUID(REQ), campaign_id=UUID(CAMP), cost_usd=Decimal("1.5"))
    assert res is True
    # accumulate + the running->paused-at-cap CASE are one atomic UPDATE (RETURNING state)
    fake_pool.fetchrow.assert_awaited_once()
    sql = fake_pool.fetchrow.call_args.args[0]
    assert "spent_usd = spent_usd + $2" in sql
    assert "'paused'" in sql and "status = 'running'" in sql
    assert "RETURNING" in sql
    # D-JOBS-CAMPAIGN-SPEND-EMIT — a best-effort job event carries the LIVE accumulated
    # cost (the running TOTAL, not the delta) + the current status, post-commit.
    emit.assert_awaited_once()
    kw = emit.await_args.kwargs
    assert kw["cost_usd"] == 1.5 and kw["status"] == "running"
    assert kw["job_id"] == CAMP and kw["owner_user_id"] == TEST_USER


async def test_accumulate_duplicate_is_noop(fake_pool):
    fake_pool.fetchval.return_value = None  # dup request_id → already counted
    res = await repo.accumulate_and_maybe_pause(
        fake_pool, request_id=UUID(REQ), campaign_id=UUID(CAMP), cost_usd=Decimal("1.5"))
    assert res is False
    fake_pool.execute.assert_not_awaited()  # no double-count


async def test_update_budget_is_owner_scoped(fake_pool):
    fake_pool.fetchrow.return_value = FakeRecord({"campaign_id": UUID(CAMP)})
    row = await repo.update_campaign_fields(
        fake_pool, UUID(CAMP), UUID(TEST_USER), {"budget_usd": Decimal("9")})
    assert row is not None
    sql = fake_pool.fetchrow.call_args.args[0]
    assert "owner_user_id = $2" in sql and "budget_usd = $3" in sql


# ── SpendConsumer._process (flat-field parse + permanent/transient) ──────────

async def test_spend_process_valid_accumulates(mocker, fake_pool):
    acc = mocker.patch("app.repositories.accumulate_and_maybe_pause",
                       new_callable=AsyncMock, return_value=True)
    c = SpendConsumer("redis://x", fake_pool)
    permanent, err = await c._process(
        {"request_id": REQ, "campaign_id": CAMP, "cost_usd": "2.50"})
    assert err is None and permanent is False
    assert acc.call_args.kwargs["cost_usd"] == Decimal("2.50")
    assert str(acc.call_args.kwargs["campaign_id"]) == CAMP
    assert str(acc.call_args.kwargs["request_id"]) == REQ


async def test_spend_process_empty_cost_is_zero(mocker, fake_pool):
    acc = mocker.patch("app.repositories.accumulate_and_maybe_pause",
                       new_callable=AsyncMock, return_value=True)
    c = SpendConsumer("redis://x", fake_pool)
    await c._process({"request_id": REQ, "campaign_id": CAMP, "cost_usd": ""})
    assert acc.call_args.kwargs["cost_usd"] == Decimal(0)


async def test_spend_process_malformed_is_permanent(mocker, fake_pool):
    acc = mocker.patch("app.repositories.accumulate_and_maybe_pause",
                       new_callable=AsyncMock)
    c = SpendConsumer("redis://x", fake_pool)
    permanent, err = await c._process({"request_id": "not-a-uuid", "campaign_id": CAMP})
    assert permanent is True and err is not None
    acc.assert_not_awaited()  # never touch the DB for a malformed event


async def test_spend_process_db_error_is_transient(mocker, fake_pool):
    mocker.patch("app.repositories.accumulate_and_maybe_pause",
                 new_callable=AsyncMock, side_effect=RuntimeError("db down"))
    c = SpendConsumer("redis://x", fake_pool)
    permanent, err = await c._process(
        {"request_id": REQ, "campaign_id": CAMP, "cost_usd": "1"})
    assert permanent is False and err is not None  # transient → caller leaves pending
