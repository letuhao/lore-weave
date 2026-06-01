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


# ── Q4b — judge-path gating ───────────────────────────────────────────


def _run():
    return {"run_id": str(uuid.uuid4()), "user_id": uuid.uuid4(),
            "project_id": None, "book_id": None, "config_hash": None}


def _enable_judge(monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "online_judge_enabled", True)
    monkeypatch.setattr(settings, "online_judge_model_ref", "jm")
    monkeypatch.setattr(settings, "online_judge_user_id", "u")


async def test_judge_runs_when_opted_in(monkeypatch):
    _enable_judge(monkeypatch)
    rj = AsyncMock(return_value={"overall_precision": 0.8})
    pj = AsyncMock(return_value=uuid.uuid4())
    monkeypatch.setattr("app.db.online_judge.run_online_judge", rj)
    monkeypatch.setattr("app.db.online_judge.persist_online_judge", pj)
    runner = _runner()
    monkeypatch.setattr(runner, "_ensure_judge_client", AsyncMock(return_value=object()))
    await runner._maybe_judge(
        {"judge_panel_id": uuid.uuid4()}, _run(),
        {"items": {"entity": [{}]}, "source_text": "Alice fell down the hole."},
    )
    rj.assert_awaited_once()
    pj.assert_awaited_once()


async def test_judge_skipped_without_items(monkeypatch):
    _enable_judge(monkeypatch)
    rj = AsyncMock()
    monkeypatch.setattr("app.db.online_judge.run_online_judge", rj)
    runner = _runner()
    await runner._maybe_judge({"judge_panel_id": uuid.uuid4()}, _run(), {"items": None, "source_text": None})
    rj.assert_not_awaited()  # no items/source -> structural-only


async def test_judge_skipped_when_disabled(monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "online_judge_enabled", False)
    rj = AsyncMock()
    monkeypatch.setattr("app.db.online_judge.run_online_judge", rj)
    runner = _runner()
    await runner._maybe_judge(
        {"judge_panel_id": uuid.uuid4()}, _run(),
        {"items": {"entity": [{}]}, "source_text": "x"},
    )
    rj.assert_not_awaited()


async def test_judge_skipped_without_panel(monkeypatch):
    _enable_judge(monkeypatch)
    rj = AsyncMock()
    monkeypatch.setattr("app.db.online_judge.run_online_judge", rj)
    runner = _runner()
    await runner._maybe_judge(
        {"judge_panel_id": None}, _run(),
        {"items": {"entity": [{}]}, "source_text": "x"},
    )
    rj.assert_not_awaited()  # rule has no judge panel -> structural-only
