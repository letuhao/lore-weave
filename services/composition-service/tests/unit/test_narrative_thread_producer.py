"""FD-1 / narrative_thread S2 — detect_and_update_threads producer unit tests.

Fakes the LLM (submit_and_wait → a gateway-shaped job result) + the repo, to
verify without a live stack: opens new promises, pays a GIVEN open id, dedups a
same-fold re-open, bounds at max_open, ignores invented paid ids, and degrades
to a no-op (NEVER raises) on LLM error / malformed JSON / empty text.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.db.models import NarrativeThread
from app.engine.narrative_thread import detect_and_update_threads


class _FakeLLM:
    """submit_and_wait → a gateway-shaped Job (content at result.messages[0])."""
    def __init__(self, content: str, *, raise_error: bool = False, status: str = "completed"):
        self._content = content
        self._raise = raise_error
        self._status = status

    async def submit_and_wait(self, **kwargs):
        if self._raise:
            from loreweave_llm.errors import LLMError
            raise LLMError("boom")
        return SimpleNamespace(
            status=self._status,
            result={"messages": [{"content": self._content}]},
        )


class _FakeRepo:
    def __init__(self, open_threads=None):
        self._open = open_threads or []
        self.opened: list[dict] = []
        self.paid: list[tuple[str, str]] = []

    async def list_open(self, project_id, *, limit=100):
        return self._open

    async def open_thread(self, project_id, *, created_by=None, kind, summary,
                          opened_at_node=None, trigger="", **kw):
        self.opened.append({"kind": kind, "summary": summary})
        return None

    async def update_status(self, project_id, thread_id, *, status, payoff_node=None):
        self.paid.append((str(thread_id), status))
        return SimpleNamespace(id=thread_id)  # non-None = matched/updated


def _thread(summary: str, kind: str = "promise") -> NarrativeThread:
    return NarrativeThread(
        id=uuid4(), created_by=uuid4(), project_id=uuid4(),
        kind=kind, status="open", summary=summary,
    )


def _llm(opened, paid):
    return _FakeLLM(json.dumps({"opened": opened, "paid": paid}))


async def _run(llm, repo, **over):
    kw = dict(
        user_id=uuid4(), project_id=uuid4(), scene_text="A scene happened.",
        opened_at_node=uuid4(), drafter_source="user_model", drafter_ref="m",
    )
    kw.update(over)
    return await detect_and_update_threads(llm, repo, **kw)


@pytest.mark.asyncio
async def test_opens_new_and_pays_given_open_id():
    existing = _thread("the locked door")
    repo = _FakeRepo([existing])
    llm = _llm(
        opened=[{"kind": "foreshadow", "summary": "a black spear glints on the wall"}],
        paid=[str(existing.id)],
    )
    res = await _run(llm, repo)
    assert res.opened == 1 and res.paid == 1
    assert repo.opened[0]["kind"] == "foreshadow"
    assert repo.paid[0] == (str(existing.id), "paid")


@pytest.mark.asyncio
async def test_dedup_skips_same_fold_reopen():
    existing = _thread("The Locked   Door")
    repo = _FakeRepo([existing])
    llm = _llm(opened=[{"kind": "promise", "summary": "the locked door"}], paid=[])
    res = await _run(llm, repo)
    assert res.opened == 0 and repo.opened == []


@pytest.mark.asyncio
async def test_bounds_max_open():
    repo = _FakeRepo([])
    llm = _llm(opened=[{"kind": "promise", "summary": f"promise {i}"} for i in range(10)], paid=[])
    res = await _run(llm, repo, max_open=3)
    assert res.opened == 3 and len(repo.opened) == 3


@pytest.mark.asyncio
async def test_ignores_paid_id_not_in_open_set():
    repo = _FakeRepo([])  # nothing open
    llm = _llm(opened=[], paid=[str(uuid4())])  # invented id
    res = await _run(llm, repo)
    assert res.paid == 0 and repo.paid == []


@pytest.mark.asyncio
async def test_drops_unknown_kind():
    repo = _FakeRepo([])
    llm = _llm(opened=[{"kind": "vibe", "summary": "not a real kind"}], paid=[])
    res = await _run(llm, repo)
    assert res.opened == 0 and repo.opened == []


@pytest.mark.asyncio
async def test_degrades_on_llm_error():
    repo = _FakeRepo([])
    res = await _run(_FakeLLM("", raise_error=True), repo)
    assert res.status == "degraded" and repo.opened == [] and repo.paid == []


@pytest.mark.asyncio
async def test_malformed_json_no_writes():
    repo = _FakeRepo([])
    res = await _run(_FakeLLM("not json at all"), repo)
    assert res.opened == 0 and res.paid == 0 and repo.opened == []


@pytest.mark.asyncio
async def test_empty_text_is_noop():
    repo = _FakeRepo([])
    res = await _run(_llm([], []), repo, scene_text="   ")
    assert res.status == "empty" and repo.opened == []


# ── wiring (review-impl MED#1): the gated, best-effort call site in engine.py ──

from unittest.mock import AsyncMock, patch  # noqa: E402


def _work(enabled):
    return SimpleNamespace(settings={"narrative_thread_enabled": enabled})


async def _call_wiring(work):
    from app.routers import engine as engine_mod
    return engine_mod, await engine_mod._maybe_detect_narrative_threads(
        work, llm=object(), repo=object(), user_id=uuid4(), project_id=uuid4(),
        scene_text="a scene", opened_at_node=None,
        model_source="user_model", model_ref="m", source_language="auto",
    )


@pytest.mark.asyncio
async def test_wiring_gate_off_does_not_call_detector():
    from app.routers import engine as engine_mod
    with patch.object(engine_mod, "detect_and_update_threads", new_callable=AsyncMock) as m:
        await _call_wiring(_work(False))
        m.assert_not_awaited()


@pytest.mark.asyncio
async def test_wiring_gate_on_calls_detector():
    from app.routers import engine as engine_mod
    with patch.object(engine_mod, "detect_and_update_threads", new_callable=AsyncMock) as m:
        await _call_wiring(_work(True))
        m.assert_awaited_once()


@pytest.mark.asyncio
async def test_wiring_swallows_detector_error_never_fails_generate():
    from app.routers import engine as engine_mod
    with patch.object(engine_mod, "detect_and_update_threads",
                      new_callable=AsyncMock, side_effect=RuntimeError("boom")) as m:
        # Must NOT raise — the producer is advisory (F1).
        await _call_wiring(_work(True))
        m.assert_awaited_once()
