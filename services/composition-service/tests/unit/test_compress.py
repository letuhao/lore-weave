"""S2 — compress primitive tests (degrade-safe; spoiler-safe by construction)."""

from __future__ import annotations

from types import SimpleNamespace

from app.engine import compress as C


def test_cap_recent_prose_keeps_most_recent_within_budget():
    # D-COMP-COMPRESS-INPUT-CAP: keep the newest paragraphs whose total ≤ cap.
    prose = ["A" * 100, "B" * 100, "C" * 100, "D" * 100]  # 400 chars
    assert C.cap_recent_prose(prose, 1000) == prose          # under budget → unchanged
    assert C.cap_recent_prose(prose, 250) == ["C" * 100, "D" * 100]  # newest two fit
    # always keeps ≥1 even if the newest alone exceeds the cap
    assert C.cap_recent_prose(["X" * 500], 100) == ["X" * 500]


async def test_compress_caps_input_to_recent():
    # the older prose is bounded before the LLM call (newest kept).
    llm = FakeLLM(content="summary")
    await C.compress(llm, user_id="u", model_source="user_model", model_ref="m",
                     prose=["old" * 100, "mid" * 100, "new" * 100], timeline=[],
                     max_input_chars=350)
    user_msg = llm.last_input["messages"][1]["content"]
    assert "new" in user_msg and "old" not in user_msg  # oldest elided


class FakeLLM:
    def __init__(self, content=None, status="completed", raises=False):
        self._content, self._status, self._raises = content, status, raises
        self.calls = 0
        self.last_input = None

    async def submit_and_wait(self, **kw):
        from loreweave_llm.errors import LLMError
        self.calls += 1
        self.last_input = kw["input"]
        if self._raises:
            raise LLMError("gateway down")
        res = {"messages": [{"content": self._content}]} if self._content is not None else {}
        return SimpleNamespace(status=self._status, result=res)


async def test_compress_returns_summary():
    llm = FakeLLM(content="Kael reached the keep; Bryn distrusts him.")
    out = await C.compress(llm, user_id="u", model_source="user_model", model_ref="m",
                           prose=["para one", "para two"], timeline=["Kael arrives"], plan="retake the keep")
    assert out == "Kael reached the keep; Bryn distrusts him."
    # all three inputs reached the prompt (prose + timeline + plan)
    user = llm.last_input["messages"][1]["content"]
    assert "para one" in user and "Kael arrives" in user and "retake the keep" in user


async def test_compress_llm_error_returns_empty_not_raise():
    llm = FakeLLM(raises=True)
    out = await C.compress(llm, user_id="u", model_source="user_model", model_ref="m",
                           prose=["x"], timeline=[], plan="")
    assert out == ""  # degrade → caller keeps raw prose


async def test_compress_non_completed_returns_empty():
    llm = FakeLLM(content="ignored", status="failed")
    out = await C.compress(llm, user_id="u", model_source="user_model", model_ref="m",
                           prose=["x"], timeline=[], plan="")
    assert out == ""


async def test_compress_empty_inputs_is_noop_no_llm_call():
    llm = FakeLLM(content="should not run")
    out = await C.compress(llm, user_id="u", model_source="user_model", model_ref="m",
                           prose=[], timeline=[], plan="")
    assert out == "" and llm.calls == 0  # nothing to compress → no LLM call
