"""Authoring-run tenancy regression suite (spec 25 Stage-1 re-key, Heal-B).

Locks in three real defects that were found + fixed after the repos/service were
de-scoped (READs bare-id, WRITEs stamp `created_by` but never filter on it; access
is decided BEFORE the repo, at the E0 book-grant gate):

(1) HIGH cross-book IDOR — the confirm-dispatch (app/routers/actions.py) EDIT-gates
    the request-body `book_id`, then ran `svc.start/resume/gate/revert_all(run_id)`
    with the run loaded BARE-ID, never checking `run.book_id == book_id`. Fixed by
    `_authoring_run_in_book`. An attacker with EDIT on their OWN book could start
    another user's run (spending their BYOK budget) or revert_all it (destroying
    their drafted chapters).
(3) MED missing-creator check — the MCP propose tools EDIT-gated the book only,
    while the REST `_run_for_mutation` is CREATOR-only (book-owner escalation is
    pause/close ONLY). Fixed by `_require_own_run` in app/mcp/server.py.

Asserted by EFFECT (checklist-is-self-report-enforce-by-tests): the service mutator
is spied and MUST NOT be called on a refusal; the propose tools MUST mint NO confirm
token; a missing run and a foreign run yield the SAME uniform refusal (no oracle).

(2) HIGH arity break (jobs.get(project_id, job_id) after the repo went bare-id) is
    regression-guarded in test_authoring_runs_service.py (the seam-level effect test),
    per the Heal-B split.
"""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

import app.mcp.server as srv
from app.db.models import AuthoringRun
from app.routers import actions
from loreweave_mcp import NotAccessibleError

USER = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
OTHER = uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
BOOK = uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")
OTHER_BOOK = uuid.UUID("dddddddd-dddd-dddd-dddd-dddddddddddd")
RUN = uuid.UUID("11111111-1111-1111-1111-111111111111")
PLAN = uuid.UUID("22222222-2222-2222-2222-222222222222")
CH1 = uuid.UUID("33333333-3333-3333-3333-333333333333")


def _run(*, created_by=USER, book_id=BOOK, status="gated", **over) -> AuthoringRun:
    base = dict(
        run_id=RUN, created_by=created_by, book_id=book_id, plan_run_id=PLAN,
        level=3, scope=[str(CH1)], budget_usd=Decimal("1.00"),
        spent_usd=Decimal("0"), tool_allowlist=["composition_write_prose"],
        params={}, breaker_state={}, status=status, current_unit=0,
        pause_after_each_unit=True,
    )
    base.update(over)
    return AuthoringRun(**base)


def _bad_run(bad: str):
    """The three inputs a fence must uniformly refuse."""
    if bad == "foreign_book":
        return _run(book_id=OTHER_BOOK)         # run lives in a DIFFERENT book
    if bad == "foreign_creator":
        return _run(created_by=OTHER)           # run in this book, someone else's
    return None                                 # missing run


# ══════════════════════════════════════════════════════════════════════════════
# (1) confirm-dispatch IDOR — actions.py `_authoring_run_in_book` + each effect
# ══════════════════════════════════════════════════════════════════════════════

_MUTATOR = {"start": "start", "resume": "resume", "gate": "gate",
            "revert_all": "revert_all"}


async def _run_executor(name: str, book) -> dict:
    """Drive the confirm-effect the dispatcher routes to (the effects re-resolve
    the run BARE-ID and must fence it against the confirm-gated book first)."""
    payload = {"run_id": str(RUN)}
    if name == "start":
        return await actions._execute_authoring_run_start(payload, BOOK, USER)
    if name == "resume":
        return await actions._execute_authoring_run_resume(payload, BOOK, USER)
    if name == "gate":
        return await actions._execute_authoring_run_gate(payload, BOOK, USER, book)
    if name == "revert_all":
        return await actions._execute_authoring_run_revert_all(payload, BOOK, USER, book)
    raise AssertionError(name)


@pytest.mark.parametrize("name", ["start", "resume", "gate", "revert_all"])
@pytest.mark.parametrize("bad", ["foreign_book", "foreign_creator", "missing"])
async def test_confirm_dispatch_refuses_and_never_mutates(name, bad):
    """The core IDOR fix: a confirm whose payload book_id (BOOK, EDIT-gated) does
    NOT own the target run — or whose creator is someone else — is refused with a
    uniform action_error, and the service mutator is NEVER reached (no spend, no
    destructive revert)."""
    spy = AsyncMock()
    spy.get = AsyncMock(return_value=_bad_run(bad))
    book = AsyncMock()
    with patch("app.deps.get_authoring_run_service", new=AsyncMock(return_value=spy)):
        with pytest.raises(HTTPException) as ei:
            await _run_executor(name, book)
    assert ei.value.status_code == 400
    assert ei.value.detail == {"code": "action_error"}
    # EFFECT: the mutator that spends budget / destroys drafts was never called.
    getattr(spy, _MUTATOR[name]).assert_not_awaited()


@pytest.mark.parametrize("name", ["start", "resume", "gate", "revert_all"])
async def test_confirm_dispatch_happy_path_calls_mutator(name):
    """Own run + matching book still succeeds and DOES call the mutator."""
    spy = AsyncMock()
    spy.get = AsyncMock(return_value=_run(status="report_ready"))  # own, this book
    spy.start = AsyncMock(return_value=_run(status="running"))
    spy.resume = AsyncMock(return_value=_run(status="running"))
    spy.gate = AsyncMock(return_value=_run(status="gated"))
    spy.revert_all = AsyncMock(return_value={
        "reverted_unit_indexes": [], "failed_unit_index": None,
        "error": None, "run_status": "closed", "closed": True,
    })
    book = AsyncMock()
    book.list_chapters = AsyncMock(return_value=[{"chapter_id": str(CH1)}])
    with patch("app.deps.get_authoring_run_service", new=AsyncMock(return_value=spy)):
        res = await _run_executor(name, book)
    assert res["outcome"] == "action_done"
    mutator = getattr(spy, _MUTATOR[name])
    mutator.assert_awaited_once()
    assert mutator.await_args.args[0] == RUN


async def test_authoring_run_in_book_missing_and_foreign_same_shape():
    """No existence oracle: a missing run and a run in a DIFFERENT book raise the
    exact same refusal shape from the shared fence."""
    errs = []
    for run in (None, _run(book_id=OTHER_BOOK)):
        spy = AsyncMock()
        spy.get = AsyncMock(return_value=run)
        with pytest.raises(HTTPException) as ei:
            await actions._authoring_run_in_book(spy, RUN, BOOK, USER)
        errs.append((ei.value.status_code, ei.value.detail))
    assert errs[0] == errs[1] == (400, {"code": "action_error"})


async def test_authoring_run_in_book_foreign_creator_refused():
    """Book matches, creator does not — refused (the confirm-gated EDIT proves
    only book access, never that the run is the caller's)."""
    spy = AsyncMock()
    spy.get = AsyncMock(return_value=_run(created_by=OTHER))
    with pytest.raises(HTTPException) as ei:
        await actions._authoring_run_in_book(spy, RUN, BOOK, USER)
    assert ei.value.status_code == 400
    assert ei.value.detail == {"code": "action_error"}


async def test_authoring_run_in_book_own_run_returns_it():
    spy = AsyncMock()
    own = _run()
    spy.get = AsyncMock(return_value=own)
    got = await actions._authoring_run_in_book(spy, RUN, BOOK, USER)
    assert got is own


# ══════════════════════════════════════════════════════════════════════════════
# (3) MCP propose/review creator fence — server.py `_require_own_run`
# ══════════════════════════════════════════════════════════════════════════════


class _Ctx:
    """Stand-in for the kit ToolContext (only `user_id` is read by handlers)."""

    def __init__(self, user_id=USER):
        self.user_id = user_id
        self.session_id = "sess-1"
        self.project_id = None
        self.trace_id = None
        self.internal_token = "test_token"


@asynccontextmanager
async def _patched(*, grant_level: int, svc):
    """Patch `_ctx` (skip header parsing), the grant resolver (returns
    `grant_level`: 1=VIEW, 2=EDIT, 4=OWNER), the service factory, and
    `mint_confirm_token` (yielded so a refusal can prove NO token was minted)."""
    async def _resolve(book_id, user_id):
        return grant_level

    mint = MagicMock(return_value="minted-token")
    with patch.object(srv, "_ctx", side_effect=lambda ctx: ctx), \
         patch.object(srv, "_grant_resolver", return_value=_resolve), \
         patch.object(srv, "get_authoring_run_service", new=AsyncMock(return_value=svc)), \
         patch.object(srv, "mint_confirm_token", mint):
        yield mint


async def _call_propose(name: str, ctx):
    if name == "gate":
        return await srv.composition_authoring_run_gate(
            ctx, srv._AuthoringRunIdArgs(book_id=str(BOOK), run_id=str(RUN)))
    if name == "start":
        return await srv.composition_authoring_run_start(
            ctx, srv._AuthoringRunStartArgs(book_id=str(BOOK), run_id=str(RUN)))
    if name == "resume":
        return await srv.composition_authoring_run_resume(
            ctx, srv._AuthoringRunResumeArgs(book_id=str(BOOK), run_id=str(RUN)))
    return await srv.composition_authoring_run_revert_all(
        ctx, srv._AuthoringRunIdArgs(book_id=str(BOOK), run_id=str(RUN)))


@pytest.mark.parametrize("name", ["gate", "start", "resume", "revert_all"])
@pytest.mark.parametrize("bad", ["foreign_book", "foreign_creator", "missing"])
async def test_mcp_propose_refuses_foreign_run_and_mints_no_token(name, bad):
    """A propose tool has EDIT on the book (grant 2) but the run is foreign / not
    the caller's / missing — `_require_own_run` refuses uniformly and NO confirm
    token is minted (nothing to confirm-execute against another user's run)."""
    svc = AsyncMock()
    svc.get = AsyncMock(return_value=_bad_run(bad))
    async with _patched(grant_level=2, svc=svc) as mint:
        with pytest.raises(NotAccessibleError):
            await _call_propose(name, _Ctx())
    mint.assert_not_called()


@pytest.mark.parametrize("name", ["gate", "start", "resume", "revert_all"])
async def test_mcp_propose_own_run_mints_token(name):
    """Own run + EDIT still mints the confirm token (the fence lets the creator
    through)."""
    svc = AsyncMock()
    svc.get = AsyncMock(return_value=_run())
    async with _patched(grant_level=2, svc=svc) as mint:
        res = await _call_propose(name, _Ctx())
    assert res["confirm_token"] == "minted-token"
    mint.assert_called_once()


@pytest.mark.parametrize("tool", ["accept", "reject"])
async def test_mcp_review_refuses_non_creator_even_with_edit(tool):
    """accept_unit/reject_unit are creator-only — a non-creator EDIT-grantee is
    refused (rejecting a unit RESTORES the chapter's prior revision, so an EDIT
    collaborator could otherwise destroy another author's draft). The service
    review mutator is never reached."""
    svc = AsyncMock()
    svc.get = AsyncMock(return_value=_run(created_by=OTHER, status="paused"))
    args = srv._AuthoringRunUnitArgs(book_id=str(BOOK), run_id=str(RUN), unit_index=0)
    async with _patched(grant_level=2, svc=svc):   # EDIT — not enough on its own
        with pytest.raises(NotAccessibleError):
            if tool == "accept":
                await srv.composition_authoring_run_accept_unit(_Ctx(), args)
            else:
                await srv.composition_authoring_run_reject_unit(_Ctx(), args)
    svc.accept_unit.assert_not_called()
    svc.reject_unit.assert_not_called()


async def test_mcp_missing_and_foreign_run_same_refusal_message():
    """No existence oracle at the MCP door either: a missing run and a run in a
    different book produce the identical refusal message."""
    msgs = []
    for run in (None, _run(book_id=OTHER_BOOK)):
        svc = AsyncMock()
        svc.get = AsyncMock(return_value=run)
        async with _patched(grant_level=2, svc=svc):
            with pytest.raises(NotAccessibleError) as ei:
                await srv.composition_authoring_run_start(
                    _Ctx(), srv._AuthoringRunStartArgs(book_id=str(BOOK), run_id=str(RUN)))
        msgs.append(str(ei.value))
    assert msgs[0] == msgs[1]
