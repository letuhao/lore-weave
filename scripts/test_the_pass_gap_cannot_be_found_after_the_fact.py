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


# ── 2026-08-28 · THE SEARCH SPACE HALVED, BY STRUCTURE RATHER THAN BY A RUN ────────────────
#
# The row carried this as its standing lead: "`advertised_tools=_advertised.advertised_json()`
# is read at the PERSIST sites, so a pass that runs after the last persist on that path would
# not be in the column. NOT VERIFIED — it is where to look, not what happened."
#
# It is now verified in the OTHER direction, which is the useful one: the missing pass reached
# the recorder. It is not a recording failure at all, so every hypothesis of the shape "the
# chunk never got there" is dead and only the PERSIST remains.
#
# THE ARGUMENT IS STRUCTURAL, so it costs no live runs at 1-in-15:
#
#   1. In `_stream_with_tools`, under `if advertised:`, the pass's chunk is yielded
#      UNCONDITIONALLY (`yield {"advertised": _adv_ev_pending}`), and the
#      "agent-surface advertised (session=...)" log line sits BELOW it, inside
#      `if surface_tracker is not None:`. There is no branch that reaches the log without
#      first executing that yield.
#   2. An async generator resumes past a `yield` only when its consumer asks for the NEXT
#      item. So the generator cannot reach the log line until the consumer's loop body for
#      that chunk has finished — and that body is where `record_pass` runs.
#   3. The only thing between them is `_bounded_turn_stream`, which does NOT prefetch: it
#      awaits `iterator.__anext__()` one item at a time under `wait_for`. A ceiling trip
#      `aclose()`s the inner generator, which raises GeneratorExit AT the yield — losing the
#      LOG line, never the recorded pass. That is the opposite direction from the defect.
#
# Therefore EVERY "agent-surface advertised" line the log printed is proof that `record_pass`
# ran for that pass. The store held 4 where the log printed 5, so the fifth WAS recorded and
# was then lost at write time.
#
# These guards pin the three structural facts the argument rests on. If any of them changes,
# the argument stops holding and this row's search space must be reopened — which is the whole
# reason they are asserted rather than written down in prose.

SRC = (ROOT / "services" / "chat-service" / "app" / "services"
       / "stream_service.py").read_text(encoding="utf-8")


def _advertised_branch() -> str:
    """The `if advertised:` block of the tool loop — from the branch to its dedent."""
    i = SRC.index("                if advertised:\n")
    tail = SRC[i:]
    lines = tail.splitlines(keepends=True)
    out = [lines[0]]
    for ln in lines[1:]:
        if ln.strip() and (len(ln) - len(ln.lstrip())) <= 16:
            break
        out.append(ln)
    return "".join(out)


def test_the_pass_chunk_is_yielded_BEFORE_the_log_line_that_witnesses_it():
    """Step 1. The log is downstream of the yield, so a logged pass was a delivered pass."""
    block = _advertised_branch()
    y = block.index('yield {"advertised": _adv_ev_pending}')
    g = block.index("agent-surface advertised (session=%s)")
    assert y < g, (
        "the 'agent-surface advertised' log no longer sits BELOW the advertised yield — a "
        "logged pass is no longer proof the consumer received it, and this row's 2026-08-28 "
        "narrowing (the loss is in the PERSIST, not the recording) no longer holds"
    )


def test_the_yield_is_unconditional_within_that_branch():
    """Step 1, the half that makes it an argument rather than a coincidence: no guard sits
    between `if advertised:` and the yield, so the log cannot be reached by a path that
    skipped it."""
    block = _advertised_branch()
    head = block[: block.index('yield {"advertised": _adv_ev_pending}')]
    # The schema_tokens sub-block is allowed to intervene (it yields, it does not branch AROUND
    # the advertised yield); what must not appear is a conditional wrapping the yield itself.
    yield_line = [ln for ln in block.splitlines()
                  if 'yield {"advertised": _adv_ev_pending}' in ln][0]
    assert len(yield_line) - len(yield_line.lstrip()) == 20, (
        f"the advertised yield is no longer at the branch's own indent ({yield_line!r}) — it "
        "has been moved under a condition, so a pass can now be logged without being recorded"
    )
    assert "schema_tokens_reported" in head  # the one legitimate intervening block


def test_the_turn_ceiling_wrapper_does_NOT_prefetch():
    """Step 3. A prefetching wrapper would let the inner generator run ahead of the consumer,
    and the log line would stop proving delivery."""
    i = SRC.index("async def _bounded_turn_stream(")
    body = SRC[i:i + 4000]
    assert "await asyncio.wait_for(iterator.__anext__(), remaining)" in body, (
        "_bounded_turn_stream no longer pulls one item at a time under wait_for; if it now "
        "buffers or reads ahead, a logged pass is no longer proof the consumer processed it"
    )
    for forbidden in ("create_task", "Queue(", "gather("):
        assert forbidden not in body, (
            f"_bounded_turn_stream now uses {forbidden!r} — that is a prefetch shape, and it "
            "breaks the ordering argument this row's narrowing rests on"
        )


def test_every_terminal_write_reports_how_many_passes_it_carried():
    """2026-08-30 — the THIRD number the gap has never had.

    A gap today gives two figures: what the log printed, and what the column ended up holding.
    Those cannot separate "a write carried too few entries" from "the last write that carried any
    ran too early". `adv=` on the terminal-persist line makes the sequence of writes for one
    msg_id reconstruct itself from the log alone.

    Pinned because it is a DIAGNOSTIC and diagnostics are exactly what gets tidied away: it earns
    its place only on the ~1-in-15 session that reproduces, so nothing else will miss it if it
    disappears.
    """
    i = SRC.index("terminal-persist: saved")
    line = SRC[i:i + 400]
    assert "adv=%s" in line, (
        "the terminal-persist log no longer reports how many per-pass entries the write carried"
    )
    assert "seg=%s" in line, "the terminal-persist log no longer reports the segment"
    assert "_adv_n" in SRC and "_adv_seg" in SRC


def test_the_count_is_taken_from_what_is_WRITTEN_not_from_the_recorder():
    """🔴 THE WHOLE POINT. Reading the live recorder here would print what the recorder holds at
    log time, which is the number already known to be right — the open question is what the WRITE
    carried. It must be measured off the `advertised_tools` argument."""
    i = SRC.index("_adv_n = len(")
    assert SRC[i:i + 80].startswith("_adv_n = len(advertised_tools)"), SRC[i:i + 80]
