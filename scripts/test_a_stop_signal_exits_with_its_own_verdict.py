"""A loop's stop instrument must EXIT with the verdict it PRINTS.

🔴 THE DEFECT THIS PINS, measured 2026-09-03. `scripts/toolloop/problem_remaining.py` printed

    🔴 STOPPING IS NOT YET LEGITIMATE. 13 problem(s) have every tool proven and do NOT meet
       the CLEARED definition ...

and returned **0**. So `docs/plans/2026-08-22-tool-resolution-RUNBOOK.md` carried
`STATUS: COMPLETE (2026-09-02)` while the loop's own generator refused the stop, and every CI
check or `$?` read scored that refusal as a pass. Thirteen unwritten invariants stayed invisible
behind a green exit code.

🔴 AND IT IS THE THIRD ITERATION OF THE SAME BUG. The ledger records two earlier fixes to this
same stop signal (rows 4812 and 5713): the first taught it to CHECK the definition it printed,
the second stopped it calling a problem CLEARED on the tool count alone. Both corrected what the
function PRINTS. Neither touched what it RETURNS, so the signal stayed unusable by anything but a
human reading scrollback.

WHY THIS TEST RUNS THE SCRIPT rather than reading its source. A substring assertion over
`problem_remaining.py` would match the `return 1 if unsound else 0` line while proving nothing
about what the process actually hands back — and this repo has already shipped three guards that
passed with their fix deleted, because they matched an import line, a dead string, or a comment.
The only honest check is the exit status of a real run.

NOTE ON SCOPE: this asserts the AGREEMENT, not a particular verdict. When the 13 invariants are
finally written the script will print "Stopping is legitimate" and exit 0, and this test must
keep passing unchanged — it pins the relationship, never the number.
"""
from __future__ import annotations

import pathlib
import subprocess
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "toolloop" / "problem_remaining.py"

REFUSES = "STOPPING IS NOT YET LEGITIMATE"
ALLOWS = "Stopping is legitimate"


@pytest.fixture(scope="module")
def run() -> tuple[int, str]:
    if not SCRIPT.is_file():
        pytest.skip(f"{SCRIPT} not present")
    p = subprocess.run([sys.executable, str(SCRIPT)], cwd=ROOT,
                       capture_output=True, text=True, timeout=600)
    return p.returncode, p.stdout + p.stderr


def test_the_script_actually_ran(run):
    """Guard the guard: a crashed or skipped run must fail loudly, not pass vacuously.

    Without this, a script that died on an import would print neither verdict, both assertions
    below would be trivially satisfied, and the gate would go green while measuring nothing.
    """
    code, out = run
    assert out.strip(), "the stop instrument produced no output at all"
    assert (REFUSES in out) or (ALLOWS in out) or ("NEXT — cycle" in out), (
        "the run reached neither verdict nor a next-cycle report — it did not complete:\n"
        + out[-1500:])


def test_a_printed_refusal_is_a_nonzero_exit(run):
    code, out = run
    if REFUSES not in out:
        pytest.skip("this run did not refuse — nothing to check here")
    assert code != 0, (
        "the instrument printed STOPPING IS NOT YET LEGITIMATE and exited 0. A green exit over a "
        "printed refusal is how thirteen unwritten invariants stayed invisible behind a runbook "
        "that said COMPLETE.")


def test_a_printed_allowance_is_a_zero_exit(run):
    code, out = run
    if ALLOWS not in out:
        pytest.skip("this run did not allow stopping — nothing to check here")
    assert code == 0, (
        "the instrument said stopping is legitimate and then exited non-zero — a caller cannot "
        "act on a signal that contradicts itself in the other direction either.")


def test_the_two_verdicts_are_mutually_exclusive(run):
    """Both printed at once would make the exit code meaningless whichever value it took."""
    _code, out = run
    assert not (REFUSES in out and ALLOWS in out), (
        "the instrument printed BOTH verdicts in one run; the exit code cannot agree with both")
