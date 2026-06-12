"""T0.4 (M0): translation-pipeline instrumentation (W10)."""
import logging

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.metrics import record_stage, timed


def test_record_stage_emits_structured_line(caplog):
    caplog.set_level(logging.INFO, logger="translation.metrics")
    record_stage("translation.chapter", pipeline="v2", status="completed", in_tokens=10)
    msgs = [r.getMessage() for r in caplog.records]
    assert any(
        "stage=translation.chapter" in m and "status=completed" in m and "pipeline=v2" in m
        for m in msgs
    )


def test_timed_emits_duration_and_ok_outcome(caplog):
    caplog.set_level(logging.INFO, logger="translation.metrics")
    with timed("translation.batch", batch_idx=0):
        pass
    msgs = [r.getMessage() for r in caplog.records]
    assert any(
        "stage=translation.batch" in m and "outcome=ok" in m and "duration_s=" in m
        for m in msgs
    )


def test_timed_marks_error_outcome_on_exception(caplog):
    caplog.set_level(logging.INFO, logger="translation.metrics")
    with pytest.raises(ValueError):
        with timed("translation.batch"):
            raise ValueError("boom")
    assert any("outcome=error" in r.getMessage() for r in caplog.records)


@pytest.mark.asyncio
async def test_chapter_worker_emits_completed_metric():
    """A successfully translated chapter emits a translation.chapter / completed event."""
    from tests.test_chapter_worker import _make_pool, _chapter_msg, _patched_book_http

    pool, _ = _make_pool()
    msg = _chapter_msg()

    with patch("app.workers.chapter_worker.httpx.AsyncClient") as mock_cls, \
         patch("app.workers.chapter_worker.translate_chapter",
               new_callable=AsyncMock, return_value=("Body.", 10, 8)), \
         patch("app.workers.chapter_worker.record_stage") as rec:
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=_patched_book_http())
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        from app.workers.chapter_worker import handle_chapter_message
        await handle_chapter_message(msg, pool, AsyncMock(), MagicMock(), retry_count=0)

    stages = [c.args[0] for c in rec.call_args_list]
    statuses = [c.kwargs.get("status") for c in rec.call_args_list]
    assert "translation.chapter" in stages
    assert "completed" in statuses
