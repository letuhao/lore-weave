"""D-THE-PERSISTED-PER-PASS-RECORDER-DROPS-A-PASS-ON-THE-SECOND-TURN.

    THE QUESTION THIS ANSWERS. The gap is witnessed only by a container log with a 30-minute
    window, and the rate is about 1 in 15 sessions. So the obvious move is to find it in the
    STORE instead, historically, across every turn ever recorded. Two ways to do that were
    measured and BOTH FAIL — recorded here so neither is proposed again as if it were new.

🔴 REJECTED 1 — `tool_calls[].iteration`. Each recorded call carries the pass it ran on, so
`max(iteration) + 1` is an independent lower bound on the pass count, and
`len(advertised_tools) < max(iteration) + 1` would be a STRICT gap indicator that outlives the
log. Measured across the live chat store: 4,436 rows carry both columns, and it finds ZERO.

That zero is the instrument, not the platform. TESTED AGAINST THE KNOWN INSTANCE — session
01a03f44, the row's own — and it MISSES IT:

    the gap row:  advertised_tools = 4 entries, max(iteration) = 2
    the test:     4 < 2 + 1  ->  False, so it lands in the "expected" bucket

The dropped pass is the TAIL of the turn — the final answer — and a final answer makes no tool
call, so no `iteration` records it. The bound is real and is simply never tight where the
defect lives. A check that returns 0 on a population containing a known positive is not
evidence of absence.

🔴 REJECTED 2 — an independent per-pass counter. `stream_job_id` is minted once per pass
(stream_service.py, M3) but is passed to the gateway and persisted NOWHERE: no column in
loreweave_chat or loreweave_jobs holds it. No LLM-call-count column exists on a chat turn
either — that counter rides unified-JOB params, and a chat turn is not a job.

WHAT REMAINS TRUE, THEREFORE: the gap can only be caught LIVE, at the moment both numbers still
exist, which is exactly what `fe_runner.pass_ledger` does. This cycle did not find the cause;
it closed off the cheap way of looking for it, with the reason.
"""
from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "toolloop"))

import fe_runner as fr  # noqa: E402

#: The row's own instance, as the store holds it: 4 advertised entries, max iteration 2, and
#: the wire log printed 5. Read from `chat_messages` on 2026-08-27.
KNOWN_GAP = {"adv_len": 4, "max_iteration": 2, "wire_log": 5}


def _iteration_bound_says_gap(row) -> bool:
    """The REJECTED instrument, written out so the test can show it failing."""
    return row["adv_len"] < row["max_iteration"] + 1


def test_the_iteration_bound_MISSES_the_known_instance():
    """🔴 THE SENSITIVITY TEST, and the reason its 0-of-4,436 was not reported as a clean bill.
    A check that returns 'no gap' on the one row known to have one measures nothing."""
    assert not _iteration_bound_says_gap(KNOWN_GAP), (
        "the iteration bound now catches the known instance — the store's shape has changed "
        "and the historical sweep is worth re-running before it is dismissed again"
    )
    assert KNOWN_GAP["adv_len"] < KNOWN_GAP["wire_log"], "the instance must still BE a gap"


def test_the_bound_is_only_ever_a_LOWER_bound():
    """Why it cannot work in principle, not merely on this row: a pass that makes no tool call
    leaves no iteration, and the dropped pass is a final answer, which is exactly that."""
    final_answer_dropped = {"adv_len": 3, "max_iteration": 2, "wire_log": 4}
    assert not _iteration_bound_says_gap(final_answer_dropped)
    # It can only fire when the LAST pass both called a tool and was dropped — a shape the
    # store has never once produced.
    tool_bearing_dropped = {"adv_len": 2, "max_iteration": 2, "wire_log": 4}
    assert _iteration_bound_says_gap(tool_bearing_dropped)


def test_the_LIVE_ledger_is_still_the_only_witness():
    """`pass_ledger` takes both numbers while both exist. If this import ever breaks, the only
    way of seeing the gap at all has gone with it."""
    assert callable(fr.wire_log_pass_count)
    assert callable(fr.wire_passes)


def test_wire_log_absence_is_None_and_never_zero():
    """🔴 CARRIED FORWARD FROM THE ROW, because it is the trap this whole area already fell
    into once: a zero would claim the service printed nothing, and an unreadable log would then
    read as a maximal gap. Absence must stay distinguishable from a measurement."""
    import inspect
    src = inspect.getsource(fr.wire_log_pass_count)
    assert "return None" in src, (
        "wire_log_pass_count no longer has an explicit None return — if it now falls through "
        "to 0, an unreadable log reports every pass as dropped"
    )
