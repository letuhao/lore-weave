"""The plan-liveness check inside `run_canon_reflect` — the WIRING, not the comparison.

`test_plan_conflict.py` proves the rule. This proves the rule is reached, that every failure
mode reports a STATUS instead of a clean result, and that the violation actually lands on the
envelope. Those are different bugs and the pure tests cannot see any of them: a `plan_cast` the
caller never fetched, an extractor that raises, a kwarg the extractor does not accept.

That last one is not hypothetical — the first version of this wiring passed `trace_id=` and
`source_language=` to `extract_events`, which accepts neither. Every test that stubs the
extractor stays green on that; only a live call raises TypeError. Hence
`test_the_extractor_is_called_with_kwargs_it_actually_accepts`, which asserts against the REAL
signature rather than against the stub.
"""
from __future__ import annotations

import inspect
import uuid

import pytest
from loreweave_guard import CheckStatus

from app.engine import canon_reflect as CR
from app.engine.plan_conflict import PLAN_CONFLICT_KIND

DAO, VIEN = "e-dao", "e-vien"
CAST = [
    {"entity_id": DAO, "cached_name": "Tô Thanh Dao", "cached_aliases": ["Dao"]},
    {"entity_id": VIEN, "cached_name": "Lạc Viên", "cached_aliases": []},
]
PLAN = {DAO: "alive", VIEN: "alive"}


class _Eff:
    def __init__(self, entity_ref, status):
        self.entity_ref, self.status = entity_ref, status


class _Ev:
    def __init__(self, *effects):
        self.status_effects = list(effects)


class _Knowledge:
    """A populated graph that simply has no row for this cast — the S2 fixture."""

    async def fact_for_check(self, **kw):
        return {"entities": [{"entity_id": "someone_else", "status": "alive"}]}


def _stub_extractor(monkeypatch, events=None, raises=None, capture=None):
    async def fake(text, entities, known, **kw):
        if capture is not None:
            capture.update({"text": text, "known": known, **kw})
        if raises is not None:
            raise raises
        return events or []
    monkeypatch.setattr(CR, "extract_events", fake)


async def _reflect(monkeypatch, *, plan=PLAN, cast=CAST, events=None, raises=None,
                   capture=None, draft="Lạc Viên đâm chết Tô Thanh Dao."):
    _stub_extractor(monkeypatch, events=events, raises=raises, capture=capture)
    return await CR.run_canon_reflect(
        knowledge=_Knowledge(), llm=None, user_id=uuid.uuid4(), project_id=uuid.uuid4(),
        cast_glossary_ids=[DAO, VIEN], scene_sort_order=1,
        plan_status=plan, plan_cast=cast,
        draft=draft, packed_prompt="",
        profile=type("P", (), {"source_language": "vi"})(),
        drafter_source="user_model", drafter_ref="m",
        judge_source=None, judge_ref=None,
        prompt_estimate=0, max_output_tokens=100, max_iters=0,
    )


# ── the acceptance case, end to end through the engine ────────────────────────────────────

@pytest.mark.asyncio
async def test_a_draft_that_kills_a_plan_alive_character_raises_a_violation(monkeypatch):
    _t, r, _ = await _reflect(monkeypatch, events=[_Ev(_Eff("Tô Thanh Dao", "gone"))])
    hits = [v for v in r.violations if v.kind == PLAN_CONFLICT_KIND]
    assert len(hits) == 1
    assert hits[0].entity_id == DAO and hits[0].name == "Tô Thanh Dao"
    assert hits[0].confirmed is None, "symbolic tier is ADVISORY until a judge confirms it"
    assert r.checks["plan_liveness"] == CheckStatus.CHECKED


@pytest.mark.asyncio
async def test_CONTROL_a_draft_that_kills_nobody_raises_nothing(monkeypatch):
    """The live POC's own control, in-process. Without it, "always violate" satisfies the test
    above and every scene becomes unpublishable."""
    _t, r, _ = await _reflect(monkeypatch, events=[_Ev(), _Ev()],
                              draft="Hai người uống trà rồi ai về nhà nấy.")
    assert [v for v in r.violations if v.kind == PLAN_CONFLICT_KIND] == []
    assert r.checks["plan_liveness"] == CheckStatus.CHECKED
    assert r.unlinked_gone_refs == []


# ── every failure mode reports a STATUS, never a clean result ─────────────────────────────

@pytest.mark.asyncio
async def test_no_plan_at_all_is_NOT_APPLICABLE_not_a_gap(monkeypatch):
    """The last scene of a chapter has nothing after it. That is not a coverage hole, and
    calling it one would paint amber on every chapter ending in the book."""
    _t, r, _ = await _reflect(monkeypatch, plan={}, events=[_Ev(_Eff("Tô Thanh Dao", "gone"))])
    assert r.checks["plan_liveness"] == CheckStatus.NOT_APPLICABLE
    assert [v for v in r.violations if v.kind == PLAN_CONFLICT_KIND] == []


@pytest.mark.asyncio
async def test_a_plan_with_NO_NAMES_to_join_is_unverified_not_clean(monkeypatch):
    """A glossary outage. The plan HAS an opinion and we could not fetch the names to test it
    against — reporting `checked` there is the exact false-green this arc exists to kill."""
    _t, r, _ = await _reflect(monkeypatch, cast=[], events=[_Ev(_Eff("Tô Thanh Dao", "gone"))])
    assert r.checks["plan_liveness"] == CheckStatus.UNVERIFIED_INPUT
    assert r.guard_status != "checked"


@pytest.mark.asyncio
async def test_an_extractor_that_RAISES_is_degraded_and_does_not_fail_the_generate(monkeypatch):
    """F1: a check never costs the author the draft they already paid for."""
    text, r, _ = await _reflect(monkeypatch, raises=RuntimeError("provider down"))
    assert r.checks["plan_liveness"] == CheckStatus.DEGRADED
    assert text, "the draft survives"


@pytest.mark.asyncio
async def test_a_death_it_could_not_PLACE_is_reported_as_unverified(monkeypatch):
    """The live POC's actual failure: glossary held the cast with an empty `cached_name`, the
    death WAS detected, and nothing joined. The names must ride the envelope."""
    _t, r, _ = await _reflect(monkeypatch, events=[_Ev(_Eff("Mộ Dung Tuyết", "gone"))])
    assert r.checks["plan_liveness"] == CheckStatus.UNVERIFIED_INPUT
    assert r.unlinked_gone_refs == ["Mộ Dung Tuyết"]
    assert [v for v in r.violations if v.kind == PLAN_CONFLICT_KIND] == []


# ── the boundary the stub cannot check ────────────────────────────────────────────────────

def test_the_extractor_is_called_with_kwargs_it_actually_accepts():
    """Asserted against the REAL `extract_events` signature, because a stub accepts anything.

    The first version of this wiring passed `trace_id=` and `source_language=`; the extractor
    takes neither, so it would have raised TypeError on the first live call while every stubbed
    test stayed green. The DEGRADED branch would then have swallowed it and the check would
    have reported "extraction failed" forever, on every scene, silently."""
    from loreweave_extraction.extractors.event import extract_events
    accepted = set(inspect.signature(extract_events).parameters)
    src = inspect.getsource(CR._check_plan_liveness)
    call = src[src.index("await extract_events("):]
    call = call[:call.index("\n        )")]
    passed = {ln.split("=")[0].strip() for ln in call.split(",") if "=" in ln}
    unknown = {k for k in passed if k and not k.startswith("#")} - accepted
    assert not unknown, f"kwargs extract_events does not accept: {sorted(unknown)}"


@pytest.mark.asyncio
async def test_the_extractor_is_anchored_on_the_cast_names(monkeypatch):
    """`known_entities` is what lets the model resolve "Dao" to the character rather than
    inventing a new one. Passing [] there is a silent quality loss with no failing test."""
    cap: dict = {}
    await _reflect(monkeypatch, events=[], capture=cap)
    assert set(cap["known"]) == {"Tô Thanh Dao", "Lạc Viên"}
    assert cap["model_source"] == "user_model", "the DRAFTER's model, not a hardcoded one"


@pytest.mark.asyncio
async def test_the_violation_reaches_the_envelope_the_FE_reads(monkeypatch):
    """A violation the envelope drops is a violation nobody sees."""
    from app.engine.canon_check import canon_envelope
    _t, r, _ = await _reflect(monkeypatch, events=[_Ev(_Eff("Dao", "gone"))])
    env = canon_envelope(r)
    kinds = [v["kind"] for v in env["violations"]]
    assert PLAN_CONFLICT_KIND in kinds
    assert env["checks"]["plan_liveness"] == "checked"
    assert "unlinked_gone_refs" in env
