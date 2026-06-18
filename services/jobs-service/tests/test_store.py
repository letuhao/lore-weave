"""`upsert_job_event` param mapping + JSONB serialization (spy pool).

The MONOTONIC ordering (terminal-wins, forward-only) is SQL in the ON CONFLICT
WHERE clause — proven on real Postgres in the M2 live-smoke. Here we lock the
param contract: the right values reach `execute`, dicts are json-encoded, and
None passes through as SQL NULL (the ::jsonb cast)."""

import json
from datetime import datetime, timezone

import pytest

from app.projection.store import upsert_job_event
from loreweave_jobs import JobEvent, JobStatus

U = "11111111-1111-1111-1111-111111111111"
J = "22222222-2222-2222-2222-222222222222"
P = "33333333-3333-3333-3333-333333333333"


@pytest.mark.asyncio
async def test_upsert_passes_canonical_params(spy_pool):
    ev = JobEvent(
        service="knowledge", job_id=J, owner_user_id=U, kind="extraction",
        status=JobStatus.RUNNING, parent_job_id=P, detail_status="ch 3/40",
        progress={"done": 3, "total": 40}, title="万古神帝 extract",
        error=None, occurred_at="2026-06-15T10:00:00+00:00",
    )
    await upsert_job_event(spy_pool, ev)
    spy_pool.execute.assert_awaited_once()
    args = spy_pool.execute.await_args.args
    # args[0] is the SQL; args[1:] the params in declared order.
    assert args[1] == "knowledge"
    assert args[2] == J and args[3] == U and args[4] == "extraction"
    assert args[5] == "running"          # canonical enum value, not the Enum
    assert args[6] == P                  # parent_job_id
    assert args[7] == "ch 3/40"          # detail_status
    assert json.loads(args[8]) == {"done": 3, "total": 40}   # progress jsonb str
    assert args[9] == "万古神帝 extract"  # title (CJK preserved)
    assert args[10] is None              # error → NULL
    # occurred_at MUST be a datetime, not a str — asyncpg rejects a str for a
    # timestamptz param (the M3 live-smoke bug; this locks the regression).
    assert isinstance(args[11], datetime)
    assert args[11] == datetime.fromisoformat("2026-06-15T10:00:00+00:00")


@pytest.mark.asyncio
async def test_upsert_missing_occurred_at_defaults_to_now(spy_pool):
    ev = JobEvent(
        service="knowledge", job_id=J, owner_user_id=U, kind="extraction",
        status=JobStatus.RUNNING, occurred_at=None,
    )
    await upsert_job_event(spy_pool, ev)
    args = spy_pool.execute.await_args.args
    assert isinstance(args[11], datetime)  # NOT NULL job_updated_at always set
    assert args[11].tzinfo is not None


@pytest.mark.asyncio
async def test_upsert_nulls_optional_fields(spy_pool):
    ev = JobEvent(
        service="video_gen", job_id=J, owner_user_id=U, kind="video_gen",
        status=JobStatus.COMPLETED, occurred_at="2026-06-15T11:00:00+00:00",
    )
    await upsert_job_event(spy_pool, ev)
    args = spy_pool.execute.await_args.args
    assert args[5] == "completed"
    assert args[6] is None   # parent_job_id
    assert args[8] is None   # progress
    assert args[10] is None  # error


@pytest.mark.asyncio
async def test_upsert_returns_applied_from_command_tag(spy_pool):
    ev = JobEvent(service="knowledge", job_id=J, owner_user_id=U, kind="extraction",
                  status=JobStatus.RUNNING, occurred_at="2026-06-15T10:00:00+00:00")
    spy_pool.execute = __import__("unittest.mock", fromlist=["AsyncMock"]).AsyncMock(return_value="INSERT 0 1")
    assert await upsert_job_event(spy_pool, ev) is True
    spy_pool.execute.return_value = "INSERT 0 0"  # monotonic WHERE skipped → no row
    assert await upsert_job_event(spy_pool, ev) is False


@pytest.mark.asyncio
async def test_upsert_passes_p4_usage_params(spy_pool):
    # P4 usage fields land at the declared positions ($12 model … $16 params); params
    # is jsonb-encoded, cost/tokens pass through raw (NUMERIC/BIGINT bind natively).
    ev = JobEvent(
        service="knowledge", job_id=J, owner_user_id=U, kind="extraction",
        status=JobStatus.RUNNING, model="qwen2.5-7b-instruct", cost_usd=2.74,
        tokens_in=980142, tokens_out=180553, params={"concurrency": 4},
        occurred_at="2026-06-15T10:00:00+00:00",
    )
    await upsert_job_event(spy_pool, ev)
    args = spy_pool.execute.await_args.args
    assert args[12] == "qwen2.5-7b-instruct"   # model
    assert args[13] == 2.74                     # cost_usd
    assert args[14] == 980142                   # tokens_in
    assert args[15] == 180553                   # tokens_out
    assert json.loads(args[16]) == {"concurrency": 4}  # params jsonb str


@pytest.mark.asyncio
async def test_upsert_coerces_float_tokens_to_int(spy_pool):
    # A producer emitting tokens as a float (or a value that survived JSON as a float)
    # must be coerced to int — a float bound to a BIGINT param raises in asyncpg and
    # would poison the event into the DLQ. cost stays float; a bad value → None.
    ev = JobEvent(
        service="knowledge", job_id=J, owner_user_id=U, kind="extraction",
        status=JobStatus.RUNNING, cost_usd="2.5", tokens_in=100.0, tokens_out="nope",
        occurred_at="2026-06-15T10:00:00+00:00",
    )
    await upsert_job_event(spy_pool, ev)
    args = spy_pool.execute.await_args.args
    assert args[13] == 2.5 and isinstance(args[13], float)   # cost "2.5" → 2.5
    assert args[14] == 100 and isinstance(args[14], int)     # tokens 100.0 → 100
    assert args[15] is None                                   # "nope" → None (best-effort)


@pytest.mark.asyncio
async def test_upsert_nulls_p4_usage_when_absent(spy_pool):
    ev = JobEvent(
        service="video_gen", job_id=J, owner_user_id=U, kind="video_gen",
        status=JobStatus.RUNNING, occurred_at="2026-06-15T10:00:00+00:00",
    )
    await upsert_job_event(spy_pool, ev)
    args = spy_pool.execute.await_args.args
    assert args[12] is None and args[13] is None  # model / cost_usd
    assert args[14] is None and args[15] is None  # tokens_in / tokens_out
    assert args[16] is None                        # params → SQL NULL


@pytest.mark.asyncio
async def test_upsert_encodes_error_dict(spy_pool):
    ev = JobEvent(
        service="translation", job_id=J, owner_user_id=U, kind="translation",
        status=JobStatus.FAILED, error={"code": "LLM_TIMEOUT", "message": "boom"},
        occurred_at="2026-06-15T12:00:00+00:00",
    )
    await upsert_job_event(spy_pool, ev)
    args = spy_pool.execute.await_args.args
    assert json.loads(args[10]) == {"code": "LLM_TIMEOUT", "message": "boom"}
