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


# ── the JUDGE tier: advisory -> HARD, and the ways it must NOT fire ───────────────────────
#
# The author's rule, verbatim: judge confirms => HARD, no judge => advisory. These pin both
# halves, plus the thing a "does it become HARD" test alone would miss — that `resolved` has
# to flip too, because the publish gate keys on `resolved == false` and NOT on the violation
# list. A red row on a chapter that still publishes is the false-green in reverse.

class _Judge:
    """A judge whose verdicts are scripted. `status` is settable so the CC4 degrade paths
    (a job that never completes) can be exercised without a network."""

    def __init__(self, verdicts, status="completed"):
        self._verdicts, self._status = verdicts, status
        self.calls = []

    def __init_subclass__(cls, **kw):  # pragma: no cover - defensive
        super().__init_subclass__(**kw)

    async def submit_and_wait(self, **kw):
        self.calls.append(kw)
        import json as _json
        import types
        # `messages[0].content`, NOT `content` — the gateway's job result shape, which
        # `extract_judge_text` calls LOAD-BEARING in its own docstring. The first version of
        # this stub used `{"content": ...}`, invented from what the code looked like it wanted,
        # and both judge tests failed for a reason that had nothing to do with the code. Take a
        # fixture's shape from the PRODUCER's schema, never from the consumer.
        return types.SimpleNamespace(
            status=self._status,
            result={"messages": [{"content": _json.dumps({"verdicts": self._verdicts})}]},
        )


async def _reflect_judged(monkeypatch, verdicts, *, status="completed",
                          judge=("user_model", "critic-model"),
                          identity_verified=True):
    _stub_extractor(monkeypatch, events=[_Ev(_Eff("Tô Thanh Dao", "gone"))])
    llm = _Judge(verdicts, status=status)
    return await CR.run_canon_reflect(
        knowledge=_Knowledge(), llm=llm, user_id=uuid.uuid4(), project_id=uuid.uuid4(),
        cast_glossary_ids=[DAO, VIEN], scene_sort_order=1,
        plan_status=PLAN, plan_cast=CAST,
        draft="Lạc Viên đâm chết Tô Thanh Dao.",
        # The names must be IN the packed prompt or name-grounding reports NO_RULES, the
        # derived guard_status is not `checked`, and `verdict` is None by the honesty rule
        # — which would make the verdict assertions below untestable for a reason that has
        # nothing to do with the judge.
        packed_prompt="Tô Thanh Dao và Lạc Viên ở cổng thành.",
        profile=type("P", (), {"source_language": "vi"})(),
        drafter_source="user_model", drafter_ref="drafter-model",
        judge_source=judge[0] if judge else None,
        judge_ref=judge[1] if judge else None,
        identity_verified=identity_verified,
        prompt_estimate=0, max_output_tokens=100, max_iters=0,
    ), llm


@pytest.mark.asyncio
async def test_a_CONFIRMED_conflict_is_HARD_and_blocks_publish(monkeypatch):
    (_t, r, _), _llm = await _reflect_judged(
        monkeypatch, [{"entity_id": DAO, "violated": True, "why": "cô ấy chết thật"}])
    hit = next(v for v in r.violations if v.kind == PLAN_CONFLICT_KIND)
    assert hit.confirmed is True
    assert r.resolved is False, "the publish gate keys on resolved, not on the violation list"
    assert r.guard_status == "checked", "the fixture must fully check, or verdict is None"
    assert r.verdict is False, "a fully-checked guard with a HARD violation is a FAILED verdict"


@pytest.mark.asyncio
async def test_a_judge_that_CLEARS_it_does_not_block(monkeypatch):
    """A feint, a dream, a prophecy. The counterweight without which "always HARD" passes the
    test above and every planned death becomes unpublishable."""
    (_t, r, _), _llm = await _reflect_judged(
        monkeypatch, [{"entity_id": DAO, "violated": False, "why": "chỉ là giấc mơ"}])
    hit = next(v for v in r.violations if v.kind == PLAN_CONFLICT_KIND)
    assert hit.confirmed is False
    assert r.resolved is True
    assert r.verdict is True, "cleared by the judge ⇒ the scene really did pass"


@pytest.mark.asyncio
async def test_NO_distinct_judge_leaves_it_advisory(monkeypatch):
    """Invariant 2 — the drafter that wrote the death may not certify it. Without a distinct
    judge the finding is neither promoted nor dropped."""
    (_t, r, _), llm = await _reflect_judged(monkeypatch, [], judge=None)
    hit = next(v for v in r.violations if v.kind == PLAN_CONFLICT_KIND)
    assert hit.confirmed is None
    assert r.resolved is True, "advisory must not block"
    assert llm.calls == [], "no judge call may be made without a distinct judge"


@pytest.mark.asyncio
async def test_a_judge_that_never_COMPLETES_leaves_it_advisory(monkeypatch):
    """CC4: a judge that is down must not be able to block a publish — nor clear one."""
    (_t, r, _), _llm = await _reflect_judged(
        monkeypatch, [{"entity_id": DAO, "violated": True, "why": "x"}], status="failed")
    hit = next(v for v in r.violations if v.kind == PLAN_CONFLICT_KIND)
    assert hit.confirmed is None and r.resolved is True


@pytest.mark.asyncio
async def test_the_judge_is_called_with_the_CRITIC_model_not_the_drafters(monkeypatch):
    (_t, _r, _), llm = await _reflect_judged(
        monkeypatch, [{"entity_id": DAO, "violated": True, "why": "x"}])
    assert llm.calls, "the judge was never called"
    assert llm.calls[0]["model_ref"] == "critic-model"
    assert llm.calls[0]["model_ref"] != "drafter-model"


@pytest.mark.asyncio
async def test_a_judge_verdict_for_SOMEONE_ELSE_leaves_the_candidate_advisory(monkeypatch):
    """A candidate the judge does not answer for stays `None` — it must not inherit another
    entity's verdict, and it must not be silently promoted."""
    (_t, r, _), _llm = await _reflect_judged(
        monkeypatch, [{"entity_id": "someone-else", "violated": True, "why": "x"}])
    hit = next(v for v in r.violations if v.kind == PLAN_CONFLICT_KIND)
    assert hit.confirmed is None and r.resolved is True


def test_the_plan_judge_asks_a_DIFFERENT_question_from_the_gone_cast_judge():
    """Two judges, two questions. `judge_canon` asks whether an already-gone character is being
    portrayed as present; this one asks whether the death the passage just wrote is real. A
    shared prompt would ask the wrong one for whichever check borrowed it."""
    from app.engine.canon_check import _build_judge_messages, _build_plan_conflict_messages
    v = [CR.CanonViolation(kind=PLAN_CONFLICT_KIND, entity_id=DAO, name="Tô Thanh Dao",
                           matched="Tô Thanh Dao", status="gone")]
    gone_sys, _ = _build_judge_messages("prose", v, "vi")
    plan_sys, plan_user = _build_plan_conflict_messages("prose", v, "vi")
    assert gone_sys != plan_sys
    assert "permanently" in plan_sys and "ACTIVE PRESENCE" not in plan_sys
    assert "vi" in plan_sys, "the judge must write its `why` in the book's language"
    assert "Tô Thanh Dao" in plan_user


# ── the CHAPTER paths: a declared gap, not a silent pass ──────────────────────────────────

@pytest.mark.asyncio
async def test_a_chapter_level_path_reports_NO_POSITION_not_not_applicable(monkeypatch):
    """The single-pass and stitch paths cover many scenes at once, so there is no single
    position for "who does the plan need AFTER this" and the rung cannot be built.

    That is a GAP, and it must not look like the other reason `plan_status` is empty — a scene
    with nothing after it, where there is genuinely nothing to check. Until `plan_supported`
    existed both returned NOT_APPLICABLE and the envelope could not tell them apart, which is
    precisely the distinction the per-check vocabulary was added for."""
    _stub_extractor(monkeypatch, events=[])
    _t, r, _ = await CR.run_canon_reflect(
        knowledge=_Knowledge(), llm=None, user_id=uuid.uuid4(), project_id=uuid.uuid4(),
        cast_glossary_ids=[DAO], scene_sort_order=1,
        plan_status=None, plan_cast=None, plan_supported=False,
        draft="prose", packed_prompt="",
        profile=type("P", (), {"source_language": "vi"})(),
        drafter_source="user_model", drafter_ref="m",
        judge_source=None, judge_ref=None,
        prompt_estimate=0, max_output_tokens=100, max_iters=0,
    )
    assert r.checks["plan_liveness"] == CheckStatus.NO_POSITION
    assert r.guard_status != "checked", "a declared gap must not round up to a checked guard"


@pytest.mark.asyncio
async def test_CONTROL_a_SCENE_with_nothing_after_it_is_still_NOT_APPLICABLE(monkeypatch):
    """The counterweight: without it, "always NO_POSITION" satisfies the test above and every
    chapter-ending scene turns amber forever — the permanent-amber failure S1 exists to stop."""
    _t, r, _ = await _reflect(monkeypatch, plan={}, events=[])
    assert r.checks["plan_liveness"] == CheckStatus.NOT_APPLICABLE


def test_every_CHAPTER_level_call_site_declares_plan_supported_False():
    r"""Mechanical, because the failure is an omission: a fifth chapter path added later that
    forgets the flag would silently report NOT_APPLICABLE — indistinguishable from a scene with
    nothing after it, which is the exact confusion this flag removes.

    AST, not a regex. The first version matched call bodies with
    `r"await run_canon_reflect\((.*?)
\s{4,8}\)"` and PASSED its own injection: in
    `routers/engine.py` it caught 2 of 3 calls and one match ran to 19,993 characters, having
    swallowed the next call whole — so a flag deleted from one site was still found inside
    another's blob. A guard that survives its own defect is not a guard.
    """
    import ast
    import pathlib

    root = pathlib.Path(__file__).resolve().parents[2] / "app"
    checked, missing = 0, []
    for rel in ("worker/operations.py", "routers/engine.py"):
        tree = ast.parse((root / rel).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            fn = node.func
            if getattr(fn, "id", None) != "run_canon_reflect" and                     getattr(fn, "attr", None) != "run_canon_reflect":
                continue
            checked += 1
            kw = {k.arg for k in node.keywords}
            # A call is scene-level iff it passes the rung; anything else is chapter-level and
            # must SAY so rather than defaulting to "nothing to check".
            if "plan_status" not in kw and "plan_supported" not in kw:
                missing.append(f"{rel}:{node.lineno}")
    assert checked == 6, f"expected 6 run_canon_reflect call sites, found {checked}"
    assert missing == [], f"chapter-level call sites not declaring the gap: {missing}"


# ── a judge that came back with NOTHING must not read as "declined to confirm" ────────────

class _TruncatedJudge:
    """A COMPLETED job whose text is a half-finished reply — no JSON, no verdicts.

    Not hypothetical. MEASURED 2026-08-01 on real 500-word drafts: the judge model reasoned
    aloud in Vietnamese for 5,684 characters and hit the output cap before emitting any JSON.
    `status='completed'`, `finish_reason='length'`, zero verdicts parsed, every candidate left
    `confirmed=None` — byte-identical to a judge that looked and declined. The blocking tier
    had stopped existing and nothing on the envelope said so.

    The earlier 3/3 live judge validation used three-sentence excerpts, which never reproduced
    it. That is why this fixture is long-reply-shaped rather than error-shaped.
    """

    def __init__(self):
        self.calls = []

    async def submit_and_wait(self, **kw):
        self.calls.append(kw)
        import types
        return types.SimpleNamespace(
            status="completed",
            result={"finish_reason": "length",
                    "messages": [{"content": "Hãy xem xét lại: đoạn văn mô tả Lạc Viên bị đâm"}]},
        )


@pytest.mark.asyncio
async def test_a_TRUNCATED_judge_is_UNPARSEABLE_not_a_quiet_advisory(monkeypatch):
    _stub_extractor(monkeypatch, events=[_Ev(_Eff("Tô Thanh Dao", "gone"))])
    llm = _TruncatedJudge()
    _t, r, _ = await CR.run_canon_reflect(
        knowledge=_Knowledge(), llm=llm, user_id=uuid.uuid4(), project_id=uuid.uuid4(),
        cast_glossary_ids=[DAO, VIEN], scene_sort_order=1,
        plan_status=PLAN, plan_cast=CAST,
        draft="Lạc Viên đâm chết Tô Thanh Dao.",
        packed_prompt="Tô Thanh Dao và Lạc Viên ở cổng thành.",
        profile=type("P", (), {"source_language": "vi"})(),
        drafter_source="user_model", drafter_ref="drafter-model",
        judge_source="user_model", judge_ref="critic-model",
        prompt_estimate=0, max_output_tokens=100, max_iters=0,
    )
    assert llm.calls, "the judge WAS asked"
    assert r.checks["plan_liveness"] == CheckStatus.UNPARSEABLE
    assert r.guard_status != "checked", "a guard that could not judge must not read as checked"
    hit = next(v for v in r.violations if v.kind == PLAN_CONFLICT_KIND)
    assert hit.confirmed is None, "still advisory — a mute judge may not block either"
    assert r.resolved is True


@pytest.mark.asyncio
async def test_CONTROL_a_judge_that_ANSWERS_is_checked_not_unparseable(monkeypatch):
    """The counterweight: without it, "always UNPARSEABLE" satisfies the test above and the
    check goes permanently amber on every book that has a working critic."""
    (_t, r, _), _llm = await _reflect_judged(
        monkeypatch, [{"entity_id": DAO, "violated": False, "why": "chỉ là giấc mơ"}])
    assert r.checks["plan_liveness"] == CheckStatus.CHECKED


def test_judge_plan_conflicts_reports_whether_it_actually_judged():
    """The signature carries the fact, because the candidates cannot: an unjudged candidate and
    a judge-declined one are both `confirmed=None`."""
    import inspect
    from app.engine.canon_check import judge_plan_conflicts
    ret = str(inspect.signature(judge_plan_conflicts).return_annotation)
    assert "tuple" in ret and "bool" in ret, ret


# ── the judge is a different ROW; is it a different MODEL? ────────────────────────────────

@pytest.mark.asyncio
async def test_an_UNVERIFIED_judge_identity_leaves_it_advisory(monkeypatch):
    """The distinct-critic rule was fixed to compare the RESOLVED PROVIDER MODEL, because five
    `user_model_id` rows on the dev box are one model. The router adopted that; the path that
    decides whether a conflict BLOCKS A PUBLISH did not, and re-derived distinctness from the
    refs — a comparison that cannot see two rows collapsing to one model.

    `identity_verified=False` means provider-registry could not tell us which model either ref
    is. That is not "they are the same" and not "they are different": it is unknown, and an
    unknown must not be allowed to certify. Same direction the file already takes for a judge
    that is down — a judge we cannot vouch for may not BLOCK a publish."""
    (_t, r, _), llm = await _reflect_judged(
        monkeypatch, [{"entity_id": DAO, "violated": True, "why": "cô ấy chết thật"}],
        identity_verified=False)
    hit = next(v for v in r.violations if v.kind == PLAN_CONFLICT_KIND)
    assert hit.confirmed is None, "an unverifiable judge must not promote a candidate to HARD"
    assert r.resolved is True, "advisory must not block publish"
    assert llm.calls == [], "and the judge must not even be asked — its verdict is unusable"


@pytest.mark.asyncio
async def test_a_VERIFIED_judge_identity_still_blocks(monkeypatch):
    """The control. Without it, "never promote" passes the test above and the blocking tier
    quietly stops existing — which is the exact failure this whole arc was written about."""
    (_t, r, _), llm = await _reflect_judged(
        monkeypatch, [{"entity_id": DAO, "violated": True, "why": "cô ấy chết thật"}],
        identity_verified=True)
    hit = next(v for v in r.violations if v.kind == PLAN_CONFLICT_KIND)
    assert hit.confirmed is True
    assert r.resolved is False
    assert llm.calls, "a verified-distinct judge IS asked"


@pytest.mark.asyncio
async def test_an_UNRESOLVED_identity_None_is_treated_as_usable(monkeypatch):
    """`None` is not `False`. It means the caller never resolved identity at all (an older
    path, or a worker that has no provider-registry client), and turning that into a silent
    downgrade would disable the blocking tier everywhere the signal is simply absent —
    the reverse false-green. Only an ATTEMPT that FAILED downgrades."""
    (_t, r, _), llm = await _reflect_judged(
        monkeypatch, [{"entity_id": DAO, "violated": True, "why": "cô ấy chết thật"}],
        identity_verified=None)
    hit = next(v for v in r.violations if v.kind == PLAN_CONFLICT_KIND)
    assert hit.confirmed is True
    assert r.resolved is False
    assert llm.calls
