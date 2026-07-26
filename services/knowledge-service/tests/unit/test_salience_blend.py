"""Track 4 P1 — salience-weighted entity ranking (blend_entity_salience / apply_salience).

Proves: weight=0 is the identity (byte-identical pre-P1), a heavily/recently-accessed
entity is boosted above a higher static-rank one, recency decay demotes stale entities,
missing rows get 0 boost, and apply_salience does NO DB read when the flag is off.
"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.context.selectors.salience import apply_salience, blend_entity_salience
from app.db.repositories.entity_access import EntitySalience

NOW = datetime(2026, 7, 2, tzinfo=timezone.utc)


def _e(eid: str, rank: float, is_pinned: bool = False):
    return SimpleNamespace(entity_id=eid, rank_score=rank, is_pinned=is_pinned)


def _s(eid: str, count: int, age_days: float) -> EntitySalience:
    return EntitySalience(eid, count, 0.0, NOW - timedelta(days=age_days))


def _blend(ents, sal, weight=0.3):
    return blend_entity_salience(ents, sal, weight=weight, half_life_days=14.0, now=NOW)


def test_weight_zero_is_identity():
    ents = [_e("a", 0.5), _e("b", 0.9)]
    out = _blend(ents, {"a": _s("a", 100, 0)}, weight=0.0)
    assert out is ents  # same object, untouched


def test_empty_salience_is_identity():
    ents = [_e("a", 0.5)]
    assert _blend(ents, {}) is ents


def test_high_access_entity_boosted_above_higher_static_rank():
    # b has higher static rank (0.5) but a is heavily+recently accessed.
    ents = [_e("b", 0.5), _e("a", 0.4)]
    out = _blend(ents, {"a": _s("a", 100, 0)})  # a: 0.4 + 0.3*1.0 = 0.7 > b: 0.5
    assert [e.entity_id for e in out] == ["a", "b"]


def test_recency_decay_demotes_stale():
    ents = [_e("stale", 0.0), _e("recent", 0.0)]
    sal = {"stale": _s("stale", 100, 60), "recent": _s("recent", 100, 0)}
    out = _blend(ents, sal)
    assert [e.entity_id for e in out] == ["recent", "stale"]


def test_entity_without_salience_row_gets_zero_boost():
    ents = [_e("a", 0.5), _e("b", 0.4)]
    out = _blend(ents, {"b": _s("b", 100, 0)})  # b: 0.4+0.3=0.7 > a: 0.5 (no row)
    assert [e.entity_id for e in out] == ["b", "a"]


def test_stable_order_on_equal_blended_rank():
    ents = [_e("a", 0.5), _e("b", 0.5)]
    sal = {"a": _s("a", 10, 0), "b": _s("b", 10, 0)}  # identical → order preserved
    out = _blend(ents, sal)
    assert [e.entity_id for e in out] == ["a", "b"]


def test_pinned_entity_always_leads_even_vs_high_salience():
    # a is pinned but never accessed; b is a heavily-accessed non-pin. The pin MUST
    # stay first (else full-mode budget-trim, which pops the tail, could drop it).
    ents = [_e("a_pin", 0.3, is_pinned=True), _e("b_hot", 0.9)]
    out = _blend(ents, {"b_hot": _s("b_hot", 1000, 0)}, weight=0.6)
    assert [e.entity_id for e in out] == ["a_pin", "b_hot"]


def test_pins_ordered_among_themselves_by_salience():
    ents = [_e("p_cold", 0.5, is_pinned=True), _e("p_hot", 0.5, is_pinned=True), _e("n", 0.4)]
    out = _blend(ents, {"p_hot": _s("p_hot", 100, 0)}, weight=0.3)
    # both pins lead the non-pin; the accessed pin leads the cold pin.
    assert [e.entity_id for e in out] == ["p_hot", "p_cold", "n"]


def test_rank_score_left_untouched():
    ents = [_e("a", 0.4)]
    out = _blend(ents, {"a": _s("a", 100, 0)})
    assert out[0].rank_score == 0.4  # only ORDER changes, not the displayed score


class TestPromotionP3a:
    def _promo(self, ev=0, mn=0, age_days=None):
        from app.context.selectors.salience import PromotionSignals
        up = (NOW - timedelta(days=age_days)) if age_days is not None else None
        return PromotionSignals(evidence_count=ev, mention_count=mn, updated_at=up)

    def test_promotion_reorders_by_evidence(self):
        # equal static rank; b has strong graph evidence → b leads.
        ents = [_e("a", 0.5), _e("b", 0.5)]
        out = blend_entity_salience(
            ents, {}, weight=0.0, half_life_days=14.0, now=NOW,
            promotion={"b": self._promo(ev=50, mn=30, age_days=0)},
            promote_weight=0.3,
        )
        assert [e.entity_id for e in out] == ["b", "a"]

    def test_promotion_zero_weight_is_identity(self):
        ents = [_e("a", 0.5), _e("b", 0.4)]
        out = blend_entity_salience(
            ents, {}, weight=0.0, half_life_days=14.0, now=NOW,
            promotion={"b": self._promo(ev=50)}, promote_weight=0.0,
        )
        assert out is ents

    def test_stale_edit_contributes_less_than_fresh(self):
        from app.context.selectors.salience import promotion_score
        fresh = self._promo(ev=10, mn=10, age_days=0)
        stale = self._promo(ev=10, mn=10, age_days=300)
        kw = dict(max_log_evidence=3.0, max_log_mention=3.0, half_life_days=30.0, now=NOW)
        assert promotion_score(fresh, **kw) > promotion_score(stale, **kw)

    def test_log_damping_caps_mega_entity(self):
        from app.context.selectors.salience import promotion_score
        import math
        big = self._promo(ev=10_000)
        kw = dict(
            max_log_evidence=math.log1p(10_000), max_log_mention=0.0,
            half_life_days=30.0, now=NOW,
        )
        assert promotion_score(big, **kw) <= 1.0  # bounded even at extreme counts

    def test_access_and_promotion_compose(self):
        # a gets access boost, b gets promotion boost — both beat c (no signals).
        ents = [_e("c", 0.5), _e("a", 0.45), _e("b", 0.45)]
        out = blend_entity_salience(
            ents, {"a": _s("a", 100, 0)}, weight=0.3, half_life_days=14.0, now=NOW,
            promotion={"b": self._promo(ev=50, mn=20, age_days=0)}, promote_weight=0.3,
        )
        assert out[-1].entity_id == "c"

    def test_pins_still_lead_over_promotion(self):
        ents = [_e("pin", 0.2, is_pinned=True), _e("hot", 0.9)]
        out = blend_entity_salience(
            ents, {}, weight=0.0, half_life_days=14.0, now=NOW,
            promotion={"hot": self._promo(ev=1000, mn=1000, age_days=0)},
            promote_weight=1.0,
        )
        assert out[0].entity_id == "pin"


class TestFeedbackP3b:
    def _sal(self, eid, feedback, count=1, age_days=0.0):
        from app.db.repositories.entity_access import EntitySalience
        return EntitySalience(eid, count, 0.0, NOW - timedelta(days=age_days), feedback_score=feedback)

    def test_positive_feedback_boosts(self):
        ents = [_e("a", 0.5), _e("b", 0.45)]
        out = blend_entity_salience(
            ents, {"b": self._sal("b", feedback=5.0)},
            weight=0.0, half_life_days=14.0, now=NOW, feedback_weight=0.3,
        )
        assert [e.entity_id for e in out] == ["b", "a"]  # tanh(5/3)≈0.93 → +0.28

    def test_negative_feedback_demotes(self):
        ents = [_e("a", 0.5), _e("b", 0.5)]
        out = blend_entity_salience(
            ents, {"a": self._sal("a", feedback=-5.0)},
            weight=0.0, half_life_days=14.0, now=NOW, feedback_weight=0.3,
        )
        assert [e.entity_id for e in out] == ["b", "a"]  # a demoted below b

    def test_feedback_saturates(self):
        import math
        # 1000 thumbs isn't meaningfully stronger than 10 — tanh squash.
        assert abs(math.tanh(1000 / 3.0) - math.tanh(10 / 3.0)) < 0.01

    def test_feedback_weight_zero_is_identity(self):
        ents = [_e("a", 0.5)]
        out = blend_entity_salience(
            ents, {"a": self._sal("a", feedback=5.0)},
            weight=0.0, half_life_days=14.0, now=NOW, feedback_weight=0.0,
        )
        assert out is ents


@pytest.mark.asyncio
async def test_apply_salience_promotion_only_loads_neo4j_not_repo(monkeypatch):
    # w_access=0 + w_promote>0 → no access-log read; Neo4j promotion load runs.
    from app.config import settings
    from app.context.selectors import salience as mod

    monkeypatch.setattr(settings, "salience_access_weight", 0.0)
    monkeypatch.setattr(settings, "salience_promote_weight", 0.3)

    async def fake_load(session, project_id, ids):
        return {"b": mod.PromotionSignals(50, 20, NOW)}

    monkeypatch.setattr(mod, "load_promotion_signals", fake_load)
    repo = AsyncMock()
    ents = [_e("a", 0.5), _e("b", 0.5)]
    out = await mod.apply_salience(repo, ents, uuid4(), uuid4(), neo4j_session=object())
    repo.load_salience.assert_not_called()
    assert [e.entity_id for e in out] == ["b", "a"]


@pytest.mark.asyncio
async def test_apply_salience_promotion_neo4j_failure_degrades(monkeypatch):
    from app.config import settings
    from app.context.selectors import salience as mod

    monkeypatch.setattr(settings, "salience_access_weight", 0.0)
    monkeypatch.setattr(settings, "salience_promote_weight", 0.3)

    async def boom(session, project_id, ids):
        raise RuntimeError("neo4j down")

    monkeypatch.setattr(mod, "load_promotion_signals", boom)
    ents = [_e("a", 0.5)]
    out = await mod.apply_salience(AsyncMock(), ents, uuid4(), uuid4(), neo4j_session=object())
    assert out is ents  # degrade to identity, never raise


@pytest.mark.asyncio
async def test_apply_salience_skips_repo_when_weight_zero(monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "salience_access_weight", 0.0)
    repo = AsyncMock()
    ents = [_e("a", 0.5)]
    out = await apply_salience(repo, ents, uuid4(), uuid4())
    assert out is ents
    repo.load_salience.assert_not_called()  # no DB read when the flag is off


@pytest.mark.asyncio
async def test_apply_salience_loads_and_blends_when_positive(monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "salience_access_weight", 0.3)
    monkeypatch.setattr(settings, "salience_half_life_days", 14.0)
    repo = AsyncMock()
    repo.load_salience = AsyncMock(return_value={"a": _s("a", 100, 0)})
    out = await apply_salience(repo, [_e("b", 0.5), _e("a", 0.4)], uuid4(), uuid4())
    repo.load_salience.assert_awaited_once()
    assert [e.entity_id for e in out] == ["a", "b"]
