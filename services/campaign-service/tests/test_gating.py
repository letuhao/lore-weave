"""Gating-logic tests — the load-bearing policy of S1.

These guard against the double-dispatch = double-spend class of bug (the very
gap, G3, the Auto-Draft Factory exists to close). Every branch of
`next_dispatches` / `is_complete` is exercised.
"""

from app.saga.gating import (
    ChapterState,
    Dispatch,
    StageFailure,
    next_dispatches,
    is_complete,
)

STAGES = ["knowledge", "translation", "eval"]


def _ch(cid, k="pending", t="pending", ka=0, ta=0):
    return ChapterState(
        chapter_id=cid,
        knowledge_status=k,
        translation_status=t,
        knowledge_attempts=ka,
        translation_attempts=ta,
    )


def _run(mode, chapters, *, max_attempts=3, max_inflight=-1):
    return next_dispatches(
        gating_mode=mode,
        chapters=chapters,
        stages=STAGES,
        max_attempts=max_attempts,
        max_inflight=max_inflight,
    )


# ── knowledge stage dispatch ──────────────────────────────────────────────

def test_pending_knowledge_dispatched_both_modes():
    for mode in ("phase_barrier", "cold_start"):
        r = _run(mode, [_ch("c1")])
        assert Dispatch("c1", "knowledge") in r.dispatches


def test_done_knowledge_never_redispatched():
    r = _run("cold_start", [_ch("c1", k="done")])
    assert all(d.stage != "knowledge" for d in r.dispatches)


def test_dispatched_knowledge_not_redispatched():
    # Already in-flight — must NOT be dispatched again (double-spend guard).
    r = _run("cold_start", [_ch("c1", k="dispatched")])
    assert r.dispatches == []


def test_failed_knowledge_retried_until_cap():
    r = _run("cold_start", [_ch("c1", k="failed", ka=1)], max_attempts=3)
    assert Dispatch("c1", "knowledge") in r.dispatches


def test_failed_knowledge_exhausted_reported_not_dispatched():
    r = _run("cold_start", [_ch("c1", k="failed", ka=3)], max_attempts=3)
    assert r.dispatches == []
    assert StageFailure("c1", "knowledge") in r.exhausted


# ── translation gating — cold_start ───────────────────────────────────────

def test_cold_start_translates_chapter_once_its_own_knowledge_done():
    # c1 knowledge done → translate c1; c2 knowledge pending → only knowledge c2.
    r = _run("cold_start", [_ch("c1", k="done"), _ch("c2", k="pending")])
    assert Dispatch("c1", "translation") in r.dispatches
    assert Dispatch("c2", "knowledge") in r.dispatches
    assert Dispatch("c2", "translation") not in r.dispatches


def test_cold_start_does_not_translate_before_chapter_knowledge():
    r = _run("cold_start", [_ch("c1", k="pending")])
    assert Dispatch("c1", "translation") not in r.dispatches


# ── translation gating — phase_barrier ────────────────────────────────────

def test_phase_barrier_holds_translation_until_whole_book_knowledge_settled():
    # c1 knowledge done but c2 still pending → barrier closed → NO translation.
    chapters = [_ch("c1", k="done"), _ch("c2", k="pending")]
    r = _run("phase_barrier", chapters)
    assert all(d.stage != "translation" for d in r.dispatches)
    assert Dispatch("c2", "knowledge") in r.dispatches


def test_phase_barrier_opens_when_all_knowledge_settled():
    chapters = [_ch("c1", k="done"), _ch("c2", k="done")]
    r = _run("phase_barrier", chapters)
    assert Dispatch("c1", "translation") in r.dispatches
    assert Dispatch("c2", "translation") in r.dispatches


def test_phase_barrier_not_deadlocked_by_permanently_failed_knowledge():
    # c2's knowledge permanently failed (attempts exhausted) → it is SETTLED, so
    # the barrier opens and c1 (knowledge done) gets translated. c2 itself is not
    # translatable (its knowledge isn't terminal-success).
    chapters = [_ch("c1", k="done"), _ch("c2", k="failed", ka=3)]
    r = _run("phase_barrier", chapters, max_attempts=3)
    assert Dispatch("c1", "translation") in r.dispatches
    assert Dispatch("c2", "translation") not in r.dispatches


# ── attempt cap on translation ────────────────────────────────────────────

def test_translation_exhausted_reported():
    chapters = [_ch("c1", k="done", t="failed", ta=3)]
    r = _run("cold_start", chapters, max_attempts=3)
    assert StageFailure("c1", "translation") in r.exhausted
    assert all(d.stage != "translation" for d in r.dispatches)


# ── stage subsetting ──────────────────────────────────────────────────────

def test_translation_only_campaign_skips_knowledge_gate():
    # stages without 'knowledge' → translation dispatches regardless of knowledge.
    r = next_dispatches(
        gating_mode="phase_barrier",
        chapters=[_ch("c1", k="pending")],
        stages=["translation", "eval"],
        max_attempts=3,
        max_inflight=-1,
    )
    assert Dispatch("c1", "translation") in r.dispatches
    assert all(d.stage != "knowledge" for d in r.dispatches)


# ── max_inflight fairness window ──────────────────────────────────────────

def test_max_inflight_bounds_dispatch_count():
    chapters = [_ch(f"c{i}") for i in range(50)]
    r = _run("cold_start", chapters, max_inflight=10)
    assert len(r.dispatches) == 10


def test_negative_inflight_is_unbounded():
    chapters = [_ch(f"c{i}") for i in range(50)]
    r = _run("cold_start", chapters, max_inflight=-1)
    assert len(r.dispatches) == 50


# ── completion ────────────────────────────────────────────────────────────

def test_is_complete_zero_chapters():
    assert is_complete(chapters=[], stages=STAGES, max_attempts=3) is True


def test_is_complete_all_done():
    chapters = [_ch("c1", k="done", t="done"), _ch("c2", k="skipped", t="done")]
    assert is_complete(chapters=chapters, stages=STAGES, max_attempts=3) is True


def test_not_complete_with_pending():
    chapters = [_ch("c1", k="done", t="pending")]
    assert is_complete(chapters=chapters, stages=STAGES, max_attempts=3) is False


def test_complete_with_permanent_failures():
    # A campaign with exhausted failures is settled → complete (failures recorded).
    chapters = [_ch("c1", k="done", t="failed", ta=3)]
    assert is_complete(chapters=chapters, stages=STAGES, max_attempts=3) is True


def test_not_complete_with_retryable_failure():
    chapters = [_ch("c1", k="done", t="failed", ta=1)]
    assert is_complete(chapters=chapters, stages=STAGES, max_attempts=3) is False
