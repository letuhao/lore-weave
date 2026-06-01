"""Q4 — eval-runner consumer decision logic (sample / persist / always-ack).

The Redis loop itself is not unit-tested; the per-message decision (_handle /
_maybe_eval) is, with the module-level deps monkeypatched.
"""

from __future__ import annotations

import json
import uuid
from unittest.mock import AsyncMock

import pytest

from app.events.eval_runner import EvalRunner


def _fields(event_type="knowledge.extraction_run_completed", payload=None, outbox_id="ob-1"):
    return {
        "event_type": event_type,
        "payload": json.dumps(payload or {}),
        "outbox_id": outbox_id,
    }


def _run_payload(metrics=None):
    return {
        "run_id": str(uuid.uuid4()),
        "user_id": str(uuid.uuid4()),
        "metrics": metrics if metrics is not None else {"entities_merged": 5, "relations_created": 3, "events_merged": 2},
    }


def _runner():
    return EvalRunner("redis://x", AsyncMock())


async def test_sampled_in_persists_with_completeness(monkeypatch):
    runner = _runner()
    monkeypatch.setattr(
        "app.events.eval_runner.get_active_rule",
        AsyncMock(return_value={"sampling_rate": 1.0, "judge_panel_id": None}),
    )
    persist = AsyncMock(return_value=uuid.uuid4())
    monkeypatch.setattr("app.events.eval_runner.persist_online_eval", persist)

    await runner._maybe_eval(_fields(payload=_run_payload()))
    persist.assert_awaited_once()
    assert persist.await_args.kwargs["completeness"] == 1.0


async def test_sampled_out_does_not_persist(monkeypatch):
    runner = _runner()
    monkeypatch.setattr(
        "app.events.eval_runner.get_active_rule",
        AsyncMock(return_value={"sampling_rate": 0.0}),
    )
    persist = AsyncMock()
    monkeypatch.setattr("app.events.eval_runner.persist_online_eval", persist)

    await runner._maybe_eval(_fields(payload=_run_payload()))
    persist.assert_not_awaited()


async def test_no_active_rule_skips(monkeypatch):
    runner = _runner()
    monkeypatch.setattr("app.events.eval_runner.get_active_rule", AsyncMock(return_value=None))
    persist = AsyncMock()
    monkeypatch.setattr("app.events.eval_runner.persist_online_eval", persist)

    await runner._maybe_eval(_fields(payload=_run_payload()))
    persist.assert_not_awaited()


async def test_handle_always_acks_non_run_event(monkeypatch):
    runner = _runner()
    r = AsyncMock()
    await runner._handle(r, "1-0", _fields(event_type="knowledge.entity_corrected"))
    r.xack.assert_awaited_once()  # not a run event -> no eval, but ack


async def test_handle_acks_even_on_error(monkeypatch):
    runner = _runner()
    monkeypatch.setattr(
        "app.events.eval_runner.get_active_rule", AsyncMock(side_effect=RuntimeError("boom"))
    )
    r = AsyncMock()
    await runner._handle(r, "1-0", _fields(payload=_run_payload()))
    r.xack.assert_awaited_once()  # best-effort: ack despite the handler error
