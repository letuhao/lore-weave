"""S3·authoring_run — dispatch tests for the 2 tier-split unified tools:
composition_authoring_run_manage (W/book — gated) and composition_authoring_run_review
(A/book — immediate). The tier split is behavioral (W mints a confirm-token, A auto-applies),
so it must be TWO tools; these tests prove op-routing + per-op arg construction + validation,
with delegates patched so a mis-route reds.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from unittest.mock import AsyncMock, patch

import app.mcp.server as srv

BOOK = "cccccccc-cccc-cccc-cccc-cccccccccccc"
RUN = "11111111-1111-1111-1111-111111111111"
PLAN = "22222222-2222-2222-2222-222222222222"


class _Ctx:
    def __init__(self):
        self.user_id = None
        self.session_id = "s"
        self.project_id = None
        self.trace_id = None
        self.internal_token = "t"


# ── composition_authoring_run_manage (W) ─────────────────────────────────────────


async def test_manage_create_routes_and_keeps_defaults():
    with patch.object(srv, "composition_authoring_run_create", AsyncMock(return_value={"ok": 1})) as m:
        await srv.composition_authoring_run_manage(
            _Ctx(),
            srv._AuthoringRunManageArgs(op="create", book_id=BOOK, plan_run_id=PLAN,
                                        budget_usd=Decimal("5"), pause_after_each_unit=True),
        )
    passed = m.await_args.args[1]
    assert isinstance(passed, srv._AuthoringRunCreateArgs)
    assert passed.plan_run_id == PLAN and passed.budget_usd == Decimal("5")
    assert passed.pause_after_each_unit is True
    # _present dropped omitted scope/level → sub-model defaults apply.
    assert passed.level == 3 and passed.scope == []


async def test_manage_create_requires_plan_budget_pause():
    with pytest.raises(ValueError, match="plan_run_id, budget_usd, and pause_after_each_unit"):
        await srv.composition_authoring_run_manage(
            _Ctx(), srv._AuthoringRunManageArgs(op="create", book_id=BOOK, plan_run_id=PLAN),
        )


async def test_manage_start_routes_and_needs_run_id():
    with patch.object(srv, "composition_authoring_run_start", AsyncMock(return_value={"ok": 1})) as m:
        await srv.composition_authoring_run_manage(
            _Ctx(),
            srv._AuthoringRunManageArgs(op="start", book_id=BOOK, run_id=RUN,
                                        pause_after_each_unit=False),
        )
    passed = m.await_args.args[1]
    assert isinstance(passed, srv._AuthoringRunStartArgs)
    assert passed.run_id == RUN and passed.pause_after_each_unit is False
    with pytest.raises(ValueError, match="run_id"):
        await srv.composition_authoring_run_manage(
            _Ctx(), srv._AuthoringRunManageArgs(op="start", book_id=BOOK),
        )


async def test_manage_gate_routes_not_revert():
    with patch.object(srv, "composition_authoring_run_gate", AsyncMock(return_value={"ok": 1})) as g, \
         patch.object(srv, "composition_authoring_run_revert_all", AsyncMock()) as rv:
        await srv.composition_authoring_run_manage(
            _Ctx(), srv._AuthoringRunManageArgs(op="gate", book_id=BOOK, run_id=RUN),
        )
    g.assert_awaited_once()
    rv.assert_not_awaited()
    assert g.await_args.args[1].run_id == RUN


async def test_manage_revert_all_routes():
    with patch.object(srv, "composition_authoring_run_revert_all", AsyncMock(return_value={"ok": 1})) as m:
        await srv.composition_authoring_run_manage(
            _Ctx(), srv._AuthoringRunManageArgs(op="revert_all", book_id=BOOK, run_id=RUN),
        )
    m.assert_awaited_once()
    assert m.await_args.args[1].run_id == RUN


async def test_manage_resume_routes():
    with patch.object(srv, "composition_authoring_run_resume", AsyncMock(return_value={"ok": 1})) as m:
        await srv.composition_authoring_run_manage(
            _Ctx(), srv._AuthoringRunManageArgs(op="resume", book_id=BOOK, run_id=RUN),
        )
    assert isinstance(m.await_args.args[1], srv._AuthoringRunResumeArgs)


# ── composition_authoring_run_review (A) ─────────────────────────────────────────


async def test_review_pause_routes_not_close():
    with patch.object(srv, "composition_authoring_run_pause", AsyncMock(return_value={"ok": 1})) as p, \
         patch.object(srv, "composition_authoring_run_close", AsyncMock()) as c:
        await srv.composition_authoring_run_review(
            _Ctx(), srv._AuthoringRunReviewArgs(op="pause", book_id=BOOK, run_id=RUN),
        )
    p.assert_awaited_once()
    c.assert_not_awaited()
    assert p.await_args.args[1].run_id == RUN


async def test_review_close_routes():
    with patch.object(srv, "composition_authoring_run_close", AsyncMock(return_value={"ok": 1})) as m:
        await srv.composition_authoring_run_review(
            _Ctx(), srv._AuthoringRunReviewArgs(op="close", book_id=BOOK, run_id=RUN),
        )
    assert isinstance(m.await_args.args[1], srv._AuthoringRunIdArgs)


async def test_review_accept_unit_routes_with_index():
    with patch.object(srv, "composition_authoring_run_accept_unit", AsyncMock(return_value={"ok": 1})) as m:
        await srv.composition_authoring_run_review(
            _Ctx(),
            srv._AuthoringRunReviewArgs(op="accept_unit", book_id=BOOK, run_id=RUN, unit_index=2),
        )
    passed = m.await_args.args[1]
    assert isinstance(passed, srv._AuthoringRunUnitArgs)
    assert passed.unit_index == 2 and passed.run_id == RUN


async def test_review_reject_unit_routes_not_accept():
    with patch.object(srv, "composition_authoring_run_reject_unit", AsyncMock(return_value={"ok": 1})) as r, \
         patch.object(srv, "composition_authoring_run_accept_unit", AsyncMock()) as a:
        await srv.composition_authoring_run_review(
            _Ctx(),
            srv._AuthoringRunReviewArgs(op="reject_unit", book_id=BOOK, run_id=RUN, unit_index=0),
        )
    r.assert_awaited_once()
    a.assert_not_awaited()


async def test_review_unit_ops_require_unit_index():
    with pytest.raises(ValueError, match="unit_index"):
        await srv.composition_authoring_run_review(
            _Ctx(), srv._AuthoringRunReviewArgs(op="accept_unit", book_id=BOOK, run_id=RUN),
        )
