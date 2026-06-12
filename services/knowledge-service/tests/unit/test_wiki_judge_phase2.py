"""D-WIKI-M8-EVAL-PLUS Phase 2 — the orchestrator's automatic-sampled judge hook.

`_maybe_judge` posts the fresh article + its full context sources to the learning
groundedness judge, gated OFF by default (flag + rate 0 + no model = no call) and
best-effort (never raises into generation). post_wiki_judge + ir_to_plaintext are
mocked; settings are monkeypatched.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock

from app.config import settings
from app.wiki import orchestrator


class _Src:
    def __init__(self, text):
        self.text = text


class _Ctx:
    def __init__(self, texts):
        self.items = [_Src(t) for t in texts]


class _Job:
    def __init__(self):
        self.book_id = uuid.uuid4()
        self.user_id = uuid.uuid4()


def _enable(monkeypatch, *, rate=1.0, model="model-x"):
    monkeypatch.setattr(settings, "wiki_llm_judge_enabled", True)
    monkeypatch.setattr(settings, "wiki_llm_judge_model_ref", model)
    monkeypatch.setattr(settings, "wiki_llm_judge_sample_rate", rate)
    monkeypatch.setattr(orchestrator, "ir_to_plaintext", lambda ir: "ARTICLE TEXT")


def test_sampled_bounds():
    assert orchestrator._sampled(1.0) is True
    assert orchestrator._sampled(2.0) is True
    assert orchestrator._sampled(0.0) is False
    assert orchestrator._sampled(-0.5) is False


async def test_off_by_default(monkeypatch):
    posted = AsyncMock()
    monkeypatch.setattr(orchestrator, "post_wiki_judge", posted)
    await orchestrator._maybe_judge(job=_Job(), context=_Ctx(["s"]), ir=object(), article_id="a1", action="written")
    posted.assert_not_awaited()  # wiki_llm_judge_enabled defaults False


async def test_posts_when_enabled_rate1(monkeypatch):
    posted = AsyncMock()
    monkeypatch.setattr(orchestrator, "post_wiki_judge", posted)
    _enable(monkeypatch, rate=1.0)
    job = _Job()
    await orchestrator._maybe_judge(
        job=job, context=_Ctx(["src1", "src2"]), ir=object(), article_id="a1", action="written")
    posted.assert_awaited_once()
    kw = posted.await_args.kwargs
    assert kw["article_id"] == "a1"
    assert kw["book_id"] == job.book_id
    assert kw["user_id"] == job.user_id
    assert kw["article_text"] == "ARTICLE TEXT"
    assert kw["sources"] == ["src1", "src2"]  # FULL context sources, not stored snippets
    assert kw["judge_model"] == "model-x"


async def test_rate_zero_no_post(monkeypatch):
    posted = AsyncMock()
    monkeypatch.setattr(orchestrator, "post_wiki_judge", posted)
    _enable(monkeypatch, rate=0.0)
    await orchestrator._maybe_judge(job=_Job(), context=_Ctx(["s"]), ir=object(), article_id="a1", action="written")
    posted.assert_not_awaited()


async def test_no_model_no_post(monkeypatch):
    posted = AsyncMock()
    monkeypatch.setattr(orchestrator, "post_wiki_judge", posted)
    _enable(monkeypatch, rate=1.0, model="")  # enabled + rate but no model → inert
    await orchestrator._maybe_judge(job=_Job(), context=_Ctx(["s"]), ir=object(), article_id="a1", action="written")
    posted.assert_not_awaited()


async def test_no_article_id_no_post(monkeypatch):
    posted = AsyncMock()
    monkeypatch.setattr(orchestrator, "post_wiki_judge", posted)
    _enable(monkeypatch, rate=1.0)
    await orchestrator._maybe_judge(
        job=_Job(), context=_Ctx(["s"]), ir=object(), article_id=None, action="written")
    posted.assert_not_awaited()


async def test_suggestion_action_no_post(monkeypatch):
    # a clobber-guarded suggestion: gen.ir is NOT the live article → must not judge it
    # (else the suggestion's groundedness misattributes to the human article).
    posted = AsyncMock()
    monkeypatch.setattr(orchestrator, "post_wiki_judge", posted)
    _enable(monkeypatch, rate=1.0)
    await orchestrator._maybe_judge(
        job=_Job(), context=_Ctx(["s"]), ir=object(), article_id="a1", action="suggestion")
    posted.assert_not_awaited()


async def test_best_effort_swallows_errors(monkeypatch):
    posted = AsyncMock(side_effect=RuntimeError("boom"))
    monkeypatch.setattr(orchestrator, "post_wiki_judge", posted)
    _enable(monkeypatch, rate=1.0)
    # must NOT raise — the auto-judge can never break generation.
    await orchestrator._maybe_judge(job=_Job(), context=_Ctx(["s"]), ir=object(), article_id="a1", action="written")
    posted.assert_awaited_once()
