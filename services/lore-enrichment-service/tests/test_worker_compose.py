"""Compose slice 1 — the resume worker threads seed_text/expand_mode (mode D).

redrive_one is the SAME consumer a fresh compose_draft job is enqueued onto. This
pins that it (1) reads the compose-specific request fields and (2) threads them
into the StrategyContext the runner drives — without which the DraftExpandStrategy
has no draft to seed from. The heavy collaborators (DB pool, build_live_runner,
run_job) are faked so this is a pure wiring test (the real generation runs in the
live-smoke).
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from app.worker import resume_consumer as rc

pytestmark = pytest.mark.asyncio

_BOOK = str(uuid4())
_PROJECT = str(uuid4())
_USER = str(uuid4())


class _FakeRunner:
    def __init__(self, sink):
        self._sink = sink

    async def run_job(self, *, job_id, gaps, context, entity_kind, skip_gap_refs):
        self._sink["context"] = context
        self._sink["entity_kind"] = entity_kind
        self._sink["gaps"] = gaps

        class _Outcome:
            final_state = "completed"
            resumed_skipped: list = []
            proposals: list = []
            spent = 0.0

        return _Outcome()


class _FakeBundle:
    def __init__(self, sink):
        self.runner = _FakeRunner(sink)

    async def aclose(self):
        ...


async def test_redrive_threads_seed_text_and_expand_mode(monkeypatch):
    sink: dict = {}
    request = {
        "project_id": _PROJECT,
        "embedding_model_ref": str(uuid4()),
        "generation_model_ref": str(uuid4()),
        "technique": "compose_draft",
        "top_k": 5,
        "eval_reserve_fraction": 0.15,
        "max_spend_usd": None,
        "entity_kind": "generic",
        "targets": [
            {"canonical_name": "新天地", "target_ref": None, "entity_kind": "generic",
             "mention_count": 1, "present_dimensions": []},
        ],
        "user_id": _USER,
        "book_id": _BOOK,
        "input_source": "draft",
        "seed_text": "新天地乃星际殖民地，悬于双星轨道之间。",
        "expand_mode": "add_only",
    }

    async def _load_request(*, pool, job_id):
        return request

    async def _profile(_pool, _book_id):
        from app.db.book_profile import NEUTRAL_PROFILE
        return NEUTRAL_PROFILE

    async def _spent(*, pool, job_id):
        return 0.0

    async def _done(*, pool, job_id):
        return set()

    async def _build(**kw):
        sink["build_kwargs"] = kw
        return _FakeBundle(sink)

    monkeypatch.setattr(rc, "load_job_request", _load_request)
    monkeypatch.setattr(rc, "get_book_profile", _profile)
    monkeypatch.setattr(rc, "load_spent_so_far", _spent)
    monkeypatch.setattr(rc, "existing_gap_refs", _done)
    monkeypatch.setattr(rc, "build_live_runner", _build)

    state = await rc.redrive_one(pool=object(), job_id=str(uuid4()),
                                 project_id=_PROJECT, user_id=_USER)
    assert state == "completed"
    # the build selected the compose_draft technique...
    assert sink["build_kwargs"]["technique"] == "compose_draft"
    # ...and the ctx carries the author's draft + expand mode (the load-bearing wiring).
    ctx = sink["context"]
    assert ctx.seed_text == "新天地乃星际殖民地，悬于双星轨道之间。"
    assert ctx.expand_mode == "add_only"
    assert sink["entity_kind"] == "generic"
    # one gap built from the new target (all dims missing → target_ref None)
    assert len(sink["gaps"]) == 1
    assert sink["gaps"][0].target_ref is None
