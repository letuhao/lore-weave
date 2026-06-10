"""A2-S3 — SCORE symbolic canon guard (pure units)."""

from __future__ import annotations

from app.engine.canon_check import (
    EVENT_ORDER_CHAPTER_STRIDE,
    CanonViolation,
    gone_cast_in_draft,
    scene_at_order,
)


def _snap(*entities):
    return {"at_order": 5_000_000, "entities": list(entities)}


def _ent(entity_id, name, status, **extra):
    return {"entity_id": entity_id, "name": name, "canonical_name": name.lower(),
            "status": status, **extra}


# ── scene_at_order ────────────────────────────────────────────────────

def test_scene_at_order_scales_by_stride():
    assert scene_at_order(3) == 3 * EVENT_ORDER_CHAPTER_STRIDE
    assert scene_at_order(0) == 0
    assert scene_at_order(None) is None


# ── gone_cast_in_draft ────────────────────────────────────────────────

def test_flags_gone_entity_present_in_draft():
    snap = _snap(_ent("e-kai", "Kai", "gone", glossary_entity_id="g-kai"))
    out = gone_cast_in_draft("Kai drew his sword and charged.", snap)
    assert len(out) == 1
    assert out[0].entity_id == "e-kai"
    assert out[0].glossary_entity_id == "g-kai"
    assert out[0].status == "gone"
    assert out[0].source == "score_symbolic"
    assert "Kai" in out[0].span


def test_active_entity_not_flagged():
    snap = _snap(_ent("e-bob", "Bob", "active"))
    assert gone_cast_in_draft("Bob walked to town.", snap) == []


def test_gone_entity_absent_from_draft_not_flagged():
    snap = _snap(_ent("e-kai", "Kai", "gone"))
    assert gone_cast_in_draft("Bob walked alone through the empty hall.", snap) == []


def test_ascii_word_boundary_avoids_substring_false_positive():
    # 'Al' (gone) must NOT match inside 'Always'.
    snap = _snap(_ent("e-al", "Al", "gone"))
    assert gone_cast_in_draft("Always the wind blew cold.", snap) == []
    # but a real word-boundary mention IS flagged.
    assert len(gone_cast_in_draft("Al stood in the doorway.", snap)) == 1


def test_cjk_name_substring_match():
    # CJK has no \b word boundary → plain containment.
    snap = _snap(_ent("e-z", "卡斯托", "gone"))
    out = gone_cast_in_draft("城门倒下，卡斯托举起了剑。", snap)
    assert len(out) == 1 and out[0].entity_id == "e-z"


def test_dedup_per_entity():
    snap = _snap(_ent("e-kai", "Kai", "gone"))
    out = gone_cast_in_draft("Kai spoke. Kai laughed. Kai left.", snap)
    assert len(out) == 1  # one violation per entity, not per occurrence


def test_absent_snapshot_degrades_to_empty():
    assert gone_cast_in_draft("Kai acted.", None) == []
    assert gone_cast_in_draft("", _snap(_ent("e", "Kai", "gone"))) == []


def test_canonical_name_match_when_display_name_differs():
    # name 'The Phoenix' absent, canonical 'phoenix' present.
    snap = _snap({"entity_id": "e-p", "name": "The Phoenix",
                  "canonical_name": "phoenix", "status": "gone"})
    out = gone_cast_in_draft("A phoenix rose from the ash.", snap)
    assert len(out) == 1 and out[0].matched == "phoenix"


def test_violation_model_shape():
    v = CanonViolation(entity_id="e1", span="x")
    assert v.kind == "gone_entity_present" and v.confirmed is None


# ── judge_canon (A2-S3b — fake LLM) ───────────────────────────────────

import pytest
from types import SimpleNamespace
from app.engine.canon_check import (
    judge_canon, check_canon, reflect_revise, ReflectResult,
)


class _FakeJudge:
    def __init__(self, content=None, status="completed", raise_exc=None):
        self._content, self._status, self._exc = content, status, raise_exc
        self.calls = 0

    async def submit_and_wait(self, **kwargs):
        self.calls += 1
        if self._exc:
            raise self._exc
        return SimpleNamespace(status=self._status,
                               result={"messages": [{"content": self._content}]})


def _cand(eid="e-kai", name="Kai"):
    return CanonViolation(entity_id=eid, name=name, span=f"{name} drew his sword")


@pytest.mark.asyncio
async def test_judge_confirms_violation():
    judge = _FakeJudge('{"verdicts":[{"entity_id":"e-kai","violated":true,"why":"acts"}]}')
    out = await judge_canon(judge, user_id="u", model_source="user_model",
                            model_ref="m", draft="Kai drew his sword.", candidates=[_cand()])
    assert out[0].confirmed is True and out[0].source == "llm_judge"
    assert out[0].why == "acts"  # /review-impl #3 — judge reasoning surfaced
    assert out[0].span  # symbolic span preserved (not overwritten)


@pytest.mark.asyncio
async def test_reflect_surfaces_advisory_drops_cleared():
    """/review-impl #1 — advisory (confirmed=None) candidates are surfaced (the
    author sees them); judge-cleared (confirmed=False) are dropped; the gate's
    `resolved` depends on the HARD subset only."""
    advisory = CanonViolation(entity_id="e-a", name="A", confirmed=None)
    cleared = CanonViolation(entity_id="e-c", name="C", confirmed=False)
    async def check(_): return [advisory, cleared]
    async def revise(_t, _v): raise AssertionError("no hard → no revise")
    r = await reflect_revise(draft="x", check_fn=check, revise_fn=revise, max_iters=2)
    assert r.resolved is True                  # no confirmed-hard
    assert [v.entity_id for v in r.violations] == ["e-a"]  # advisory kept, cleared dropped


@pytest.mark.asyncio
async def test_judge_clears_non_violation():
    # flashback / mention → violated false → confirmed False (not hard).
    judge = _FakeJudge('{"verdicts":[{"entity_id":"e-kai","violated":false,"why":"memory"}]}')
    out = await judge_canon(judge, user_id="u", model_source="user_model",
                            model_ref="m", draft="She remembered Kai.", candidates=[_cand()])
    assert out[0].confirmed is False


@pytest.mark.asyncio
async def test_judge_degrades_to_symbolic_on_error():
    from loreweave_llm.errors import LLMError
    judge = _FakeJudge(raise_exc=LLMError("down"))
    out = await judge_canon(judge, user_id="u", model_source="user_model",
                            model_ref="m", draft="Kai acts.", candidates=[_cand()])
    assert out[0].confirmed is None  # CC4 — never blocks on its own failure


@pytest.mark.asyncio
async def test_check_canon_symbolic_only_without_judge():
    snap = _snap(_ent("e-kai", "Kai", "gone"))
    out = await check_canon("Kai charged forward.", snap, judge=None)
    assert len(out) == 1 and out[0].confirmed is None  # advisory (no judge)


# ── reflect_revise (A2-S3b) ───────────────────────────────────────────

def _hard(eid="e-kai"):
    return CanonViolation(entity_id=eid, name="Kai", confirmed=True)


@pytest.mark.asyncio
async def test_reflect_no_violations_no_revise():
    async def check(_): return []
    async def revise(_t, _v): raise AssertionError("must not revise")
    r = await reflect_revise(draft="clean", check_fn=check, revise_fn=revise, max_iters=2)
    assert r.resolved and r.iterations == 0 and r.text == "clean"


@pytest.mark.asyncio
async def test_reflect_repairs_then_resolves():
    checks = [[_hard()], []]  # 1st check: hard; after revise: clean
    async def check(_): return checks.pop(0)
    async def revise(_t, _v): return "revised"
    r = await reflect_revise(draft="bad", check_fn=check, revise_fn=revise, max_iters=2)
    assert r.resolved and r.iterations == 1 and r.text == "revised" and r.violations == []


@pytest.mark.asyncio
async def test_reflect_escalates_when_unfixable():
    async def check(_): return [_hard()]   # always hard
    async def revise(_t, _v): return "still bad"
    r = await reflect_revise(draft="bad", check_fn=check, revise_fn=revise, max_iters=1)
    assert not r.resolved and r.iterations == 1 and len(r.violations) == 1


@pytest.mark.asyncio
async def test_reflect_stops_when_reviser_gives_up():
    async def check(_): return [_hard()]
    async def revise(_t, _v): return None   # reviser failed
    r = await reflect_revise(draft="bad", check_fn=check, revise_fn=revise, max_iters=3)
    assert not r.resolved and r.iterations == 1 and r.text == "bad"  # kept original
