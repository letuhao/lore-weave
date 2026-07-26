"""D-AGENT-MODE §20 — MCP tool tests for `composition_authoring_run_*` (11
tools, spec docs/specs/2026-07-01-writing-studio/20_agent_mode.md, D5/D6/D7).

Unlike most of this server's tools (Work/project_id-scoped, `test_mcp_server.py`'s
`_patched` helper resolves a `WorksRepo`), these tools are BOOK-scoped directly
(D7 — explicit book_id, never inferred). This file patches `_ctx` + `_grant_resolver`
directly (mirrors `_patched`'s mechanics) and injects a stub `AuthoringRunService`
via the module-level `get_authoring_run_service` import.

Confirm-gated tools (create/gate/start/resume/revert_all, D6) mint a
`confirm_token` and touch NO service at all — the effect only fires through
`confirm_action` (app/routers/actions.py, tested separately in
test_mcp_actions.py-style coverage below). Direct tools (list/get/pause/close/
accept_unit/reject_unit) call the stub service."""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest

from app.db.models import AuthoringRun, AuthoringRunUnit
from app.services.authoring_run_service import (
    ActiveRunOverlapError,
    TransitionConflictError,
)

_GOOD_TOKEN = "test_token"  # matches tests/conftest.py INTERNAL_SERVICE_TOKEN
TEST_USER = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
OTHER_USER = uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
BOOK = uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")
RUN = uuid.UUID("11111111-1111-1111-1111-111111111111")
PLAN = uuid.UUID("22222222-2222-2222-2222-222222222222")
CH1 = uuid.UUID("33333333-3333-3333-3333-333333333333")
CH2 = uuid.UUID("44444444-4444-4444-4444-444444444444")


class _Ctx:
    """Stand-in for the kit ToolContext (only `user_id` is read by handlers)."""

    def __init__(self, user_id=TEST_USER):
        self.user_id = user_id
        self.session_id = "sess-1"
        self.project_id = None
        self.trace_id = None
        self.internal_token = _GOOD_TOKEN


def _run(status="draft", **over) -> AuthoringRun:
    base = dict(
        run_id=RUN, created_by=TEST_USER, book_id=BOOK, plan_run_id=PLAN,
        level=3, scope=[str(CH1), str(CH2)], budget_usd=Decimal("5.00"),
        spent_usd=Decimal("0"), tool_allowlist=["composition_write_prose"], params={},
        breaker_state={}, status=status, current_unit=0,
        pause_after_each_unit=True,
    )
    base.update(over)
    return AuthoringRun(**base)


def _unit(unit_index=0, status="drafted", **over) -> AuthoringRunUnit:
    base = dict(
        run_id=RUN, unit_index=unit_index, chapter_id=CH1, status=status,
        pre_revision_id=uuid.uuid4(), post_revision_id=uuid.uuid4(),
        cost_usd=Decimal("0.02"),
    )
    base.update(over)
    return AuthoringRunUnit(**base)


@asynccontextmanager
async def _patched(*, grant_level=2, svc=None):
    """Patch the server's `_ctx` (skip header parsing), the grant resolver
    (returns `grant_level`: 0=none, 1=VIEW, 2=EDIT, 4=OWNER — loreweave_grants
    ints), and `get_authoring_run_service` to return `svc`.

    Default stub (svc=None): a bare AsyncMock whose `get` returns the caller's
    OWN run in this book — spec 25 made every run mutation (incl. the PROPOSE
    tools' `_require_own_run` creator fence) resolve the run BARE-ID, so a
    confirm-gated tool must reconcile it before minting. Tests that need a
    foreign/None run override `svc.get` explicitly."""
    import app.mcp.server as srv

    async def _resolve(book_id, user_id):
        return grant_level

    stub = svc if svc is not None else AsyncMock()
    if svc is None:
        stub.get = AsyncMock(return_value=_run())  # own run in BOOK
    with patch.object(srv, "_ctx", side_effect=lambda ctx: ctx), \
         patch.object(srv, "_grant_resolver", return_value=_resolve), \
         patch.object(srv, "get_authoring_run_service", new=AsyncMock(return_value=stub)):
        yield srv, stub


# ── Tier R — list / get ──────────────────────────────────────────────────────


async def test_list_returns_items():
    import app.mcp.server as srv

    svc = AsyncMock()
    svc.list = AsyncMock(return_value=[_run(status="running"), _run(run_id=uuid.uuid4())])
    async with _patched(grant_level=1, svc=svc):
        res = await srv.composition_authoring_run_list(
            _Ctx(), srv._AuthoringRunListArgs(book_id=str(BOOK)),
        )
    assert len(res["items"]) == 2
    assert res["items"][0]["book_id"] == str(BOOK)
    assert res["items"][0]["pause_after_each_unit"] is True
    assert res["has_more"] is False
    # OUT-5 (mcp-tool-io.md): over-fetches by one to detect a capped result honestly.
    # spec 25: the list is book-scoped (no owner arg).
    svc.list.assert_awaited_once_with(BOOK, limit=21)


async def test_list_reports_has_more_when_capped():
    """OUT-5 — never silently truncate: a result at the requested limit must say so."""
    import app.mcp.server as srv

    svc = AsyncMock()
    svc.list = AsyncMock(return_value=[_run(run_id=uuid.uuid4()) for _ in range(3)])
    async with _patched(grant_level=1, svc=svc):
        res = await srv.composition_authoring_run_list(
            _Ctx(), srv._AuthoringRunListArgs(book_id=str(BOOK), limit=2),
        )
    assert len(res["items"]) == 2
    assert res["has_more"] is True
    svc.list.assert_awaited_once_with(BOOK, limit=3)


async def test_list_rejects_limit_out_of_bounds():
    import app.mcp.server as srv
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        srv._AuthoringRunListArgs(book_id=str(BOOK), limit=0)
    with pytest.raises(ValidationError):
        srv._AuthoringRunListArgs(book_id=str(BOOK), limit=101)


async def test_create_rejects_non_positive_budget():
    import app.mcp.server as srv
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        srv._AuthoringRunCreateArgs(
            book_id=str(BOOK), plan_run_id=str(uuid.uuid4()),
            budget_usd="0", pause_after_each_unit=True,
        )


async def test_create_rejects_unknown_tool_allowlist_entry():
    """IN-3 (mcp-tool-io.md): tool_allowlist is a closed-set enum, not a bare
    string list — a hallucinated/typo'd tool name must reject at the schema
    level (self-correcting, before the model wastes a confirm round-trip)."""
    import app.mcp.server as srv
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        srv._AuthoringRunCreateArgs(
            book_id=str(BOOK), plan_run_id=str(uuid.uuid4()),
            budget_usd=Decimal("1"), pause_after_each_unit=True,
            tool_allowlist=["not_a_real_tool"],
        )


async def test_create_accepts_a_real_allowlistable_tool():
    import app.mcp.server as srv

    args = srv._AuthoringRunCreateArgs(
        book_id=str(BOOK), plan_run_id=str(uuid.uuid4()),
        budget_usd=Decimal("1"), pause_after_each_unit=True,
        tool_allowlist=["composition_write_prose"],
    )
    assert args.tool_allowlist == ["composition_write_prose"]


async def test_unit_args_rejects_negative_unit_index():
    import app.mcp.server as srv
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        srv._AuthoringRunUnitArgs(book_id=str(BOOK), run_id=str(uuid.uuid4()), unit_index=-1)


async def test_list_denied_without_view_grant():
    from loreweave_mcp import NotAccessibleError

    async with _patched(grant_level=0):
        with pytest.raises(NotAccessibleError):
            import app.mcp.server as srv
            await srv.composition_authoring_run_list(
                _Ctx(), srv._AuthoringRunListArgs(book_id=str(BOOK)),
            )


async def test_get_returns_run_and_unit_report():
    import app.mcp.server as srv

    svc = AsyncMock()
    svc.get = AsyncMock(return_value=_run(status="report_ready"))
    svc.unit_report = AsyncMock(return_value=[{"unit_index": 0, "status": "drafted"}])
    async with _patched(grant_level=1, svc=svc):
        res = await srv.composition_authoring_run_get(
            _Ctx(), srv._AuthoringRunGetArgs(book_id=str(BOOK), run_id=str(RUN)),
        )
    assert res["run"]["run_id"] == str(RUN)
    assert res["units"] == [{"unit_index": 0, "status": "drafted"}]


async def test_get_tolerates_a_harmless_hallucinated_extra_field():
    """IN-5 (mcp-tool-io.md, /review-impl): all 7 authoring-run arg models were
    migrated from ForbidExtra to TolerantArgs — a weak model adding a plausible
    but unrecognized extra kwarg must NOT hard-fail the call (it used to)."""
    import app.mcp.server as srv

    svc = AsyncMock()
    svc.get = AsyncMock(return_value=_run(status="report_ready"))
    svc.unit_report = AsyncMock(return_value=[])
    args = srv._AuthoringRunGetArgs(
        book_id=str(BOOK), run_id=str(RUN), reason="just checking",
    )
    assert not hasattr(args, "reason")  # dropped, not smuggled through
    async with _patched(grant_level=1, svc=svc):
        res = await srv.composition_authoring_run_get(_Ctx(), args)
    assert res["run"]["run_id"] == str(RUN)


async def test_get_run_not_reportable_surfaces_units_error_not_raise():
    import app.mcp.server as srv

    svc = AsyncMock()
    svc.get = AsyncMock(return_value=_run(status="draft"))
    svc.unit_report = AsyncMock(
        side_effect=TransitionConflictError("report requires status in (...), run is draft"),
    )
    async with _patched(grant_level=1, svc=svc):
        res = await srv.composition_authoring_run_get(
            _Ctx(), srv._AuthoringRunGetArgs(book_id=str(BOOK), run_id=str(RUN)),
        )
    assert res["units"] is None
    assert "report requires" in res["units_error"]


async def test_get_foreign_run_refused():
    """A run_id that exists but belongs to a DIFFERENT book than the explicit
    book_id arg (D7) is refused uniformly — never silently resolved."""
    import app.mcp.server as srv
    from loreweave_mcp import NotAccessibleError

    svc = AsyncMock()
    svc.get = AsyncMock(return_value=_run(book_id=uuid.uuid4()))
    async with _patched(svc=svc):
        with pytest.raises(NotAccessibleError):
            await srv.composition_authoring_run_get(
                _Ctx(), srv._AuthoringRunGetArgs(book_id=str(BOOK), run_id=str(RUN)),
            )


async def test_get_unowned_run_refused():
    import app.mcp.server as srv
    from loreweave_mcp import NotAccessibleError

    svc = AsyncMock()
    svc.get = AsyncMock(return_value=None)  # owner-scoped lookup found nothing
    async with _patched(svc=svc):
        with pytest.raises(NotAccessibleError):
            await srv.composition_authoring_run_get(
                _Ctx(), srv._AuthoringRunGetArgs(book_id=str(BOOK), run_id=str(RUN)),
            )


# ── Tier W — create (confirm-gated; D6 required args, no service touched) ───


async def test_create_mints_confirm_token_with_full_payload():
    import app.mcp.server as srv
    from loreweave_mcp import verify_confirm_token
    from app.config import settings

    async with _patched(grant_level=2) as (_srv, svc):
        res = await srv.composition_authoring_run_create(
            _Ctx(),
            srv._AuthoringRunCreateArgs(
                book_id=str(BOOK), plan_run_id=str(PLAN),
                scope=[str(CH1), str(CH2)], level=3, budget_usd=Decimal("2.50"),
                tool_allowlist=["composition_write_prose"], pause_after_each_unit=True,
            ),
        )
    assert res["descriptor"] == "composition.authoring_run_create"
    assert res["domain"] == "composition"
    claims = verify_confirm_token(settings.confirm_token_signing_secret, res["confirm_token"])
    assert claims.user_id == TEST_USER
    assert claims.resource_id == BOOK
    assert claims.payload["book_id"] == str(BOOK)
    assert claims.payload["plan_run_id"] == str(PLAN)
    assert claims.payload["budget_usd"] == "2.50"
    assert claims.payload["pause_after_each_unit"] is True
    assert claims.payload["level"] == 3
    # PROPOSE mints a token only — the service is never touched at create-time.
    svc.create.assert_not_called()


def test_create_args_require_budget_usd_and_pause_after_each_unit():
    """D4b/D6: both are REQUIRED with no default — a missing value is a
    pydantic validation error, never a silent default."""
    import app.mcp.server as srv
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        srv._AuthoringRunCreateArgs(
            book_id=str(BOOK), plan_run_id=str(PLAN),
            tool_allowlist=["composition_write_prose"], pause_after_each_unit=True,
        )  # missing budget_usd
    with pytest.raises(ValidationError):
        srv._AuthoringRunCreateArgs(
            book_id=str(BOOK), plan_run_id=str(PLAN),
            tool_allowlist=["composition_write_prose"], budget_usd=Decimal("1"),
        )  # missing pause_after_each_unit


async def test_create_denied_without_edit_grant():
    import app.mcp.server as srv
    from loreweave_mcp import NotAccessibleError

    async with _patched(grant_level=1):  # VIEW only
        with pytest.raises(NotAccessibleError):
            await srv.composition_authoring_run_create(
                _Ctx(),
                srv._AuthoringRunCreateArgs(
                    book_id=str(BOOK), plan_run_id=str(PLAN),
                    budget_usd=Decimal("1"), tool_allowlist=["composition_write_prose"],
                    pause_after_each_unit=False,
                ),
            )


# ── Tier W — gate / start / resume (confirm-gated) ──────────────────────────


async def test_gate_mints_confirm_token():
    import app.mcp.server as srv
    from loreweave_mcp import verify_confirm_token
    from app.config import settings

    async with _patched(grant_level=2):
        res = await srv.composition_authoring_run_gate(
            _Ctx(), srv._AuthoringRunIdArgs(book_id=str(BOOK), run_id=str(RUN)),
        )
    assert res["descriptor"] == "composition.authoring_run_gate"
    claims = verify_confirm_token(settings.confirm_token_signing_secret, res["confirm_token"])
    assert claims.resource_id == RUN
    assert claims.payload == {"book_id": str(BOOK), "run_id": str(RUN)}


async def test_start_mints_confirm_token_without_override_by_default():
    import app.mcp.server as srv
    from loreweave_mcp import verify_confirm_token
    from app.config import settings

    async with _patched(grant_level=2):
        res = await srv.composition_authoring_run_start(
            _Ctx(), srv._AuthoringRunStartArgs(book_id=str(BOOK), run_id=str(RUN)),
        )
    assert res["descriptor"] == "composition.authoring_run_start"
    claims = verify_confirm_token(settings.confirm_token_signing_secret, res["confirm_token"])
    assert "pause_after_each_unit" not in claims.payload  # no override → omitted


async def test_start_mints_confirm_token_with_explicit_override():
    import app.mcp.server as srv
    from loreweave_mcp import verify_confirm_token
    from app.config import settings

    async with _patched(grant_level=2):
        res = await srv.composition_authoring_run_start(
            _Ctx(),
            srv._AuthoringRunStartArgs(
                book_id=str(BOOK), run_id=str(RUN), pause_after_each_unit=False,
            ),
        )
    claims = verify_confirm_token(settings.confirm_token_signing_secret, res["confirm_token"])
    assert claims.payload["pause_after_each_unit"] is False


async def test_resume_mints_confirm_token_with_override():
    import app.mcp.server as srv
    from loreweave_mcp import verify_confirm_token
    from app.config import settings

    async with _patched(grant_level=2):
        res = await srv.composition_authoring_run_resume(
            _Ctx(),
            srv._AuthoringRunResumeArgs(
                book_id=str(BOOK), run_id=str(RUN), pause_after_each_unit=False,
            ),
        )
    assert res["descriptor"] == "composition.authoring_run_resume"
    claims = verify_confirm_token(settings.confirm_token_signing_secret, res["confirm_token"])
    assert claims.payload["pause_after_each_unit"] is False


async def test_gate_start_resume_denied_without_edit_grant():
    import app.mcp.server as srv
    from loreweave_mcp import NotAccessibleError

    for coro, args in (
        (srv.composition_authoring_run_gate, srv._AuthoringRunIdArgs(book_id=str(BOOK), run_id=str(RUN))),
        (srv.composition_authoring_run_start, srv._AuthoringRunStartArgs(book_id=str(BOOK), run_id=str(RUN))),
        (srv.composition_authoring_run_resume, srv._AuthoringRunResumeArgs(book_id=str(BOOK), run_id=str(RUN))),
    ):
        async with _patched(grant_level=1):
            with pytest.raises(NotAccessibleError):
                await coro(_Ctx(), args)


# ── Tier A — pause / close (direct, book-owner-may-act widening) ───────────


async def test_pause_direct_no_confirm_token():
    import app.mcp.server as srv

    svc = AsyncMock()
    svc.get = AsyncMock(return_value=_run(status="running"))
    svc.pause = AsyncMock(return_value=_run(status="paused"))
    async with _patched(svc=svc):
        res = await srv.composition_authoring_run_pause(
            _Ctx(), srv._AuthoringRunIdArgs(book_id=str(BOOK), run_id=str(RUN)),
        )
    assert "confirm_token" not in res
    assert res["success"] is True
    assert res["run"]["status"] == "paused"
    svc.pause.assert_awaited_once_with(RUN)  # spec 25: bare-id transition


async def test_pause_wrong_state_returns_tool_error_not_raise():
    import app.mcp.server as srv

    svc = AsyncMock()
    svc.get = AsyncMock(return_value=_run(status="draft"))
    svc.pause = AsyncMock(side_effect=TransitionConflictError("pause requires status=running"))
    async with _patched(svc=svc):
        res = await srv.composition_authoring_run_pause(
            _Ctx(), srv._AuthoringRunIdArgs(book_id=str(BOOK), run_id=str(RUN)),
        )
    assert res["success"] is False
    assert "pause requires" in res["error"]


async def test_close_book_owner_may_act_on_foreign_run():
    """The book's OWNER-grant holder may close a collaborator's run — acting
    AS the run's real owner (mirrors the REST router's book_owner_may_act)."""
    import app.mcp.server as srv

    other_owner = OTHER_USER
    svc = AsyncMock()
    # spec 25: run resolved BARE-ID; the caller is NOT the creator, so the
    # OWNER-grant escalation (`_authoring_run_actor` allow_book_owner) lets them
    # close it. The transition itself is bare-id (created_by preserved on the row).
    svc.get = AsyncMock(return_value=_run(created_by=other_owner, book_id=BOOK, status="paused"))
    svc.close = AsyncMock(return_value=_run(created_by=other_owner, status="closed"))
    async with _patched(grant_level=4, svc=svc):     # 4 = OWNER
        res = await srv.composition_authoring_run_close(
            _Ctx(), srv._AuthoringRunIdArgs(book_id=str(BOOK), run_id=str(RUN)),
        )
    assert res["success"] is True
    svc.close.assert_awaited_once_with(RUN)  # bare-id transition (spec 25)


async def test_close_non_owner_grant_cannot_act_on_foreign_run():
    import app.mcp.server as srv
    from loreweave_mcp import NotAccessibleError

    svc = AsyncMock()
    # Foreign run (someone else's) in this book; caller has EDIT, not OWNER — the
    # book-owner escalation requires OWNER, so `_authoring_run_actor` refuses.
    svc.get = AsyncMock(return_value=_run(created_by=OTHER_USER, book_id=BOOK, status="paused"))
    async with _patched(grant_level=2, svc=svc):     # EDIT only, not OWNER
        with pytest.raises(NotAccessibleError):
            await srv.composition_authoring_run_close(
                _Ctx(), srv._AuthoringRunIdArgs(book_id=str(BOOK), run_id=str(RUN)),
            )
    svc.close.assert_not_called()


async def test_start_stays_run_owner_only_even_with_owner_grant():
    """start/resume spend the run CREATOR's budget — unlike pause/close, a book
    OWNER grant does NOT unlock someone else's run. spec 25 tightened this at
    PROPOSE too: `_require_own_run` creator-fences the mint (no book_owner
    escalation path). Here the caller OWNS the default run, so with OWNER on the
    book the token still mints (the foreign-run refusal is covered in
    test_authoring_run_tenancy.py)."""
    import app.mcp.server as srv

    async with _patched(grant_level=4):  # OWNER on the book, caller owns the run
        res = await srv.composition_authoring_run_start(
            _Ctx(), srv._AuthoringRunStartArgs(book_id=str(BOOK), run_id=str(RUN)),
        )
    assert "confirm_token" in res


# ── Tier A — accept_unit / reject_unit (direct, owner-scoped) ───────────────


async def test_accept_unit_direct():
    import app.mcp.server as srv

    svc = AsyncMock()
    svc.get = AsyncMock(return_value=_run(status="report_ready"))
    svc.accept_unit = AsyncMock(return_value=_unit(status="accepted"))
    async with _patched(svc=svc):
        res = await srv.composition_authoring_run_accept_unit(
            _Ctx(),
            srv._AuthoringRunUnitArgs(book_id=str(BOOK), run_id=str(RUN), unit_index=0),
        )
    assert res["success"] is True
    assert res["status"] == "accepted"
    assert "confirm_token" not in res


async def test_accept_unit_foreign_book_refused():
    import app.mcp.server as srv
    from loreweave_mcp import NotAccessibleError

    svc = AsyncMock()
    svc.get = AsyncMock(return_value=_run(book_id=uuid.uuid4()))
    async with _patched(svc=svc):
        with pytest.raises(NotAccessibleError):
            await srv.composition_authoring_run_accept_unit(
                _Ctx(),
                srv._AuthoringRunUnitArgs(book_id=str(BOOK), run_id=str(RUN), unit_index=0),
            )


async def test_reject_unit_restores_via_headless_bearer_and_warns_cascade():
    import app.mcp.server as srv

    svc = AsyncMock()
    svc.get = AsyncMock(return_value=_run(status="paused"))
    pre_rev = uuid.uuid4()
    restore_calls = []

    async def fake_reject_unit(run_id, unit_index, *, restore):  # spec 25: bare-id
        await restore(BOOK, CH1, pre_rev)
        return _unit(status="rejected"), [1], True

    svc.reject_unit = AsyncMock(side_effect=fake_reject_unit)
    book = AsyncMock()
    book.restore_revision = AsyncMock(return_value={"draft_version": 3})
    async with _patched(svc=svc):
        with patch.object(srv, "get_book_client", return_value=book), \
             patch.object(srv, "mint_service_bearer", return_value="tok"):
            res = await srv.composition_authoring_run_reject_unit(
                _Ctx(),
                srv._AuthoringRunUnitArgs(book_id=str(BOOK), run_id=str(RUN), unit_index=0),
            )
    assert res["success"] is True
    assert res["reverted"] is True
    assert res["cascade_warning"]["downstream_unit_indexes"] == [1]
    book.restore_revision.assert_awaited_once_with(BOOK, CH1, pre_rev, "tok")


async def test_reject_unit_restore_failure_surfaces_as_tool_error():
    import app.mcp.server as srv
    from app.clients.book_client import BookClientError

    svc = AsyncMock()
    svc.get = AsyncMock(return_value=_run(status="paused"))
    svc.reject_unit = AsyncMock(side_effect=BookClientError(502, "BOOK_SERVICE_UNAVAILABLE"))
    async with _patched(svc=svc):
        with patch.object(srv, "get_book_client", return_value=AsyncMock()), \
             patch.object(srv, "mint_service_bearer", return_value="tok"):
            res = await srv.composition_authoring_run_reject_unit(
                _Ctx(),
                srv._AuthoringRunUnitArgs(book_id=str(BOOK), run_id=str(RUN), unit_index=0),
            )
    assert res["success"] is False
    assert "left drafted" in res["error"]


# ── Tier W — revert_all (confirm-gated, destructive) ────────────────────────


async def test_revert_all_mints_confirm_token():
    import app.mcp.server as srv
    from loreweave_mcp import verify_confirm_token
    from app.config import settings

    async with _patched(grant_level=2) as (_srv, svc):
        res = await srv.composition_authoring_run_revert_all(
            _Ctx(), srv._AuthoringRunIdArgs(book_id=str(BOOK), run_id=str(RUN)),
        )
    assert res["descriptor"] == "composition.authoring_run_revert_all"
    claims = verify_confirm_token(settings.confirm_token_signing_secret, res["confirm_token"])
    assert claims.resource_id == RUN
    assert claims.payload == {"book_id": str(BOOK), "run_id": str(RUN)}
    svc.revert_all.assert_not_called()  # PROPOSE only — no effect until confirm


async def test_revert_all_denied_without_edit_grant():
    import app.mcp.server as srv
    from loreweave_mcp import NotAccessibleError

    async with _patched(grant_level=1):
        with pytest.raises(NotAccessibleError):
            await srv.composition_authoring_run_revert_all(
                _Ctx(), srv._AuthoringRunIdArgs(book_id=str(BOOK), run_id=str(RUN)),
            )
