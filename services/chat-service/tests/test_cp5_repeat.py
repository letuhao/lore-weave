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

🔴 **THAT LAST CLAUSE WAS FALSE WHEN IT WAS WRITTEN, AND THE CORPUS SAYS SO** (TOOL-V2 LOOP #58).
The count came from `read_call_results`, which only advances after a real DISPATCH — and a blocked
repeat never reaches one. So of the **598 calls this breaker blocked, across 40 sessions and 10
tools** (tool_list's separate F18 breaker excluded), **every single one reported "3 times"**, on
the 3rd attempt and on the 194th alike. Nothing escalated either: the model read "STOP calling it"
and re-emitted the call, 194 times in one real product turn. Both halves are now real — the count
is fed by a BLOCK ledger, and past a second blocked repeat the tool leaves the advertised set, the
same lever the repeated-FAILURE breaker and F18 already use.
"""
from __future__ import annotations

import pathlib

from unittest.mock import AsyncMock, patch

import pytest

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
        assert '"repeat_count": _attempts,' in src, (
            "the repeated-read refusal does not record how deep the loop is, so the two "
            "populations (a single repeat in 23 sessions vs 566 in one) cannot be told apart"
        )
        # The anchor used to be the literal `_prior[1] + 1`, and that expression was itself the
        # defect: `read_call_results` only advances on a real DISPATCH, so a BLOCKED repeat never
        # moved it and every refusal in a 194-call loop reported the same "3". The count now comes
        # from `repeat_block_counts`, which counts the blocks — so this asserts the field is fed
        # by the block ledger rather than pinning one arithmetic expression that was wrong.
        assert "repeat_block_counts" in src, (
            "the repeat count must be driven by the BLOCK ledger; a count read from the dispatch "
            "ledger is frozen at the cap for every blocked call"
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


# ── §3 said the breaker "keeps escalating". It did not. (TOOL-V2 LOOP #58) ───
#
# These live HERE rather than beside the behavioural repeated-read tests because this is the
# CP-5.7 repeat-semantics suite — the one the falsification gate measures, and the one whose
# tuple `test_THE_SUITE_LIST_IS_EVERY_CP_SUITE_ON_DISK` keeps equal to the checkpoint suites on
# disk. A guard about repeat semantics that sat outside it would be declared by arithmetic.
from tests.test_repeated_read_breaker import _drive, _read_tool, _tool_calls  # noqa: E402

class TestTheBreakerActuallyEscalates:
    """Measured on the corpus, excluding tool_list's separate F18 breaker so the denominator is
    this breaker's own: 598 blocked calls across 40 sessions and 10 tools, and ONE real product
    turn emitted 194 blocked `book_get` calls over 35 iterations.
    Short-circuiting the dispatch saved the backend round trip and did nothing about the loop —
    the model read "STOP calling it" and called it again, 194 times. That is the same failure the
    repeated-FAILURE breaker answered by taking the tool off the wire, and the same one F18
    recorded for tool_list (an error "framed the repeat as a failure the model fixes by retrying
    HARDER, 28→311 calls"). This breaker was the one that never got the escalation."""

    @pytest.mark.asyncio
    async def test_THE_REPORTED_ATTEMPT_COUNT_RISES_INSTEAD_OF_FREEZING(self):
        """Every blocked call said "3 times" — on the 3rd attempt and on the 194th alike.

        The count lived in `read_call_results`, which only advances after a real DISPATCH, and a
        blocked call never reaches one. So the one number in the message that was supposed to
        convey escalating pressure was a constant.
        """
        chunks, _kc = await _drive(times=8)
        blocked = [t for t in _tool_calls(chunks) if not t["ok"]]
        assert len(blocked) >= 2, "need at least two blocked repeats to see a count move"

        counts = [b.get("repeat_count") for b in blocked]
        assert all(c is not None for c in counts), counts
        assert counts == sorted(counts) and counts[-1] > counts[0], (
            f"the attempt count must RISE across blocked repeats, got {counts}")

    @pytest.mark.asyncio
    async def test_THE_LOOPED_TOOL_LEAVES_THE_ADVERTISED_SET(self):
        """THE fix. A tool the model cannot see is a tool it cannot re-emit."""
        offered: list[list[str]] = []
        chunks, _kc = await _drive(times=8, offered=offered)
        blocked = [t for t in _tool_calls(chunks) if not t["ok"]]
        name = _read_tool()["function"]["name"]

        assert any(b.get("deadvertised") for b in blocked), (
            "the breaker must escalate from steering to de-advertising")

        # THE assertion, and it is on the WIRE rather than on the flag: a `deadvertised: True`
        # stamp next to a tool that is still being offered is a mechanism that reports itself
        # working while changing nothing.
        assert any(name in pass_tools for pass_tools in offered), (
            "sanity: the tool must be offered before it can stop being offered")
        assert offered[-1] == [] or name not in offered[-1], (
            f"the looped tool must be GONE from the advertised set, got {offered[-1]}")
        # And the model is TOLD, because a tool that vanishes without a word invites a hunt
        # for it rather than the next step.
        assert any("disabled for the rest of this turn" in b["error"] for b in blocked)

        # The escalation is ORDERED: steer first, de-advertise only after the steer was ignored.
        assert not blocked[0].get("deadvertised"), (
            "the first block must steer, not de-advertise — a model that listens listens early")

    @pytest.mark.asyncio
    async def test_A_NORMAL_READ_NEVER_REACHES_THE_ESCALATION(self):
        """The escalation must cost the common case nothing."""
        chunks, _kc = await _drive(times=1)
        tc = _tool_calls(chunks)
        assert len(tc) == 1 and tc[0]["ok"] is True
        assert not any(t.get("deadvertised") for t in tc)


class TestBothBreakersDeAdvertiseOnThePlainPath:
    """TOOLV2 LOOP #84 — the repeated-FAILURE breaker's de-advertise was discovery-only.

    Measured, in ONE session 17 minutes apart, which is why this is not a guess about commit
    dates: the 04:47 turn emitted 30 `book_get_chapter` failures with ZERO breaker steers, and
    the 05:04 turn emitted 2 failures then 22 steers. The breaker started working mid-session.
    The de-advertise beside it did not: 22 blocked emissions across 23 iterations means the tool
    was still being offered every pass.

    `failure_suppress` fed only the discovery chokepoint, and iteration 58's fix here covered
    `repeat_read_suppress` alone — so the asymmetry was mine.
    """

    @pytest.mark.asyncio
    async def test_A_REPEATEDLY_FAILING_TOOL_LEAVES_THE_WIRE_ON_THE_PLAIN_PATH(self):
        """Asserted on the WIRE, not on the source. A guard that greps for the fix would pass
        over a fix that is never reached — which is exactly the failure this iteration found in
        the product code, so it must not be the failure in its guard."""
        import app.services.stream_service as ss

        from tests.test_repeated_read_breaker import _fake_client_repeating, _read_tool
        from tests.test_spend_gate import _kc

        tool = _read_tool("book_get_chapter")
        name = tool["function"]["name"]
        kc = _kc()
        # Every dispatch fails with the SAME error — the repeated-failure breaker's subject.
        kc.mcp_execute_tool = AsyncMock(return_value={
            "success": False,
            "error": "no active chapter with that chapter_id in this book",
        })
        # A SECOND, innocent tool. Without it the final pass offers nothing at all (the forced
        # answer pass drops tools), and `name not in []` would pass over any defect — the guard
        # would be green for the wrong reason, which is the whole subject of this iteration.
        bystander = _read_tool("book_list")
        offered: list[list[str]] = []
        with patch.object(ss, "Client", _fake_client_repeating(name, 8, offered)):
            async for _ in ss._stream_with_tools(
                model_source="user_model", model_ref="00000000-0000-0000-0000-0000000000aa",
                user_id="u", messages=[{"role": "user", "content": "read chapter 3"}],
                gen_params={"max_tokens": 100}, tools=[tool, bystander],
                knowledge_client=kc, session_id="s", project_id=None,
                permission_mode="write",
            ):
                pass

        assert any(name in p for p in offered), "sanity: it must be offered before it can go"
        dropped = [p for p in offered if "book_list" in p and name not in p]
        assert dropped, (
            "a tool the repeated-failure breaker gave up on must leave the advertised set on "
            "the plain path too — no pass ever offered the bystander WITHOUT it, so it never "
            f"left the wire. offered per pass: {offered}")

    def test_BOTH_SETS_STILL_REACH_THE_DISCOVERY_CHOKEPOINT(self):
        """The plain-path fix must not be a REPLACEMENT for the discovery wiring."""
        src = STREAM.read_text(encoding="utf-8")
        assert "_suppress = set(_suppress) | failure_suppress" in src
        assert "_suppress = set(_suppress) | repeat_read_suppress" in src

