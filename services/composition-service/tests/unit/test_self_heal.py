"""Unit tests for the Phase-2 self-heal orchestrator (engine/self_heal.py).

Focus: the load-bearing fuzzy LOCATE (the judge abbreviates/re-spaces spans), the
tolerant findings parse, and the orchestration invariants — splice correctness,
and the SKIP guards (not-located / overlap / runaway-expansion) that keep the pass
advisory (original prose preserved).
"""

import json
from types import SimpleNamespace

from app.engine import self_heal
from app.engine.self_heal import (
    EditProposal,
    Finding,
    apply_self_heal_edits,
    build_judge_messages,
    code_mechanical_edits,
    locate_span,
    parse_findings,
    propose_self_heal,
    run_self_heal,
    code_pronoun_findings,
    _judge_vote,
    _snap_to_sentence,
    _verify,
    _verify_vote,
)

# async tests are collected via pytest.ini asyncio auto-mode.


# ── locate_span (the fuzzy match — make-or-break) ──

def test_locate_exact():
    assert locate_span("hello world", "a hello world b") == (2, 13)


def test_locate_whitespace_flexible():
    text = "a hello  world b"   # double space the judge didn't reproduce
    s, e = locate_span("hello world", text)
    assert text[s:e] == "hello  world"


def test_locate_ellipsis_spans_the_gap():
    text = "the cat sat quietly on the mat here"
    s, e = locate_span("the cat … on the mat", text)
    assert text[s:e] == "the cat sat quietly on the mat"


def test_locate_shingle_fallback():
    text = "noise the quick brown fox jumps over"
    # leading word absent → no exact/ws/ellipsis anchor → 5-word shingle rescues it
    s, e = locate_span("absent the quick brown fox jumps", text)
    assert text[s:e] == "the quick brown fox jumps"


def test_locate_miss_returns_none():
    assert locate_span("completely unrelated phrase here", "some other text entirely") is None
    assert locate_span("   ", "anything") is None


# ── parse_findings (tolerant) ──

def test_parse_findings_drops_spanless_and_garbage():
    content = ('noise before ['
               '{"type":"motif","span":"cold wind","issue":"i","fix":"f"},'
               '{"type":"x","issue":"no span"},'         # dropped — no usable span
               '"not a dict",'
               '{"type":"y","span":"  ","fix":"f"}'       # dropped — blank span
               '] noise after')
    out = parse_findings(content)
    assert [f.span for f in out] == ["cold wind"]
    assert parse_findings("no json here") == []
    assert parse_findings("") == []


# ── orchestration ──

class FakeHealLLM:
    """Routes by system prompt: the JUDGE ('demanding fiction editor') replays a queue
    of JSON arrays; the EDITOR ('co-writer') transforms the SELECTED PASSAGE via edit_fn."""

    def __init__(self, judge_responses, edit_fn):
        self._judge = list(judge_responses)
        self._edit_fn = edit_fn
        self.judge_calls = 0
        self.edit_calls = 0

    async def submit_and_wait(self, **kw):
        system = kw["input"]["messages"][0]["content"]
        user = kw["input"]["messages"][1]["content"]
        if "demanding fiction editor" in system:
            r = self._judge[min(self.judge_calls, len(self._judge) - 1)]
            self.judge_calls += 1
            return SimpleNamespace(status="completed", result={"messages": [{"content": r}]})
        # editor: pull the selection back out of the built prompt
        sel = user.split("SELECTED PASSAGE:\n", 1)[1].split("\n\nAuthor guidance:", 1)[0]
        self.edit_calls += 1
        return SimpleNamespace(status="completed",
                               result={"messages": [{"content": self._edit_fn(sel)}]})


def _findings_json(*spans):
    return json.dumps([{"type": "t", "span": s, "issue": "i", "fix": "f"} for s in spans])


async def test_run_self_heal_happy_splices_and_rejudges():
    chapter = "The sky was cold and the wind was cold here. She fell into the abyss without any cause now."
    judge = [_findings_json("cold and the wind was cold", "fell into the abyss without any cause"),
             "[]"]  # re-judge: clean
    llm = FakeHealLLM(judge, edit_fn=lambda sel: f"<<{len(sel)}>>")
    healed, rep = await run_self_heal(
        llm, user_id="u", model_source="user_model", model_ref="m",
        chapter=chapter, source_language="en")
    assert rep.located == 2 and rep.edits_applied == 2
    assert "cold and the wind was cold" not in healed
    assert "fell into the abyss without any cause" not in healed
    assert healed.count("<<") == 2  # both (sentence-snapped) spans spliced in
    assert rep.rejudge_before == 2 and rep.rejudge_after == 0


async def test_run_self_heal_skips_unlocatable():
    chapter = "A plain sentence with nothing special in it at all."
    llm = FakeHealLLM([_findings_json("this phrase is absent from the text")],
                      edit_fn=lambda sel: "X")
    healed, rep = await run_self_heal(
        llm, user_id="u", model_source="user_model", model_ref="m",
        chapter=chapter, source_language="en")
    assert healed == chapter and rep.edits_applied == 0
    assert rep.findings[0].skip_reason == "not_located"
    assert llm.edit_calls == 0


async def test_run_self_heal_rejects_runaway_expansion():
    chapter = "Tighten this short clause please now."
    big = "x" * 500  # >> max(40, len('short clause'))*1.6
    llm = FakeHealLLM([_findings_json("short clause")], edit_fn=lambda sel: big)
    healed, rep = await run_self_heal(
        llm, user_id="u", model_source="user_model", model_ref="m",
        chapter=chapter, source_language="en")
    assert healed == chapter and rep.edits_applied == 0
    assert rep.findings[0].skip_reason == "edit_expanded"


async def test_run_self_heal_skips_overlapping_spans():
    chapter = "alpha beta gamma delta epsilon end"
    # two findings whose located spans overlap → the second is skipped
    llm = FakeHealLLM([_findings_json("alpha beta gamma", "beta gamma delta")],
                      edit_fn=lambda sel: "[E]")
    healed, rep = await run_self_heal(
        llm, user_id="u", model_source="user_model", model_ref="m",
        chapter=chapter, source_language="en")
    assert rep.located == 2 and rep.edits_applied == 1
    assert any(f.skip_reason == "overlap" for f in rep.findings)


async def test_run_self_heal_degraded_rejudge_reports_none_not_zero():
    # the re-judge call returns empty (degraded) → rejudge_after must be None, NOT 0
    # (a false 0 would read as "chapter is now clean" — the real-run bug this guards).
    chapter = "The sky was cold and the wind was cold here today."
    llm = FakeHealLLM([_findings_json("cold and the wind was cold"), ""],  # 2nd judge: empty
                      edit_fn=lambda sel: "milder weather")
    healed, rep = await run_self_heal(
        llm, user_id="u", model_source="user_model", model_ref="m",
        chapter=chapter, source_language="en")
    assert rep.edits_applied == 1
    assert rep.rejudge_after is None  # degraded, not a false zero


async def test_run_self_heal_no_findings_is_noop():
    chapter = "Nothing to fix here."
    llm = FakeHealLLM(["[]"], edit_fn=lambda sel: "X")
    healed, rep = await run_self_heal(
        llm, user_id="u", model_source="user_model", model_ref="m",
        chapter=chapter, source_language="en")
    assert healed == chapter and rep.edits_applied == 0 and rep.rejudge_after is None
    assert llm.edit_calls == 0


# ── cheap-stack layers (canon grounding / vote / verify / mechanical) ──

_KW = dict(user_id="u", model_source="user_model", model_ref="m",
           trace_id=None, cancel_check=None)


def test_build_judge_messages_grounds_only_with_canon():
    plain, _ = build_judge_messages("ch", "vi")
    assert "demanding fiction editor" in plain and "STORY BIBLE" not in plain
    grounded, _ = build_judge_messages("ch", "vi", canon="Tô Yến: never protected her.")
    assert "demanding fiction editor" in grounded           # the test-routing anchor survives
    assert "STORY BIBLE:" in grounded and "Tô Yến: never protected her." in grounded
    assert "do NOT infer events outside" in grounded         # the false-positive guard


def test_code_mechanical_edits_collapses_consecutive_dup_word():
    text = "He ran ran fast and the wind was was cold."
    edits = code_mechanical_edits(text, "en")
    healed = text
    for s, e, new in sorted(edits, key=lambda x: x[0], reverse=True):
        healed = healed[:s] + new + healed[e:]
    assert healed == "He ran fast and the wind was cold."
    assert code_mechanical_edits("no repeats at all here", "en") == []


def test_code_mechanical_edits_skips_reduplication_languages():
    # Vietnamese reduplication ('chằm chằm' = staring intently) must NOT be collapsed
    text = "Nàng nhìn chằm chằm vào hư không, tiếng rắc rắc vang lên."
    assert code_mechanical_edits(text, "vi") == []
    assert code_mechanical_edits(text, "zh") == []
    # a genuinely reduplication-free language still gets the fix
    assert code_mechanical_edits("the the cat", "en")


class FakeStackLLM:
    """Routes verify ('SKEPTICAL reviewer') / judge ('demanding fiction editor') / editor.
    Judge replays a queue; verify_fn(user)->'CONFIRMED'|'REFUTED'; edit via edit_fn."""

    def __init__(self, judge_responses, *, edit_fn=lambda s: f"<<{len(s)}>>", verify_fn=None):
        self._judge = list(judge_responses)
        self._edit_fn = edit_fn
        self._verify_fn = verify_fn
        self.judge_calls = self.edit_calls = self.verify_calls = 0

    async def submit_and_wait(self, **kw):
        system = kw["input"]["messages"][0]["content"]
        user = kw["input"]["messages"][1]["content"]
        if "SKEPTICAL reviewer" in system:
            self.verify_calls += 1
            v = self._verify_fn(user) if self._verify_fn else "CONFIRMED"
            return SimpleNamespace(status="completed",
                                   result={"messages": [{"content": json.dumps({"verdict": v})}]})
        if "demanding fiction editor" in system:
            r = self._judge[min(self.judge_calls, len(self._judge) - 1)]
            self.judge_calls += 1
            return SimpleNamespace(status="completed", result={"messages": [{"content": r}]})
        sel = user.split("SELECTED PASSAGE:\n", 1)[1].split("\n\nAuthor guidance:", 1)[0]
        self.edit_calls += 1
        return SimpleNamespace(status="completed",
                               result={"messages": [{"content": self._edit_fn(sel)}]})


# spans placed >40 chars apart so they fall in distinct vote buckets (offset // 40)
_VOTE_CH = ("the quick brown fox " + "padd " * 16 + "lazy sleeping hound here "
            + "more " * 16 + "final distinct ending clause")


def _fj(*pairs):
    return json.dumps([{"type": "t", "span": s, "issue": i, "fix": "f"} for s, i in pairs])


async def test_vote_keeps_recurring_drops_singletons():
    a, b, c = "the quick brown fox", "lazy sleeping hound", "final distinct ending clause"
    runs = [_fj((a, "ia"), (b, "ib")), _fj((a, "ia")), _fj((c, "ic"))]
    llm = FakeStackLLM(runs)
    out = await _judge_vote(llm, _VOTE_CH, source_language="en", max_tokens=100,
                            canon=None, k=3, min_votes=2, temperature=0.7, **_KW)
    assert [f.span for f in out] == [a]            # only the 2/3-recurring span survives


async def test_vote_must_quote_drops_unlocatable_even_if_recurring():
    bogus = "this phrase is absent from the chapter entirely"
    runs = [_fj((bogus, "x")), _fj((bogus, "x")), _fj((bogus, "x"))]
    llm = FakeStackLLM(runs)
    out = await _judge_vote(llm, _VOTE_CH, source_language="en", max_tokens=100,
                            canon=None, k=3, min_votes=2, temperature=0.7, **_KW)
    assert out == []                                # un-anchorable ⇒ never votes (L2 must-quote)


async def test_verify_refuted_finding_is_dropped_not_edited():
    chapter = "the quick brown fox jumps. the lazy dog sleeps soundly now."
    good, bad = "the quick brown fox jumps", "the lazy dog sleeps soundly"
    judge = [_fj((good, "ok"), (bad, "REFUTEME")), "[]"]
    llm = FakeStackLLM(judge, edit_fn=lambda s: "EDITED",
                       verify_fn=lambda user: "REFUTED" if "REFUTEME" in user else "CONFIRMED")
    healed, rep = await run_self_heal(
        llm, user_id="u", model_source="user_model", model_ref="m",
        chapter=chapter, source_language="en", verify=True)
    assert llm.verify_calls == 2 and llm.edit_calls == 1 and rep.edits_applied == 1
    assert any(f.skip_reason == "refuted" for f in rep.findings)
    assert bad in healed and good not in healed     # refuted span untouched, confirmed span edited


async def test_prefilter_applies_mechanical_with_no_judge_findings():
    chapter = "He ran ran fast."
    llm = FakeStackLLM(["[]"])
    healed, rep = await run_self_heal(
        llm, user_id="u", model_source="user_model", model_ref="m",
        chapter=chapter, source_language="en", prefilter=True)
    assert healed == "He ran fast." and rep.edits_applied == 1 and llm.edit_calls == 0


def test_snap_to_sentence_widens_fragment_to_clause():
    text = "Alpha first sentence. Beta the wind was cold here. Gamma last one."
    # a fragment quoted mid-sentence snaps OUT to the enclosing sentence (no orphaned tail)
    i = text.index("wind was cold")
    s, e = _snap_to_sentence(text, i, i + len("wind was cold"))
    assert text[s:e] == "Beta the wind was cold here."
    # already-aligned span at the very start stays put
    s2, e2 = _snap_to_sentence(text, 0, len("Alpha first sentence."))
    assert text[s2:e2] == "Alpha first sentence."


def test_code_pronoun_findings_full_recall_no_false_hit_on_substrings():
    text = ("Ánh mắt ông nhìn nàng. Bên cạnh ông, Tô Yến tới. Bà không lên tiếng. "
            "Nàng không trông thấy gì, lòng không nguôi.")  # 'trông'/'không' must NOT match
    found = [f.span.lower() for f in code_pronoun_findings(text)]
    assert found == ["ông", "ông", "bà"]   # 3 real pronoun slips, zero substring false hits


async def test_verify_fail_open_on_degrade_keeps_finding():
    f = Finding(type="t", span="s", issue="i", fix="f")
    # a degraded (non-completed) verify call ⇒ keep the finding (fail-open)
    class Degrade:
        async def submit_and_wait(self, **kw):
            return SimpleNamespace(status="failed", result={})
    assert await _verify(Degrade(), "ch", f, canon=None, **_KW) is True

    # explicit REFUTED ⇒ drop; ambiguous garbage ⇒ keep (fail-open)
    class Resp:
        def __init__(self, c): self.c = c
        async def submit_and_wait(self, **kw):
            return SimpleNamespace(status="completed", result={"messages": [{"content": self.c}]})
    assert await _verify(Resp('{"verdict":"REFUTED"}'), "ch", f, canon=None, **_KW) is False
    assert await _verify(Resp('{"verdict":"CONFIRMED"}'), "ch", f, canon=None, **_KW) is True
    assert await _verify(Resp("no verdict here"), "ch", f, canon=None, **_KW) is True


class _VerdictQueue:
    """Verify-only fake: replays a queue of CONFIRMED/REFUTED verdicts by call order."""
    def __init__(self, verdicts):
        self.verdicts = list(verdicts)
        self.i = 0

    async def submit_and_wait(self, **kw):
        v = self.verdicts[min(self.i, len(self.verdicts) - 1)]
        self.i += 1
        return SimpleNamespace(status="completed",
                               result={"messages": [{"content": json.dumps({"verdict": v})}]})


async def test_verify_vote_drops_only_on_unanimous_refute():
    f = Finding(type="t", span="s", issue="i", fix="f")
    C, R = "CONFIRMED", "REFUTED"
    # recall-biased: ONE confirming vote (overcoming the skeptical default) keeps the finding
    assert await _verify_vote(_VerdictQueue([C, R, R]), "ch", f, canon=None, k=3, **_KW) is True   # 1/3 confirm → keep
    assert await _verify_vote(_VerdictQueue([R, R, C]), "ch", f, canon=None, k=3, **_KW) is True   # order-independent
    assert await _verify_vote(_VerdictQueue([R, R, R]), "ch", f, canon=None, k=3, **_KW) is False  # unanimous refute → drop
    assert await _verify_vote(_VerdictQueue([C, R]), "ch", f, canon=None, k=2, **_KW) is True
    # k<=1 is plain single-shot
    assert await _verify_vote(_VerdictQueue([R]), "ch", f, canon=None, k=1, **_KW) is False
    assert await _verify_vote(_VerdictQueue([C]), "ch", f, canon=None, k=1, **_KW) is True


# ── propose / apply review-gate — DIRECT high-recall judge (find + propose in one pass) ──

_PA_CH = "the quick brown fox jumps. the lazy dog sleeps soundly now."


def _dj(*items):
    # each item: (original, replacement, explanation, type) — the direct judge's emit shape
    return json.dumps([{"type": t, "original": o, "replacement": r, "explanation": e}
                       for (o, r, e, t) in items])


def _pa_llm():
    # the direct judge routes on "demanding fiction editor" in FakeStackLLM → returns this array
    return FakeStackLLM([_dj(
        ("the quick brown fox jumps", "THE RED FOX LEAPS", "tighten", "style"),
        ("the lazy dog sleeps soundly", "the hound dozes", "vary", "style"))])


async def test_propose_returns_unspliced_proposals():
    proposals, rep = await propose_self_heal(
        _pa_llm(), user_id="u", model_source="user_model", model_ref="m",
        chapter=_PA_CH, source_language="en")
    assert [p.id for p in proposals] == ["e0", "e1"]            # offset-ascending stable ids
    assert rep.edits_applied == 2 and rep.located == 2
    p0 = proposals[0]
    assert p0.before == "the quick brown fox jumps"            # the EXACT located span (not snapped)
    assert _PA_CH[p0.start:p0.end] == p0.before                # offsets address the real span
    assert p0.after == "THE RED FOX LEAPS" and p0.tier == "semantic"


async def test_propose_drops_unlocatable_original():
    # an `original` not present in the chapter is dropped (must-quote — can't splice it)
    llm = FakeStackLLM([_dj(("absent phrase not here at all", "X", "y", "z"))])
    proposals, rep = await propose_self_heal(
        llm, user_id="u", model_source="user_model", model_ref="m",
        chapter=_PA_CH, source_language="en")
    assert proposals == []
    assert rep.findings[0].skip_reason == "not_located"


async def test_apply_self_heal_edits_accepts_subset():
    proposals, _ = await propose_self_heal(
        _pa_llm(), user_id="u", model_source="user_model", model_ref="m",
        chapter=_PA_CH, source_language="en")
    assert apply_self_heal_edits(_PA_CH, proposals, accepted_ids=[]) == _PA_CH   # reject all → no-op
    only0 = apply_self_heal_edits(_PA_CH, proposals, accepted_ids=["e0"])        # accept first only
    assert only0.startswith("THE RED FOX LEAPS") and "the lazy dog sleeps soundly" in only0
    assert "the quick brown fox jumps" not in only0


def test_edit_proposal_is_serializable():
    import dataclasses
    p = EditProposal(id="e0", type="t", tier="semantic", start=0, end=3, before="abc", after="xyz")
    d = dataclasses.asdict(p)
    assert d["id"] == "e0" and d["tier"] == "semantic" and d["after"] == "xyz"
