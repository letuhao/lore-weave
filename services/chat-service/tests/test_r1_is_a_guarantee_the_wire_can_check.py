"""R1 answerability promises a tool reaches the wire. Nothing checked that it did.

    "R1 answerability: request matches [book_steering_list, glossary_book_sync_apply,
     glossary_book_sync_available]"

…and glossary_book_sync_apply was absent from the advertised set on all 6 passes of all 5 runs,
while its sibling glossary_book_sync_available was present (batch c-booksync1). The request
contains its declared synonym verbatim ("Apply the standard updates").

🔴 EVERY SKIP INSIDE THE BUILDER LOGS — suppressed-by-a-breaker, absent-from-the-catalog, wrong
tier under ask/plan — and across the whole window there were ZERO such lines. Calling
`_advertise_discovery_tools` directly in the deployed container RETURNS the tool. So it left the
builder and was gone by the wire, removed by something that registered nothing.

This does not fix that removal; it makes the next one impossible to miss. R1 is the mechanism a
declared emitter rides to reach the model, and several fixes in this loop are built on it — a
silent hole in it means those fixes hold only where nothing else drops the tool, and the log
still says "matched".
"""
from __future__ import annotations

import inspect

from app.services import stream_service as ss

SRC = inspect.getsource(ss)


class TestTheBuilderPublishesWhatItForced:
    def test_the_forced_set_is_recorded(self):
        b = inspect.getsource(ss._advertise_discovery_tools)
        assert "_r1_forced.add(_ans_name)" in b, "the builder does not record what it forced"
        assert "_R1_FORCED.set(" in b, "the forced set never leaves the builder"

    def test_only_names_that_actually_REACHED_out_are_promised(self):
        """A name the builder skipped must not be reported as dropped downstream — that would
        turn this check into a source of false alarms, which is how a guard gets switched off."""
        b = inspect.getsource(ss._advertise_discovery_tools)
        seg = b.split("_R1_FORCED.set(", 1)[1][:260]
        assert 'for d in out' in seg, "the published set is not filtered against `out`"

    def test_it_is_a_ContextVar_not_a_return_value(self):
        """The two points are far apart. Threading a value through every caller in between is how
        a check ends up not being written at all — the same reasoning record_surface_withheld
        already documents for itself."""
        from contextvars import ContextVar

        assert isinstance(ss._R1_FORCED, ContextVar)
        # 🔴 NOT an assertion about its CURRENT value. The first version asserted
        # `.get() == frozenset()` and passed alone while failing in the full suite, because a
        # sibling test had set the var in the same context — an order-dependent guard, which is
        # the one kind that reports green exactly when you most need it to report red. What
        # matters here is the TYPE; the clearing is covered by its own test below.
        assert ss._R1_FORCED.name == "_r1_forced"


class TestTheWireChecksTheGuarantee:
    def test_the_check_runs_where_advertised_is_FINAL(self):
        """The file states it: 'advertised is final here: every producer and every append is
        upstream.' A check placed earlier would miss exactly the removals it exists to catch."""
        i = SRC.index("_r1_promised = _R1_FORCED.get()")
        head = SRC[max(0, i - 2600):i]
        assert "advertised = _agentruntime_wire_surface(pass_number=iteration + 1)" in head, (
            "the check does not sit after the last producer of `advertised`")

    # 🔴 THESE SLICED A FIXED BYTE WINDOW AND A COMMENT BROKE THEM. Each took SRC[i:i+900]
    # (or +1800) from the anchor. On 2026-08-26 a kept-case INFO log — six lines of comment
    # and a logger.info — was added between the anchor and the code under test, and two of
    # these went red while the property they assert was completely untouched. A byte window
    # measures how much PROSE sits in the block, which is not a property worth pinning.
    #
    # The block is now bounded by its own END (the next banner), so it grows with the code.
    @staticmethod
    def _block() -> str:
        i = SRC.index("_r1_promised = _R1_FORCED.get()")
        j = SRC.index("CP-0.1 / CP-0.2", i)
        return SRC[i:j]

    def test_a_lost_tool_is_RECORDED_not_just_logged(self):
        """A log line is not a column. record_surface_withheld is the one sink every narrowing in
        this file registers through, so a drop here shows up beside every other narrowing."""
        seg = self._block()
        assert 'stage="r1_forced_then_dropped"' in seg
        assert "record_surface_withheld(" in seg
        assert "logger.warning(" in seg, "a broken guarantee should be louder than INFO"

    def test_the_names_come_from_the_WIRE_list(self):
        # 🔴 THIS USED TO ACCEPT THE LOG LINE. It asserted only that "for td in advertised"
        # appeared SOMEWHERE in the block — and the kept-case logger.info iterates `advertised`
        # too, so it passed with the ENFORCEMENT set built from anything at all. Proven
        # 2026-08-26 by repointing `_wire_names` at another list: still green. Pin the set the
        # drop-detection actually subtracts, not any mention of the name.
        lines = self._block().splitlines()
        at = next(n for n, line in enumerate(lines) if "_wire_names = {" in line)
        assign = " ".join(lines[at:at + 5])
        assert "for td in advertised" in assign, (
            "the check compares against something other than what is sent")
        assert "_r1_promised - _wire_names" in self._block(), (
            "the drop set is not promised-minus-wire")

    def test_the_var_is_CLEARED_so_a_later_pass_cannot_inherit_it(self):
        """Passes share a context. A stale promise would report a tool as dropped on a pass that
        never forced it."""
        assert "_R1_FORCED.set(frozenset())" in self._block()
