"""T4 (Context Budget Law D4) — stream_service wiring for the story_state block.

Proves, by EFFECT on the captured system message, that when `story_state_block_enabled`
is ON and the orchestrator returns a projected block, that block lands in the system
prompt for the turn — and that with the flag OFF (the default) the orchestrator is never
even called (zero prod behavior change). The orchestrator's own decision logic is unit-
tested in test_story_state_projection.py; here we only prove the WIRING.

Mirrors the steering harness: knowledge client + gateway patched, messages captured.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.config import settings
from app.services.stream_service import stream_response
from tests.conftest import TEST_MODEL_REF, TEST_SESSION_ID, TEST_USER_ID
from tests.test_stream_service import (
    _make_chunk,
    _make_creds,
    _make_pool_with_conn,
    _patched_knowledge,
)

BLOCK = "<story_state>\nentities: Lâm Uyển, Đại Việt\n</story_state>"


async def _run_turn(*, enabled: bool, projected: str, monkeypatch) -> tuple[list[dict], AsyncMock]:
    """Drive one turn with the story_state flag set and the orchestrator patched to
    return `projected`; return (captured messages, the project_story_state mock)."""
    monkeypatch.setattr(settings, "story_state_block_enabled", enabled, raising=False)
    pool, conn = _make_pool_with_conn()
    # A real turn always carries a session system prompt → a system message always exists,
    # so the negative cases assert "block ABSENT from a real system message" (not the
    # empty-everything edge where build_system_message returns None and inserts nothing).
    pool.fetchrow.return_value = {"system_prompt": "You are a helper.", "generation_params": {}}
    pool.fetch.return_value = []
    conn.fetchval.return_value = 1
    pool.fetchval.return_value = 7  # the turn-counter query (MAX(sequence_num))

    captured: list[dict] = []

    async def fake_acompletion(**kwargs):
        captured.extend(kwargs.get("messages", []))
        yield _make_chunk("ok")
        yield _make_chunk(None)

    orch = AsyncMock(return_value=projected)
    # degraded grounding (empty stable + empty context) — the realistic case where the
    # safety net fires; the orchestrator is patched so the result is deterministic.
    with patch(
        "app.services.stream_service.get_knowledge_client",
        return_value=_patched_knowledge(stable="", volatile="", context=""),
    ), patch(
        "app.services.stream_service._stream_via_gateway",
        side_effect=lambda **kw: fake_acompletion(**kw),
    ), patch(
        "app.services.stream_service.project_story_state", orch,
    ):
        async for _ in stream_response(
            session_id=TEST_SESSION_ID,
            user_message_content="make it darker",
            user_id=TEST_USER_ID,
            model_source="user_model",
            model_ref=TEST_MODEL_REF,
            creds=_make_creds(provider_kind="openai"),
            pool=pool,
            billing=AsyncMock(),
            # D-LONG-WORK auto-detect — force tiers ALLOWED so this test exercises the
            # story_state wiring itself (flag on/off), not the pressure decision (which
            # has its own truth-table coverage in test_context_autodetect).
            context_mode="on",
        ):
            pass
    return captured, orch


def _system_text(messages: list[dict]) -> str:
    system = next((m for m in messages if m["role"] == "system"), None)
    assert system is not None, "no system message captured"
    content = system["content"]
    return content if isinstance(content, str) else "\n\n".join(p["text"] for p in content)


class TestStoryStateWiring:
    @pytest.mark.asyncio
    async def test_flag_on_projects_block_into_system_prompt(self, monkeypatch):
        msgs, orch = await _run_turn(enabled=True, projected=BLOCK, monkeypatch=monkeypatch)
        orch.assert_awaited_once()
        # orchestrator is fed the kctx grounding split for the maintain/decide step
        kw = orch.await_args.kwargs
        assert kw["stable_context"] == "" and kw["full_context"] == ""
        assert kw["owner_user_id"] == TEST_USER_ID
        assert kw["current_turn"] == 7  # from the MAX(sequence_num) query
        # EFFECT: the projected block is in the system message
        assert "<story_state>" in _system_text(msgs)
        assert "Lâm Uyển" in _system_text(msgs)

    @pytest.mark.asyncio
    async def test_flag_off_never_calls_orchestrator_and_no_block(self, monkeypatch):
        msgs, orch = await _run_turn(enabled=False, projected=BLOCK, monkeypatch=monkeypatch)
        orch.assert_not_awaited()
        text = _system_text(msgs)
        assert "You are a helper." in text  # the turn assembled a real system message
        assert "<story_state>" not in text

    @pytest.mark.asyncio
    async def test_empty_projection_adds_no_block(self, monkeypatch):
        """When the orchestrator returns '' (live grounding present / no cache), the tail
        block list skips it — no empty <story_state> wrapper leaks into the prompt."""
        msgs, orch = await _run_turn(enabled=True, projected="", monkeypatch=monkeypatch)
        orch.assert_awaited_once()
        text = _system_text(msgs)
        assert "You are a helper." in text  # the turn assembled a real system message
        assert "<story_state>" not in text
