"""Story 04 review-impl — integration tests for curated surface, skills, top_p, resume."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.client.knowledge_client import KnowledgeContext
from app.services.stream_service import (
    _emit_chat_turn,
    resume_stream_response,
    stream_response,
)
from tests.conftest import TEST_MODEL_REF, TEST_SESSION_ID, TEST_USER_ID, make_session_record
from tests.test_stream_service import (
    _Usage,
    _make_chunk,
    _make_creds,
    _make_pool_with_conn,
    _patched_knowledge,
)
from tests.test_stream_tools import _drain, _patch_client, done, tok, usage
from tests.test_frontend_tools import _suspended as _suspended_propose_edit


def _session_row(**overrides):
    base = {
        "system_prompt": None,
        "generation_params": {},
        "project_id": None,
        "composer_model_source": None,
        "composer_model_ref": None,
        "planner_model_ref": None,
        "enabled_tools": [],
        "enabled_skills": [],
        "activated_tools": [],
    }
    base.update(overrides)
    return base


class TestGlossaryOnlySkillInject:
    @pytest.mark.asyncio
    async def test_enabled_skills_glossary_only_excludes_universal(self):
        """Criterion §11.4: curated glossary skill → system prompt has glossary, not universal."""
        pool, conn = _make_pool_with_conn()
        pool.fetchrow.return_value = _session_row()
        pool.fetch.return_value = []
        conn.fetchval.return_value = 1

        kc = _patched_knowledge(
            stable="", volatile="", mode="static",
            tool_defs=[{"type": "function", "function": {"name": "glossary_search"}}],
        )

        async def fake_tool_loop(**kwargs):
            yield {"content": "ok", "reasoning_content": "", "finish_reason": "stop", "usage": _Usage(1, 1)}

        with patch("app.services.stream_service.get_knowledge_client", return_value=kc), \
             patch("app.services.stream_service._stream_with_tools", side_effect=fake_tool_loop) as loop_mock, \
             patch("app.services.stream_service._stream_via_gateway"):
            async for _ in stream_response(
                session_id=TEST_SESSION_ID,
                user_message_content="rename entity",
                user_id=TEST_USER_ID,
                model_source="user_model",
                model_ref=TEST_MODEL_REF,
                creds=_make_creds(),
                pool=pool,
                billing=AsyncMock(),
                stream_format="agui",
                book_context={"book_id": "b1"},
                enabled_skills=["glossary"],
            ):
                pass

        msgs = loop_mock.call_args.kwargs["messages"]
        system = next((m for m in msgs if m["role"] == "system"), None)
        assert system is not None
        content = system["content"] if isinstance(system["content"], str) \
            else " ".join(p["text"] for p in system["content"])
        assert "Glossary assistant" in content
        assert "Universal assistant" not in content
        assert "Knowledge & graph assistant" not in content


class TestStudioSurface:
    @pytest.mark.asyncio
    async def test_studio_context_advertises_studio_nav_tools(self):
        """#09 Lane A — closing the loop: a request carrying studio_context makes the REAL
        stream path advertise the studio dock-nav frontend tools (ui_open_studio_panel /
        ui_focus_manuscript_unit) into the tool loop, so the agent can call them."""
        pool, conn = _make_pool_with_conn()
        pool.fetchrow.return_value = _session_row()
        pool.fetch.return_value = []
        conn.fetchval.return_value = 1

        kc = _patched_knowledge(
            stable="", volatile="", mode="static",
            tool_defs=[{"type": "function", "function": {"name": "book_get_chapter"}}],
        )

        async def fake_tool_loop(**kwargs):
            yield {"content": "ok", "reasoning_content": "", "finish_reason": "stop", "usage": _Usage(1, 1)}

        with patch("app.services.stream_service.get_knowledge_client", return_value=kc), \
             patch("app.services.stream_service._stream_with_tools", side_effect=fake_tool_loop) as loop_mock, \
             patch("app.services.stream_service._stream_via_gateway"):
            async for _ in stream_response(
                session_id=TEST_SESSION_ID,
                user_message_content="open the compose panel please",
                user_id=TEST_USER_ID,
                model_source="user_model",
                model_ref=TEST_MODEL_REF,
                creds=_make_creds(),
                pool=pool,
                billing=AsyncMock(),
                stream_format="agui",
                book_context={"book_id": "b1"},
                studio_context={"book_id": "b1"},
            ):
                pass

        extra_fe = loop_mock.call_args.kwargs["discovery_extra_frontend"]
        names = {t["function"]["name"] for t in extra_fe}
        assert "ui_open_studio_panel" in names
        assert "ui_focus_manuscript_unit" in names

    @pytest.mark.asyncio
    async def test_studio_context_seeds_the_composition_domain_hot(self):
        """M-E live-caught — the studio compose surface is the composition surface: its
        composition_* family must be HOT (advertised pass 1), not find_tools-lazy (a
        local model spun in memory/glossary searches and never discovered the family)."""
        pool, conn = _make_pool_with_conn()
        pool.fetchrow.return_value = _session_row()
        pool.fetch.return_value = []
        conn.fetchval.return_value = 1
        kc = _patched_knowledge(
            stable="", volatile="", mode="static",
            tool_defs=[
                {"type": "function", "function": {"name": "composition_list_outline"}},
                {"type": "function", "function": {"name": "composition_outline_node_update"}},
                {"type": "function", "function": {"name": "book_get_chapter"}},
            ],
        )

        async def fake_tool_loop(**kwargs):
            yield {"content": "ok", "reasoning_content": "", "finish_reason": "stop", "usage": _Usage(1, 1)}

        with patch("app.services.stream_service.get_knowledge_client", return_value=kc), \
             patch("app.services.stream_service._stream_with_tools", side_effect=fake_tool_loop) as loop_mock, \
             patch("app.services.stream_service._stream_via_gateway"):
            async for _ in stream_response(
                session_id=TEST_SESSION_ID,
                user_message_content="update the scene synopsis",
                user_id=TEST_USER_ID,
                model_source="user_model",
                model_ref=TEST_MODEL_REF,
                creds=_make_creds(),
                pool=pool,
                billing=AsyncMock(),
                stream_format="agui",
                book_context={"book_id": "b1"},
                studio_context={"book_id": "b1", "project_id": "p1"},
            ):
                pass

        seeds = loop_mock.call_args.kwargs["discovery_seed_names"]
        assert "composition_list_outline" in seeds
        assert "composition_outline_node_update" in seeds
        # book_* stays lazy even on the studio surface.
        assert "book_get_chapter" not in seeds

    @pytest.mark.asyncio
    async def test_studio_context_position_pointer_in_system_message(self):
        """CTX-1 — a studio_context carrying project_id/active_chapter_id puts the position
        pointer INTO the system message (book + chapter + project ids), so the model passes
        project_id to composition_* tools instead of foraging for it (the live M-E gate run
        dead-ended retrying the book_id AS a project_id)."""
        pool, conn = _make_pool_with_conn()
        pool.fetchrow.return_value = _session_row()
        pool.fetch.return_value = []
        conn.fetchval.return_value = 1
        kc = _patched_knowledge(
            stable="", volatile="", mode="static",
            tool_defs=[{"type": "function", "function": {"name": "book_get_chapter"}}],
        )

        async def fake_tool_loop(**kwargs):
            yield {"content": "ok", "reasoning_content": "", "finish_reason": "stop", "usage": _Usage(1, 1)}

        with patch("app.services.stream_service.get_knowledge_client", return_value=kc), \
             patch("app.services.stream_service._stream_with_tools", side_effect=fake_tool_loop) as loop_mock, \
             patch("app.services.stream_service._stream_via_gateway"):
            async for _ in stream_response(
                session_id=TEST_SESSION_ID,
                user_message_content="update the scene synopsis",
                user_id=TEST_USER_ID,
                model_source="user_model",
                model_ref=TEST_MODEL_REF,
                creds=_make_creds(),
                pool=pool,
                billing=AsyncMock(),
                stream_format="agui",
                studio_context={"book_id": "b1", "project_id": "p1", "active_chapter_id": "ch1"},
            ):
                pass

        msgs = loop_mock.call_args.kwargs["messages"]
        system = next((m for m in msgs if m["role"] == "system"), None)
        assert system is not None
        content = system["content"] if isinstance(system["content"], str) \
            else " ".join(p["text"] for p in system["content"])
        assert "book_id=b1" in content
        assert "chapter_id=ch1" in content
        assert "project_id=p1" in content
        assert "a book_id is NOT a project_id" in content

    @pytest.mark.asyncio
    async def test_group_directory_rides_the_system_prompt_when_tools_are_live(self):
        """Tool-catalog-simplification Part A — group_directory_text() must actually be
        wired into the system prompt (not just the find_tools schema/filter side), so a
        book-scoped agui turn gets the domain map instead of relying purely on whole-domain
        hot-seeding."""
        pool, conn = _make_pool_with_conn()
        pool.fetchrow.return_value = _session_row()
        pool.fetch.return_value = []
        conn.fetchval.return_value = 1
        kc = _patched_knowledge(
            stable="", volatile="", mode="static",
            tool_defs=[{"type": "function", "function": {"name": "book_get_chapter"}}],
        )

        async def fake_tool_loop(**kwargs):
            yield {"content": "ok", "reasoning_content": "", "finish_reason": "stop", "usage": _Usage(1, 1)}

        with patch("app.services.stream_service.get_knowledge_client", return_value=kc), \
             patch("app.services.stream_service._stream_with_tools", side_effect=fake_tool_loop) as loop_mock, \
             patch("app.services.stream_service._stream_via_gateway"):
            async for _ in stream_response(
                session_id=TEST_SESSION_ID,
                user_message_content="what can you do here?",
                user_id=TEST_USER_ID,
                model_source="user_model",
                model_ref=TEST_MODEL_REF,
                creds=_make_creds(),
                pool=pool,
                billing=AsyncMock(),
                stream_format="agui",
                book_context={"book_id": "b1"},
            ):
                pass

        msgs = loop_mock.call_args.kwargs["messages"]
        system = next((m for m in msgs if m["role"] == "system"), None)
        assert system is not None
        content = system["content"] if isinstance(system["content"], str) \
            else " ".join(p["text"] for p in system["content"])
        assert "Tool domains (call tool_list with category=<name> to see every tool in one):" in content
        assert "- glossary: Lore entities" in content

    @pytest.mark.asyncio
    async def test_no_studio_context_does_not_advertise_studio_tools(self):
        """Control: a non-studio chat never advertises the studio tools (so it never suspends)."""
        pool, conn = _make_pool_with_conn()
        pool.fetchrow.return_value = _session_row()
        pool.fetch.return_value = []
        conn.fetchval.return_value = 1
        kc = _patched_knowledge(
            stable="", volatile="", mode="static",
            tool_defs=[{"type": "function", "function": {"name": "book_get_chapter"}}],
        )

        async def fake_tool_loop(**kwargs):
            yield {"content": "ok", "reasoning_content": "", "finish_reason": "stop", "usage": _Usage(1, 1)}

        with patch("app.services.stream_service.get_knowledge_client", return_value=kc), \
             patch("app.services.stream_service._stream_with_tools", side_effect=fake_tool_loop) as loop_mock, \
             patch("app.services.stream_service._stream_via_gateway"):
            async for _ in stream_response(
                session_id=TEST_SESSION_ID, user_message_content="hi", user_id=TEST_USER_ID,
                model_source="user_model", model_ref=TEST_MODEL_REF, creds=_make_creds(),
                pool=pool, billing=AsyncMock(), stream_format="agui", book_context={"book_id": "b1"},
            ):
                pass

        names = {t["function"]["name"] for t in loop_mock.call_args.kwargs["discovery_extra_frontend"]}
        assert "ui_open_studio_panel" not in names


class TestTopPForward:
    @pytest.mark.asyncio
    async def test_top_p_forwarded_on_plain_gateway_path(self):
        pool, conn = _make_pool_with_conn()
        pool.fetchrow.return_value = _session_row(generation_params={"top_p": 0.85})
        pool.fetch.return_value = []
        conn.fetchval.return_value = 5

        kctx = KnowledgeContext(
            mode="static", context="", recent_message_count=50,
            token_count=0, tool_calling_enabled=False,
        )
        kc = MagicMock()
        kc.build_context = AsyncMock(return_value=kctx)

        captured: dict = {}

        async def capture_gateway(**kwargs):
            captured.update(kwargs)
            yield _make_chunk("ok")
            yield _make_chunk(None)

        with patch("app.services.stream_service.get_knowledge_client", return_value=kc), \
             patch("app.services.stream_service._stream_via_gateway", side_effect=capture_gateway):
            async for _ in stream_response(
                session_id=TEST_SESSION_ID,
                user_message_content="hi",
                user_id=TEST_USER_ID,
                model_source="user_model",
                model_ref=TEST_MODEL_REF,
                creds=_make_creds(),
                pool=pool,
                billing=AsyncMock(),
            ):
                pass

        assert captured.get("gen_params", {}).get("top_p") == 0.85


class TestActivatedToolsPersist:
    @pytest.mark.asyncio
    async def test_emit_chat_turn_persists_dirty_activation_state(self):
        """Criterion §11.2: find_tools union → activated_tools UPDATE on turn end."""
        pool, conn = _make_pool_with_conn()
        conn.fetchval.return_value = 2
        pool.execute = AsyncMock()

        async def fake_tool_loop(**kwargs):
            yield {"content": "done", "reasoning_content": "", "finish_reason": "stop", "usage": _Usage(1, 1)}

        activation_state = {"activated_tools": ["book_get_chapter"], "dirty": True}

        with patch("app.services.stream_service._stream_with_tools", side_effect=fake_tool_loop), \
             patch("app.services.stream_service.get_knowledge_client", return_value=_patched_knowledge()):
            events = []
            async for line in _emit_chat_turn(
                session_id=TEST_SESSION_ID,
                user_message_content="hi",
                user_id=TEST_USER_ID,
                model_source="user_model",
                model_ref=TEST_MODEL_REF,
                creds=_make_creds(),
                pool=pool,
                billing=AsyncMock(),
                parent_message_id=None,
                project_id=None,
                stream_format="agui",
                editor_context=None,
                messages=[{"role": "user", "content": "hi"}],
                gen_params={},
                tool_defs=[],
                use_tools=True,
                knowledge_client=_patched_knowledge(),
                admin_token=None,
                fe_memory_mode="static",
                msg_id="msg-1",
                seed_usage=None,
                curated=True,
                activation_state=activation_state,
            ):
                events.append(line)

        pool.execute.assert_awaited()
        # The post-turn block issues MORE than one UPDATE (activated_tools AND capture_status),
        # so find the activated_tools call among ALL execute calls rather than assuming it is last.
        activation_calls = [
            c for c in pool.execute.await_args_list
            if c.args and isinstance(c.args[0], str) and "activated_tools" in c.args[0]
        ]
        assert activation_calls, "expected an activated_tools UPDATE among the post-turn writes"
        assert activation_calls[-1].args[2] == ["book_get_chapter"]


class TestResumeCuratedSurface:
    @pytest.mark.asyncio
    async def test_resume_curated_seed_uses_pins_not_full_hot_set(self):
        """P0: resume with session pins must not seed the full editor hot set."""
        pool, conn = _make_pool_with_conn()
        conn.fetchval.return_value = 1
        pool.fetchrow.return_value = _session_row(
            enabled_tools=["book_get_chapter"],
            enabled_skills=[],
            activated_tools=[],
        )

        catalog = [
            {"type": "function", "function": {"name": "book_get_chapter"}},
            {"type": "function", "function": {"name": "glossary_search"}},
            {"type": "function", "function": {"name": "glossary_propose_batch"}},
            {"type": "function", "function": {"name": "translation_start_job"}},
        ]
        kc = _patched_knowledge(tool_defs=catalog)

        captured: dict = {}

        async def fake_tool_loop(**kwargs):
            captured["discovery_seed_names"] = kwargs.get("discovery_seed_names")
            yield {"content": "ok", "reasoning_content": "", "finish_reason": "stop", "usage": _Usage(1, 1)}

        with patch("app.services.stream_service.get_knowledge_client", return_value=kc), \
             patch("app.services.stream_service._stream_with_tools", side_effect=fake_tool_loop), \
             patch("app.services.stream_service.load_suspended_run",
                   AsyncMock(return_value=_suspended_propose_edit(10, 5))), \
             patch("app.services.stream_service.delete_suspended_run", AsyncMock()):
            await _drain(resume_stream_response(
                session_id=str(TEST_SESSION_ID),
                user_id=str(TEST_USER_ID),
                run_id="run-1",
                tool_call_id="c1",
                outcome="applied",
                applied_text="Applied.",
                creds=_make_creds(),
                pool=pool,
                billing=AsyncMock(),
                stream_format="agui",
            ))

        seed = captured.get("discovery_seed_names") or set()
        assert "book_get_chapter" in seed
        assert "translation_start_job" not in seed
        # Glossary hot tools still seed on book/editor resume when glossary skill is default.
        assert "glossary_search" in seed

    @pytest.mark.asyncio
    async def test_resume_emits_agent_surface_custom_events(self):
        """Resume path passes surface_tracker → Curated/SkillInjected/Idle SSE."""
        pool, conn = _make_pool_with_conn()
        conn.fetchval.return_value = 1
        pool.fetchrow.return_value = _session_row(enabled_tools=["book_get_chapter"])
        kc = _patched_knowledge(
            tool_defs=[{"type": "function", "function": {"name": "book_get_chapter"}}],
        )

        scripts = [[tok("Applied."), usage(2, 1), done("stop")]]

        with _patch_client(scripts), \
             patch("app.services.stream_service.get_knowledge_client", return_value=kc), \
             patch("app.services.stream_service.load_suspended_run",
                   AsyncMock(return_value=_suspended_propose_edit(1, 1))), \
             patch("app.services.stream_service.delete_suspended_run", AsyncMock()):
            lines = []
            async for line in resume_stream_response(
                session_id=str(TEST_SESSION_ID),
                user_id=str(TEST_USER_ID),
                run_id="run-1",
                tool_call_id="c1",
                outcome="applied",
                applied_text="Applied.",
                creds=_make_creds(),
                pool=pool,
                billing=AsyncMock(),
                stream_format="agui",
            ):
                lines.append(line)

        agent_surface = [
            line for line in lines
            if '"agentSurface"' in line or '"name": "agentSurface"' in line
        ]
        assert len(agent_surface) >= 2
