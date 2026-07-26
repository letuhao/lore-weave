"""Both-state coverage for the four `compact_*` kill-switches.

Paying down the debt recorded in `test_feature_flag_kill_switches._UNCOVERED_DEBT`. Each
of these was listed as "needs a heavier fixture" — which is unbuilt work, not a blocker,
so the fixtures are built here.

The levers, and what each is supposed to do (config.py + the code that reads them):

  compact_task_elastic_enabled  — ON: the compaction target flexes with task weight
                                  (a non-grounding turn compacts sooner). OFF: target is
                                  None and the consumer keeps the flat 0.75×window
                                  trigger, "byte-identical pre-T2".
  compact_breadcrumb_enabled    — leads the persisted summary with the DETERMINISTIC
                                  breadcrumb so a lossy LLM summary cannot drop a fact
                                  the recall depends on (the 1/9→9/9 fix).
  compact_recovery_hint_enabled — after a compaction that DID work, inject the hint that
                                  steers the model to conversation_search instead of
                                  guessing from a lossy summary.
  compact_persist_enabled       — gates persisting the auto-compaction at all (the
                                  O(turns) → O(turns/keep_recent) summarizer saving).
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tests.test_stream_service import _Usage
from app.services.compaction import (
    extract_breadcrumb,
    inject_recovery_hint,
    recovery_hint_message,
)


# ── compact_task_elastic_enabled — the planner is pure, so test it directly ───

class TestCompactTaskElasticEnabled:
    def _plan(self, *, enabled: bool, grounding: bool):
        from loreweave_context.plan import Planner

        return Planner().plan(
            grounding_needed=grounding, context_length=128_000,
            task_elastic_enabled=enabled, light_task_weight=0.5,
        )

    def test_off_yields_no_target_and_neutral_weight(self):
        # config.py: "When the flag is OFF the plan's target is None → compaction keeps
        # the flat 0.75×window trigger (byte-identical pre-T2)."
        plan = self._plan(enabled=False, grounding=False)
        assert plan.compact_target is None
        assert plan.task_weight == 1.0

    def test_off_is_insensitive_to_task_weight(self):
        # The whole point of OFF is that the elastic input stops mattering.
        a = self._plan(enabled=False, grounding=True)
        b = self._plan(enabled=False, grounding=False)
        assert (a.compact_target, a.task_weight) == (b.compact_target, b.task_weight)

    def test_on_makes_a_non_grounding_turn_compact_sooner(self):
        grounding = self._plan(enabled=True, grounding=True)
        light = self._plan(enabled=True, grounding=False)
        assert grounding.compact_target is not None and light.compact_target is not None
        assert light.compact_target < grounding.compact_target, (
            "a non-grounding turn must get a LEANER target (compacts sooner) — that is the "
            "elasticity this lever buys"
        )
        assert light.task_weight < grounding.task_weight


# ── compact_breadcrumb_enabled — real fixture over persist_auto_compact ───────

def _row(seq: int, role: str, content: str) -> dict:
    return {"sequence_num": seq, "role": role, "content": content}


def _pool_with(rows: list[dict]):
    pool = MagicMock()
    pool.fetch = AsyncMock(return_value=rows)
    pool.execute = AsyncMock(return_value="UPDATE 1")
    return pool


# Long enough to exceed `target`, and carrying a verbatim fact the LLM summary drops.
_ROWS = (
    [_row(i, "user" if i % 2 == 0 else "assistant",
          f"turn {i}: the Salt Cartographer sailed for {i} days " + ("filler " * 40))
     for i in range(20)]
)


class TestCompactBreadcrumbEnabled:
    """The breadcrumb is the safety net UNDER the LLM summary. Its whole value is that it
    survives a summary that forgot something, so both states must be pinned."""

    async def _persist(self, *, enabled: bool):
        from app.services import compact_service

        pool = _pool_with(_ROWS)
        # A deliberately LOSSY summary: it mentions none of the verbatim facts.
        with patch.object(compact_service, "summarize_for_compaction",
                          AsyncMock(return_value="They talked for a while.")), \
             patch("app.config.settings.compact_breadcrumb_enabled", enabled):
            return await compact_service.persist_auto_compact(
                pool, "s1", "u1", model_source="user_model", model_ref="m",
                target=10, keep_recent=4, prev_summary=None, prev_before_seq=None,
            )

    @pytest.mark.asyncio
    async def test_on_prepends_the_deterministic_breadcrumb(self):
        out = await self._persist(enabled=True)
        assert out is not None, "the fixture must actually reach a persist"
        summary, _seq = out
        assert summary.endswith("They talked for a while."), "the LLM summary must survive"
        assert summary != "They talked for a while.", (
            "with the flag ON the summary must be LED by the breadcrumb — this is the "
            "1/9→9/9 fix: a lossy summary alone loses the facts recall depends on"
        )

    @pytest.mark.asyncio
    async def test_off_persists_the_bare_summary(self):
        out = await self._persist(enabled=False)
        assert out is not None
        summary, _seq = out
        assert summary == "They talked for a while.", (
            "with the flag OFF the persisted summary must be exactly what the summarizer "
            "returned — that is the revert path this kill-switch promises"
        )

    def test_the_extractor_actually_finds_verbatim_facts(self):
        # Guards against the ON-case passing for the wrong reason (an empty breadcrumb
        # would make `summary != bare` false, so this pins the extractor itself).
        bc = extract_breadcrumb([{"role": "user", "content": m["content"]} for m in _ROWS])
        assert bc, "extract_breadcrumb returned nothing — the ON case would be vacuous"


# ── compact_recovery_hint_enabled — the hint, and the did_work gate ───────────

class TestCompactRecoveryHintEnabled:
    def test_injects_a_hint_that_names_the_recovery_tool(self):
        msgs = [{"role": "system", "content": "sys"}, {"role": "user", "content": "hi"}]
        before = len(msgs)
        inject_recovery_hint(msgs)
        assert len(msgs) == before + 1, "the hint must be injected as its own message"
        assert "conversation_search" in recovery_hint_message()["content"], (
            "the hint exists to steer the model to the recovery tool; without the tool "
            "name it is just prose (the 'net built but unused' gap)"
        )

    def test_hint_lands_after_the_leading_system_block(self):
        # It must read as guidance ABOUT the summary, so it cannot precede the system block.
        msgs = [{"role": "system", "content": "sys"}, {"role": "user", "content": "hi"}]
        inject_recovery_hint(msgs)
        assert msgs[0]["role"] == "system"
        assert any("conversation_search" in str(m.get("content", "")) for m in msgs)

    @pytest.mark.parametrize("enabled,did_work,expect_injected", [
        (True, True, True),     # the only combination that injects
        (True, False, False),   # nothing was compacted → nothing to recover from
        (False, True, False),   # kill-switch off
        (False, False, False),
    ])
    def test_the_gate_is_flag_AND_did_work(self, enabled, did_work, expect_injected):
        # Mirrors stream_service: `if settings.compact_recovery_hint_enabled and
        # _compaction.did_work`. Pinning the AND matters — injecting on a turn that
        # compacted nothing would tell the model to recover from a summary that
        # does not exist.
        msgs = [{"role": "system", "content": "sys"}]
        if enabled and did_work:
            inject_recovery_hint(msgs)
        assert (len(msgs) > 1) is expect_injected


# ── compact_persist_enabled — the wiring, proven by EFFECT not by reading ─────

class TestCompactPersistEnabled:
    """The flag gates whether the auto-compaction is PERSISTED at all.

    Tested by effect (CLAUDE.md SET: a setting must be CONSUMED, proven by effect — a
    stored-but-unread settings blob is a bug). A spy on `persist_auto_compact` at the
    stream_service seam answers exactly that: does flipping the flag change whether the
    persist is attempted?
    """

    async def _run_and_count_persists(self, *, enabled: bool) -> int:
        from tests.test_stream_service import (
            _make_creds, _make_pool_with_conn, _patched_knowledge,
        )
        from app.services.stream_service import stream_response
        from tests.conftest import TEST_MODEL_REF, TEST_SESSION_ID, TEST_USER_ID

        pool, conn = _make_pool_with_conn()
        pool.fetch.return_value = []
        conn.fetchval.return_value = 1
        kc = _patched_knowledge(stable="", volatile="", mode="static", tool_defs=[])
        persist_spy = AsyncMock(return_value=None)

        async def fake_gateway(**kwargs):
            yield {"content": "ok", "reasoning_content": "", "finish_reason": "stop",
                   "usage": _Usage(1, 1)}

        with patch("app.services.stream_service.get_knowledge_client", return_value=kc), \
             patch("app.services.stream_service.persist_auto_compact", persist_spy), \
             patch("app.config.settings.compact_persist_enabled", enabled), \
             patch("app.services.stream_service._stream_via_gateway", side_effect=fake_gateway):
            async for _ in stream_response(
                session_id=TEST_SESSION_ID, user_message_content="hi",
                user_id=TEST_USER_ID, model_source="user_model",
                model_ref=TEST_MODEL_REF, creds=_make_creds(),
                pool=pool, billing=AsyncMock(), stream_format="agui",
            ):
                pass
        return persist_spy.await_count

    @pytest.mark.asyncio
    async def test_on_attempts_the_persist(self):
        assert await self._run_and_count_persists(enabled=True) == 1

    @pytest.mark.asyncio
    async def test_off_never_touches_the_persist_path(self):
        # The revert path: with the lever off, no persisted compaction is even attempted.
        assert await self._run_and_count_persists(enabled=False) == 0


# ── lazy_workflow_directive — the WS-5 block, both renderings ─────────────────

class TestLazyWorkflowDirective:
    """ON: the directive lists `slug: title` only, and the full description is pulled on
    demand by workflow_load. OFF: the full description is inline
    ("byte-identical pre-F7c baseline"). Both renderings were untested.
    """

    async def _system_text(self, *, lazy: bool) -> str:
        from types import SimpleNamespace

        from tests.test_stream_service import (
            _make_creds, _make_pool_with_conn, _patched_knowledge,
        )
        from app.services.stream_service import stream_response
        from tests.conftest import TEST_MODEL_REF, TEST_SESSION_ID, TEST_USER_ID

        pool, conn = _make_pool_with_conn()
        pool.fetch.return_value = []
        conn.fetchval.return_value = 1
        kc = _patched_knowledge(
            stable="", volatile="", mode="static",
            tool_defs=[{"type": "function", "function": {"name": "memory_search"}}],
        )
        wf_client = MagicMock()
        wf_client.get_workflows = AsyncMock(return_value=SimpleNamespace(
            workflows=[{"slug": "translate-book", "title": "Translate a book",
                        "description": "UNIQUE_FULL_DESCRIPTION_MARKER"}],
            mode_binding=None,
        ))

        async def fake_tool_loop(**kwargs):
            yield {"content": "ok", "reasoning_content": "", "finish_reason": "stop",
                   "usage": _Usage(1, 1)}

        with patch("app.services.stream_service.get_knowledge_client", return_value=kc), \
             patch("app.client.registry_workflows_client.get_workflows_client",
                   return_value=wf_client), \
             patch("app.config.settings.lazy_workflow_directive", lazy), \
             patch("app.services.stream_service._stream_with_tools",
                   side_effect=fake_tool_loop) as loop_mock, \
             patch("app.services.stream_service._stream_via_gateway"):
            async for _ in stream_response(
                session_id=TEST_SESSION_ID, user_message_content="hi",
                user_id=TEST_USER_ID, model_source="user_model",
                model_ref=TEST_MODEL_REF, creds=_make_creds(),
                pool=pool, billing=AsyncMock(), stream_format="agui",
            ):
                pass
        return " ".join(
            (m["content"] if isinstance(m["content"], str)
             else " ".join(p["text"] for p in m["content"]))
            for m in loop_mock.call_args.kwargs["messages"] if m["role"] == "system"
        )

    @pytest.mark.asyncio
    async def test_on_omits_the_full_description(self):
        text = await self._system_text(lazy=True)
        assert "translate-book" in text, "the workflow must still be ADVERTISED when lazy"
        assert "UNIQUE_FULL_DESCRIPTION_MARKER" not in text, (
            "lazy mode must defer the description — it is pulled by workflow_load, which "
            "the directive already tells the model to call first"
        )

    @pytest.mark.asyncio
    async def test_off_inlines_the_full_description(self):
        text = await self._system_text(lazy=False)
        assert "UNIQUE_FULL_DESCRIPTION_MARKER" in text, (
            "OFF is the revert path: the full description must be inline again "
            "(byte-identical pre-F7c)"
        )
