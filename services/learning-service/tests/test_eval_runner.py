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


# M1 (LLM re-arch Phase 3): _maybe_judge now STARTS a decoupled judge
# (start_extraction_judge → durable job-row + terminal-event consumer) instead of an
# inline run_online_judge + persist. The gating logic is unchanged; the tests assert
# whether the START is invoked. Folding/persisting is covered by the SM tests.


async def test_judge_runs_when_opted_in(monkeypatch):
    _enable_judge(monkeypatch)
    start = AsyncMock(return_value=True)
    monkeypatch.setattr("app.judges.decoupled_judge.start_extraction_judge", start)
    runner = _runner()
    monkeypatch.setattr(runner, "_ensure_judge_sdk", AsyncMock(return_value=object()))
    await runner._maybe_judge(
        {"judge_panel_id": uuid.uuid4()}, _run(),
        # inline override still requires the consent flag (/review-impl LOW#2)
        {"save_raw_extraction": True,
         "items": {"entity": [{}]}, "source_text": "Alice fell down the hole."},
    )
    start.assert_awaited_once()
    assert start.call_args.kwargs["source_text"] == "Alice fell down the hole."
    assert start.call_args.kwargs["items_by_category"] == {"entity": [{}]}


async def test_judge_bills_run_owner_not_operator(monkeypatch):
    # D-EVAL-JUDGE-PER-USER: the BYOK judge bills the extraction OWNER
    # (run["user_id"]), not the operator's env-configured id ("u").
    _enable_judge(monkeypatch)
    start = AsyncMock(return_value=True)
    monkeypatch.setattr("app.judges.decoupled_judge.start_extraction_judge", start)
    runner = _runner()
    monkeypatch.setattr(runner, "_ensure_judge_sdk", AsyncMock(return_value=object()))
    run = _run()
    await runner._maybe_judge(
        {"judge_panel_id": uuid.uuid4()}, run,
        {"save_raw_extraction": True, "items": {"entity": [{}]}, "source_text": "x."},
    )
    assert start.call_args.kwargs["billing_user_id"] == str(run["user_id"])
    assert start.call_args.kwargs["billing_user_id"] != "u"
    assert start.call_args.kwargs["owner_user_id"] == run["user_id"]


async def test_judge_inline_items_skipped_without_consent_flag(monkeypatch):
    """/review-impl LOW#2 regression-lock: inline items WITHOUT
    save_raw_extraction are NOT judged — consent gate governs the inline
    path too (defense-in-depth for redact-by-default)."""
    _enable_judge(monkeypatch)
    start = AsyncMock()
    monkeypatch.setattr("app.judges.decoupled_judge.start_extraction_judge", start)
    runner = _runner()
    await runner._maybe_judge(
        {"judge_panel_id": uuid.uuid4()}, _run(),
        {"items": {"entity": [{}]}, "source_text": "x"},  # no save_raw_extraction
    )
    start.assert_not_awaited()


async def test_judge_skipped_without_items(monkeypatch):
    _enable_judge(monkeypatch)
    start = AsyncMock()
    monkeypatch.setattr("app.judges.decoupled_judge.start_extraction_judge", start)
    runner = _runner()
    await runner._maybe_judge({"judge_panel_id": uuid.uuid4()}, _run(), {"items": None, "source_text": None})
    start.assert_not_awaited()  # no items/source -> structural-only


async def test_judge_skipped_when_disabled(monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "online_judge_enabled", False)
    start = AsyncMock()
    monkeypatch.setattr("app.judges.decoupled_judge.start_extraction_judge", start)
    runner = _runner()
    await runner._maybe_judge(
        {"judge_panel_id": uuid.uuid4()}, _run(),
        {"items": {"entity": [{}]}, "source_text": "x"},
    )
    start.assert_not_awaited()


async def test_judge_skipped_without_panel(monkeypatch):
    _enable_judge(monkeypatch)
    start = AsyncMock()
    monkeypatch.setattr("app.judges.decoupled_judge.start_extraction_judge", start)
    runner = _runner()
    await runner._maybe_judge(
        {"judge_panel_id": None}, _run(),
        {"items": {"entity": [{}]}, "source_text": "x"},
    )
    start.assert_not_awaited()  # rule has no judge panel -> structural-only


# ── Q4b-feed — fetch path (production: items+source NOT inline) ────────


async def test_judge_fetches_sample_for_opted_in_run(monkeypatch):
    """Production path: the event carries NO items (redact-by-default) but
    save_raw_extraction=true → fetch the sample from knowledge-service, judge."""
    _enable_judge(monkeypatch)
    start = AsyncMock(return_value=True)
    monkeypatch.setattr("app.judges.decoupled_judge.start_extraction_judge", start)
    runner = _runner()
    monkeypatch.setattr(runner, "_ensure_judge_sdk", AsyncMock(return_value=object()))
    fake_kc = AsyncMock()
    fake_kc.fetch_run_sample = AsyncMock(return_value={
        "items": {"entity": [{"name": "Alice", "kind": "person"}]},
        "source_text": "Alice fell down the hole.",
    })
    monkeypatch.setattr(runner, "_ensure_knowledge_client", AsyncMock(return_value=fake_kc))
    await runner._maybe_judge(
        {"judge_panel_id": uuid.uuid4()}, _run(),
        {"save_raw_extraction": True},  # no inline items/source
    )
    fake_kc.fetch_run_sample.assert_awaited_once()
    start.assert_awaited_once()
    # judged against the FETCHED items+source
    assert start.call_args.kwargs["source_text"] == "Alice fell down the hole."


async def test_judge_skipped_when_not_opted_in_no_fetch(monkeypatch):
    """save_raw_extraction falsy + no inline → NO knowledge call at all."""
    _enable_judge(monkeypatch)
    start = AsyncMock()
    monkeypatch.setattr("app.judges.decoupled_judge.start_extraction_judge", start)
    runner = _runner()
    fake_kc = AsyncMock()
    fake_kc.fetch_run_sample = AsyncMock()
    monkeypatch.setattr(runner, "_ensure_knowledge_client", AsyncMock(return_value=fake_kc))
    await runner._maybe_judge({"judge_panel_id": uuid.uuid4()}, _run(), {})
    fake_kc.fetch_run_sample.assert_not_awaited()  # never fetched
    start.assert_not_awaited()


async def test_judge_skipped_when_sample_404(monkeypatch):
    """Opted-in but knowledge returns None (404/pruned) → structural-only."""
    _enable_judge(monkeypatch)
    start = AsyncMock()
    monkeypatch.setattr("app.judges.decoupled_judge.start_extraction_judge", start)
    runner = _runner()
    fake_kc = AsyncMock()
    fake_kc.fetch_run_sample = AsyncMock(return_value=None)
    monkeypatch.setattr(runner, "_ensure_knowledge_client", AsyncMock(return_value=fake_kc))
    await runner._maybe_judge(
        {"judge_panel_id": uuid.uuid4()}, _run(), {"save_raw_extraction": True},
    )
    fake_kc.fetch_run_sample.assert_awaited_once()
    start.assert_not_awaited()
