"""K16.6b — Unit tests for the extraction job runner.

Tests the core process_job logic with mocked DB pool and HTTP clients.

Phase 4b-gamma: extract_item HTTP call was replaced by an in-process
LLM run + thin /persist-pass2 POST. Tests now patch
`app.runner._extract_and_persist` (the runner-helper that wraps both
steps) instead of mocking `KnowledgeClient.extract_item` directly.
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.clients import (
    BookClient, ChapterHierarchy, ChapterInfo, ChatClient, ExtractionResult,
    GlossaryClient, GlossaryEntity, GlossaryPage, GlossarySyncResult,
    HierarchyPart, HierarchyScene, KnowledgeClient, ProviderRegistryClient,
)
from app.runner import (
    JobRow, process_job, poll_and_run, _get_running_jobs,
    _enumerate_chapters, _ensure_chat_pending_jobs, _is_likely_reasoning_model,
)


# ── Helpers ──────────────────────────────────────────────────────────


def _job(**overrides) -> JobRow:
    defaults = dict(
        job_id=uuid4(),
        user_id=uuid4(),
        project_id=uuid4(),
        scope="chapters",
        scope_range=None,
        status="running",
        llm_model="test-model",
        embedding_model="bge-m3",
        max_spend_usd=Decimal("10.00"),
        items_total=5,
        items_processed=0,
        current_cursor=None,
        cost_spent_usd=Decimal("0"),
    )
    defaults.update(overrides)
    return JobRow(**defaults)


class _FakeCandidates:
    """Q4b-feed — minimal Pass2Candidates stand-in. `_extract_and_persist`
    now returns (ExtractionResult, candidates); process_job unpacks the tuple.
    Empty lists → project_items yields empty categories (and save_raw defaults
    False in these tests, so the sample write is skipped anyway)."""
    entities: list = []
    relations: list = []
    events: list = []
    facts: list = []


def _ok_result(source_id: str = "ch-1") -> tuple[ExtractionResult, _FakeCandidates]:
    """Q4b-feed: returns the (result, candidates) tuple the chapter loop unpacks."""
    return ExtractionResult(
        source_id=source_id,
        entities_merged=2,
        relations_created=1,
        events_merged=1,
        facts_merged=3,
    ), _FakeCandidates()


def _error_result(retryable: bool = True) -> tuple[ExtractionResult, None]:
    return ExtractionResult(
        source_id="ch-1",
        entities_merged=0,
        relations_created=0,
        events_merged=0,
        facts_merged=0,
        retryable=retryable,
        error="something broke",
    ), None


_TEST_BOOK_ID = uuid4()


def _mock_pool(book_id=_TEST_BOOK_ID):
    """Create a mock asyncpg pool.

    fetchval is called for both _get_project_book_id (returns UUID)
    and _refresh_job_status (returns str). We use side_effect to
    return book_id first, then 'running' for all subsequent calls.
    """
    pool = AsyncMock()
    pool.fetchval = AsyncMock(side_effect=[book_id, *["running"] * 100])
    # Default: try_spend succeeds
    pool.fetchrow = AsyncMock(return_value={"cost_spent_usd": Decimal("0.004"), "status": "running"})
    # Default: execute succeeds
    pool.execute = AsyncMock()
    # Default: no pending chat turns
    pool.fetch = AsyncMock(return_value=[])
    # B2-A: the chapter-success/skip path advances the cursor + emits the
    # extraction_run in ONE transaction via `async with pool.acquire() as conn,
    # conn.transaction():`. Wire acquire()/transaction() as async context
    # managers; the acquired conn SHARES pool.execute so existing
    # call-inspection assertions still observe the cursor-advance (and the new
    # INSERT INTO outbox_events).
    conn = AsyncMock()
    conn.execute = pool.execute
    _txn = MagicMock()
    _txn.__aenter__ = AsyncMock(return_value=None)
    _txn.__aexit__ = AsyncMock(return_value=False)
    conn.transaction = MagicMock(return_value=_txn)
    # P1 job-emit: _complete_job/_fail_job now do `UPDATE … RETURNING` via
    # conn.fetchrow (so the rowcount gates the emit) + emit_job_event on the same
    # conn. Default the acquired conn's fetchrow to a truthy row (transition won) so
    # the happy path emits; tests inspect `pool.acquired_conn.fetchrow`.
    # P4 carries the final cost on the terminal event — _complete_job/_fail_job read
    # row["cost_spent_usd"] from the RETURNING row, so the mock must supply it.
    conn.fetchrow = AsyncMock(return_value={
        "job_id": "00000000-0000-0000-0000-000000000001",
        "cost_spent_usd": Decimal("0.004"),
    })
    _acq = MagicMock()
    _acq.__aenter__ = AsyncMock(return_value=conn)
    _acq.__aexit__ = AsyncMock(return_value=False)
    pool.acquire = MagicMock(return_value=_acq)
    pool.acquired_conn = conn
    return pool


def _mock_knowledge_client():
    """Mock KnowledgeClient. Phase 4b-gamma: extract_item is gone; the
    runner's _extract_and_persist helper internally calls
    knowledge_client.persist_pass2. Tests patch _extract_and_persist at
    the runner level so this client mock is passive (only used by the
    glossary_sync path which still goes through glossary_sync_entity).
    """
    client = AsyncMock(spec=KnowledgeClient)
    # persist_pass2 returns a single ExtractionResult (NOT the tuple _ok_result
    # now returns) — the real _extract_and_persist wraps it with candidates.
    client.persist_pass2 = AsyncMock(return_value=ExtractionResult(
        source_id="ch-1", entities_merged=2, relations_created=1,
        events_merged=1, facts_merged=3,
    ))
    return client


def _mock_llm_client():
    """Phase 4b-gamma: LLMClient is required by process_job/poll_and_run
    but is never invoked in tests because _extract_and_persist is
    patched. A MagicMock placeholder is enough."""
    return MagicMock()


# ── D-KG-WORKER-GRADED-EFFORT — sync path threads job effort to the SDK ─────


@pytest.mark.asyncio
@patch("app.runner.extract_pass2", new_callable=AsyncMock)
async def test_extract_and_persist_threads_reasoning_effort(mock_pass2):
    """_extract_and_persist(reasoning_effort='high') forwards it to extract_pass2."""
    from app.runner import _extract_and_persist

    mock_pass2.return_value = _FakeCandidates()
    await _extract_and_persist(
        knowledge_client=_mock_knowledge_client(),
        llm_client=_mock_llm_client(),
        user_id=uuid4(), project_id=uuid4(),
        source_type="chapter", source_id="ch-1", job_id=uuid4(),
        model_ref="m", text="Kai walks.",
        reasoning_effort="high",
    )
    assert mock_pass2.call_args.kwargs["reasoning_effort"] == "high"


@pytest.mark.asyncio
@patch("app.runner.extract_pass2", new_callable=AsyncMock)
async def test_extract_and_persist_default_effort_is_none(mock_pass2):
    """Omitting reasoning_effort (chat_turn/glossary callers) defaults to 'none'."""
    from app.runner import _extract_and_persist

    mock_pass2.return_value = _FakeCandidates()
    await _extract_and_persist(
        knowledge_client=_mock_knowledge_client(),
        llm_client=_mock_llm_client(),
        user_id=uuid4(), project_id=uuid4(),
        source_type="chapter", source_id="ch-1", job_id=uuid4(),
        model_ref="m", text="Kai walks.",
    )
    assert mock_pass2.call_args.kwargs["reasoning_effort"] == "none"


def test_jobrow_default_reasoning_effort_is_none():
    """A JobRow built without the field defaults to 'none' (synthetic/test rows)."""
    assert _job().reasoning_effort == "none"
    assert _job(reasoning_effort="high").reasoning_effort == "high"


# ── bug #34 — immediate-cancel hook threaded into the SDK ──────────────


@pytest.mark.asyncio
@patch("app.runner.extract_pass2", new_callable=AsyncMock)
async def test_extract_and_persist_forwards_cancel_check(mock_pass2):
    """bug #34 — _extract_and_persist(cancel_check=...) forwards it to extract_pass2."""
    from app.runner import _extract_and_persist

    mock_pass2.return_value = _FakeCandidates()

    async def _cancel() -> bool:
        return False

    await _extract_and_persist(
        knowledge_client=_mock_knowledge_client(),
        llm_client=_mock_llm_client(),
        user_id=uuid4(), project_id=uuid4(),
        source_type="chapter", source_id="ch-1", job_id=uuid4(),
        model_ref="m", text="Kai walks.",
        cancel_check=_cancel,
    )
    assert mock_pass2.call_args.kwargs["cancel_check"] is _cancel


@pytest.mark.asyncio
@patch("app.runner.extract_pass2", new_callable=AsyncMock)
async def test_extract_and_persist_default_cancel_check_is_none(mock_pass2):
    """bug #34 — omitting cancel_check forwards None (back-compat)."""
    from app.runner import _extract_and_persist

    mock_pass2.return_value = _FakeCandidates()
    await _extract_and_persist(
        knowledge_client=_mock_knowledge_client(),
        llm_client=_mock_llm_client(),
        user_id=uuid4(), project_id=uuid4(),
        source_type="chapter", source_id="ch-1", job_id=uuid4(),
        model_ref="m", text="Kai walks.",
    )
    assert mock_pass2.call_args.kwargs["cancel_check"] is None


@pytest.mark.asyncio
async def test_start_decoupled_chunk_stashes_effort_into_resume_state():
    """D-KG-WORKER-GRADED-EFFORT — the decoupled dispatch MUST stash the job's
    effort into resume_state (the spec's flagged 'silently drops effort on the
    decoupled flow' failure mode); the consumer rebuilds the trio submits from
    it on resume. Locks the dispatch stash directly (the assemble-side is tested
    separately given an rs that already carries the key)."""
    import json as _json
    from unittest.mock import MagicMock as _MM
    from app.runner import _start_decoupled_chunk

    job = _job(scope="chapters", reasoning_effort="high")
    pool = AsyncMock()
    captured = {}

    async def _exec(sql, *args):
        if "resume_state" in sql:
            captured["rs"] = _json.loads(args[1])  # $2 = json.dumps(rs)
    pool.execute = AsyncMock(side_effect=_exec)

    llm = _MM()
    llm.submit_job = AsyncMock(return_value=_MM(job_id="pj-1"))

    snap = _MM()
    snap.model_ref = "m"; snap.model_source = "user_model"
    snap.entity_recovery = None; snap.precision_filter = None
    snap.prompts = {}; snap.writer_autocreate = None; snap.prompt_versions = {}

    ch = _MM(); ch.chapter_id = "ch-1"

    await _start_decoupled_chunk(
        pool, llm, job=job, ch=ch, text="Kai walks.", book_id=_TEST_BOOK_ID,
        run_snapshot=snap, run_cfg_hash="h", run_base_version="v",
        p3_hierarchy_paths=None, p3_chapter_index=0, p3_book_parts=None, p3_is_last=False,
    )

    assert captured["rs"]["reasoning_effort"] == "high"


def _mock_book_client(chapters=None, text="Chapter text here."):
    client = AsyncMock(spec=BookClient)
    if chapters is None:
        # CM3c: a published chapter carries its pinned published_revision_id
        # (→ ChapterInfo.revision_id), so the manual rebuild reads the pinned
        # revision text via get_chapter_revision_text.
        chapters = [ChapterInfo(
            chapter_id="ch-1", title="Ch 1", sort_order=1, revision_id="rev-1",
        )]
    client.list_chapters = AsyncMock(return_value=chapters)
    client.get_chapter_text = AsyncMock(return_value=text)
    # CM3c: published chapters fetch the pinned revision; mirror `text` so
    # text-unavailable (text=None) still exercises the skip path.
    client.get_chapter_revision_text = AsyncMock(return_value=text)
    return client


def _mock_chat_client(text=""):
    """FD-2 — mock ChatClient. Default get_turn_text returns "" (the chat path
    degrades to a graceful no-op); pass `text` to exercise real chat extraction."""
    client = AsyncMock(spec=ChatClient)
    client.get_turn_text = AsyncMock(return_value=text or None)
    return client


def _mock_provider_client(model_name=None, context_length=None):
    """FD-27 — mock ProviderRegistryClient. Default get_model_name returns None
    (advisory off); pass a name to exercise the reasoning-model advisory. Default
    get_context_length returns None (unresolved — the chapter branch's ContextBudget
    stays unset); pass an int to exercise model-context-aware chunk sizing."""
    client = AsyncMock(spec=ProviderRegistryClient)
    client.get_model_name = AsyncMock(return_value=model_name)
    client.get_context_length = AsyncMock(return_value=context_length)
    return client


def _mock_glossary_client(pages=None):
    """C12c-a — mock GlossaryClient. Default returns a single empty
    page. `pages` is a list of (items, next_cursor) tuples returned
    in order via side_effect.
    """
    client = AsyncMock(spec=GlossaryClient)
    if pages is None:
        client.list_book_entities = AsyncMock(
            return_value=GlossaryPage(items=(), next_cursor=None),
        )
    else:
        client.list_book_entities = AsyncMock(
            side_effect=[
                GlossaryPage(items=tuple(items), next_cursor=nc)
                for items, nc in pages
            ],
        )
    return client


def _glossary_entity(entity_id: str, name: str = "Alice") -> GlossaryEntity:
    return GlossaryEntity(
        entity_id=entity_id,
        name=name,
        kind_code="character",
        aliases=(),
        short_description=None,
    )


def _glossary_sync_ok(entity_id: str) -> GlossarySyncResult:
    return GlossarySyncResult(
        glossary_entity_id=entity_id,
        action="created",
        canonical_name="alice",
    )


# ── S4a: process_job binds the owning campaign as a contextvar ───────


@pytest.mark.asyncio
@patch("app.runner.set_campaign_id")
@patch("app.runner._extract_and_persist", new_callable=AsyncMock)
async def test_process_job_binds_campaign_id_contextvar(mock_extract_persist, mock_set):
    """The campaign on the job row is bound (as str) before any LLM call, so the
    llm_client merge stamps it onto every provider job_meta. None → cleared."""
    mock_extract_persist.return_value = _ok_result()
    camp = uuid4()
    job = _job(scope="chapters", campaign_id=camp)
    await process_job(_mock_pool(), _mock_knowledge_client(), _mock_llm_client(),
                      _mock_book_client(), _mock_glossary_client(),
                      _mock_chat_client(), _mock_provider_client(), job)
    mock_set.assert_called_once_with(str(camp))


@pytest.mark.asyncio
@patch("app.runner.set_campaign_id")
@patch("app.runner._extract_and_persist", new_callable=AsyncMock)
async def test_process_job_clears_campaign_id_when_none(mock_extract_persist, mock_set):
    """A non-campaign job clears the contextvar (None) so it can't inherit a
    previous job's campaign on a reused task."""
    mock_extract_persist.return_value = _ok_result()
    await process_job(_mock_pool(), _mock_knowledge_client(), _mock_llm_client(),
                      _mock_book_client(), _mock_glossary_client(),
                      _mock_chat_client(), _mock_provider_client(), _job(scope="chapters"))
    mock_set.assert_called_once_with(None)


# ── E0-3 Phase 2a: fail-safe wiring into process_job (review-impl MED-2) ──


@pytest.mark.asyncio
@patch("app.runner._fail_job", new_callable=AsyncMock)
@patch("app.runner._extract_and_persist", new_callable=AsyncMock)
async def test_process_job_fails_job_on_partial_billing_identity(
    mock_extract_persist, mock_fail_job
):
    """A job with billing_user_id but a missing billing ref must be FAILED (not
    crash the poll loop, not silently run on the owner's key). Proves the
    assert_billing_complete fail-safe is wired INSIDE process_job's try so the
    existing except→_fail_job handler catches it — and that no extraction (no
    provider call) happens first."""
    job = _job(
        scope="chapters",
        billing_user_id=uuid4(),
        billing_llm_model=None,  # partial → fail-safe must trip
        billing_embedding_model="collab-emb",
    )
    await process_job(_mock_pool(), _mock_knowledge_client(), _mock_llm_client(),
                      _mock_book_client(), _mock_glossary_client(),
                      _mock_chat_client(), _mock_provider_client(), job)
    # Job failed via the fail-safe; no provider call was made.
    mock_fail_job.assert_awaited_once()
    assert job.job_id in mock_fail_job.call_args.args
    mock_extract_persist.assert_not_called()


@pytest.mark.asyncio
@patch("app.runner._extract_and_persist", new_callable=AsyncMock)
async def test_process_job_runs_normally_with_complete_billing(mock_extract_persist):
    """The mirror: a complete billing identity passes the fail-safe and proceeds
    to extraction (the collaborator path actually runs)."""
    mock_extract_persist.return_value = _ok_result()
    job = _job(
        scope="chapters",
        billing_user_id=uuid4(),
        billing_llm_model="collab-llm",
        billing_embedding_model="collab-emb",
    )
    await process_job(_mock_pool(), _mock_knowledge_client(), _mock_llm_client(),
                      _mock_book_client(), _mock_glossary_client(),
                      _mock_chat_client(), _mock_provider_client(), job)
    mock_extract_persist.assert_called_once()


# ── process_job: chapters scope ──────────────────────────────────────


@pytest.mark.asyncio
@patch("app.runner._start_decoupled_chunk", new_callable=AsyncMock)
@patch("app.runner.fair_sched.try_acquire_chunk", new_callable=AsyncMock)
@patch("app.runner._extract_and_persist", new_callable=AsyncMock)
async def test_p5_defers_chunk_and_skips_spend_when_owner_at_cap(
    mock_extract_persist, mock_acquire, mock_decoupled, monkeypatch
):
    """P5 — when the owner is at the per-owner in-flight cap, the decoupled chunk is
    deferred to a later poll: NO submit and NO cost reservation (try_spend) — so a
    deferred chunk can't inflate cost_spent_usd. Proves the gate sits BEFORE try_spend
    in the real path (memory: assert the wrapper fires at the call site)."""
    monkeypatch.setenv("EXTRACTION_DECOUPLE_ENABLED", "true")
    mock_acquire.return_value = (False, None)  # owner at cap → defer
    job = _job(scope="chapters")
    pool = _mock_pool()
    # in-flight guard runs first (resume_state IS NOT NULL → False), then book_id, then
    # _refresh_job_status → 'running'.
    pool.fetchval = AsyncMock(side_effect=[False, _TEST_BOOK_ID, "running", *["running"] * 50])

    await process_job(
        pool, _mock_knowledge_client(), _mock_llm_client(), _mock_book_client(),
        _mock_glossary_client(), _mock_chat_client(), _mock_provider_client(), job,
    )

    mock_acquire.assert_awaited_once()        # the gate was consulted
    mock_decoupled.assert_not_called()        # chunk NOT submitted
    pool.fetchrow.assert_not_called()         # _try_spend (fetchrow) NOT reached → no spend inflation


@pytest.mark.asyncio
@patch("app.runner._extract_and_persist", new_callable=AsyncMock)
async def test_process_job_chapters_success(mock_extract_persist):
    """Happy path: one chapter extracted, job completed."""
    mock_extract_persist.return_value = _ok_result()
    job = _job(scope="chapters")
    pool = _mock_pool()
    kc = _mock_knowledge_client()
    llm = _mock_llm_client()
    bc = _mock_book_client()
    gc = _mock_glossary_client()

    await process_job(pool, kc, llm, bc, gc, _mock_chat_client(), _mock_provider_client(), job)

    # Should have called _extract_and_persist once
    mock_extract_persist.assert_called_once()
    # Should have advanced cursor + recorded spending + completed job
    assert pool.execute.call_count >= 3


@pytest.mark.asyncio
@patch("app.runner._extract_and_persist", new_callable=AsyncMock)
async def test_chapter_index_threaded_when_no_part(mock_extract_persist):
    """FD-4 (066 regression): a part-less chapter (hierarchy.part is None) must
    STILL thread chapter_index (= sort_order) to persist — the capture reads
    hierarchy.chapter_index INDEPENDENT of the part gate. Before the fix the
    chapter_index lived only inside the `part is not None` block, so flat books
    got event_order=None → every status_effect silently dropped. hierarchy_paths
    stays None (the part-MERGE genuinely needs a part)."""
    from types import SimpleNamespace

    mock_extract_persist.return_value = _ok_result()
    job = _job(scope="chapters")
    pool = _mock_pool()
    kc = _mock_knowledge_client()
    llm = _mock_llm_client()
    bc = _mock_book_client()
    # Part-less hierarchy: no part, no chapter_path — but a real sort_order.
    bc.get_chapter_hierarchy = AsyncMock(return_value=SimpleNamespace(
        part=None, chapter_path=None, chapter_index=2, book_id="bk-1",
    ))
    gc = _mock_glossary_client()

    await process_job(pool, kc, llm, bc, gc, _mock_chat_client(), _mock_provider_client(), job)

    mock_extract_persist.assert_called_once()
    kwargs = mock_extract_persist.call_args.kwargs
    assert kwargs["chapter_index"] == 2          # threaded despite no part
    assert kwargs["hierarchy_paths"] is None      # part-MERGE correctly skipped


def _execs_with(pool, needle):
    return [
        c for c in pool.execute.call_args_list
        if isinstance(c.args[0], str) and needle in c.args[0]
    ]


@pytest.mark.asyncio
@patch("app.runner._extract_and_persist", new_callable=AsyncMock)
async def test_q4b_feed_no_sample_when_not_opted_in(mock_extract_persist):
    """Q4b-feed redact-by-default: a project WITHOUT save_raw_extraction writes
    NO extraction_run_samples row (the online judge never sees its content)."""
    mock_extract_persist.return_value = _ok_result()
    job = _job(scope="chapters", save_raw_extraction=False)
    pool = _mock_pool()
    await process_job(pool, _mock_knowledge_client(), _mock_llm_client(),
                      _mock_book_client(), _mock_glossary_client(), _mock_chat_client(), _mock_provider_client(), job)
    assert _execs_with(pool, "INSERT INTO extraction_run_samples") == []


@pytest.mark.asyncio
@patch("app.runner._extract_and_persist", new_callable=AsyncMock)
async def test_q4b_feed_sample_written_with_run_id_parity(mock_extract_persist):
    """Q4b-feed #1 risk regression-lock: an opted-in project writes exactly one
    sample, keyed by the SAME run_id that lands in the extraction_run event —
    parity is load-bearing (the online judge fetches the sample by that id)."""
    mock_extract_persist.return_value = _ok_result()
    job = _job(scope="chapters", save_raw_extraction=True)
    pool = _mock_pool()
    await process_job(pool, _mock_knowledge_client(), _mock_llm_client(),
                      _mock_book_client(), _mock_glossary_client(), _mock_chat_client(), _mock_provider_client(), job)

    samples = _execs_with(pool, "INSERT INTO extraction_run_samples")
    assert len(samples) == 1
    sample_run_id = samples[0].args[1]  # $1 run_id (UUID)

    # the run_id in the emitted event payload must equal the sample's run_id
    import json as _json
    outbox = _execs_with(pool, "INSERT INTO outbox_events")
    # find the run-completed event (payload param carries run_id)
    event_run_ids = [
        _json.loads(c.args[3])["run_id"]
        for c in outbox
        if len(c.args) > 3 and isinstance(c.args[3], str) and "run_id" in c.args[3]
    ]
    assert event_run_ids, "no run-completed event emitted"
    assert str(sample_run_id) in event_run_ids, (
        f"run_id parity broken: sample={sample_run_id} not in event {event_run_ids}"
    )


@pytest.mark.asyncio
@patch("app.runner._extract_and_persist", new_callable=AsyncMock)
async def test_process_job_chapters_records_spending_on_success(mock_extract_persist):
    """D-K16.11-01: after each successful chapter, the worker bumps
    knowledge_projects.current_month_spent_usd + actual_cost_usd so
    the CostSummary card sees real production figures."""
    mock_extract_persist.return_value = _ok_result()
    chapters = [
        ChapterInfo(chapter_id=f"ch-{i}", title=f"Ch {i}", sort_order=i, revision_id=f"rev-{i}")
        for i in range(3)
    ]
    job = _job(scope="chapters")
    pool = _mock_pool()
    kc = _mock_knowledge_client()
    llm = _mock_llm_client()
    bc = _mock_book_client(chapters=chapters)
    gc = _mock_glossary_client()

    await process_job(pool, kc, llm, bc, gc, _mock_chat_client(), _mock_provider_client(), job)

    # Collect the SQL text of every execute call; count how many
    # target knowledge_projects with the monthly-spend + all-time
    # counter bumps. One per successful chapter.
    spending_calls = [
        c for c in pool.execute.call_args_list
        if isinstance(c.args[0], str)
        and "UPDATE knowledge_projects" in c.args[0]
        and "current_month_spent_usd" in c.args[0]
        and "actual_cost_usd" in c.args[0]
    ]
    assert len(spending_calls) == 3


@pytest.mark.asyncio
@patch("app.runner._extract_and_persist", new_callable=AsyncMock)
async def test_process_job_appends_log_on_chapter_success(mock_extract_persist):
    """K19b.8: each successful chapter writes a job_logs row with
    level=info and an event=chapter_processed context tag."""
    mock_extract_persist.return_value = _ok_result()
    chapters = [
        ChapterInfo(chapter_id=f"ch-{i}", title=f"Ch {i}", sort_order=i, revision_id=f"rev-{i}")
        for i in range(2)
    ]
    job = _job(scope="chapters")
    pool = _mock_pool()
    kc = _mock_knowledge_client()
    llm = _mock_llm_client()
    bc = _mock_book_client(chapters=chapters)
    gc = _mock_glossary_client()

    await process_job(pool, kc, llm, bc, gc, _mock_chat_client(), _mock_provider_client(), job)

    log_calls = [
        c for c in pool.execute.call_args_list
        if isinstance(c.args[0], str)
        and "INSERT INTO job_logs" in c.args[0]
    ]
    # 2 chapters → 2 info logs for success; no other kinds.
    assert len(log_calls) == 2
    for call in log_calls:
        # args: (sql, job_id, user_id, level, message, context_json)
        assert call.args[3] == "info"
        assert "processed" in call.args[4]


@pytest.mark.asyncio
@patch("app.runner._extract_and_persist", new_callable=AsyncMock)
async def test_process_job_appends_error_log_on_fatal_failure(mock_extract_persist):
    """K19b.8: non-retryable extraction error writes an error-level log
    with event=failed before the job transitions to failed."""
    mock_extract_persist.return_value = _error_result(retryable=False)
    job = _job(scope="chapters")
    pool = _mock_pool()
    kc = _mock_knowledge_client()
    llm = _mock_llm_client()
    bc = _mock_book_client()
    gc = _mock_glossary_client()

    await process_job(pool, kc, llm, bc, gc, _mock_chat_client(), _mock_provider_client(), job)

    error_logs = [
        c for c in pool.execute.call_args_list
        if isinstance(c.args[0], str)
        and "INSERT INTO job_logs" in c.args[0]
        and c.args[3] == "error"
    ]
    assert len(error_logs) == 1


@pytest.mark.asyncio
@patch("app.runner._extract_and_persist", new_callable=AsyncMock)
async def test_process_job_chat_records_spending_on_success(mock_extract_persist):
    """D-K16.11-01: chat-scope success path also records spending.
    Mirrors the chapters test — same two-counter update per item."""
    mock_extract_persist.return_value = _ok_result()
    job = _job(scope="chat")
    pool = _mock_pool()
    # Seed 2 pending chat turns so the chat branch iterates twice.
    pool.fetch = AsyncMock(return_value=[
        {"pending_id": uuid4(), "aggregate_id": uuid4()},
        {"pending_id": uuid4(), "aggregate_id": uuid4()},
    ])
    kc = _mock_knowledge_client()
    llm = _mock_llm_client()
    bc = _mock_book_client()
    gc = _mock_glossary_client()

    # The turns must carry TEXT. D-EXTRACTION-SILENT-NOOP later made an empty turn a
    # deliberate skip that is not charged, so `_mock_chat_client()`'s default of no text
    # stopped exercising the success path this test names — it was asserting the spend of
    # a branch it no longer entered. Non-empty text puts it back on the paid path.
    chat = _mock_chat_client(text="Kai told Master Lin he would leave the sect.")

    await process_job(pool, kc, llm, bc, gc, chat, _mock_provider_client(), job)

    spending_calls = [
        c for c in pool.execute.call_args_list
        if isinstance(c.args[0], str)
        and "UPDATE knowledge_projects" in c.args[0]
        and "current_month_spent_usd" in c.args[0]
    ]
    assert len(spending_calls) == 2


@pytest.mark.asyncio
@patch("app.runner._extract_and_persist", new_callable=AsyncMock)
async def test_process_job_chat_passes_fetched_turn_text(mock_extract_persist):
    """FD-2 core regression: the chat branch fetches the REAL turn text from
    chat-service (by the assistant message id = aggregate_id) and feeds it to
    extraction — was a hardcoded text="" no-op. Lock the wired text."""
    mock_extract_persist.return_value = _ok_result()
    job = _job(scope="chat")
    pool = _mock_pool()
    msg_id = uuid4()
    pool.fetch = AsyncMock(return_value=[{"pending_id": uuid4(), "aggregate_id": msg_id}])
    cc = _mock_chat_client(text="User: who is Kael?\n\nAssistant: a disgraced knight.")

    await process_job(pool, _mock_knowledge_client(), _mock_llm_client(),
                      _mock_book_client(), _mock_glossary_client(), cc, _mock_provider_client(), job)

    cc.get_turn_text.assert_awaited_once_with(msg_id)
    assert mock_extract_persist.await_args.kwargs["text"] == \
        "User: who is Kael?\n\nAssistant: a disgraced knight."
    assert mock_extract_persist.await_args.kwargs["source_type"] == "chat_message"


@pytest.mark.asyncio
@patch("app.runner._extract_and_persist", new_callable=AsyncMock)
async def test_process_job_chat_missing_text_degrades_to_empty(mock_extract_persist):
    """FD-2 — a turn whose text can't be fetched (None) degrades to text="" (the
    graceful no-op the path always had), NOT a crash."""
    mock_extract_persist.return_value = _ok_result()
    job = _job(scope="chat")
    pool = _mock_pool()
    pool.fetch = AsyncMock(return_value=[{"pending_id": uuid4(), "aggregate_id": uuid4()}])
    cc = _mock_chat_client(text="")  # get_turn_text → None

    await process_job(pool, _mock_knowledge_client(), _mock_llm_client(),
                      _mock_book_client(), _mock_glossary_client(), cc, _mock_provider_client(), job)

    assert mock_extract_persist.await_args.kwargs["text"] == ""


@pytest.mark.asyncio
@patch("app.runner._extract_and_persist", new_callable=AsyncMock)
async def test_process_job_multiple_chapters(mock_extract_persist):
    """Multiple chapters processed in order."""
    mock_extract_persist.return_value = _ok_result()
    chapters = [
        ChapterInfo(chapter_id=f"ch-{i}", title=f"Ch {i}", sort_order=i, revision_id=f"rev-{i}")
        for i in range(3)
    ]
    job = _job(scope="chapters")
    pool = _mock_pool()
    kc = _mock_knowledge_client()
    llm = _mock_llm_client()
    bc = _mock_book_client(chapters=chapters)
    gc = _mock_glossary_client()

    await process_job(pool, kc, llm, bc, gc, _mock_chat_client(), _mock_provider_client(), job)

    assert mock_extract_persist.call_count == 3


@pytest.mark.asyncio
@patch("app.runner._extract_and_persist", new_callable=AsyncMock)
async def test_process_job_pause_detected(mock_extract_persist):
    """Job paused mid-run — runner stops processing."""
    mock_extract_persist.return_value = _ok_result()
    chapters = [
        ChapterInfo(chapter_id=f"ch-{i}", title=f"Ch {i}", sort_order=i, revision_id=f"rev-{i}")
        for i in range(5)
    ]
    job = _job(scope="chapters")
    pool = _mock_pool()
    # fetchval: book_id, then running (1st chapter), then paused (2nd)
    pool.fetchval = AsyncMock(side_effect=[_TEST_BOOK_ID, "running", "paused"])
    kc = _mock_knowledge_client()
    llm = _mock_llm_client()
    bc = _mock_book_client(chapters=chapters)
    gc = _mock_glossary_client()

    await process_job(pool, kc, llm, bc, gc, _mock_chat_client(), _mock_provider_client(), job)

    # Only 1 chapter processed before pause detected
    assert mock_extract_persist.call_count == 1


@pytest.mark.asyncio
@patch("app.runner._extract_and_persist", new_callable=AsyncMock)
async def test_process_job_cancel_detected(mock_extract_persist):
    """Job cancelled — runner stops immediately."""
    mock_extract_persist.return_value = _ok_result()
    job = _job(scope="chapters")
    pool = _mock_pool()
    # fetchval: book_id, then cancelled
    pool.fetchval = AsyncMock(side_effect=[_TEST_BOOK_ID, "cancelled"])
    kc = _mock_knowledge_client()
    llm = _mock_llm_client()
    bc = _mock_book_client()
    gc = _mock_glossary_client()

    await process_job(pool, kc, llm, bc, gc, _mock_chat_client(), _mock_provider_client(), job)

    mock_extract_persist.assert_not_called()


@pytest.mark.asyncio
@patch("app.runner._extract_and_persist", new_callable=AsyncMock)
async def test_process_job_budget_auto_pause(mock_extract_persist):
    """try_spend returns auto_paused — runner stops."""
    mock_extract_persist.return_value = _ok_result()
    job = _job(scope="chapters")
    pool = _mock_pool()
    pool.fetchrow = AsyncMock(
        return_value={"cost_spent_usd": Decimal("10"), "status": "paused"},
    )
    kc = _mock_knowledge_client()
    llm = _mock_llm_client()
    bc = _mock_book_client()
    gc = _mock_glossary_client()

    await process_job(pool, kc, llm, bc, gc, _mock_chat_client(), _mock_provider_client(), job)

    mock_extract_persist.assert_not_called()


@pytest.mark.asyncio
@patch("app.runner._extract_and_persist", new_callable=AsyncMock)
async def test_process_job_permanent_error_fails_job(mock_extract_persist):
    """Permanent extraction error → job transitions to failed."""
    mock_extract_persist.return_value = _error_result(retryable=False)
    job = _job(scope="chapters")
    pool = _mock_pool()
    kc = _mock_knowledge_client()
    llm = _mock_llm_client()
    bc = _mock_book_client()
    gc = _mock_glossary_client()

    await process_job(pool, kc, llm, bc, gc, _mock_chat_client(), _mock_provider_client(), job)

    # Should have called execute for fail_job + update_project
    fail_calls = [
        c for c in pool.execute.call_args_list
        if "failed" in str(c)
    ]
    assert len(fail_calls) >= 1


@pytest.mark.asyncio
@patch("app.runner._extract_and_persist", new_callable=AsyncMock)
async def test_process_job_retryable_error_stops_run_for_retry(mock_extract_persist):
    """Retryable error — runner stops this run (retry on next poll).
    Cursor is updated with retry count but not advanced past the item."""
    mock_extract_persist.return_value = _error_result(retryable=True)
    job = _job(scope="chapters")
    pool = _mock_pool()
    kc = _mock_knowledge_client()
    llm = _mock_llm_client()
    bc = _mock_book_client()
    gc = _mock_glossary_client()

    await process_job(pool, kc, llm, bc, gc, _mock_chat_client(), _mock_provider_client(), job)

    # Only one extraction attempt this run
    mock_extract_persist.assert_called_once()
    # Cursor should be updated with retry count (items_delta=0)
    cursor_calls = [
        c for c in pool.execute.call_args_list
        if "items_processed" in str(c)
    ]
    assert len(cursor_calls) >= 1


@pytest.mark.asyncio
@patch("app.runner._extract_and_persist", new_callable=AsyncMock)
async def test_process_job_no_book_id(mock_extract_persist):
    """Project with no book_id — chapters scope returns empty."""
    mock_extract_persist.return_value = _ok_result()
    job = _job(scope="chapters")
    pool = _mock_pool()
    kc = _mock_knowledge_client()
    llm = _mock_llm_client()
    bc = _mock_book_client()
    gc = _mock_glossary_client()
    bc.list_chapters = AsyncMock(return_value=None)

    await process_job(pool, kc, llm, bc, gc, _mock_chat_client(), _mock_provider_client(), job)

    mock_extract_persist.assert_not_called()


# ── poll_and_run ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_poll_no_jobs_returns_zero():
    pool = _mock_pool()
    pool.fetch = AsyncMock(return_value=[])
    kc = _mock_knowledge_client()
    llm = _mock_llm_client()
    bc = _mock_book_client()
    gc = _mock_glossary_client()

    count = await poll_and_run(pool, kc, llm, bc, gc, _mock_chat_client(), _mock_provider_client())
    assert count == 0


@pytest.mark.asyncio
@patch("app.runner._extract_and_persist", new_callable=AsyncMock)
async def test_process_job_chapter_text_unavailable_skips(mock_extract_persist):
    """Chapter with no text — skipped, cursor advanced."""
    mock_extract_persist.return_value = _ok_result()
    job = _job(scope="chapters")
    pool = _mock_pool()
    kc = _mock_knowledge_client()
    llm = _mock_llm_client()
    bc = _mock_book_client(text=None)
    gc = _mock_glossary_client()

    await process_job(pool, kc, llm, bc, gc, _mock_chat_client(), _mock_provider_client(), job)

    mock_extract_persist.assert_not_called()  # skipped


# ── K16.7: backfill — items_total population ─────────────────────────


@pytest.mark.asyncio
@patch("app.runner._extract_and_persist", new_callable=AsyncMock)
async def test_backfill_sets_items_total_when_none(mock_extract_persist):
    """When items_total is None, runner counts items and sets it."""
    mock_extract_persist.return_value = _ok_result()
    chapters = [
        ChapterInfo(chapter_id=f"ch-{i}", title=f"Ch {i}", sort_order=i, revision_id=f"rev-{i}")
        for i in range(5)
    ]
    job = _job(scope="chapters", items_total=None)
    pool = _mock_pool()
    kc = _mock_knowledge_client()
    llm = _mock_llm_client()
    bc = _mock_book_client(chapters=chapters)
    gc = _mock_glossary_client()

    await process_job(pool, kc, llm, bc, gc, _mock_chat_client(), _mock_provider_client(), job)

    # items_total should be set via _set_items_total (execute call)
    set_total_calls = [
        c for c in pool.execute.call_args_list
        if "items_total" in str(c)
    ]
    assert len(set_total_calls) >= 1
    # All 5 chapters should be extracted
    assert mock_extract_persist.call_count == 5


@pytest.mark.asyncio
@patch("app.runner._extract_and_persist", new_callable=AsyncMock)
async def test_backfill_skips_items_total_when_already_set(mock_extract_persist):
    """When items_total is already set, runner does not overwrite it."""
    mock_extract_persist.return_value = _ok_result()
    job = _job(scope="chapters", items_total=10)
    pool = _mock_pool()
    kc = _mock_knowledge_client()
    llm = _mock_llm_client()
    bc = _mock_book_client()
    gc = _mock_glossary_client()

    await process_job(pool, kc, llm, bc, gc, _mock_chat_client(), _mock_provider_client(), job)

    # _set_items_total should NOT be called
    set_total_calls = [
        c for c in pool.execute.call_args_list
        if "items_total = $3" in str(c)
    ]
    assert len(set_total_calls) == 0


@pytest.mark.asyncio
@patch("app.runner._extract_and_persist", new_callable=AsyncMock)
async def test_backfill_scope_all_counts_chapters_and_chat(mock_extract_persist):
    """scope=all counts both chapters and pending chat turns."""
    mock_extract_persist.return_value = _ok_result()
    chapters = [
        ChapterInfo(chapter_id=f"ch-{i}", title=f"Ch {i}", sort_order=i, revision_id=f"rev-{i}")
        for i in range(3)
    ]
    pending_rows = [
        {"pending_id": uuid4(), "event_id": uuid4(), "event_type": "chat.turn",
         "aggregate_type": "session", "aggregate_id": uuid4()}
        for _ in range(2)
    ]
    job = _job(scope="all", items_total=None)
    pool = _mock_pool()
    # fetch is called for _enumerate_pending_chat_turns (twice: once for
    # counting in backfill, once for actual processing)
    pool.fetch = AsyncMock(return_value=pending_rows)
    kc = _mock_knowledge_client()
    llm = _mock_llm_client()
    bc = _mock_book_client(chapters=chapters)
    gc = _mock_glossary_client()

    await process_job(pool, kc, llm, bc, gc, _mock_chat_client(), _mock_provider_client(), job)

    # 3 chapters + 2 chat turns = 5 extract calls
    assert mock_extract_persist.call_count == 5


# ── process_job: glossary_sync scope (C12c-a) ────────────────────────


@pytest.mark.asyncio
@patch("app.runner._extract_and_persist", new_callable=AsyncMock)
async def test_process_job_glossary_sync_success(mock_extract_persist):
    """C12c-a happy path: scope='glossary_sync' iterates glossary
    entities and calls knowledge_client.glossary_sync_entity per
    entity. No LLM extract calls."""
    mock_extract_persist.return_value = _ok_result()
    job = _job(scope="glossary_sync")
    pool = _mock_pool()
    kc = _mock_knowledge_client()
    # Mirror the knowledge-service result wire for glossary-sync.
    kc.glossary_sync_entity = AsyncMock(
        side_effect=lambda **kwargs: _glossary_sync_ok(kwargs["glossary_entity_id"]),
    )
    llm = _mock_llm_client()
    bc = _mock_book_client()
    gc = _mock_glossary_client(pages=[
        (
            [_glossary_entity("e1", "Alice"), _glossary_entity("e2", "Bob")],
            None,
        ),
    ])

    await process_job(pool, kc, llm, bc, gc, _mock_chat_client(), _mock_provider_client(), job)

    # No LLM extract — only the two glossary sync calls.
    mock_extract_persist.assert_not_called()
    assert kc.glossary_sync_entity.call_count == 2

    # Glossary endpoint called once (single page).
    gc.list_book_entities.assert_called_once()


@pytest.mark.asyncio
@patch("app.runner._extract_and_persist", new_callable=AsyncMock)
async def test_process_job_all_scope_includes_glossary(mock_extract_persist):
    """C12c-a behaviour change: scope='all' now iterates glossary
    after chapters+chat. The TODO at line 621 is removed; a user
    who runs `all` gets chapters + chat + glossary end-to-end."""
    mock_extract_persist.return_value = _ok_result()
    chapters = [ChapterInfo(chapter_id="ch-1", title="Ch 1", sort_order=1, revision_id="rev-1")]
    job = _job(scope="all")
    pool = _mock_pool()
    # Return one pending chat turn to exercise the chat branch too.
    pending_rows = [{
        "pending_id": uuid4(),
        "event_id": uuid4(),
        "event_type": "chat.turn.created",
        "aggregate_type": "chat_turn",
        "aggregate_id": uuid4(),
    }]
    pool.fetch = AsyncMock(return_value=pending_rows)
    kc = _mock_knowledge_client()
    kc.glossary_sync_entity = AsyncMock(
        side_effect=lambda **kwargs: _glossary_sync_ok(kwargs["glossary_entity_id"]),
    )
    llm = _mock_llm_client()
    bc = _mock_book_client(chapters=chapters)
    gc = _mock_glossary_client(pages=[
        ([_glossary_entity("e1", "Arthur")], None),
    ])

    await process_job(pool, kc, llm, bc, gc, _mock_chat_client(), _mock_provider_client(), job)

    # chapters + chat → 2 _extract_and_persist; glossary → 1 glossary_sync_entity.
    assert mock_extract_persist.call_count == 2
    assert kc.glossary_sync_entity.call_count == 1


@pytest.mark.asyncio
@patch("app.runner._extract_and_persist", new_callable=AsyncMock)
async def test_process_job_items_total_includes_glossary(mock_extract_persist):
    """C12c-a: when items_total is None (backfill), the pre-count
    covers chapters + chat + glossary pages."""
    mock_extract_persist.return_value = _ok_result()
    chapters = [ChapterInfo(chapter_id=f"ch-{i}", title=f"Ch {i}", sort_order=i, revision_id=f"rev-{i}") for i in range(2)]
    job = _job(scope="all", items_total=None)
    pool = _mock_pool()
    kc = _mock_knowledge_client()
    kc.glossary_sync_entity = AsyncMock(
        side_effect=lambda **kwargs: _glossary_sync_ok(kwargs["glossary_entity_id"]),
    )
    llm = _mock_llm_client()
    bc = _mock_book_client(chapters=chapters)
    gc = _mock_glossary_client(pages=[
        (
            [_glossary_entity(f"e{i}", f"Entity{i}") for i in range(3)],
            None,
        ),
    ])

    await process_job(pool, kc, llm, bc, gc, _mock_chat_client(), _mock_provider_client(), job)

    # _set_items_total sends an UPDATE with SET items_total = $X.
    set_total_calls = [
        c for c in pool.execute.call_args_list
        if isinstance(c.args[0], str)
        and "UPDATE extraction_jobs" in c.args[0]
        and "items_total" in c.args[0]
    ]
    assert len(set_total_calls) == 1
    # Total = 2 chapters + 0 pending + 3 glossary = 5.
    # The bound value is at position [1] after the SQL string; skip
    # past user_id/job_id to reach the total arg.
    call = set_total_calls[0]
    assert 5 in call.args, f"expected total=5 in args, got {call.args}"


@pytest.mark.asyncio
@patch("app.runner._extract_and_persist", new_callable=AsyncMock)
async def test_process_job_glossary_sync_empty_book_no_op(mock_extract_persist):
    """C12c-a: glossary-service returning an empty first page ends
    the branch immediately. Job still completes (no items to sync
    is a valid terminal state)."""
    mock_extract_persist.return_value = _ok_result()
    job = _job(scope="glossary_sync")
    pool = _mock_pool()
    kc = _mock_knowledge_client()
    kc.glossary_sync_entity = AsyncMock()
    llm = _mock_llm_client()
    bc = _mock_book_client()
    gc = _mock_glossary_client()  # default: empty page

    await process_job(pool, kc, llm, bc, gc, _mock_chat_client(), _mock_provider_client(), job)

    kc.glossary_sync_entity.assert_not_called()
    mock_extract_persist.assert_not_called()
    # Job completion sets status=complete (now via conn.fetchrow … RETURNING so the
    # rowcount gates the P1 job-event emit).
    complete_calls = [
        c for c in pool.acquired_conn.fetchrow.call_args_list
        if isinstance(c.args[0], str)
        and "UPDATE extraction_jobs" in c.args[0]
        and "status = 'complete'" in c.args[0].replace('"', "'")
    ]
    assert len(complete_calls) == 1


@pytest.mark.asyncio
@patch("app.runner._extract_and_persist", new_callable=AsyncMock)
async def test_process_job_glossary_partial_enumeration_skips_items_total(mock_extract_persist):
    """/review-impl LOW#5 — when glossary-service returns None on a
    later page, the enumerator returns the partial list + complete=False.
    The runner then MUST skip _set_items_total (or the bar would
    freeze at the wrong total). Any entities already fetched from
    earlier pages are still processed."""
    mock_extract_persist.return_value = _ok_result()
    chapters: list[ChapterInfo] = []
    job = _job(scope="glossary_sync", items_total=None)
    pool = _mock_pool()
    kc = _mock_knowledge_client()
    kc.glossary_sync_entity = AsyncMock(
        side_effect=lambda **kwargs: _glossary_sync_ok(kwargs["glossary_entity_id"]),
    )
    llm = _mock_llm_client()
    bc = _mock_book_client(chapters=chapters)
    # Page 1 returns 2 entities with next_cursor="p2"; page 2 returns
    # None (glossary-service flake). Enumerator keeps page 1's entities
    # and reports complete=False.
    gc = AsyncMock(spec=GlossaryClient)
    gc.list_book_entities = AsyncMock(
        side_effect=[
            GlossaryPage(
                items=(_glossary_entity("e1", "Alpha"), _glossary_entity("e2", "Bravo")),
                next_cursor="p2",
            ),
            None,  # mid-enumeration failure
        ],
    )

    await process_job(pool, kc, llm, bc, gc, _mock_chat_client(), _mock_provider_client(), job)

    # 2 entities synced (page 1 survived).
    assert kc.glossary_sync_entity.call_count == 2
    # items_total SHOULD NOT be set — complete=False gates it.
    set_total_calls = [
        c for c in pool.execute.call_args_list
        if isinstance(c.args[0], str)
        and "UPDATE extraction_jobs" in c.args[0]
        and "items_total" in c.args[0]
    ]
    assert len(set_total_calls) == 0, f"expected no items_total update on partial enum, got {len(set_total_calls)}"


@pytest.mark.asyncio
@patch("app.runner._extract_and_persist", new_callable=AsyncMock)
async def test_process_job_glossary_retry_exhaustion_skips_entity(mock_extract_persist):
    """/review-impl MED#3 — bounded retry. Retryable error for the
    same entity 3 times (persisted via cursor.retry_glossary_<id>)
    causes the entity to be SKIPPED on the 3rd attempt + cursor
    advances past it. Prevents infinite retry loops when
    glossary-service flaps on a specific entity."""
    mock_extract_persist.return_value = _ok_result()
    entity_id = "e1"
    # Simulate third attempt — cursor already has retry count 2.
    job = _job(
        scope="glossary_sync",
        current_cursor={f"retry_glossary_{entity_id}": 2, "scope": "glossary_sync"},
    )
    pool = _mock_pool()
    kc = _mock_knowledge_client()
    kc.glossary_sync_entity = AsyncMock(
        return_value=GlossarySyncResult(
            glossary_entity_id=entity_id,
            action="",
            canonical_name="",
            retryable=True,
            error="glossary-service 502",
        ),
    )
    llm = _mock_llm_client()
    bc = _mock_book_client(chapters=[])
    gc = _mock_glossary_client(pages=[
        ([_glossary_entity(entity_id, "Flaky")], None),
    ])

    await process_job(pool, kc, llm, bc, gc, _mock_chat_client(), _mock_provider_client(), job)

    # One attempt this run — reaches retry count 3 == _MAX_RETRIES_PER_ITEM
    # → skipped. Error log with retry_exhausted event emitted.
    retry_exhausted_logs = [
        c for c in pool.execute.call_args_list
        if isinstance(c.args[0], str)
        and "INSERT INTO job_logs" in c.args[0]
        and c.args[3] == "error"
        and "retry_exhausted" in str(c.args[5])
    ]
    assert len(retry_exhausted_logs) == 1, \
        f"expected 1 retry_exhausted log, got {len(retry_exhausted_logs)}"


# ── Phase 4b-γ /review-impl MED#1 — _extract_and_persist helper ────


def _entity_candidate(name: str = "Kai", kind: str = "person") -> "LLMEntityCandidate":
    """Build a real library candidate for helper tests so ExtractionResult
    flow + persist_pass2 kwargs can be asserted concretely."""
    from loreweave_extraction.extractors.entity import LLMEntityCandidate
    return LLMEntityCandidate(
        name=name, kind=kind, aliases=[],
        confidence=0.9,
        canonical_name=name.lower(),
        canonical_id="a" * 32,
    )


@pytest.mark.asyncio
@patch("app.runner.extract_pass2", new_callable=AsyncMock)
async def test_extract_and_persist_happy_path_calls_persist_with_candidates(
    mock_extract,
):
    """Phase 4b-γ /review-impl MED#1 — verify _extract_and_persist
    threads candidates from extract_pass2 into knowledge_client.persist_pass2
    with the right kwargs. Locks the bridge contract that all 23
    runner tests bypass via @patch."""
    from loreweave_extraction.pass2 import Pass2Candidates
    from app.runner import _extract_and_persist

    candidates = Pass2Candidates(
        entities=[_entity_candidate("Kai")],
        relations=[],
        events=[],
        facts=[],
    )
    mock_extract.return_value = candidates
    kc = AsyncMock(spec=KnowledgeClient)
    kc.persist_pass2 = AsyncMock(return_value=ExtractionResult(
        source_id="ch-1", entities_merged=2, relations_created=1,
        events_merged=1, facts_merged=3,
    ))
    user_id = uuid4()
    project_id = uuid4()
    job_id = uuid4()

    result, _candidates = await _extract_and_persist(
        knowledge_client=kc,
        llm_client=_mock_llm_client(),
        user_id=user_id,
        project_id=project_id,
        source_type="chapter",
        source_id="ch-1",
        job_id=job_id,
        model_ref="qwen-test",
        text="Some chapter text.",
    )

    assert result.error is None
    assert result.entities_merged == 2  # from _ok_result
    kc.persist_pass2.assert_awaited_once()
    persist_kwargs = kc.persist_pass2.call_args.kwargs
    assert persist_kwargs["user_id"] == user_id
    assert persist_kwargs["project_id"] == project_id
    assert persist_kwargs["source_type"] == "chapter"
    assert persist_kwargs["source_id"] == "ch-1"
    assert persist_kwargs["job_id"] == job_id
    assert persist_kwargs["extraction_model"] == "qwen-test"
    assert len(persist_kwargs["entities"]) == 1
    assert persist_kwargs["entities"][0].name == "Kai"
    # extract_pass2 received user_id/project_id as STRINGS (library contract)
    extract_kwargs = mock_extract.call_args.kwargs
    assert extract_kwargs["user_id"] == str(user_id)
    assert extract_kwargs["project_id"] == str(project_id)
    assert extract_kwargs["text"] == "Some chapter text."


@pytest.mark.asyncio
@patch("app.runner.extract_pass2", new_callable=AsyncMock)
async def test_extract_and_persist_provider_exhausted_is_retryable(mock_extract):
    """Phase 4b-γ /review-impl MED#1 — ExtractionError(stage='provider_exhausted')
    surfaces as ExtractionResult(retryable=True) so the runner retries
    the item per its _MAX_RETRIES_PER_ITEM logic. Persist endpoint
    is NOT called on this path (no candidates to write)."""
    from loreweave_extraction.errors import ExtractionError
    from app.runner import _extract_and_persist

    mock_extract.side_effect = ExtractionError(
        "transient retry exhausted",
        stage="provider_exhausted",
    )
    kc = AsyncMock(spec=KnowledgeClient)
    kc.persist_pass2 = AsyncMock()

    result, _candidates = await _extract_and_persist(
        knowledge_client=kc, llm_client=_mock_llm_client(),
        user_id=uuid4(), project_id=uuid4(),
        source_type="chapter", source_id="ch-1", job_id=uuid4(),
        model_ref="qwen-test", text="text",
    )

    assert result.retryable is True
    assert result.error is not None
    assert "provider_exhausted" in result.error
    kc.persist_pass2.assert_not_awaited()


@pytest.mark.asyncio
@patch("app.runner.extract_pass2", new_callable=AsyncMock)
async def test_extract_and_persist_provider_stage_is_not_retryable(mock_extract):
    """Phase 4b-γ /review-impl MED#1 — non-transient provider failure
    (stage='provider') is NOT retryable; runner will fail the job."""
    from loreweave_extraction.errors import ExtractionError
    from app.runner import _extract_and_persist

    mock_extract.side_effect = ExtractionError(
        "invalid api key", stage="provider",
    )
    kc = AsyncMock(spec=KnowledgeClient)
    kc.persist_pass2 = AsyncMock()

    result, _candidates = await _extract_and_persist(
        knowledge_client=kc, llm_client=_mock_llm_client(),
        user_id=uuid4(), project_id=uuid4(),
        source_type="chapter", source_id="ch-1", job_id=uuid4(),
        model_ref="qwen-test", text="text",
    )

    assert result.retryable is False
    kc.persist_pass2.assert_not_awaited()


@pytest.mark.asyncio
@patch("app.runner.extract_pass2", new_callable=AsyncMock)
async def test_extract_and_persist_cancelled_stage_is_not_retryable(mock_extract):
    """Phase 4b-γ /review-impl MED#1 — operator-initiated LLM cancel
    (stage='cancelled') is NOT retryable. Runner treats this as a
    non-retryable error → fails the whole extraction job. Same
    behavior as the legacy extract-item path."""
    from loreweave_extraction.errors import ExtractionError
    from app.runner import _extract_and_persist

    mock_extract.side_effect = ExtractionError(
        "operator cancelled job", stage="cancelled",
    )
    kc = AsyncMock(spec=KnowledgeClient)
    kc.persist_pass2 = AsyncMock()

    result, _candidates = await _extract_and_persist(
        knowledge_client=kc, llm_client=_mock_llm_client(),
        user_id=uuid4(), project_id=uuid4(),
        source_type="chapter", source_id="ch-1", job_id=uuid4(),
        model_ref="qwen-test", text="text",
    )

    assert result.retryable is False
    assert "cancelled" in result.error
    kc.persist_pass2.assert_not_awaited()


@pytest.mark.asyncio
@patch("app.runner.extract_pass2", new_callable=AsyncMock)
async def test_extract_and_persist_empty_text_still_persists(mock_extract):
    """Phase 4b-γ /review-impl MED#1 — empty text → library
    short-circuits to empty Pass2Candidates → persist_pass2 STILL
    called with empty lists (idempotent source-row upsert).
    Matches the legacy extract-item path's behavior for chat_turn
    placeholders that don't fetch text from chat-service yet."""
    from loreweave_extraction.pass2 import Pass2Candidates
    from app.runner import _extract_and_persist

    mock_extract.return_value = Pass2Candidates()  # all 4 lists empty
    kc = AsyncMock(spec=KnowledgeClient)
    kc.persist_pass2 = AsyncMock(return_value=ExtractionResult(
        source_id="turn-1", entities_merged=0, relations_created=0,
        events_merged=0, facts_merged=0,
    ))

    result, _candidates = await _extract_and_persist(
        knowledge_client=kc, llm_client=_mock_llm_client(),
        user_id=uuid4(), project_id=uuid4(),
        source_type="chat_turn", source_id="turn-1", job_id=uuid4(),
        model_ref="qwen-test", text="",
    )

    assert result.error is None
    kc.persist_pass2.assert_awaited_once()
    persist_kwargs = kc.persist_pass2.call_args.kwargs
    assert persist_kwargs["entities"] == []
    assert persist_kwargs["relations"] == []
    assert persist_kwargs["events"] == []
    assert persist_kwargs["facts"] == []


# ── Phase 4b-γ /review-impl MED#2 — KnowledgeClient.persist_pass2 wire ──


@pytest.mark.asyncio
async def test_knowledge_client_persist_pass2_posts_correct_body_shape():
    """Phase 4b-γ /review-impl MED#2 — verify the wire format sent to
    /internal/extraction/persist-pass2 matches server-side
    PersistPass2Request schema. Catches a future library field rename
    or JSON-key change that would silently 422 in production."""
    import httpx
    from loreweave_extraction.extractors.entity import LLMEntityCandidate

    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["method"] = request.method
        captured["headers"] = dict(request.headers)
        captured["body"] = request.read().decode()
        return httpx.Response(200, json={
            "source_id": "ch-1",
            "entities_merged": 1,
            "relations_created": 0,
            "events_merged": 0,
            "facts_merged": 0,
            "evidence_edges": 0,
            "duration_seconds": 0.5,
        })

    transport = httpx.MockTransport(handler)
    client = KnowledgeClient(
        base_url="http://test-host:8092",
        internal_token="dev_token",
        timeout_s=30.0,
    )
    # Replace the underlying httpx client with a MockTransport-backed one
    await client._http.aclose()
    client._http = httpx.AsyncClient(
        transport=transport,
        timeout=httpx.Timeout(30.0),
        headers={"X-Internal-Token": "dev_token"},
    )

    user_id = uuid4()
    project_id = uuid4()
    job_id = uuid4()
    entity = LLMEntityCandidate(
        name="Kai", kind="person", aliases=["K"],
        confidence=0.9, canonical_name="kai",
        canonical_id="a" * 32,
    )

    result = await client.persist_pass2(
        user_id=user_id,
        project_id=project_id,
        source_type="chapter",
        source_id="ch-1",
        job_id=job_id,
        extraction_model="qwen-test",
        entities=[entity],
        relations=[],
        events=[],
        facts=[],
    )

    await client.aclose()

    # Wire-format assertions (the meat of MED#2)
    import json as _json
    assert captured["url"].endswith("/internal/extraction/persist-pass2")
    assert captured["method"] == "POST"
    assert captured["headers"].get("x-internal-token") == "dev_token"
    body = _json.loads(captured["body"])
    assert body["user_id"] == str(user_id)
    assert body["project_id"] == str(project_id)
    assert body["source_type"] == "chapter"
    assert body["source_id"] == "ch-1"
    assert body["job_id"] == str(job_id)
    assert body["extraction_model"] == "qwen-test"
    assert isinstance(body["entities"], list) and len(body["entities"]) == 1
    assert body["entities"][0]["name"] == "Kai"
    assert body["entities"][0]["kind"] == "person"
    assert body["entities"][0]["canonical_id"] == "a" * 32
    assert body["entities"][0]["confidence"] == 0.9
    assert body["entities"][0]["aliases"] == ["K"]
    assert body["relations"] == []
    assert body["events"] == []
    assert body["facts"] == []

    # Response was parsed correctly
    assert result.entities_merged == 1
    assert result.error is None


@pytest.mark.asyncio
async def test_knowledge_client_persist_pass2_502_returns_retryable_error():
    """Phase 4b-γ /review-impl MED#2 — 5xx from server surfaces as
    ExtractionResult(retryable=True) so the runner's retry logic
    fires. Locks the contract for transient knowledge-service
    failures (Neo4j hiccup, deploy mid-extraction)."""
    import httpx

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(502, text="upstream gone")

    transport = httpx.MockTransport(handler)
    client = KnowledgeClient(
        base_url="http://test-host:8092",
        internal_token="dev_token",
        timeout_s=30.0,
    )
    await client._http.aclose()
    client._http = httpx.AsyncClient(
        transport=transport,
        timeout=httpx.Timeout(30.0),
        headers={"X-Internal-Token": "dev_token"},
    )

    result = await client.persist_pass2(
        user_id=uuid4(), project_id=uuid4(),
        source_type="chapter", source_id="ch-1", job_id=uuid4(),
        extraction_model="qwen-test",
        entities=[], relations=[], events=[], facts=[],
    )

    await client.aclose()

    assert result.retryable is True
    assert result.error is not None
    assert "502" in result.error


# ── P3 D-P3-EXTRACTION-CALLER-WIRE-UP — BookClient.get_chapter_hierarchy ──


@pytest.mark.asyncio
async def test_book_client_get_chapter_hierarchy_parses_full_response():
    """200 with full hierarchy → ChapterHierarchy with part + scenes."""
    from app.clients import BookClient, ChapterHierarchy
    client = BookClient("http://book", "tok", timeout_s=5.0)

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    book_id_str = str(uuid4())
    chapter_id_str = str(uuid4())
    part_id_str = str(uuid4())
    scene_id_str = str(uuid4())
    mock_resp.json.return_value = {
        "book": {"id": book_id_str, "path": "book", "title": "The Book"},
        "part": {
            "id": part_id_str, "path": "book/part-1",
            "index": 1, "title": "Part 1",
        },
        "chapter": {
            "id": chapter_id_str, "path": "book/part-1/chapter-1",
            "index": 1, "title": "Chapter 1", "sort_order": 1,
        },
        "scenes": [
            {"id": scene_id_str, "path": "book/part-1/chapter-1/scene-1", "index": 1},
        ],
        "book_parts": [
            {"id": part_id_str, "path": "book/part-1", "index": 1, "title": "Part 1"},
        ],
    }
    with patch.object(client._http, "get", AsyncMock(return_value=mock_resp)):
        hierarchy = await client.get_chapter_hierarchy(uuid4(), chapter_id_str)

    assert isinstance(hierarchy, ChapterHierarchy)
    assert hierarchy.book_id == book_id_str
    assert hierarchy.part is not None
    assert hierarchy.part.path == "book/part-1"
    assert len(hierarchy.scenes) == 1
    assert hierarchy.scenes[0].id == scene_id_str
    assert len(hierarchy.book_parts) == 1
    await client.aclose()


@pytest.mark.asyncio
async def test_book_client_get_chapter_hierarchy_legacy_chapter_has_null_part():
    """Legacy chapter (NULL part_id) → part=None + scenes=()."""
    from app.clients import BookClient
    client = BookClient("http://book", "tok", timeout_s=5.0)
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    chapter_id_str = str(uuid4())
    mock_resp.json.return_value = {
        "book": {"id": str(uuid4()), "path": "book", "title": None},
        "part": None,
        "chapter": {
            "id": chapter_id_str, "path": None,
            "index": 1, "title": "Legacy", "sort_order": 1,
        },
        "scenes": [],
        "book_parts": [],
    }
    with patch.object(client._http, "get", AsyncMock(return_value=mock_resp)):
        hierarchy = await client.get_chapter_hierarchy(uuid4(), chapter_id_str)
    assert hierarchy is not None
    assert hierarchy.part is None
    assert hierarchy.chapter_path is None
    assert hierarchy.scenes == ()
    await client.aclose()


@pytest.mark.asyncio
async def test_book_client_get_chapter_hierarchy_404_returns_none():
    from app.clients import BookClient
    client = BookClient("http://book", "tok", timeout_s=5.0)
    mock_resp = MagicMock()
    mock_resp.status_code = 404
    with patch.object(client._http, "get", AsyncMock(return_value=mock_resp)):
        hierarchy = await client.get_chapter_hierarchy(uuid4(), "ch-1")
    assert hierarchy is None
    await client.aclose()


@pytest.mark.asyncio
async def test_book_client_get_chapter_hierarchy_http_error_returns_none():
    import httpx
    from app.clients import BookClient
    client = BookClient("http://book", "tok", timeout_s=5.0)
    with patch.object(
        client._http, "get",
        AsyncMock(side_effect=httpx.ConnectError("refused")),
    ):
        hierarchy = await client.get_chapter_hierarchy(uuid4(), "ch-1")
    assert hierarchy is None
    await client.aclose()


@pytest.mark.asyncio
async def test_knowledge_client_persist_pass2_forwards_p3_fields_when_provided():
    """When all P3 kwargs supplied, persist_pass2 includes them in the body."""
    client = KnowledgeClient("http://ks", "tok", timeout_s=5.0)
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "source_id": "ch-1", "entities_merged": 1,
        "relations_created": 0, "events_merged": 0, "facts_merged": 0,
        "evidence_edges": 0,
    }
    hp = {"book_id": "b1", "book_path": "book", "part_id": "p1",
          "part_path": "book/part-1", "part_index": 1,
          "chapter_id": "c1", "chapter_path": "book/part-1/chapter-1",
          "chapter_index": 1, "scenes": []}
    post_mock = AsyncMock(return_value=mock_resp)
    with patch.object(client._http, "post", post_mock):
        await client.persist_pass2(
            user_id=uuid4(), project_id=uuid4(),
            source_type="chapter", source_id="ch-1", job_id=uuid4(),
            extraction_model="qwen-test",
            entities=[], relations=[], events=[], facts=[],
            hierarchy_paths=hp, book_parts=[("p1", "book/part-1", "1")],
            is_last_chapter_of_book=True,
            embedding_model_uuid="emb-uuid", embedding_dimension=1024,
        )
    body = post_mock.call_args.kwargs["json"]
    assert body["hierarchy_paths"] == hp
    assert body["book_parts"] == [("p1", "book/part-1", "1")]
    assert body["is_last_chapter_of_book"] is True
    assert body["embedding_model_uuid"] == "emb-uuid"
    assert body["embedding_dimension"] == 1024
    await client.aclose()


@pytest.mark.asyncio
async def test_knowledge_client_persist_pass2_omits_p3_fields_when_legacy():
    """Legacy callers (no P3 kwargs) → body has no P3 keys."""
    client = KnowledgeClient("http://ks", "tok", timeout_s=5.0)
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "source_id": "ch-1", "entities_merged": 0,
        "relations_created": 0, "events_merged": 0, "facts_merged": 0,
        "evidence_edges": 0,
    }
    post_mock = AsyncMock(return_value=mock_resp)
    with patch.object(client._http, "post", post_mock):
        await client.persist_pass2(
            user_id=uuid4(), project_id=uuid4(),
            source_type="chapter", source_id="ch-1", job_id=uuid4(),
            extraction_model="qwen-test",
            entities=[], relations=[], events=[], facts=[],
        )
    body = post_mock.call_args.kwargs["json"]
    assert "hierarchy_paths" not in body
    assert "embedding_model_uuid" not in body
    assert "is_last_chapter_of_book" not in body
    await client.aclose()


# ── P3 runner wire-up — embedding_dimension threaded through JobRow ──


@pytest.mark.asyncio
async def test_get_running_jobs_pulls_embedding_dimension(monkeypatch):
    """SQL JOIN to knowledge_projects threads embedding_dimension onto JobRow."""
    from app.runner import _get_running_jobs
    project_id = uuid4()
    user_id = uuid4()
    fake_row = {
        "job_id": uuid4(), "user_id": user_id, "project_id": project_id,
        "scope": "chapters", "scope_range": None, "status": "running",
        "llm_model": "qwen", "embedding_model": "emb-uuid",
        "max_spend_usd": Decimal("10"), "items_total": 5,
        "items_processed": 0, "current_cursor": None,
        "cost_spent_usd": Decimal("0"),
        "campaign_id": None,
        "billing_user_id": None,
        "billing_embedding_model": None,
        "billing_llm_model": None,
        "embedding_dimension": 1024,
        "extraction_config": {},
        "genre": "Tiên hiệp",
        "save_raw_extraction": True,
        # C12 + C13 — columns added to the running-jobs SELECT.
        "targets": None,
        "concurrency_level": None,
        "pinned_entity_ids": None,
        "reasoning_effort": "none",
        "mcp_key_id": None,
        "spend_cap_usd": None,
    }
    pool = AsyncMock()
    pool.fetch = AsyncMock(return_value=[fake_row])
    jobs = await _get_running_jobs(pool)
    assert len(jobs) == 1
    assert jobs[0].embedding_dimension == 1024
    assert jobs[0].genre == "Tiên hiệp"
    assert jobs[0].save_raw_extraction is True  # Q4b-feed: threaded onto JobRow
    assert jobs[0].billing_user_id is None  # E0-3 2a: owner-triggered ⇒ NULL


@pytest.mark.asyncio
async def test_get_running_jobs_handles_null_embedding_dimension():
    """LEFT JOIN can return NULL dimension for projects with no embedding."""
    from app.runner import _get_running_jobs
    fake_row = {
        "job_id": uuid4(), "user_id": uuid4(), "project_id": uuid4(),
        "scope": "chapters", "scope_range": None, "status": "running",
        "llm_model": "qwen", "embedding_model": "",
        "max_spend_usd": None, "items_total": None,
        "items_processed": 0, "current_cursor": None,
        "cost_spent_usd": Decimal("0"),
        "campaign_id": None,
        "billing_user_id": None,
        "billing_embedding_model": None,
        "billing_llm_model": None,
        "embedding_dimension": None,
        "extraction_config": None,
        "genre": None,
        "save_raw_extraction": False,
        # C12 + C13 — columns added to the running-jobs SELECT.
        "targets": None,
        "concurrency_level": None,
        "pinned_entity_ids": None,
        "reasoning_effort": "none",
        "mcp_key_id": None,
        "spend_cap_usd": None,
    }
    pool = AsyncMock()
    pool.fetch = AsyncMock(return_value=[fake_row])
    jobs = await _get_running_jobs(pool)
    assert jobs[0].embedding_dimension is None
    assert jobs[0].save_raw_extraction is False  # Q4b-feed: default OFF


@pytest.mark.asyncio
async def test_get_running_jobs_threads_billing_identity():
    """E0-3 Phase 2a: a collaborator-triggered job's billing identity is read
    from the SELECT onto JobRow so process_job can bill the caller's key."""
    from app.runner import _get_running_jobs
    collab = uuid4()
    fake_row = {
        "job_id": uuid4(), "user_id": uuid4(), "project_id": uuid4(),
        "scope": "chapters", "scope_range": None, "status": "running",
        "llm_model": "owner-llm", "embedding_model": "owner-emb",
        "max_spend_usd": None, "items_total": None,
        "items_processed": 0, "current_cursor": None,
        "cost_spent_usd": Decimal("0"),
        "campaign_id": None,
        "billing_user_id": collab,
        "billing_embedding_model": "collab-emb",
        "billing_llm_model": "collab-llm",
        "embedding_dimension": 1024,
        "extraction_config": None,
        "genre": None,
        "save_raw_extraction": False,
        # C12 + C13 — columns added to the running-jobs SELECT.
        "targets": None,
        "concurrency_level": None,
        "pinned_entity_ids": None,
        "reasoning_effort": "none",
        "mcp_key_id": None,
        "spend_cap_usd": None,
    }
    pool = AsyncMock()
    pool.fetch = AsyncMock(return_value=[fake_row])
    jobs = await _get_running_jobs(pool)
    assert jobs[0].billing_user_id == collab
    assert jobs[0].billing_embedding_model == "collab-emb"
    assert jobs[0].billing_llm_model == "collab-llm"


@pytest.mark.asyncio
async def test_get_running_jobs_threads_pinned_entity_ids():
    """C13: pinned_entity_ids (JSONB) is read from the SELECT onto JobRow so
    process_job can fetch the pinned names + inject them into every window.
    asyncpg may hand JSONB back as a raw JSON string — _decode_pinned normalises
    it to a list."""
    from app.runner import _get_running_jobs
    fake_row = {
        "job_id": uuid4(), "user_id": uuid4(), "project_id": uuid4(),
        "scope": "chapters", "scope_range": None, "status": "running",
        "llm_model": "qwen", "embedding_model": "emb",
        "max_spend_usd": None, "items_total": None,
        "items_processed": 0, "current_cursor": None,
        "cost_spent_usd": Decimal("0"),
        "campaign_id": None,
        "billing_user_id": None,
        "billing_embedding_model": None,
        "billing_llm_model": None,
        "embedding_dimension": 1024,
        "extraction_config": None,
        "genre": None,
        "save_raw_extraction": False,
        "targets": None,
        "concurrency_level": None,
        # JSONB returned as a raw JSON string (the asyncpg default codec).
        "pinned_entity_ids": '["g-1", "g-2"]',
        "reasoning_effort": "high",
        "mcp_key_id": None,
        "spend_cap_usd": None,
    }
    pool = AsyncMock()
    pool.fetch = AsyncMock(return_value=[fake_row])
    jobs = await _get_running_jobs(pool)
    assert jobs[0].pinned_entity_ids == ["g-1", "g-2"]
    # D-KG-WORKER-GRADED-EFFORT — the stored graded effort threads onto JobRow.
    assert jobs[0].reasoning_effort == "high"


# ── D-PHASE6C-WORKERAI-JOB-SPAN: parent span per process_job call ───


@pytest.fixture(scope="module")
def _worker_ai_span_exporter():
    """Install an in-memory OTel exporter as the global provider so
    every `tracer.start_as_current_span` in app.runner exports here.

    Module-scoped because OTel's `set_tracer_provider` is set-once;
    re-installing per test silently no-ops on the second call.
    """
    from opentelemetry import trace as _trace
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
        InMemorySpanExporter,
    )

    exporter = InMemorySpanExporter()
    provider = TracerProvider(resource=Resource.create({"service.name": "worker-ai-test"}))
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    _trace.set_tracer_provider(provider)

    # Re-create the module-level tracer so it binds to the new provider
    # (the original was created at module import before the test provider
    # existed).
    from app import runner as _runner
    _runner.tracer = _trace.get_tracer(_runner.__name__)
    return exporter


@pytest.mark.asyncio
@patch("app.runner._extract_and_persist", new_callable=AsyncMock)
async def test_process_job_emits_parent_span_with_job_attributes(
    mock_extract_persist, _worker_ai_span_exporter,
):
    """The decorator MUST wrap each process_job call in one OTel span
    named `worker_ai.process_job`, carrying the job's identifiers as
    attributes so an operator filtering Tempo by `job.id` finds the
    whole job trace (and all SDK-call children under it via httpx
    instrumentation in production).
    """
    mock_extract_persist.return_value = _ok_result()
    job = _job(scope="chapters", items_total=7)
    pool = _mock_pool()
    kc = _mock_knowledge_client()
    llm = _mock_llm_client()
    bc = _mock_book_client()
    gc = _mock_glossary_client()

    _worker_ai_span_exporter.clear()
    await process_job(pool, kc, llm, bc, gc, _mock_chat_client(), _mock_provider_client(), job)

    spans = [
        s for s in _worker_ai_span_exporter.get_finished_spans()
        if s.name == "worker_ai.process_job"
    ]
    assert len(spans) == 1, (
        f"expected exactly one worker_ai.process_job span, got "
        f"{[s.name for s in _worker_ai_span_exporter.get_finished_spans()]}"
    )
    span = spans[0]
    attrs = dict(span.attributes or {})
    assert attrs["job.id"] == str(job.job_id)
    assert attrs["job.scope"] == "chapters"
    assert attrs["job.project_id"] == str(job.project_id)
    assert attrs["job.user_id"] == str(job.user_id)
    assert attrs["job.items_total"] == 7


@pytest.mark.asyncio
@patch("app.runner._extract_and_persist", new_callable=AsyncMock)
async def test_process_job_span_handles_none_items_total(
    mock_extract_persist, _worker_ai_span_exporter,
):
    """Defensive: `items_total` is nullable on the JobRow (backfill case,
    pre-K16.7 jobs). The span attribute must coerce to 0 so the OTel
    SDK doesn't reject the None value (attribute values must be
    primitive types)."""
    mock_extract_persist.return_value = _ok_result()
    job = _job(scope="chapters", items_total=None)
    pool = _mock_pool()
    kc = _mock_knowledge_client()
    llm = _mock_llm_client()
    bc = _mock_book_client()
    gc = _mock_glossary_client()

    _worker_ai_span_exporter.clear()
    await process_job(pool, kc, llm, bc, gc, _mock_chat_client(), _mock_provider_client(), job)

    spans = [
        s for s in _worker_ai_span_exporter.get_finished_spans()
        if s.name == "worker_ai.process_job"
    ]
    assert len(spans) == 1
    assert dict(spans[0].attributes or {})["job.items_total"] == 0


# ── Cycle 72 — precision filter env wiring regression tests ────────────


@pytest.mark.asyncio
async def test_runner_env_unset_skips_filter() -> None:
    """When WORKER_AI_PRECISION_FILTER_MODEL_REF is unset, the runner
    calls extract_pass2 with precision_filter=None (current behavior
    preserved). Regression-lock for the kwarg default — see
    docs/specs/2026-05-29-pass2-precision-filter.md acceptance #3."""
    from app.runner import _extract_and_persist

    captured: list[dict] = []

    async def _stub_extract_pass2(**kwargs):
        captured.append(kwargs)
        from loreweave_extraction import Pass2Candidates
        return Pass2Candidates()

    with patch("app.runner._PRECISION_FILTER_CONFIG", None), \
         patch("app.runner.extract_pass2", new=_stub_extract_pass2):
        kc = _mock_knowledge_client()
        llm = _mock_llm_client()

        await _extract_and_persist(
            knowledge_client=kc,
            llm_client=llm,
            user_id=uuid4(),
            project_id=uuid4(),
            source_type="chapter",
            source_id="ch-1",
            job_id=uuid4(),
            model_ref="test-model",
            text="A short passage.",
        )

    assert len(captured) == 1
    # The kwarg is present and explicitly None
    assert captured[0].get("precision_filter") is None


@pytest.mark.asyncio
async def test_runner_env_set_passes_filter_config_to_extract_pass2() -> None:
    """When WORKER_AI_PRECISION_FILTER_MODEL_REF is set, the runner
    threads the resulting PrecisionFilterConfig through to extract_pass2.
    """
    from loreweave_extraction import PrecisionFilterConfig

    sentinel = PrecisionFilterConfig(
        model_ref="test-filter-model",
        partial_policy="drop",
        categories=("relation", "event"),
    )

    captured: list[dict] = []

    async def _stub_extract_pass2(**kwargs):
        captured.append(kwargs)
        from loreweave_extraction import Pass2Candidates
        return Pass2Candidates()

    from app.runner import _extract_and_persist

    with patch("app.runner._PRECISION_FILTER_CONFIG", sentinel), \
         patch("app.runner.extract_pass2", new=_stub_extract_pass2):
        kc = _mock_knowledge_client()
        llm = _mock_llm_client()

        await _extract_and_persist(
            knowledge_client=kc,
            llm_client=llm,
            user_id=uuid4(),
            project_id=uuid4(),
            source_type="chapter",
            source_id="ch-2",
            job_id=uuid4(),
            model_ref="test-model",
            text="A short passage.",
        )

    assert len(captured) == 1
    assert captured[0].get("precision_filter") is sentinel


@pytest.mark.asyncio
async def test_runner_filter_degraded_status_still_persists_pass_a() -> None:
    """Even when extract_pass2 returns filter_status='degraded', the
    runner persists the Pass A candidates (filter is best-effort).
    Regression-lock for the no-raise contract."""
    from loreweave_extraction import (
        LLMEntityCandidate, Pass2Candidates, PrecisionFilterConfig,
    )

    pass_a_entity = LLMEntityCandidate(
        name="Kai", kind="person", aliases=[],
        confidence=0.9, canonical_name="kai", canonical_id="eid-kai",
    )

    async def _stub_extract_pass2(**kwargs):
        # Simulate filter degradation: Pass A returned, status=degraded
        return Pass2Candidates(
            entities=[pass_a_entity],
            filter_status="degraded",
            filter_coverage={"entity": 0.0},
        )

    from app.runner import _extract_and_persist

    config = PrecisionFilterConfig(model_ref="test-filter")
    with patch("app.runner._PRECISION_FILTER_CONFIG", config), \
         patch("app.runner.extract_pass2", new=_stub_extract_pass2):
        kc = _mock_knowledge_client()
        llm = _mock_llm_client()

        result, _candidates = await _extract_and_persist(
            knowledge_client=kc,
            llm_client=llm,
            user_id=uuid4(),
            project_id=uuid4(),
            source_type="chapter",
            source_id="ch-3",
            job_id=uuid4(),
            model_ref="test-model",
            text="A short passage.",
        )

    # persist_pass2 was called with the Pass A entity intact
    kc.persist_pass2.assert_called_once()
    call_kwargs = kc.persist_pass2.call_args.kwargs
    assert call_kwargs["entities"] == [pass_a_entity]
    # ExtractionResult is the mocked _ok_result return
    assert isinstance(result, ExtractionResult)


def test_load_precision_filter_config_env_unset_returns_none() -> None:
    """Empty / unset env returns None (filter disabled)."""
    import os
    from app.runner import _load_precision_filter_config

    original = os.environ.pop("WORKER_AI_PRECISION_FILTER_MODEL_REF", None)
    try:
        assert _load_precision_filter_config() is None
        os.environ["WORKER_AI_PRECISION_FILTER_MODEL_REF"] = ""
        assert _load_precision_filter_config() is None
    finally:
        os.environ.pop("WORKER_AI_PRECISION_FILTER_MODEL_REF", None)
        if original is not None:
            os.environ["WORKER_AI_PRECISION_FILTER_MODEL_REF"] = original


def test_load_precision_filter_config_ignores_env_model_ref() -> None:
    """D-WX-PRECISION-FILTER-MODEL-ARCH — the env is NO LONGER a filter-model source.
    Even with WORKER_AI_PRECISION_FILTER_MODEL_REF set, the loader returns None: a
    global env model is cross-tenant (it 404'd for every user who didn't own it and
    stalled the decoupled fold). The filter model now comes ONLY from the per-project
    extraction_config.precision_filter override (resolve_effective_config), resolved
    per-user. This regression-locks that no env can reintroduce a global filter model."""
    import os
    from app.runner import _load_precision_filter_config

    saved = {
        k: os.environ.pop(k, None) for k in (
            "WORKER_AI_PRECISION_FILTER_MODEL_REF",
            "WORKER_AI_PRECISION_FILTER_PARTIAL_POLICY",
            "WORKER_AI_PRECISION_FILTER_MODEL_SOURCE",
            "WORKER_AI_PRECISION_FILTER_CATEGORIES",
        )
    }
    try:
        os.environ["WORKER_AI_PRECISION_FILTER_MODEL_REF"] = "some-cross-tenant-uuid"
        os.environ["WORKER_AI_PRECISION_FILTER_PARTIAL_POLICY"] = "drop"
        os.environ["WORKER_AI_PRECISION_FILTER_MODEL_SOURCE"] = "user_model"
        os.environ["WORKER_AI_PRECISION_FILTER_CATEGORIES"] = "relation"
        assert _load_precision_filter_config() is None
    finally:
        for k, v in saved.items():
            os.environ.pop(k, None)
            if v is not None:
                os.environ[k] = v


def test_resolve_filter_falls_back_to_extraction_model() -> None:
    """D-WX-PRECISION-FILTER-MODEL-ARCH — a per-project precision_filter override that
    ENABLES the filter WITHOUT its own model_ref resolves to the EXTRACTION model
    (user-owned, UI-selected, DB-stored, per-user) — never an env/global model. The
    category/policy still come from the override."""
    from loreweave_extraction import resolve_effective_config

    snap = resolve_effective_config(
        global_defaults={
            "model_ref": "user-extraction-model", "model_source": "user_model",
            "precision_filter": None, "entity_recovery": None, "writer_autocreate": False,
        },
        project_overrides={
            "precision_filter": {
                "enabled": True, "categories": ["relation"], "partial_policy": "drop",
            },
        },
    )
    assert snap.precision_filter is not None
    assert snap.precision_filter.model_ref == "user-extraction-model"
    assert snap.precision_filter.model_source == "user_model"
    assert snap.precision_filter.categories == ("relation",)


def test_resolve_filter_honors_explicit_override_model() -> None:
    """An explicit per-project filter model_ref (e.g. a stronger judge the user picked
    in the UI) is honored over the extraction-model fallback — still per-user."""
    from loreweave_extraction import resolve_effective_config

    snap = resolve_effective_config(
        global_defaults={
            "model_ref": "extraction-model", "model_source": "user_model",
            "precision_filter": None, "entity_recovery": None, "writer_autocreate": False,
        },
        project_overrides={
            "precision_filter": {
                "enabled": True, "model_ref": "explicit-filter-model",
                "model_source": "user_model", "categories": ["relation"],
            },
        },
    )
    assert snap.precision_filter is not None
    assert snap.precision_filter.model_ref == "explicit-filter-model"


# ── Cycle 73d — entity recovery env loader ─────────────────────────────


def test_load_entity_recovery_config_env_unset_returns_none() -> None:
    import os
    from app.runner import _load_entity_recovery_config

    saved = os.environ.pop("WORKER_AI_ENTITY_RECOVERY_MODEL_REF", None)
    try:
        assert _load_entity_recovery_config() is None
    finally:
        if saved is not None:
            os.environ["WORKER_AI_ENTITY_RECOVERY_MODEL_REF"] = saved


def test_load_entity_recovery_config_env_set_builds_config() -> None:
    import os
    from app.runner import _load_entity_recovery_config

    saved = {
        k: os.environ.pop(k, None) for k in (
            "WORKER_AI_ENTITY_RECOVERY_MODEL_REF",
            "WORKER_AI_ENTITY_RECOVERY_MODEL_SOURCE",
            "WORKER_AI_ENTITY_RECOVERY_MAX_BATCH",
        )
    }
    try:
        os.environ["WORKER_AI_ENTITY_RECOVERY_MODEL_REF"] = "claude-4.7-opus-uuid"
        os.environ["WORKER_AI_ENTITY_RECOVERY_MODEL_SOURCE"] = "platform_model"
        os.environ["WORKER_AI_ENTITY_RECOVERY_MAX_BATCH"] = "8"
        config = _load_entity_recovery_config()
        assert config is not None
        assert config.model_ref == "claude-4.7-opus-uuid"
        assert config.model_source == "platform_model"
        assert config.max_items_per_batch == 8
        # worker-ai has no glossary → empty known_kinds
        assert dict(config.known_entity_kinds) == {}
    finally:
        for k, v in saved.items():
            os.environ.pop(k, None)
            if v is not None:
                os.environ[k] = v


@pytest.mark.asyncio
async def test_runner_recovery_env_set_passes_config_to_extract_pass2() -> None:
    """Cycle 73d — when WORKER_AI_ENTITY_RECOVERY_MODEL_REF is set, the
    runner threads the recovery config to extract_pass2 alongside any
    precision filter config."""
    from loreweave_extraction import EntityRecoveryConfig
    from app.runner import _extract_and_persist

    recovery_sentinel = EntityRecoveryConfig(model_ref="recov-model")

    captured: list[dict] = []

    async def _stub_extract_pass2(**kwargs):
        captured.append(kwargs)
        from loreweave_extraction import Pass2Candidates
        return Pass2Candidates()

    with patch("app.runner._PRECISION_FILTER_CONFIG", None), \
         patch("app.runner._ENTITY_RECOVERY_CONFIG", recovery_sentinel), \
         patch("app.runner.extract_pass2", new=_stub_extract_pass2):
        kc = _mock_knowledge_client()
        llm = _mock_llm_client()
        await _extract_and_persist(
            knowledge_client=kc,
            llm_client=llm,
            user_id=uuid4(),
            project_id=uuid4(),
            source_type="chapter",
            source_id="ch-recovery",
            job_id=uuid4(),
            model_ref="test-model",
            text="short passage",
        )

    assert len(captured) == 1
    assert captured[0].get("entity_recovery") is recovery_sentinel


# ─────────────────────────────────────────────────────────────────────
# Cycle 73f — runtime filter config reload (subscriber + setter)
# ─────────────────────────────────────────────────────────────────────


def test_set_precision_filter_config_swaps_module_cache():
    """Cycle 73f: setter atomically swaps module-level _PRECISION_FILTER_CONFIG.
    Subscriber path calls this on each Redis re-read."""
    from loreweave_extraction import PrecisionFilterConfig
    import app.runner as runner_module

    saved = runner_module._PRECISION_FILTER_CONFIG
    try:
        new_config = PrecisionFilterConfig(
            model_ref="cycle-73f-uuid",
            categories=("relation", "event"),
            partial_policy="drop",
        )
        returned = runner_module.set_precision_filter_config(new_config)
        assert returned is new_config
        assert runner_module._PRECISION_FILTER_CONFIG is new_config

        # Reverse: set to None disables filter.
        runner_module.set_precision_filter_config(None)
        assert runner_module._PRECISION_FILTER_CONFIG is None
    finally:
        # Restore original module state for downstream tests.
        runner_module.set_precision_filter_config(saved)


@pytest.mark.asyncio
async def test_consume_filter_reload_signal_reads_redis_and_swaps_cache(monkeypatch):
    """Cycle 73f: on pubsub signal, subscriber re-reads Redis key + swaps
    cache. Mock SDK's subscribe_filter_reload to fire one signal then exit."""
    from loreweave_extraction import PrecisionFilterConfig
    import app.runner as runner_module

    new_config = PrecisionFilterConfig(
        model_ref="from-redis-uuid",
        categories=("event",),
        partial_policy="drop",
    )

    async def fake_subscribe_filter_reload(redis_client, on_reload, **kwargs):
        # Simulate one pubsub signal arriving.
        await on_reload()
        # Exit cleanly (subscriber's outer loop accepts this).
        return

    async def fake_get_filter_config(redis_client):
        return new_config

    saved = runner_module._PRECISION_FILTER_CONFIG
    monkeypatch.setattr(
        "loreweave_extraction.subscribe_filter_reload",
        fake_subscribe_filter_reload,
    )
    monkeypatch.setattr(
        "loreweave_extraction.get_filter_config",
        fake_get_filter_config,
    )
    # Mock aioredis.from_url so we don't open a real Redis connection.
    fake_redis = MagicMock()
    fake_redis.aclose = AsyncMock()
    monkeypatch.setattr(
        "redis.asyncio.from_url",
        lambda *args, **kwargs: fake_redis,
    )

    try:
        await runner_module.consume_filter_reload_signal("redis://fake")
        # After the simulated signal, module cache should reflect new_config.
        assert runner_module._PRECISION_FILTER_CONFIG is new_config
    finally:
        runner_module.set_precision_filter_config(saved)


@pytest.mark.asyncio
async def test_consume_filter_reload_reverts_to_env_when_key_absent(monkeypatch):
    """Cycle 74b: pubsub re-read with the key absent (e.g. after a
    disable=true DELETE) reverts to ENV config, NOT None — the runtime path
    now matches startup hydrate. Closes the cycle-73f live-smoke cross-path
    divergence (runtime set None while a restart reloaded env config)."""
    from loreweave_extraction import PrecisionFilterConfig
    import app.runner as runner_module

    env_config = PrecisionFilterConfig(
        model_ref="env-revert-uuid",
        categories=("relation",),
        partial_policy="drop",
    )

    async def fake_subscribe_filter_reload(redis_client, on_reload, **kwargs):
        await on_reload()
        return

    async def fake_get_filter_config(redis_client):
        return None  # key absent

    saved = runner_module._PRECISION_FILTER_CONFIG
    monkeypatch.setattr(
        "loreweave_extraction.subscribe_filter_reload",
        fake_subscribe_filter_reload,
    )
    monkeypatch.setattr(
        "loreweave_extraction.get_filter_config",
        fake_get_filter_config,
    )
    monkeypatch.setattr(
        runner_module, "_load_precision_filter_config", lambda: env_config
    )
    fake_redis = MagicMock()
    fake_redis.aclose = AsyncMock()
    monkeypatch.setattr(
        "redis.asyncio.from_url",
        lambda *args, **kwargs: fake_redis,
    )

    try:
        await runner_module.consume_filter_reload_signal("redis://fake")
        # Reverted to env config, not None.
        assert runner_module._PRECISION_FILTER_CONFIG is env_config
    finally:
        runner_module.set_precision_filter_config(saved)


# Cycle 73f r3 H1 fold — worker startup hydrate (symmetric with KS).


@pytest.mark.asyncio
async def test_hydrate_precision_filter_config_seeds_cache_from_redis(monkeypatch):
    """r3 H1 fold: on worker startup, hydrate reads Redis key + swaps
    cache. Without this, worker restart silently reverts to env defaults
    even when Redis has an active ops-override."""
    from loreweave_extraction import PrecisionFilterConfig
    import app.runner as runner_module

    persisted_config = PrecisionFilterConfig(
        model_ref="persisted-uuid",
        categories=("relation",),
        partial_policy="drop",
    )

    async def fake_get_filter_config(redis_client):
        return persisted_config

    saved = runner_module._PRECISION_FILTER_CONFIG
    monkeypatch.setattr(
        "loreweave_extraction.get_filter_config",
        fake_get_filter_config,
    )
    fake_redis = MagicMock()
    fake_redis.aclose = AsyncMock()
    monkeypatch.setattr(
        "redis.asyncio.from_url",
        lambda *args, **kwargs: fake_redis,
    )

    try:
        await runner_module.hydrate_precision_filter_config_from_redis("redis://fake")
        # Worker cache reflects what Redis had.
        assert runner_module._PRECISION_FILTER_CONFIG is persisted_config
    finally:
        runner_module.set_precision_filter_config(saved)


@pytest.mark.asyncio
async def test_hydrate_precision_filter_config_leaves_cache_when_redis_empty(monkeypatch):
    """r3 H1 fold edge case: Redis key absent → hydrate is a no-op
    (cache stays at whatever env-load produced). Defends the worker
    from clobbering env defaults when Redis exists but key is empty."""
    import app.runner as runner_module

    async def fake_get_filter_config(redis_client):
        return None  # Redis empty / key absent

    saved = runner_module._PRECISION_FILTER_CONFIG
    monkeypatch.setattr(
        "loreweave_extraction.get_filter_config",
        fake_get_filter_config,
    )
    fake_redis = MagicMock()
    fake_redis.aclose = AsyncMock()
    monkeypatch.setattr(
        "redis.asyncio.from_url",
        lambda *args, **kwargs: fake_redis,
    )

    try:
        await runner_module.hydrate_precision_filter_config_from_redis("redis://fake")
        # Cache should remain at its pre-hydrate value (no clobber).
        assert runner_module._PRECISION_FILTER_CONFIG is saved
    finally:
        runner_module.set_precision_filter_config(saved)


# ─────────────────────────────────────────────────────────────────────
# Cycle 73h — Prometheus counter regression-lock
# (closes cycle 73f r3 M4 / cycle 73g log-only stopgap)
# ─────────────────────────────────────────────────────────────────────


def _worker_reload_counter_value(outcome: str) -> float:
    """Snapshot the worker-ai filter-reload counter for delta assertions."""
    from app.metrics import worker_ai_filter_reload_total
    return worker_ai_filter_reload_total.labels(outcome=outcome)._value.get()


@pytest.mark.asyncio
async def test_worker_filter_reload_counter_bumps_on_successful_re_read(monkeypatch):
    """Cycle 73h: pubsub-driven re-read success → bumps
    `worker_ai_filter_reload_total{outcome=applied}`."""
    from loreweave_extraction import PrecisionFilterConfig
    import app.runner as runner_module

    new_config = PrecisionFilterConfig(
        model_ref="counter-test-uuid",
        categories=("event",),
        partial_policy="drop",
    )

    async def fake_subscribe_filter_reload(redis_client, on_reload, **kwargs):
        await on_reload()
        return

    async def fake_get_filter_config(redis_client):
        return new_config

    saved = runner_module._PRECISION_FILTER_CONFIG
    pre_applied = _worker_reload_counter_value("applied")

    monkeypatch.setattr(
        "loreweave_extraction.subscribe_filter_reload",
        fake_subscribe_filter_reload,
    )
    monkeypatch.setattr(
        "loreweave_extraction.get_filter_config",
        fake_get_filter_config,
    )
    fake_redis = MagicMock()
    fake_redis.aclose = AsyncMock()
    monkeypatch.setattr(
        "redis.asyncio.from_url",
        lambda *args, **kwargs: fake_redis,
    )

    try:
        await runner_module.consume_filter_reload_signal("redis://fake")
        assert _worker_reload_counter_value("applied") == pre_applied + 1
    finally:
        runner_module.set_precision_filter_config(saved)


@pytest.mark.asyncio
async def test_worker_filter_reload_counter_bumps_failed_on_exception(monkeypatch):
    """Cycle 73h: pubsub re-read failure → bumps
    `worker_ai_filter_reload_total{outcome=failed}` (NOT applied)."""
    import app.runner as runner_module

    async def fake_subscribe_filter_reload(redis_client, on_reload, **kwargs):
        await on_reload()
        return

    async def fake_get_filter_config_raises(redis_client):
        raise RuntimeError("simulated redis read failure")

    saved = runner_module._PRECISION_FILTER_CONFIG
    pre_failed = _worker_reload_counter_value("failed")
    pre_applied = _worker_reload_counter_value("applied")

    monkeypatch.setattr(
        "loreweave_extraction.subscribe_filter_reload",
        fake_subscribe_filter_reload,
    )
    monkeypatch.setattr(
        "loreweave_extraction.get_filter_config",
        fake_get_filter_config_raises,
    )
    fake_redis = MagicMock()
    fake_redis.aclose = AsyncMock()
    monkeypatch.setattr(
        "redis.asyncio.from_url",
        lambda *args, **kwargs: fake_redis,
    )

    try:
        await runner_module.consume_filter_reload_signal("redis://fake")
        # Failed bumps; applied does NOT.
        assert _worker_reload_counter_value("failed") == pre_failed + 1
        assert _worker_reload_counter_value("applied") == pre_applied
    finally:
        runner_module.set_precision_filter_config(saved)


@pytest.mark.asyncio
async def test_worker_hydrate_counter_bumps_on_startup(monkeypatch):
    """Cycle 73h: startup hydrate (success) → bumps
    `worker_ai_filter_reload_total{outcome=startup}`. Distinct from
    `applied` so dashboards can attribute "where did the cache value
    come from"."""
    from loreweave_extraction import PrecisionFilterConfig
    import app.runner as runner_module

    persisted = PrecisionFilterConfig(
        model_ref="hydrate-counter-uuid",
        categories=("relation",),
        partial_policy="drop",
    )

    async def fake_get_filter_config(redis_client):
        return persisted

    saved = runner_module._PRECISION_FILTER_CONFIG
    pre_startup = _worker_reload_counter_value("startup")

    monkeypatch.setattr(
        "loreweave_extraction.get_filter_config",
        fake_get_filter_config,
    )
    fake_redis = MagicMock()
    fake_redis.aclose = AsyncMock()
    monkeypatch.setattr(
        "redis.asyncio.from_url",
        lambda *args, **kwargs: fake_redis,
    )

    try:
        await runner_module.hydrate_precision_filter_config_from_redis("redis://fake")
        assert _worker_reload_counter_value("startup") == pre_startup + 1
    finally:
        runner_module.set_precision_filter_config(saved)


def test_start_metrics_server_no_op_when_port_zero(caplog):
    """Cycle 73h: METRICS_PORT=0 disables the WSGI server cleanly
    (no port collision in tests / dev runs)."""
    import logging
    from app.metrics import start_metrics_server

    with caplog.at_level(logging.INFO, logger="app.metrics"):
        start_metrics_server(0)
    assert any(
        "metrics server disabled" in r.getMessage() for r in caplog.records
    )


# ── CM3c: _enumerate_chapters canon=published gate + is_last scope-guard ──


def _full_hierarchy(chapter_id: str) -> ChapterHierarchy:
    """A complete hierarchy (part + chapter_path set) so the P3 is_last
    branch in process_job is reached."""
    return ChapterHierarchy(
        book_id=str(uuid4()),
        book_path="book",
        book_title="The Book",
        part=HierarchyPart(id=str(uuid4()), path="book/part-1", index=1, title="P1"),
        chapter_id=chapter_id,
        chapter_path=f"book/part-1/{chapter_id}",
        chapter_index=1,
        chapter_title="C1",
        scenes=(HierarchyScene(id=str(uuid4()), path="s", index=1),),
        book_parts=(HierarchyPart(id=str(uuid4()), path="book/part-1", index=1, title="P1"),),
    )


@pytest.mark.asyncio
async def test_enumerate_chapters_requests_kg_indexed_and_skips_null_revision():
    """WS-0.6 (spec 2026-07-11-publish-independent-kg-indexing §3.5, red-team P0-2).

    _enumerate_chapters asks book-service for the chapters that are IN THE KNOWLEDGE
    GRAPH (``kg_indexed=True``), NOT the ones that happen to be published. This
    REPLACES the old CM3c canon=published gate.

    Publishing no longer decides KG membership: a draft can be explicitly indexed, and
    a kind='diary' book never publishes at all. Asking the publish question here would
    enumerate ZERO of a user's 50 indexed drafts, and the rebuild would report success
    having extracted nothing — the user's explicit act silently undone.

    The null-revision skip is KEPT and is load-bearing: with ``revision_id=None`` the
    per-chapter fetch falls back to the LIVE DRAFT text, which would extract unreviewed
    prose and break the pinned-revision guarantee.
    """
    book_id = uuid4()
    bc = AsyncMock(spec=BookClient)
    bc.list_chapters = AsyncMock(return_value=[
        # a DRAFT chapter the user explicitly indexed — the case the old gate dropped
        ChapterInfo(chapter_id="ch-1", title="C1", sort_order=1,
                    revision_id="rev-1", editorial_status="draft"),
        # in the graph but no pinned revision → must be skipped (with a WARNING),
        # never silently read from the live draft
        ChapterInfo(chapter_id="ch-2", title="C2", sort_order=2,
                    revision_id=None, editorial_status="published"),
    ])

    result = await _enumerate_chapters(bc, book_id, None)

    bc.list_chapters.assert_awaited_once_with(book_id, kg_indexed=True)
    assert [c.chapter_id for c in result] == ["ch-1"]  # null-revision dropped


@pytest.mark.asyncio
@patch("app.runner._extract_and_persist", new_callable=AsyncMock)
async def test_chapters_pending_drain_never_asserts_is_last(mock_extract_persist):
    """R2-BLOCK#1: the coalescing chapters_pending drain processes a SUBSET of
    re-published chapters → its tail is NOT the book tail → is_last_chapter_of_book
    must be False (else every incremental re-publish re-rolls the whole-book L0
    summary)."""
    mock_extract_persist.return_value = _ok_result()
    job = _job(scope="chapters_pending", embedding_dimension=1024)
    pool = _mock_pool()
    kc = _mock_knowledge_client()
    llm = _mock_llm_client()
    bc = _mock_book_client()
    bc.get_chapter_hierarchy = AsyncMock(return_value=_full_hierarchy("ch-1"))
    gc = _mock_glossary_client()

    with patch(
        "app.runner._enumerate_pending_chapters",
        AsyncMock(return_value=[ChapterInfo(
            chapter_id="ch-1", title="C1", sort_order=1,
            revision_id="rev-1", pending_id=uuid4(),
        )]),
    ):
        await process_job(pool, kc, llm, bc, gc, _mock_chat_client(), _mock_provider_client(), job)

    mock_extract_persist.assert_awaited_once()
    assert mock_extract_persist.await_args.kwargs["is_last_chapter_of_book"] is False


@pytest.mark.asyncio
@patch("app.runner._mark_pending_processed", new_callable=AsyncMock)
@patch("app.runner._extract_and_persist", new_callable=AsyncMock)
async def test_chapters_pending_dead_revision_marks_processed(mock_extract, mock_mark):
    """D-CM3B-DEAD-REVISION-LOOP: when a chapters_pending chapter's PINNED
    revision is permanently gone (get_chapter_revision_text → None), the drain
    MUST mark the pending row processed (revision-guarded) so it stops re-arming
    a fresh drain job every poll. Without this an orphaned pending row loops
    forever emitting skipped extraction_runs."""
    pending = uuid4()
    job = _job(scope="chapters_pending", embedding_dimension=1024)
    pool = _mock_pool()
    kc = _mock_knowledge_client()
    llm = _mock_llm_client()
    bc = _mock_book_client(text=None)  # pinned revision 404 → None (gone)
    gc = _mock_glossary_client()

    with patch(
        "app.runner._enumerate_pending_chapters",
        AsyncMock(return_value=[ChapterInfo(
            chapter_id="ch-dead", title="C", sort_order=1,
            revision_id="rev-gone", pending_id=pending,
        )]),
    ):
        await process_job(pool, kc, llm, bc, gc, _mock_chat_client(), _mock_provider_client(), job)

    # the dead chapter was NOT extracted, but its pending row was drained
    mock_extract.assert_not_awaited()
    mock_mark.assert_awaited_once()
    assert mock_mark.await_args.args[2] == pending          # pending_id
    assert mock_mark.await_args.kwargs["revision_id"] == "rev-gone"  # revision-guarded


@pytest.mark.asyncio
@patch("app.runner._extract_and_persist", new_callable=AsyncMock)
async def test_chapters_whole_book_asserts_is_last_on_tail(mock_extract_persist):
    """Counterpart: a genuine whole-book ('chapters') pass DOES assert is_last
    on the tail chapter — the guard must not over-suppress."""
    mock_extract_persist.return_value = _ok_result()
    job = _job(scope="chapters", embedding_dimension=1024)
    pool = _mock_pool()
    kc = _mock_knowledge_client()
    llm = _mock_llm_client()
    bc = _mock_book_client()  # single published chapter ch-1 (the tail)
    bc.get_chapter_hierarchy = AsyncMock(return_value=_full_hierarchy("ch-1"))
    gc = _mock_glossary_client()

    await process_job(pool, kc, llm, bc, gc, _mock_chat_client(), _mock_provider_client(), job)

    mock_extract_persist.assert_awaited_once()
    assert mock_extract_persist.await_args.kwargs["is_last_chapter_of_book"] is True


# ── FD-2: chat→KG auto-drain ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_ensure_chat_pending_jobs_creates_chat_scope_job():
    """FD-2: a project with unprocessed `aggregate_type='chat'` rows + a prior
    job (to reuse models from) gets a `scope='chat'` drain job created. Without
    this, chat turns would only extract on a manual full run."""
    user_id, project_id = uuid4(), uuid4()
    pool = AsyncMock()
    pool.fetch = AsyncMock(return_value=[{"user_id": user_id, "project_id": project_id}])
    pool.fetchrow = AsyncMock(return_value={
        "llm_model": "gpt-4o", "embedding_model": "bge-m3",
        "max_spend_usd": Decimal("5.00"),
    })
    pool.execute = AsyncMock()

    created = await _ensure_chat_pending_jobs(pool)

    assert created == 1
    pool.execute.assert_awaited_once()
    sql, *args = pool.execute.await_args.args
    assert "INSERT INTO extraction_jobs" in sql
    assert "'chat'" in sql              # scope literal in the INSERT
    assert args[0] == user_id and args[1] == project_id
    assert args[2] == "gpt-4o"          # reuses the last job's model (no placeholder)


@pytest.mark.asyncio
async def test_ensure_chat_pending_jobs_skips_project_with_no_prior_job():
    """A project with queued chat rows but NO prior job is skipped — a manual
    /extraction/start bootstraps the models first (a placeholder model_ref would
    break extraction). No INSERT issued."""
    pool = AsyncMock()
    pool.fetch = AsyncMock(return_value=[{"user_id": uuid4(), "project_id": uuid4()}])
    pool.fetchrow = AsyncMock(return_value=None)   # no prior job
    pool.execute = AsyncMock()

    created = await _ensure_chat_pending_jobs(pool)

    assert created == 0
    pool.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_poll_and_run_invokes_chat_drainer():
    """poll_and_run must arm the chat drainer each cycle (alongside chapters),
    else chat pending rows never auto-drain."""
    pool = _mock_pool()
    pool.fetch = AsyncMock(return_value=[])  # no pending rows, no running jobs
    kc, llm = _mock_knowledge_client(), _mock_llm_client()
    bc, gc = _mock_book_client(), _mock_glossary_client()

    with patch("app.runner._ensure_chat_pending_jobs", new_callable=AsyncMock) as mock_chat_drain, \
         patch("app.runner._ensure_chapters_pending_jobs", new_callable=AsyncMock):
        await poll_and_run(pool, kc, llm, bc, gc, _mock_chat_client(), _mock_provider_client())

    mock_chat_drain.assert_awaited_once_with(pool)


# ── FD-27: zero-output guard + reasoning-model advisory ──────────────


@pytest.mark.parametrize("name,expected", [
    ("o1", True), ("o3-mini", True), ("O1-preview", True), ("o4-mini", True),
    ("qwen/qwen3.6-35b-a3b", True), ("deepseek-r1-distill", True), ("qwq-32b", True),
    ("glm-z1-9b", True), ("some-thinking-model", True), ("magistral-small", True),
    ("gpt-4o", False), ("gpt-4.1", False), ("qwen2.5-72b-instruct", False),
    ("llama-3.3-70b", False), ("claude-opus-4-8", False), ("mistral-large", False),
    (None, False), ("", False),
])
def test_is_likely_reasoning_model(name, expected):
    """FD-27 heuristic: o-series + known reasoning families flagged; chat models
    (incl. the gpt-4o trap, where 'o' is a suffix) not."""
    assert _is_likely_reasoning_model(name) is expected


@pytest.mark.asyncio
@patch("app.runner.extract_pass2", new_callable=AsyncMock)
async def test_extract_and_persist_warns_on_zero_output(mock_extract):
    """FD-27 symptom guard: substantive input + empty candidates → counter +1."""
    from loreweave_extraction.pass2 import Pass2Candidates
    from app.runner import _extract_and_persist
    from app.metrics import worker_ai_extraction_zero_output_total

    mock_extract.return_value = Pass2Candidates(entities=[], relations=[], events=[], facts=[])
    kc = AsyncMock(spec=KnowledgeClient)
    kc.persist_pass2 = AsyncMock(return_value=_ok_result())
    before = worker_ai_extraction_zero_output_total.labels(source_type="chapter")._value.get()

    await _extract_and_persist(
        knowledge_client=kc, llm_client=_mock_llm_client(),
        user_id=uuid4(), project_id=uuid4(),
        source_type="chapter", source_id="ch-1", job_id=uuid4(),
        model_ref="qwen3-test", text="x" * 100,  # ≥ 40 chars
    )

    after = worker_ai_extraction_zero_output_total.labels(source_type="chapter")._value.get()
    assert after == before + 1


@pytest.mark.asyncio
@patch("app.runner.extract_pass2", new_callable=AsyncMock)
async def test_extract_and_persist_no_warn_on_short_or_nonempty(mock_extract):
    """FD-27: short input (below threshold) OR non-empty candidates → no counter bump."""
    from loreweave_extraction.pass2 import Pass2Candidates
    from app.runner import _extract_and_persist
    from app.metrics import worker_ai_extraction_zero_output_total

    kc = AsyncMock(spec=KnowledgeClient)
    kc.persist_pass2 = AsyncMock(return_value=_ok_result())
    before = worker_ai_extraction_zero_output_total.labels(source_type="chapter")._value.get()

    # short input + empty → no warn (trivial input legitimately yields nothing)
    mock_extract.return_value = Pass2Candidates(entities=[], relations=[], events=[], facts=[])
    await _extract_and_persist(
        knowledge_client=kc, llm_client=_mock_llm_client(),
        user_id=uuid4(), project_id=uuid4(),
        source_type="chapter", source_id="ch-1", job_id=uuid4(),
        model_ref="m", text="short",
    )
    # substantive input + NON-empty candidates → no warn
    mock_extract.return_value = Pass2Candidates(
        entities=[_entity_candidate("Kai")], relations=[], events=[], facts=[],
    )
    await _extract_and_persist(
        knowledge_client=kc, llm_client=_mock_llm_client(),
        user_id=uuid4(), project_id=uuid4(),
        source_type="chapter", source_id="ch-2", job_id=uuid4(),
        model_ref="m", text="x" * 100,
    )

    after = worker_ai_extraction_zero_output_total.labels(source_type="chapter")._value.get()
    assert after == before


@pytest.mark.asyncio
@patch("app.runner._extract_and_persist", new_callable=AsyncMock)
async def test_process_job_reasoning_model_advisory(mock_extract):
    """FD-27 pre-check: a reasoning-model name → advisory counter +1; the
    provider lookup is awaited once per job."""
    from app.metrics import worker_ai_extraction_reasoning_model_advised_total
    mock_extract.return_value = _ok_result()
    pool = _mock_pool()
    kc, llm = _mock_knowledge_client(), _mock_llm_client()
    bc, gc = _mock_book_client(), _mock_glossary_client()
    job = _job(scope="chapters", embedding_dimension=1024)
    pc = _mock_provider_client(model_name="qwen/qwen3.6-35b-a3b")
    before = worker_ai_extraction_reasoning_model_advised_total._value.get()

    await process_job(pool, kc, llm, bc, gc, _mock_chat_client(), pc, job)

    after = worker_ai_extraction_reasoning_model_advised_total._value.get()
    assert after == before + 1
    pc.get_model_name.assert_awaited_once()


@pytest.mark.asyncio
@patch("app.runner._extract_and_persist", new_callable=AsyncMock)
async def test_process_job_no_advisory_for_nonreasoning_model(mock_extract):
    """FD-27: a non-reasoning model name (or None lookup) → no advisory bump."""
    from app.metrics import worker_ai_extraction_reasoning_model_advised_total
    mock_extract.return_value = _ok_result()
    pool = _mock_pool()
    kc, llm = _mock_knowledge_client(), _mock_llm_client()
    bc, gc = _mock_book_client(), _mock_glossary_client()
    job = _job(scope="chapters", embedding_dimension=1024)
    pc = _mock_provider_client(model_name="gpt-4o")
    before = worker_ai_extraction_reasoning_model_advised_total._value.get()

    await process_job(pool, kc, llm, bc, gc, _mock_chat_client(), pc, job)

    after = worker_ai_extraction_reasoning_model_advised_total._value.get()
    assert after == before


@pytest.mark.asyncio
@patch("app.runner._extract_and_persist", new_callable=AsyncMock)
async def test_process_job_no_advisory_for_glossary_sync_scope(mock_extract):
    """FD-27 /review-impl MED: glossary_sync runs NO LLM extraction → the
    reasoning advisory must not fire (and must not even resolve the model)."""
    from app.metrics import worker_ai_extraction_reasoning_model_advised_total
    mock_extract.return_value = _ok_result()
    pool = _mock_pool()
    kc = _mock_knowledge_client()
    kc.glossary_sync_entity = AsyncMock(
        side_effect=lambda **kwargs: _glossary_sync_ok(kwargs["glossary_entity_id"]),
    )
    bc = _mock_book_client()
    gc = _mock_glossary_client(pages=[([_glossary_entity("e1", "Alice")], None)])
    job = _job(scope="glossary_sync")
    pc = _mock_provider_client(model_name="qwen/qwen3.6-35b-a3b")  # would fire if not gated
    before = worker_ai_extraction_reasoning_model_advised_total._value.get()

    await process_job(pool, kc, _mock_llm_client(), bc, gc, _mock_chat_client(), pc, job)

    after = worker_ai_extraction_reasoning_model_advised_total._value.get()
    assert after == before
    pc.get_model_name.assert_not_awaited()  # gated before the lookup
