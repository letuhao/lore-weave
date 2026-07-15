"""Track D S-SPEND — the sync-tool-path spend-approval gate.

A ``_meta.paid`` tool (external paid search / an LLM research loop) spends real
money when CALLED. The background-job path already reserves spend; the SYNCHRONOUS
MCP tool-call path (the tool loop in ``_stream_with_tools``) had NO spend gate — a
model could loop a paid tool and burn the user's budget with zero consent. This
slice adds a consent gate on that path.

Load-bearing properties proven here:
* fires for a Tier-R paid tool (orthogonal to tier — the test a tier-coupled
  implementation fails),
* fires in ``ask`` mode (mode-independent — ask restricts mutation, not spend),
* an unpaid Tier-R tool does NOT prompt (negative control),
* a spend-allowlisted paid tool runs without re-prompting (persisted consent is
  CONSUMED),
* a paid Tier-A tool raises ONE card carrying BOTH consent kinds,
* the spend read fails CLOSED (spend is irreversible), unlike the mutation gate,
* a subagent cannot raise the card — it errors instead of spending,
* spend and mutation approvals are SEPARATE, independent rows.

These drive ``_stream_with_tools`` / the DB helpers directly with no real Postgres
or ports, so no ``xdist_group("pg")`` marker is needed.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.db import tool_approvals
from tests.conftest import TEST_MODEL_REF


# ── helpers ──────────────────────────────────────────────────────────────────

def _paid_tool(name: str = "glossary_web_search", *, tier: str = "R", paid: bool = True) -> dict:
    """A tool def with C-TOOL `_meta` and NO required args (so the missing-args
    interceptor upstream of the gate never fires — the call reaches the spend gate)."""
    meta: dict = {"tier": tier}
    if paid:
        meta["paid"] = True
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": "search the open web (costs money)",
            "parameters": {"type": "object", "properties": {}},
            "_meta": meta,
        },
    }


def _fake_client(tool_name: str):
    """A Client whose pass 0 calls ``tool_name`` with blank (but complete — no
    required) args, and whose pass 1 answers in text (only reached if pass 0 did
    NOT suspend)."""
    from loreweave_llm import ToolCallEvent, DoneEvent, TokenEvent

    passes = {"n": 0}

    class FakeClient:
        def __init__(self, **kw):
            pass

        async def aclose(self):
            pass

        def stream(self, request):
            i = passes["n"]
            passes["n"] += 1

            async def gen():
                if i == 0:
                    yield ToolCallEvent(index=0, id="c1", name=tool_name, arguments_delta="{}")
                    yield DoneEvent(finish_reason="tool_calls")
                else:
                    yield TokenEvent(delta="done")
                    yield DoneEvent(finish_reason="stop")
            return gen()

    return FakeClient


def _kc():
    kc = AsyncMock()
    kc.get_catalog_meta = MagicMock(return_value={})
    kc.mcp_execute_tool = AsyncMock(return_value={"success": True, "result": {"hits": []}})
    return kc


async def _drive(tool_def, *, decision_check, permission_mode="write", subagent_depth=0):
    """Run ONE tool-loop over ``tool_def`` (plain-index path — discovery off) and
    collect the yielded chunks."""
    import app.services.stream_service as ss

    name = tool_def["function"]["name"]
    kc = _kc()
    chunks = []
    with patch.object(ss, "Client", _fake_client(name)):
        async for ch in ss._stream_with_tools(
            model_source="user_model", model_ref=TEST_MODEL_REF, user_id="u",
            messages=[{"role": "user", "content": "look it up on the web"}],
            gen_params={"max_tokens": 100}, tools=[tool_def],
            knowledge_client=kc, session_id="s", project_id=None,
            permission_mode=permission_mode,
            decision_check=decision_check,
            subagent_depth=subagent_depth,
            allowed_tool_names={name} if subagent_depth else None,
        ):
            chunks.append(ch)
    return chunks, kc


def _suspends(chunks):
    return [c for c in chunks if "suspend" in c]


def _tool_calls(chunks):
    return [c["tool_call"] for c in chunks if "tool_call" in c]


# ── the gate ─────────────────────────────────────────────────────────────────

class TestSpendGate:
    @pytest.mark.asyncio
    async def test_paid_tier_r_tool_suspends_for_spend_approval(self):
        """THE test: a Tier-R PAID tool must suspend for a spend card — the one a
        tier-coupled implementation (gating only Tier-A) fails."""
        check = AsyncMock(return_value=None)
        chunks, kc = await _drive(_paid_tool(tier="R"), decision_check=check)

        kc.mcp_execute_tool.assert_not_awaited()  # never spent
        suspends = _suspends(chunks)
        assert len(suspends) == 1
        args = suspends[0]["suspend"]["pending_tool_call"]["args"]
        assert args["kind"] == "tool_approval"
        assert args["tool"] == "glossary_web_search"
        assert args["tier"] == "R"          # orthogonal to tier — still R
        assert args["spend"] is True         # wire signal for the FE
        assert args["approval_kinds"] == ["spend"]
        # the allowlist was consulted on the SPEND axis for the PROMPT. (Track C WS-3
        # also reads both axes up-front to honor a standing refusal, so this is no longer
        # the ONLY read — what matters is that the spend decision is what gates the card.)
        assert ("glossary_web_search", "spend") in [c.args for c in check.await_args_list]

    @pytest.mark.asyncio
    async def test_paid_tool_suspends_in_ask_mode(self):
        """Mode-independent: ask restricts MUTATION, not SPEND. A read-only paid
        research call in ask mode still costs money → still prompts."""
        check = AsyncMock(return_value=None)
        chunks, kc = await _drive(_paid_tool(tier="R"), decision_check=check, permission_mode="ask")

        kc.mcp_execute_tool.assert_not_awaited()
        suspends = _suspends(chunks)
        assert len(suspends) == 1
        assert suspends[0]["suspend"]["pending_tool_call"]["args"]["spend"] is True

    @pytest.mark.asyncio
    async def test_unpaid_tier_r_tool_does_not_suspend(self):
        """Negative control: a NON-paid Tier-R tool never raises a spend CARD.

        Track C WS-3 note — it IS still asked about (the standing-refusal read runs for
        every tool, because a "Never allow" must hold wherever the tool can execute), but
        with no decision on file it neither prompts nor blocks: it simply runs."""
        check = AsyncMock(return_value=None)
        chunks, kc = await _drive(_paid_tool(tier="R", paid=False), decision_check=check)

        assert _suspends(chunks) == []
        kc.mcp_execute_tool.assert_awaited_once()   # it just runs
        # no PROMPT was raised, which is what "does not touch the spend gate" means now
        assert all(c.args[1] in ("mutation", "spend") for c in check.await_args_list if len(c.args) > 1)

    @pytest.mark.asyncio
    async def test_spend_approved_tool_runs_without_reprompt(self):
        """Persisted consent is CONSUMED: once spend is allowlisted, the paid tool
        executes with no further prompt (proves the stored approval is READ)."""
        async def check(name, kind="mutation"):
            return "allow" if kind == "spend" else None  # spend already allowlisted

        chunks, kc = await _drive(_paid_tool(tier="R"), decision_check=check)

        assert _suspends(chunks) == []
        kc.mcp_execute_tool.assert_awaited_once()
        assert _tool_calls(chunks)[0]["ok"] is True

    @pytest.mark.asyncio
    async def test_paid_tier_a_tool_raises_single_card_with_both_kinds(self):
        """A paid Tier-A tool needs BOTH consents. Because the resume path executes
        the approved tool DIRECTLY (no loop re-entry), a call has exactly one suspend
        point — so it raises ONE card enumerating both kinds (not two prompts)."""
        check = AsyncMock(return_value=None)
        chunks, kc = await _drive(_paid_tool(tier="A"), decision_check=check, permission_mode="write")

        kc.mcp_execute_tool.assert_not_awaited()
        suspends = _suspends(chunks)
        assert len(suspends) == 1                    # ONE card, not two
        args = suspends[0]["suspend"]["pending_tool_call"]["args"]
        assert args["tier"] == "A"
        assert args["spend"] is True
        assert args["approval_kinds"] == ["spend", "mutation"]

    @pytest.mark.asyncio
    async def test_spend_read_error_fails_closed_and_prompts(self):
        """Spend is IRREVERSIBLE: a read failure fails CLOSED (still prompt) — the
        deliberate opposite of the mutation gate's fail-OPEN. A DB blip must never
        silently spend money."""
        check = AsyncMock(side_effect=RuntimeError("db down"))
        chunks, kc = await _drive(_paid_tool(tier="R"), decision_check=check)

        kc.mcp_execute_tool.assert_not_awaited()     # did NOT spend on doubt
        assert len(_suspends(chunks)) == 1

    @pytest.mark.asyncio
    async def test_unpaid_read_decision_error_fails_closed_and_skips(self):
        """RISK-2 (adversarial review 2026-07-15): a NON-paid Tier-R read the user may
        have set to 'Never allow' must NOT run when the decision read raises. It has no
        downstream prompt arm (not paid → no spend card; not Tier-A → no mutation card),
        so the deny-loop itself must fail CLOSED: skip the tool with a transient error,
        never dispatch it on doubt. (Contrast test_unpaid_tier_r_tool_does_not_suspend,
        where the read SUCCEEDS with None → the tool runs.)"""
        check = AsyncMock(side_effect=RuntimeError("db down"))
        chunks, kc = await _drive(_paid_tool(tier="R", paid=False), decision_check=check)

        kc.mcp_execute_tool.assert_not_awaited()     # did NOT run on an unreadable decision
        assert _suspends(chunks) == []               # a skip, not a prompt
        calls = _tool_calls(chunks)
        assert len(calls) == 1 and calls[0]["ok"] is False
        assert "could not be read" in (calls[0]["error"] or "")

    @pytest.mark.asyncio
    async def test_no_decision_check_does_not_gate(self):
        """decision_check=None (a caller not wired for consent) → the paid tool is
        not gated (matches the DR-C2 mutation-gate contract for the None case)."""
        chunks, kc = await _drive(_paid_tool(tier="R"), decision_check=None)
        assert _suspends(chunks) == []
        kc.mcp_execute_tool.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_subagent_paid_tool_errors_not_suspends(self):
        """A headless sub-run cannot raise the card — it must NOT spend. It returns
        a result.error the sub-model can adapt to, and never dispatches the tool."""
        check = AsyncMock(return_value=None)
        chunks, kc = await _drive(
            _paid_tool(tier="R"), decision_check=check,
            permission_mode="write", subagent_depth=1,
        )

        assert _suspends(chunks) == []
        kc.mcp_execute_tool.assert_not_awaited()
        tc = _tool_calls(chunks)[0]
        assert tc["ok"] is False
        assert "not pre-approved for spend" in tc["error"]


# ── the persistence (kind separation) ────────────────────────────────────────

from tests.fake_approvals_pool import FakeApprovalsPool as _FakePool


class TestApprovalKindSeparation:
    @pytest.mark.asyncio
    async def test_spend_and_mutation_are_independent_rows(self):
        pool = _FakePool()
        await tool_approvals.approve_tool(pool, "u", "glossary_web_search", "spend")

        # spend granted…
        assert await tool_approvals.is_tool_approved(pool, "u", "glossary_web_search", "spend") is True
        # …but mutation is NOT (a "may spend" grant is not a "may write" grant)
        assert await tool_approvals.is_tool_approved(pool, "u", "glossary_web_search", "mutation") is False
        # default kind is mutation → also not approved
        assert await tool_approvals.is_tool_approved(pool, "u", "glossary_web_search") is False

    @pytest.mark.asyncio
    async def test_mutation_uses_legacy_unnamespaced_key_spend_is_namespaced(self):
        pool = _FakePool()
        await tool_approvals.approve_tool(pool, "u", "book_create")            # mutation (default)
        await tool_approvals.approve_tool(pool, "u", "glossary_web_search", "spend")

        # mutation keeps the legacy bare tool_name (backward compat with pre-S-SPEND rows)
        assert "book_create" in pool.inserted_keys
        # spend is a DISTINCT namespaced row
        assert "spend::glossary_web_search" in pool.inserted_keys

    @pytest.mark.asyncio
    async def test_reverse_direction_mutation_grant_is_not_spend(self):
        pool = _FakePool()
        await tool_approvals.approve_tool(pool, "u", "glossary_web_search")  # mutation only
        assert await tool_approvals.is_tool_approved(pool, "u", "glossary_web_search", "mutation") is True
        assert await tool_approvals.is_tool_approved(pool, "u", "glossary_web_search", "spend") is False
