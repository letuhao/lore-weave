"""D-APPROVE-THEN-FAIL — op=create minted a cost-bearing card for a plan run that did not exist.

The lookup lived ONLY in the accept effect (`_execute_authoring_run_create` ->
`svc.create` -> `get_for_book` -> LookupError), which surfaces as
`HTTPException(400, {"code": "action_error"})` with the message discarded. So the author was
shown an approval card for an authoring run that could not be created, approved it, and got a
bare 400 with nothing to act on. Measured 5/5 (batch c-authrun2) and 2/2 (c-authrun4).

Refusing at PROPOSE cannot block a call that would have worked — the accept performs the
identical lookup — and it turns an opaque post-approval failure into a refusal that names where
the real id comes from.
"""
from __future__ import annotations

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import app.mcp.server as srv

BOOK = "cccccccc-cccc-cccc-cccc-cccccccccccc"
PLAN = "22222222-2222-2222-2222-222222222222"


class _Ctx:
    user_id = None
    session_id = "s"
    project_id = None
    trace_id = None
    internal_token = "t"


def _args(plan_run_id=PLAN):
    return srv._AuthoringRunCreateArgs(
        book_id=BOOK, plan_run_id=plan_run_id,
        budget_usd=Decimal("5"), pause_after_each_unit=True,
    )


def _patched(found):
    """_gate/pool stubbed; the repo's answer is the only variable."""
    repo = MagicMock()
    repo.return_value.get_for_book = AsyncMock(return_value=found)
    # `_ctx` builds a real ToolContext off request headers this stub has none of. Patching it is
    # what keeps a RED here meaning "the check did not fire" rather than "the fixture is thin" —
    # the first version of this test failed on AttributeError, which looks identical in a summary
    # line and proves nothing at all.
    return (patch.object(srv, "_ctx", MagicMock(return_value=MagicMock(user_id=None))),
            patch.object(srv, "_gate", AsyncMock()),
            patch.object(srv, "get_pool", MagicMock()),
            patch("app.db.repositories.plan_runs.PlanRunsRepo", repo))


async def test_a_plan_run_not_on_this_book_is_refused_at_propose():
    a, b, c, dd = _patched(found=None)
    with a, b, c, dd, pytest.raises(ValueError, match="no plan run"):
        await srv.composition_authoring_run_create(_Ctx(), _args())


async def test_the_refusal_names_where_the_real_id_comes_from():
    """A refusal the model cannot act on just becomes a retry of the same call."""
    a, b, c, dd = _patched(found=None)
    with a, b, c, dd, pytest.raises(ValueError) as e:
        await srv.composition_authoring_run_create(_Ctx(), _args())
    msg = str(e.value)
    assert "composition_package_tree" in msg, "the existing-plan supplier is not named"
    assert "chapter id" in msg, "the measured cross-wire is not called out"


async def test_a_malformed_plan_run_id_is_refused_as_a_uuid():
    a, b, c, dd = _patched(found=None)
    with a, b, c, dd, pytest.raises(Exception) as e:
        await srv.composition_authoring_run_create(_Ctx(), _args(plan_run_id="default"))
    assert "plan_run_id" in str(e.value)


async def test_a_plan_run_THAT_EXISTS_is_not_refused_by_this_check():
    """🔴 THE PRECISION HALF. If this check fired on a good id the tool would be unusable, and
    the test above would still pass. The call is allowed to fail LATER for its own reasons —
    what must not happen is the plan-run refusal."""
    a, b, c, dd = _patched(found=object())
    with a, b, c, dd:
        try:
            await srv.composition_authoring_run_create(_Ctx(), _args())
        except Exception as exc:  # noqa: BLE001 — downstream minting is out of scope here
            assert "no plan run" not in str(exc), (
                "a plan run that EXISTS was refused as absent"
            )
