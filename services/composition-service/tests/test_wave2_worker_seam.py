"""W2-F0 — the Wave-2 worker-dispatch FREEZE (the parallelization contract).

Proves the three Tier-W motif ops (already enqueued today by the confirm effects in
routers/actions.py) are RECOGNIZED by the worker dispatch and routed to their
WS-owned engine modules — NOT ``UnsupportedOperationError``. This is the seam W8/W9/W5
build behind without re-editing constants.py / job_consumer.py (so their worktrees stay
disjoint). All fakes — no Redis, no DB, no real LLM.
"""

from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.worker import job_consumer as jc
from app.worker.constants import SUPPORTED_OPERATIONS, is_worker_drivable, worker_op_of

_WAVE2_OPS = ("mine_motifs", "analyze_reference", "conformance_run")


def _job(operation, input=None):
    # created_by is the row-authoritative actor the worker injects (25 F7); user_id
    # kept as the SAME value so the test's `str(job.user_id)` assertions still hold.
    _uid = uuid4()
    return SimpleNamespace(
        id=uuid4(), created_by=_uid, user_id=_uid, project_id=uuid4(), operation=operation,
        status="pending", input=input if input is not None else {"worker_op": operation},
    )


def test_wave2_ops_are_supported_and_drivable():
    """Each op is in the retryable/recognized set + passes the strict drivability
    predicate when stamped on input['worker_op'] (the confirm effect stamps it)."""
    for op in _WAVE2_OPS:
        assert op in SUPPORTED_OPERATIONS, f"{op} missing from SUPPORTED_OPERATIONS"
        assert is_worker_drivable(op, {"worker_op": op}) is True
        assert worker_op_of(op, {"worker_op": op}) == op


@pytest.mark.parametrize(
    "op,module_attr",
    [
        ("mine_motifs", ("app.engine.motif_mine", "run_mine_motifs")),
        ("analyze_reference", ("app.engine.motif_deconstruct", "run_analyze_reference")),
        ("conformance_run", ("app.engine.motif_conformance_run", "run_conformance_run")),
    ],
)
async def test_dispatch_routes_each_wave2_op_to_its_module(monkeypatch, op, module_attr):
    """``_run_operation`` resolves the op (no UnsupportedOperationError) and calls the
    WS-owned module entrypoint with the job's input envelope + ids."""
    import importlib

    mod_name, fn_name = module_attr
    mod = importlib.import_module(mod_name)
    seen: dict = {}

    async def _fake(*args, **kwargs):
        seen.update(kwargs)
        seen["positional"] = len(args)
        return {"ok": True, "op": op}

    monkeypatch.setattr(mod, fn_name, _fake)

    job = _job(op, input={"worker_op": op, "scope": "book", "book_id": "b1",
                          "import_source_id": "i1", "chapter_id": "c1"})
    out = await jc._run_operation(object(), object(), job)
    assert out == {"ok": True, "op": op}
    assert seen["input"]["worker_op"] == op
    assert seen["user_id"] == str(job.user_id)


async def test_dispatch_stub_raises_terminal_business_error(monkeypatch):
    """A WS handler that hits a bad/missing input raises ValueError — a TERMINAL
    business error (job marked failed cleanly), NOT UnsupportedOperationError and NOT
    an infra error that would redeliver-loop. Verified through the real run_job path.

    (W8 has now landed the ``mine_motifs`` compute; this drives it with a scope='book'
    job that carries NO book_id, so the handler's input-validation ValueError stands
    in for the former stub ValueError — the SAME terminal-fail contract, a real
    business error instead of the not-yet-implemented placeholder.)"""
    job = _job("mine_motifs", input={"worker_op": "mine_motifs", "scope": "book"})

    class _FakeRepo:
        def __init__(self, j):
            self._j = j
            self.updates = []

        async def get(self, jid):
            return self._j

        async def update_status(self, jid, status, *, result=None, **kw):
            self.updates.append((status, result))
            return self._j

    repo = _FakeRepo(job)
    monkeypatch.setattr(jc, "GenerationJobsRepo", lambda pool: repo)
    monkeypatch.setattr(jc, "get_knowledge_client", lambda: object())

    out = await jc.run_job(object(), object(), job_id=str(job.id), user_id=str(job.user_id))
    assert out == "failed"  # ValueError is a business error → clean terminal fail
    assert repo.updates[-1][0] == "failed"
    assert "book_id" in repo.updates[-1][1]["error"]  # the handler's terminal business ValueError
