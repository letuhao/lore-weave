"""CP-5.7 — repeat semantics: the cost was already gone; the SIGNAL was pointing at the wrong thing.

🔴 **MEASURED: 2,189 of 4,181 recorded tool failures — 52.4% — are our own breaker prose.** §1's
failure corpus is more than half runtime refusals wearing a tool's name. Same conflation as a
suspension recorded `ok:false` (5.5) and a missing argument that the runtime owes (5.4), a third
time and the largest.

🔴 **AND THE ROW CONTAINS TWO POPULATIONS THAT §1's RANKING WARNED ABOUT.** By CALLS it is a handful
of pathological loops — `tool_list` **1,180 calls across 3 sessions**, worst session **566 repeats**;
`book_get` 495 across 5. By SESSIONS the broad shape is bigger — `glossary_book_ontology_read`
repeats exactly **once in each of 23 sessions**. One number would have hidden whichever it did not
rank by.

§3's rule, made structural: **the contract may remove a repeat's COST; it may never remove its
SIGNAL.** The breaker already removes the cost — it short-circuits before the dispatch — so nothing
here caches anything. What changes is that a refusal stops being typed as a tool failure, while the
repeat count keeps rising and the breaker keeps escalating.
"""
from __future__ import annotations

import pathlib

from app.agentruntime.observation import FAILED, OUTCOMES
from app.services import instrument

STREAM = (pathlib.Path(__file__).resolve().parents[1]
          / "app" / "services" / "stream_service.py")


def instrumented(**chunk) -> dict:
    chunk.setdefault("tool", "tool_list")
    return instrument.ensure_tool_call_instrumented(dict(chunk))


class TestARefusalIsNotAFailure:

    def test_A_BREAKER_SHORT_CIRCUIT_IS_REFUSED(self):
        got = instrumented(**instrument.stamp_refused(
            {"ok": False, "error": "already called"}, "repeated_read"))
        assert got["call_outcome"] == "refused"
        assert got["call_outcome"] != FAILED

    def test_REFUSED_IS_ALREADY_IN_THE_DECLARED_VOCABULARY(self):
        """No new member was invented for this — C-14 already had the word."""
        assert instrument.CALL_REFUSED in OUTCOMES

    def test_THE_BREAKERS_STAY_SEPARABLE_FROM_EACH_OTHER(self):
        """'the model looped on an unchanged read' and 'the model re-ran a no-op write' are
        different defects and must not merge into one number."""
        a = instrumented(**instrument.stamp_refused({"ok": False}, "repeated_read"))
        b = instrumented(**instrument.stamp_refused({"ok": False}, "idempotent_noop_write"))
        assert a["refusal_kind"] != b["refusal_kind"]

    def test_A_REFUSAL_CARRIES_NO_ERROR_CLASS(self):
        """§4.2 — the class is a sub-field of `failed`. Asking whether a refusal is retryable is a
        category error, and here it would be actively wrong: retrying is the thing being refused."""
        got = instrumented(**instrument.stamp_refused(
            {"ok": False, "error_class": "retryable_transient"}, "repeated_read"))
        assert "error_class" not in got

    def test_AN_ORDINARY_FAILURE_IS_STILL_FAILED(self):
        """The split must not swallow real failures — that would be removing the signal to remove
        the cost, which is exactly what §3 forbids."""
        assert instrumented(ok=False, error="book not found")["call_outcome"] == FAILED


class TestTheSignalIsRetained:

    def test_THE_REPEAT_COUNT_RIDES_THE_RECORD(self):
        """*The contract may remove a repeat's COST; it may never remove its SIGNAL.* A refusal
        that did not say how many times would turn 566 repeats into an unreadable 566 rows."""
        src = STREAM.read_text(encoding="utf-8")
        assert '"repeat_count": _prior[1] + 1,' in src, (
            "the repeated-read refusal does not record how deep the loop is, so the two "
            "populations (a single repeat in 23 sessions vs 566 in one) cannot be told apart"
        )

    def test_THE_BREAKER_STILL_ESCALATES(self):
        """Serving a repeat silently is the metric laundering §3 exists to refuse: 393 errors
        become 393 silent successes and the loop runs exactly as long."""
        src = STREAM.read_text(encoding="utf-8")
        assert "_prior[1] >= REPEAT_READ_CAP" in src, "the escalation was removed with the cost"
        assert "continue" in src

    def test_BOTH_NAMED_BREAKERS_ARE_WIRED(self):
        """§3 names the repeated read; the no-op write is its sibling and was recorded the same
        wrong way. A mechanism wired at one of two sites is the shape this run keeps finding."""
        src = STREAM.read_text(encoding="utf-8")
        # 🔴 This pinned the exact COUNT of `stamp_refused` sites and went red the moment 5.10
        # legitimately added a third (an undispatchable tool name). A count over a set that is
        # SUPPOSED to grow is a guard against progress; the claim was always "both NAMED breakers
        # are wired", so it asserts the kinds — which is the thing that can actually regress.
        assert '"repeated_read")' in src, "the repeated-read breaker is not typed as a refusal"
        assert '"idempotent_noop_write")' in src, "the no-op-write breaker is not typed as one"
        assert src.count("instrument.stamp_refused(") >= 2

    def test_NOTHING_IS_SERVED_FROM_A_CACHE(self):
        """🔴 The design decision, guarded. §3 ALLOWS a declared-idempotent read to be served from
        cache, and this row deliberately does not do it: `read_call_results` holds a FINGERPRINT
        and a count, not a result body, so 'serve the cache' would mean retaining every read's
        payload for the turn. The cost is already gone without it — the breaker short-circuits
        before dispatch — so caching would buy nothing and risk the silent-success failure."""
        assert "tuple[str, int]" in STREAM.read_text(encoding="utf-8"), (
            "read_call_results changed shape; if it now holds result bodies, revisit whether a "
            "cached repeat is served — and if it is, it must still be COUNTED and still escalate"
        )
