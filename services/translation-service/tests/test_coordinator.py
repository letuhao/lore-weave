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


class _TxCM:
    async def __aenter__(self):
        return None

    async def __aexit__(self, *_):
        return False


def _make_pool(owner_user_id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"):
    db = AsyncMock()
    db.execute = AsyncMock()
    # P1: the running transition is now `UPDATE ... RETURNING owner_user_id`
    # (fetchrow) + emit_job_event inside `async with db.transaction()`.
    from uuid import UUID
    db.fetchrow = AsyncMock(return_value={"owner_user_id": UUID(owner_user_id)})
    db.transaction = MagicMock(return_value=_TxCM())
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
async def test_coordinator_marks_job_running(monkeypatch):
    """Coordinator must UPDATE job status to 'running' before fanning out chapters.

    P1: the running UPDATE is now a fetchrow (RETURNING owner_user_id) inside a tx.
    """
    monkeypatch.setattr("app.workers.coordinator.emit_job_event", AsyncMock())
    pool, db = _make_pool()
    from app.workers.coordinator import handle_job_message
    await handle_job_message(_job_msg(), pool, AsyncMock(), AsyncMock())

    db.fetchrow.assert_called_once()
    sql = db.fetchrow.call_args.args[0]
    assert "running" in sql
    assert "started_at" in sql


@pytest.mark.asyncio
async def test_coordinator_passes_job_id_to_update(monkeypatch):
    """The running UPDATE must target the correct job_id."""
    monkeypatch.setattr("app.workers.coordinator.emit_job_event", AsyncMock())
    pool, db = _make_pool()
    msg = _job_msg()
    from app.workers.coordinator import handle_job_message
    await handle_job_message(msg, pool, AsyncMock(), AsyncMock())

    args = db.fetchrow.call_args.args
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
        "pipeline_version",
    }
    assert required.issubset(body.keys())


@pytest.mark.asyncio
async def test_coordinator_forwards_pipeline_version():
    """T0.6 regression (review-impl MED-1): the flag must survive the job→chapter
    fan-out. If it doesn't, a 'v3' job silently downgrades to 'v2' at the worker
    (which defaults an absent field to 'v2'), and no other test would catch it."""
    pool, _ = _make_pool()
    publish = AsyncMock()
    msg = {**_job_msg([str(uuid4())]), "pipeline_version": "v3"}
    from app.workers.coordinator import handle_job_message
    await handle_job_message(msg, pool, publish, AsyncMock())

    assert publish.call_args.args[1]["pipeline_version"] == "v3"


@pytest.mark.asyncio
async def test_coordinator_defaults_pipeline_version_when_absent():
    """A legacy job message without the flag fans out as 'v2' (back-compat)."""
    pool, _ = _make_pool()
    publish = AsyncMock()
    from app.workers.coordinator import handle_job_message
    await handle_job_message(_job_msg([str(uuid4())]), pool, publish, AsyncMock())

    assert publish.call_args.args[1]["pipeline_version"] == "v2"


@pytest.mark.asyncio
async def test_coordinator_forwards_qa_config():
    """config-plumbing: qa_depth / max_qa_rounds / verifier_model must survive the
    job→chapter fan-out (else a 'thorough' job silently runs 'standard' defaults)."""
    pool, _ = _make_pool()
    publish = AsyncMock()
    vref = str(uuid4())
    msg = {**_job_msg([str(uuid4())]), "qa_depth": "thorough", "max_qa_rounds": 4,
           "verifier_model_source": "platform_model", "verifier_model_ref": vref}
    from app.workers.coordinator import handle_job_message
    await handle_job_message(msg, pool, publish, AsyncMock())

    body = publish.call_args.args[1]
    assert body["qa_depth"] == "thorough" and body["max_qa_rounds"] == 4
    assert body["verifier_model_source"] == "platform_model"
    assert body["verifier_model_ref"] == vref


@pytest.mark.asyncio
async def test_coordinator_defaults_qa_config_when_absent():
    """A legacy job message without QA config fans out as standard defaults."""
    pool, _ = _make_pool()
    publish = AsyncMock()
    from app.workers.coordinator import handle_job_message
    await handle_job_message(_job_msg([str(uuid4())]), pool, publish, AsyncMock())

    body = publish.call_args.args[1]
    assert body["qa_depth"] == "standard" and body["max_qa_rounds"] == 2
    assert body["verifier_model_ref"] is None


@pytest.mark.asyncio
async def test_coordinator_forwards_campaign_id():
    """S4a: campaign_id must survive the job→chapter fan-out, or the chapter worker
    never binds it and the provider job_meta loses attribution. (LOW-5 hop guard.)"""
    pool, _ = _make_pool()
    publish = AsyncMock()
    camp = str(uuid4())
    msg = {**_job_msg([str(uuid4())]), "campaign_id": camp}
    from app.workers.coordinator import handle_job_message
    await handle_job_message(msg, pool, publish, AsyncMock())
    assert publish.call_args.args[1]["campaign_id"] == camp


@pytest.mark.asyncio
async def test_coordinator_campaign_id_none_when_absent():
    """A non-campaign job fans out campaign_id=None (no attribution) — no behavior change."""
    pool, _ = _make_pool()
    publish = AsyncMock()
    from app.workers.coordinator import handle_job_message
    await handle_job_message(_job_msg([str(uuid4())]), pool, publish, AsyncMock())
    assert publish.call_args.args[1]["campaign_id"] is None


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
