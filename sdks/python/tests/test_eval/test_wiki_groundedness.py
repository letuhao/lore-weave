"""D-WIKI-M8-EVAL-PLUS — judge_wiki_groundedness: a standalone [0,1] groundedness
judge built on the shared JudgeLLMClient. Best-effort → None on any non-usable
outcome."""

from __future__ import annotations

import pytest

from loreweave_eval.llm_judge import GroundednessVerdict, judge_wiki_groundedness


class _FakeJob:
    def __init__(self, status, content):
        self.status = status
        self.result = {"messages": [{"content": content}]} if content is not None else None


class _FakeClient:
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
async def test_valid_score_parsed_and_inputs_fed():
    client = _FakeClient('{"score": 0.85, "reason": "claims supported"}')
    v = await judge_wiki_groundedness(
        client, article_text="Mina is a teacher.", sources=["Mina taught school."], **_ARGS)
    assert isinstance(v, GroundednessVerdict)
    assert v.score == 0.85
    assert "supported" in v.reason
    # prove the judge is fed ARTICLE + SOURCES under the groundedness prompt.
    msgs = client.last_kwargs["input"]["messages"]
    system = next(m["content"] for m in msgs if m["role"] == "system")
    user = next(m["content"] for m in msgs if m["role"] == "user")
    assert "groundedness judge" in system
    assert "ARTICLE:" in user and "SOURCES:" in user
    assert user.index("Mina is a teacher.") < user.index("Mina taught school.")


@pytest.mark.asyncio
async def test_score_out_of_range_returns_none():
    client = _FakeClient('{"score": 1.4}')
    assert await judge_wiki_groundedness(
        client, article_text="x", sources=["y"], **_ARGS) is None


@pytest.mark.asyncio
async def test_empty_article_or_sources_skip_the_call():
    client = _FakeClient('{"score": 1.0}')
    assert await judge_wiki_groundedness(client, article_text="", sources=["y"], **_ARGS) is None
    assert await judge_wiki_groundedness(client, article_text="x", sources=[], **_ARGS) is None
    assert await judge_wiki_groundedness(client, article_text="x", sources=["  "], **_ARGS) is None
    assert client.calls == 0  # no LLM call when either side is empty


@pytest.mark.asyncio
async def test_unparseable_response_returns_none():
    client = _FakeClient("not json")
    assert await judge_wiki_groundedness(
        client, article_text="x", sources=["y"], **_ARGS) is None


@pytest.mark.asyncio
async def test_non_completed_job_returns_none():
    client = _FakeClient('{"score": 0.8}', status="failed")
    assert await judge_wiki_groundedness(
        client, article_text="x", sources=["y"], **_ARGS) is None


@pytest.mark.asyncio
async def test_boundary_scores_accepted():
    for s in ("0.0", "1.0"):
        client = _FakeClient(f'{{"score": {s}, "reason": "ok"}}')
        v = await judge_wiki_groundedness(client, article_text="x", sources=["y"], **_ARGS)
        assert v is not None and v.score == float(s)
