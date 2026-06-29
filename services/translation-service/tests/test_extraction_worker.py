"""Extraction worker — runaway-fix regression tests.

Covers the two bugs behind a glossary-extraction job that "ran for days and
ignored cancel":
  1. cancel-safe claim — a cancelled/terminal job is NOT clobbered back to
     'running'; the handler settles + returns so the AMQP message is ACKed
     (stops the redelivery loop).
  2. resume-from-checkpoint — chapters already finished on a prior delivery are
     skipped (no re-spent LLM), and completed/failed seed from the checkpoint so
     the job converges to a terminal state instead of restarting at 0 forever.
"""
import logging
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from loreweave_llm.models import Job

from app.workers import extraction_worker as ew
from app.workers.extraction_worker import _run_extraction_job
from app.workers.extraction_prompt import ParseStats


class _AcquireCM:
    def __init__(self, db):
        self._db = db

    async def __aenter__(self):
        return self._db

    async def __aexit__(self, *_):
        return False


def _pool(db):
    pool = MagicMock()
    pool.acquire = MagicMock(return_value=_AcquireCM(db))
    return pool


@pytest.mark.asyncio
async def test_cancelled_job_is_not_clobbered_and_does_no_work():
    # claim UPDATE matches nothing (job is cancelling/terminal) → fetchval None
    db = AsyncMock()
    db.fetchval = AsyncMock(return_value=None)
    db.execute = AsyncMock()
    db.fetch = AsyncMock(return_value=[])
    publish, publish_event = AsyncMock(), AsyncMock()

    with patch("app.workers.extraction_worker.fetch_known_entities", new=AsyncMock(return_value=[])) as known, \
         patch("app.workers.extraction_worker._process_extraction_chapter", new=AsyncMock()) as proc:
        await _run_extraction_job(
            {"book_id": "b", "chapter_ids": [str(uuid4()), str(uuid4())]},
            uuid4(), "u", _pool(db), publish, publish_event, MagicMock(),
        )

    known.assert_not_awaited()   # never fetched known entities → never started the run
    proc.assert_not_awaited()    # never processed a chapter → no LLM spend
    # settled the 'cancelling' row to a terminal 'cancelled' (not re-armed to running).
    # The settle is now a guarded `fetchval … RETURNING job_id` (so the worker only emits
    # 'cancelled' when it actually flipped a cancelling row, not for an already-terminal job).
    assert any("status='cancelled'" in str(c.args[0]) for c in db.fetchval.await_args_list)
    # emitted a cancelled status event
    assert any(
        c.args[1].get("payload", {}).get("status") == "cancelled"
        for c in publish_event.await_args_list
    )
    # CRUCIALLY: the claim UPDATE is guarded (won't run a cancelled job)
    claim_sql = db.fetchval.await_args_list[0].args[0]
    assert "status NOT IN" in claim_sql and "RETURNING job_id" in claim_sql


@pytest.mark.asyncio
async def test_resume_skips_completed_chapters_and_finalizes():
    jid = uuid4()
    c1, c2 = str(uuid4()), str(uuid4())
    db = AsyncMock()
    db.fetchval = AsyncMock(return_value=jid)  # claim succeeds
    db.fetch = AsyncMock(return_value=[
        {"chapter_id": c1, "status": "completed", "it": 100, "ot": 50},
        {"chapter_id": c2, "status": "completed", "it": 200, "ot": 80},
    ])
    db.execute = AsyncMock()
    publish, publish_event = AsyncMock(), AsyncMock()

    with patch("app.workers.extraction_worker.fetch_known_entities", new=AsyncMock(return_value=[])), \
         patch("app.workers.extraction_worker._process_extraction_chapter", new=AsyncMock()) as proc, \
         patch("app.workers.extraction_worker.resolve_job_cost_usd", new=AsyncMock(return_value=None)), \
         patch("app.workers.extraction_worker.emit_job_event_safe", new=AsyncMock()) as emit:
        await _run_extraction_job(
            {"book_id": "b", "chapter_ids": [c1, c2]},
            jid, "u", _pool(db), publish, publish_event, MagicMock(),
        )

    proc.assert_not_awaited()  # both chapters already done on a prior delivery → no work
    # finalized: the terminal UPDATE ran with status='completed' (failed==0)
    finals = [c for c in db.execute.await_args_list if "SET status=$2, finished_at=now()" in str(c.args[0])]
    assert finals and finals[-1].args[2] == "completed"
    # Unified Job Control Plane (D-JOBS-GLOSSARY-EXTRACT-UNWIRED): emitted running on claim
    # + completed on finalize, as kind='glossary_extraction'.
    emitted = [c.kwargs.get("status") for c in emit.await_args_list]
    assert "running" in emitted and "completed" in emitted
    assert all(c.kwargs.get("kind") == "glossary_extraction" for c in emit.await_args_list)


@pytest.mark.asyncio
async def test_late_cancel_on_last_chapter_finalizes_as_cancelled():
    # bug #34 (live-smoke D-CANCEL-IMMEDIATE): a cancel that lands DURING the last chapter
    # aborts its in-flight LLM calls (cancel_check → DELETE → upstream abort) but the
    # per-chapter cooperative gate never fires again (no chapter left to gate), so the loop
    # falls through to finalize with the job still 'cancelling'. The finalize must honor the
    # cancel — report 'cancelled' (completed chapters kept) — NOT let the chapter-aggregate
    # mask it as 'completed'/'completed_with_errors'. The smoke caught the row + the unified
    # jobs stream both mislabeling an explicit cancel as "completed with errors".
    jid = uuid4()
    c1 = str(uuid4())
    db = AsyncMock()
    # claim UPDATE...RETURNING → jid; the lone "SELECT status FROM extraction_jobs" is the
    # NEW finalize check (the per-chapter gate is skipped — c1 is a resume-done chapter) →
    # 'cancelling' simulates the cancel arriving mid-last-chapter.
    async def _fetchval(query, *args):
        if "SELECT status FROM extraction_jobs" in str(query):
            return "cancelling"
        return jid

    db.fetchval = AsyncMock(side_effect=_fetchval)
    # one resume-done chapter → aggregate would be 'completed' (failed==0, errors==0)
    db.fetch = AsyncMock(return_value=[
        {"chapter_id": c1, "status": "completed", "it": 100, "ot": 50},
    ])
    db.execute = AsyncMock()
    publish, publish_event = AsyncMock(), AsyncMock()

    with patch("app.workers.extraction_worker.fetch_known_entities", new=AsyncMock(return_value=[])), \
         patch("app.workers.extraction_worker._process_extraction_chapter", new=AsyncMock()) as proc, \
         patch("app.workers.extraction_worker.resolve_job_cost_usd", new=AsyncMock(return_value=None)), \
         patch("app.workers.extraction_worker.emit_job_event_safe", new=AsyncMock()) as emit:
        await _run_extraction_job(
            {"book_id": "b", "chapter_ids": [c1]},
            jid, "u", _pool(db), publish, publish_event, MagicMock(),
        )

    proc.assert_not_awaited()  # c1 already done → no work; cancel lands at finalize
    # the terminal UPDATE wrote 'cancelled', NOT the 'completed' aggregate it would otherwise be
    finals = [c for c in db.execute.await_args_list if "SET status=$2, finished_at=now()" in str(c.args[0])]
    assert finals and finals[-1].args[2] == "cancelled"
    # the unified jobs stream agrees: canonical terminal event is 'cancelled' (not 'completed')
    assert any(c.kwargs.get("status") == "cancelled" for c in emit.await_args_list)
    assert not any(c.kwargs.get("status") == "completed" for c in emit.await_args_list)
    # the SSE payload to the user also reads 'cancelled'
    terminal_payloads = [c.args[1]["payload"]["status"] for c in publish_event.await_args_list
                         if c.args[1].get("event") == "job.status_changed"
                         and c.args[1]["payload"].get("status") in ("completed", "completed_with_errors", "cancelled", "failed")]
    assert terminal_payloads and terminal_payloads[-1] == "cancelled"


@pytest.mark.asyncio
async def test_per_chapter_emits_unified_progress_for_live_monitoring():
    # bug #2 (D-JOBS-EXTRACT-LIVE-PROGRESS): each processed chapter mirrors progress onto the
    # UNIFIED jobs-service stream (a 'running' event carrying progress={done,total}) so the
    # /jobs detail page advances live instead of sitting frozen between the lone 'running'
    # transition and the terminal event.
    jid = uuid4()
    c1 = str(uuid4())
    db = AsyncMock()
    db.fetchval = AsyncMock(return_value=jid)  # claim succeeds; in-loop status check → not cancelled
    db.fetch = AsyncMock(return_value=[])      # no resume checkpoint; empty finalize rollup
    db.execute = AsyncMock()
    publish, publish_event = AsyncMock(), AsyncMock()

    with patch("app.workers.extraction_worker.fetch_known_entities", new=AsyncMock(return_value=[])), \
         patch("app.workers.extraction_worker._process_extraction_chapter", new=AsyncMock(return_value={})) as proc, \
         patch("app.workers.extraction_worker.emit_job_event_safe", new=AsyncMock()) as emit:
        await _run_extraction_job(
            {"book_id": "b", "chapter_ids": [c1]},
            jid, "u", _pool(db), publish, publish_event, MagicMock(),
        )

    proc.assert_awaited_once()
    progress_emits = [
        c for c in emit.await_args_list
        if c.kwargs.get("status") == "running" and c.kwargs.get("progress")
    ]
    assert progress_emits, "no unified 'running' progress event emitted for live /jobs monitoring"
    # baseline (0/1 before the loop) + per-chapter (1/1 after processing c1)
    assert progress_emits[0].kwargs["progress"] == {"done": 0, "total": 1}
    assert progress_emits[-1].kwargs["progress"] == {"done": 1, "total": 1}
    assert all(c.kwargs.get("kind") == "glossary_extraction" for c in progress_emits)


@pytest.mark.asyncio
async def test_progress_emits_llm_calls_done_from_batch_outcomes():
    # bug #37 — the running progress emit advances params.llm_calls_done = accumulated realized
    # batch calls (one per BatchOutcome row, the unit estimated_llm_calls counts). Baseline
    # starts at 0 (the seed count from the mock is a non-int → 0), then climbs per chapter.
    jid = uuid4()
    c1 = str(uuid4())
    db = AsyncMock()
    db.fetchval = AsyncMock(return_value=jid)  # claim ok; seed count → non-int → 0
    db.fetch = AsyncMock(return_value=[])
    db.execute = AsyncMock()
    publish, publish_event = AsyncMock(), AsyncMock()
    chapter_result = {
        "created": 1, "input_tokens": 10, "output_tokens": 5, "entities": [],
        "batch_outcomes": [{"status": "completed"}, {"status": "completed"}, {"status": "completed"}],
    }
    with patch("app.workers.extraction_worker.fetch_known_entities", new=AsyncMock(return_value=[])), \
         patch("app.workers.extraction_worker._process_extraction_chapter",
               new=AsyncMock(return_value=chapter_result)), \
         patch("app.workers.extraction_worker.resolve_job_cost_usd", new=AsyncMock(return_value=None)), \
         patch("app.workers.extraction_worker.emit_job_event_safe", new=AsyncMock()) as emit:
        await _run_extraction_job(
            {"book_id": "b", "chapter_ids": [c1]},
            jid, "u", _pool(db), publish, publish_event, MagicMock(),
        )
    running = [c for c in emit.await_args_list
               if c.kwargs.get("status") == "running" and c.kwargs.get("progress")]
    assert running[0].kwargs.get("params", {}).get("llm_calls_done") == 0   # baseline pre-loop
    assert running[-1].kwargs.get("params", {}).get("llm_calls_done") == 3   # after 1 chapter, 3 batches


@pytest.mark.asyncio
async def test_progress_and_terminal_carry_live_cost_and_tokens():
    # bug #3: the unified Jobs detail Cost & Usage panel must update live, not only at
    # completion. Each progress emit + the terminal emit carry tokens_in/out and a cost_usd
    # PRICED FROM THE ACTUAL summed tokens via the provider-registry oracle (not a placeholder),
    # and finalize persists cost_usd onto extraction_jobs.
    jid = uuid4()
    c1 = str(uuid4())
    db = AsyncMock()
    db.fetchval = AsyncMock(return_value=jid)
    db.fetch = AsyncMock(return_value=[])
    db.execute = AsyncMock()
    publish, publish_event = AsyncMock(), AsyncMock()
    chapter_result = {"created": 2, "input_tokens": 100, "output_tokens": 40, "entities": []}

    with patch("app.workers.extraction_worker.fetch_known_entities", new=AsyncMock(return_value=[])), \
         patch("app.workers.extraction_worker._process_extraction_chapter",
               new=AsyncMock(return_value=chapter_result)), \
         patch("app.workers.extraction_worker.resolve_job_cost_usd",
               new=AsyncMock(return_value=0.0123)) as price, \
         patch("app.workers.extraction_worker.emit_job_event_safe", new=AsyncMock()) as emit:
        await _run_extraction_job(
            {"book_id": "b", "chapter_ids": [c1], "model_source": "user_model", "model_ref": "m1"},
            jid, "u", _pool(db), publish, publish_event, MagicMock(),
        )

    # cost is priced from the ACTUAL summed tokens (100/40), not a flat placeholder
    price.assert_awaited()
    assert price.await_args_list[-1].kwargs["input_tokens"] == 100
    assert price.await_args_list[-1].kwargs["output_tokens"] == 40
    # the post-chapter progress emit carries live cost + tokens (updates every chapter)
    progress_emits = [c for c in emit.await_args_list
                      if c.kwargs.get("status") == "running" and c.kwargs.get("progress")]
    live = progress_emits[-1].kwargs
    assert live["cost_usd"] == 0.0123
    assert live["tokens_in"] == 100 and live["tokens_out"] == 40
    # the terminal emit also carries the final cost + tokens
    terminal = [c for c in emit.await_args_list
                if c.kwargs.get("status") in ("completed", "completed_with_errors", "failed")]
    assert terminal and terminal[-1].kwargs["cost_usd"] == 0.0123
    assert terminal[-1].kwargs["tokens_in"] == 100
    # finalize persisted cost_usd onto extraction_jobs
    assert any("cost_usd=COALESCE" in str(c.args[0]) for c in db.execute.await_args_list)


@pytest.mark.asyncio
async def test_cost_repricing_is_throttled_not_every_chapter():
    # bug #3 review (MED): pricing hits provider-registry on a 5s-timeout network call.
    # Repricing every chapter would couple the run's latency to registry health (a degraded
    # registry → +5s PER chapter). Cost is re-priced on the first chapter + every
    # _COST_REPRICE_EVERY, reusing the last figure between — while TOKENS update on every emit.
    jid = uuid4()
    chapters = [str(uuid4()) for _ in range(6)]
    db = AsyncMock()
    db.fetchval = AsyncMock(return_value=jid)  # claim + each in-loop status check → not cancelled
    db.fetch = AsyncMock(return_value=[])
    db.execute = AsyncMock()
    publish, publish_event = AsyncMock(), AsyncMock()
    result = {"created": 1, "input_tokens": 10, "output_tokens": 5, "entities": []}

    with patch("app.workers.extraction_worker.fetch_known_entities", new=AsyncMock(return_value=[])), \
         patch("app.workers.extraction_worker._process_extraction_chapter", new=AsyncMock(return_value=result)), \
         patch("app.workers.extraction_worker.resolve_job_cost_usd", new=AsyncMock(return_value=0.02)) as price, \
         patch("app.workers.extraction_worker.emit_job_event_safe", new=AsyncMock()) as emit:
        await _run_extraction_job(
            {"book_id": "b", "chapter_ids": chapters, "model_source": "user_model", "model_ref": "m1"},
            jid, "u", _pool(db), publish, publish_event, MagicMock(),
        )

    # 6 chapters but far fewer reprices (baseline + first + every-5th + finalize = 4) — WITHOUT
    # the throttle this would be 8 (baseline + 6 + finalize). The `< len` bound proves throttle.
    assert price.await_count < len(chapters), f"cost re-priced too often: {price.await_count}"
    # every per-chapter progress emit still carries live, cumulative tokens
    progress_emits = [c for c in emit.await_args_list
                      if c.kwargs.get("status") == "running" and c.kwargs.get("progress")]
    assert len(progress_emits) == len(chapters) + 1  # baseline + one per chapter
    assert progress_emits[-1].kwargs["tokens_in"] == 60  # 6 × 10, cumulative & live


@pytest.mark.asyncio
async def test_job_terminal_emits_batch_summary_rollup():
    # OBS/M2 (INV-O14): the job-terminal notification carries a per-status rollup derived
    # from the extraction_batch_outcomes SSOT, so a truncated/rejected batch is visible.
    jid = uuid4()
    c1 = str(uuid4())
    db = AsyncMock()
    db.fetchval = AsyncMock(return_value=jid)  # claim succeeds
    db.fetch = AsyncMock(side_effect=[
        # 1) resume checkpoint: c1 already completed on a prior delivery.
        [{"chapter_id": c1, "status": "completed", "it": 10, "ot": 5}],
        # 2) the finalize rollup query over extraction_batch_outcomes.
        [{"status": "ok", "n": 3}, {"status": "truncated", "n": 1}],
    ])
    db.execute = AsyncMock()
    publish, publish_event = AsyncMock(), AsyncMock()

    with patch("app.workers.extraction_worker.fetch_known_entities", new=AsyncMock(return_value=[])), \
         patch("app.workers.extraction_worker._process_extraction_chapter", new=AsyncMock()), \
         patch("app.workers.extraction_worker.resolve_job_cost_usd", new=AsyncMock(return_value=None)), \
         patch("app.workers.extraction_worker.emit_job_event_safe", new=AsyncMock()):
        await _run_extraction_job(
            {"book_id": "b", "chapter_ids": [c1]},
            jid, "u", _pool(db), publish, publish_event, MagicMock(),
        )

    terminal = [
        c.args[1]["payload"] for c in publish_event.await_args_list
        if c.args[1].get("payload", {}).get("status") in ("completed", "completed_with_errors", "failed")
    ]
    assert terminal, "no terminal status_changed event emitted"
    assert terminal[-1]["batch_summary"] == {"ok": 3, "truncated": 1}


@pytest.mark.asyncio
async def test_cache_hit_skips_llm_and_reuses_entities():
    # CACHE/M6: a cached batch reuses the stored parse — the LLM is NOT called, no new tokens,
    # and the cached entities still flow to the glossary writeback.
    db = AsyncMock()
    db.fetchval = AsyncMock(return_value=uuid4())  # owner_user_id resolve
    db.execute = AsyncMock()
    llm = MagicMock()
    llm.submit_and_wait = AsyncMock()  # must NOT be awaited on a cache hit
    post = AsyncMock(return_value={"created": 1, "updated": 0, "skipped": 0})
    cached = {
        "parsed_entities": [{"name": "张若尘", "kind_code": "character", "evidence": "", "attributes": {}}],
        "finish_reason": "stop", "input_tokens": 0, "output_tokens": 0, "parse_status": "ok",
    }
    put_mock = AsyncMock()

    with patch.object(ew.httpx, "AsyncClient",
                      return_value=_http_cm_returning({"title": "Ch1", "content": "text"})), \
         patch.object(ew, "prepare_chapter_text", new=MagicMock(return_value="some chapter text")), \
         patch.object(ew, "plan_kind_batches", return_value=[["character"]]), \
         patch.object(ew, "build_known_entities_context", return_value=""), \
         patch.object(ew, "stamp_entity_provenance", new=MagicMock()), \
         patch.object(ew, "_persist_batch_outcomes", new=AsyncMock()), \
         patch.object(ew, "get_cached_batch", new=AsyncMock(return_value=cached)), \
         patch.object(ew, "put_batch", new=put_mock), \
         patch.object(ew, "post_extracted_entities", new=post):
        result = await ew._process_extraction_chapter(
            job_id=uuid4(), book_id="b", chapter_id=uuid4(), chapter_index=0,
            extraction_profile={"character": {}}, kinds_metadata=[], known_entities=[],
            source_language="zh", model_source="user_model", model_ref=str(uuid4()),
            max_entities_per_kind=10, thinking_enabled=False, reasoning_effort=None,
            pool=_pool(db), llm_client=llm,
        )

    llm.submit_and_wait.assert_not_awaited()  # LLM skipped
    put_mock.assert_not_awaited()             # nothing new to cache on a hit
    assert result.get("output_tokens", 0) == 0  # no new tokens spent
    posted = post.await_args.kwargs["entities"]
    assert any(e.get("name") == "张若尘" for e in posted)  # cached entity reached writeback


@pytest.mark.asyncio
async def test_cache_busts_on_model_change_when_enabled(monkeypatch):
    # D-CACHE-MODEL-KEY: with the flag ON, a cache hit whose stored model_ref differs from the
    # CURRENT model is busted → the LLM IS called (re-extract on a model change). Default-off is
    # covered by test_cache_hit_skips_llm (the hit is reused).
    monkeypatch.setattr(ew.settings, "extraction_cache_bust_on_model_change", True)
    db = AsyncMock()
    db.fetchval = AsyncMock(return_value=uuid4())
    db.execute = AsyncMock()
    llm = MagicMock()
    llm.submit_and_wait = AsyncMock(return_value=_sdk_job("stop"))
    cached = {  # a parse produced by a DIFFERENT (old) model
        "parsed_entities": [{"name": "X", "kind_code": "character"}], "finish_reason": "stop",
        "input_tokens": 0, "output_tokens": 0, "parse_status": "ok", "model_ref": str(uuid4()),
    }
    with patch.object(ew.httpx, "AsyncClient",
                      return_value=_http_cm_returning({"title": "Ch1", "content": "text"})), \
         patch.object(ew, "prepare_chapter_text", new=MagicMock(return_value="short chapter text")), \
         patch.object(ew, "plan_kind_batches", return_value=[["character"]]), \
         patch.object(ew, "build_known_entities_context", return_value=""), \
         patch.object(ew, "build_extraction_prompt", return_value={}), \
         patch.object(ew, "build_system_prompt", return_value="sys"), \
         patch.object(ew, "build_user_prompt", return_value="usr"), \
         patch.object(ew, "parse_and_validate_with_stats",
                      return_value=([], ParseStats(raw_count=0, parse_ok=True))), \
         patch.object(ew, "stamp_entity_provenance", new=MagicMock()), \
         patch.object(ew, "_persist_batch_outcomes", new=AsyncMock()), \
         patch.object(ew, "get_cached_batch", new=AsyncMock(return_value=cached)), \
         patch.object(ew, "put_batch", new=AsyncMock()), \
         patch.object(ew, "post_extracted_entities", new=AsyncMock(return_value={})):
        await ew._process_extraction_chapter(
            job_id=uuid4(), book_id="b", chapter_id=uuid4(), chapter_index=0,
            extraction_profile={"character": {}}, kinds_metadata=[], known_entities=[],
            source_language="zh", model_source="user_model", model_ref=str(uuid4()),  # NEW model
            max_entities_per_kind=10, thinking_enabled=False, pool=_pool(db), llm_client=llm,
        )
    llm.submit_and_wait.assert_awaited()  # cache busted on the model change → a live call ran


@pytest.mark.asyncio
async def test_unplannable_oversized_window_skips_llm(caplog):
    # D-CACHE-PLANNER-WIRING Part 2: a window too big to fit the context even alone is flagged
    # `unplannable` by the pre-flight planner gate → its LLM call is SKIPPED (no truncation, no
    # tokens), the batch outcome is recorded `unplannable`, and the chapter derives
    # completed_with_errors so the un-fittable block is VISIBLE.
    caplog.set_level(logging.WARNING, logger="app.workers.extraction_worker")
    db = AsyncMock()
    db.fetchval = AsyncMock(return_value=uuid4())  # owner_user_id resolve
    db.execute = AsyncMock()
    llm = MagicMock()
    llm.submit_and_wait = AsyncMock()  # must NOT be awaited — the call is skipped
    post = AsyncMock(return_value={"created": 0, "updated": 0, "skipped": 0})
    persisted = {}

    async def _capture_outcomes(pool, job_id, owner, book, chap, outcomes):
        persisted["outcomes"] = outcomes

    huge_window = "这是一个非常长的段落。" * 60_000  # one block far larger than the 8192 ctx

    with patch.object(ew.httpx, "AsyncClient",
                      return_value=_http_cm_returning({"title": "Ch1", "content": "text"})), \
         patch.object(ew, "prepare_chapter_text", new=MagicMock(return_value="some chapter text")), \
         patch.object(ew, "_plan_chapter_windows", return_value=[huge_window]), \
         patch.object(ew, "plan_kind_batches", return_value=[["character"]]), \
         patch.object(ew, "build_known_entities_context", return_value=""), \
         patch.object(ew, "stamp_entity_provenance", new=MagicMock()), \
         patch.object(ew, "_persist_batch_outcomes", new=AsyncMock(side_effect=_capture_outcomes)), \
         patch.object(ew, "get_cached_batch", new=AsyncMock(return_value=None)), \
         patch.object(ew, "put_batch", new=AsyncMock()), \
         patch.object(ew, "post_extracted_entities", new=post):
        result = await ew._process_extraction_chapter(
            job_id=uuid4(), book_id="b", chapter_id=uuid4(), chapter_index=0,
            extraction_profile={"character": {}}, kinds_metadata=[], known_entities=[],
            source_language="zh", model_source="user_model", model_ref=str(uuid4()),
            max_entities_per_kind=10, thinking_enabled=False, pool=_pool(db), llm_client=llm,
        )

    llm.submit_and_wait.assert_not_awaited()  # the oversized unit's call was skipped
    assert result["chapter_status"] == "completed_with_errors"
    assert [o["status"] for o in persisted["outcomes"]] == ["unplannable"]
    assert any("UNPLANNABLE" in r.getMessage() for r in caplog.records)


async def _run_with_window_and_ctx(window: str, ctx: int, llm_job):
    """Drive _process_extraction_chapter with a FIXED single window + a FIXED model context, so
    a test can probe the planner gate's budget boundary. Returns (llm_mock, captured_outcomes)."""
    db = AsyncMock()
    db.fetchval = AsyncMock(return_value=uuid4())
    db.execute = AsyncMock()
    llm = MagicMock()
    llm.submit_and_wait = AsyncMock(return_value=llm_job)
    captured = {}

    async def _cap(pool, job_id, owner, book, chap, outcomes):
        captured["outcomes"] = outcomes

    with patch.object(ew.httpx, "AsyncClient",
                      return_value=_http_cm_returning({"title": "Ch1", "content": "text"})), \
         patch.object(ew, "prepare_chapter_text", new=MagicMock(return_value="t")), \
         patch.object(ew, "_get_model_context_window", new=AsyncMock(return_value=ctx)), \
         patch.object(ew, "_plan_chapter_windows", return_value=[window]), \
         patch.object(ew, "plan_kind_batches", return_value=[["character"]]), \
         patch.object(ew, "build_known_entities_context", return_value=""), \
         patch.object(ew, "build_extraction_prompt", return_value={}), \
         patch.object(ew, "build_system_prompt", return_value="sys"), \
         patch.object(ew, "build_user_prompt", return_value="usr"), \
         patch.object(ew, "reasoning_fields", return_value={}), \
         patch.object(ew, "parse_and_validate_with_stats",
                      return_value=([], ParseStats(raw_count=0, parse_ok=True))), \
         patch.object(ew, "stamp_entity_provenance", new=MagicMock()), \
         patch.object(ew, "_persist_batch_outcomes", new=AsyncMock(side_effect=_cap)), \
         patch.object(ew, "get_cached_batch", new=AsyncMock(return_value=None)), \
         patch.object(ew, "put_batch", new=AsyncMock()), \
         patch.object(ew, "post_extracted_entities",
                      new=AsyncMock(return_value={"created": 0, "updated": 0, "skipped": 0})):
        await ew._process_extraction_chapter(
            job_id=uuid4(), book_id="b", chapter_id=uuid4(), chapter_index=0,
            extraction_profile={"character": {}}, kinds_metadata=[], known_entities=[],
            source_language="zh", model_source="user_model", model_ref=str(uuid4()),
            max_entities_per_kind=10, thinking_enabled=False, pool=_pool(db), llm_client=llm,
        )
    return llm, captured.get("outcomes", [])


@pytest.mark.asyncio
async def test_graded_effort_reaches_llm_input():
    # D-RE-WORKER-GRADED-EFFORT: the clamped graded effort reaches the LLM call (NOT collapsed
    # to medium/none by the old thinking_enabled bool) and keys the cache effort_band.
    db = AsyncMock()
    db.fetchval = AsyncMock(return_value=uuid4())
    db.execute = AsyncMock()
    llm = MagicMock()
    llm.submit_and_wait = AsyncMock(return_value=_sdk_job("stop"))
    put_mock = AsyncMock()
    with patch.object(ew.httpx, "AsyncClient",
                      return_value=_http_cm_returning({"title": "Ch1", "content": "text"})), \
         patch.object(ew, "prepare_chapter_text", new=MagicMock(return_value="short chapter text")), \
         patch.object(ew, "plan_kind_batches", return_value=[["character"]]), \
         patch.object(ew, "build_known_entities_context", return_value=""), \
         patch.object(ew, "build_extraction_prompt", return_value={}), \
         patch.object(ew, "build_system_prompt", return_value="sys"), \
         patch.object(ew, "build_user_prompt", return_value="usr"), \
         patch.object(ew, "parse_and_validate_with_stats",
                      return_value=([], ParseStats(raw_count=0, parse_ok=True))), \
         patch.object(ew, "stamp_entity_provenance", new=MagicMock()), \
         patch.object(ew, "_persist_batch_outcomes", new=AsyncMock()), \
         patch.object(ew, "get_cached_batch", new=AsyncMock(return_value=None)), \
         patch.object(ew, "put_batch", new=put_mock), \
         patch.object(ew, "post_extracted_entities", new=AsyncMock(return_value={})):
        await ew._process_extraction_chapter(
            job_id=uuid4(), book_id="b", chapter_id=uuid4(), chapter_index=0,
            extraction_profile={"character": {}}, kinds_metadata=[], known_entities=[],
            source_language="zh", model_source="user_model", model_ref=str(uuid4()),
            max_entities_per_kind=10, thinking_enabled=False, reasoning_effort="low",
            pool=_pool(db), llm_client=llm,
        )
    inp = llm.submit_and_wait.await_args.kwargs["input"]
    assert inp.get("reasoning_effort") == "low"            # graded → reached the LLM
    assert put_mock.await_args.args[1].effort_band == "low"  # graded → keyed the cache
    # bug #24: the Usage-GUI billing label rides job_meta.usage_purpose — lock it so a
    # future refactor can't silently revert glossary extraction to a "chat" label.
    assert llm.submit_and_wait.await_args.kwargs["job_meta"]["usage_purpose"] == "glossary_extraction"


@pytest.mark.asyncio
async def test_gate_budget_boundary_respects_real_context():
    # The SAME window is UNPLANNABLE under a small context but PLANNED under a large one —
    # locks the gate's budget math (a regression making it always- or never-fire breaks this)
    # AND proves the gate uses the REAL resolved context, not a constant.
    from app.workers.chunk_splitter import estimate_tokens
    window = "这是一段中等长度的文本。" * 1500
    win_tok = estimate_tokens(window)
    # est_input = win_tok + schema(20) + known(0) + 600; in_budget = ctx*0.85 − 1024.
    # Unplannable iff ctx < (win_tok + 620 + 1024) / 0.85. Pick contexts well on each side.
    thresh = (win_tok + 1644) / 0.85
    ctx_small, ctx_large = int(thresh) - 3000, int(thresh) + 4000

    llm_small, out_small = await _run_with_window_and_ctx(window, ctx_small, _sdk_job("stop"))
    llm_small.submit_and_wait.assert_not_awaited()          # gate refused → no LLM
    assert [o["status"] for o in out_small] == ["unplannable"]

    llm_large, out_large = await _run_with_window_and_ctx(window, ctx_large, _sdk_job("stop"))
    llm_large.submit_and_wait.assert_awaited_once()         # fits → the LLM ran
    assert "unplannable" not in [o["status"] for o in out_large]


@pytest.mark.asyncio
async def test_truncated_batch_is_not_cached():
    # CACHE/M6 (review-impl HIGH): a truncated batch (entities lost) must NOT be cached, so a
    # re-run re-attempts it instead of replaying the partial result forever.
    db = AsyncMock()
    db.fetchval = AsyncMock(return_value=uuid4())
    db.execute = AsyncMock()
    llm = MagicMock()
    llm.submit_and_wait = AsyncMock(return_value=_sdk_job("length"))  # finish_reason=length
    post = AsyncMock(return_value={"created": 1, "updated": 0, "skipped": 0})
    put_mock = AsyncMock()
    entities = [{"name": "张若尘", "kind_code": "character"}]

    with patch.object(ew.httpx, "AsyncClient",
                      return_value=_http_cm_returning({"title": "Ch1", "content": "text"})), \
         patch.object(ew, "prepare_chapter_text", new=MagicMock(return_value="some chapter text")), \
         patch.object(ew, "plan_kind_batches", return_value=[["character"]]), \
         patch.object(ew, "build_known_entities_context", return_value=""), \
         patch.object(ew, "build_extraction_prompt", return_value={}), \
         patch.object(ew, "build_system_prompt", return_value="sys"), \
         patch.object(ew, "build_user_prompt", return_value="usr"), \
         patch.object(ew, "reasoning_fields", return_value={}), \
         patch.object(ew, "parse_and_validate_with_stats",
                      return_value=(entities, ParseStats(raw_count=1, parse_ok=True))), \
         patch.object(ew, "_persist_batch_outcomes", new=AsyncMock()), \
         patch.object(ew, "get_cached_batch", new=AsyncMock(return_value=None)), \
         patch.object(ew, "put_batch", new=put_mock), \
         patch.object(ew, "post_extracted_entities", new=post):
        await ew._process_extraction_chapter(
            job_id=uuid4(), book_id="b", chapter_id=uuid4(), chapter_index=0,
            extraction_profile={"character": {}}, kinds_metadata=[], known_entities=[],
            source_language="zh", model_source="user_model", model_ref=str(uuid4()),
            max_entities_per_kind=10, thinking_enabled=False, reasoning_effort=None,
            pool=_pool(db), llm_client=llm,
        )

    put_mock.assert_not_awaited()  # truncated → NOT cached (re-run must be able to recover)


# ── M0 (extraction pipeline FND): finish_reason consumption ───────────────


def _http_cm_returning(chapter_json: dict):
    """A patched httpx.AsyncClient() context manager whose .get() returns a
    200 with the given chapter JSON (the book-service chapter fetch)."""
    resp = MagicMock()
    resp.status_code = 200
    resp.json = MagicMock(return_value=chapter_json)
    client = AsyncMock()
    client.get = AsyncMock(return_value=resp)
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=client)
    cm.__aexit__ = AsyncMock(return_value=False)
    return cm


def _sdk_job(finish_reason: str | None):
    """A terminal chat Job as the gateway returns it — finish_reason lives
    INSIDE result (the aggregator stamps it there); the SDK property reads it."""
    result: dict = {
        "messages": [{"role": "assistant", "content": "[]"}],
        "usage": {"input_tokens": 10, "output_tokens": 20},
    }
    if finish_reason is not None:
        result["finish_reason"] = finish_reason
    return Job(
        job_id=str(uuid4()), operation="chat", status="completed",
        result=result, submitted_at="2026-06-21T00:00:00Z",
    )


async def _run_one_chapter_batch(finish_reason: str | None, entities: list[dict],
                                 *, prepare_texts: list[str] | None = None):
    """Drive _process_extraction_chapter through ONE batch with a stubbed LLM
    result carrying `finish_reason`, and stubbed parse → `entities`. Returns
    (result, post_mock) so callers can assert the M1 writeback contract.

    prepare_texts: optional 2-element [initial, recheck] so a test can simulate the
    M1 content-hash drift precondition (initial != recheck → stale skip)."""
    db = AsyncMock()
    db.fetchval = AsyncMock(return_value=uuid4())  # owner_user_id resolve
    llm = MagicMock()
    llm.submit_and_wait = AsyncMock(return_value=_sdk_job(finish_reason))
    post = AsyncMock(return_value={"created": len(entities), "updated": 0, "skipped": 0})

    if prepare_texts is not None:
        prepare_mock = MagicMock(side_effect=prepare_texts)
    else:
        prepare_mock = MagicMock(return_value="some chapter text")

    with patch.object(ew.httpx, "AsyncClient",
                      return_value=_http_cm_returning({"title": "Ch1", "content": "text"})), \
         patch.object(ew, "prepare_chapter_text", new=prepare_mock), \
         patch.object(ew, "plan_kind_batches", return_value=[["character"]]), \
         patch.object(ew, "build_known_entities_context", return_value=""), \
         patch.object(ew, "build_extraction_prompt", return_value={}), \
         patch.object(ew, "build_system_prompt", return_value="sys"), \
         patch.object(ew, "build_user_prompt", return_value="usr"), \
         patch.object(ew, "reasoning_fields", return_value={}), \
         patch.object(ew, "parse_and_validate_with_stats",
                      return_value=(entities, ParseStats(raw_count=len(entities), parse_ok=True))), \
         patch.object(ew, "_persist_batch_outcomes", new=AsyncMock()), \
         patch.object(ew, "get_cached_batch", new=AsyncMock(return_value=None)), \
         patch.object(ew, "put_batch", new=AsyncMock()), \
         patch.object(ew, "post_extracted_entities", new=post):
        result = await ew._process_extraction_chapter(
            job_id=uuid4(), book_id="b", chapter_id=uuid4(), chapter_index=0,
            extraction_profile={"character": {}}, kinds_metadata=[], known_entities=[],
            source_language="zh", model_source="user_model", model_ref=str(uuid4()),
            max_entities_per_kind=10, thinking_enabled=False, reasoning_effort=None,
            pool=_pool(db), llm_client=llm,
        )
        return result, post


# ── D-EXTRACTION-BATCH-CONCURRENCY: the worker fans batches out under a semaphore ──


@pytest.mark.asyncio
async def test_batch_concurrency_runs_all_units_via_gather():
    """concurrency>1 drives every (window×batch) unit through the semaphore-bounded
    gather: each spends tokens, records an outcome, and its entity reaches the
    writeback — same coverage as the sequential path, just concurrent."""
    db = AsyncMock()
    db.fetchval = AsyncMock(return_value=uuid4())  # owner_user_id resolve
    llm = MagicMock()
    llm.submit_and_wait = AsyncMock(side_effect=lambda **kw: _sdk_job("stop"))
    post = AsyncMock(return_value={"created": 4, "updated": 0, "skipped": 0})
    persist = AsyncMock()
    batches = [["character"], ["location"], ["item"], ["event"]]

    def _parse(text, batch, profile):
        # one entity per batch, named by kind so the cross-window merge keeps all 4 distinct
        kind = batch[0]
        return (
            [{"name": f"e-{kind}", "kind_code": kind, "evidence": "", "attributes": {}}],
            ParseStats(raw_count=1, parse_ok=True),
        )

    with patch.object(ew.httpx, "AsyncClient",
                      return_value=_http_cm_returning({"title": "Ch1", "content": "text"})), \
         patch.object(ew, "prepare_chapter_text", new=MagicMock(return_value="some chapter text")), \
         patch.object(ew, "plan_kind_batches", return_value=batches), \
         patch.object(ew, "build_known_entities_context", return_value=""), \
         patch.object(ew, "build_extraction_prompt", return_value={}), \
         patch.object(ew, "build_system_prompt", return_value="sys"), \
         patch.object(ew, "build_user_prompt", return_value="usr"), \
         patch.object(ew, "reasoning_fields", return_value={}), \
         patch.object(ew, "parse_and_validate_with_stats", side_effect=_parse), \
         patch.object(ew, "_persist_batch_outcomes", new=persist), \
         patch.object(ew, "get_cached_batch", new=AsyncMock(return_value=None)), \
         patch.object(ew, "put_batch", new=AsyncMock()), \
         patch.object(ew, "post_extracted_entities", new=post):
        result = await ew._process_extraction_chapter(
            job_id=uuid4(), book_id="b", chapter_id=uuid4(), chapter_index=0,
            extraction_profile={k[0]: {} for k in batches}, kinds_metadata=[], known_entities=[],
            source_language="zh", model_source="user_model", model_ref=str(uuid4()),
            max_entities_per_kind=10, thinking_enabled=False, reasoning_effort=None,
            pool=_pool(db), llm_client=llm, concurrency=4,
        )

    assert llm.submit_and_wait.await_count == 4          # all 4 units ran (one LLM call each)
    assert len(persist.await_args.args[-1]) == 4         # 4 outcome rows recorded (the SSOT)
    posted = post.await_args.kwargs["entities"]
    assert len({e["name"] for e in posted}) == 4         # all 4 distinct entities reached writeback
    assert result["output_tokens"] == 80                 # 4 × 20 tokens summed across concurrent units


# ── RE (D-RE-WORKER-GRADED-EFFORT): the worker honors graded reasoning_effort ──


async def _capture_llm_input(*, thinking_enabled: bool, reasoning_effort):
    """Drive ONE batch through the LLM (cache miss) and return the gateway `input`
    dict the worker built, so a test can assert the reasoning wire fields."""
    db = AsyncMock()
    db.fetchval = AsyncMock(return_value=uuid4())
    db.execute = AsyncMock()
    llm = MagicMock()
    llm.submit_and_wait = AsyncMock(return_value=_sdk_job("stop"))
    post = AsyncMock(return_value={"created": 1, "updated": 0, "skipped": 0})
    entities = [{"name": "x", "kind_code": "character"}]
    with patch.object(ew.httpx, "AsyncClient",
                      return_value=_http_cm_returning({"title": "Ch1", "content": "text"})), \
         patch.object(ew, "prepare_chapter_text", new=MagicMock(return_value="some chapter text")), \
         patch.object(ew, "plan_kind_batches", return_value=[["character"]]), \
         patch.object(ew, "build_known_entities_context", return_value=""), \
         patch.object(ew, "build_extraction_prompt", return_value={}), \
         patch.object(ew, "build_system_prompt", return_value="sys"), \
         patch.object(ew, "build_user_prompt", return_value="usr"), \
         patch.object(ew, "stamp_entity_provenance", new=MagicMock()), \
         patch.object(ew, "parse_and_validate_with_stats",
                      return_value=(entities, ParseStats(raw_count=1, parse_ok=True))), \
         patch.object(ew, "_persist_batch_outcomes", new=AsyncMock()), \
         patch.object(ew, "get_cached_batch", new=AsyncMock(return_value=None)), \
         patch.object(ew, "put_batch", new=AsyncMock()), \
         patch.object(ew, "post_extracted_entities", new=post):
        await ew._process_extraction_chapter(
            job_id=uuid4(), book_id="b", chapter_id=uuid4(), chapter_index=0,
            extraction_profile={"character": {}}, kinds_metadata=[], known_entities=[],
            source_language="zh", model_source="user_model", model_ref=str(uuid4()),
            max_entities_per_kind=10, thinking_enabled=thinking_enabled,
            reasoning_effort=reasoning_effort, pool=_pool(db), llm_client=llm,
        )
    return llm.submit_and_wait.await_args.kwargs["input"]


@pytest.mark.asyncio
async def test_graded_reasoning_effort_reaches_gateway():
    # A high request is honored end-to-end (NOT collapsed to medium-or-none).
    inp = await _capture_llm_input(thinking_enabled=False, reasoning_effort="high")
    assert inp["reasoning_effort"] == "high"
    assert inp["chat_template_kwargs"] == {"thinking": True, "enable_thinking": True}


@pytest.mark.asyncio
async def test_reasoning_effort_none_disables_thinking():
    # effort='none' explicitly disables hidden thinking (no reasoning-token burn).
    inp = await _capture_llm_input(thinking_enabled=False, reasoning_effort="none")
    assert inp["reasoning_effort"] == "none"
    assert inp["chat_template_kwargs"] == {"thinking": False, "enable_thinking": False}


# NOTE (main-merge): the legacy-bool → "medium" fallback now lives in the OUTER worker
# message handler (`reasoning_effort = msg.get(...) or ("medium" if thinking_enabled ...)`),
# NOT in `_process_extraction_chapter` (which trusts the already-resolved effort). The
# former HEAD test that drove this through `_process_extraction_chapter` was obsolete; the
# explicit-effort tests above (high / none) cover the wire shape.


@pytest.mark.asyncio
async def test_process_chapter_records_truncation_and_warns(caplog):
    # finish_reason=length → batch recorded truncated=True + a loud WARNING so
    # output-token truncation is no longer invisible (architecture §8.3 / the
    # 26-scenario data-loss bug).
    caplog.set_level(logging.WARNING, logger="app.workers.extraction_worker")
    result, _ = await _run_one_chapter_batch(
        "length", [{"name": "张若尘", "kind_code": "character", "status": "created"}],
    )
    bfr = result["batch_finish_reasons"]
    assert len(bfr) == 1
    assert bfr[0]["finish_reason"] == "length"
    assert bfr[0]["truncated"] is True
    assert bfr[0]["kinds"] == ["character"]
    assert any("TRUNCATED" in r.getMessage() for r in caplog.records)


@pytest.mark.asyncio
async def test_process_chapter_records_clean_finish_no_warning(caplog):
    # finish_reason=stop → recorded, NOT truncated, no warning. Also exercises the
    # 0-entities early-return path still surfacing batch_finish_reasons.
    caplog.set_level(logging.WARNING, logger="app.workers.extraction_worker")
    result, _ = await _run_one_chapter_batch("stop", [])  # empty parse → early return
    bfr = result["batch_finish_reasons"]
    assert len(bfr) == 1
    assert bfr[0]["finish_reason"] == "stop"
    assert bfr[0]["truncated"] is False
    assert not any("TRUNCATED" in r.getMessage() for r in caplog.records)


@pytest.mark.asyncio
async def test_process_chapter_passes_writeback_idempotency_fields():
    # M1 — the per-chapter writeback carries the two-ledger fields so glossary can
    # dedupe it: chapter_id, a content_hash, an owner-scoped writeback_key.
    _, post = await _run_one_chapter_batch(
        "stop", [{"name": "张若尘", "kind_code": "character", "status": "created"}],
    )
    post.assert_awaited_once()
    kw = post.await_args.kwargs
    assert kw.get("chapter_id"), "writeback must carry chapter_id"
    assert len(kw.get("content_hash") or "") == 64, "content_hash must be a sha256 hex digest"
    assert len(kw.get("writeback_key") or "") == 64, "writeback_key must be a sha256 hex digest"
    assert kw.get("owner_user_id"), "writeback must carry owner_user_id (tenancy)"


@pytest.mark.asyncio
async def test_process_chapter_skips_stale_writeback_on_source_drift(caplog):
    # M1 (INV-C4) — if the chapter text changes between the initial fetch and the
    # post-extraction re-check, the entities are stale: skip the writeback entirely.
    caplog.set_level(logging.WARNING, logger="app.workers.extraction_worker")
    result, post = await _run_one_chapter_batch(
        "stop", [{"name": "张若尘", "kind_code": "character", "status": "created"}],
        prepare_texts=["original chapter text", "EDITED chapter text"],
    )
    assert result.get("stale_skipped") is True
    assert result["created"] == 0
    post.assert_not_awaited()  # nothing written back
    assert any("DRIFTED" in r.getMessage() for r in caplog.records)


# ── D-LLM-FAILURE-RATE #1 — structured-output schema builder ──────────────────


def test_entity_response_format_is_loose_array_schema():
    """The json_schema must force a top-level ARRAY of objects that require
    kind (restricted to the batch's kinds) + name, while leaving attributes FREE
    (additionalProperties) so the per-kind profile fields aren't constrained."""
    rf = ew._entity_response_format(["character", "location", "item"])
    assert rf["type"] == "json_schema"
    schema = rf["json_schema"]["schema"]
    assert schema["type"] == "array"
    item = schema["items"]
    assert item["type"] == "object"
    assert item["required"] == ["kind", "name"]
    assert item["additionalProperties"] is True
    # kind is enum-restricted to exactly this batch's kinds (kills wrong-kind output)
    assert item["properties"]["kind"]["enum"] == ["character", "location", "item"]
    assert item["properties"]["name"]["type"] == "string"


def test_entity_response_format_enum_tracks_the_batch():
    """A different batch → a different kind enum (per-call, not global)."""
    rf = ew._entity_response_format(["event", "relationship"])
    assert rf["json_schema"]["schema"]["items"]["properties"]["kind"]["enum"] == [
        "event",
        "relationship",
    ]


# ── extraction-quality (2026-06-29 ontology analysis) ────────────────────────


def test_drop_non_extractable_kinds_removes_relationship():
    """`relationship` is a KG edge, not a glossary entity — it must be filtered from the
    LLM extraction profile + metadata so it can't flood the glossary with `A與B的關係`
    phrase-rows. Other (concrete) kinds are untouched."""
    profile = {"character": {"name": "fill"}, "relationship": {"name": "fill"}, "location": {"name": "fill"}}
    meta = [{"code": "character"}, {"code": "relationship"}, {"code": "location"}]
    fp, fm, dropped = ew.drop_non_extractable_kinds(profile, meta)
    assert dropped == ["relationship"]
    assert set(fp) == {"character", "location"}
    assert [m["code"] for m in fm] == ["character", "location"]


def test_drop_non_extractable_kinds_noop_when_absent():
    """A book without `relationship` is unaffected (returns the inputs, no churn)."""
    profile = {"character": {"name": "fill"}}
    meta = [{"code": "character"}]
    fp, fm, dropped = ew.drop_non_extractable_kinds(profile, meta)
    assert dropped == []
    assert fp == profile and fm == meta


def test_extraction_system_template_has_precision_filter():
    """The glossary extraction prompt must carry the scene-relevance / discreteness filter
    (the precision control the KG prompt had and this one lacked) and must NOT say 'all'."""
    from app.workers.extraction_prompt import SYSTEM_TEMPLATE
    t = SYSTEM_TEMPLATE
    assert "SALIENT, DISCRETE, NAMED" in t
    assert "identify all named entities" not in t.lower()
    assert "RELATIONSHIPS between" in t  # explicit: a relationship is not an entity
    assert "OMIT" in t and "backstory" in t  # omission bias for background mentions
