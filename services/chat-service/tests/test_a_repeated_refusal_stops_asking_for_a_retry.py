"""T14/T15 — the second identical refusal must stop inviting a retry.

WHY THIS EXISTS, measured rather than imagined. The duplicate-identifier refusal is well-worded
and models ignore it anyway: in the audited corpus one session repeated a refused call **14 times**
and another **71**. A 2026-09-06 human-sim run watched PlanForge send the same bad shape three
times across two Tier-A approval prompts — roughly ten minutes of the author's time, two consent
decisions, zero arcs created — and then announce it would send it a fourth. The turn still closed
reporting partial success ("Did plan_propose_spec"), so the author believed a plan existed when
nothing durable had been created.

A refusal that says exactly the same thing every time is, to a model that has already failed to act
on it, no signal at all. So the refusal counts, and on a repeat it stops asking for a retry and
asks for an honest report instead.

This is the same escalation shape ``FindToolsAttemptTracker`` uses for repeated ``find_tools``
guessing, and for the same reason: an unbounded retry invitation is what turns one bad call into
seventy. Reusing it was deliberate — two mechanisms for one rule is how they drift apart.
"""
from __future__ import annotations

import time

from app.agentruntime.toolcontract import (
    RepeatedRefusalTracker,
    duplicate_identifier_message,
)

_A, _B, _V = "book_id", "chapter_id", "0f9d1a2b-3c4d-5e6f-7a8b-9c0d1e2f3a4b"


class TestTheMessageEscalates:
    def test_the_first_refusal_asks_for_a_lookup_and_a_retry(self):
        msg = duplicate_identifier_message(_A, _B, _V)
        assert "can never be the same id" in msg
        assert "call again" in msg, "the first refusal should still invite a corrected retry"
        assert "STOP retrying" not in msg

    def test_the_second_refusal_tells_it_to_STOP(self):
        msg = duplicate_identifier_message(_A, _B, _V, attempt=2)
        assert "STOP retrying" in msg
        assert "refused every time" in msg

    def test_the_repeat_refusal_forbids_claiming_success(self):
        """T15 — the run's real harm was not the failed call, it was the turn REPORTING partial
        success afterwards, so the author believed a plan existed."""
        msg = duplicate_identifier_message(_A, _B, _V, attempt=3)
        assert "tell the user" in msg.lower()
        assert "do not report the task as done" in msg.lower()

    def test_the_repeat_refusal_says_how_many_times(self):
        """"You have done this before" is weaker than "you have done this 3 times"."""
        assert "3 times" in duplicate_identifier_message(_A, _B, _V, attempt=3)
        assert "7 times" in duplicate_identifier_message(_A, _B, _V, attempt=7)

    def test_it_is_still_a_refusal_and_never_a_repair(self):
        """The runtime still does not know WHICH argument is wrong; only the advice changes."""
        for attempt in (1, 2, 5):
            msg = duplicate_identifier_message(_A, _B, _V, attempt=attempt)
            assert "identify DIFFERENT things" in msg
            assert _A in msg and _B in msg and _V in msg


class TestTheTrackerCounts:
    def test_the_first_time_is_attempt_one(self):
        t = RepeatedRefusalTracker(now=time.monotonic)
        assert t.record("s1", "tool", _A, _B, _V) == 1

    def test_the_same_call_again_escalates(self):
        t = RepeatedRefusalTracker(now=time.monotonic)
        t.record("s1", "tool", _A, _B, _V)
        assert t.record("s1", "tool", _A, _B, _V) == 2
        assert t.record("s1", "tool", _A, _B, _V) == 3

    def test_the_param_ORDER_does_not_reset_the_count(self):
        """Otherwise a model could alternate orderings and never trip the escalation — the same
        mistake counted as two different ones."""
        t = RepeatedRefusalTracker(now=time.monotonic)
        assert t.record("s1", "tool", _A, _B, _V) == 1
        assert t.record("s1", "tool", _B, _A, _V) == 2

    def test_a_DIFFERENT_call_is_counted_separately(self):
        """NV-7 — a counter that escalates on everything would fire on a model's first, honest
        attempt at an unrelated call, which is worse than not escalating at all."""
        t = RepeatedRefusalTracker(now=time.monotonic)
        t.record("s1", "tool", _A, _B, _V)
        assert t.record("s1", "OTHER_tool", _A, _B, _V) == 1
        assert t.record("s1", "tool", _A, "parent_id", _V) == 1
        assert t.record("s1", "tool", _A, _B, "99999999-0000-0000-0000-000000000000") == 1

    def test_sessions_do_not_contaminate_each_other(self):
        t = RepeatedRefusalTracker(now=time.monotonic)
        t.record("s1", "tool", _A, _B, _V)
        t.record("s1", "tool", _A, _B, _V)
        assert t.record("s2", "tool", _A, _B, _V) == 1, "one session's mistakes escalated another's"

    def test_an_expired_entry_starts_over(self):
        """A session that hit this an hour ago should not meet an escalated refusal on a fresh,
        honest attempt today."""
        clock = {"t": 1000.0}
        t = RepeatedRefusalTracker(now=lambda: clock["t"], ttl_s=60.0)
        assert t.record("s1", "tool", _A, _B, _V) == 1
        clock["t"] += 3600.0
        assert t.record("s1", "tool", _A, _B, _V) == 1

    def test_no_session_id_never_escalates(self):
        """Without a session there is nothing to count, and guessing would escalate at a caller
        who has done nothing wrong."""
        t = RepeatedRefusalTracker(now=time.monotonic)
        assert t.record(None, "tool", _A, _B, _V) == 1
        assert t.record(None, "tool", _A, _B, _V) == 1

    def test_the_session_bucket_is_released_when_it_empties(self):
        """The leak FindToolsAttemptTracker had to be patched for twice, in two engines: pruning
        only INSIDE a session's bucket leaves one dict entry per session forever."""
        clock = {"t": 1000.0}
        t = RepeatedRefusalTracker(now=lambda: clock["t"], ttl_s=60.0)
        t.record("s1", "tool", _A, _B, _V)
        clock["t"] += 3600.0
        t.record("s2", "tool", _A, _B, _V)   # any later call prunes
        t.record("s1", "tool", _A, _B, _V)   # s1's stale entry is gone, so this is a fresh 1
        assert t.record("s1", "tool", _A, _B, _V) == 2
