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


class _FakeLockConn:
    """A pooled connection that answers ONLY the advisory-lock SQL redrive_one issues
    (key derivation + try-lock + unlock). `claimed` controls whether the try-lock wins;
    `events` records lock/unlock so a test can assert release happened."""

    def __init__(self, *, claimed: bool, events: list):
        self._claimed = claimed
        self._events = events

    async def fetchval(self, sql, *args):
        if "pg_try_advisory_lock" in sql:
            self._events.append("lock")
            return self._claimed
        if "pg_advisory_unlock" in sql:
            self._events.append("unlock")
            return True
        # the bigint key-derivation SELECT — return a stable fake key
        return 4242


class _FakeAcquire:
    def __init__(self, conn):
        self._conn = conn

    async def __aenter__(self):
        return self._conn

    async def __aexit__(self, *exc):
        return False


class _FakePool:
    """Minimal asyncpg.Pool stand-in: only `acquire()` (the lock-claim path) is real;
    every other DB collaborator in redrive_one is monkeypatched away."""

    def __init__(self, *, claimed: bool = True):
        self.events: list = []
        self._claimed = claimed

    def acquire(self):
        return _FakeAcquire(_FakeLockConn(claimed=self._claimed, events=self.events))


async def test_redrive_threads_seed_text_and_expand_mode(monkeypatch):
    sink: dict = {}
    request = {
        "project_id": _PROJECT,
        "embedding_model_ref": str(uuid4()),
        "generation_model_ref": str(uuid4()),
        "technique": "compose_draft",
        "top_k": 5,
        "eval_reserve_fraction": 0.15,
        "max_spend_tokens": None,
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

    pool = _FakePool(claimed=True)
    state = await rc.redrive_one(pool=pool, job_id=str(uuid4()),
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
    # the per-job claim was taken AND released (lock then unlock) — HIGH-2.
    assert pool.events == ["lock", "unlock"]


async def test_redrive_skips_when_job_already_claimed(monkeypatch):
    """HIGH-2: a second runner whose pg_try_advisory_lock loses MUST no-op — it must
    not load the request or build a runner (which would double-spend real LLM tokens).
    Proves the claim gates the call site, not just that the SQL is issued."""
    sink: dict = {}

    async def _fail_if_called(*a, **k):  # any DB collaborator firing = the claim leaked
        raise AssertionError("redrive must not touch the job when the claim is lost")

    async def _build(**kw):
        raise AssertionError("redrive must not build a runner when the claim is lost")

    monkeypatch.setattr(rc, "load_job_request", _fail_if_called)
    monkeypatch.setattr(rc, "build_live_runner", _build)

    pool = _FakePool(claimed=False)
    state = await rc.redrive_one(pool=pool, job_id=str(uuid4()),
                                 project_id=_PROJECT, user_id=_USER)
    assert state == "already_claimed"
    # claim attempted, but NOT unlocked (we never held it) — the holder releases its own.
    assert pool.events == ["lock"]
    assert "build_kwargs" not in sink
