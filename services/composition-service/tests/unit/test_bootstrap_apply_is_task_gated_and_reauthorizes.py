"""`plan_bootstrap_apply` runs task-shaped, and its ACCEPT re-checks the book grant.

🔴 WHY THIS TOOL AND NOT ITS FIVE NEIGHBOURS. `app/mcp/server.py` deliberately does NOT register
the ledger-guarded KIND-C confirms (decompile, motif_adopt, motif_mine, arc_import,
conformance_run) — their `_execute_*` reads the confirm TOKEN as a replay-ledger / billing key and
a durable resolver has none. `_execute_bootstrap_apply(payload, book_id, envelope_user)` takes no
token, so it CAN be gated. That distinction was verified from the executor signatures in
`app/routers/actions.py`, not from the comment — the comment does not name this tool at all, and
reading it alone would also have missed `composition_library_translate`, which DOES need the token.

🔴 THE SECURITY HALF, WHICH THE WORK-SCOPED RESOLVERS DO NOT HAVE. A durable task can sit pending
for as long as the TTL allows. The confirm route runs `authorize_book(..., EDIT)` immediately
before the effect; a resolver that skipped it would let a grant REVOKED between propose and accept
still apply the plan. `_resolve_publish` gets away with a bare existence re-fetch because a Work is
user-scoped and the kit's provide-input already checks caller == task owner — but a BOOK grant is
revocable by a third party, so owning the task is not the same question as still having access.

These are BEHAVIOURAL assertions on purpose. The sibling guard in
`test_bootstrap_apply_checks_the_proposal_before_minting.py` slices the handler's SOURCE and looks
for substrings; it stayed green through this change because the strings merely moved into the
fallback closure — which is exactly how a source-substring guard passes over a rewritten function.
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


def _server():
    import app.mcp.server as srv
    return srv


def test_the_descriptor_is_REGISTERED_in_the_task_store():
    """The gate is only real if the ACCEPT can be resolved. A `gate_or_confirm` call whose
    descriptor has no resolver opens a task nobody can drive — worse than not gating at all,
    because the human sees a pending card that can never complete."""
    srv = _server()
    reg = srv._task_store._resolvers
    assert srv._BOOTSTRAP_APPLY_DESCRIPTOR in reg, (
        f"{srv._BOOTSTRAP_APPLY_DESCRIPTOR} is gated but has no resolver — accepting its task "
        f"would strand. Registered: {sorted(reg)}")
    assert reg[srv._BOOTSTRAP_APPLY_DESCRIPTOR] is srv._resolve_bootstrap_apply


def test_the_ledger_guarded_five_stay_UNREGISTERED():
    """The other half of the same invariant, and it must not drift open. Registering one of these
    would hand a durable task to an effect that needs the confirm token, which resolves to an
    exception at accept time — after the human has approved."""
    srv = _server()
    reg = srv._task_store._resolvers
    for desc in ("composition.decompile_arcs", "composition.motif_adopt", "composition.motif_mine",
                 "composition.arc_import", "composition.conformance_run",
                 "composition.library_translate"):
        assert desc not in reg, (
            f"{desc} is ledger-guarded: its effect reads the confirm token, which a durable "
            f"resolver does not have. It must stay on the plain mint path.")


@pytest.mark.asyncio
async def test_the_resolver_DENIES_when_the_grant_is_gone():
    """🔴 THE FALSIFIER FOR THE RE-AUTHORIZATION. Delete the `authorize_book` call from
    `_resolve_bootstrap_apply` and this goes red: the effect would run for a caller whose EDIT
    grant was revoked while the task sat pending."""
    from fastapi import HTTPException

    from app.grant_deps import InsufficientGrant

    srv = _server()
    payload = {"book_id": str(uuid4()), "proposal_id": str(uuid4())}
    effect = AsyncMock()
    with patch("app.deps.get_grant_client_dep", AsyncMock(return_value=object())), \
         patch("app.grant_deps.authorize_book", AsyncMock(side_effect=InsufficientGrant())), \
         patch("app.routers.actions._execute_bootstrap_apply", effect):
        with pytest.raises(HTTPException) as ei:
            await srv._resolve_bootstrap_apply(str(uuid4()), payload, {})
    assert ei.value.status_code == 403
    effect.assert_not_awaited(), "the plan was applied despite a failed grant check"


@pytest.mark.asyncio
async def test_an_authority_OUTAGE_also_denies():
    """Fail CLOSED. `GrantAuthorityUnavailable` subclasses `OwnershipError`, so the same catch
    covers it — an accept that ran because the permission service was down is the one outcome
    worse than asking the human to retry."""
    from fastapi import HTTPException

    from app.grant_deps import GrantAuthorityUnavailable

    srv = _server()
    payload = {"book_id": str(uuid4()), "proposal_id": str(uuid4())}
    effect = AsyncMock()
    with patch("app.deps.get_grant_client_dep", AsyncMock(return_value=object())), \
         patch("app.grant_deps.authorize_book",
               AsyncMock(side_effect=GrantAuthorityUnavailable())), \
         patch("app.routers.actions._execute_bootstrap_apply", effect):
        with pytest.raises(HTTPException):
            await srv._resolve_bootstrap_apply(str(uuid4()), payload, {})
    effect.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_GRANTED_caller_reaches_the_effect():
    """The control. Without it the two denial tests above would pass just as well against a
    resolver that refuses everything — a guard whose subject cannot vary proves nothing."""
    srv = _server()
    book_id, pid, owner = str(uuid4()), str(uuid4()), str(uuid4())
    effect = AsyncMock(return_value={"applied": True})
    with patch("app.deps.get_grant_client_dep", AsyncMock(return_value=object())), \
         patch("app.grant_deps.authorize_book", AsyncMock(return_value=None)), \
         patch("app.routers.actions._execute_bootstrap_apply", effect):
        out = await srv._resolve_bootstrap_apply(owner, {"book_id": book_id,
                                                         "proposal_id": pid}, {})
    assert out == {"applied": True}
    effect.assert_awaited_once()
    # the effect is handed the BOOK from the payload and the TASK OWNER as the caller — never a
    # value the accepting client supplied, or a revoked user could ride someone else's task
    args = effect.await_args.args
    assert str(args[1]) == book_id and str(args[2]) == owner
