"""RAID Wave B2 (07S §5b) — PLAN mode: research + PlanForge planning, no prose.

Covers:
 - the plan-mode surface at both advertise chokepoints (discovery + plain):
   ask surface (tier R + find_tools + frontend) PLUS the `plan_*` tools,
 - defense-in-depth: a tiered non-plan server tool call in plan mode feeds a
   "plan mode" tool-result error and never executes; `plan_*` and tier-R still
   execute,
 - `plan_*` tools run WITHOUT the C2 Tier-A approval suspend in plan mode
   (the approval gate is write-mode-only — pinned here),
 - plan_forge skill auto-injection in plan mode (and NOT in write/ask),
 - the plan-mode system nudge lands on BOTH system-part assembly paths
   (plain string join + Anthropic cache_control parts),
 - the suspended-run row round-trips permission_mode='plan' and the resume
   continues under plan-mode rules,
 - the router accepts permission_mode='plan' (junk still 422s — pinned in
   test_permission_modes).

Reuses the `_FakeClient` scripting harness from test_stream_tools and the
representative tiered catalog from test_permission_modes.
"""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.db.suspended_runs import SuspendedRun
from app.services.frontend_tools import PROPOSE_EDIT_TOOL
from app.services.skill_registry import resolve_skills_to_inject
from app.services.stream_service import (
    ASK_MODE_NUDGE,
    PLAN_MODE_NUDGE,
    _stream_with_tools,
    resume_stream_response,
    stream_response,
)
from app.services.tool_surface import SessionToolPins, discovery_seed_for_surface
from tests.conftest import (
    TEST_MODEL_REF,
    TEST_SESSION_ID,
    TEST_USER_ID,
    make_session_record,
)
from tests.test_frontend_tools import _creds
from tests.test_permission_modes import (
    ALL_CATALOG_NAMES,
    PLAN_TOOL_NAMES,
    R_CATALOG_NAMES,
    _catalog_with_plan,
)
from tests.test_stream_service import (
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
)

ALL_PLAN_ACTIVE = ALL_CATALOG_NAMES | PLAN_TOOL_NAMES


def _run_plan(
    scripts,
    *,
    knowledge_client,
    tools=None,
    permission_mode="plan",
    decision_check=None,
    discovery_catalog=None,
    discovery_seed_names=None,
):
    return _stream_with_tools(
        model_source="user_model",
        model_ref=TEST_MODEL_REF,
        user_id=TEST_USER_ID,
        messages=[{"role": "user", "content": "plan chapter 3"}],
        gen_params={},
        tools=tools if tools is not None else _catalog_with_plan(),
        knowledge_client=knowledge_client,
        session_id=TEST_SESSION_ID,
        project_id="proj-1",
        permission_mode=permission_mode,
        decision_check=decision_check,
        discovery_catalog=discovery_catalog,
        discovery_seed_names=discovery_seed_names,
    )


# ════════════════════════════════════════════════════════════════════════════
# the per-pass advertise chokepoint — plan surface (discovery + plain)
# ════════════════════════════════════════════════════════════════════════════


class TestPlanChokepoint:
    @pytest.mark.asyncio
    async def test_plain_path_advertises_r_plus_plan_tools(self):
        kc = AsyncMock()
        scripts = [[tok("plan"), done("stop")]]
        with _patch_client(scripts):
            await _drain(_run_plan(scripts, knowledge_client=kc))
        req = _FakeClient.instances[0].requests[0]
        # + the always-on recovery pair appended when tools are offered:
        #   conversation_search (T6/D6, same-session) + chat_search_sessions (B1/WS-1.9, cross-session).
        # (chat_search_sessions added here by M4/P-2 — a concurrent session wired it in and left this
        #  assertion listing only conversation_search.)
        assert {t["function"]["name"] for t in req.tools} == (
            R_CATALOG_NAMES | PLAN_TOOL_NAMES | {"conversation_search", "chat_search_sessions"}
        )

    @pytest.mark.asyncio
    async def test_discovery_pass_advertises_r_plus_plan_tools(self):
        kc = AsyncMock()
        kc.get_catalog_meta = MagicMock(return_value={})
        scripts = [[tok("plan"), done("stop")]]
        with _patch_client(scripts):
            await _drain(_run_plan(
                scripts, knowledge_client=kc,
                discovery_catalog=_catalog_with_plan(),
                discovery_seed_names=set(ALL_PLAN_ACTIVE),
            ))
        req = _FakeClient.instances[0].requests[0]
        names = {t["function"]["name"] for t in req.tools}
        assert names & ALL_PLAN_ACTIVE == R_CATALOG_NAMES | PLAN_TOOL_NAMES
        # discovery machinery intact in plan mode
        assert "find_tools" in names


# ════════════════════════════════════════════════════════════════════════════
# the REAL discovery-seeding function — every other test in this module
# hand-injects `discovery_seed_names`, which masked a real gap: turn 1 of a
# Plan-mode session never seeded plan_* tools at all (tool_discovery.py's
# hot-domain sets never included "plan"), so the plan_forge skill's "Act — do
# NOT narrate, emit the tool call" instruction pointed at a tool the model had
# no schema for. These exercise `discovery_seed_for_surface` itself.
# ════════════════════════════════════════════════════════════════════════════


class TestPlanModeRealSeeding:
    def _auto_pins(self) -> SessionToolPins:
        return SessionToolPins(
            effective_enabled=[],
            effective_skills=[],
            curated_mode=False,
            activation_state={"activated_tools": [], "dirty": False},
        )

    def test_plan_mode_seeds_plan_tools_on_book_surface(self):
        names = discovery_seed_for_surface(
            _catalog_with_plan(), pins=self._auto_pins(),
            editor=False, book_scoped=True, permission_mode="plan",
        )
        assert PLAN_TOOL_NAMES <= names

    def test_plan_mode_seeds_plan_tools_on_editor_surface(self):
        names = discovery_seed_for_surface(
            _catalog_with_plan(), pins=self._auto_pins(),
            editor=True, book_scoped=True, permission_mode="plan",
        )
        assert PLAN_TOOL_NAMES <= names

    def test_write_mode_does_not_seed_plan_tools(self):
        """Regression guard: the plan hot-domain must not leak into write mode."""
        names = discovery_seed_for_surface(
            _catalog_with_plan(), pins=self._auto_pins(),
            editor=False, book_scoped=True, permission_mode="write",
        )
        assert not (PLAN_TOOL_NAMES & names)

    def test_ask_mode_does_not_seed_plan_tools(self):
        names = discovery_seed_for_surface(
            _catalog_with_plan(), pins=self._auto_pins(),
            editor=False, book_scoped=True, permission_mode="ask",
        )
        assert not (PLAN_TOOL_NAMES & names)

    def test_curated_plan_mode_seeds_plan_tools_even_when_unpinned(self):
        """A curated session (explicit tool-name pins) that pinned only
        ["glossary_search"] — no plan_* name, no "glossary" skill — must still
        get plan_* tools in Plan mode: plan_forge auto-injects regardless of
        curated pins (skill_registry.resolve_skills_to_inject), so its tools
        can't be stranded behind the glossary-specific union gate. Exercises the
        SHARED-budget path (empty effective_skills on a book-scoped surface
        already triggers the glossary-gate's union, which now includes "plan"
        via surface_hot_domains — no separate carve-out call needed here)."""
        pins = SessionToolPins(
            effective_enabled=["glossary_search"],
            effective_skills=[],
            curated_mode=True,
            activation_state={"activated_tools": [], "dirty": False},
        )
        names = discovery_seed_for_surface(
            _catalog_with_plan(), pins=pins,
            editor=False, book_scoped=True, permission_mode="plan",
        )
        assert PLAN_TOOL_NAMES <= names
        assert "glossary_search" in names

    def test_curated_plan_mode_seeds_plan_tools_via_separate_carveout_when_glossary_gate_skips(self):
        """review-impl follow-up: a curated session with a NON-EMPTY pinned skill
        set that excludes "glossary" (so the glossary-gate union in
        `effective_enabled_tools` is skipped entirely — `glossary_in_skills` is
        False) must still get plan_* tools via the separate carve-out branch,
        and that branch must NOT ALSO double-run the shared union (there is
        nothing shared to double here — this is the one place a second,
        independently-budgeted call is correct)."""
        pins = SessionToolPins(
            effective_enabled=["glossary_search"],
            effective_skills=["knowledge"],  # non-empty, excludes "glossary"
            curated_mode=True,
            activation_state={"activated_tools": [], "dirty": False},
        )
        names = discovery_seed_for_surface(
            _catalog_with_plan(), pins=pins,
            editor=False, book_scoped=True, permission_mode="plan",
        )
        assert PLAN_TOOL_NAMES <= names
        assert "glossary_search" in names  # the explicit pin still rides along
        # the glossary hot-domain union did NOT run (gate skipped) — story/glossary
        # hot tools beyond the explicit pin are absent, proving this came from the
        # carve-out, not the shared union.
        assert "glossary_get_entity" not in names


# ════════════════════════════════════════════════════════════════════════════
# defense-in-depth + the no-approval-prompt rule for plan_* tools
# ════════════════════════════════════════════════════════════════════════════


class TestPlanDefenseInDepth:
    @pytest.mark.asyncio
    async def test_non_plan_write_tool_errors_and_never_executes(self):
        """A tier-A non-plan tool call that slips through in plan mode feeds a
        plan-mode tool-result error the model can self-correct from."""
        kc = AsyncMock()
        kc.get_catalog_meta = MagicMock(return_value={})
        scripts = [
            [
                tool_frag(index=0, id="c1", name="book_create"),
                tool_frag(index=0, arguments_delta='{"title":"X"}'),
                done("tool_calls"),
            ],
            [tok("understood, planning only"), done("stop")],
        ]
        with _patch_client(scripts):
            chunks = await _drain(_run_plan(
                scripts, knowledge_client=kc,
                discovery_catalog=_catalog_with_plan(),
                discovery_seed_names=set(ALL_PLAN_ACTIVE),
            ))
        kc.mcp_execute_tool.assert_not_awaited()
        tc = [c["tool_call"] for c in chunks if "tool_call" in c][0]
        assert tc["ok"] is False
        assert "plan mode" in tc["error"]
        assert "Write" in tc["error"]  # steers to the mode switch
        # the model got a self-correctable tool result
        msgs = _FakeClient.instances[0].requests[1].messages
        tool_msg = next(m for m in msgs if m.get("role") == "tool")
        assert "plan mode" in json.loads(tool_msg["content"])["error"]

    @pytest.mark.asyncio
    async def test_plan_tool_executes_without_approval_suspend(self):
        """Pins the DR-B2 rule: the C2 Tier-A approval gate applies in WRITE
        mode only — a tier-A `plan_*` tool in plan mode executes directly,
        even when the allowlist would deny it (no `tool_approval` suspend)."""
        kc = AsyncMock()
        kc.get_catalog_meta = MagicMock(return_value={})
        kc.mcp_execute_tool.return_value = _envelope(
            success=True, result={"run_id": "pr-1"})
        check = AsyncMock(return_value=None)  # would gate in write mode
        scripts = [
            [
                tool_frag(index=0, id="c1", name="plan_propose_spec"),
                tool_frag(index=0, arguments_delta='{"book_id":"b1"}'),
                done("tool_calls"),
            ],
            [tok("proposed"), done("stop")],
        ]
        with _patch_client(scripts):
            chunks = await _drain(_run_plan(
                scripts, knowledge_client=kc, decision_check=check,
                discovery_catalog=_catalog_with_plan(),
                discovery_seed_names=set(ALL_PLAN_ACTIVE),
            ))
        kc.mcp_execute_tool.assert_awaited_once()
        # The write-mode approval CARD never fires in plan mode (planning artifacts are
        # the mode's whole point and are reversible plan_runs rows). Track C WS-3: the
        # standing REFUSAL is still read — plan-mode Tier-A was one of the two silent holes
        # where a tool the user had blocked in Settings kept running — but with no decision
        # on file it neither prompts nor blocks, so the tool executes exactly as before.
        assert not [c for c in chunks if "suspend" in c]
        tc = [c["tool_call"] for c in chunks if "tool_call" in c][0]
        assert tc["ok"] is True and tc["tool"] == "plan_propose_spec"

    @pytest.mark.asyncio
    async def test_r_tool_still_executes_in_plan_mode(self):
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
            chunks = await _drain(_run_plan(
                scripts, knowledge_client=kc,
                discovery_catalog=_catalog_with_plan(),
                discovery_seed_names=set(ALL_PLAN_ACTIVE),
            ))
        kc.mcp_execute_tool.assert_awaited_once()
        assert [c["tool_call"] for c in chunks if "tool_call" in c][0]["ok"] is True

    @pytest.mark.asyncio
    async def test_plain_path_defense_reads_tier_from_caller_defs(self):
        """The non-discovery path rejects a tiered non-plan tool too."""
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
            chunks = await _drain(_run_plan(scripts, knowledge_client=kc))
        kc.mcp_execute_tool.assert_not_awaited()
        tc = [c["tool_call"] for c in chunks if "tool_call" in c][0]
        assert tc["ok"] is False and "plan mode" in tc["error"]


# ════════════════════════════════════════════════════════════════════════════
# plan_forge skill auto-injection
# ════════════════════════════════════════════════════════════════════════════


class TestPlanSkillAutoInject:
    def _resolve(self, *, permission_mode, enabled_skills=None,
                 editor=False, book_scoped=True):
        return resolve_skills_to_inject(
            enabled_skills=enabled_skills or [],
            stream_format="agui",
            disable_tools=False,
            tool_calling_enabled=True,
            editor=editor,
            book_scoped=book_scoped,
            admin=False,
            permission_mode=permission_mode,
        )

    def test_plan_mode_injects_plan_forge_on_book_surface(self):
        codes = self._resolve(permission_mode="plan")
        assert "plan_forge" in codes
        # the surface defaults still ride along
        assert "glossary" in codes and "knowledge" in codes

    def test_plan_mode_injects_plan_forge_on_editor_surface(self):
        assert "plan_forge" in self._resolve(
            permission_mode="plan", editor=True, book_scoped=True)

    def test_plan_mode_does_not_inject_on_plain_chat_surface(self):
        """plan_forge is book/editor-only — a plain-chat plan turn stays out."""
        assert "plan_forge" not in self._resolve(
            permission_mode="plan", book_scoped=False)

    def test_write_and_ask_modes_do_not_auto_inject(self):
        assert "plan_forge" not in self._resolve(permission_mode="write")
        assert "plan_forge" not in self._resolve(permission_mode="ask")

    def test_plan_mode_with_pins_appends_plan_forge(self):
        """A curated pin set that omits plan_forge still gets it in plan mode."""
        codes = self._resolve(permission_mode="plan", enabled_skills=["glossary"])
        assert codes == ["glossary", "plan_forge"]

    def test_plan_mode_never_duplicates_a_pinned_plan_forge(self):
        codes = self._resolve(
            permission_mode="plan", enabled_skills=["plan_forge", "glossary"])
        assert codes.count("plan_forge") == 1

    def test_write_mode_pinned_plan_forge_still_resolves(self):
        """Regression: pinning plan_forge outside plan mode keeps working."""
        assert "plan_forge" in self._resolve(
            permission_mode="write", enabled_skills=["plan_forge"])


# ════════════════════════════════════════════════════════════════════════════
# the plan-mode system nudge — BOTH assembly paths
# ════════════════════════════════════════════════════════════════════════════


def _steering_mock():
    steering = MagicMock()
    steering.get_steering = AsyncMock(return_value=[])
    return steering


async def _drive_stream_response(kc, creds, permission_mode: str):
    pool, conn = _make_pool_with_conn()
    pool.fetch.return_value = []
    conn.fetchval.return_value = 1
    scripts = [[tok("hi"), done("stop")]]
    with _patch_client(scripts), \
         patch("app.services.stream_service.get_knowledge_client", return_value=kc), \
         patch("app.client.book_steering_client.get_book_steering_client",
               return_value=_steering_mock()):
        async for _ in stream_response(
            session_id=TEST_SESSION_ID,
            user_message_content="plan the next arc",
            user_id=TEST_USER_ID,
            model_source="user_model",
            model_ref=TEST_MODEL_REF,
            creds=creds,
            pool=pool,
            billing=AsyncMock(),
            stream_format="agui",
            book_context={"book_id": "b1"},
            permission_mode=permission_mode,
        ):
            pass
    return _FakeClient.instances[0].requests[0].messages


class TestPlanNudgeBothAssemblyPaths:
    @pytest.mark.asyncio
    async def test_plain_string_path_carries_nudge_and_skill(self):
        """Non-Anthropic (plain join) path: the system message carries the
        plan nudge AND the auto-injected plan_forge skill body."""
        kc = _patched_knowledge(tool_defs=_catalog_with_plan())
        msgs = await _drive_stream_response(kc, _creds(), "plan")
        system = next(m for m in msgs if m["role"] == "system")
        assert isinstance(system["content"], str)
        assert PLAN_MODE_NUDGE in system["content"]
        # plan_forge skill body auto-injected (names the flow's first tool)
        assert "plan_propose_spec" in system["content"]

    @pytest.mark.asyncio
    async def test_anthropic_parts_path_carries_nudge_and_skill(self):
        """Anthropic cache_control (structured parts) path: the nudge is one
        of the system parts."""
        kc = _patched_knowledge(
            stable='<memory mode="static"><project/></memory>',
            tool_defs=_catalog_with_plan(),
        )
        msgs = await _drive_stream_response(kc, _make_creds(), "plan")
        system = next(m for m in msgs if m["role"] == "system")
        assert isinstance(system["content"], list)
        texts = [p["text"] for p in system["content"]]
        assert PLAN_MODE_NUDGE in texts
        assert any("plan_propose_spec" in t for t in texts)

    @pytest.mark.asyncio
    async def test_write_mode_has_no_nudge_or_auto_skill(self):
        """Write mode stays byte-identical: no nudge, no plan_forge body. Checks
        a phrase unique to the skill BODY, not a bare tool name (the always-on
        group directory legitimately names every plan_* tool as a find_tools
        pointer in every mode) nor the "Act — do NOT narrate" heading (shared
        verbatim with glossary_skill.py) nor "hand off to drafting" (also in
        the surface-gated, mode-independent L1 skill-metadata description)."""
        kc = _patched_knowledge(tool_defs=_catalog_with_plan())
        msgs = await _drive_stream_response(kc, _creds(), "write")
        system = next(m for m in msgs if m["role"] == "system")
        assert PLAN_MODE_NUDGE not in system["content"]
        assert "propose → refine → validate → compile" not in system["content"]


class TestAskNudgeBothAssemblyPaths:
    """Ask mode had no nudge at all — the model only learned it was read-only
    reactively, from a rejected tool-call error, instead of upfront the way
    plan mode explains itself. Mirrors TestPlanNudgeBothAssemblyPaths."""

    @pytest.mark.asyncio
    async def test_plain_string_path_carries_ask_nudge(self):
        kc = _patched_knowledge(tool_defs=_catalog_with_plan())
        msgs = await _drive_stream_response(kc, _creds(), "ask")
        system = next(m for m in msgs if m["role"] == "system")
        assert isinstance(system["content"], str)
        assert ASK_MODE_NUDGE in system["content"]
        assert PLAN_MODE_NUDGE not in system["content"]

    @pytest.mark.asyncio
    async def test_anthropic_parts_path_carries_ask_nudge(self):
        kc = _patched_knowledge(
            stable='<memory mode="static"><project/></memory>',
            tool_defs=_catalog_with_plan(),
        )
        msgs = await _drive_stream_response(kc, _make_creds(), "ask")
        system = next(m for m in msgs if m["role"] == "system")
        assert isinstance(system["content"], list)
        texts = [p["text"] for p in system["content"]]
        assert ASK_MODE_NUDGE in texts

    @pytest.mark.asyncio
    async def test_write_mode_has_no_ask_nudge(self):
        kc = _patched_knowledge(tool_defs=_catalog_with_plan())
        msgs = await _drive_stream_response(kc, _creds(), "write")
        system = next(m for m in msgs if m["role"] == "system")
        assert ASK_MODE_NUDGE not in system["content"]


# ════════════════════════════════════════════════════════════════════════════
# suspended-run round-trip — 'plan' persists and the resume stays in plan mode
# ════════════════════════════════════════════════════════════════════════════


def _plan_suspended() -> SuspendedRun:
    return SuspendedRun(
        run_id="run-plan",
        session_id=str(TEST_SESSION_ID),
        owner_user_id=str(TEST_USER_ID),
        message_id=str(uuid4()),
        working=[
            {"role": "user", "content": "plan it"},
            {"role": "assistant", "content": "",
             "tool_calls": [{"id": "c1", "type": "function",
                             "function": {"name": "confirm_action", "arguments": "{}"}}]},
        ],
        pending_tool_call={"id": "c1", "name": "confirm_action", "args": {}},
        input_tokens=10,
        output_tokens=4,
        model_source="user_model",
        model_ref=str(TEST_MODEL_REF),
        parent_message_id=None,
        user_message_content="plan it",
        permission_mode="plan",
    )


class TestPlanSuspendResumeRoundTrip:
    @pytest.mark.asyncio
    async def test_frontend_suspend_saves_plan_mode(self):
        """A plan-mode turn that suspends on a frontend tool persists
        permission_mode='plan' (the VARCHAR(8) column carries it fine)."""
        pool, conn = _make_pool_with_conn()
        pool.fetch.return_value = []
        conn.fetchval.return_value = 1
        kc = _patched_knowledge(tool_defs=[])  # gateway-down agui editor surface

        scripts = [[
            tool_frag(index=0, id="c1", name="propose_edit"),
            tool_frag(index=0, arguments_delta='{"operation":"insert_at_cursor","text":"x"}'),
            done("tool_calls"),
        ]]
        save_mock = AsyncMock()
        with _patch_client(scripts), \
             patch("app.services.stream_service.get_knowledge_client", return_value=kc), \
             patch("app.services.stream_service.save_suspended_run", save_mock), \
             patch("app.client.book_steering_client.get_book_steering_client",
                   return_value=_steering_mock()):
            async for _ in stream_response(
                session_id=TEST_SESSION_ID,
                user_message_content="plan then propose",
                user_id=TEST_USER_ID,
                model_source="user_model",
                model_ref=TEST_MODEL_REF,
                creds=_make_creds(),
                pool=pool,
                billing=AsyncMock(),
                stream_format="agui",
                editor_context={"book_id": "b1", "chapter_id": "ch1"},
                permission_mode="plan",
            ):
                pass

        save_mock.assert_awaited_once()
        assert save_mock.await_args.kwargs["permission_mode"] == "plan"

    @pytest.mark.asyncio
    async def test_resume_continues_under_plan_rules(self):
        """A resumed plan-mode run still rejects a tiered non-plan tool —
        proving the loaded row's mode governs the 2nd pass (not 'write')."""
        pool, conn = _make_pool_with_conn()
        conn.fetchval.return_value = 1
        pool.fetchrow.return_value = {"generation_params": {}, "project_id": None}
        kc = AsyncMock()
        kc.get_tool_definitions.return_value = _catalog_with_plan()
        kc.get_catalog_meta = MagicMock(return_value={})

        scripts = [
            [
                tool_frag(index=0, id="c2", name="book_create"),
                tool_frag(index=0, arguments_delta='{"title":"X"}'),
                done("tool_calls"),
            ],
            [tok("ok, plan only"), done("stop")],
        ]
        with _patch_client(scripts), \
             patch("app.services.stream_service.get_knowledge_client", return_value=kc), \
             patch("app.services.stream_service.load_suspended_run",
                   AsyncMock(return_value=_plan_suspended())), \
             patch("app.services.stream_service.delete_suspended_run", AsyncMock()):
            async for _ in resume_stream_response(
                session_id=str(TEST_SESSION_ID), user_id=str(TEST_USER_ID),
                run_id="run-plan", tool_call_id="c1", outcome="confirmed",
                applied_text=None, creds=_creds(), pool=pool, billing=AsyncMock(),
                stream_format="agui",
            ):
                pass

        # the tiered non-plan tool never executed on the resume pass
        kc.mcp_execute_tool.assert_not_awaited()
        msgs = _FakeClient.instances[0].requests[1].messages
        tool_msg = next(m for m in msgs if m.get("role") == "tool"
                        and m.get("tool_call_id") == "c2")
        assert "plan mode" in json.loads(tool_msg["content"])["error"]


# ════════════════════════════════════════════════════════════════════════════
# router — permission_mode='plan' accepted end-to-end
# ════════════════════════════════════════════════════════════════════════════


class TestRouterAcceptsPlan:
    @pytest.mark.asyncio
    @patch("app.routers.messages.get_provider_client")
    @patch("app.routers.messages.get_billing_client")
    @patch("app.routers.messages.stream_response")
    async def test_body_plan_mode_reaches_stream_response(
        self, mock_stream, mock_billing, mock_provider, client, mock_pool
    ):
        from app.models import ProviderCredentials
        mock_provider.return_value.resolve = AsyncMock(return_value=ProviderCredentials(
            provider_kind="openai", provider_model_name="gpt-4",
            base_url="https://api.openai.com", api_key="sk-test", context_length=8192,
        ))
        conn = mock_pool._conn
        mock_pool.fetchrow.return_value = make_session_record()
        conn.fetchval.return_value = 1

        async def fake_stream(**kwargs):
            yield "data: [DONE]\n\n"

        mock_stream.return_value = fake_stream()
        resp = await client.post(
            f"/v1/chat/sessions/{TEST_SESSION_ID}/messages",
            json={"content": "Plan the arc", "permission_mode": "plan"},
        )
        assert resp.status_code == 200
        assert mock_stream.call_args.kwargs["permission_mode"] == "plan"

    @pytest.mark.asyncio
    async def test_junk_permission_mode_still_422(self, client, mock_pool):
        """The Literal widened to include 'plan' — junk still rejects."""
        resp = await client.post(
            f"/v1/chat/sessions/{TEST_SESSION_ID}/messages",
            json={"content": "Hello", "permission_mode": "draft"},
        )
        assert resp.status_code == 422
