"""B3 stitch tests — input cap (head+tail) + stitch_chapter degrade/success."""

from __future__ import annotations

from loreweave_llm.errors import LLMError

from app.engine.stitch import cap_scene_drafts, stitch_chapter
from app.packer.profile import NEUTRAL


# ── cap_scene_drafts (pure) ──

def test_cap_no_cap_when_under_budget():
    drafts = ["a" * 10, "b" * 10, "c" * 10]
    assert cap_scene_drafts(drafts, 100) == (drafts, 0)


def test_cap_two_or_fewer_never_capped():
    drafts = ["X" * 1000, "Y" * 1000]
    assert cap_scene_drafts(drafts, 10) == (drafts, 0)


def test_cap_keeps_head_and_tail_elides_middle():
    drafts = ["A" * 30, "B" * 30, "C" * 30, "D" * 30]  # 120 > 65; budget after ends = 5
    kept, elided = cap_scene_drafts(drafts, 65)
    assert kept == ["A" * 30, "D" * 30] and elided == 2


def test_cap_keeps_ends_even_when_over_budget():
    drafts = ["A" * 100, "B" * 100, "C" * 100]  # ends alone (200) exceed 50
    kept, elided = cap_scene_drafts(drafts, 50)
    assert kept == ["A" * 100, "C" * 100] and elided == 1


# ── stitch_chapter (async; asyncio_mode=auto) ──

class _Job:
    def __init__(self, status, result):
        self.status = status
        self.result = result


class _LLM:
    def __init__(self, *, status="completed", content="STITCHED", raises=None, finish_reason=None):
        self._status, self._content, self._raises = status, content, raises
        self._finish_reason = finish_reason
        self.calls = []

    async def submit_and_wait(self, **kw):
        self.calls.append(kw)
        if self._raises:
            raise self._raises
        result = {"messages": [{"content": self._content}]}
        if self._finish_reason is not None:
            result["finish_reason"] = self._finish_reason
        return _Job(self._status, result)


async def _stitch(llm, drafts, **over):
    kw = dict(user_id="u", model_source="user_model", model_ref="m",
              scene_drafts=drafts, chapter_intent="intent", profile=NEUTRAL,
              max_tokens=2048, max_input_chars=10000)
    kw.update(over)
    return await stitch_chapter(llm, **kw)


# stitch_chapter returns (text, finish_reason) — D-COMP-TRUNCATION-SURFACING.

async def test_stitch_empty_input_returns_empty_no_llm_call():
    llm = _LLM()
    assert await _stitch(llm, []) == ("", None)
    assert await _stitch(llm, ["   ", ""]) == ("", None)  # whitespace-only filtered
    assert llm.calls == []


async def test_stitch_success_returns_content_and_finish_reason():
    llm = _LLM(content="MERGED CHAPTER", finish_reason="stop")
    assert await _stitch(llm, ["a", "b"]) == ("MERGED CHAPTER", "stop")
    assert llm.calls and llm.calls[0]["operation"] == "chat"


async def test_stitch_surfaces_length_finish_reason():
    # the truncation signal the engine maps to truncated=True
    llm = _LLM(content="LONG MERGED", finish_reason="length")
    assert await _stitch(llm, ["a", "b"]) == ("LONG MERGED", "length")


async def test_stitch_llm_error_degrades_to_empty():
    llm = _LLM(raises=LLMError("boom"))
    assert await _stitch(llm, ["a", "b"]) == ("", None)


async def test_stitch_non_completed_degrades_to_empty():
    llm = _LLM(status="failed")
    assert await _stitch(llm, ["a", "b"]) == ("", None)


async def test_stitch_empty_output_degrades_to_empty():
    llm = _LLM(content="   ")
    assert await _stitch(llm, ["a", "b"]) == ("", None)
