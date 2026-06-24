"""Unified Job Control Plane P1 — emit_job_event wiring in campaign-service.

The shared emit lib + JobEvent payload shape are SDK-tested centrally; these prove the
WIRING fires at campaign's lifecycle chokepoints (create_campaign + set_campaign_status)
on the SAME conn the write uses (so the event commits atomically with the status change
— H1), maps campaign-native status → canonical JobStatus, and does NOT fire when no row
matched. Reconcile/sweeper/spend-consumer paths are intentionally NOT wired here.
"""

from __future__ import annotations

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app import repositories as repo

USER = uuid4()
CAMPAIGN = uuid4()
BOOK = uuid4()


class _NullCM:
    async def __aenter__(self):
        return None

    async def __aexit__(self, *exc):
        return False


class FakeConn:
    """Minimal asyncpg-conn stand-in: fetchrow returns a scripted row; `transaction()`
    is a no-op async context manager (asyncpg's Connection.transaction())."""

    def __init__(self, row):
        self._row = row

    async def fetchrow(self, *a, **k):
        return self._row

    async def execute(self, *a, **k):
        return "UPDATE 1"

    def transaction(self):
        return _NullCM()


class FakePool:
    """Pool whose `acquire()` yields the FakeConn — mirrors the conftest fake_pool
    semantics so `set_campaign_status` runs its real body."""

    def __init__(self, conn):
        self._conn = conn

    def acquire(self):
        conn = self._conn

        class _CM:
            async def __aenter__(self_inner):
                return conn

            async def __aexit__(self_inner, *exc):
                return False

        return _CM()


def _status_row(**over):
    base = dict(
        campaign_id=CAMPAIGN, owner_user_id=USER, status="running", error_message=None,
        spent_usd=0,  # P4 — set_campaign_status RETURNING now includes spent_usd
    )
    base.update(over)
    return base


def _create_row(**over):
    base = dict(
        campaign_id=CAMPAIGN, owner_user_id=USER, status="created", name="My run",
        # P4 — create_campaign emit reads these from the RETURNING row for cost+params
        spent_usd=0, gating_mode="phase_barrier", target_language="vi",
        total_chapters=0, knowledge_model_ref=None, translation_model_ref=None,
    )
    base.update(over)
    return base


# ── set_campaign_status (the PRIMARY transition chokepoint) ──────────────────


@pytest.mark.asyncio
async def test_set_status_emits_running(monkeypatch):
    spy = AsyncMock()
    monkeypatch.setattr(repo, "emit_job_event", spy)
    conn = FakeConn(_status_row(status="running"))
    await repo.set_campaign_status(FakePool(conn), CAMPAIGN, "running", set_started=True)
    spy.assert_awaited_once()
    kw = spy.await_args.kwargs
    assert kw["service"] == "campaign"
    assert kw["status"] == "running"
    assert kw["job_id"] == str(CAMPAIGN)
    assert kw["owner_user_id"] == str(USER)
    assert kw["kind"] == "campaign"
    assert kw.get("detail_status") is None  # running is already canonical
    # emit fired on the SAME conn as the UPDATE (atomic) — first positional arg.
    assert spy.await_args.args[0] is conn


@pytest.mark.asyncio
async def test_set_status_paused_is_canonical(monkeypatch):
    spy = AsyncMock()
    monkeypatch.setattr(repo, "emit_job_event", spy)
    conn = FakeConn(_status_row(status="paused"))
    await repo.set_campaign_status(FakePool(conn), CAMPAIGN, "paused")
    kw = spy.await_args.kwargs
    assert kw["status"] == "paused"
    assert kw.get("detail_status") is None


@pytest.mark.asyncio
async def test_set_status_cancelling_is_canonical(monkeypatch):
    spy = AsyncMock()
    monkeypatch.setattr(repo, "emit_job_event", spy)
    conn = FakeConn(_status_row(status="cancelling"))
    await repo.set_campaign_status(FakePool(conn), CAMPAIGN, "cancelling")
    kw = spy.await_args.kwargs
    assert kw["status"] == "cancelling"
    assert kw.get("detail_status") is None


@pytest.mark.asyncio
async def test_set_status_failed_passes_error(monkeypatch):
    spy = AsyncMock()
    monkeypatch.setattr(repo, "emit_job_event", spy)
    conn = FakeConn(_status_row(status="failed", error_message="boom"))
    await repo.set_campaign_status(
        FakePool(conn), CAMPAIGN, "failed", error_message="boom", set_finished=True
    )
    kw = spy.await_args.kwargs
    assert kw["status"] == "failed"
    assert kw["error"] == {"code": "error", "message": "boom"}


@pytest.mark.asyncio
async def test_set_status_missing_row_no_emit(monkeypatch):
    spy = AsyncMock()
    monkeypatch.setattr(repo, "emit_job_event", spy)
    conn = FakeConn(None)  # UPDATE matched nothing
    await repo.set_campaign_status(FakePool(conn), CAMPAIGN, "completed", set_finished=True)
    spy.assert_not_awaited()


# ── create_campaign (initial lifecycle event) ────────────────────────────────


@pytest.mark.asyncio
async def test_create_emits_pending_with_native_detail(monkeypatch):
    spy = AsyncMock()
    monkeypatch.setattr(repo, "emit_job_event", spy)
    conn = FakeConn(_create_row(status="created"))
    await repo.create_campaign(
        conn,
        owner_user_id=USER,
        book_owner_user_id=USER,
        book_id=BOOK,
        name="My run",
        gating_mode="phase_barrier",
        target_language="vi",
        knowledge_project_id=None,
        embedding_model_ref=None,
        knowledge_model_source=None,
        knowledge_model_ref=None,
        translation_model_source=None,
        translation_model_ref=None,
        chapter_from=None,
        chapter_to=None,
        total_chapters=0,
    )
    spy.assert_awaited_once()
    kw = spy.await_args.kwargs
    assert kw["service"] == "campaign"
    assert kw["status"] == "pending"            # canonical for native `created`
    assert kw["detail_status"] == "created"     # native sub-state preserved
    assert kw["job_id"] == str(CAMPAIGN)
    assert kw["owner_user_id"] == str(USER)
    assert kw["kind"] == "campaign"
    assert spy.await_args.args[0] is conn       # same conn as the INSERT
    # P4 — create carries cost (spent_usd) + whitelisted params
    assert kw["cost_usd"] == 0.0
    assert kw["params"]["gating_mode"] == "phase_barrier"
    assert kw["params"]["target_language"] == "vi"


@pytest.mark.asyncio
async def test_create_emits_per_stage_model_names(monkeypatch):
    # D-JOBS-P4-CAMPAIGN-MODEL-NAMES — the router resolves the per-stage NAMES out-of-tx
    # and passes them; the create emit carries them (top-level model = translation stage,
    # per-stage names in params). The projection's COALESCE keeps them across status events.
    spy = AsyncMock()
    monkeypatch.setattr(repo, "emit_job_event", spy)
    conn = FakeConn(_create_row(status="created"))
    await repo.create_campaign(
        conn,
        owner_user_id=USER, book_owner_user_id=USER, book_id=BOOK, name="My run",
        gating_mode="phase_barrier",
        target_language="vi", knowledge_project_id=None, embedding_model_ref=None,
        knowledge_model_source="user_model", knowledge_model_ref=uuid4(),
        translation_model_source="user_model", translation_model_ref=uuid4(),
        chapter_from=None, chapter_to=None, total_chapters=0,
        knowledge_model_name="qwen2.5-7b-instruct",
        translation_model_name="gemma-2-9b",
    )
    kw = spy.await_args.kwargs
    assert kw["model"] == "gemma-2-9b"  # top-level = translation stage
    assert kw["params"]["knowledge_model"] == "qwen2.5-7b-instruct"
    assert kw["params"]["translation_model"] == "gemma-2-9b"
