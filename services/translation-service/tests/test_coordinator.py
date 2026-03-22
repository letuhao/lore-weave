"""
Unit tests for the coordinator worker — Plan §4.1.

Coordinator receives one job message, marks job running, publishes
one chapter message per chapter (fan-out), and emits job.status_changed(running).
Expected duration: < 1 second. Must never call external services.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4


# ── Helpers ───────────────────────────────────────────────────────────────────

class _AcquireCM:
    def __init__(self, db):
        self._db = db

    async def __aenter__(self):
        return self._db

    async def __aexit__(self, *_):
        pass


def _make_pool():
    db = AsyncMock()
    db.execute = AsyncMock()
    pool = MagicMock()
    pool.acquire = MagicMock(return_value=_AcquireCM(db))
    return pool, db


CHAPTER_IDS = [str(uuid4()), str(uuid4()), str(uuid4())]
USER_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"


def _job_msg(chapter_ids=None):
    return {
        "job_id":          str(uuid4()),
        "user_id":         USER_ID,
        "book_id":         str(uuid4()),
        "chapter_ids":     chapter_ids or CHAPTER_IDS,
        "model_source":    "user_model",
        "model_ref":       str(uuid4()),
        "system_prompt":   "Translate faithfully.",
        "user_prompt_tpl": "Translate: {chapter_text}",
        "target_language": "vi",
    }


# ── Status update ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_coordinator_marks_job_running():
    """Coordinator must UPDATE job status to 'running' before fanning out chapters."""
    pool, db = _make_pool()
    from app.workers.coordinator import handle_job_message
    await handle_job_message(_job_msg(), pool, AsyncMock(), AsyncMock())

    db.execute.assert_called_once()
    sql = db.execute.call_args.args[0]
    assert "running" in sql
    assert "started_at" in sql


@pytest.mark.asyncio
async def test_coordinator_passes_job_id_to_update():
    """The running UPDATE must target the correct job_id."""
    pool, db = _make_pool()
    msg = _job_msg()
    from app.workers.coordinator import handle_job_message
    await handle_job_message(msg, pool, AsyncMock(), AsyncMock())

    args = db.execute.call_args.args
    from uuid import UUID
    assert UUID(msg["job_id"]) in args


# ── Fan-out ───────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_coordinator_publishes_one_message_per_chapter():
    """Fan-out: exactly N publish() calls for N chapter_ids — Plan §4.1."""
    pool, _ = _make_pool()
    publish = AsyncMock()
    from app.workers.coordinator import handle_job_message
    await handle_job_message(_job_msg(CHAPTER_IDS), pool, publish, AsyncMock())

    assert publish.call_count == len(CHAPTER_IDS)


@pytest.mark.asyncio
async def test_coordinator_all_chapter_messages_use_correct_routing_key():
    """Every chapter publish must use routing_key='translation.chapter'."""
    pool, _ = _make_pool()
    publish = AsyncMock()
    from app.workers.coordinator import handle_job_message
    await handle_job_message(_job_msg(CHAPTER_IDS), pool, publish, AsyncMock())

    for call in publish.call_args_list:
        assert call.args[0] == "translation.chapter"


@pytest.mark.asyncio
async def test_coordinator_chapter_message_contains_required_fields():
    """Each chapter message must be self-contained — Plan §3.4."""
    pool, _ = _make_pool()
    publish = AsyncMock()
    chapter_id = str(uuid4())
    msg = _job_msg([chapter_id])

    from app.workers.coordinator import handle_job_message
    await handle_job_message(msg, pool, publish, AsyncMock())

    body = publish.call_args.args[1]
    required = {
        "job_id", "chapter_id", "chapter_index", "total_chapters",
        "book_id", "user_id", "model_source", "model_ref",
        "system_prompt", "user_prompt_tpl", "target_language",
    }
    assert required.issubset(body.keys())


@pytest.mark.asyncio
async def test_coordinator_chapter_id_matches_input():
    pool, _ = _make_pool()
    publish = AsyncMock()
    chapter_id = str(uuid4())
    from app.workers.coordinator import handle_job_message
    await handle_job_message(_job_msg([chapter_id]), pool, publish, AsyncMock())

    body = publish.call_args.args[1]
    assert body["chapter_id"] == chapter_id


@pytest.mark.asyncio
async def test_coordinator_chapter_index_is_zero_based_sequential():
    """chapter_index must be 0, 1, 2, ... matching position in chapter_ids list."""
    pool, _ = _make_pool()
    publish = AsyncMock()
    from app.workers.coordinator import handle_job_message
    await handle_job_message(_job_msg(CHAPTER_IDS), pool, publish, AsyncMock())

    indices = [c.args[1]["chapter_index"] for c in publish.call_args_list]
    assert indices == list(range(len(CHAPTER_IDS)))


@pytest.mark.asyncio
async def test_coordinator_total_chapters_matches_input_length():
    pool, _ = _make_pool()
    publish = AsyncMock()
    from app.workers.coordinator import handle_job_message
    await handle_job_message(_job_msg(CHAPTER_IDS), pool, publish, AsyncMock())

    for call in publish.call_args_list:
        assert call.args[1]["total_chapters"] == len(CHAPTER_IDS)


# ── Event emission ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_coordinator_emits_job_status_changed_running():
    """After fan-out, coordinator must emit job.status_changed(running) — Plan §4.1."""
    pool, _ = _make_pool()
    publish_event = AsyncMock()
    msg = _job_msg()
    from app.workers.coordinator import handle_job_message
    await handle_job_message(msg, pool, AsyncMock(), publish_event)

    publish_event.assert_called_once()
    body = publish_event.call_args.args[1]
    assert body["event"] == "job.status_changed"
    assert body["payload"]["status"] == "running"


@pytest.mark.asyncio
async def test_coordinator_event_user_id_matches_message():
    pool, _ = _make_pool()
    publish_event = AsyncMock()
    msg = _job_msg()
    from app.workers.coordinator import handle_job_message
    await handle_job_message(msg, pool, AsyncMock(), publish_event)

    event_user_id = publish_event.call_args.args[0]
    assert event_user_id == USER_ID


@pytest.mark.asyncio
async def test_coordinator_event_initial_counters_are_zero():
    """Running event must have completed_chapters=0 and failed_chapters=0."""
    pool, _ = _make_pool()
    publish_event = AsyncMock()
    from app.workers.coordinator import handle_job_message
    await handle_job_message(_job_msg(), pool, AsyncMock(), publish_event)

    payload = publish_event.call_args.args[1]["payload"]
    assert payload["completed_chapters"] == 0
    assert payload["failed_chapters"] == 0


@pytest.mark.asyncio
async def test_coordinator_single_chapter_job():
    """Edge case: job with exactly one chapter produces exactly one publish call."""
    pool, _ = _make_pool()
    publish = AsyncMock()
    from app.workers.coordinator import handle_job_message
    await handle_job_message(_job_msg([str(uuid4())]), pool, publish, AsyncMock())

    assert publish.call_count == 1
    assert publish.call_args.args[1]["chapter_index"] == 0
    assert publish.call_args.args[1]["total_chapters"] == 1
