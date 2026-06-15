"""B2-A — worker-ai run telemetry: outbox emit + config snapshot/payload."""

from __future__ import annotations

import json
import uuid
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from loreweave_extraction import PrecisionFilterConfig

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


_CHAP_EXTRACTED = {
    "user_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
    "project_id": "99999999-9999-9999-9999-999999999999",
    "book_id": "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
    "chapter_id": "11111111-1111-1111-1111-111111111111",
}


async def test_chapter_extracted_emitted_in_same_txn():
    # D-CAMPAIGN-BESTEFFORT-EMIT-REDIS: the campaign completion event rides the
    # SAME transaction as cursor-advance + run-emit (3 writes, atomic).
    pool, conn = _txn_pool()
    await _advance_cursor_and_emit_run(
        pool, uuid.uuid4(), uuid.uuid4(), {"k": "v"},
        {"run_id": str(uuid.uuid4()), "outcome": "succeeded"},
        chapter_extracted=_CHAP_EXTRACTED,
    )
    assert conn.execute.await_count == 3  # cursor UPDATE + run INSERT + chapter INSERT


async def test_chapter_extracted_best_effort_on_txn_fallback():
    # On the tx-failure fallback, the cursor still advances AND we best-effort emit
    # the chapter event (the campaign's stuck-reconcile is the backstop for loss).
    pool = AsyncMock()
    pool.execute = AsyncMock()

    class _Acq:
        async def __aenter__(self):
            raise RuntimeError("db blip during txn")

        async def __aexit__(self, *a):
            return False

    pool.acquire = MagicMock(return_value=_Acq())
    await _advance_cursor_and_emit_run(
        pool, uuid.uuid4(), uuid.uuid4(), {"k": "v"},
        {"run_id": str(uuid.uuid4()), "outcome": "succeeded"},
        chapter_extracted=_CHAP_EXTRACTED,
    )
    # fallback cursor-advance + best-effort chapter emit, both on the pool
    assert pool.execute.await_count == 2


# ── _build_run_config (config snapshot + hash) ───────────────────────

def test_build_run_config_returns_hash_and_base_version():
    job = _job(extraction_config={})
    snapshot, cfg_hash, base_version = _build_run_config(job)
    assert snapshot.model_ref == "extractor-model"
    assert len(cfg_hash) == 64
    assert len(base_version) == 8


def test_malformed_extraction_config_falls_back_to_globals_no_raise():
    """/review-impl MED-3 — a per-project override that enables the filter with no
    model_ref must NOT raise from the telemetry path. Since D-WX-PRECISION-FILTER-MODEL-ARCH
    (94bba787) the env is no longer a model source, so the fallback for an enabled filter
    with no model is the per-user EXTRACTION model — NOT None."""
    job = _job(extraction_config={"precision_filter": {"enabled": True}})
    snapshot, cfg_hash, base_version = _build_run_config(job)  # must not raise
    # enabled-without-model → reuse the extraction model (env is no longer a model source).
    assert snapshot.precision_filter is not None
    assert snapshot.precision_filter.model_ref == "extractor-model"
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
        "outcome_source", "genre", "save_raw_extraction", "emitted_at",
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


# ── B2-B-b1: per-project config drives extract_pass2 (sentinel resolution) ──

async def test_extract_and_persist_omitted_filter_uses_global(monkeypatch):
    """Omitting precision_filter → the module global (chat_turn/glossary path)."""
    from app import runner

    captured = {}

    class _Cands:
        entities = []
        relations = []
        events = []
        facts = []
        filter_status = "skipped"

    async def fake_extract_pass2(**kwargs):
        captured.update(kwargs)
        return _Cands()

    sentinel_cfg = PrecisionFilterConfig(model_ref="global-filter")
    monkeypatch.setattr(runner, "extract_pass2", fake_extract_pass2)
    monkeypatch.setattr(runner, "_PRECISION_FILTER_CONFIG", sentinel_cfg)

    kc = AsyncMock()
    kc.persist_pass2 = AsyncMock(return_value=ExtractionResult(
        source_id="s", entities_merged=0, relations_created=0,
        events_merged=0, facts_merged=0,
    ))
    await runner._extract_and_persist(
        knowledge_client=kc, llm_client=MagicMock(), user_id=uuid.uuid4(),
        project_id=uuid.uuid4(), source_type="chat_turn", source_id="s",
        job_id=uuid.uuid4(), model_ref="m", text="hello",
    )
    assert captured["precision_filter"] is sentinel_cfg


async def test_extract_and_persist_forwards_targets_to_sdk_and_persist(monkeypatch):
    """C12 — targets reach extract_pass2 (as a set) AND persist_pass2 (as a
    list, for the summary-enqueue gate)."""
    from app import runner

    captured = {}
    persist_kwargs = {}

    class _Cands:
        entities = []
        relations = []
        events = []
        facts = []
        filter_status = "skipped"

    async def fake_extract_pass2(**kwargs):
        captured.update(kwargs)
        return _Cands()

    async def fake_persist(**kwargs):
        persist_kwargs.update(kwargs)
        return ExtractionResult(
            source_id="s", entities_merged=0, relations_created=0,
            events_merged=0, facts_merged=0,
        )

    monkeypatch.setattr(runner, "extract_pass2", fake_extract_pass2)
    kc = AsyncMock()
    kc.persist_pass2 = AsyncMock(side_effect=fake_persist)
    await runner._extract_and_persist(
        knowledge_client=kc, llm_client=MagicMock(), user_id=uuid.uuid4(),
        project_id=uuid.uuid4(), source_type="chapter", source_id="s",
        job_id=uuid.uuid4(), model_ref="m", text="hello",
        targets=["entities", "events"],
    )
    assert captured["targets"] == {"entities", "events"}
    assert persist_kwargs["targets"] == ["entities", "events"]


async def test_extract_and_persist_forwards_concurrency_level(monkeypatch):
    """C12 — concurrency_level reaches extract_pass2 (caps the R/E/F gather)."""
    from app import runner

    captured = {}

    class _Cands:
        entities = []
        relations = []
        events = []
        facts = []
        filter_status = "skipped"

    async def fake_extract_pass2(**kwargs):
        captured.update(kwargs)
        return _Cands()

    monkeypatch.setattr(runner, "extract_pass2", fake_extract_pass2)
    kc = AsyncMock()
    kc.persist_pass2 = AsyncMock(return_value=ExtractionResult(
        source_id="s", entities_merged=0, relations_created=0,
        events_merged=0, facts_merged=0,
    ))
    await runner._extract_and_persist(
        knowledge_client=kc, llm_client=MagicMock(), user_id=uuid.uuid4(),
        project_id=uuid.uuid4(), source_type="chapter", source_id="s",
        job_id=uuid.uuid4(), model_ref="m", text="hello",
        concurrency_level=2,
    )
    assert captured["concurrency_level"] == 2


async def test_extract_and_persist_targets_none_passes_none(monkeypatch):
    """C12 back-compat — targets omitted ⇒ None to the SDK (all passes)."""
    from app import runner

    captured = {}

    class _Cands:
        entities = []
        relations = []
        events = []
        facts = []
        filter_status = "skipped"

    async def fake_extract_pass2(**kwargs):
        captured.update(kwargs)
        return _Cands()

    monkeypatch.setattr(runner, "extract_pass2", fake_extract_pass2)
    kc = AsyncMock()
    kc.persist_pass2 = AsyncMock(return_value=ExtractionResult(
        source_id="s", entities_merged=0, relations_created=0,
        events_merged=0, facts_merged=0,
    ))
    await runner._extract_and_persist(
        knowledge_client=kc, llm_client=MagicMock(), user_id=uuid.uuid4(),
        project_id=uuid.uuid4(), source_type="chat_turn", source_id="s",
        job_id=uuid.uuid4(), model_ref="m", text="hello",
    )
    assert captured["targets"] is None


async def test_extract_and_persist_forwards_prompt_overrides(monkeypatch):
    """B2-B-b2 — per-op prompt_overrides from the snapshot reach extract_pass2."""
    from app import runner

    captured = {}

    class _Cands:
        entities = []
        relations = []
        events = []
        facts = []
        filter_status = "skipped"

    async def fake_extract_pass2(**kwargs):
        captured.update(kwargs)
        return _Cands()

    monkeypatch.setattr(runner, "extract_pass2", fake_extract_pass2)
    kc = AsyncMock()
    kc.persist_pass2 = AsyncMock(return_value=ExtractionResult(
        source_id="s", entities_merged=0, relations_created=0,
        events_merged=0, facts_merged=0,
    ))
    overrides = {"entity": {"system": "custom entity prompt"}}
    await runner._extract_and_persist(
        knowledge_client=kc, llm_client=MagicMock(), user_id=uuid.uuid4(),
        project_id=uuid.uuid4(), source_type="chapter", source_id="s",
        job_id=uuid.uuid4(), model_ref="m", text="hello",
        prompt_overrides=overrides,
    )
    assert captured["prompt_overrides"] == overrides


async def test_extract_and_persist_forwards_writer_autocreate(monkeypatch):
    """B2 follow-up — per-project writer_autocreate reaches persist_pass2."""
    from app import runner

    class _Cands:
        entities = []
        relations = []
        events = []
        facts = []
        filter_status = "skipped"

    async def fake_extract_pass2(**kwargs):
        return _Cands()

    monkeypatch.setattr(runner, "extract_pass2", fake_extract_pass2)
    kc = AsyncMock()
    kc.persist_pass2 = AsyncMock(return_value=ExtractionResult(
        source_id="s", entities_merged=0, relations_created=0,
        events_merged=0, facts_merged=0,
    ))
    await runner._extract_and_persist(
        knowledge_client=kc, llm_client=MagicMock(), user_id=uuid.uuid4(),
        project_id=uuid.uuid4(), source_type="chapter", source_id="s",
        job_id=uuid.uuid4(), model_ref="m", text="hello",
        writer_autocreate=True,
    )
    assert kc.persist_pass2.await_args.kwargs["writer_autocreate"] is True


def test_writer_autocreate_default_reads_env(monkeypatch):
    """_WRITER_AUTOCREATE_DEFAULT is True when env var is set to 'true'."""
    import importlib
    from app import runner

    monkeypatch.setenv("KNOWLEDGE_EXTRACTION_WRITER_AUTOCREATE_ENABLED", "true")
    importlib.reload(runner)
    assert runner._WRITER_AUTOCREATE_DEFAULT is True

    monkeypatch.setenv("KNOWLEDGE_EXTRACTION_WRITER_AUTOCREATE_ENABLED", "false")
    importlib.reload(runner)
    assert runner._WRITER_AUTOCREATE_DEFAULT is False


def test_run_payload_forwards_genre():
    """E2 — genre from JobRow appears as top-level key in the run payload."""
    job = _job(genre="Tiên hiệp")
    snapshot, cfg_hash, base_version = _build_run_config(job)
    payload = _run_payload(
        job=job, book_id=None, chapter_ref="ch01",
        snapshot=snapshot, cfg_hash=cfg_hash, base_version=base_version,
        outcome="succeeded", result=None,
    )
    assert payload["genre"] == "Tiên hiệp"


def test_run_payload_genre_none_when_unset():
    """E2 — genre=None propagates (not dropped from wire)."""
    job = _job(genre=None)
    snapshot, cfg_hash, base_version = _build_run_config(job)
    payload = _run_payload(
        job=job, book_id=None, chapter_ref="ch01",
        snapshot=snapshot, cfg_hash=cfg_hash, base_version=base_version,
        outcome="succeeded", result=None,
    )
    assert "genre" in payload
    assert payload["genre"] is None


async def test_extract_and_persist_explicit_none_disables_not_global(monkeypatch):
    """Explicit precision_filter=None → DISABLED, must NOT fall back to the
    global (memory sdk-default-arg-dropped-from-wire — the sentinel guards this)."""
    from app import runner

    captured = {}

    class _Cands:
        entities = []
        relations = []
        events = []
        facts = []
        filter_status = "skipped"

    async def fake_extract_pass2(**kwargs):
        captured.update(kwargs)
        return _Cands()

    monkeypatch.setattr(runner, "extract_pass2", fake_extract_pass2)
    monkeypatch.setattr(runner, "_PRECISION_FILTER_CONFIG",
                        PrecisionFilterConfig(model_ref="global-filter"))

    kc = AsyncMock()
    kc.persist_pass2 = AsyncMock(return_value=ExtractionResult(
        source_id="s", entities_merged=0, relations_created=0,
        events_merged=0, facts_merged=0,
    ))
    await runner._extract_and_persist(
        knowledge_client=kc, llm_client=MagicMock(), user_id=uuid.uuid4(),
        project_id=uuid.uuid4(), source_type="chapter", source_id="s",
        job_id=uuid.uuid4(), model_ref="m", text="hello",
        precision_filter=None, entity_recovery=None,
    )
    assert captured["precision_filter"] is None
    assert captured["entity_recovery"] is None
