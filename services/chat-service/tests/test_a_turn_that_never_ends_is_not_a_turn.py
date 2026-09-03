"""DQ-T56 — a chat turn must have a ceiling, and a turn that hits it must SAY so.

THE DEFECT, measured live before any of this was written: one pass advertised, then three
minutes of provider silence, then the CLIENT's disconnect is the only thing that ends the turn.
Server-side, provider-registry's own job rows show `chat` completions that ended `failed`
running to 1,858.9s — half an hour after the browser gave up. The author is left with their own
message standing alone, and the turn's fate in an `outcome` column only the database can read.

THE INVARIANT, in two halves, both decided by the owner:

  (1) A TURN IS BOUNDED AS A WHOLE. Not by an idle-read cap — that competes with a slow FIRST
      token and is the thing that once ReadTimeout'd Gemma-4 26B mid-thought, so
      `llm_stream_idle_read_timeout_s` stays 0. The bound is on total turn duration.

  (2) A TURN THAT DIES SAYS SO. A terminal row carrying an explicit "this turn did not
      complete", not a blank assistant bubble and not a column.

WHAT THIS FILE PROVES AND WHAT IT DOES NOT. Everything here is a real functional exercise of
`_bounded_turn_stream` — the ONE chokepoint every provider await in a turn passes through. It
does NOT drive `_emit_chat_turn`, because nothing in this suite can: that generator needs a
pool, credentials, a billing client and a provider. So half (2) — the arm being REACHED and
handed the right content — is proven by the live run, not here, and this docstring says so
rather than letting a green file imply otherwise.
"""
import asyncio
import time

import pytest

from app.services.stream_service import (
    TurnCeilingExceeded,
    _aclose_quietly,
    _bounded_turn_stream,
    _humanize_seconds,
)


# ── stream shapes ──────────────────────────────────────────────────────────────────────────

async def _silent_after_one(first="advertised"):
    """THE ORIGINAL INSTANCE. One chunk, then silence that never ends — the exact live shape:
    a pass advertises its tools and the provider never speaks again."""
    yield {"content": first}
    await asyncio.Event().wait()  # never set
    yield {"content": "unreachable"}


async def _silent_from_the_start():
    """The harder shape: nothing at all, so there is no chunk on which to check a deadline."""
    await asyncio.Event().wait()
    yield {"content": "unreachable"}


async def _chatty(n=40, gap=0.01):
    """Never silent for long, but long overall. An IDLE cap can never fire on this stream;
    a whole-turn ceiling must."""
    for i in range(n):
        await asyncio.sleep(gap)
        yield {"content": str(i)}


async def _prompt(n=3):
    for i in range(n):
        yield {"content": str(i)}


async def _drain(stream):
    return [c async for c in stream]


# ── (1) the ceiling fires, and fires on the AWAIT ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_a_provider_that_goes_silent_after_one_chunk_is_bounded():
    """The instance. Without the ceiling this coroutine never returns."""
    got = []
    t0 = time.monotonic()
    with pytest.raises(TurnCeilingExceeded):
        async for chunk in _bounded_turn_stream(
            _silent_after_one(), started_at=t0, ceiling_s=0.3
        ):
            got.append(chunk)
    assert got == [{"content": "advertised"}], (
        "the chunk that DID arrive must still reach the turn — the ceiling ends the turn, it "
        "does not discard the work already streamed"
    )
    assert time.monotonic() - t0 < 3.0, "the ceiling did not actually bound anything"


@pytest.mark.asyncio
async def test_a_provider_that_never_speaks_at_all_is_bounded():
    """🔴 THE ONE A CHUNK-TRIGGERED CHECK CANNOT CATCH. A deadline evaluated when a chunk
    arrives never runs here, because no chunk ever arrives. This is why the bound is imposed ON
    the `__anext__` await rather than checked around it."""
    t0 = time.monotonic()
    with pytest.raises(TurnCeilingExceeded):
        await _drain(_bounded_turn_stream(
            _silent_from_the_start(), started_at=t0, ceiling_s=0.3
        ))
    assert time.monotonic() - t0 < 3.0


@pytest.mark.asyncio
async def test_the_clock_is_the_turns_and_not_the_gap_between_chunks():
    """🔴 THE DISCRIMINATING TEST — the whole reason this is not an idle cap.

    `_chatty` is never silent for more than 10ms, so an idle-read timeout of ANY positive value
    above 10ms would let it run forever. The turn ceiling must still end it, because what is
    bounded is how long the TURN has run, not how long the provider has been quiet."""
    t0 = time.monotonic()
    got = []
    with pytest.raises(TurnCeilingExceeded) as excinfo:
        async for chunk in _bounded_turn_stream(
            _chatty(n=400, gap=0.01), started_at=t0, ceiling_s=0.3
        ):
            got.append(chunk)
    assert len(got) < 400, "the stream ran to completion — nothing was bounded"
    assert excinfo.value.elapsed_s >= 0.3


@pytest.mark.asyncio
async def test_a_turn_already_over_its_ceiling_when_it_reaches_the_stream_is_bounded():
    """`started_at` is the TURN's clock, set before the first line is emitted — so a turn that
    burnt its budget building context arrives here already expired and must not get a fresh
    one."""
    with pytest.raises(TurnCeilingExceeded):
        await _drain(_bounded_turn_stream(
            _prompt(), started_at=time.monotonic() - 100.0, ceiling_s=10.0
        ))


# ── (2) the ceiling does NOT fire where it must not ────────────────────────────────────────

@pytest.mark.asyncio
async def test_a_turn_inside_its_budget_is_untouched():
    """The control. If this ever goes red the ceiling is eating healthy turns, which is the
    failure mode that made an idle cap unacceptable in the first place."""
    out = await _drain(_bounded_turn_stream(
        _prompt(5), started_at=time.monotonic(), ceiling_s=30.0
    ))
    assert out == [{"content": str(i)} for i in range(5)]


@pytest.mark.asyncio
@pytest.mark.parametrize("disabled", [0, 0.0, -1.0, None])
async def test_a_disabled_ceiling_restores_the_previous_behaviour_exactly(disabled):
    """Not "approximately unbounded". A stream that WOULD have expired at any positive ceiling
    must run to completion, so an operator turning this off gets back the code that shipped
    before it — the same convention `llm_stream_idle_read_timeout_s <= 0` already uses."""
    out = await _drain(_bounded_turn_stream(
        _chatty(n=6, gap=0.05), started_at=time.monotonic() - 10_000.0, ceiling_s=disabled
    ))
    assert len(out) == 6


# ── the exception is the right KIND ────────────────────────────────────────────────────────

def test_the_ceiling_is_not_a_cancellation():
    """🔴 IF THIS INVERTS, A DEAD TURN IS RECORDED AS THE AUTHOR'S OWN CHOICE.

    `_emit_chat_turn` catches `(asyncio.CancelledError, GeneratorExit)` and writes
    `abandoned_by_user`. A ceiling expiry is the platform giving up, not a person changing their
    mind — fusing the two is the exact error `OUTCOME_ABANDONED_BY_USER`'s own comment records
    as already having happened once."""
    assert not issubclass(TurnCeilingExceeded, asyncio.CancelledError)
    assert not issubclass(TurnCeilingExceeded, GeneratorExit)
    assert issubclass(TurnCeilingExceeded, Exception)


@pytest.mark.asyncio
async def test_the_exception_carries_what_a_human_needs_to_read_it():
    """`error_detail` and the visible note are both built from these, so an expiry that cannot
    say how long it waited cannot say anything useful."""
    t0 = time.monotonic()
    with pytest.raises(TurnCeilingExceeded) as excinfo:
        await _drain(_bounded_turn_stream(
            _silent_from_the_start(), started_at=t0, ceiling_s=0.25
        ))
    exc = excinfo.value
    assert exc.ceiling_s == 0.25
    assert exc.elapsed_s >= 0.25
    assert "ceiling" in str(exc)


# ── the stalled stream is released ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_the_stalled_stream_is_closed_so_the_connection_is_released():
    """A ceiling that ends the turn but leaves the provider stream open trades a hung turn for
    a leaked connection, which is a worse defect than the one it fixes."""
    closed = []

    class _Tracked:
        def __aiter__(self):
            return self

        async def __anext__(self):
            await asyncio.Event().wait()

        async def aclose(self):
            closed.append(True)

    with pytest.raises(TurnCeilingExceeded):
        await _drain(_bounded_turn_stream(
            _Tracked(), started_at=time.monotonic(), ceiling_s=0.2
        ))
    assert closed == [True], "the stalled stream was abandoned, not closed"


@pytest.mark.asyncio
async def test_a_cleanup_failure_never_masks_the_ceiling():
    """If closing the stream throws, the turn must still end as a ceiling expiry. A cleanup
    exception replacing the real one is how a diagnosable failure becomes an unreadable one."""
    class _Angry:
        def __aiter__(self):
            return self

        async def __anext__(self):
            await asyncio.Event().wait()

        async def aclose(self):
            raise RuntimeError("connection reset during close")

    with pytest.raises(TurnCeilingExceeded):
        await _drain(_bounded_turn_stream(
            _Angry(), started_at=time.monotonic(), ceiling_s=0.2
        ))


@pytest.mark.asyncio
async def test_aclose_quietly_tolerates_an_iterator_that_cannot_be_closed():
    """`_stream_via_gateway` and `_stream_with_tools` are async generators and have `aclose`,
    but the helper must not assume it: an iterator without one is a legal async iterator."""
    class _NoClose:
        def __aiter__(self):
            return self

        async def __anext__(self):
            raise StopAsyncIteration

    await _aclose_quietly(_NoClose())  # must not raise


# ── the config default is defensible against the live distribution ─────────────────────────

def test_the_default_ceiling_sits_above_every_turn_the_store_has_recorded():
    """🔴 THIS BAR IS THE MEASUREMENT, AND IT IS ALLOWED TO GO RED.

    The longest turn measured over 8,222 live user->reply pairs is 364.9s, and that figure is
    itself a FLOOR (tool turns are stamped at their first tool boundary, not at their finish).
    The default must clear it with room, or the ceiling starts killing turns that work.

    If a future measurement finds a legitimate turn above the default, the honest repair is to
    RAISE the default and re-record the number here — not to relax this assertion."""
    from app.config import Settings

    longest_measured_turn_s = 364.9
    default = Settings().llm_turn_ceiling_s
    assert default > 0, "shipping with the ceiling off would make the whole mechanism dead"
    assert default >= 2 * longest_measured_turn_s, (
        f"default ceiling {default}s is not comfortably above the longest measured live turn "
        f"({longest_measured_turn_s}s) — it will end turns that are merely slow"
    )


# ── the visible note tells the truth at every ceiling ──────────────────────────────────────

@pytest.mark.parametrize(
    "elapsed, expected",
    [
        (20.0, "20 seconds"),     # 🔴 THE DEFECT THE LIVE RUN FOUND
        (0.4, "0 seconds"),
        (45.0, "45 seconds"),
        (89.0, "89 seconds"),
        (90.0, "2 minutes"),
        (75.0, "75 seconds"),
        (900.0, "15 minutes"),
        (1858.9, "31 minutes"),   # the longest hung turn provider-registry has recorded
    ],
)
def test_the_note_says_how_long_the_turn_actually_ran(elapsed, expected):
    """🔴 THIS EXISTS BECAUSE THE FIRST VERSION SAID "1 minute(s)" AFTER 20 SECONDS.

    `max(1, round(elapsed / 60))` is correct at the production ceiling (900s -> "15") and wrong
    at every ceiling below 90s, so reading the code proved nothing and only a real run at a
    small ceiling exposed it. Five live turns printed the false sentence five times.

    The 90s boundary is the parameterised case that matters: it is where the two branches meet,
    and a rounding fix that got the boundary wrong would pass every other row here."""
    assert _humanize_seconds(elapsed) == expected


def test_the_note_never_says_a_bare_plural_placeholder():
    """"1 minute(s)" is not a sentence a product writes to a person. The failure it signals is
    real (a duration nobody rendered), but the tell is cosmetic and cheap to guard."""
    for elapsed in (0.0, 1.0, 20.0, 60.0, 90.0, 300.0, 3600.0):
        rendered = _humanize_seconds(elapsed)
        assert "(s)" not in rendered
        assert rendered.split()[-1] in {"seconds", "minute", "minutes"}


def test_the_idle_cap_is_still_off_because_the_ceiling_replaced_the_need_for_it():
    """Half (1) of the decision, stated as an assertion: the ceiling is NOT an idle cap, and
    turning the idle cap on 'as well' would reintroduce the Gemma-4 mid-thought ReadTimeout
    this platform explicitly refused."""
    from app.config import Settings

    assert Settings().llm_stream_idle_read_timeout_s == 0.0
