"""D-SCHEMA-WRITE-APPLIES-ON-A-SIGNATURE-THAT-DOES-NOT-EXIST.

`kg_triage_schema_write` took the caller's `signature` on trust. Measured on the deployed
build 2026-08-23 and again 2026-08-26:

    signature='no-such-signature-000', action=add_to_schema, code='probe_edge_absent'
      mint    -> {"proposed": true, "summary": "... (schema v2 -> v3 on confirm)"}
      confirm -> {"applied": true, "schema_version": 2, "stamped": 0, "resolved": 0}

`resolved: 0` is the tell: the effect knew it had closed no triage group and mutated the
project's ontology anyway. The signature IS the authority for the change — it is the claim
that a real proposal needed this edge type — so an unvalidated one lets any caller rewrite a
project ontology, with `applied: true` making it indistinguishable downstream.

Only an EMPTY signature was refused, and that is a min_length validator on the argument, not
a check that the group exists.

THE CHECK ALREADY EXISTED ONE FUNCTION AWAY: `_handle_kg_triage_resolve` confirms the group
before resolving it. The tool that merely closes triage items validated its signature; the
tool that rewrites the ontology did not.

The guard is at the MINT, not in the shared apply effect: this path mints a token and never
touches the items, so they are still PENDING at confirm, while the REST resolve route reaches
that same effect with its rows ALREADY resolved. Refusing on a zero count inside the effect
would break that caller — see test_the_shared_apply_effect_is_left_alone.
"""
from __future__ import annotations

import inspect
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.tools.executor import execute_tool

from tests.unit.test_graph_schema_tools import _ctx


def _schemas(version: int = 4):
    schemas = AsyncMock()
    schemas.active_project_schema = AsyncMock(
        return_value=SimpleNamespace(schema_id=uuid4(), schema_version=version)
    )
    return schemas


def _triage(pending: list | None):
    repo = AsyncMock()
    repo.list_pending_for_signature = AsyncMock(return_value=pending)
    return repo


ARGS = {
    "signature": "no-such-signature-000",
    "action": "add_to_schema",
    "code": "probe_edge_absent",
    "label": "probe",
}


@pytest.mark.asyncio
async def test_an_invented_signature_mints_no_token():
    """The original defect, verbatim: a signature naming no open group must not mint."""
    ctx = _ctx(graph_schemas_repo=_schemas(), triage_repo=_triage([]))
    res = await execute_tool(ctx, "kg_triage_schema_write", dict(ARGS))
    assert not res.success
    assert "no pending triage items" in res.error.lower()


@pytest.mark.asyncio
async def test_the_refusal_names_the_signature_and_its_supplier():
    """A caller holding no valid signature needs the SOURCE, not just the complaint —
    and the echo is what makes a typo'd or truncated signature visible in its own text."""
    ctx = _ctx(graph_schemas_repo=_schemas(), triage_repo=_triage([]))
    res = await execute_tool(ctx, "kg_triage_schema_write", dict(ARGS))
    assert "no-such-signature-000" in res.error
    assert "kg_triage_list" in res.error
    # It must also say the ontology was NOT changed — the whole confusion of the defect
    # was a response that could not be told apart from a real application.
    assert "unchanged" in res.error.lower()


@pytest.mark.asyncio
async def test_a_real_signature_still_mints():
    """RECALL. The guard must not cost the legitimate path: a signature with open items
    mints exactly as before."""
    ctx = _ctx(
        graph_schemas_repo=_schemas(version=4),
        triage_repo=_triage([SimpleNamespace(item_type="edge_kind_unknown")]),
    )
    res = await execute_tool(ctx, "kg_triage_schema_write", dict(ARGS))
    assert res.success, res.error
    assert res.result["proposed"] is True
    assert res.result["confirm_token"]


@pytest.mark.asyncio
async def test_the_signature_is_verified_within_the_caller_scope():
    """The lookup is scoped to (owner, project) — so a signature that is real but belongs
    to someone else's project is refused by the SAME message as one that never existed.
    Not-found and not-permitted stay uniform (H13: no existence oracle)."""
    triage = _triage([])
    ctx = _ctx(graph_schemas_repo=_schemas(), triage_repo=triage)
    await execute_tool(ctx, "kg_triage_schema_write", dict(ARGS))
    kwargs = triage.list_pending_for_signature.await_args.kwargs
    assert kwargs["signature"] == "no-such-signature-000"
    assert kwargs["user_id"] is not None
    assert kwargs["project_id"] == str(ctx.project_id)


@pytest.mark.asyncio
async def test_an_unavailable_triage_repo_fails_CLOSED():
    """A guard that silently skips when its dependency is missing is not a guard. If the
    signature cannot be verified, the ontology change does not get proposed."""
    ctx = _ctx(graph_schemas_repo=_schemas(), triage_repo=None)
    res = await execute_tool(ctx, "kg_triage_schema_write", dict(ARGS))
    assert not res.success
    assert "cannot verify" in res.error.lower()


@pytest.mark.asyncio
async def test_no_token_is_minted_before_the_signature_is_checked():
    """CLASS. The verification must precede the mint in the source, not merely accompany
    it — a check placed after mint_action_token would leave a live token behind on every
    refusal, which is the defect with extra steps."""
    from app.tools import graph_schema_tools as gst

    src = inspect.getsource(gst._handle_kg_triage_schema_write)
    assert "list_pending_for_signature" in src, "the mint path must verify the signature"
    assert src.index("list_pending_for_signature") < src.index("mint_action_token"), (
        "the signature check must run BEFORE the token is minted"
    )


def test_the_shared_apply_effect_is_left_alone():
    """The confirm-time effect is shared with the REST resolve route, which arrives with
    its triage rows ALREADY resolved (`resolve_signature` only touches PENDING). A
    zero-resolved refusal there would break that caller, so the authority check belongs at
    the mint. This pins the reasoning: if someone later adds such a refusal to the effect,
    they have to come and read this."""
    from app.ontology import triage_schema_write_effect as eff

    src = inspect.getsource(eff.apply_triage_schema_write)
    assert "resolved = 0" in src or "resolved = await" in src
    assert "raise" not in src.split("resolved = await")[-1].split("return")[0], (
        "the effect must not start refusing on a zero resolve count — the REST path "
        "legitimately resolves nothing here"
    )
