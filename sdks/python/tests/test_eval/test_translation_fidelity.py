"""M7d-1 — judge_translation_fidelity: a standalone [0,1] translation-fidelity
judge built on the shared JudgeLLMClient. Best-effort → None on any non-usable
outcome."""

from __future__ import annotations

import pytest

from loreweave_eval.llm_judge import FidelityVerdict, judge_translation_fidelity


class _FakeJob:
    def __init__(self, status, content):
        self.status = status
        self.result = {"messages": [{"content": content}]} if content is not None else None


class _FakeClient:
    """Returns a fixed judge response; records the call count + last kwargs."""
    def __init__(self, content, status="completed"):
        self._content = content
        self._status = status
        self.calls = 0
        self.last_kwargs = None

    async def submit_and_wait(self, **kwargs):
        self.calls += 1
        self.last_kwargs = kwargs
        return _FakeJob(self._status, self._content)


_ARGS = dict(judge_model="gemma-judge", user_id="u1", model_source="lm_studio")


@pytest.mark.asyncio
async def test_valid_score_parsed():
    client = _FakeClient('{"score": 0.9, "reason": "faithful, minor omission"}')
    v = await judge_translation_fidelity(
        client, source_text="他来了。", translated_text="Anh ấy đã đến.", **_ARGS)
    assert isinstance(v, FidelityVerdict)
    assert v.score == 0.9
    assert "faithful" in v.reason
    # review-impl: prove the judge is FED the right inputs (a swapped
    # source/translated would otherwise pass). Assert both texts reach the LLM,
    # correctly labeled, with the fidelity system prompt.
    msgs = client.last_kwargs["input"]["messages"]
    system = next(m["content"] for m in msgs if m["role"] == "system")
    user = next(m["content"] for m in msgs if m["role"] == "user")
    assert "translation-quality judge" in system  # _FIDELITY_SYSTEM, not precision
    assert user.index("他来了。") < user.index("Anh ấy đã đến.")  # SOURCE before TRANSLATION
    assert "SOURCE:" in user and "TRANSLATION:" in user


@pytest.mark.asyncio
async def test_score_out_of_range_returns_none():
    client = _FakeClient('{"score": 1.5}')
    v = await judge_translation_fidelity(
        client, source_text="x", translated_text="y", **_ARGS)
    assert v is None


@pytest.mark.asyncio
async def test_empty_inputs_skip_the_call():
    client = _FakeClient('{"score": 1.0}')
    assert await judge_translation_fidelity(
        client, source_text="", translated_text="y", **_ARGS) is None
    assert await judge_translation_fidelity(
        client, source_text="x", translated_text="   ", **_ARGS) is None
    assert client.calls == 0  # no LLM call when either side is empty


@pytest.mark.asyncio
async def test_unparseable_response_returns_none():
    client = _FakeClient("not json at all")
    v = await judge_translation_fidelity(
        client, source_text="x", translated_text="y", **_ARGS)
    assert v is None


@pytest.mark.asyncio
async def test_non_completed_job_returns_none():
    client = _FakeClient('{"score": 0.8}', status="failed")
    v = await judge_translation_fidelity(
        client, source_text="x", translated_text="y", **_ARGS)
    assert v is None


@pytest.mark.asyncio
async def test_boundary_scores_accepted():
    for s in ("0.0", "1.0"):
        client = _FakeClient(f'{{"score": {s}, "reason": "ok"}}')
        v = await judge_translation_fidelity(
            client, source_text="x", translated_text="y", **_ARGS)
        assert v is not None and v.score == float(s)
