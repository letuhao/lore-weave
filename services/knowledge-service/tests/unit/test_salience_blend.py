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
