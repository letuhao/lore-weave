"""P15-TRANSPORT-STALL — a turn the transport killed measures nothing about the tool.

🔴 THE INVARIANT. "A tool cannot be adjudicated on a turn the transport killed. Either the stall
is fixed, or its tools are stated as unmeasurable and why."

THE BAR EXISTS AND NOTHING ASSERTED IT. Measured 2026-09-03 by replacing gate.py's
`self._check(not errs, ...)` with `self._check(True, ...)` — excusing the LIVE clean bar entirely,
which is the widening DQ-T40 explicitly forbade ("DO NOT widen gate.py's excused set ... widening
the excuse would weaken a LIVE bar, which this loop's rules forbid"). All 11 tests in
test_an_unmeasurable_tool_earns_that_word.py stayed GREEN. That file guards the third terminal
STATE; nothing guarded the bar that makes the state necessary.

That is the FIFTH instance of one shape in this loop — after P14's transitive walk, P7's fact leg,
P12's silent-turn fallback and P16's guard. Each was implemented, argued for at length, and
assertable-away without a test noticing.

WHY THE DIAGNOSIS MATTERS TO THE BAR, and why it is not one substring. Three failure classes reach
this code as "a run has an `error`", and they point at three different places:

    PROVISION…   the SEED could not build the fixture      -> not the platform
    SNAPSHOT…    the store could not be READ               -> Postgres, not the provider
    anything else                                          -> the transport

The verdict is identical — this run is not evidence about the tool — and the loop has already paid
for conflating them: an `err` count of 5 was written up as "5 of 5 lost to transport errors" in
three commits while every run said SEED ASSERTION FAILED.
"""
from __future__ import annotations

import importlib.util
import pathlib

import pytest

GATE = pathlib.Path(__file__).resolve().parent / "toolloop" / "gate.py"


def _gate_module():
    # 🔴 gate.py IMPORTS `call_outcome` BY BARE NAME, so its own directory must be on sys.path
    # before it will load at all. SESSION_HANDOFF carries the warning verbatim ("must cd; it
    # imports call_outcome by bare name") and this test hit it on its first run: every assertion
    # failed with ModuleNotFoundError, which reads exactly like "the bar is broken".
    import sys
    d = str(GATE.parent)
    if d not in sys.path:
        sys.path.insert(0, d)
    spec = importlib.util.spec_from_file_location("toolloop_gate", GATE)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _run_live(tool_entry):
    """Run gate.py's LIVE bars over one tool entry and return (ok, fail) label lists."""
    m = _gate_module()
    if not hasattr(m, "Gate"):  # the class moved — say so rather than passing vacuously
        pytest.fail("gate.py no longer exposes the checker class this test drives; re-anchor it")
    checker = m.Gate({}, GATE)  # batch + path are unused by live(); the bars read the entry
    checker.ok, checker.fail = [], []
    checker.live(tool_entry)
    return checker.ok, checker.fail


def _entry(errors):
    """A run set at or above MIN_REPEATS, so the REPEATS bar never masks the CLEAN one.

    🔴 THE FIRST DRAFT USED THREE RUNS AND READ THE WRONG BAR. `live()` checks repeats before
    cleanliness, so a short set fails for a reason that has nothing to do with the transport --
    and a test calibrated on that would have asserted the repeats bar while claiming to assert
    the clean one."""
    m = _gate_module()
    runs = [{"error": e} if e else {"ok": True} for e in errors]
    while len(runs) < getattr(m, "MIN_REPEATS", 3):
        runs.insert(0, {"ok": True})
    return {"tool": "composition_motif_link_edit", "runs": runs}


def test_a_transport_error_fails_the_LIVE_clean_bar():
    """🔴 THE ORIGINAL INSTANCE. composition_motif_link_edit lost 4 of 5 runs to the stall and
    gate.py refused to conclude ANY state. Excusing that is what this asserts against."""
    _ok, fail = _run_live(_entry([None, None, "upstream sent \"error\" with no error message"]))
    assert any("LIVE clean" in f for f in fail), (
        "a run that errored did not fail the LIVE clean bar — a turn the transport killed is "
        "being read as evidence about the tool, which is P15's invariant exactly"
    )


def test_a_clean_run_set_passes_the_bar():
    """The control. Without it the test above passes on a bar that fails everything."""
    ok, fail = _run_live(_entry([None, None, None]))
    assert any("LIVE clean" in o for o in ok), "the bar now fails a clean run set"
    assert not any("LIVE clean" in f for f in fail)


@pytest.mark.parametrize("prefix,points_at", [
    ("PROVISION MCPToolError: the seed hit a per-session cap", "the fixture"),
    ("SNAPSHOT could not read the store", "Postgres"),
])
def test_the_bar_still_fails_but_names_the_RIGHT_cause(prefix, points_at):
    """Same verdict, different diagnosis. Reading the error STRING rather than its presence is
    what stops 'the seed could not build the fixture' being written up as a transport failure —
    which happened, in three commits."""
    _ok, fail = _run_live(_entry([None, prefix]))
    line = next((f for f in fail if "LIVE clean" in f), "")
    assert line, "an errored run must still fail the bar whatever its class"
    assert "transport failure is not a model result" not in line, (
        f"a {prefix.split()[0]} failure is being reported as a transport failure, which sends the "
        f"reader at the provider when the cause is {points_at}"
    )
