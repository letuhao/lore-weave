"""ARCH-1 C6 — frontend-tool (editor write-back) suspend/resume tests.

Reuses the _FakeClient scripting harness from test_stream_tools. Covers:
 - the propose_edit schema + name set,
 - the tool loop SUSPENDING on a frontend tool (no server execution, a `suspend`
   chunk with the rehydrate state),
 - a backend tool in the SAME pass still executing before the suspend,
 - tool-def gating (advertised only for agui + editor_context),
 - the emitter's tool_call_pending + suspended finish.
"""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from app.config import settings
from app.db.suspended_runs import SuspendedRun
from app.models import ProviderCredentials
from app.services.frontend_tools import (
    FRONTEND_TOOL_NAMES,
    GLOSSARY_CONFIRM_ACTION_TOOL,
    GLOSSARY_PROPOSE_EDIT_TOOL,
    PROPOSE_EDIT_TOOL,
    UI_FOCUS_MANUSCRIPT_UNIT_TOOL,
    UI_OPEN_STUDIO_PANEL_TOOL,
    frontend_tool_defs,
    is_frontend_tool,
)
from app.services.stream_events import AgUiEmitter, LegacyEmitter
from app.services.stream_service import resume_stream_response
from tests.conftest import TEST_MODEL_REF, TEST_SESSION_ID, TEST_USER_ID
from tests.test_stream_service import _make_pool_with_conn
from tests.test_stream_tools import (
    _FakeClient,
    _drain,
    _envelope,
    _patch_client,
    _run,
    done,
    tok,
    tool_frag,
    usage,
)


# ── schema / name set ────────────────────────────────────────────────────────


class TestFrontendToolDefs:
    def test_propose_edit_is_no_longer_a_frontend_tool(self):
        # Phase 2 (P2.2) — propose_edit moved to ai-gateway as a consumer-local tool
        # that returns a GATED proposal directive; chat-service stops intercepting it
        # as a frontend tool (it routes to ai-gateway, then suspends on the directive).
        assert not is_frontend_tool("propose_edit")
        assert "propose_edit" not in FRONTEND_TOOL_NAMES

    def test_glossary_edit_is_a_frontend_tool(self):
        assert is_frontend_tool("glossary_propose_entity_edit")
        assert "glossary_propose_entity_edit" in FRONTEND_TOOL_NAMES

    def test_glossary_confirm_action_is_a_frontend_tool(self):
        assert is_frontend_tool("glossary_confirm_action")
        assert "glossary_confirm_action" in FRONTEND_TOOL_NAMES

    def test_glossary_confirm_action_schema_is_wire_standard(self):
        d = GLOSSARY_CONFIRM_ACTION_TOOL
        assert d["function"]["name"] == "glossary_confirm_action"
        params = d["function"]["parameters"]
        assert set(params["required"]) == {"confirm_token", "descriptor", "title"}

    def test_glossary_skill_prompt_references_the_real_tool_names(self):
        """P5 drift guard: the static glossary-skill prompt instructs the LLM by
        tool name. If a glossary frontend tool is renamed in FRONTEND_TOOL_NAMES,
        the prompt must be updated too — else the LLM is told to call a tool that
        no longer exists and nothing fails. Catch that drift here."""
        from app.services.glossary_skill import GLOSSARY_SKILL_PROMPT
        glossary_frontend_tools = {n for n in FRONTEND_TOOL_NAMES if n.startswith("glossary_")}
        # sanity: there ARE glossary frontend tools to check
        assert glossary_frontend_tools
        for name in glossary_frontend_tools:
            assert name in GLOSSARY_SKILL_PROMPT, f"skill prompt is missing tool name {name!r}"

    def test_glossary_skill_prompt_mandates_one_card_batch(self):
        """#27/#29/#30 regression: the skill must steer multi-write goals to ONE
        batched card and forbid looping the single-propose tools — the run lifecycle
        honours only one confirm card per turn, so a loop produces dead, un-confirmable
        cards. If this guidance is lost, a weak model regresses to the N-card failure.

        N5a (2026-07-18 F3) SPLIT the glossary skill: the always-injected CORE keeps the
        ENTITY multi-write steering (glossary_propose_entities, "1+ items in one call"),
        while the ONTOLOGY batch guidance (glossary_propose_batch for kinds/attributes) +
        the hard one-card/no-loop rule moved to GLOSSARY_SHAPING_PROMPT — injected only
        when the author actually does ontology work (pin / world-setup intent), which is
        the only context that batches ontology writes. This asserts the guardrail is
        preserved in BOTH halves at its correct home, not that it all lives in core."""
        from app.services.glossary_skill import GLOSSARY_SKILL_PROMPT, GLOSSARY_SHAPING_PROMPT
        # Ontology batch home (shaping): the deterministic batch path is named + the hard
        # one-card-per-turn rule and the no-loop prohibition are present.
        assert "glossary_propose_batch" in GLOSSARY_SHAPING_PROMPT
        assert "ONE confirm card per turn" in GLOSSARY_SHAPING_PROMPT
        shap = GLOSSARY_SHAPING_PROMPT.lower()
        assert "never" in shap and "loop" in shap
        # Core (always-injected) must still steer ENTITY multi-write to a single batched
        # call, so the common "add these N characters" turn can't regress to N dead cards.
        assert "glossary_propose_entities" in GLOSSARY_SKILL_PROMPT
        assert "in one call" in GLOSSARY_SKILL_PROMPT

    def test_memory_tools_are_not_frontend(self):
        assert not is_frontend_tool("memory_search")
        assert not is_frontend_tool("memory_remember")

    def test_schema_is_wire_standard_openai_function(self):
        d = PROPOSE_EDIT_TOOL
        assert d["type"] == "function"
        assert d["function"]["name"] == "propose_edit"
        params = d["function"]["parameters"]
        assert set(params["required"]) == {"operation", "text"}
        assert params["properties"]["operation"]["enum"] == ["insert_at_cursor", "replace_selection"]
        # no non-standard keys leak to the provider
        assert "execution_location" not in d and "execution_location" not in d["function"]

    def test_glossary_edit_schema_is_wire_standard(self):
        d = GLOSSARY_PROPOSE_EDIT_TOOL
        assert d["type"] == "function"
        assert d["function"]["name"] == "glossary_propose_entity_edit"
        params = d["function"]["parameters"]
        # EDIT-ATOMIC: top-level args are the entity + base_version + a changes[] array.
        assert set(params["required"]) == {"book_id", "entity_id", "base_version", "changes"}
        changes = params["properties"]["changes"]
        assert changes["type"] == "array"
        item = changes["items"]
        assert set(item["required"]) == {"target", "field_label", "old_value", "new_value"}
        assert item["properties"]["target"]["enum"] == ["short_description", "attribute"]

    def test_frontend_tool_defs_are_surface_scoped(self):
        # editor surface → prose write-back only
        assert frontend_tool_defs(editor=True, book_scoped=False) == [PROPOSE_EDIT_TOOL]
        # glossary-page surface (book-scoped, not editor) → glossary edit + action confirm
        assert frontend_tool_defs(editor=False, book_scoped=True) == [
            GLOSSARY_PROPOSE_EDIT_TOOL, GLOSSARY_CONFIRM_ACTION_TOOL,
        ]
        # editor chat is also book-scoped → prose edit + both glossary tools
        assert frontend_tool_defs(editor=True, book_scoped=True) == [
            PROPOSE_EDIT_TOOL, GLOSSARY_PROPOSE_EDIT_TOOL, GLOSSARY_CONFIRM_ACTION_TOOL,
        ]
        # neither surface → nothing
        assert frontend_tool_defs() == []

    def test_ui_tools_are_no_longer_frontend_tools(self):
        # Phase 3 (P3.2) — the KIND-A ui_* tools moved to ai-gateway as consumer-local
        # directive tools; chat-service no longer intercepts/suspends on them (so they
        # route to ai-gateway and return an io.loreweave/ui-directive result). They are
        # still ADVERTISED (nav via the federated catalog, studio via frontend_tool_defs).
        for name in (
            "ui_navigate", "ui_open_book", "ui_open_chapter", "ui_show_panel",
            "ui_watch_job", "ui_open_studio_panel", "ui_focus_manuscript_unit",
        ):
            assert not is_frontend_tool(name), f"{name} must no longer be a frontend tool"
            assert name not in FRONTEND_TOOL_NAMES

    def test_studio_surface_advertises_only_the_studio_nav_tools(self):
        # studio flag adds ONLY the two dock-nav tools; independent of editor/book_scoped.
        assert frontend_tool_defs(studio=True) == [UI_OPEN_STUDIO_PANEL_TOOL, UI_FOCUS_MANUSCRIPT_UNIT_TOOL]
        # not advertised without the studio flag (a non-studio chat never suspends on them)
        assert UI_OPEN_STUDIO_PANEL_TOOL not in frontend_tool_defs(editor=True, book_scoped=True)

    def test_studio_ui_tool_schemas_are_wire_standard(self):
        # NOTE: this used to also assert `panel_id`'s enum against a hand-copied literal
        # list — that list drifted stale at least twice (missing context-inspector,
        # sharing, book-settings, translation, enrichment-*, user-guide, agent-mode) because
        # nothing forced it to stay in sync with the real enum. The actual anti-drift
        # mechanism for that is test_frontend_tools_contract.py's committed
        # contracts/frontend-tools.contract.json (regenerated via WRITE_FRONTEND_CONTRACT=1),
        # which the FE guard also reads — duplicating the list here only added a second,
        # unmaintained copy that could fail for reasons unrelated to whatever change
        # actually broke the contract. Keep this test to what it can uniquely catch:
        # wire shape + no duplicate/empty enum values.
        p = UI_OPEN_STUDIO_PANEL_TOOL["function"]
        assert p["name"] == "ui_open_studio_panel"
        assert set(p["parameters"]["required"]) == {"panel_id"}
        # panel_id is enum-constrained so a weak model can't drift the value (or the arg name) —
        # a live gemma-26b smoke otherwise sent the ui_show_panel `panel` arg + guessed a value.
        panel_ids = p["parameters"]["properties"]["panel_id"]["enum"]
        assert panel_ids, "panel_id must declare a non-empty enum"
        assert all(isinstance(v, str) and v for v in panel_ids), "every panel_id value must be a non-empty string"
        assert len(panel_ids) == len(set(panel_ids)), "panel_id enum has a duplicate value"
        assert "agent-mode" in panel_ids  # 20_agent_mode.md D1 — mission control panel
        f = UI_FOCUS_MANUSCRIPT_UNIT_TOOL["function"]
        assert f["name"] == "ui_focus_manuscript_unit"
        assert set(f["parameters"]["required"]) == {"chapter_id"}


# ── the suspend in the tool loop ─────────────────────────────────────────────


class TestSuspendLoop:
    @pytest.mark.asyncio
    async def test_confirm_action_frontend_tool_suspends_without_executing(self):
        """A still-frontend tool (confirm_action) yields a `suspend` chunk carrying the
        rehydrate state and does NOT call knowledge_client.execute_tool (the classic
        frontend-tool suspend path, kept after propose_edit migrated to ai-gateway)."""
        kc = AsyncMock()
        args = '{"confirm_token":"tok","descriptor":"book.publish","title":"Publish?"}'
        scripts = [[
            tool_frag(index=0, id="call_fe", name="confirm_action"),
            tool_frag(index=0, arguments_delta=args),
            usage(10, 4),
            done("tool_calls"),
        ]]
        with _patch_client(scripts):
            chunks = await _drain(_run(
                scripts, knowledge_client=kc,
                tools=[{"type": "function", "function": {"name": "confirm_action"}}],
            ))
        # never executed server-side (a frontend tool suspends, it doesn't call mcp)
        kc.mcp_execute_tool.assert_not_awaited()
        suspends = [c for c in chunks if "suspend" in c]
        assert len(suspends) == 1
        s = suspends[0]["suspend"]
        assert s["pending_tool_call"]["name"] == "confirm_action"
        assert s["pending_tool_call"]["id"] == "call_fe"
        assert s["input_tokens"] == 10 and s["output_tokens"] == 4
        assert any(m.get("role") == "assistant" and m.get("tool_calls") for m in s["working"])

    @pytest.mark.asyncio
    async def test_propose_edit_suspends_via_the_gated_proposal_directive(self):
        """Phase 2 (P2.2) — propose_edit now ROUTES to ai-gateway (a real mcp call) which
        returns a GATED proposal directive; chat-service detects it and suspends with the
        SAME pending shape the old frontend-tool suspend used (so ProposeEditCard is
        unchanged). Contrast the confirm_action test: propose_edit DOES call mcp now."""
        kc = AsyncMock()
        kc.mcp_execute_tool.return_value = _envelope(success=True, result={
            "type": "io.loreweave/propose-edit", "operation": "insert_at_cursor", "text": "Hi",
        })
        scripts = [[
            tool_frag(index=0, id="call_pe", name="propose_edit"),
            tool_frag(index=0, arguments_delta='{"operation":"insert_at_cursor","text":"Hi"}'),
            usage(10, 4),
            done("tool_calls"),
        ]]
        with _patch_client(scripts):
            chunks = await _drain(_run(
                scripts, knowledge_client=kc,
                tools=[{"type": "function", "function": {"name": "propose_edit"}}],
            ))
        # propose_edit IS executed via ai-gateway now (returns the proposal directive)
        kc.mcp_execute_tool.assert_awaited_once()
        suspends = [c for c in chunks if "suspend" in c]
        assert len(suspends) == 1
        s = suspends[0]["suspend"]
        assert s["pending_tool_call"]["name"] == "propose_edit"
        assert s["pending_tool_call"]["id"] == "call_pe"
        # reconstructed to the legacy shape so ProposeEditCard renders unchanged
        assert s["pending_tool_call"]["args"] == {"operation": "insert_at_cursor", "text": "Hi"}
        # NOT a durable task (client-effect gate → resumed like a frontend tool)
        assert "task" not in s["pending_tool_call"]

    @pytest.mark.asyncio
    async def test_backend_tool_executes_then_suspends_on_propose_edit_directive(self):
        """A pass with memory_search AND propose_edit: both call mcp now (memory returns
        hits, propose_edit returns the proposal directive), then the loop suspends on the
        propose_edit directive with the memory result already in `working`."""
        kc = AsyncMock()
        kc.mcp_execute_tool.side_effect = [
            _envelope(success=True, result={"hits": []}),  # memory_search
            _envelope(success=True, result={  # propose_edit → proposal directive
                "type": "io.loreweave/propose-edit", "operation": "insert_at_cursor", "text": "x"}),
        ]
        scripts = [[
            tool_frag(index=0, id="call_mem", name="memory_search"),
            tool_frag(index=0, arguments_delta='{"query":"Kai"}'),
            tool_frag(index=1, id="call_pe", name="propose_edit"),
            tool_frag(index=1, arguments_delta='{"operation":"insert_at_cursor","text":"x"}'),
            usage(5, 2),
            done("tool_calls"),
        ]]
        with _patch_client(scripts):
            chunks = await _drain(_run(
                scripts, knowledge_client=kc,
                tools=[{"type": "function", "function": {"name": "memory_search"}},
                       {"type": "function", "function": {"name": "propose_edit"}}],
            ))
        # both tools executed (memory + propose_edit route through mcp now)
        assert kc.mcp_execute_tool.await_count == 2
        tool_chunks = [c for c in chunks if "tool_call" in c]
        assert [c["tool_call"]["tool"] for c in tool_chunks] == ["memory_search"]
        suspends = [c for c in chunks if "suspend" in c]
        assert len(suspends) == 1
        assert suspends[0]["suspend"]["pending_tool_call"]["name"] == "propose_edit"
        working = suspends[0]["suspend"]["working"]
        assert any(m.get("role") == "tool" and m.get("tool_call_id") == "call_mem" for m in working)

    @pytest.mark.asyncio
    async def test_memory_only_pass_is_unchanged(self):
        """Regression: a pass with only a memory tool still executes inline and
        loops to a normal text answer (no suspend)."""
        kc = AsyncMock()
        kc.mcp_execute_tool.return_value = _envelope(success=True, result={"hits": []})
        scripts = [
            [tool_frag(index=0, id="c1", name="memory_search"),
             tool_frag(index=0, arguments_delta='{"query":"Kai"}'),
             usage(3, 1), done("tool_calls")],
            [tok("Kai is a knight."), usage(2, 5), done("stop")],
        ]
        with _patch_client(scripts):
            chunks = await _drain(_run(
                scripts, knowledge_client=kc,
                tools=[{"type": "function", "function": {"name": "memory_search"}}],
            ))
        kc.mcp_execute_tool.assert_awaited_once()
        assert not [c for c in chunks if "suspend" in c]
        # final text chunk present
        assert any(c.get("content") == "Kai is a knight." for c in chunks)


# ── emitter pending + suspended finish ───────────────────────────────────────


def _parse(line: str) -> dict:
    return json.loads(line.removeprefix("data: ").strip())


class TestPendingEmitter:
    def test_agui_tool_call_pending_omits_result(self):
        # Use the PRODUCTION shape: the suspend chunk's pending_tool_call is
        # {id, name, args} (NOT {tool}). A live smoke caught a KeyError here
        # because the test previously used {tool} while the producer emits
        # {name} — the boundary mismatch slipped past both isolated tests.
        em = AgUiEmitter(thread_id="s", message_id="m")
        lines = em.tool_call_pending({"id": "c1", "name": "propose_edit",
                                      "args": {"operation": "insert_at_cursor", "text": "Hi"}})
        types = [_parse(x)["type"] for x in lines]
        assert types == ["TOOL_CALL_START", "TOOL_CALL_ARGS", "TOOL_CALL_END"]
        assert _parse(lines[0])["toolCallName"] == "propose_edit"
        assert "TOOL_CALL_RESULT" not in types  # result comes on resume
        args = _parse(lines[1])
        assert json.loads(args["delta"]) == {"operation": "insert_at_cursor", "text": "Hi"}

    @pytest.mark.asyncio
    async def test_suspend_chunk_pending_call_feeds_emitter(self):
        """Regression (live-smoke KeyError 'tool'): the dict the suspend
        producer emits (`chunk["suspend"]["pending_tool_call"]`) must flow
        through BOTH emitter consumers — tool_call_pending() and
        finish(pending=...) — exactly as _emit_chat_turn wires them, with no
        KeyError and a correct toolCallName. Pins the producer↔consumer key
        contract that the two isolated tests missed."""
        scripts = [[
            tool_frag(index=0, id="call_fe", name="propose_edit"),
            tool_frag(index=0, arguments_delta='{"operation":"insert_at_cursor","text":"Hi"}'),
            usage(10, 4),
            done("tool_calls"),
        ]]
        with _patch_client(scripts):
            chunks = await _drain(_run(
                scripts, knowledge_client=AsyncMock(),
                tools=[{"type": "function", "function": {"name": "propose_edit"}}],
            ))
        pending = [c for c in chunks if "suspend" in c][0]["suspend"]["pending_tool_call"]

        em = AgUiEmitter(thread_id="s", message_id="m")
        # mirrors stream_service _emit_chat_turn suspend branch
        start = _parse(em.tool_call_pending(pending)[0])
        assert start["toolCallName"] == "propose_edit"
        fin = em.finish(
            {"type": "finish-message", "finishReason": "tool_calls", "usage": {}, "timing": {}},
            status="suspended",
            pending={"runId": "r1", "toolCallId": pending["id"], "toolName": pending["name"]},
        )
        assert _parse(fin[-1])["result"]["pendingToolCall"]["toolName"] == "propose_edit"

    def test_agui_finish_suspended_carries_pending(self):
        em = AgUiEmitter(thread_id="s", message_id="m")
        lines = em.finish(
            {"type": "finish-message", "finishReason": "tool_calls", "usage": {}, "timing": {}},
            status="suspended",
            pending={"runId": "r1", "toolCallId": "c1", "toolName": "propose_edit"},
        )
        run_finished = _parse(lines[-1])
        assert run_finished["type"] == "RUN_FINISHED"
        assert run_finished["result"]["status"] == "suspended"
        assert run_finished["result"]["pendingToolCall"]["runId"] == "r1"

    def test_legacy_pending_is_noop(self):
        assert LegacyEmitter().tool_call_pending({"id": "c", "tool": "propose_edit", "args": {}}) == []


# ── resume: usage summed + tool re-advertised even with NO memory tools ───────


def _creds() -> ProviderCredentials:
    return ProviderCredentials(
        provider_kind="lm_studio", provider_model_name="qwen/qwen3-coder-30b",
        base_url="", api_key="x", context_length=32768,
    )


def _suspended(seed_in: int, seed_out: int) -> SuspendedRun:
    return SuspendedRun(
        run_id="run-1",
        session_id=str(TEST_SESSION_ID),
        owner_user_id=str(TEST_USER_ID),
        message_id=str(uuid4()),
        working=[
            {"role": "user", "content": "rewrite this"},
            {"role": "assistant", "content": "",
             "tool_calls": [{"id": "c1", "type": "function",
                             "function": {"name": "propose_edit", "arguments": "{}"}}]},
        ],
        pending_tool_call={"id": "c1", "name": "propose_edit", "args": {}},
        input_tokens=seed_in,
        output_tokens=seed_out,
        model_source="user_model",
        model_ref=str(TEST_MODEL_REF),
        parent_message_id=None,
        user_message_content="rewrite this",
    )


class TestResumeUsageSummed:
    @pytest.mark.asyncio
    async def test_resume_with_no_memory_tools_sums_usage(self):
        """Regression (C6 live smoke): on resume with NO memory tools (no
        project), the frontend tool must STILL be advertised so the run goes
        through _stream_with_tools — otherwise it falls to the no-tools gateway
        path which ignores seed_usage and the two-run usage is NOT summed.

        Seed = 100/20 (run 1); the resumed pass reports 500/30 → the persisted
        finish must carry the SUM 600/50, not 500/30."""
        pool, conn = _make_pool_with_conn()
        conn.fetchval.return_value = 1
        pool.fetchrow.return_value = {"generation_params": {}, "project_id": None}
        billing = AsyncMock()

        kc = AsyncMock()
        kc.get_tool_definitions.return_value = []  # the no-project / empty case

        # resumed pass: a plain text answer + its own usage
        scripts = [[tok("Applied."), usage(500, 30), done("stop")]]

        with _patch_client(scripts), \
             patch("app.services.stream_service.get_knowledge_client", return_value=kc), \
             patch("app.services.stream_service.load_suspended_run",
                   AsyncMock(return_value=_suspended(100, 20))), \
             patch("app.services.stream_service.delete_suspended_run", AsyncMock()):
            lines = []
            async for line in resume_stream_response(
                session_id=str(TEST_SESSION_ID), user_id=str(TEST_USER_ID),
                run_id="run-1", tool_call_id="c1", outcome="applied",
                applied_text="Applied.", creds=_creds(), pool=pool, billing=billing,
                stream_format="agui",
            ):
                lines.append(line)

        # the resumed pass went through the TOOL path (frontend tool re-advertised)
        req = _FakeClient.instances[0].requests[0]
        names = [t["function"]["name"] for t in (req.tools or [])]
        assert "propose_edit" in names

        run_finished = [
            json.loads(x.removeprefix("data: ").strip())
            for x in lines if '"RUN_FINISHED"' in x
        ][-1]
        assert run_finished["result"]["status"] == "success"
        # seed (100/20) + resumed pass (500/30) = 600/50
        assert run_finished["result"]["usage"]["promptTokens"] == 600
        assert run_finished["result"]["usage"]["completionTokens"] == 50

    @pytest.mark.asyncio
    async def test_resume_feeds_real_glossary_outcome_to_agent(self):
        """H6 truthful resume: the assistant must see the ACTUAL Apply outcome
        (e.g. applied_conflict), not merely 'the user clicked Apply'. The resume
        appends the outcome verbatim as the frontend tool's result, so the next
        LLM pass can refuse to claim success on a conflict/error."""
        pool, conn = _make_pool_with_conn()
        conn.fetchval.return_value = 1
        pool.fetchrow.return_value = {"generation_params": {}, "project_id": None}

        kc = AsyncMock()
        kc.get_tool_definitions.return_value = []
        scripts = [[tok("It changed — let me re-read it."), usage(10, 5), done("stop")]]

        with _patch_client(scripts), \
             patch("app.services.stream_service.get_knowledge_client", return_value=kc), \
             patch("app.services.stream_service.load_suspended_run",
                   AsyncMock(return_value=_suspended(1, 1))), \
             patch("app.services.stream_service.delete_suspended_run", AsyncMock()):
            await _drain(resume_stream_response(
                session_id=str(TEST_SESSION_ID), user_id=str(TEST_USER_ID),
                run_id="run-1", tool_call_id="c1", outcome="applied_conflict",
                applied_text=None, creds=_creds(), pool=pool, billing=AsyncMock(),
                stream_format="agui",
            ))

        msgs = _FakeClient.instances[0].requests[0].messages
        tool_msg = next(m for m in msgs if m.get("role") == "tool" and m.get("tool_call_id") == "c1")
        assert json.loads(tool_msg["content"]) == {"outcome": "applied_conflict"}
