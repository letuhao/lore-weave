"""P3 — tests for summary_processor (D3 + D9 + M4 + M5 + D10 cache)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest

from app.db.repositories.level_summaries import LevelSummary, UpsertOutcome
from app.jobs.summary_enqueue import SummarizeMessage
from app.jobs.summary_processor import (
    REENQUEUE_BACKOFF_S,
    RETRY_BUDGET,
    SummaryProcessorDeps,
    _DefensiveCheckFailed,
    _load_scene_leaf_texts,
    process_summarize_message,
)


_BOOK_ID = str(uuid4())
_CHAPTER_ID = str(uuid4())


# ── FD-3: _load_scene_leaf_texts loads REAL prose from book-service (not paths) ──

def _book_client(scenes, draft=None):
    c = MagicMock()
    c.list_scenes_by_chapter = AsyncMock(return_value=scenes)
    c.get_chapter_draft_text = AsyncMock(return_value=draft)
    return c


@pytest.mark.asyncio
async def test_load_scene_leaf_texts_returns_real_prose_ordered():
    # A P1-decomposed chapter → the ordered scene leaf_texts (REAL prose), NOT the
    # Neo4j `s.path` strings the old stub returned (FD-3 regression).
    scenes = [{"leaf_text": "Kael stood at the gate."}, {"leaf_text": "Mira counted the rations."}]
    client = _book_client(scenes)
    with patch("app.jobs.summary_processor.get_book_client", return_value=client):
        out = await _load_scene_leaf_texts(UUID(_BOOK_ID), UUID(_CHAPTER_ID))
    assert out == ["Kael stood at the gate.", "Mira counted the rations."]
    client.list_scenes_by_chapter.assert_awaited_once()
    client.get_chapter_draft_text.assert_not_awaited()  # scenes had text → no fallback


@pytest.mark.asyncio
async def test_load_scene_leaf_texts_legacy_chapter_falls_back_to_draft():
    # Legacy chapter (empty scenes) → D8 fallback to the chapter draft as one unit
    # (PO: legacy chapters get a real summary, not abandoned).
    client = _book_client([], draft="The whole chapter as one draft.")
    with patch("app.jobs.summary_processor.get_book_client", return_value=client):
        out = await _load_scene_leaf_texts(UUID(_BOOK_ID), UUID(_CHAPTER_ID))
    assert out == ["The whole chapter as one draft."]
    client.get_chapter_draft_text.assert_awaited_once()


@pytest.mark.asyncio
async def test_load_scene_leaf_texts_scenes_without_text_fall_back():
    # Scenes exist but carry no usable leaf_text → still fall back to the draft.
    client = _book_client([{"leaf_text": ""}, {"leaf_text": "   "}], draft="Draft body.")
    with patch("app.jobs.summary_processor.get_book_client", return_value=client):
        out = await _load_scene_leaf_texts(UUID(_BOOK_ID), UUID(_CHAPTER_ID))
    assert out == ["Draft body."]


@pytest.mark.asyncio
async def test_load_scene_leaf_texts_transport_failure_raises_transient():
    # None = book-service transport failure → raise (transient) so the caller
    # re-enqueues; NEVER summarize on missing prose.
    client = _book_client(None)
    with patch("app.jobs.summary_processor.get_book_client", return_value=client):
        with pytest.raises(_DefensiveCheckFailed):
            await _load_scene_leaf_texts(UUID(_BOOK_ID), UUID(_CHAPTER_ID))


@pytest.mark.asyncio
async def test_load_scene_leaf_texts_truly_empty_returns_empty():
    # No scenes AND no draft → [] (the caller raises → skipped, not crash).
    client = _book_client([], draft=None)
    with patch("app.jobs.summary_processor.get_book_client", return_value=client):
        out = await _load_scene_leaf_texts(UUID(_BOOK_ID), UUID(_CHAPTER_ID))
    assert out == []
_PART_ID = str(uuid4())
_USER_ID = str(uuid4())
_PROJECT_ID = str(uuid4())
_JOB_ID = str(uuid4())


def _msg(level="chapter", node_id=_CHAPTER_ID, retried_n=0, retry_at_epoch=0.0):
    return SummarizeMessage(
        level=level,  # type: ignore[arg-type]
        node_path=f"book/part-1/{level}-1",
        node_id=node_id,
        book_id=_BOOK_ID,
        user_id=_USER_ID,
        project_id=_PROJECT_ID,
        job_id=_JOB_ID,
        model_ref="model-uuid",
        embedding_model_uuid="embed-uuid",
        embedding_dimension=1024,
        retry_at_epoch=retry_at_epoch,
        retried_n=retried_n,
    )


def _deps(
    *,
    cache_hit_summary: LevelSummary | None = None,
    upsert_outcome: UpsertOutcome | None = None,
    scene_texts: list[str] | None = None,
    entity_names: list[str] | None = None,
    chapter_summaries: list[LevelSummary] | None = None,
    part_summaries: list[LevelSummary] | None = None,
    expected_chapter_count: int = 0,
    expected_part_count: int = 0,
    summary_text: str = "A meaningful 2-sentence summary of the level content.",
) -> SummaryProcessorDeps:
    # Mock repo via patching at module level — return value depends on test.
    deps = SummaryProcessorDeps(
        knowledge_pool=MagicMock(),
        neo4j_session=MagicMock(),
        llm_client=MagicMock(),
        embedding_client=MagicMock(),
        summary_enqueue=AsyncMock(return_value="msg-id-1"),
    )
    # Wire neo4j_session.run to async-iterable mocks.
    return deps


async def test_retry_budget_exhaustion_returns_skipped_no_llm_call():
    """M4: when retried_n >= RETRY_BUDGET, abandon without LLM call."""
    msg = _msg(retried_n=RETRY_BUDGET)
    deps = _deps()
    result = await process_summarize_message(msg, deps)
    assert result.skipped_retry_exhausted is True
    assert result.cache_hit is False
    assert result.re_enqueued is False
    assert result.summary_id is None
    deps.summary_enqueue.assert_not_called()


@patch("app.jobs.summary_processor.asyncio.sleep", new_callable=AsyncMock)
@patch("app.jobs.summary_processor.LevelSummariesRepo")
@patch("app.jobs.summary_processor._load_scene_leaf_texts", new_callable=AsyncMock)
@patch("app.jobs.summary_processor._load_top_entities_for_chapter", new_callable=AsyncMock)
@patch("app.jobs.summary_processor.summarize_level", new_callable=AsyncMock)
async def test_retry_at_in_future_sleeps_then_processes_without_burning_budget(
    mock_summarize, mock_entities, mock_scenes, mock_repo_cls, mock_sleep,
):
    """D-P3-BOOK-SUMMARY-PERSIST-AUDIT regression-lock.

    When a message arrives with retry_at_epoch in the future, the processor
    must SLEEP in-place (not re-enqueue + increment retried_n). The earlier
    impl re-enqueued, which Redis Streams delivered immediately, burning
    the entire RETRY_BUDGET in milliseconds and abandoning higher-level
    summaries before their children settled.
    """
    from loreweave_extraction import LevelSummary as ExtLevelSummary

    mock_scenes.return_value = ["s1", "s2"]
    mock_entities.return_value = []
    mock_summarize.return_value = ExtLevelSummary(
        summary_text="A summary text long enough to satisfy validation.",
        token_usage={},
    )
    repo = MagicMock()
    repo.find_cached = AsyncMock(return_value=None)
    upsert_id = uuid4()
    repo.upsert_summary = AsyncMock(return_value=UpsertOutcome(
        cache_hit=False, race_winner=True, summary_id=upsert_id,
    ))
    mock_repo_cls.return_value = repo

    # retry_at_epoch 30s in the future — should sleep, not re-enqueue.
    import time as _time
    msg = _msg(retried_n=1, retry_at_epoch=_time.time() + 30)
    deps = _deps()
    deps.embedding_client = MagicMock()
    deps.embedding_client.embed = AsyncMock(return_value=[0.1] * 1024)
    deps.neo4j_session.run = AsyncMock()

    result = await process_summarize_message(msg, deps)

    # Must have slept (mocked) — not re-enqueued.
    mock_sleep.assert_awaited_once()
    sleep_arg = mock_sleep.await_args.args[0]
    assert 0 < sleep_arg <= 30  # roughly the requested delay (or cap)
    # Budget MUST NOT be burned: no XADD of a re-enqueued message.
    deps.summary_enqueue.assert_not_called()
    # Processing proceeded normally → upsert happened.
    assert result.re_enqueued is False
    assert result.summary_id == upsert_id


@patch("app.jobs.summary_processor.asyncio.sleep", new_callable=AsyncMock)
@patch("app.jobs.summary_processor.LevelSummariesRepo")
@patch("app.jobs.summary_processor._load_scene_leaf_texts", new_callable=AsyncMock)
@patch("app.jobs.summary_processor._load_top_entities_for_chapter", new_callable=AsyncMock)
@patch("app.jobs.summary_processor.summarize_level", new_callable=AsyncMock)
async def test_retry_at_absurd_future_sleep_capped_at_max(
    mock_summarize, mock_entities, mock_scenes, mock_repo_cls, mock_sleep,
):
    """Clock-skew defense: retry_at_epoch far in the future (decades) must
    be capped at MAX_INLINE_RETRY_SLEEP_S (120s) — never sleep longer
    regardless of what the message claims."""
    from loreweave_extraction import LevelSummary as ExtLevelSummary
    from app.jobs.summary_processor import MAX_INLINE_RETRY_SLEEP_S

    mock_scenes.return_value = ["s1"]
    mock_entities.return_value = []
    mock_summarize.return_value = ExtLevelSummary(
        summary_text="A summary text long enough to satisfy validation.",
        token_usage={},
    )
    repo = MagicMock()
    repo.find_cached = AsyncMock(return_value=None)
    repo.upsert_summary = AsyncMock(return_value=UpsertOutcome(
        cache_hit=False, race_winner=True, summary_id=uuid4(),
    ))
    mock_repo_cls.return_value = repo

    msg = _msg(retried_n=0, retry_at_epoch=9999999999.0)  # year 2286
    deps = _deps()
    deps.embedding_client = MagicMock()
    deps.embedding_client.embed = AsyncMock(return_value=[0.1] * 1024)
    deps.neo4j_session.run = AsyncMock()

    await process_summarize_message(msg, deps)

    mock_sleep.assert_awaited_once()
    assert mock_sleep.await_args.args[0] == MAX_INLINE_RETRY_SLEEP_S


@patch("app.jobs.summary_processor.LevelSummariesRepo")
@patch("app.jobs.summary_processor._load_scene_leaf_texts", new_callable=AsyncMock)
@patch("app.jobs.summary_processor._load_top_entities_for_chapter", new_callable=AsyncMock)
@patch("app.jobs.summary_processor.summarize_level", new_callable=AsyncMock)
async def test_cache_hit_skips_llm_and_neo4j_write(
    mock_summarize, mock_entities, mock_scenes, mock_repo_cls,
):
    """D10 cache: existing row with matching md5 → no LLM, no write."""
    mock_scenes.return_value = ["Scene 1 text.", "Scene 2 text."]
    mock_entities.return_value = ["Alice"]
    repo = MagicMock()
    cached_id = uuid4()
    repo.find_cached = AsyncMock(return_value=LevelSummary(
        id=cached_id, level="chapter", level_id=UUID(_CHAPTER_ID),
        book_id=UUID(_BOOK_ID),
        summary_text="cached summary",
        summary_input_md5="abc",  # value compared against fresh computation; in cache hit, repo
                                  # find_cached has already done the md5 check internally.
        embedding_dimension=1024,
        embedding_model_uuid="embed-uuid",
    ))
    repo.upsert_summary = AsyncMock()
    mock_repo_cls.return_value = repo

    msg = _msg()
    deps = _deps()
    result = await process_summarize_message(msg, deps)
    assert result.cache_hit is True
    assert result.summary_id == cached_id
    mock_summarize.assert_not_called()
    repo.upsert_summary.assert_not_called()


@patch("app.jobs.summary_processor.LevelSummariesRepo")
@patch("app.jobs.summary_processor._load_scene_leaf_texts", new_callable=AsyncMock)
@patch("app.jobs.summary_processor._load_top_entities_for_chapter", new_callable=AsyncMock)
@patch("app.jobs.summary_processor.summarize_level", new_callable=AsyncMock)
async def test_cache_miss_calls_llm_then_upsert_then_neo4j_write(
    mock_summarize, mock_entities, mock_scenes, mock_repo_cls,
):
    """Cache miss → summarize_level + upsert + Neo4j write."""
    from loreweave_extraction import LevelSummary as ExtLevelSummary

    mock_scenes.return_value = ["Scene 1 text.", "Scene 2 text."]
    mock_entities.return_value = ["Alice", "Bob"]
    mock_summarize.return_value = ExtLevelSummary(
        summary_text="Alice and Bob navigate the trial together.",
        token_usage={"input": 100, "output": 30},
    )
    repo = MagicMock()
    repo.find_cached = AsyncMock(return_value=None)  # cache miss
    upsert_id = uuid4()
    repo.upsert_summary = AsyncMock(return_value=UpsertOutcome(
        cache_hit=False, race_winner=True, summary_id=upsert_id,
    ))
    mock_repo_cls.return_value = repo

    deps = _deps()
    deps.embedding_client = MagicMock()
    deps.embedding_client.embed = AsyncMock(return_value=[0.1] * 1024)
    deps.neo4j_session.run = AsyncMock()

    msg = _msg()
    result = await process_summarize_message(msg, deps)

    assert result.cache_hit is False
    assert result.race_winner is True
    assert result.summary_id == upsert_id
    mock_summarize.assert_awaited_once()
    repo.upsert_summary.assert_awaited_once()
    deps.embedding_client.embed.assert_awaited_once()


@patch("app.jobs.summary_processor.LevelSummariesRepo")
@patch("app.jobs.summary_processor._load_scene_leaf_texts", new_callable=AsyncMock)
@patch("app.jobs.summary_processor._load_top_entities_for_chapter", new_callable=AsyncMock)
@patch("app.jobs.summary_processor.summarize_level", new_callable=AsyncMock)
async def test_race_loser_skips_neo4j_write(
    mock_summarize, mock_entities, mock_scenes, mock_repo_cls,
):
    """M5: when upsert returns race_winner=False, skip Neo4j write (the
    race winner already wrote the vector index)."""
    from loreweave_extraction import LevelSummary as ExtLevelSummary

    mock_scenes.return_value = ["s1"]
    mock_entities.return_value = []
    mock_summarize.return_value = ExtLevelSummary(
        summary_text="A summary text long enough to satisfy validation.",
        token_usage={},
    )
    repo = MagicMock()
    repo.find_cached = AsyncMock(return_value=None)
    repo.upsert_summary = AsyncMock(return_value=UpsertOutcome(
        cache_hit=True, race_winner=False, summary_id=uuid4(),
    ))
    mock_repo_cls.return_value = repo

    deps = _deps()
    deps.embedding_client = MagicMock()
    deps.embedding_client.embed = AsyncMock(return_value=[0.1])
    deps.neo4j_session.run = AsyncMock()
    msg = _msg()
    result = await process_summarize_message(msg, deps)
    assert result.race_winner is False
    # Neo4j .run() NOT called for the SET summary_text/embedding statement.
    # (It IS called for ensure_summary_indexes + _load_scene_leaf_texts mocks,
    # but those are bypassed via patch.)
    # Check: SET cypher was not invoked.
    cypher_calls = [c.args[0] for c in deps.neo4j_session.run.call_args_list]
    assert not any("SET n.summary_text" in c for c in cypher_calls)


async def test_reenqueue_backoff_progression():
    """M4 backoff: 30s/60s/120s exponential. Tested by retried_n indexing."""
    assert REENQUEUE_BACKOFF_S == (30, 60, 120)
    # First retry uses index 0 = 30s; second uses 1 = 60s; clamp at last index.
    # Test retry_at_in_future_reenqueues_without_processing already exercises
    # the re-enqueue path; here just confirm the constants.


@patch("app.jobs.summary_processor._count_expected_chapter_children", new_callable=AsyncMock)
@patch("app.jobs.summary_processor._load_top_entities_for_part", new_callable=AsyncMock)
@patch("app.jobs.summary_processor.LevelSummariesRepo")
async def test_part_level_defensive_check_reenqueues_when_children_missing(
    mock_repo_cls, mock_entities, mock_count,
):
    """D9: part summary defers when expected_children > actual_summary_rows."""
    mock_count.return_value = 5  # part expects 5 chapter summaries
    repo = MagicMock()
    repo.find_cached = AsyncMock(return_value=None)
    repo.list_by_book = AsyncMock(return_value=[])  # 0 chapter summaries present
    mock_repo_cls.return_value = repo

    msg = _msg(level="part", node_id=_PART_ID)
    deps = _deps()
    deps.neo4j_session.run = AsyncMock()
    result = await process_summarize_message(msg, deps)
    assert result.re_enqueued is True
    deps.summary_enqueue.assert_awaited_once()
