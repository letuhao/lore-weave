"""B2-A — worker-ai run telemetry: outbox emit + config snapshot/payload."""

from __future__ import annotations

import json
import uuid
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.clients import ExtractionResult
from app.outbox_emit import (
    RUN_COMPLETED_EVENT,
    emit_extraction_run,
    emit_extraction_run_best_effort,
)
from app.runner import (
    JobRow,
    _advance_cursor_and_emit_run,
    _build_run_config,
    _run_payload,
)


def _job(**over) -> JobRow:
    d = dict(
        job_id=uuid.uuid4(), user_id=uuid.uuid4(), project_id=uuid.uuid4(),
        scope="chapters", scope_range=None, status="running",
        llm_model="extractor-model", embedding_model="bge-m3",
        max_spend_usd=Decimal("10"), items_total=5, items_processed=0,
        current_cursor=None, cost_spent_usd=Decimal("0"),
    )
    d.update(over)
    return JobRow(**d)


class _Capture:
    def __init__(self, raises: bool = False):
        self.calls = []
        self._raises = raises

    async def execute(self, sql, *params):
        if self._raises:
            raise RuntimeError("db down")
        self.calls.append((sql, params))


# ── emit_extraction_run ──────────────────────────────────────────────

async def test_emit_inserts_into_outbox_with_run_id_and_payload():
    ex = _Capture()
    run_id = str(uuid.uuid4())
    payload = {"run_id": run_id, "outcome": "succeeded"}
    await emit_extraction_run(ex, payload)

    assert len(ex.calls) == 1
    sql, params = ex.calls[0]
    assert "INSERT INTO outbox_events" in sql
    assert params[0] == uuid.UUID(run_id)          # aggregate_id = run_id (UUID)
    assert params[1] == RUN_COMPLETED_EVENT
    assert json.loads(params[2])["outcome"] == "succeeded"


async def test_best_effort_swallows_executor_failure():
    ex = _Capture(raises=True)
    # must NOT raise
    await emit_extraction_run_best_effort(ex, {"run_id": str(uuid.uuid4()), "outcome": "failed"})


# ── _advance_cursor_and_emit_run (MED-1: telemetry never load-bearing) ──

def _txn_pool():
    """AsyncMock pool with acquire()/transaction() async context managers; the
    acquired conn records execute calls."""
    pool = AsyncMock()
    pool.execute = AsyncMock()
    conn = AsyncMock()
    conn.execute = AsyncMock()
    _txn = MagicMock()
    _txn.__aenter__ = AsyncMock(return_value=None)
    _txn.__aexit__ = AsyncMock(return_value=False)
    conn.transaction = MagicMock(return_value=_txn)
    _acq = MagicMock()
    _acq.__aenter__ = AsyncMock(return_value=conn)
    _acq.__aexit__ = AsyncMock(return_value=False)
    pool.acquire = MagicMock(return_value=_acq)
    return pool, conn


async def test_advance_and_emit_runs_both_writes_in_one_txn():
    pool, conn = _txn_pool()
    await _advance_cursor_and_emit_run(
        pool, uuid.uuid4(), uuid.uuid4(), {"k": "v"},
        {"run_id": str(uuid.uuid4()), "outcome": "succeeded"},
    )
    # cursor-advance UPDATE + outbox INSERT both ran on the txn connection
    assert conn.execute.await_count == 2


async def test_advance_and_emit_txn_failure_falls_back_does_not_raise():
    """A transaction failure must NOT propagate (would fail the whole job) — it
    falls back to a plain best-effort cursor-advance so the job progresses."""
    pool = AsyncMock()
    pool.execute = AsyncMock()  # fallback _advance_cursor uses pool.execute

    class _Acq:
        async def __aenter__(self):
            raise RuntimeError("db blip during txn")

        async def __aexit__(self, *a):
            return False

    pool.acquire = MagicMock(return_value=_Acq())

    # must NOT raise
    await _advance_cursor_and_emit_run(
        pool, uuid.uuid4(), uuid.uuid4(), {"k": "v"},
        {"run_id": str(uuid.uuid4()), "outcome": "succeeded"},
    )
    # fallback cursor-advance ran exactly once on the pool
    assert pool.execute.await_count == 1


# ── _build_run_config (config snapshot + hash) ───────────────────────

def test_build_run_config_returns_hash_and_base_version():
    job = _job(extraction_config={})
    snapshot, cfg_hash, base_version = _build_run_config(job)
    assert snapshot.model_ref == "extractor-model"
    assert len(cfg_hash) == 64
    assert len(base_version) == 8


def test_malformed_extraction_config_falls_back_to_globals_no_raise():
    """/review-impl MED-3 — a malformed per-project override (filter enabled
    with no model_ref, and no global filter in this test env) must NOT raise
    from the telemetry path; it degrades to global defaults."""
    job = _job(extraction_config={"precision_filter": {"enabled": True}})
    snapshot, cfg_hash, base_version = _build_run_config(job)  # must not raise
    # global env has no precision filter in tests → fallback yields None filter
    assert snapshot.precision_filter is None
    assert len(cfg_hash) == 64


def test_override_changes_config_hash_not_default_equals_expected():
    """Guard against the default-equals-expected false-negative
    (memory happy-path-default-value-false-negative): a non-default project
    override must produce a DIFFERENT config_hash than the empty-override
    default, proving extraction_config actually flows into the hash."""
    _, hash_default, _ = _build_run_config(_job(extraction_config={}))
    _, hash_override, _ = _build_run_config(
        _job(extraction_config={"llm_model": {"model_ref": "a-different-model"}})
    )
    assert hash_default != hash_override


# ── _run_payload ─────────────────────────────────────────────────────

def test_run_payload_metrics_from_result():
    job = _job()
    snapshot, cfg_hash, base_version = _build_run_config(job)
    result = ExtractionResult(
        source_id="ch-1", entities_merged=4, relations_created=2,
        events_merged=1, facts_merged=3,
    )
    p = _run_payload(
        job=job, book_id=uuid.uuid4(), chapter_ref="ch-1", snapshot=snapshot,
        cfg_hash=cfg_hash, base_version=base_version, outcome="succeeded", result=result,
    )
    assert p["outcome"] == "succeeded"
    assert p["outcome_source"] == "pipeline"
    assert p["scope"] == "chapter"
    assert p["config_hash"] == cfg_hash
    assert p["metrics"]["entities_merged"] == 4
    assert p["metrics"]["relations_created"] == 2
    # resolved_config carries prompt IDENTITY, never raw prompt text
    assert "prompts" not in p["resolved_config"]
    assert set(p["prompt_versions"])  # non-empty


def test_run_payload_key_set_is_pinned_to_consumer_contract():
    """/review-impl MED-2 — pin the producer↔consumer payload contract.

    The learning-service `handle_run_completed` reads exactly these top-level
    keys. Neither unit suite alone proves the producer's output matches the
    consumer's reads (each builds its own payload), so this test fails loudly if
    `_run_payload` renames/drops a field — prompting a matching handler update
    (memory `test-input-fields-from-producer-schema`,
    `mock-only-coverage-hides-crossservice-bugs`)."""
    job = _job()
    snapshot, cfg_hash, base_version = _build_run_config(job)
    p = _run_payload(
        job=job, book_id=uuid.uuid4(), chapter_ref="ch-1", snapshot=snapshot,
        cfg_hash=cfg_hash, base_version=base_version, outcome="succeeded", result=None,
    )
    assert set(p.keys()) == {
        "run_id", "user_id", "project_id", "book_id", "job_id", "scope",
        "chapter_ref", "config_hash", "resolved_config", "prompt_versions",
        "base_default_version", "model_ref", "metrics", "outcome",
        "outcome_source", "emitted_at",
    }


def test_run_payload_skip_has_zero_metrics():
    job = _job()
    snapshot, cfg_hash, base_version = _build_run_config(job)
    p = _run_payload(
        job=job, book_id=None, chapter_ref="ch-9", snapshot=snapshot,
        cfg_hash=cfg_hash, base_version=base_version, outcome="skipped", result=None,
    )
    assert p["outcome"] == "skipped"
    assert p["book_id"] is None
    assert p["metrics"]["entities_merged"] == 0
