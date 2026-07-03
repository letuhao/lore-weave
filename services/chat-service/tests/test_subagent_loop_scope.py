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
