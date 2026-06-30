"""Unit tests for the Phase-2 self-heal orchestrator (engine/self_heal.py).

Focus: the load-bearing fuzzy LOCATE (the judge abbreviates/re-spaces spans), the
tolerant findings parse, and the orchestration invariants — splice correctness,
and the SKIP guards (not-located / overlap / runaway-expansion) that keep the pass
advisory (original prose preserved).
"""

import json
from types import SimpleNamespace

from app.engine import self_heal
from app.engine.self_heal import Finding, locate_span, parse_findings, run_self_heal

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
    assert "<<26>>" in healed and "<<37>>" in healed  # both span lengths spliced in
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
