"""P5 REG-P5-01 — the loop-level defense-in-depth checks that only run inside a
NESTED subagent turn (`allowed_tool_names` set): the execute-time scope whitelist,
and the depth-0-only advertisement of `run_subagent`.

Reuses the test_permission_modes / test_stream_tools fake-client harness so we drive
the REAL `_stream_with_tools` loop deterministically (no live model).
"""

from __future__ import annotations

import json

import pytest
from unittest.mock import AsyncMock, MagicMock

from app.services.stream_service import _stream_with_tools
from app.services.subagent_runtime import build_run_subagent_tool
from tests.test_permission_modes import _catalog
from tests.test_stream_tools import (
    _drain,
    _envelope,
    _patch_client,
    done,
    tok,
    tool_frag,
    _FakeClient,
)


def _run(scripts, **kw):
    base = dict(
        model_source="user_model",
        model_ref="00000000-0000-0000-0000-000000000001",
        user_id="u1",
        messages=[{"role": "user", "content": "go"}],
        gen_params={},
        tools=_catalog(),
        session_id="s1",
        project_id="p1",
    )
    base.update(kw)
    return _stream_with_tools(**base)


class TestExecuteTimeWhitelist:
    @pytest.mark.asyncio
    async def test_out_of_scope_tierR_call_is_rejected_by_the_whitelist(self):
        # glossary_get_entity is tier R (so the ask-mode filter would NOT catch it)
        # but it is NOT in the subagent's allowed set → the whitelist must reject it,
        # and it must NEVER execute. This isolates the scope whitelist from ask mode.
        kc = AsyncMock()
        kc.get_catalog_meta = MagicMock(return_value={})
        scripts = [
            [
                tool_frag(index=0, id="c1", name="glossary_get_entity"),
                tool_frag(index=0, arguments_delta='{"id":"x"}'),
                done("tool_calls"),
            ],
            [tok("ok"), done("stop")],
        ]
        with _patch_client(scripts):
            chunks = await _drain(_run(
                scripts, knowledge_client=kc, permission_mode="ask",
                allowed_tool_names={"glossary_search"}, subagent_depth=1,
            ))
        kc.mcp_execute_tool.assert_not_awaited()
        tc = [c["tool_call"] for c in chunks if "tool_call" in c][0]
        assert tc["ok"] is False
        assert "tool scope" in tc["error"]
        # the sub-model got a self-correctable error result
        msgs = _FakeClient.instances[0].requests[1].messages
        tool_msg = next(m for m in msgs if m.get("role") == "tool")
        assert "tool scope" in json.loads(tool_msg["content"])["error"]

    @pytest.mark.asyncio
    async def test_in_scope_call_executes_in_the_subrun(self):
        kc = AsyncMock()
        kc.get_catalog_meta = MagicMock(return_value={})
        kc.mcp_execute_tool.return_value = _envelope(success=True, result={"hits": []})
        scripts = [
            [
                tool_frag(index=0, id="c1", name="glossary_search"),
                tool_frag(index=0, arguments_delta='{"q":"Kai"}'),
                done("tool_calls"),
            ],
            [tok("found"), done("stop")],
        ]
        with _patch_client(scripts):
            chunks = await _drain(_run(
                scripts, knowledge_client=kc, permission_mode="ask",
                allowed_tool_names={"glossary_search"}, subagent_depth=1,
            ))
        kc.mcp_execute_tool.assert_awaited_once()
        tc = [c["tool_call"] for c in chunks if "tool_call" in c][0]
        assert tc["ok"] is True

    @pytest.mark.asyncio
    async def test_top_level_run_without_whitelist_is_unaffected(self):
        # allowed_tool_names=None (a normal top-level turn) → NO whitelist rejection;
        # a tier-R read executes as usual (regression guard for the new branch).
        kc = AsyncMock()
        kc.get_catalog_meta = MagicMock(return_value={})
        kc.mcp_execute_tool.return_value = _envelope(success=True, result={"hits": []})
        scripts = [
            [
                tool_frag(index=0, id="c1", name="glossary_get_entity"),
                tool_frag(index=0, arguments_delta='{"id":"x"}'),
                done("tool_calls"),
            ],
            [tok("done"), done("stop")],
        ]
        with _patch_client(scripts):
            await _drain(_run(scripts, knowledge_client=kc, permission_mode="ask"))
        kc.mcp_execute_tool.assert_awaited_once()


class TestWriteDelegation:
    """D-REG-P5-SUBAGENT-WRITE-DELEGATION — a WRITE-mode sub-run (subagent_depth>0)
    may auto-commit an ALLOWLISTED Tier-A tool in its scope, but an UN-allowlisted
    Tier-A returns a result.error instead of suspending (a headless sub-run can't
    raise the approval card). Tenancy stays enforced at the tool layer regardless."""

    @pytest.mark.asyncio
    async def test_allowlisted_tier_a_executes_in_write_subrun(self):
        kc = AsyncMock()
        kc.get_catalog_meta = MagicMock(return_value={})
        kc.mcp_execute_tool.return_value = _envelope(success=True, result={"book_id": "b1"})
        check = AsyncMock(return_value="allow")  # book_create IS allowlisted
        scripts = [
            [
                tool_frag(index=0, id="c1", name="book_create"),
                tool_frag(index=0, arguments_delta='{"title":"X"}'),
                done("tool_calls"),
            ],
            [tok("made it"), done("stop")],
        ]
        with _patch_client(scripts):
            chunks = await _drain(_run(
                scripts, knowledge_client=kc, permission_mode="write",
                decision_check=check,
                allowed_tool_names={"book_create"}, subagent_depth=1,
            ))
        kc.mcp_execute_tool.assert_awaited_once()            # it really wrote
        # the mutation grant is what let it auto-commit. (WS-3 also reads both axes
        # up-front for the standing-refusal check, so this is no longer the only await.)
        assert ("book_create",) in [c.args for c in check.await_args_list]
        assert not [c for c in chunks if "suspend" in c]     # a sub-run never suspends
        tc = [c["tool_call"] for c in chunks if "tool_call" in c][0]
        assert tc["ok"] is True

    @pytest.mark.asyncio
    async def test_unallowlisted_tier_a_errors_not_suspends_in_write_subrun(self):
        kc = AsyncMock()
        kc.get_catalog_meta = MagicMock(return_value={})
        check = AsyncMock(return_value=None)  # book_create NOT allowlisted
        scripts = [
            [
                tool_frag(index=0, id="c1", name="book_create"),
                tool_frag(index=0, arguments_delta='{"title":"X"}'),
                done("tool_calls"),
            ],
            [tok("ok, skipping"), done("stop")],
        ]
        with _patch_client(scripts):
            chunks = await _drain(_run(
                scripts, knowledge_client=kc, permission_mode="write",
                decision_check=check,
                allowed_tool_names={"book_create"}, subagent_depth=1,
            ))
        kc.mcp_execute_tool.assert_not_awaited()             # never executed
        assert not [c for c in chunks if "suspend" in c]     # NOT suspended (the fix)
        tc = [c["tool_call"] for c in chunks if "tool_call" in c][0]
        assert tc["ok"] is False
        assert "not pre-approved" in tc["error"]
        # the sub-model received a self-correctable error result (no silent no-op)
        msgs = _FakeClient.instances[0].requests[1].messages
        tool_msg = next(m for m in msgs if m.get("role") == "tool")
        assert "not pre-approved" in json.loads(tool_msg["content"])["error"]

    @pytest.mark.asyncio
    async def test_volume_cap_errors_not_suspends_in_write_subrun(self):
        # /review-impl: with Tier-A now correctly tiered in a sub-run, the per-op
        # auto-write cap (5) would fire a confirm_action SUSPEND that a headless
        # sub-run swallows silently. It must instead return a result.error — the 6th
        # same-op Tier-A call is capped, the first 5 execute.
        kc = AsyncMock()
        kc.get_catalog_meta = MagicMock(return_value={})
        kc.mcp_execute_tool.return_value = _envelope(success=True, result={"book_id": "b"})
        check = AsyncMock(return_value="allow")  # all allowlisted → they auto-commit
        frags = []
        for i in range(6):  # TIER_A_SAME_OP_CAP=5 → the 6th trips the per-op cap
            frags.append(tool_frag(index=i, id=f"c{i}", name="book_create"))
            frags.append(tool_frag(index=i, arguments_delta='{"title":"X"}'))
        frags.append(done("tool_calls"))
        scripts = [frags, [tok("summarized"), done("stop")]]
        with _patch_client(scripts):
            chunks = await _drain(_run(
                scripts, knowledge_client=kc, permission_mode="write",
                decision_check=check,
                allowed_tool_names={"book_create"}, subagent_depth=1,
            ))
        assert kc.mcp_execute_tool.await_count == 5          # first 5 wrote
        assert not [c for c in chunks if "suspend" in c]     # capped call did NOT suspend
        capped = [c["tool_call"] for c in chunks if "tool_call" in c and not c["tool_call"]["ok"]]
        assert len(capped) == 1
        assert "cannot request batch confirmation" in capped[0]["error"]


class TestRunSubagentAdvertisement:
    @pytest.mark.asyncio
    async def test_subagent_tool_advertised_at_depth_0(self):
        kc = AsyncMock()
        kc.get_catalog_meta = MagicMock(return_value={})
        sa_tool = build_run_subagent_tool(["lore-scout"])
        scripts = [[tok("hi"), done("stop")]]
        with _patch_client(scripts):
            await _drain(_run(
                scripts, knowledge_client=kc, permission_mode="write",
                subagent_tool=sa_tool, subagent_defs={"lore-scout": {}},
            ))
        offered = {t["function"]["name"] for t in _FakeClient.instances[0].requests[0].tools}
        assert "run_subagent" in offered

    @pytest.mark.asyncio
    async def test_subagent_tool_NOT_advertised_when_nested(self):
        # Inside a nested run (subagent_depth=1) run_subagent must never be offered —
        # a subagent can't spawn another (no recursion).
        kc = AsyncMock()
        kc.get_catalog_meta = MagicMock(return_value={})
        sa_tool = build_run_subagent_tool(["lore-scout"])
        scripts = [[tok("hi"), done("stop")]]
        with _patch_client(scripts):
            await _drain(_run(
                scripts, knowledge_client=kc, permission_mode="ask",
                subagent_tool=sa_tool, subagent_defs={"lore-scout": {}},
                allowed_tool_names={"glossary_search"}, subagent_depth=1,
            ))
        offered = {t["function"]["name"] for t in _FakeClient.instances[0].requests[0].tools}
        assert "run_subagent" not in offered
