"""Unit tests for judge_prose (parse tolerance, 4 dims, CC4 degrade)."""

from __future__ import annotations

import json
from types import SimpleNamespace

from loreweave_llm.errors import LLMError

from app.engine import critic
from app.engine.critic import map_rule_tokens, rule_token
from app.packer.profile import NEUTRAL, BookProfile


# ── tolerant parse ──

def test_parse_strips_fences():
    out = critic.parse_critique_json('```json\n{"coherence": 4}\n```')
    assert out == {"coherence": 4}

def test_parse_extracts_balanced_object_amid_prose():
    out = critic.parse_critique_json('Here is my verdict: {"pacing": 3} hope that helps')
    assert out == {"pacing": 3}

def test_parse_returns_none_on_garbage():
    assert critic.parse_critique_json("not json at all") is None
    assert critic.parse_critique_json("") is None


# ── normalize (score coercion + violation filter) ──

def test_normalize_coerces_scores_and_filters_violations():
    parsed = {
        "coherence": 4, "voice_match": "high", "pacing": 9, "canon_consistency": 3,
        "violations": [
            {"rule_id": "r1", "violated": True, "span": "x", "why": "contradicts"},
            {"violated": True},                  # no rule_id → dropped
            "not-a-dict",                        # malformed → dropped
            {"rule_id": "r2"},                   # minimal valid → kept
        ],
    }
    out = critic.normalize_critique(parsed)
    assert out["coherence"] == 4 and out["canon_consistency"] == 3
    assert out["voice_match"] is None            # non-int → None
    assert out["pacing"] is None                 # out of 0-5 range → None
    assert [v["rule_id"] for v in out["violations"]] == ["r1", "r2"]  # malformed filtered


def test_normalize_handles_none():
    out = critic.normalize_critique(None)
    assert out["coherence"] is None and out["violations"] == []


# ── de-bias prompt ──

def test_prompt_carries_source_language_no_english_default():
    sys_zh, _ = critic.build_critique_prompt("p", [], [], BookProfile(source_language="zh"))
    assert "'zh'" in sys_zh
    sys_auto, _ = critic.build_critique_prompt("p", [], [], NEUTRAL)
    assert "language with code" not in sys_auto  # auto → no forced language


# ── judge_prose (fake judge) ──

class FakeJudge:
    def __init__(self, *, content=None, status="completed", raises=False):
        self._content = content
        self._status = status
        self._raises = raises
        self.calls = []

    async def submit_and_wait(self, **kw):
        self.calls.append(kw)
        if self._raises:
            raise LLMError("gateway down")
        result = {"messages": [{"role": "assistant", "content": self._content}]} if self._content else {}
        return SimpleNamespace(status=self._status, result=result)


async def test_judge_prose_happy_returns_four_dims_and_violations():
    content = json.dumps({"coherence": 5, "voice_match": 4, "pacing": 3, "canon_consistency": 2,
                          "violations": [{"rule_id": "r1", "violated": True, "span": "s", "why": "w"}]})
    judge = FakeJudge(content=content)
    out = await critic.judge_prose(judge, user_id="u", model_source="user_model", model_ref="m",
                                   passage="prose", active_rules=[{"rule_id": "r1", "text": "no magic"}],
                                   present_facts=[], profile=NEUTRAL)
    assert out["coherence"] == 5 and out["canon_consistency"] == 2
    assert out["violations"][0]["rule_id"] == "r1"
    # the critic ran with the distinct critic ref
    assert judge.calls[0]["model_ref"] == "m" and judge.calls[0]["operation"] == "chat"
    # disables hidden thinking via the WORKING knob (reasoning_effort), not just
    # the no-op chat_template_kwargs — else reasoning_tokens burn the JSON budget.
    assert judge.calls[0]["input"]["reasoning_effort"] == "none"


async def test_judge_prose_cc4_degrades_on_llm_error():
    judge = FakeJudge(raises=True)
    out = await critic.judge_prose(judge, user_id="u", model_source="user_model", model_ref="m",
                                   passage="p", active_rules=[], present_facts=[], profile=NEUTRAL)
    assert out["error"] == "critic_unavailable" and out["violations"] == []
    assert all(out[d] is None for d in ("coherence", "voice_match", "pacing", "canon_consistency"))


async def test_judge_prose_non_completed_status_degrades():
    judge = FakeJudge(content="{}", status="failed")
    out = await critic.judge_prose(judge, user_id="u", model_source="user_model", model_ref="m",
                                   passage="p", active_rules=[], present_facts=[], profile=NEUTRAL)
    assert out["error"] == "critic_failed"


async def test_judge_prose_malformed_json_yields_empty_not_crash():
    judge = FakeJudge(content="the model rambled without JSON")
    out = await critic.judge_prose(judge, user_id="u", model_source="user_model", model_ref="m",
                                   passage="p", active_rules=[], present_facts=[], profile=NEUTRAL)
    assert out["violations"] == [] and out["coherence"] is None  # degraded, not raised


# ── per-rule attribution (D-QC5-PROSE-JUDGE-VERDICT-NOT-PER-RULE, 2026-08-12) ──

_RULES = [
    {"rule_id": "0331a53f-0000-0000-0000-000000000001", "text": "rule one"},
    {"rule_id": "6e153c35-0000-0000-0000-000000000002", "text": "rule two"},
]


def test_rules_are_shown_under_short_labels_not_their_uuids():
    """🔴 REGRESSION. The prompt used to render `- [<uuid>] text` and ask the judge to echo
    the uuid back per verdict. Measured on QC-5: given one rule the passage contradicts and
    one it plainly confirms, the judge marked BOTH violated and copied the same `why` to each.
    A 36-char uuid is not a label a model carries accurately through a long passage.
    """
    _, user = critic.build_critique_prompt("passage", _RULES, [], NEUTRAL)
    assert "[R1]" in user and "[R2]" in user
    for r in _RULES:
        assert r["rule_id"] not in user, (
            "a rule uuid is back in the prompt — the judge will be asked to echo it again"
        )


def test_a_label_is_mapped_back_to_its_real_rule_id():
    out = critic.map_rule_tokens(
        [{"rule_id": "R2", "violated": True, "span": "s", "why": "w"}], _RULES)
    assert [v["rule_id"] for v in out] == [_RULES[1]["rule_id"]]


def test_an_unmappable_label_is_DROPPED_rather_than_passed_through():
    """The half that makes this a fix and not a rename.

    The old shape accepted whatever string landed in `rule_id`, so a copied or invented id
    became a verdict about a real rule the judge was never asked about. A verdict nobody can
    attribute is not evidence; it is noise with a citation.
    """
    out = critic.map_rule_tokens([
        {"rule_id": "R9", "violated": True, "span": "", "why": "off the end"},
        {"rule_id": "totally-made-up", "violated": True, "span": "", "why": "invented"},
        {"rule_id": "R1", "violated": True, "span": "", "why": "real"},
    ], _RULES)
    assert [v["why"] for v in out] == ["real"]


def test_a_judge_that_echoes_the_real_id_is_still_attributable():
    """Tolerance, not laxity: some judges echo the id anyway, and that verdict CAN be
    attributed — dropping it would lose a true finding to a formatting preference."""
    out = critic.map_rule_tokens(
        [{"rule_id": _RULES[0]["rule_id"], "violated": True, "span": "", "why": "w"}], _RULES)
    assert [v["rule_id"] for v in out] == [_RULES[0]["rule_id"]]


def test_labels_are_one_based():
    assert (critic.rule_token(0), critic.rule_token(1)) == ("R1", "R2")


async def test_a_dropped_verdict_is_visible_ON_THE_CRITIQUE_not_only_in_a_log():
    """C3 — "found nothing" and "found seven and could not attribute any" must not look alike.

    `map_rule_tokens` drops an unattributable verdict, which is correct. Until now the ONLY
    detector was a WARNING line, so every consumer of the critique — the D5 Run Report, the
    quality report, the author — saw `violations: []` for both cases. Measured on the
    acceptance book: 7 raw verdicts, 7 dropped, `rules=0`, beside `canon_consistency=1`.
    """
    judge = FakeJudge(content=json.dumps({
        "coherence": 4, "voice_match": 1, "pacing": 4, "canon_consistency": 1,
        "violations": [
            {"rule_id": "ADDRESS-FORM CONVENTION", "violated": True, "why": "not a rule id"},
            {"rule_id": "ADDRESS-FORM CONVENTION", "violated": True, "why": "nor is this"},
        ],
    }))
    crit = await critic.judge_prose(
        judge, user_id="u", model_source="user_model", model_ref="m",
        passage="prose", active_rules=[], present_facts=["a canon bible"], profile=NEUTRAL,
    )
    assert crit["violations"] == []
    assert crit["violations_raw_count"] == 2
    assert crit["violations_dropped"] == 2, (
        "a silent drop is indistinguishable from a clean passage — that is the bug"
    )


def test_the_dropped_LABELS_reach_the_envelope_not_only_a_log_line():
    """🔴 QC-5 C10. `violations_dropped` says HOW MANY were unattributable; it cannot say WHY,
    and the two causes need opposite responses.

    Measured 2026-08-21 on a live run: 2 of 2 dropped with **six** active rules, labels
    `['QUY UOC XUNG HO', ...]` — the book's six rules are character facts and none is a
    naming-convention rule, so the judge invented a category and the drop was CORRECT. The
    other cause (`rules=0`, C3's chapter 12) is a rules-plumbing bug. `dropped=2` alone reads
    identically for both, and diagnosing it required a container that happened to still be
    running.
    """
    active = [{"rule_id": "real-rule-1", "text": "X is the cousin of Y"}]
    raw = [
        {"rule_id": "QUY UOC XUNG HO", "why": "invented category"},
        {"rule_id": rule_token(0), "why": "a real one, attributable"},
    ]
    crit = {"violations": list(raw)}
    kept = map_rule_tokens(raw, active)
    assert len(kept) == 1, "fixture: exactly one verdict must be attributable"

    crit["violations"] = kept
    dropped = len(raw) - len(kept)
    labels = critic.unattributable_labels(raw, active)

    assert labels == ["QUY UOC XUNG HO"], (
        f"the unattributable label must reach the caller, got {labels} — without it "
        "'the judge invented a rule' and 'the mapper is broken' are the same observation")
    assert dropped == 1


def test_a_LABEL_MATCHING_fallback_is_NOT_added_because_it_re_opens_a_fixed_defect():
    """A guard against the obvious 'fix'. The judge returned a rule label instead of a token,
    so it is tempting to attribute by label. That would attach a FABRICATED rule to a real one
    — `D-QC5-PROSE-JUDGE-VERDICT-NOT-PER-RULE`, fixed 2026-08-12, whose whole finding was a
    verdict keyed to a rule its `why` did not belong to.

    So this pins the refusal: a label that is not a token and not a real id stays dropped, even
    when it is a plausible-looking near-miss of a real rule's text.
    """
    active = [{"rule_id": "real-rule-1", "text": "Lam Trach is the cousin of Lam Uyen"}]
    for invented in ("Lam Trach is the cousin of Lam Uyen",   # the rule's own TEXT
                     "naming convention", "R99", "rule-1"):
        assert map_rule_tokens([{"rule_id": invented, "why": "x"}], active) == [], (
            f"{invented!r} was attributed — a verdict the judge could not key to a token must "
            "stay dropped; guessing re-opens D-QC5-PROSE-JUDGE-VERDICT-NOT-PER-RULE")


def test_the_prompt_gives_out_of_rule_findings_a_CHANNEL_instead_of_a_rule_to_invent():
    """🔴 QC-5 C12. Replaying the stored judge request (job 01a02149-…) reproduced the live
    failure 3/3: `rule_id` "QUY UOC XUNG HO", whose `why` translates to "uses the pronoun 'anh'
    as the narrative person instead of conventional pronouns". A REAL craft finding —
    `voice_match` scored 2 in every arm — with nowhere to go but `violations[]`, which is keyed
    to a listed rule. So the judge invented one and `map_rule_tokens` correctly dropped it.

    Three runs per arm on that exact request:
        control                    invented [2, 6, 6]  notes [0, 0, 0]
        "do not invent a rule"     invented [0, 0, 0]  notes [0, 0, 0]
        a craft_notes CHANNEL      invented [0, 0, 0]  notes [2, 2, 2]

    Both stop the invention; only the channel keeps the finding. This pins the channel's
    presence in the prompt AND its schema line, because a prompt that asks for a field the
    response schema never mentions is a prompt asking for nothing.
    """
    system, _user = critic.build_critique_prompt(
        "passage", [{"rule_id": "r1", "text": "X is the cousin of Y"}], [], NEUTRAL)
    # ⚠️ Two assertions, deliberately, and the FIRST one is why. Asserting only
    # `"craft_notes" in system` passes on the schema line alone, so deleting the whole prose
    # instruction left this test green — bite 47 caught exactly that. The prose and the schema
    # are separate failure modes and each needs its own assertion.
    assert "never invent a rule id" in system, (
        "the INSTRUCTION is gone: the judge has no channel for a finding no listed rule covers, "
        "so it will invent a rule id to carry one — measured 2-6 invented ids per run")
    assert "is NOT a violation" in " ".join(system.split()), (
        "the clause no longer tells the judge that an out-of-rule finding is not a violation")
    assert '"craft_notes":[{"note":str,"span":str}]' in system, (
        "the channel is described in prose but missing from the JSON schema line — the judge "
        "is being asked to fill a field the contract never declares")


def test_craft_notes_SURVIVE_normalisation_or_the_channel_writes_to_nowhere():
    """A judge told to write to a field the normaliser drops is a judge told nothing: the
    finding would vanish exactly as it did when `map_rule_tokens` discarded the invented rule.
    Bounded, because the note text is model output on an author-facing envelope.
    """
    out = critic.normalize_critique({
        "coherence": 5, "voice_match": 2, "pacing": 4, "canon_consistency": 5,
        "violations": [],
        "craft_notes": [
            {"note": "narrative pronoun breaks the work's convention", "span": "…anh…"},
            {"note": "   ", "span": "dropped: no note text"},
            {"note": "x" * 900, "span": "y" * 900},
        ],
    })
    notes = out["craft_notes"]
    assert len(notes) == 2, f"the blank note must be filtered, got {notes}"
    assert notes[0]["note"].startswith("narrative pronoun")
    assert len(notes[1]["note"]) == 400 and len(notes[1]["span"]) == 200, (
        "model output on an author-facing envelope must be bounded")


# ── D-QUALITY-REPORT-CANON-UNANCHORED (T46l) — the degrade shape must not drift ──────────
#
# `normalize_critique` gained `craft_notes` with the C11 channel fix; `quality_report`'s
# `_empty_critic()` did not. A consumer reading `critic["craft_notes"]` therefore worked on a
# healthy judge and raised KeyError the moment one degraded — precisely the case the degrade
# path exists to survive. Comparing the two key SETS (rather than asserting the literal key)
# is what stops the next added field repeating it.


async def test_the_degrade_critic_shape_carries_every_key_the_success_shape_does():
    """⚠️ REWRITTEN 2026-08-21. This compared `_empty_critic()` against
    `normalize_critique(...)` — and `normalize_critique` is NOT the success shape a consumer
    sees. `judge_prose` stamps four more keys AFTER it: `violations_dropped`,
    `violations_raw_count`, `violations_dropped_labels` and `active_rule_count`. All four
    were missing from the degrade shape while this test passed, so the exact bug the function
    documents itself as preventing was live the whole time.

    The old comparison was green by construction: it was validated on `craft_notes`, the one
    key that motivated it, and `craft_notes` happens to be added by `normalize_critique`.
    Driving the REAL `judge_prose` is what makes the assertion mean what it says.
    """
    from app.engine.quality_report import _empty_critic

    judge = FakeJudge(content=json.dumps({
        "coherence": 4, "voice_match": 4, "pacing": 4, "canon_consistency": 5,
        "violations": [{"rule_id": "r1", "violated": True, "span": "s", "why": "w"}],
        "craft_notes": [{"note": "n", "span": "s"}],
    }))
    success = await critic.judge_prose(
        judge, user_id="u", model_source="user_model", model_ref="m", passage="prose",
        active_rules=[{"rule_id": "r1", "text": "no magic"}], present_facts=[], profile=NEUTRAL,
    )
    degraded = _empty_critic()
    missing = sorted(set(success) - set(degraded))
    assert not missing, (
        f"the degrade shape is missing {missing} — a consumer that reads those on a healthy "
        f"judge raises KeyError the moment one degrades. Add them to `_empty_critic`."
    )


async def test_the_success_shape_under_test_is_RICHER_than_normalize_critique():
    """The control for the rewrite above. If `judge_prose` ever stopped adding keys of its own,
    the new comparison would silently collapse back into the old weaker one and pass for the
    old wrong reason. Pin the difference itself.
    """
    judge = FakeJudge(content=json.dumps({
        "coherence": 4, "voice_match": 4, "pacing": 4, "canon_consistency": 5, "violations": [],
    }))
    success = await critic.judge_prose(
        judge, user_id="u", model_source="user_model", model_ref="m", passage="prose",
        active_rules=[{"rule_id": "r1", "text": "no magic"}], present_facts=[], profile=NEUTRAL,
    )
    normalised = critic.normalize_critique(
        {"coherence": 4, "voice_match": 4, "pacing": 4, "canon_consistency": 5, "violations": []}
    )
    added = set(success) - set(normalised)
    assert "active_rule_count" in added, (
        f"`judge_prose` no longer stamps `active_rule_count`; the second seam "
        f"(`quality_report`, which passes `active_rules=[]` on purpose) goes back to being "
        f"indistinguishable from the C3 attribution failure. added={sorted(added)}"
    )


def test_the_degrade_shape_ALSO_marks_itself_as_an_error():
    """The control. Making the shapes match by widening `_empty_critic` must not make a
    degraded verdict indistinguishable from a real one — `error` is how a reader tells."""
    from app.engine.quality_report import _empty_critic

    degraded = _empty_critic()
    assert degraded["error"], "a degraded critic must say so"
    success = critic.normalize_critique(
        {"coherence": 4, "voice_match": 4, "pacing": 4, "canon_consistency": 5,
         "violations": [], "craft_notes": []}
    )
    assert "error" not in success, "a healthy verdict must not carry an error marker"
