"""A refusal that blocks the only way forward must name the way forward.

THE INVARIANT. When `op=start` is refused because a run is already active, the message names that
run and the op that CONTINUES it. A refusal the caller cannot act on is a dead end.

🔴 MEASURED LIVE 2026-08-31, batch t64-protocol2, K=5, zero errors, the tool on 68 of 68 wire
passes. On the turn where the author approves the worklist — "Yes, that worklist is right — go
ahead and build them." — the model called `op=start` AGAIN in 5 of 5 runs and received only

    ACTIVE_RUN: this book already has a build run in progress

which is true and offers nothing. Across the whole chat store, `composition_build_cast_and_graph`
has been called 95 times in 89 sessions and `op=approve_plan` ZERO times — every recorded call is
`start` or a confirm card. The protocol's second step has never once run.

The file already knew this shape: `cancel()` carries a note about the same refusal stranding a
book for two weeks, "no way forward and no way out, from the UI or the API".
"""
from __future__ import annotations

from uuid import uuid4

import pytest

from app.services.glossary_build.service import (
    _ACTIVE_STATUSES,
    _NEXT_OP_FOR_STATUS,
    GlossaryBuildService,
)


class _Repo:
    def __init__(self, refused=None, active=None, raises=False):
        self._refused = refused
        self._active = active
        self._raises = raises
        self.asked_for = []

    async def get_run(self, run_id, owner):
        return self._refused

    async def active_run_for_book(self, book_id, owner):
        if self._raises:
            raise RuntimeError("pool is gone")
        self.asked_for.append(book_id)
        return self._active


def _svc(repo) -> GlossaryBuildService:
    svc = GlossaryBuildService.__new__(GlossaryBuildService)
    svc._repo = repo
    return svc


BOOK, RUN, ACTIVE = uuid4(), uuid4(), uuid4()


@pytest.mark.asyncio
class TestItNamesTheRunAndTheNextOp:
    async def test_a_plan_ready_run_is_pointed_at_approve_plan(self):
        """The founding instance: the worklist is waiting for exactly this call."""
        repo = _Repo(refused={"book_id": BOOK},
                     active={"run_id": ACTIVE, "status": "plan_ready"})
        msg = await _svc(repo)._active_run_refusal(run_id=RUN, owner=uuid4())
        assert "approve_plan" in msg
        assert str(ACTIVE) in msg, "the caller is told to continue a run it cannot identify"
        assert "start" in msg, "it does not say what NOT to do, which is what the model did"

    async def test_an_edges_ready_run_is_pointed_at_the_OTHER_gate(self):
        """Two human gates, two different next calls. A single hard-coded op would be wrong
        half the time it fires."""
        repo = _Repo(refused={"book_id": BOOK},
                     active={"run_id": ACTIVE, "status": "edges_ready"})
        msg = await _svc(repo)._active_run_refusal(run_id=RUN, owner=uuid4())
        assert "approve_edges" in msg and "approve_plan" not in msg

    async def test_in_flight_work_is_pointed_at_status_not_a_gate(self):
        """`building` is the driver's own work — there is no human call to make, so telling the
        caller to approve something would send it at a gate that is not open."""
        repo = _Repo(refused={"book_id": BOOK},
                     active={"run_id": ACTIVE, "status": "building"})
        msg = await _svc(repo)._active_run_refusal(run_id=RUN, owner=uuid4())
        assert "op='status'" in msg and "approve" not in msg.split("op='status'")[0]

    async def test_cancel_is_always_offered(self):
        """Abandoning a review is an ordinary thing to do, and the two-week stranding this file
        records happened because it was not reachable."""
        repo = _Repo(refused={"book_id": BOOK},
                     active={"run_id": ACTIVE, "status": "plan_ready"})
        assert "cancel" in await _svc(repo)._active_run_refusal(run_id=RUN, owner=uuid4())

    async def test_it_asks_about_the_REFUSED_runs_book(self):
        """The refused run is a fresh draft; the collision is on ITS book. Asking about any
        other book would name a run that is not blocking this one."""
        repo = _Repo(refused={"book_id": BOOK},
                     active={"run_id": ACTIVE, "status": "plan_ready"})
        await _svc(repo)._active_run_refusal(run_id=RUN, owner=uuid4())
        assert repo.asked_for == [BOOK]


@pytest.mark.asyncio
class TestItDegradesToTheRefusalItReplaces:
    """A hint that fails to build must not swallow the refusal — the 409 still has to be sent."""

    async def test_a_lookup_failure_still_refuses(self):
        repo = _Repo(refused={"book_id": BOOK}, raises=True)
        msg = await _svc(repo)._active_run_refusal(run_id=RUN, owner=uuid4())
        assert msg == "this book already has a build run in progress"

    async def test_no_active_run_found_still_refuses(self):
        repo = _Repo(refused={"book_id": BOOK}, active=None)
        assert await _svc(repo)._active_run_refusal(run_id=RUN, owner=uuid4()) == (
            "this book already has a build run in progress")

    async def test_an_unreadable_refused_run_still_refuses(self):
        assert await _svc(_Repo(refused=None))._active_run_refusal(
            run_id=RUN, owner=uuid4()) == "this book already has a build run in progress"

    async def test_an_unknown_status_does_not_invent_an_op(self):
        """Better the old sentence than a confident instruction to call something wrong."""
        repo = _Repo(refused={"book_id": BOOK},
                     active={"run_id": ACTIVE, "status": "some_new_state"})
        assert "op=" not in await _svc(repo)._active_run_refusal(run_id=RUN, owner=uuid4())


class TestTheTwoStatusListsCannotDrift:
    def test_every_index_held_status_has_a_next_op(self):
        """🔴 THE FIVE-OF-SIX BUG, WRITTEN DOWN IN THIS FILE'S OWN HISTORY. `cancel()` covered
        five of the six statuses the active-run index holds, and the sixth stranded a book from
        27 July. A status the index blocks on but this map has no answer for is the same defect:
        the caller is refused and told nothing."""
        missing = [s for s in _ACTIVE_STATUSES if s not in _NEXT_OP_FOR_STATUS]
        assert not missing, (
            f"the active-run index blocks on {missing} but the refusal has no next op for them, "
            "so a caller in that state is refused with no way forward")

    def test_the_map_invents_no_status_the_index_does_not_hold(self):
        extra = [s for s in _NEXT_OP_FOR_STATUS if s not in _ACTIVE_STATUSES]
        assert not extra, f"{extra} never blocks a start, so an entry for it is dead code"


class TestTheRaiseSiteActuallyUsesIt:
    """🔴 GUARD THE CALL SITE. Every test above drives `_active_run_refusal` directly, so all
    eleven stayed GREEN when the raise site was reverted to the hard-coded dead end. A helper
    that returns the right sentence is worth nothing if the refusal never asks it for one."""

    def test_the_ACTIVE_RUN_raise_calls_the_builder(self):
        import ast
        import inspect
        import pathlib

        from app.services.glossary_build import service as mod

        tree = ast.parse(pathlib.Path(inspect.getfile(mod)).read_text(encoding="utf-8"))
        raises = [
            n for n in ast.walk(tree)
            if isinstance(n, ast.Raise) and isinstance(n.exc, ast.Call)
            and any(isinstance(a, ast.Constant) and a.value == "ACTIVE_RUN" for a in n.exc.args)
        ]
        assert raises, "no ACTIVE_RUN refusal found — this guard is pointing at nothing"
        for r in raises:
            called = {
                n.func.attr for n in ast.walk(r)
                if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
            }
            assert "_active_run_refusal" in called, (
                f"the ACTIVE_RUN raise at line {r.lineno} builds its message without asking "
                "_active_run_refusal — the caller gets the dead end back")


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
