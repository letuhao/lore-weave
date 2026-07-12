"""W6 — tool/skill loading visibility: the agentSurface payload extension.

Three suites:
  1. server_key_for_tool / servers_for_names — the ONE prefix→server mapping
     helper (mirrors the ai-gateway federation registry).
  2. AgentSurfaceTracker payload — strictly ADDITIVE: the original eight
     fields keep values, order and semantics; the three W6 fields append.
  3. The advertise chokepoint — `_stream_with_tools` emits an agent_surface
     chunk carrying the advertised core/frontend/activated split, the
     per-server grouping and the reused W1 schema-token measurement.
"""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app.services.agent_surface import (
    AgentSurfaceTracker,
    server_key_for_tool,
    servers_for_names,
)
from app.services.frontend_tools import frontend_tool_defs
from app.services.stream_service import _stream_with_tools
from tests.conftest import TEST_MODEL_REF, TEST_SESSION_ID, TEST_USER_ID
from tests.test_stream_tools import (
    _drain,
    _patch_client,
    done,
    tok,
    tool_frag,
    usage,
)
from tests.test_tool_discovery import _CATALOG, _kc


# ════════════════════════════════════════════════════════════════════════════
# server_key_for_tool — the one mapping helper
# ════════════════════════════════════════════════════════════════════════════


class TestServerKeyForTool:
    @pytest.mark.parametrize(
        ("name", "key"),
        [
            # knowledge-service serves BOTH memory_* and kg_* (gateway
            # EXTRA_PREFIX_MAP), plus a hypothetical knowledge_* alias.
            ("memory_search", "knowledge"),
            ("kg_query_paths", "knowledge"),
            ("knowledge_lookup", "knowledge"),
            # each domain service owns its canonical prefix.
            ("glossary_search", "glossary"),
            ("glossary_propose_batch", "glossary"),
            ("book_create", "book"),
            ("composition_outline_create", "composition"),
            # PlanForge plan_* tools are federated by composition-service.
            ("plan_create_run", "composition"),
            ("translation_start_job", "translation"),
            ("jobs_list", "jobs"),
        ],
    )
    def test_known_prefixes_map_to_owning_service(self, name, key):
        assert server_key_for_tool(name) == key

    @pytest.mark.parametrize(
        "name",
        [
            "ui_navigate",
            "ui_open_book",
            "ui_show_panel",
            "confirm_action",
            "propose_edit",
            "propose_record_edit",
            # frontend check has PRECEDENCE over the glossary_ prefix — these
            # are browser-executed despite the domain prefix.
            "glossary_confirm_action",
            "glossary_propose_entity_edit",
        ],
    )
    def test_frontend_tools_map_to_ui(self, name):
        assert server_key_for_tool(name) == "ui"

    def test_find_tools_is_consumer_local_chat(self):
        assert server_key_for_tool("find_tools") == "chat"

    @pytest.mark.parametrize("name", ["settings_list_models", "frobnicate", ""])
    def test_unknown_prefix_maps_to_other(self, name):
        assert server_key_for_tool(name) == "other"


class TestServersForNames:
    def test_groups_and_counts(self):
        servers = servers_for_names(
            [
                "memory_search",
                "kg_query_paths",
                "glossary_search",
                "ui_navigate",
                "confirm_action",
                "find_tools",
                "settings_list_models",
            ]
        )
        assert servers == {
            "knowledge": {"tools": 2},
            "glossary": {"tools": 1},
            "ui": {"tools": 2},
            "chat": {"tools": 1},
            "other": {"tools": 1},
        }

    def test_empty(self):
        assert servers_for_names([]) == {}


# ════════════════════════════════════════════════════════════════════════════
# AgentSurfaceTracker — additive payload
# ════════════════════════════════════════════════════════════════════════════


# The pre-W6 payload contract, frozen (order matters — consumers may rely on
# key order across the wire; the W6 fields APPEND after these).
_ORIGINAL_KEYS = [
    "phase",
    "pinned_count",
    "hot_seed_count",
    "activated_count",
    "injected_skills",
    "running_tool",
    "last_find_tools_query",
    "find_tools_call_count",
]


class TestTrackerPayloadAdditive:
    def test_original_fields_byte_identical(self):
        tr = AgentSurfaceTracker()
        tr.curated(pinned_count=2, hot_seed_count=5, activated_count=1)
        payload = tr.payload()
        # original keys first, same order, same values as pre-W6.
        assert list(payload)[: len(_ORIGINAL_KEYS)] == _ORIGINAL_KEYS
        assert {k: payload[k] for k in _ORIGINAL_KEYS} == {
            "phase": "Curated",
            "pinned_count": 2,
            "hot_seed_count": 5,
            "activated_count": 1,
            "injected_skills": [],
            "running_tool": None,
            "last_find_tools_query": None,
            "find_tools_call_count": 0,
        }

    def test_new_fields_default_empty(self):
        payload = AgentSurfaceTracker().payload()
        assert payload["advertised"] == {"core": [], "frontend": [], "activated": []}
        assert payload["servers"] == {}
        assert payload["schema_tokens"] == {"frontend": 0, "mcp": 0}

    def test_advertised_pass_sets_fields_and_groups_servers(self):
        tr = AgentSurfaceTracker()
        payload = tr.advertised_pass(
            core=["find_tools", "ui_navigate"],
            frontend=["propose_edit"],
            activated=["memory_search", "glossary_search"],
            schema_tokens={"frontend": 120, "mcp": 300},
        )
        assert payload is not None
        assert payload["advertised"] == {
            "core": ["find_tools", "ui_navigate"],
            "frontend": ["propose_edit"],
            "activated": ["glossary_search", "memory_search"],  # sorted
        }
        assert payload["servers"] == {
            "chat": {"tools": 1},
            "ui": {"tools": 2},
            "knowledge": {"tools": 1},
            "glossary": {"tools": 1},
        }
        assert payload["schema_tokens"] == {"frontend": 120, "mcp": 300}
        # phase is untouched — advertising is NOT a phase transition.
        assert payload["phase"] == "Idle"

    def test_advertised_pass_quiet_on_no_change(self):
        tr = AgentSurfaceTracker()
        assert tr.advertised_pass(
            core=["find_tools"], frontend=[], activated=["memory_search"],
            schema_tokens={"frontend": 1, "mcp": 2},
        ) is not None
        # identical repeat pass (schema tokens measured once → None) → silent.
        assert tr.advertised_pass(
            core=["find_tools"], frontend=[], activated=["memory_search"],
        ) is None
        # discovery grew the active set → emits again, tokens retained.
        payload = tr.advertised_pass(
            core=["find_tools"], frontend=[], activated=["memory_search", "book_list"],
        )
        assert payload is not None
        assert payload["advertised"]["activated"] == ["book_list", "memory_search"]
        assert payload["schema_tokens"] == {"frontend": 1, "mcp": 2}


# ════════════════════════════════════════════════════════════════════════════
# The advertise chokepoint — emitted with the split counts
# ════════════════════════════════════════════════════════════════════════════


def _run_with_tracker(scripts, *, knowledge_client, tracker, discovery: bool):
    kwargs = dict(
        model_source="user_model",
        model_ref=TEST_MODEL_REF,
        user_id=TEST_USER_ID,
        messages=[{"role": "user", "content": "hi"}],
        gen_params={},
        knowledge_client=knowledge_client,
        session_id=TEST_SESSION_ID,
        project_id="proj-1",
        surface_tracker=tracker,
    )
    if discovery:
        return _stream_with_tools(
            tools=[],
            discovery_catalog=_CATALOG,
            discovery_extra_frontend=frontend_tool_defs(editor=False, book_scoped=False),
            **kwargs,
        )
    return _stream_with_tools(
        tools=[
            {"type": "function", "function": {
                "name": "memory_search",
                "parameters": {"type": "object", "properties": {}},
            }},
            {"type": "function", "function": {
                "name": "propose_edit",
                "parameters": {"type": "object", "properties": {}},
            }},
        ],
        **kwargs,
    )


class TestAdvertiseEmitsSurface:
    @pytest.mark.asyncio
    async def test_plain_path_emits_split_and_reuses_w1_tokens(self):
        tracker = AgentSurfaceTracker()
        scripts = [[tok("hi"), usage(1, 1), done()]]
        with _patch_client(scripts):
            out = await _drain(_run_with_tracker(
                scripts, knowledge_client=AsyncMock(), tracker=tracker, discovery=False,
            ))
        surfaces = [c["agent_surface"] for c in out
                    if c.get("agent_surface", {}).get("advertised")]
        assert len(surfaces) == 1, "one advertise pass → one surface emit"
        adv = surfaces[0]["advertised"]
        assert adv["core"] == []
        assert adv["frontend"] == ["propose_edit"]
        # T6/D6 — conversation_search is always appended (chat-native, server-
        # executed); it groups under the "chat" server, like find_tools.
        # B1/WS-1.9 — chat_search_sessions is also always-appended (chat-native), grouped under "chat".
        assert adv["activated"] == ["chat_search_sessions", "conversation_search", "memory_search"]
        assert surfaces[0]["servers"] == {
            "ui": {"tools": 1},
            "knowledge": {"tools": 1},
            "chat": {"tools": 2},  # conversation_search + chat_search_sessions (B1/WS-1.9)
        }
        # schema_tokens REUSES the W1 measurement from the same pass.
        st = next(c["schema_tokens"] for c in out if "schema_tokens" in c)
        assert surfaces[0]["schema_tokens"] == {
            "frontend": st["frontend_tool_schemas"],
            "mcp": st["mcp_tool_schemas"],
        }
        assert surfaces[0]["schema_tokens"]["frontend"] > 0
        assert surfaces[0]["schema_tokens"]["mcp"] > 0

    @pytest.mark.asyncio
    async def test_discovery_second_pass_emits_grown_surface(self):
        """find_tools grows the active set → the NEXT pass's advertise emits an
        updated surface including the newly activated tool + its server."""
        tracker = AgentSurfaceTracker()
        kc = _kc()
        scripts = [
            [tool_frag(0, id="f", name="find_tools"),
             tool_frag(0, arguments_delta='{"intent":"translate my book"}'),
             done("tool_calls")],
            [tok("ok"), done("stop")],
        ]
        with _patch_client(scripts):
            out = await _drain(_run_with_tracker(
                scripts, knowledge_client=kc, tracker=tracker, discovery=True,
            ))
        surfaces = [c["agent_surface"] for c in out
                    if c.get("agent_surface", {}).get("advertised")]
        assert len(surfaces) >= 2, "pass 0 + the post-discovery pass both emit"
        first, last = surfaces[0], surfaces[-1]
        # pass 0: the always-on core, plus the always-appended conversation_search
        # recovery tool (T6/D6) in activated. No discovered domain tool yet.
        assert "find_tools" in first["advertised"]["core"]
        assert first["advertised"]["activated"] == ["chat_search_sessions", "conversation_search"]
        assert first["servers"].get("translation") is None
        # after find_tools matched: translation tool advertised + grouped.
        assert "translation_start_job" in last["advertised"]["activated"]
        assert last["servers"]["translation"] == {"tools": 1}
        # core unchanged between passes; W1 tokens measured once and retained.
        assert last["advertised"]["core"] == first["advertised"]["core"]
        assert last["schema_tokens"] == first["schema_tokens"]
        st_chunks = [c for c in out if "schema_tokens" in c]
        assert len(st_chunks) == 1, "W1 measurement stays once-per-turn"

    @pytest.mark.asyncio
    async def test_no_tracker_no_surface_chunks(self):
        scripts = [[tok("hi"), usage(1, 1), done()]]
        with _patch_client(scripts):
            out = await _drain(_stream_with_tools(
                model_source="user_model",
                model_ref=TEST_MODEL_REF,
                user_id=TEST_USER_ID,
                messages=[{"role": "user", "content": "hi"}],
                gen_params={},
                tools=[{"type": "function", "function": {"name": "memory_search"}}],
                knowledge_client=AsyncMock(),
                session_id=TEST_SESSION_ID,
                project_id="proj-1",
            ))
        assert [c for c in out if "agent_surface" in c] == []
