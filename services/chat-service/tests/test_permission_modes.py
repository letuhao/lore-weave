"""RAID Wave C2 (DR-C2) — HITL permission modes + per-tool approval.

Covers:
 - permission_mode threading (POST body → stream_response → _stream_with_tools),
 - the ADVERTISE-time ask filter at the single chokepoint (discovery +
   non-discovery paths), incl. the availability regression guard: `write`
   advertises the IDENTICAL pinned surface as pre-C2,
 - ask-mode defense-in-depth (a non-R server tool call never executes),
 - the Write-mode Tier-A prompt-once gate (suspend payload shape, allowlisted
   pass-through, fail-OPEN on allowlist read errors),
 - the approval resume outcomes (approved_once / approved_always / denied),
 - permission_mode persisted on the suspended run + carried through resume.

Reuses the `_FakeClient` scripting harness from test_stream_tools.
"""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.db.suspended_runs import SuspendedRun
from app.services.frontend_tools import PROPOSE_EDIT_TOOL
from app.services.stream_service import (
    _advertise_discovery_tools,
    _catalog_index,
    _filter_tools_for_ask,
    _stream_with_tools,
    resume_stream_response,
    stream_response,
)
from app.services.tool_discovery import ALWAYS_ON_CORE_NAMES
from tests.conftest import (
    TEST_MODEL_REF,
    TEST_SESSION_ID,
    TEST_USER_ID,
    make_session_record,
)
from tests.test_frontend_tools import _creds
from tests.test_stream_service import (
    _Usage,
    _make_creds,
    _make_pool_with_conn,
    _patched_knowledge,
)
from tests.test_stream_tools import (
    _FakeClient,
    _drain,
    _envelope,
    _patch_client,
    done,
    tok,
    tool_frag,
    usage,
)


# ── representative catalog (the C-TOOL tier spread) ──────────────────────────


def _tiered(name: str, tier: str, desc: str = "") -> dict:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": desc or f"{name} tool",
            "parameters": {"type": "object", "properties": {}},
            "_meta": {"tier": tier},
        },
    }


def _catalog() -> list[dict]:
    return [
        _tiered("glossary_search", "R", "Search glossary entities"),
        _tiered("glossary_get_entity", "R", "Fetch one glossary entity"),
        _tiered("book_create", "A", "Create a book (undoable)"),
        _tiered("chapter_update", "A", "Update a chapter (undoable)"),
        _tiered("translation_start_job", "W", "Start a priced translation job"),
        _tiered("settings_update", "S", "Change account settings"),
        # Track D CD5 — `web_search` is ALWAYS-ON CORE *and* federated, the only core tool
        # sourced from the catalog rather than from a generic frontend def. It must be in
        # this fixture or the core loop resolves nothing for it (`_add(None)`) and every
        # EXPECTED_*_SURFACE below — each of which unions ALWAYS_ON_CORE_NAMES — under-matches.
        # Tier R + paid: it is advertised in ask/plan mode too (spend ⊥ mutation).
        _tiered("web_search", "R", "Search the open web (paid)"),
        # legacy/untiered — defaults to tier R (inert) per the C-TOOL convention
        {"type": "function", "function": {
            "name": "legacy_tool", "description": "pre-_meta tool",
            "parameters": {"type": "object", "properties": {}},
        }},
    ]


ALL_CATALOG_NAMES = {
    "glossary_search", "glossary_get_entity", "book_create", "chapter_update",
    "translation_start_job", "settings_update", "legacy_tool", "web_search",
}
# web_search is Tier R, so it survives the ask/plan filter on its own merits — and it is
# ALSO always-on core, so it would be advertised either way. Both paths must agree.
R_CATALOG_NAMES = {"glossary_search", "glossary_get_entity", "legacy_tool", "web_search"}

# RAID Wave B2 — the PlanForge `plan_*` tools (M4 federation) as they appear in
# the discovery catalog: tiered A/W, yet part of the PLAN-mode surface.
PLAN_TOOL_DEFS = [
    ("plan_propose_spec", "A"),
    ("plan_compile", "W"),
]
PLAN_TOOL_NAMES = {n for n, _ in PLAN_TOOL_DEFS}


def _catalog_with_plan() -> list[dict]:
    return _catalog() + [_tiered(n, t, f"PlanForge {n}") for n, t in PLAN_TOOL_DEFS]


def _names(tool_defs: list[dict]) -> set[str]:
    return {t["function"]["name"] for t in tool_defs}


# ════════════════════════════════════════════════════════════════════════════
# Availability regression guard — the ADVERTISE chokepoint snapshot (DR-C2)
# ════════════════════════════════════════════════════════════════════════════


class TestAdvertiseSurfaceSnapshot:
    """Pins that `write` mode advertises the IDENTICAL surface as pre-change
    (the flagged risk: the ask filter must not silently shrink the default
    surface) and that `ask` advertises exactly the R subset."""

    # The pre-C2 discovery surface for the representative catalog with every
    # catalog tool active + propose_edit as the surface frontend tool. This is
    # a SNAPSHOT — if it shrinks, the filter leaked into write mode.
    EXPECTED_WRITE_SURFACE = set(ALWAYS_ON_CORE_NAMES) | {"propose_edit"} | ALL_CATALOG_NAMES
    EXPECTED_ASK_SURFACE = set(ALWAYS_ON_CORE_NAMES) | {"propose_edit"} | R_CATALOG_NAMES
    # RAID Wave B2 — the PLAN surface pin: the ASK surface PLUS the `plan_*`
    # tools (even though they're tiered A/W). If this shrinks, plan mode lost
    # its planning tools; if it grows, a write tool leaked into plan mode.
    EXPECTED_PLAN_SURFACE = (
        set(ALWAYS_ON_CORE_NAMES) | {"propose_edit"} | R_CATALOG_NAMES | PLAN_TOOL_NAMES
    )

    def test_write_mode_advertises_identical_pinned_surface(self):
        idx = _catalog_index(_catalog())
        out = _advertise_discovery_tools(
            idx, ALL_CATALOG_NAMES, [PROPOSE_EDIT_TOOL], permission_mode="write",
        )
        assert _names(out) == self.EXPECTED_WRITE_SURFACE

    def test_default_mode_is_byte_identical_to_write(self):
        """Omitting permission_mode (every pre-C2 call site) == explicit write."""
        idx = _catalog_index(_catalog())
        default_out = _advertise_discovery_tools(idx, ALL_CATALOG_NAMES, [PROPOSE_EDIT_TOOL])
        write_out = _advertise_discovery_tools(
            idx, ALL_CATALOG_NAMES, [PROPOSE_EDIT_TOOL], permission_mode="write",
        )
        assert default_out == write_out

    def test_ask_mode_advertises_exactly_the_r_subset(self):
        idx = _catalog_index(_catalog())
        out = _advertise_discovery_tools(
            idx, ALL_CATALOG_NAMES, [PROPOSE_EDIT_TOOL], permission_mode="ask",
        )
        assert _names(out) == self.EXPECTED_ASK_SURFACE

    def test_ask_mode_keeps_frontend_tools_and_find_tools(self):
        """Frontend tools are human-executed by construction — never filtered."""
        idx = _catalog_index(_catalog())
        out = _names(_advertise_discovery_tools(
            idx, ALL_CATALOG_NAMES, [PROPOSE_EDIT_TOOL], permission_mode="ask",
        ))
        assert "find_tools" in out
        assert "confirm_action" in out
        assert "propose_record_edit" in out
        assert "propose_edit" in out

    def test_meta_is_stripped_in_both_modes(self):
        idx = _catalog_index(_catalog())
        for mode in ("write", "ask", "plan"):
            for td in _advertise_discovery_tools(
                idx, ALL_CATALOG_NAMES, [], permission_mode=mode,
            ):
                assert "_meta" not in td["function"]

    # ── RAID Wave B2 — the PLAN surface pin ──────────────────────────────────

    def test_plan_mode_advertises_ask_surface_plus_plan_tools(self):
        idx = _catalog_index(_catalog_with_plan())
        out = _advertise_discovery_tools(
            idx, ALL_CATALOG_NAMES | PLAN_TOOL_NAMES, [PROPOSE_EDIT_TOOL],
            permission_mode="plan",
        )
        assert _names(out) == self.EXPECTED_PLAN_SURFACE

    def test_plan_mode_does_not_advertise_tiered_non_plan_tools(self):
        """A tier-A/W/S server tool that is not `plan_*` stays OFF the plan
        surface (the flagged risk: plan must not become write-lite)."""
        idx = _catalog_index(_catalog_with_plan())
        out = _names(_advertise_discovery_tools(
            idx, ALL_CATALOG_NAMES | PLAN_TOOL_NAMES, [PROPOSE_EDIT_TOOL],
            permission_mode="plan",
        ))
        assert "book_create" not in out
        assert "translation_start_job" not in out
        assert "settings_update" not in out

    def test_write_surface_unchanged_when_plan_tools_present(self):
        """Write mode with plan tools in the catalog advertises everything —
        the plan filter must not leak into write."""
        idx = _catalog_index(_catalog_with_plan())
        out = _advertise_discovery_tools(
            idx, ALL_CATALOG_NAMES | PLAN_TOOL_NAMES, [PROPOSE_EDIT_TOOL],
            permission_mode="write",
        )
        assert _names(out) == self.EXPECTED_WRITE_SURFACE | PLAN_TOOL_NAMES

    def test_ask_surface_excludes_plan_tools(self):
        """Ask stays strictly read-only: the tiered plan_* tools are NOT part
        of the ask surface (plan mode is the only mode that adds them)."""
        idx = _catalog_index(_catalog_with_plan())
        out = _names(_advertise_discovery_tools(
            idx, ALL_CATALOG_NAMES | PLAN_TOOL_NAMES, [PROPOSE_EDIT_TOOL],
            permission_mode="ask",
        ))
        assert out == self.EXPECTED_ASK_SURFACE


class TestFilterToolsForAskPlain:
    """The non-discovery (legacy full-catalog / gateway-down) ask filter."""

    def test_keeps_r_untiered_and_frontend_drops_aws(self):
        tools = _catalog() + [PROPOSE_EDIT_TOOL]
        out = _names(_filter_tools_for_ask(tools))
        assert out == R_CATALOG_NAMES | {"propose_edit"}

    def test_empty_input_yields_empty(self):
        assert _filter_tools_for_ask([]) == []

    def test_plan_mode_keeps_plan_tools_on_the_plain_path(self):
        """RAID B2 — the non-discovery filter keeps R + frontend + plan_*."""
        tools = _catalog_with_plan() + [PROPOSE_EDIT_TOOL]
        out = _names(_filter_tools_for_ask(tools, "plan"))
        assert out == R_CATALOG_NAMES | {"propose_edit"} | PLAN_TOOL_NAMES


# ════════════════════════════════════════════════════════════════════════════
# permission_mode threading — POST body → stream_response → _stream_with_tools
# ════════════════════════════════════════════════════════════════════════════


class TestPermissionModeThreading:
    def _provider(self, mock_provider):
        from app.models import ProviderCredentials
        mock_provider.return_value.resolve = AsyncMock(return_value=ProviderCredentials(
            provider_kind="openai", provider_model_name="gpt-4",
            base_url="https://api.openai.com", api_key="sk-test", context_length=8192,
        ))

    @pytest.mark.asyncio
    @patch("app.routers.messages.get_provider_client")
    @patch("app.routers.messages.get_billing_client")
    @patch("app.routers.messages.stream_response")
    async def test_body_permission_mode_reaches_stream_response(
        self, mock_stream, mock_billing, mock_provider, client, mock_pool
    ):
        conn = mock_pool._conn
        mock_pool.fetchrow.return_value = make_session_record()
        conn.fetchval.return_value = 1
        self._provider(mock_provider)

        async def fake_stream(**kwargs):
            yield "data: [DONE]\n\n"

        mock_stream.return_value = fake_stream()
        resp = await client.post(
            f"/v1/chat/sessions/{TEST_SESSION_ID}/messages",
            json={"content": "Hello", "permission_mode": "ask"},
        )
        assert resp.status_code == 200
        assert mock_stream.call_args.kwargs["permission_mode"] == "ask"

    @pytest.mark.asyncio
    @patch("app.routers.messages.get_provider_client")
    @patch("app.routers.messages.get_billing_client")
    @patch("app.routers.messages.stream_response")
    async def test_absent_permission_mode_defaults_to_write(
        self, mock_stream, mock_billing, mock_provider, client, mock_pool
    ):
        conn = mock_pool._conn
        mock_pool.fetchrow.return_value = make_session_record()
        conn.fetchval.return_value = 1
        self._provider(mock_provider)

        async def fake_stream(**kwargs):
            yield "data: [DONE]\n\n"

        mock_stream.return_value = fake_stream()
        resp = await client.post(
            f"/v1/chat/sessions/{TEST_SESSION_ID}/messages",
            json={"content": "Hello"},
        )
        assert resp.status_code == 200
        assert mock_stream.call_args.kwargs["permission_mode"] == "write"

    @pytest.mark.asyncio
    async def test_invalid_permission_mode_is_422(self, client, mock_pool):
        resp = await client.post(
            f"/v1/chat/sessions/{TEST_SESSION_ID}/messages",
            json={"content": "Hello", "permission_mode": "yolo"},
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_stream_response_forwards_mode_into_tool_loop(self):
        """stream_response → _stream_with_tools carries permission_mode."""
        pool, conn = _make_pool_with_conn()
        pool.fetch.return_value = []
        conn.fetchval.return_value = 1

        kc = _patched_knowledge(tool_defs=_catalog())

        async def fake_tool_loop(**kwargs):
            yield {"content": "ok", "reasoning_content": "",
                   "finish_reason": "stop", "usage": _Usage(1, 1)}

        with patch("app.services.stream_service.get_knowledge_client", return_value=kc), \
             patch("app.services.stream_service._stream_with_tools",
                   side_effect=fake_tool_loop) as loop_mock, \
             patch("app.services.stream_service._stream_via_gateway"):
            async for _ in stream_response(
                session_id=TEST_SESSION_ID,
                user_message_content="hi",
                user_id=TEST_USER_ID,
                model_source="user_model",
                model_ref=TEST_MODEL_REF,
                creds=_make_creds(),
                pool=pool,
                billing=AsyncMock(),
                stream_format="agui",
                permission_mode="ask",
            ):
                pass

        assert loop_mock.call_args.kwargs["permission_mode"] == "ask"
        # The allowlist read is wired in as a callable (DB stays out of the loop).
        assert loop_mock.call_args.kwargs["decision_check"] is not None


# ════════════════════════════════════════════════════════════════════════════
# the per-pass advertise chokepoint in _stream_with_tools
# ════════════════════════════════════════════════════════════════════════════


def _run_modes(
    scripts,
    *,
    knowledge_client,
    tools=None,
    permission_mode="write",
    decision_check=None,
    discovery_catalog=None,
    discovery_seed_names=None,
):
    return _stream_with_tools(
        model_source="user_model",
        model_ref=TEST_MODEL_REF,
        user_id=TEST_USER_ID,
        messages=[{"role": "user", "content": "hi"}],
        gen_params={},
        tools=tools if tools is not None else _catalog(),
        knowledge_client=knowledge_client,
        session_id=TEST_SESSION_ID,
        project_id="proj-1",
        permission_mode=permission_mode,
        decision_check=decision_check,
        discovery_catalog=discovery_catalog,
        discovery_seed_names=discovery_seed_names,
    )


class TestAskChokepointNonDiscovery:
    @pytest.mark.asyncio
    async def test_write_mode_advertises_the_caller_tools_unchanged(self):
        kc = AsyncMock()
        tools = _catalog()
        scripts = [[tok("hi"), done("stop")]]
        with _patch_client(scripts):
            await _drain(_run_modes(scripts, knowledge_client=kc, tools=tools))
        req = _FakeClient.instances[0].requests[0]
        # The caller's tools pass through byte-identical (pre-C2 behavior); the always-on recovery
        # PAIR is appended last, in order: conversation_search (T6/D6) then chat_search_sessions
        # (B1/WS-1.9). (M4/P-2: chat_search_sessions was wired in by a concurrent session, so what
        # used to be a single appended tool is now two — [:-1] became [:-2].)
        assert req.tools[:-2] == tools
        assert [t["function"]["name"] for t in req.tools[-2:]] == [
            "conversation_search", "chat_search_sessions",
        ]

    @pytest.mark.asyncio
    async def test_ask_mode_advertises_only_r_subset(self):
        kc = AsyncMock()
        scripts = [[tok("hi"), done("stop")]]
        with _patch_client(scripts):
            await _drain(_run_modes(scripts, knowledge_client=kc, permission_mode="ask"))
        req = _FakeClient.instances[0].requests[0]
        # conversation_search + chat_search_sessions (both pure reads) are appended in ask mode too —
        # Tier-R-safe recovery tools (T6/D6 + B1/WS-1.9). (M4/P-2 added chat_search_sessions here.)
        assert {t["function"]["name"] for t in req.tools} == (
            R_CATALOG_NAMES | {"conversation_search", "chat_search_sessions"}
        )

    @pytest.mark.asyncio
    async def test_ask_mode_with_no_r_tools_runs_tool_free(self):
        """All-write catalog in ask → the pass streams tool-free instead of
        sending an empty tools array (which 400s on some providers)."""
        kc = AsyncMock()
        tools = [_tiered("book_create", "A"), _tiered("settings_update", "S")]
        scripts = [[tok("hi"), done("stop")]]
        with _patch_client(scripts):
            await _drain(_run_modes(scripts, knowledge_client=kc, tools=tools,
                                    permission_mode="ask"))
        req = _FakeClient.instances[0].requests[0]
        assert req.tools is None
        assert req.tool_choice is None


class TestAskChokepointDiscovery:
    @pytest.mark.asyncio
    async def test_discovery_pass_filters_advertised_to_r(self):
        kc = AsyncMock()
        kc.get_catalog_meta = MagicMock(return_value={})
        scripts = [[tok("hi"), done("stop")]]
        with _patch_client(scripts):
            await _drain(_run_modes(
                scripts, knowledge_client=kc, permission_mode="ask",
                discovery_catalog=_catalog(),
                discovery_seed_names=set(ALL_CATALOG_NAMES),
            ))
        req = _FakeClient.instances[0].requests[0]
        names = {t["function"]["name"] for t in req.tools}
        assert names & ALL_CATALOG_NAMES == R_CATALOG_NAMES
        # discovery machinery intact
        assert "find_tools" in names


class TestAskDefenseInDepth:
    @pytest.mark.asyncio
    async def test_non_r_call_in_ask_returns_error_never_executes(self):
        """Defense-in-depth behind the surface filter: a tier-A call that slips
        through in ask mode feeds a tool-result error, never executes."""
        kc = AsyncMock()
        kc.get_catalog_meta = MagicMock(return_value={})
        scripts = [
            [
                tool_frag(index=0, id="c1", name="book_create"),
                tool_frag(index=0, arguments_delta='{"title":"X"}'),
                done("tool_calls"),
            ],
            [tok("understood, read-only"), done("stop")],
        ]
        with _patch_client(scripts):
            chunks = await _drain(_run_modes(
                scripts, knowledge_client=kc, permission_mode="ask",
                discovery_catalog=_catalog(),
                discovery_seed_names=set(ALL_CATALOG_NAMES),
            ))
        kc.mcp_execute_tool.assert_not_awaited()
        tc = [c["tool_call"] for c in chunks if "tool_call" in c][0]
        assert tc["ok"] is False
        assert "read-only" in tc["error"]
        # the model got a self-correctable tool result
        msgs = _FakeClient.instances[0].requests[1].messages
        tool_msg = next(m for m in msgs if m.get("role") == "tool")
        assert "read-only" in json.loads(tool_msg["content"])["error"]

    @pytest.mark.asyncio
    async def test_r_call_in_ask_still_executes(self):
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
            chunks = await _drain(_run_modes(
                scripts, knowledge_client=kc, permission_mode="ask",
                discovery_catalog=_catalog(),
                discovery_seed_names=set(ALL_CATALOG_NAMES),
            ))
        kc.mcp_execute_tool.assert_awaited_once()
        tc = [c["tool_call"] for c in chunks if "tool_call" in c][0]
        assert tc["ok"] is True

    @pytest.mark.asyncio
    async def test_non_discovery_ask_defense_reads_tier_from_caller_defs(self):
        """The plain (non-discovery) path reads the called tool's tier from the
        caller's defs, so a legacy client in ask mode is covered too."""
        kc = AsyncMock()
        scripts = [
            [
                tool_frag(index=0, id="c1", name="settings_update"),
                tool_frag(index=0, arguments_delta="{}"),
                done("tool_calls"),
            ],
            [tok("nope"), done("stop")],
        ]
        with _patch_client(scripts):
            chunks = await _drain(_run_modes(
                scripts, knowledge_client=kc, permission_mode="ask",
            ))
        kc.mcp_execute_tool.assert_not_awaited()
        tc = [c["tool_call"] for c in chunks if "tool_call" in c][0]
        assert tc["ok"] is False and "read-only" in tc["error"]


# ════════════════════════════════════════════════════════════════════════════
# Write-mode Tier-A prompt-once approval gate
# ════════════════════════════════════════════════════════════════════════════


def _book_create_pass():
    return [
        tool_frag(index=0, id="c1", name="book_create"),
        tool_frag(index=0, arguments_delta='{"title":"My Book"}'),
        usage(10, 4),
        done("tool_calls"),
    ]


class TestWriteApprovalGate:
    @pytest.mark.asyncio
    async def test_unapproved_tier_a_suspends_with_approval_payload(self):
        kc = AsyncMock()
        kc.get_catalog_meta = MagicMock(return_value={})
        check = AsyncMock(return_value=None)
        scripts = [_book_create_pass()]
        with _patch_client(scripts):
            chunks = await _drain(_run_modes(
                scripts, knowledge_client=kc, permission_mode="write",
                decision_check=check,
                discovery_catalog=_catalog(),
                discovery_seed_names=set(ALL_CATALOG_NAMES),
            ))
        kc.mcp_execute_tool.assert_not_awaited()
        # the mutation decision gated the card. (WS-3 also reads both axes up-front for
        # the standing-refusal check, so this is no longer the only await.)
        assert ("book_create",) in [c.args for c in check.await_args_list]
        suspends = [c for c in chunks if "suspend" in c]
        assert len(suspends) == 1
        pending = suspends[0]["suspend"]["pending_tool_call"]
        # DR-C2 pending approval card payload
        assert pending["id"] == "c1"
        assert pending["name"] == "book_create"
        assert pending["args"] == {
            "kind": "tool_approval",
            "tool": "book_create",
            "args": {"title": "My Book"},
            "tier": "A",
        }
        # the dangling assistant tool-call rides `working` for the resume
        assert any(m.get("role") == "assistant" and m.get("tool_calls")
                   for m in suspends[0]["suspend"]["working"])

    @pytest.mark.asyncio
    async def test_allowlisted_tier_a_executes_without_prompt(self):
        kc = AsyncMock()
        kc.get_catalog_meta = MagicMock(return_value={})
        kc.mcp_execute_tool.return_value = _envelope(success=True, result={"book_id": "b1"})
        check = AsyncMock(return_value="allow")
        scripts = [_book_create_pass(), [tok("created"), done("stop")]]
        with _patch_client(scripts):
            chunks = await _drain(_run_modes(
                scripts, knowledge_client=kc, permission_mode="write",
                decision_check=check,
                discovery_catalog=_catalog(),
                discovery_seed_names=set(ALL_CATALOG_NAMES),
            ))
        kc.mcp_execute_tool.assert_awaited_once()
        assert not [c for c in chunks if "suspend" in c]

    @pytest.mark.asyncio
    async def test_allowlist_read_error_degrades_to_a_prompt_never_to_a_grant(self):
        """Track C WS-3 — a DELIBERATE change to DR-C2's original fail-OPEN.

        DR-C2 made an unreadable allowlist degrade to *execute*, reasoning that a DB blip
        must not brick tool calling. That is no longer safe: the SAME read now carries the
        user's standing REFUSAL, so "assume allow on error" would let a transient fault run
        a tool the user permanently denied.

        An unreadable decision is UNKNOWN — and unknown must resolve to ASK, never to run.
        The original intent survives (a card is raised; tool calling is not bricked); what
        is gone is the ability of a DB error to invent a grant nobody gave."""
        kc = AsyncMock()
        kc.get_catalog_meta = MagicMock(return_value={})
        kc.mcp_execute_tool.return_value = _envelope(success=True, result={})
        check = AsyncMock(side_effect=RuntimeError("db down"))
        scripts = [_book_create_pass(), [tok("created"), done("stop")]]
        with _patch_client(scripts):
            chunks = await _drain(_run_modes(
                scripts, knowledge_client=kc, permission_mode="write",
                decision_check=check,
                discovery_catalog=_catalog(),
                discovery_seed_names=set(ALL_CATALOG_NAMES),
            ))
        kc.mcp_execute_tool.assert_not_awaited()          # NOT executed on a read error
        suspends = [c for c in chunks if "suspend" in c]
        assert len(suspends) == 1                          # …it asks instead
        assert suspends[0]["suspend"]["pending_tool_call"]["args"]["kind"] == "tool_approval"

    @pytest.mark.asyncio
    async def test_tier_r_never_raises_a_card_but_is_still_checked_for_a_refusal(self):
        """A Tier-R tool never raises an approval CARD (the prompt is tier+mode scoped).

        But it IS consulted for a standing refusal — Track C WS-3. The first cut scoped
        the deny read to the prompt's own conditions, so a Tier-R tool the user had blocked
        in Settings kept running while the panel said "Never runs". A refusal is not a
        prompt: it must hold wherever the tool can execute."""
        kc = AsyncMock()
        kc.get_catalog_meta = MagicMock(return_value={})
        kc.mcp_execute_tool.return_value = _envelope(success=True, result={})
        check = AsyncMock(return_value=None)
        scripts = [
            [
                tool_frag(index=0, id="c1", name="glossary_search"),
                tool_frag(index=0, arguments_delta="{}"),
                done("tool_calls"),
            ],
            [tok("done"), done("stop")],
        ]
        with _patch_client(scripts):
            chunks = await _drain(_run_modes(
                scripts, knowledge_client=kc, permission_mode="write",
                decision_check=check,
                discovery_catalog=_catalog(),
                discovery_seed_names=set(ALL_CATALOG_NAMES),
            ))
        check.assert_awaited()                             # the refusal WAS checked
        assert not [c for c in chunks if "suspend" in c]   # but no card was raised
        kc.mcp_execute_tool.assert_awaited_once()          # and with no deny on file, it runs

    @pytest.mark.asyncio
    async def test_a_denied_tier_r_tool_is_blocked(self):
        """The bug the review caught, as a test: a Tier-R tool is blockable, and the block
        is honored — even though a Tier-R tool never raises an approval card."""
        kc = AsyncMock()
        kc.get_catalog_meta = MagicMock(return_value={})
        kc.mcp_execute_tool.return_value = _envelope(success=True, result={})
        check = AsyncMock(return_value="deny")
        scripts = [
            [
                tool_frag(index=0, id="c1", name="glossary_search"),
                tool_frag(index=0, arguments_delta="{}"),
                done("tool_calls"),
            ],
            [tok("done"), done("stop")],
        ]
        with _patch_client(scripts):
            chunks = await _drain(_run_modes(
                scripts, knowledge_client=kc, permission_mode="write",
                decision_check=check,
                discovery_catalog=_catalog(),
                discovery_seed_names=set(ALL_CATALOG_NAMES),
            ))
        kc.mcp_execute_tool.assert_not_awaited()           # blocked
        assert not [c for c in chunks if "suspend" in c]   # and never nagged about
        errs = [c["tool_call"]["error"] for c in chunks if "tool_call" in c]
        assert any("Never allow" in (e or "") for e in errs)

    @pytest.mark.asyncio
    async def test_a_denied_tier_a_tool_is_blocked_in_plan_mode(self):
        """Plan mode lets Tier-A `plan_*` tools through the mode filter by design — so it
        was the other silent hole: the deny read only ran in WRITE mode, so a blocked
        planning tool executed anyway."""
        kc = AsyncMock()
        kc.get_catalog_meta = MagicMock(return_value={})
        kc.mcp_execute_tool.return_value = _envelope(success=True, result={})
        check = AsyncMock(return_value="deny")
        scripts = [
            [
                tool_frag(index=0, id="c1", name="plan_propose_spec"),
                tool_frag(index=0, arguments_delta="{}"),
                done("tool_calls"),
            ],
            [tok("done"), done("stop")],
        ]
        with _patch_client(scripts):
            chunks = await _drain(_run_modes(
                scripts, knowledge_client=kc, permission_mode="plan",
                decision_check=check,
                discovery_catalog=_catalog(),
                discovery_seed_names=set(ALL_CATALOG_NAMES),
            ))
        kc.mcp_execute_tool.assert_not_awaited()
        errs = [c["tool_call"]["error"] for c in chunks if "tool_call" in c]
        assert any("Never allow" in (e or "") for e in errs)

    @pytest.mark.asyncio
    async def test_no_decision_check_preserves_legacy_behavior(self):
        """decision_check=None (any caller not wired for C2) → Tier-A
        auto-commits exactly as before."""
        kc = AsyncMock()
        kc.get_catalog_meta = MagicMock(return_value={})
        kc.mcp_execute_tool.return_value = _envelope(success=True, result={})
        scripts = [_book_create_pass(), [tok("created"), done("stop")]]
        with _patch_client(scripts):
            chunks = await _drain(_run_modes(
                scripts, knowledge_client=kc, permission_mode="write",
                decision_check=None,
                discovery_catalog=_catalog(),
                discovery_seed_names=set(ALL_CATALOG_NAMES),
            ))
        kc.mcp_execute_tool.assert_awaited_once()
        assert not [c for c in chunks if "suspend" in c]


# ════════════════════════════════════════════════════════════════════════════
# suspend persists permission_mode (through stream_response)
# ════════════════════════════════════════════════════════════════════════════


class TestSuspendPersistsMode:
    @pytest.mark.asyncio
    async def test_frontend_suspend_saves_the_turn_mode(self):
        """An ask-mode turn that suspends (frontend tools stay available in ask)
        persists permission_mode='ask' so the resume continues under it."""
        pool, conn = _make_pool_with_conn()
        pool.fetch.return_value = []
        conn.fetchval.return_value = 1

        # Gateway-down agui editor surface: catalog empty → no discovery, but
        # the frontend write-back tool is re-advertised → suspend path works.
        kc = _patched_knowledge(tool_defs=[])

        scripts = [[
            tool_frag(index=0, id="c1", name="propose_edit"),
            tool_frag(index=0, arguments_delta='{"operation":"insert_at_cursor","text":"x"}'),
            done("tool_calls"),
        ]]
        save_mock = AsyncMock()
        steering = MagicMock()
        steering.get_steering = AsyncMock(return_value=[])
        with _patch_client(scripts), \
             patch("app.services.stream_service.get_knowledge_client", return_value=kc), \
             patch("app.services.stream_service.save_suspended_run", save_mock), \
             patch("app.client.book_steering_client.get_book_steering_client",
                   return_value=steering):
            async for _ in stream_response(
                session_id=TEST_SESSION_ID,
                user_message_content="edit this",
                user_id=TEST_USER_ID,
                model_source="user_model",
                model_ref=TEST_MODEL_REF,
                creds=_make_creds(),
                pool=pool,
                billing=AsyncMock(),
                stream_format="agui",
                editor_context={"book_id": "b1", "chapter_id": "ch1"},
                permission_mode="ask",
            ):
                pass

        save_mock.assert_awaited_once()
        assert save_mock.await_args.kwargs["permission_mode"] == "ask"


# ════════════════════════════════════════════════════════════════════════════
# resume outcomes — approved_once / approved_always / denied
# ════════════════════════════════════════════════════════════════════════════


def _approval_suspended(permission_mode: str = "write") -> SuspendedRun:
    return SuspendedRun(
        run_id="run-appr",
        session_id=str(TEST_SESSION_ID),
        owner_user_id=str(TEST_USER_ID),
        message_id=str(uuid4()),
        working=[
            {"role": "user", "content": "make a book"},
            {"role": "assistant", "content": "",
             "tool_calls": [{"id": "c1", "type": "function",
                             "function": {"name": "book_create",
                                          "arguments": '{"title":"My Book"}'}}]},
        ],
        pending_tool_call={
            "id": "c1", "name": "book_create",
            "args": {"kind": "tool_approval", "tool": "book_create",
                     "args": {"title": "My Book"}, "tier": "A"},
        },
        input_tokens=10,
        output_tokens=4,
        model_source="user_model",
        model_ref=str(TEST_MODEL_REF),
        parent_message_id=None,
        user_message_content="make a book",
        permission_mode=permission_mode,
    )


def _resume(pool, kc, outcome: str):
    return resume_stream_response(
        session_id=str(TEST_SESSION_ID), user_id=str(TEST_USER_ID),
        run_id="run-appr", tool_call_id="c1", outcome=outcome,
        applied_text=None, creds=_creds(), pool=pool, billing=AsyncMock(),
        stream_format="agui",
    )


class TestApprovalResume:
    def _pool(self):
        pool, conn = _make_pool_with_conn()
        conn.fetchval.return_value = 1
        pool.fetchrow.return_value = {"generation_params": {}, "project_id": None}
        return pool

    def _kc(self):
        kc = AsyncMock()
        kc.get_tool_definitions.return_value = []
        kc.mcp_execute_tool.return_value = _envelope(
            success=True,
            result={"book_id": "b1",
                    "_meta": {"summary": "Created 'My Book'",
                              "undo_hint": {"tool": "book_delete",
                                            "args": {"book_id": "b1"}}}},
        )
        return kc

    @pytest.mark.asyncio
    async def test_approved_once_executes_and_feeds_real_result(self):
        pool = self._pool()
        kc = self._kc()
        approve_mock = AsyncMock()
        scripts = [[tok("Created it."), usage(5, 5), done("stop")]]
        with _patch_client(scripts), \
             patch("app.services.stream_service.get_knowledge_client", return_value=kc), \
             patch("app.services.stream_service.approve_tool", approve_mock), \
             patch("app.services.stream_service.load_suspended_run",
                   AsyncMock(return_value=_approval_suspended())), \
             patch("app.services.stream_service.delete_suspended_run", AsyncMock()):
            lines = [l async for l in _resume(pool, kc, "approved_once")]

        kc.mcp_execute_tool.assert_awaited_once()
        kw = kc.mcp_execute_tool.await_args.kwargs
        assert kw["tool_name"] == "book_create"
        assert kw["tool_args"] == {"title": "My Book"}
        assert kw["user_id"] == str(TEST_USER_ID)
        approve_mock.assert_not_awaited()  # once ≠ always

        # the REAL result was appended for the 2nd pass
        msgs = _FakeClient.instances[0].requests[0].messages
        tool_msg = next(m for m in msgs if m.get("role") == "tool"
                        and m.get("tool_call_id") == "c1")
        assert json.loads(tool_msg["content"])["book_id"] == "b1"

        # the executed call is surfaced to the FE (tool_call + activity events)
        events = [json.loads(l.removeprefix("data: ").strip())
                  for l in lines if l.startswith("data: ")]
        results = [e for e in events if e.get("type") == "TOOL_CALL_RESULT"]
        assert any(json.loads(r["content"]).get("ok") for r in results)
        activities = [e for e in events
                      if e.get("type") == "CUSTOM" and e.get("name") == "activity"]
        assert len(activities) == 1
        assert activities[0]["value"]["undo"]["available"] is True
        assert activities[0]["value"]["undo"]["tool"] == "book_delete"

    @pytest.mark.asyncio
    async def test_approved_always_persists_allowlist_row_then_executes(self):
        pool = self._pool()
        kc = self._kc()
        approve_mock = AsyncMock()
        scripts = [[tok("Created it."), done("stop")]]
        with _patch_client(scripts), \
             patch("app.services.stream_service.get_knowledge_client", return_value=kc), \
             patch("app.services.stream_service.approve_tool", approve_mock), \
             patch("app.services.stream_service.load_suspended_run",
                   AsyncMock(return_value=_approval_suspended())), \
             patch("app.services.stream_service.delete_suspended_run", AsyncMock()):
            async for _ in _resume(pool, kc, "approved_always"):
                pass

        approve_mock.assert_awaited_once_with(pool, str(TEST_USER_ID), "book_create")
        kc.mcp_execute_tool.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_approved_always_still_executes_when_persist_fails(self):
        """The human approved THIS call — a failed allowlist write only means a
        future re-prompt, never a dropped execution."""
        pool = self._pool()
        kc = self._kc()
        approve_mock = AsyncMock(side_effect=RuntimeError("db down"))
        scripts = [[tok("Created it."), done("stop")]]
        with _patch_client(scripts), \
             patch("app.services.stream_service.get_knowledge_client", return_value=kc), \
             patch("app.services.stream_service.approve_tool", approve_mock), \
             patch("app.services.stream_service.load_suspended_run",
                   AsyncMock(return_value=_approval_suspended())), \
             patch("app.services.stream_service.delete_suspended_run", AsyncMock()):
            async for _ in _resume(pool, kc, "approved_always"):
                pass
        kc.mcp_execute_tool.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_denied_feeds_error_and_never_executes(self):
        pool = self._pool()
        kc = self._kc()
        scripts = [[tok("Okay, I won't."), done("stop")]]
        with _patch_client(scripts), \
             patch("app.services.stream_service.get_knowledge_client", return_value=kc), \
             patch("app.services.stream_service.approve_tool", AsyncMock()), \
             patch("app.services.stream_service.load_suspended_run",
                   AsyncMock(return_value=_approval_suspended())), \
             patch("app.services.stream_service.delete_suspended_run", AsyncMock()):
            async for _ in _resume(pool, kc, "denied"):
                pass

        kc.mcp_execute_tool.assert_not_awaited()
        msgs = _FakeClient.instances[0].requests[0].messages
        tool_msg = next(m for m in msgs if m.get("role") == "tool"
                        and m.get("tool_call_id") == "c1")
        assert json.loads(tool_msg["content"]) == {"error": "denied by user"}

    @pytest.mark.asyncio
    async def test_denied_always_persists_a_deny_and_never_executes(self):
        """D3 (PO sign-off) — "Never allow" ON THE CARD: the resume persists a standing
        DENY (so the tool never prompts again) AND executes nothing this call. Distinct
        from one-shot `denied`, which blocks only this call."""
        pool = self._pool()
        kc = self._kc()
        set_decision_mock = AsyncMock()
        scripts = [[tok("Understood — I won't use that tool."), done("stop")]]
        with _patch_client(scripts), \
             patch("app.services.stream_service.get_knowledge_client", return_value=kc), \
             patch("app.services.stream_service.set_tool_decision", set_decision_mock), \
             patch("app.services.stream_service.load_suspended_run",
                   AsyncMock(return_value=_approval_suspended())), \
             patch("app.services.stream_service.delete_suspended_run", AsyncMock()):
            async for _ in _resume(pool, kc, "denied_always"):
                pass

        # a standing deny was persisted for the mutation kind (the card carried no
        # approval_kinds → defaults to ["mutation"])
        set_decision_mock.assert_awaited_once_with(
            pool, str(TEST_USER_ID), "book_create", "mutation", "deny"
        )
        # and NOTHING executed — the model is told "denied by user"
        kc.mcp_execute_tool.assert_not_awaited()
        msgs = _FakeClient.instances[0].requests[0].messages
        tool_msg = next(m for m in msgs if m.get("role") == "tool"
                        and m.get("tool_call_id") == "c1")
        assert json.loads(tool_msg["content"]) == {"error": "denied by user"}

    @pytest.mark.asyncio
    async def test_denied_always_persists_all_kinds_despite_a_partial_standing_deny(self):
        """D3 /review-impl defect: a paid card carries spend+mutation. If the user had
        already denied ONLY mutation in Settings, clicking "Never allow" on the stale card
        must STILL persist the SPEND deny — the standing-deny re-check must not downgrade
        denied_always to one-shot 'denied' (which would suppress its persist block and drop
        the other kinds, so the complete refusal the user clicked silently evaporates)."""
        pool = self._pool()
        kc = self._kc()
        set_decision_mock = AsyncMock()
        susp = _approval_suspended()
        susp.pending_tool_call["args"]["approval_kinds"] = ["spend", "mutation"]  # a paid card

        async def _get_decision(_pool, _user, _tool, kind="mutation"):
            return "deny" if kind == "mutation" else None  # only mutation pre-denied

        scripts = [[tok("ok"), done("stop")]]
        with _patch_client(scripts), \
             patch("app.services.stream_service.get_knowledge_client", return_value=kc), \
             patch("app.services.stream_service.get_tool_decision",
                   AsyncMock(side_effect=_get_decision)), \
             patch("app.services.stream_service.set_tool_decision", set_decision_mock), \
             patch("app.services.stream_service.load_suspended_run",
                   AsyncMock(return_value=susp)), \
             patch("app.services.stream_service.delete_suspended_run", AsyncMock()):
            async for _ in _resume(pool, kc, "denied_always"):
                pass

        denied_kinds = {c.args[3] for c in set_decision_mock.await_args_list}
        assert denied_kinds == {"spend", "mutation"}, "both kinds must be denied, not just the pre-existing one"
        kc.mcp_execute_tool.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_denied_always_still_refuses_when_persist_fails(self):
        """A failed deny-persist must NOT flip the refusal into an execution — the user
        said never; the worst outcome is running it anyway on a DB blip."""
        pool = self._pool()
        kc = self._kc()
        set_decision_mock = AsyncMock(side_effect=RuntimeError("db down"))
        scripts = [[tok("ok"), done("stop")]]
        with _patch_client(scripts), \
             patch("app.services.stream_service.get_knowledge_client", return_value=kc), \
             patch("app.services.stream_service.set_tool_decision", set_decision_mock), \
             patch("app.services.stream_service.load_suspended_run",
                   AsyncMock(return_value=_approval_suspended())), \
             patch("app.services.stream_service.delete_suspended_run", AsyncMock()):
            async for _ in _resume(pool, kc, "denied_always"):
                pass
        kc.mcp_execute_tool.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_unknown_outcome_on_approval_treated_as_denied(self):
        """Fail-closed on the approval decision itself: an unrecognized outcome
        never executes the write."""
        pool = self._pool()
        kc = self._kc()
        scripts = [[tok("ok"), done("stop")]]
        with _patch_client(scripts), \
             patch("app.services.stream_service.get_knowledge_client", return_value=kc), \
             patch("app.services.stream_service.approve_tool", AsyncMock()), \
             patch("app.services.stream_service.load_suspended_run",
                   AsyncMock(return_value=_approval_suspended())), \
             patch("app.services.stream_service.delete_suspended_run", AsyncMock()):
            async for _ in _resume(pool, kc, "applied"):
                pass
        kc.mcp_execute_tool.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_non_approval_resume_is_unchanged(self):
        """Regression: the ordinary frontend-tool resume (propose_edit outcome
        echo) is byte-identical — the C2 branch only fires on kind=tool_approval."""
        from tests.test_frontend_tools import _suspended
        pool = self._pool()
        kc = self._kc()
        scripts = [[tok("Applied."), done("stop")]]
        with _patch_client(scripts), \
             patch("app.services.stream_service.get_knowledge_client", return_value=kc), \
             patch("app.services.stream_service.load_suspended_run",
                   AsyncMock(return_value=_suspended(1, 1))), \
             patch("app.services.stream_service.delete_suspended_run", AsyncMock()):
            async for _ in resume_stream_response(
                session_id=str(TEST_SESSION_ID), user_id=str(TEST_USER_ID),
                run_id="run-1", tool_call_id="c1", outcome="applied",
                applied_text="x", creds=_creds(), pool=pool, billing=AsyncMock(),
                stream_format="agui",
            ):
                pass
        kc.mcp_execute_tool.assert_not_awaited()
        msgs = _FakeClient.instances[0].requests[0].messages
        tool_msg = next(m for m in msgs if m.get("role") == "tool"
                        and m.get("tool_call_id") == "c1")
        assert json.loads(tool_msg["content"]) == {"outcome": "applied", "applied_text": "x"}
