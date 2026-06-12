"""Q4b-feed — worker-ai run-sample projection + write."""

from __future__ import annotations

import json
import uuid
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.runner import JobRow
from app.sample_emit import (
    persist_run_sample,
    persist_run_sample_best_effort,
    project_items,
)


def _job(**over) -> JobRow:
    d = dict(
        job_id=uuid.uuid4(), user_id=uuid.uuid4(), project_id=uuid.uuid4(),
        scope="chapters", scope_range=None, status="running",
        llm_model="m", embedding_model="bge-m3", max_spend_usd=Decimal("10"),
        items_total=5, items_processed=0, current_cursor=None,
        cost_spent_usd=Decimal("0"),
    )
    d.update(over)
    return JobRow(**d)


def _candidates():
    return SimpleNamespace(
        entities=[
            SimpleNamespace(name="Alice", kind="person", confidence=0.9, canonical_id="x"),
        ],
        relations=[
            SimpleNamespace(subject="Alice", predicate="fell_into", object="hole",
                            polarity="positive", modality="actual", confidence=0.8),
        ],
        events=[
            SimpleNamespace(summary="Alice fell down the hole",
                            participants=["Alice"], confidence=0.7, event_id="e1"),
        ],
        facts=[SimpleNamespace(text="ignored")],
    )


# ── project_items ─────────────────────────────────────────────────────


def test_project_items_maps_judge_shape_only():
    items = project_items(_candidates())
    assert items["entity"] == [{"name": "Alice", "kind": "person"}]
    assert items["relation"] == [
        {"subject": "Alice", "predicate": "fell_into", "object": "hole", "polarity": "positive"}
    ]
    assert items["event"] == [{"summary": "Alice fell down the hole", "participants": ["Alice"]}]
    # confidence / canonical_id / modality / event_id dropped (redact-minimized)
    assert "confidence" not in items["entity"][0]
    # fact category excluded (online judge has no fact category)
    assert "fact" not in items


def test_project_items_empty_candidates():
    empty = SimpleNamespace(entities=[], relations=[], events=[], facts=[])
    assert project_items(empty) == {"entity": [], "relation": [], "event": []}


# ── persist_run_sample ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_persist_inserts_with_conflict_guard_and_json_items():
    ex = AsyncMock()
    run_id = str(uuid.uuid4())
    book_id = uuid.uuid4()
    job = _job()
    await persist_run_sample(
        ex, run_id=run_id, user_id=job.user_id, project_id=job.project_id,
        book_id=book_id, config_hash="cfg",
        candidates=_candidates(), source_text="Alice fell down the hole.",
    )
    sql, params = ex.execute.await_args.args[0], ex.execute.await_args.args
    assert "INSERT INTO extraction_run_samples" in sql
    assert "ON CONFLICT (run_id) DO NOTHING" in sql
    assert params[1] == uuid.UUID(run_id)        # $1 run_id coerced to UUID
    assert params[2] == job.user_id              # $2 user_id
    assert params[4] == book_id                  # $4 book_id coerced to UUID
    items = json.loads(params[6])                # $6 items_jsonb
    assert items["entity"][0]["name"] == "Alice"
    assert params[7] == "Alice fell down the hole."  # $7 source_text


@pytest.mark.asyncio
async def test_persist_null_book_id_ok():
    ex = AsyncMock()
    job = _job()
    await persist_run_sample(
        ex, run_id=str(uuid.uuid4()), user_id=job.user_id, project_id=job.project_id,
        book_id=None, config_hash=None,
        candidates=_candidates(), source_text="x",
    )
    assert ex.execute.await_args.args[4] is None  # book_id NULL


@pytest.mark.asyncio
async def test_best_effort_swallows_executor_failure():
    ex = AsyncMock()
    ex.execute = AsyncMock(side_effect=RuntimeError("db down"))
    # must NOT raise
    job = _job()
    await persist_run_sample_best_effort(
        ex, run_id=str(uuid.uuid4()), user_id=job.user_id, project_id=job.project_id,
        book_id=None, config_hash=None,
        candidates=_candidates(), source_text="x",
    )
