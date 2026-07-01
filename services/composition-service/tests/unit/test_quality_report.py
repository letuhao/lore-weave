"""Unit tests for the Quality Report orchestrator (engine/quality_report.py).

Focus: the two chapter-level advisory judges (critic + promise_audit) run
concurrently and shape one report; each side degrades independently (an LLM
failure in one returns its empty shape + `error` and never sinks the other).
"""

import json
from types import SimpleNamespace

from app.engine.quality_report import build_promise_coverage, build_quality_report

# async tests are collected via pytest.ini asyncio auto-mode.


_CRITIC_JSON = json.dumps({
    "coherence": 4, "voice_match": 3, "pacing": 5, "canon_consistency": 2,
    "violations": [{"rule_id": "R1", "violated": True, "span": "he said", "why": "wrong pronoun"}],
})
_PROMISE_JSON = json.dumps({
    "introduced": ["the sealed grimoire", "the debt to the sect"],
    "resolved": ["the sealed grimoire"],
    "dropped": ["the debt to the sect"],
})


class FakeQRLLM:
    """Routes submit_and_wait by the SYSTEM prompt: the critic system says
    'craft critic', the promise system says 'NARRATIVE PROMISES'. Each side can be
    forced to a non-completed status to exercise the degrade path."""

    def __init__(self, *, critic="ok", promise="ok"):
        self._critic = critic
        self._promise = promise
        self.calls = []

    async def submit_and_wait(self, **kw):
        system = kw["input"]["messages"][0]["content"]
        self.calls.append(system)
        if "craft critic" in system:
            mode, payload = self._critic, _CRITIC_JSON
        else:  # promise audit
            mode, payload = self._promise, _PROMISE_JSON
        if mode == "fail":
            return SimpleNamespace(status="failed", result={})
        if mode == "raise":
            # a non-LLMError raised on the completed path (the window the engines'
            # `except LLMError` does NOT cover) — build_quality_report must degrade it,
            # not let it sink the sibling judge or raise out of the op.
            raise RuntimeError("unexpected boom")
        return SimpleNamespace(status="completed", result={"messages": [{"content": payload}]})


async def test_report_both_ok():
    llm = FakeQRLLM()
    rep = await build_quality_report(
        llm, user_id="u", model_source="s", model_ref="m",
        chapter="Some chapter prose.", source_language="vi")
    assert rep["critic"]["coherence"] == 4
    assert rep["critic"]["canon_consistency"] == 2
    assert len(rep["critic"]["violations"]) == 1
    # reframed (D-QUALITY-DROPPED-FP): threads RAISED (= introduced) + RESOLVED, no "dropped"
    assert rep["threads"]["raised"] == ["the sealed grimoire", "the debt to the sect"]
    assert rep["threads"]["resolved"] == ["the sealed grimoire"]
    assert rep["threads"]["raised_count"] == 2 and rep["threads"]["resolved_count"] == 1
    assert "dropped" not in rep["threads"]  # the false-positive verdict is gone
    # both judges ran (2 concurrent calls)
    assert len(llm.calls) == 2


async def test_critic_degrades_threads_survive():
    llm = FakeQRLLM(critic="fail")
    rep = await build_quality_report(
        llm, user_id="u", model_source="s", model_ref="m", chapter="prose")
    assert rep["critic"]["error"].startswith("critic_")
    assert rep["critic"]["coherence"] is None
    # the thread audit is unaffected by the critic's failure
    assert rep["threads"]["raised"] == ["the sealed grimoire", "the debt to the sect"]
    assert "error" not in rep["threads"]


async def test_threads_degrade_critic_survives():
    llm = FakeQRLLM(promise="fail")
    rep = await build_quality_report(
        llm, user_id="u", model_source="s", model_ref="m", chapter="prose")
    assert rep["critic"]["coherence"] == 4
    # a failed audit returns the empty threads shape + error (no fabricated raised list)
    assert rep["threads"]["error"].startswith("audit_")
    assert rep["threads"]["raised"] == [] and rep["threads"]["raised_count"] == 0


async def test_unexpected_raise_in_one_judge_does_not_sink_the_other():
    # A judge raising a NON-LLMError (the window the engines don't catch) must degrade
    # to its empty shape without cancelling the sibling or raising out of the report.
    llm = FakeQRLLM(critic="raise")
    rep = await build_quality_report(
        llm, user_id="u", model_source="s", model_ref="m", chapter="prose")
    assert rep["critic"]["error"] == "critic_error"
    assert rep["critic"]["coherence"] is None
    # the thread audit still completed normally
    assert rep["threads"]["raised"] == ["the sealed grimoire", "the debt to the sect"]
    assert "error" not in rep["threads"]


async def test_canon_grounds_the_critic():
    """A canon bible is handed to the critic as an established-fact block (grounding
    its canon_consistency dim) — the report still shapes correctly."""
    llm = FakeQRLLM()
    rep = await build_quality_report(
        llm, user_id="u", model_source="s", model_ref="m",
        chapter="prose", canon="CANON: Lâm Uyển is the MC.")
    critic_system = next(c for c in llm.calls if "craft critic" in c)
    assert "craft critic" in critic_system  # critic ran with grounding present
    assert rep["critic"]["coherence"] == 4


# ── Q3 — book-level promise coverage (v2 extract → score) ─────────────────────

_EXTRACT_JSON = json.dumps({"promises": ["the sealed grimoire", "the debt to the sect"]})
_COVERAGE_JSON = json.dumps({"verdicts": [{"index": 0, "verdict": "paid"},
                                          {"index": 1, "verdict": "abandoned"}]})


class FakeCoverageLLM:
    """Routes by SYSTEM prompt: the extract system says 'PREMISE and OUTLINE', the
    coverage system says 'fixed list of narrative PROMISES'. Each side can be forced
    to a non-completed status (or a raise) to exercise the degrade paths."""

    def __init__(self, *, extract="ok", coverage="ok"):
        self._extract = extract
        self._coverage = coverage
        self.calls = []

    async def submit_and_wait(self, **kw):
        system = kw["input"]["messages"][0]["content"]
        self.calls.append(system)
        if "PREMISE and OUTLINE" in system:
            mode, payload = self._extract, _EXTRACT_JSON
        else:  # coverage
            mode, payload = self._coverage, _COVERAGE_JSON
        if mode == "fail":
            return SimpleNamespace(status="failed", result={})
        if mode == "raise":
            raise RuntimeError("unexpected boom")
        return SimpleNamespace(status="completed", result={"messages": [{"content": payload}]})


async def test_coverage_both_ok():
    llm = FakeCoverageLLM()
    cov = await build_promise_coverage(
        llm, user_id="u", model_source="s", model_ref="m",
        premise="", plan_text="## Ch1: a debt is owed\n- she finds a grimoire",
        book_text="the whole book prose ...", source_language="vi")
    assert cov["tracked_count"] == 2
    assert cov["introduced_count"] == 2          # paid + abandoned engaged
    assert cov["paid_count"] == 1 and cov["abandoned_count"] == 1
    assert cov["pay_rate"] == 0.5 and cov["abandon_rate"] == 0.5
    assert len(llm.calls) == 2                    # extract then score


async def test_coverage_extract_degrade_yields_no_tracked_promises():
    # extract fails → empty promise set → score returns the no-tracked shape (never a phantom).
    llm = FakeCoverageLLM(extract="fail")
    cov = await build_promise_coverage(
        llm, user_id="u", model_source="s", model_ref="m",
        premise="", plan_text="plan", book_text="prose")
    assert cov["tracked_count"] == 0
    assert cov["error"] == "no_tracked_promises"
    # the coverage LLM is never asked to score an empty set (short-circuit in the engine).
    assert len(llm.calls) == 1


async def test_coverage_score_degrade_marks_all_absent():
    # extract ok, score fails → the fixed set is all-'absent' + error (no fabricated pays).
    llm = FakeCoverageLLM(coverage="fail")
    cov = await build_promise_coverage(
        llm, user_id="u", model_source="s", model_ref="m",
        premise="", plan_text="plan", book_text="prose")
    assert cov["tracked_count"] == 2
    assert cov["absent_count"] == 2 and cov["paid_count"] == 0
    assert cov["error"] == "coverage_unavailable"


async def test_coverage_unexpected_raise_degrades_to_empty():
    llm = FakeCoverageLLM(extract="raise")
    cov = await build_promise_coverage(
        llm, user_id="u", model_source="s", model_ref="m",
        premise="", plan_text="plan", book_text="prose")
    assert cov["tracked_count"] == 0 and cov["error"] == "coverage_error"


# ── windowing + merge (D-QUALITY-COVERAGE-CHUNK — the whole book overflows one score call) ──

def test_split_windows():
    from app.engine.quality_report import _split_windows
    # under budget → single window
    assert _split_windows("a\n\nb", 100) == ["a\n\nb"]
    # over budget → splits on paragraph boundary
    ws = _split_windows("aaaa\n\nbbbb\n\ncccc", 6)
    assert len(ws) >= 2 and "".join(w.replace("\n", "") for w in ws) == "aaaabbbbcccc"
    # a single over-budget paragraph is its own window (never cut mid-line)
    assert _split_windows("x" * 50, 10) == ["x" * 50]


class FakeWindowLLM:
    """Extract yields ONE promise; each coverage (score) call's verdict is decided by a MARK
    embedded in that window's STORY text — so different windows return different verdicts and
    we can assert the merge picks the strongest engagement across the book."""

    def __init__(self, *, coverage_error_windows=()):
        self._err = set(coverage_error_windows)  # window marks whose score call degrades
        self.score_calls = 0

    async def submit_and_wait(self, **kw):
        system = kw["input"]["messages"][0]["content"]
        if "PREMISE and OUTLINE" in system:
            return SimpleNamespace(status="completed",
                                   result={"messages": [{"content": json.dumps({"promises": ["the debt"]})}]})
        # coverage: read the window's STORY, pick a verdict by its mark
        self.score_calls += 1
        story = kw["input"]["messages"][1]["content"]
        mark = "PAID" if "PAID_MARK" in story else "ABANDON" if "ABANDON_MARK" in story else "ABSENT"
        if mark in self._err:
            return SimpleNamespace(status="failed", result={})
        verdict = {"PAID": "paid", "ABANDON": "abandoned", "ABSENT": "absent"}[mark]
        return SimpleNamespace(status="completed", result={"messages": [
            {"content": json.dumps({"verdicts": [{"index": 0, "verdict": verdict}]})}]})


async def test_coverage_windows_and_merges_strongest_verdict():
    # 2 windows: the promise is ABANDONED in window 1 but PAID in window 2 → merged = paid
    # (resolved somewhere in the book beats dropped-in-an-earlier-window).
    llm = FakeWindowLLM()
    book = "ABANDON_MARK " + ("x" * 60) + "\n\n" + "PAID_MARK " + ("y" * 60)
    cov = await build_promise_coverage(
        llm, user_id="u", model_source="s", model_ref="m",
        premise="", plan_text="plan", book_text=book, window_chars=50)
    assert llm.score_calls == 2               # windowed, not one big call
    assert cov["paid_count"] == 1 and cov["abandoned_count"] == 0
    assert cov["coverage"][0]["verdict"] == "paid"


async def test_coverage_all_windows_fail_is_unavailable():
    # every window's score degrades → honest coverage_unavailable, never fabricated verdicts
    llm = FakeWindowLLM(coverage_error_windows=("PAID", "ABANDON", "ABSENT"))
    book = "ABANDON_MARK " + ("x" * 60) + "\n\n" + "PAID_MARK " + ("y" * 60)
    cov = await build_promise_coverage(
        llm, user_id="u", model_source="s", model_ref="m",
        premise="", plan_text="plan", book_text=book, window_chars=50)
    assert cov["error"] == "coverage_unavailable"
    assert cov["tracked_count"] == 1 and cov["paid_count"] == 0
