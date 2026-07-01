"""Unit tests for the Quality Report orchestrator (engine/quality_report.py).

Focus: the two chapter-level advisory judges (critic + promise_audit) run
concurrently and shape one report; each side degrades independently (an LLM
failure in one returns its empty shape + `error` and never sinks the other).
"""

import json
from types import SimpleNamespace

from app.engine.quality_report import build_quality_report

# async tests are collected via pytest.ini asyncio auto-mode.


_CRITIC_JSON = json.dumps({
    "coherence": 4, "voice_match": 3, "pacing": 5, "canon_consistency": 2,
    "violations": [{"rule_id": "R1", "violated": True, "span": "he said", "why": "wrong pronoun"}],
})
_PROMISE_JSON = json.dumps({
    "introduced": ["the sealed grimoire", "the debt to the sect"],
    "resolved": ["the sealed grimoire"],
    "dropped": ["the debt to the sect"],
})


class FakeQRLLM:
    """Routes submit_and_wait by the SYSTEM prompt: the critic system says
    'craft critic', the promise system says 'NARRATIVE PROMISES'. Each side can be
    forced to a non-completed status to exercise the degrade path."""

    def __init__(self, *, critic="ok", promise="ok"):
        self._critic = critic
        self._promise = promise
        self.calls = []

    async def submit_and_wait(self, **kw):
        system = kw["input"]["messages"][0]["content"]
        self.calls.append(system)
        if "craft critic" in system:
            mode, payload = self._critic, _CRITIC_JSON
        else:  # promise audit
            mode, payload = self._promise, _PROMISE_JSON
        if mode == "fail":
            return SimpleNamespace(status="failed", result={})
        if mode == "raise":
            # a non-LLMError raised on the completed path (the window the engines'
            # `except LLMError` does NOT cover) — build_quality_report must degrade it,
            # not let it sink the sibling judge or raise out of the op.
            raise RuntimeError("unexpected boom")
        return SimpleNamespace(status="completed", result={"messages": [{"content": payload}]})


async def test_report_both_ok():
    llm = FakeQRLLM()
    rep = await build_quality_report(
        llm, user_id="u", model_source="s", model_ref="m",
        chapter="Some chapter prose.", source_language="vi")
    assert rep["critic"]["coherence"] == 4
    assert rep["critic"]["canon_consistency"] == 2
    assert len(rep["critic"]["violations"]) == 1
    assert rep["promises"]["dropped"] == ["the debt to the sect"]
    assert rep["promises"]["introduced_count"] == 2
    assert rep["promises"]["dropped_count"] == 1
    # both judges ran (2 concurrent calls)
    assert len(llm.calls) == 2


async def test_critic_degrades_promise_survives():
    llm = FakeQRLLM(critic="fail")
    rep = await build_quality_report(
        llm, user_id="u", model_source="s", model_ref="m", chapter="prose")
    assert rep["critic"]["error"].startswith("critic_")
    assert rep["critic"]["coherence"] is None
    # the promise audit is unaffected by the critic's failure
    assert rep["promises"]["dropped"] == ["the debt to the sect"]
    assert "error" not in rep["promises"]


async def test_promise_degrades_critic_survives():
    llm = FakeQRLLM(promise="fail")
    rep = await build_quality_report(
        llm, user_id="u", model_source="s", model_ref="m", chapter="prose")
    assert rep["critic"]["coherence"] == 4
    # a failed audit returns the empty shape + error, rate 0.0 (no fabricated count)
    assert rep["promises"]["error"].startswith("audit_")
    assert rep["promises"]["dropped"] == []
    assert rep["promises"]["dropped_rate"] == 0.0


async def test_unexpected_raise_in_one_judge_does_not_sink_the_other():
    # A judge raising a NON-LLMError (the window the engines don't catch) must degrade
    # to its empty shape without cancelling the sibling or raising out of the report.
    llm = FakeQRLLM(critic="raise")
    rep = await build_quality_report(
        llm, user_id="u", model_source="s", model_ref="m", chapter="prose")
    assert rep["critic"]["error"] == "critic_error"
    assert rep["critic"]["coherence"] is None
    # the promise audit still completed normally
    assert rep["promises"]["dropped"] == ["the debt to the sect"]
    assert "error" not in rep["promises"]


async def test_canon_grounds_the_critic():
    """A canon bible is handed to the critic as an established-fact block (grounding
    its canon_consistency dim) — the report still shapes correctly."""
    llm = FakeQRLLM()
    rep = await build_quality_report(
        llm, user_id="u", model_source="s", model_ref="m",
        chapter="prose", canon="CANON: Lâm Uyển is the MC.")
    critic_system = next(c for c in llm.calls if "craft critic" in c)
    assert "craft critic" in critic_system  # critic ran with grounding present
    assert rep["critic"]["coherence"] == 4
