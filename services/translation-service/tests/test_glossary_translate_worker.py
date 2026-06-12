"""Unit tests for glossary_translate_worker pagination and entity_ids filter."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.workers.glossary_translate_worker import _run_job


class _AcquireCM:
    def __init__(self, db):
        self._db = db

    async def __aenter__(self):
        return self._db

    async def __aexit__(self, *_):
        pass


def _make_pool(job_status="running", owner_user_id=None):
    db = AsyncMock()
    db.execute = AsyncMock()
    owner = owner_user_id or uuid4()
    db.fetchval = AsyncMock(return_value=owner)
    db.fetchrow = AsyncMock(return_value={"status": job_status})
    pool = MagicMock()
    pool.acquire = MagicMock(return_value=_AcquireCM(db))
    return pool, db


def _entity(eid: str, name: str = "Test") -> dict:
    return {
        "entity_id": eid,
        "display_name": name,
        "kind_code": "character",
        "attributes": [
            {
                "attr_value_id": f"{eid}-name",
                "code": "name",
                "field_type": "text",
                "original_value": name,
            },
        ],
    }


def _llm_ok():
    job = MagicMock()
    job.status = "completed"
    job.result = {
        "messages": [{"content": '{"name": "Translated"}'}],
        "usage": {"input_tokens": 10, "output_tokens": 5},
    }
    return job


@pytest.mark.asyncio
async def test_missing_only_always_fetches_offset_zero():
    """missing_only shrinks candidate set — worker must not advance offset."""
    job_id = uuid4()
    book_id = str(uuid4())
    e1, e2 = str(uuid4()), str(uuid4())
    fetch_calls: list[int] = []

    async def fake_fetch(book_id, target_language, *, overwrite_mode, limit, offset, entity_ids=None):
        fetch_calls.append(offset)
        if len(fetch_calls) == 1:
            return {"total": 2, "items": [_entity(e1)]}
        if len(fetch_calls) == 2:
            return {"total": 1, "items": [_entity(e2)]}
        return {"total": 0, "items": []}

    apply_calls: list[str] = []

    async def fake_apply(book_id, target_language, items):
        apply_calls.extend(i["entity_id"] for i in items)
        return {"translated": len(items), "skipped_verified": 0, "skipped_empty": 0, "failed": []}

    pool, _ = _make_pool()
    llm = AsyncMock()
    llm.submit_and_wait = AsyncMock(return_value=_llm_ok())
    publish = AsyncMock()

    msg = {
        "book_id": book_id,
        "target_language": "vi",
        "source_language": "zh",
        "model_source": "user_model",
        "model_ref": str(uuid4()),
        "overwrite_mode": "missing_only",
        "metadata": {},
    }

    with (
        patch(
            "app.workers.glossary_translate_worker.fetch_translation_candidates",
            new=AsyncMock(side_effect=fake_fetch),
        ),
        patch(
            "app.workers.glossary_translate_worker.post_apply_translations",
            new=AsyncMock(side_effect=fake_apply),
        ),
    ):
        await _run_job(msg, job_id, "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa", pool, publish, llm)

    assert all(o == 0 for o in fetch_calls)
    assert len(fetch_calls) >= 2
    assert set(apply_calls) == {e1, e2}
    assert llm.submit_and_wait.await_count == 2


@pytest.mark.asyncio
async def test_missing_only_skips_already_processed_entity():
    """Entity still in candidate set after partial translate must not re-LLM."""
    job_id = uuid4()
    book_id = str(uuid4())
    e1 = str(uuid4())
    same_entity = _entity(e1)
    fetch_calls = 0

    async def fake_fetch(book_id, target_language, *, overwrite_mode, limit, offset, entity_ids=None):
        nonlocal fetch_calls
        fetch_calls += 1
        if fetch_calls == 1:
            return {"total": 1, "items": [same_entity]}
        # Simulate shrink: still returns same entity (partial attrs remain)
        return {"total": 1, "items": [same_entity]}

    llm_calls = 0

    async def fake_llm(**kwargs):
        nonlocal llm_calls
        llm_calls += 1
        return _llm_ok()

    pool, _ = _make_pool()
    llm = AsyncMock()
    llm.submit_and_wait = AsyncMock(side_effect=fake_llm)
    publish = AsyncMock()

    msg = {
        "book_id": book_id,
        "target_language": "vi",
        "source_language": "zh",
        "model_source": "user_model",
        "model_ref": str(uuid4()),
        "overwrite_mode": "missing_only",
        "metadata": {},
    }

    with (
        patch(
            "app.workers.glossary_translate_worker.fetch_translation_candidates",
            new=AsyncMock(side_effect=fake_fetch),
        ),
        patch(
            "app.workers.glossary_translate_worker.post_apply_translations",
            new=AsyncMock(return_value={"translated": 1, "skipped_verified": 0, "skipped_empty": 0, "failed": []}),
        ),
    ):
        await _run_job(msg, job_id, "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa", pool, publish, llm)

    assert llm_calls == 1
    assert fetch_calls == 2


@pytest.mark.asyncio
async def test_entity_ids_passed_to_fetch():
    job_id = uuid4()
    book_id = str(uuid4())
    filter_ids = [str(uuid4()), str(uuid4())]
    seen_entity_ids = []

    async def fake_fetch(book_id, target_language, *, overwrite_mode, limit, offset, entity_ids=None):
        seen_entity_ids.append(entity_ids)
        return {"total": 0, "items": []}

    pool, _ = _make_pool()
    llm = AsyncMock()
    publish = AsyncMock()

    msg = {
        "book_id": book_id,
        "target_language": "vi",
        "source_language": "zh",
        "model_source": "user_model",
        "model_ref": str(uuid4()),
        "overwrite_mode": "missing_only",
        "metadata": {"entity_ids": filter_ids},
    }

    with (
        patch(
            "app.workers.glossary_translate_worker.fetch_translation_candidates",
            new=AsyncMock(side_effect=fake_fetch),
        ),
        patch(
            "app.workers.glossary_translate_worker.post_apply_translations",
            new=AsyncMock(
                return_value={"translated": 0, "skipped_verified": 0, "skipped_empty": 0, "failed": []},
            ),
        ),
    ):
        await _run_job(msg, job_id, "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa", pool, publish, llm)

    assert seen_entity_ids == [filter_ids]


@pytest.mark.asyncio
async def test_thinking_enabled_passes_llm_kwargs():
    job_id = uuid4()
    book_id = str(uuid4())
    e1 = str(uuid4())
    llm_inputs: list[dict] = []

    async def fake_fetch(*_a, **_kw):
        return {"total": 1, "items": [_entity(e1)]}

    async def capture_llm(**kwargs):
        llm_inputs.append(kwargs.get("input") or {})
        return _llm_ok()

    pool, _ = _make_pool()
    llm = AsyncMock()
    llm.submit_and_wait = AsyncMock(side_effect=capture_llm)
    publish = AsyncMock()

    msg = {
        "book_id": book_id,
        "target_language": "vi",
        "source_language": "zh",
        "model_source": "user_model",
        "model_ref": str(uuid4()),
        "overwrite_mode": "missing_only",
        "thinking_enabled": True,
        "metadata": {},
    }

    with (
        patch(
            "app.workers.glossary_translate_worker.fetch_translation_candidates",
            new=AsyncMock(side_effect=fake_fetch),
        ),
        patch(
            "app.workers.glossary_translate_worker.post_apply_translations",
            new=AsyncMock(
                return_value={"translated": 1, "skipped_verified": 0, "skipped_empty": 0, "failed": []},
            ),
        ),
    ):
        await _run_job(msg, job_id, "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa", pool, publish, llm)

    assert llm_inputs[0]["reasoning_effort"] == "medium"
    assert llm_inputs[0]["chat_template_kwargs"]["enable_thinking"] is True
