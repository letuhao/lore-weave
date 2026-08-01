"""D-PASS-TEXT-REECHO — a continuation pass must not re-render the turn's prior text.

Measured live (Mị Đế author-dogfood, 2026-07-26): gemma re-emits its FULL prior reply
verbatim at the start of every continuation pass after a tool round, and the stream
concatenates passes — so a 2-round turn persisted 943→1884 chars (exactly doubled) and
a 4-round turn rendered the same paragraphs 4×. The echo-guard holds a continuation
pass's opening tokens while they verbatim-prefix the turn's already-streamed text:
a full match is swallowed, a divergence is flushed byte-for-byte unchanged.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

from tests.test_spend_gate import _kc

TEST_MODEL_REF = "00000000-0000-0000-0000-0000000000aa"

_PASS1_TEXT = (
    "Đã xong! Mình đã tạo bản thảo cho nhân vật chính của bạn. "
    "Bạn hãy kiểm tra lại trong hộp thư phê duyệt nhé."
)
_NEW_TEXT = " Tiếp theo mình sẽ tạo Lâm gia."


def _tool(name: str = "book_get_chapter") -> dict:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": "read a chapter",
            "parameters": {"type": "object", "properties": {"chapter_id": {"type": "string"}}},
            "_meta": {"tier": "R"},
        },
    }


def _client_echoing(pass2_text: str, chunk: int = 7):
    """Pass 1: text + a tool call. Pass 2: `pass2_text` (streamed in small deltas), done."""
    from loreweave_llm import DoneEvent, TokenEvent, ToolCallEvent

    passes = {"n": 0}

    class FakeClient:
        def __init__(self, **kw): pass
        async def aclose(self): pass

        def stream(self, request):
            i = passes["n"]; passes["n"] += 1

            async def gen():
                if i == 0:
                    for j in range(0, len(_PASS1_TEXT), chunk):
                        yield TokenEvent(delta=_PASS1_TEXT[j:j + chunk])
                    yield ToolCallEvent(index=0, id="c0", name="book_get_chapter",
                                        arguments_delta='{"chapter_id": "c1"}')
                    yield DoneEvent(finish_reason="tool_calls")
                else:
                    for j in range(0, len(pass2_text), chunk):
                        yield TokenEvent(delta=pass2_text[j:j + chunk])
                    yield DoneEvent(finish_reason="stop")

            return gen()

    return FakeClient


async def _drive(pass2_text: str):
    import app.services.stream_service as ss

    kc = _kc()
    kc.mcp_execute_tool.return_value = {"success": True, "result": {"title": "ch"}}
    chunks = []
    with patch.object(ss, "Client", _client_echoing(pass2_text)):
        async for ch in ss._stream_with_tools(
            model_source="user_model", model_ref=TEST_MODEL_REF, user_id="u",
            messages=[{"role": "user", "content": "tạo nhân vật"}],
            gen_params={"max_tokens": 100}, tools=[_tool()],
            knowledge_client=kc, session_id="s", project_id=None,
            permission_mode="write",
        ):
            chunks.append(ch)
    return "".join(c.get("content") or "" for c in chunks)


class TestPassTextReecho:
    @pytest.mark.asyncio
    async def test_full_verbatim_reecho_is_swallowed(self):
        """THE live case: pass 2 = full copy of pass 1's text + genuinely new text.
        The copy is dropped; the new text streams."""
        text = await _drive(_PASS1_TEXT + _NEW_TEXT)
        assert text.count("Đã xong!") == 1, "the re-echoed copy must not render twice"
        assert _NEW_TEXT.strip() in text

    @pytest.mark.asyncio
    async def test_divergent_continuation_is_untouched(self):
        """A continuation that does NOT re-echo streams byte-for-byte (no held loss),
        even when it happens to share the first few characters."""
        cont = "Đã tạo thêm Lâm gia cho bạn."  # shares "Đã " then diverges
        text = await _drive(cont)
        assert _PASS1_TEXT in text
        assert cont in text

    @pytest.mark.asyncio
    async def test_reecho_with_leading_whitespace_is_still_swallowed(self):
        """THE live miss of the first cut: gemma opens the re-echo with a blank line
        ("\\n\\n" + copy). An exact-prefix match diverges on the first char and flushes
        the whole copy — the guard must match through the whitespace seam."""
        text = await _drive("\n\n" + _PASS1_TEXT + _NEW_TEXT)
        assert text.count("Đã xong!") == 1, "a whitespace-prefixed re-echo must not render twice"
        assert _NEW_TEXT.strip() in text

    @pytest.mark.asyncio
    async def test_partial_echo_fragment_is_dropped_not_leaked(self):
        """A pass that emits ONLY part of the echo then stops adds nothing new —
        the fragment (a strict prefix of what is already on screen) is dropped."""
        text = await _drive(_PASS1_TEXT[:40])
        assert text.count("Đã xong!") == 1
