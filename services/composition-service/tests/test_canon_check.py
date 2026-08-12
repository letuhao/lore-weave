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
    judge_role_attribution, roles_at_position, roles_in_draft,
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


# ── T36 · role attribution (D-CANON-CHECK-BLIND-TO-ROLE) ──────────────
#
# The guard used to consume only `entities` + `status`; the snapshot's
# `relations` reached no prompt and no rule. These pin the question it can now
# ask, and the one it must NOT answer on its own.


def _role_snap(*relations, entities=()):
    return {"at_order": 5_000_000, "entities": list(entities),
            "relations": list(relations)}


def _rel(subject_id, subject_name, predicate, object_id, object_name,
         valid_from_ordinal=1_000_000, valid_to_ordinal=None):
    return {"subject_id": subject_id, "subject_name": subject_name,
            "predicate": predicate, "object_id": object_id,
            "object_name": object_name,
            "valid_from_ordinal": valid_from_ordinal,
            "valid_to_ordinal": valid_to_ordinal}


def test_roles_at_position_projects_the_snapshot_relations():
    snap = _role_snap(_rel("e-kai", "Kai", "serves", "e-bob", "Bob"))
    roles = roles_at_position(snap)
    assert len(roles) == 1
    assert roles[0]["subject_name"] == "Kai" and roles[0]["object_name"] == "Bob"
    # T36 — the interval that answered rides along, so a `why` can place the role.
    assert roles[0]["valid_from_ordinal"] == 1_000_000


def test_roles_at_position_tolerates_a_malformed_payload():
    """The snapshot crosses a service boundary, so junk is input, not an error."""
    assert roles_at_position(None) == []
    assert roles_at_position({}) == []
    assert roles_at_position({"relations": None}) == []
    # a row missing an endpoint NAME cannot be judged or matched — dropped.
    assert roles_at_position(_role_snap(
        {"subject_id": "e-kai", "predicate": "serves", "object_id": "e-bob"})) == []
    assert roles_at_position({"relations": ["not-a-dict"]}) == []


def test_roles_in_draft_selects_only_roles_this_passage_could_contradict():
    snap = _role_snap(
        _rel("e-kai", "Kai", "serves", "e-bob", "Bob"),
        _rel("e-zed", "Zed", "rules", "e-far", "Farland"),
    )
    hits = roles_in_draft("Kai knelt before the throne.", snap)
    assert len(hits) == 1 and hits[0]["subject_name"] == "Kai"


def test_roles_in_draft_matches_on_EITHER_endpoint():
    """Misattribution reads both ways — a passage naming only the role's OBJECT
    can still give that role to the wrong character."""
    snap = _role_snap(_rel("e-kai", "Kai", "serves", "e-bob", "Bob"))
    hits = roles_in_draft("Bob's champion stepped forward.", snap)
    assert len(hits) == 1 and hits[0]["object_name"] == "Bob"


def test_roles_in_draft_empty_without_a_snapshot():
    assert roles_in_draft("Kai knelt.", None) == []
    assert roles_in_draft("", _role_snap(_rel("e-kai", "Kai", "serves", "e-bob", "Bob"))) == []


@pytest.mark.asyncio
async def test_role_judge_affirms_a_misattribution():
    # Keyed by the per-STATEMENT token, not a character id. MEASURED: given a
    # subject entity id, a real judge returned the id of the character it was
    # ACCUSING — which also appeared as another role's subject, so the verdict
    # attached to the wrong relationship. Correct-sounding, pointing false.
    judge = _FakeJudge('{"verdicts":[{"entity_id":"role_0","violated":true,'
                       '"why":"the passage has Zed in Kai\'s role"}]}')
    roles = [_rel("e-kai", "Kai", "serves", "e-bob", "Bob") | {"span": "s", "matched": "Kai"}]
    out = await judge_role_attribution(
        judge, user_id="u", model_source="user_model", model_ref="m",
        draft="Zed served Bob loyally.", roles=roles)
    assert len(out) == 1
    assert out[0].kind == "role_contradiction"
    assert out[0].entity_id == "e-kai"
    assert out[0].confirmed is True
    assert out[0].source == "llm_judge"
    # NOT "gone" — this candidate says nothing about liveness.
    assert out[0].status == "role"
    assert "Kai" in out[0].why
    # WHICH relationship — a subject usually holds several roles at a position,
    # so the entity id alone does not identify the finding.
    assert out[0].predicate == "serves"
    assert out[0].object_name == "Bob"


@pytest.mark.asyncio
async def test_role_judge_reports_nothing_when_it_does_not_affirm():
    """The inverse of `judge_canon`'s convention, on purpose: the symbolic layer
    established only RELEVANCE, so an unconfirmed role is not a finding."""
    judge = _FakeJudge('{"verdicts":[{"entity_id":"role_0","violated":false,"why":"consistent"}]}')
    roles = [_rel("e-kai", "Kai", "serves", "e-bob", "Bob") | {"span": "s", "matched": "Kai"}]
    out = await judge_role_attribution(
        judge, user_id="u", model_source="user_model", model_ref="m",
        draft="Kai served Bob.", roles=roles)
    assert out == []


@pytest.mark.asyncio
async def test_role_judge_invents_nothing_when_it_fails():
    """CC4 — a judge that is down must not block a generate, and must not
    manufacture a violation either. Both failure shapes yield no findings."""
    from loreweave_llm.errors import LLMError
    roles = [_rel("e-kai", "Kai", "serves", "e-bob", "Bob") | {"span": "s", "matched": "Kai"}]
    kwargs = dict(user_id="u", model_source="user_model", model_ref="m",
                  draft="Zed served Bob.", roles=roles)
    assert await judge_role_attribution(_FakeJudge(raise_exc=LLMError("down")), **kwargs) == []
    assert await judge_role_attribution(_FakeJudge("{}", status="failed"), **kwargs) == []
    # completed-but-useless (the truncated-reply case judge_plan_conflicts records)
    assert await judge_role_attribution(_FakeJudge("no json here"), **kwargs) == []


@pytest.mark.asyncio
async def test_check_canon_does_not_run_the_role_check_by_default():
    """THE SPEND DEFAULT. Roles in force are common, so an always-on role check
    adds a judge call to most scenes. `role_check` defaults False and the caller
    opts in — a token-spending toggle fails closed."""
    judge = _FakeJudge('{"verdicts":[{"entity_id":"e-kai","violated":true,"why":"x"}]}')
    snap = _role_snap(_rel("e-kai", "Kai", "serves", "e-bob", "Bob"))
    out = await check_canon("Zed served Bob.", snap, judge=judge,
                            user_id="u", model_source="user_model", model_ref="m")
    assert out == []
    assert judge.calls == 0, "no judge call may happen with the role check off"


@pytest.mark.asyncio
async def test_check_canon_runs_the_role_check_when_enabled():
    judge = _FakeJudge('{"verdicts":[{"entity_id":"role_0","violated":true,"why":"misattributed"}]}')
    snap = _role_snap(_rel("e-kai", "Kai", "serves", "e-bob", "Bob"))
    out = await check_canon("Zed served Bob.", snap, judge=judge, user_id="u",
                            model_source="user_model", model_ref="m", role_check=True)
    assert [c.kind for c in out] == ["role_contradiction"]
    assert judge.calls == 1


@pytest.mark.asyncio
async def test_role_check_never_suppresses_a_gone_cast_finding():
    """The two checks are additive. A scene with both must report both, or
    turning the role check on would silently weaken the gate that already ships."""
    # The gone-cast judge keys on the ENTITY id; the role judge on the
    # per-statement token. Both verdicts in one reply, since one fake serves both.
    judge = _FakeJudge('{"verdicts":[{"entity_id":"e-kai","violated":true,"why":"gone"},'
                       '{"entity_id":"role_0","violated":true,"why":"role"}]}')
    snap = {"at_order": 5_000_000,
            "entities": [_ent("e-kai", "Kai", "gone")],
            "relations": [_rel("e-kai", "Kai", "serves", "e-bob", "Bob")]}
    out = await check_canon("Kai served Bob.", snap, judge=judge, user_id="u",
                            model_source="user_model", model_ref="m", role_check=True)
    assert {c.kind for c in out} == {"gone_entity_present", "role_contradiction"}


@pytest.mark.asyncio
async def test_role_check_needs_a_judge_and_stays_silent_without_one():
    """Symbolic relevance is not evidence — with no distinct judge configured
    there is nothing to report, and nothing may be reported."""
    snap = _role_snap(_rel("e-kai", "Kai", "serves", "e-bob", "Bob"))
    out = await check_canon("Zed served Bob.", snap, judge=None, user_id="u",
                            model_source="", model_ref="", role_check=True)
    assert out == []


def test_roles_in_draft_ranks_by_how_strongly_the_passage_implicates_the_role():
    """MEASURED, and it corrected a first attempt that had it backwards. On the
    dogfood book at ch.5 the relevance filter selected 20 of 24 roles, so the
    CAP decides what the judge sees. Ranking on both-endpoints-named alone
    buried the misattribution case — in a misattribution the passage has
    REPLACED the role's holder, so the true holder is exactly the absent name
    and only the OBJECT appears."""
    snap = _role_snap(
        _rel("e-a", "Alpha", "owns", "e-d", "Delta"),        # tier 2: subject only
        _rel("e-c", "Gamma", "betrayed", "e-a", "Alpha"),    # tier 1: OBJECT only
        _rel("e-a", "Alpha", "knows", "e-b", "Beta"),        # tier 0: both
    )
    hits = roles_in_draft("Alpha spoke to Beta. Someone else had betrayed her.", snap)
    assert [h["predicate"] for h in hits] == ["knows", "betrayed", "owns"]
    assert [h["tier"] for h in hits] == [0, 1, 2]


def test_roles_in_draft_cap_keeps_the_misattribution_shape_over_the_weakest():
    """The acceptance case must survive truncation: a role whose holder is
    ABSENT outranks one whose object is merely off-scene."""
    snap = _role_snap(
        _rel("e-a", "Alpha", "owns", "e-d", "Delta"),        # tier 2
        _rel("e-c", "Gamma", "betrayed", "e-a", "Alpha"),    # tier 1
    )
    hits = roles_in_draft("Alpha stood alone; she had been betrayed.", snap, limit=1)
    assert [h["predicate"] for h in hits] == ["betrayed"]


def test_roles_in_draft_equal_tier_keeps_snapshot_order():
    """Stable sort — reproducible for a given snapshot, not dict-iteration luck."""
    snap = _role_snap(
        _rel("e-a", "Alpha", "knows", "e-b", "Beta"),
        _rel("e-b", "Beta", "trusts", "e-a", "Alpha"),
    )
    hits = roles_in_draft("Alpha and Beta spoke.", snap)
    assert [h["tier"] for h in hits] == [0, 0]
    assert [h["predicate"] for h in hits] == ["knows", "trusts"]


# ── D-QC5-ROLE-JUDGE-PRECISION — the rules the live run forced ──────────
#
# The first full-flow run returned 8 affirmed contradictions on a chapter whose
# canon attribution is CORRECT. These pin the four exemptions that answers,
# because a prompt rule with no test is a rule that gets edited away.
#
# WHAT THESE DO NOT PROVE (NV-1, and /review-impl called it): they assert SUBSTRINGS of a
# prompt. They red on a harmless rewording and they PASS on a rule that does not work —
# and the live evidence says these rules do not work (8 -> 7, then 0/4/12 across batch
# sizes on byte-identical input). Presence is all they check; effectiveness is measured in
# `docs/measurements/2026-08-11-qc5-full-flow-capture.md` and cannot be a unit test,
# because the thing under test is a model's judgement. Read them as "the rule is still in
# the prompt", never as "the judge obeys it".


def _role_system_prompt() -> str:
    from app.engine.canon_check import _build_role_judge_messages
    roles = [_rel("e-a", "Alpha", "cousin_of", "e-b", "Beta")]
    return _build_role_judge_messages("Alpha spoke to Beta.", roles, "auto")[0]


def test_role_prompt_exempts_a_passage_that_CONFIRMS_the_relationship():
    """The worst of the 8: the judge said "Lam Trach reveals his betrayal to Lam
    Uyen in the passage, not someone else" and returned violated=true. That is
    canon being confirmed. Agreement is the opposite of a contradiction."""
    p = _role_system_prompt().lower()
    assert "confirm" in p
    assert "agreement is the opposite" in p


def test_role_prompt_exempts_conflict_from_ending_a_relationship():
    """Three of the 8 reasoned "X betrayed Y, therefore their kinship is
    contradicted". Betraying your cousin does not stop them being your cousin."""
    p = _role_system_prompt().lower()
    assert "betrayal" in p or "betray" in p
    assert "does not end" in p or "does not\nend" in p


def test_role_prompt_exempts_movement():
    """One of the 8 flagged `located_at` because the scene happens elsewhere.
    A character being somewhere else later is movement, not a contradiction."""
    p = _role_system_prompt().lower()
    assert "moving is not a contradiction" in p


def test_role_prompt_asks_about_one_statement_and_prefers_false():
    """Two of the 8 answered about a DIFFERENT relation than the one asked
    (predicate married_to, reason about siblings). And the asymmetry is stated:
    on correct prose a false alarm costs the author more than a miss."""
    p = _role_system_prompt().lower()
    assert "that statement only" in p
    assert "prefer false when unsure" in p


# ── SET-3 — the ceiling and the per-book setting are ANDed ─────────────
#
# /review-impl HIGH: the first cut shipped this as a process-global env flag, which is
# the SET-1 abuse the standard names by example — a behaviour two authors could
# reasonably disagree about, made "the same for every user, invisible, and unchangeable
# without a redeploy". These pin the corrected shape at the seam that decides it.


@pytest.mark.asyncio
async def test_role_check_requires_BOTH_the_ceiling_and_the_book_setting():
    """effective = AND(deploy ceiling, per-book setting). Neither alone runs it."""
    snap = _role_snap(_rel("e-kai", "Kai", "serves", "e-bob", "Bob"))
    for role_check in (False,):
        judge = _FakeJudge('{"verdicts":[{"entity_id":"role_0","violated":true,"why":"x"}]}')
        out = await check_canon("Zed served Bob.", snap, judge=judge, user_id="u",
                                model_source="user_model", model_ref="m",
                                role_check=role_check)
        assert out == [] and judge.calls == 0, (
            "a false AND-result must not reach the judge at all")


@pytest.mark.asyncio
async def test_role_check_runs_when_both_halves_are_true():
    judge = _FakeJudge('{"verdicts":[{"entity_id":"role_0","violated":true,"why":"y"}]}')
    snap = _role_snap(_rel("e-kai", "Kai", "serves", "e-bob", "Bob"))
    out = await check_canon("Zed served Bob.", snap, judge=judge, user_id="u",
                            model_source="user_model", model_ref="m", role_check=True)
    assert [c.kind for c in out] == ["role_contradiction"]


def test_the_ceiling_setting_is_named_as_a_ceiling_and_defaults_open():
    """SET-3: the env half is the deploy MAX, never the switch. A ceiling that
    shipped CLOSED would make the per-book setting a silent no-op everywhere —
    which is the 'disabled by deployment' case SET-3 says must be visible, not
    the default posture. The SPEND default lives on the per-book key instead."""
    from app.config import Settings
    fields = Settings.model_fields
    assert "authoring_canon_role_check_ceiling" in fields
    assert fields["authoring_canon_role_check_ceiling"].default is True
    assert "authoring_canon_role_check_enabled" not in fields, (
        "the old global switch must be gone, not merely unused")


# ── the role axis must be able to say "could not verify" (2026-08-12) ──

@pytest.mark.asyncio
async def test_an_empty_judge_completion_is_reported_not_swallowed():
    """🔴 REGRESSION, found by a live acceptance run (job 019ff401).

    Every failure path in `judge_role_attribution` returns `[]` — the SAME value a clean
    check returns. The live run sent 20 roles to the judge, got `tokens_used=0` and an empty
    completion, and the canon envelope carried `status: checked`, `violations: []`,
    `resolved: true`. An author reads that as canon-clean. The WARNING was in the log, and
    the log is not the verdict.
    """
    seen: list[str] = []
    kwargs = dict(user_id="u", model_source="s", model_ref="m",
                  draft="Zed served Bob.", roles=[{"subject_id": "a", "predicate": "p",
                                                   "object_id": "b", "subject_name": "Zed",
                                                   "object_name": "Bob"}])
    out = await judge_role_attribution(
        _FakeJudge("no json here"), on_degraded=seen.append, **kwargs)
    assert out == [], "the degrade contract still returns no findings"
    assert seen == ["no_verdicts"], (
        f"got {seen!r} — a judge that returned nothing must SAY so; otherwise the caller "
        "cannot tell it from a clean check"
    )


@pytest.mark.asyncio
async def test_an_unreachable_judge_is_reported_too():
    from loreweave_llm.errors import LLMError as _LLMError
    seen: list[str] = []
    kwargs = dict(user_id="u", model_source="s", model_ref="m",
                  draft="Zed served Bob.", roles=[{"subject_id": "a", "predicate": "p",
                                                   "object_id": "b", "subject_name": "Zed",
                                                   "object_name": "Bob"}])
    await judge_role_attribution(
        _FakeJudge(raise_exc=_LLMError("down")), on_degraded=seen.append, **kwargs)
    assert seen == ["llm_error"]


@pytest.mark.asyncio
async def test_a_judge_that_answers_reports_NOTHING_on_the_degrade_channel():
    """The negative control. Without it, a callback fired unconditionally would pass the two
    tests above while marking every healthy run as could-not-verify — turning the new field
    into permanent amber, which is the failure mode its own comment warns about."""
    seen: list[str] = []
    judge = _FakeJudge('{"verdicts":[{"entity_id":"role_0","violated":false,"why":"ok"}]}')
    await judge_role_attribution(
        judge, user_id="u", model_source="s", model_ref="m",
        draft="Zed served Bob.",
        roles=[{"subject_id": "a", "predicate": "p", "object_id": "b",
                "subject_name": "Zed", "object_name": "Bob"}],
        on_degraded=seen.append)
    assert seen == [], f"a healthy judge reported {seen!r} on the degrade channel"
