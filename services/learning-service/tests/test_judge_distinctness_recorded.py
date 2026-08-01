"""D-JUDGE-DISTINCTNESS-UNRECORDED — a self-graded score looked exactly like an independent one.

provider-registry's `critic` role states the rule in plain text: *"it MUST differ from the
session's actor model (else the roleplay partner grades its own performance)"*. Exactly one
place in the repo enforces it — `chat-service/app/routers/evaluate.py`, which 409s when the
two are equal. Everywhere else the two models are simply never compared, and — worse — the
generator is not even recorded next to the judge, so nobody could compare them after the
fact either.

This does not enforce distinctness here, because it cannot: the caller does not transmit
the generator. It records the honest three-state answer instead of implying the good one:

    True   judge and generator are known and differ
    False  the SAME model — the article graded itself
    None   the generator was not supplied ⇒ **unverified**, not independent

`None` is what every caller produces today. That is the finding, not a gap in the fix: the
point is that an unverified score must stop reading as an independent one, and that the
self-graded fraction becomes measurable. A hard refusal cannot be switched on before that
number is known without failing every default-configured job.
"""
from __future__ import annotations

import json
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.db.online_wiki_judge import persist_wiki_judge


class _Verdict:
    score = 0.8
    reason = "well supported"


async def _persisted_detail(monkeypatch, **kw) -> dict:
    """Run persist and return the JSON detail it wrote, without a database."""
    captured: dict = {}

    async def _fake_persist(pool, **kwargs):
        captured.update(kwargs)
        return True

    monkeypatch.setattr("app.db.online_wiki_judge.persist_consumed_score", _fake_persist)
    await persist_wiki_judge(
        AsyncMock(),
        article_id="a1", user_id=uuid4(), book_id=None,
        verdict=_Verdict(), run_id="r1", **kw,
    )
    return json.loads(captured["comment"])


@pytest.mark.asyncio
async def test_an_unsupplied_generator_records_unverified_not_independent(monkeypatch):
    """The default path today. `null` must be distinguishable from `true` — a consumer
    that cannot tell them apart is back to the original bug."""
    detail = await _persisted_detail(monkeypatch, judge_model="judge-x")
    assert detail["judge_distinct"] is None
    assert detail["generator_model"] is None


@pytest.mark.asyncio
async def test_a_self_graded_score_is_recorded_as_such(monkeypatch):
    """The case the rule exists to prevent: the article's own writer scoring it."""
    detail = await _persisted_detail(
        monkeypatch, judge_model="same-model", generator_model="same-model")
    assert detail["judge_distinct"] is False


@pytest.mark.asyncio
async def test_an_independent_judge_is_recorded_as_distinct(monkeypatch):
    detail = await _persisted_detail(
        monkeypatch, judge_model="judge-x", generator_model="writer-y")
    assert detail["judge_distinct"] is True


@pytest.mark.asyncio
async def test_the_judge_model_is_still_recorded(monkeypatch):
    """Regression guard: the existing fields must survive the addition, or a consumer
    reading `judge_model` breaks silently."""
    detail = await _persisted_detail(monkeypatch, judge_model="judge-x")
    assert detail["judge_model"] == "judge-x"
    assert detail["panel_safe"] is False
    assert detail["reason"] == "well supported"


def test_the_request_model_can_carry_the_generator():
    """The wire has to allow the caller to answer, or the field can never become True."""
    from app.routers.wiki_judge import WikiJudgeArticle

    art = WikiJudgeArticle(article_id="a", article_text="t", generator_model="writer-y")
    assert art.generator_model == "writer-y"
    # And it stays optional, so no existing caller breaks.
    assert WikiJudgeArticle(article_id="a", article_text="t").generator_model is None


# ── the translation judge carries the same contract ──────────────────────────

async def _translation_detail(monkeypatch, **kw) -> dict:
    from app.db.online_translation_judge import persist_translation_judge

    captured: dict = {}

    async def _fake_persist(pool, **kwargs):
        captured.update(kwargs)
        return True

    monkeypatch.setattr(
        "app.db.online_translation_judge.persist_consumed_score", _fake_persist)

    class _Fidelity:
        score = 0.9
        reason = "faithful"

    await persist_translation_judge(
        AsyncMock(),
        ct_id="ct1", user_id=uuid4(), book_id=None,
        verdict=_Fidelity(), origin_event_id="o1", **kw,
    )
    return json.loads(captured["comment"])


@pytest.mark.asyncio
async def test_the_translation_judge_records_distinctness_too(monkeypatch):
    """One contract, not one implementation. The wiki judge was fixed first; a fix that
    stops at the first call site leaves the same score-vs-score ambiguity everywhere
    else, which is how "17+ self-grading sites across 8 services" happened."""
    detail = await _translation_detail(monkeypatch, judge_model="j")
    assert detail["judge_distinct"] is None

    same = await _translation_detail(monkeypatch, judge_model="m", generator_model="m")
    assert same["judge_distinct"] is False

    diff = await _translation_detail(
        monkeypatch, judge_model="j", generator_model="translator-x")
    assert diff["judge_distinct"] is True
