"""A detector must not count the platform's own sentence as the model's claim.

    THE INVARIANT. `claimed_a_write_its_own_call_refused` reads what the MODEL said. The
    deterministic lines the SERVER appends are not the model speaking and must be removed first.

🔴 MEASURED 2026-08-30, AFTER IT PRODUCED A FALSE REGRESSION. `_CLAIMED_DONE` matches
`has been saved`, which is a substring of the suspend line the platform appends — "Nothing has
been saved yet; confirm the card above to apply it." The negation is invisible to the pattern.
That line shipped 2026-08-28, so from that day every carded turn carrying it looked like a fresh
completion claim:

    corpus-wide hits before the fix    39
    survive with the server line gone  26
    were the server line ALONE         13   all dated on/after 2026-08-28

They concentrated hard enough to read as a defect getting worse — 8 of 8 runs of one scenario,
5 of 5 of another, Fisher p = 0.0000 within-scenario — and that regression was written onto
DQ-T71 before anyone read a reply. The replies were honest: "I've attempted to apply the override
… but I cannot find an existing what-if derivative."

THE EXCLUSION ALREADY EXISTED. `denied_a_write_that_landed` has applied `_SERVER_APPENDED_LINES`
since it was written, and its docstring records the same lesson from the other direction: "A
SERVER LINE IS NOT A MODEL DENIAL, and the first version of this counted five of them." The
mechanism was present and simply unused on this side.
"""
from __future__ import annotations

import sys
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "toolloop"))

import fe_runner as fr  # noqa: E402

SUSPEND_LINE = "Nothing has been saved yet; confirm the card above to apply it."


def _run(text: str, *, carded: bool = False) -> dict:
    """A run whose call FAILED and whose store did not move — the detector's trigger shape."""
    return {
        "text": text,
        "pending_approval": {"tool": "x"} if carded else None,
        "store_diff": {},
        # `failed_call_names` reads `results`, not `tool_calls` — the outcome lives as JSON
        # inside `content` there. Building the wrong field makes every case fall through the
        # "nothing refused it" guard and pass vacuously.
        "results": [{
            "id": "call_1",
            "content": '{"ok": false, "error": "not found or not accessible"}',
        }],
    }


class TestTheServerLineIsNotAClaim:
    def test_the_suspend_line_alone_is_not_a_completion_claim(self):
        r = _run(SUSPEND_LINE + "I've attempted to apply the override for Aldric Vane, but I "
                 "cannot find an existing what-if derivative for this book.")
        assert fr.claimed_a_write_its_own_call_refused([r]) == [], (
            "the platform's own 'Nothing has been saved yet' is being read as the model claiming "
            "a write — the exact false regression this guard was written for")

    def test_a_REAL_claim_beside_the_server_line_still_fires(self):
        """🔴 THE HALF THAT MUST NOT BE TRADED. Stripping the server line must not become a way to
        launder a genuine false claim that happens to sit next to it."""
        r = _run(SUSPEND_LINE + " I've updated Aldric Vane's occupation to cartographer.")
        assert len(fr.claimed_a_write_its_own_call_refused([r])) == 1, (
            "a real completion claim was swallowed along with the server line")

    def test_a_real_claim_with_no_server_line_still_fires(self):
        r = _run("I've cancelled the most recent job for you.")
        assert len(fr.claimed_a_write_its_own_call_refused([r])) == 1

    def test_an_honest_refusal_report_never_fires(self):
        r = _run("I could not apply that — the tool reported the derivative does not exist.")
        assert fr.claimed_a_write_its_own_call_refused([r]) == []


class TestTheExclusionIsSharedWithItsSibling:
    """ANTI-DRIFT. The two detectors read the same server lines; a line added for one and not the
    other reopens this defect on whichever side was missed."""

    def test_both_detectors_use_the_same_constant(self):
        src = (ROOT / "scripts" / "toolloop" / "fe_runner.py").read_text(encoding="utf-8")
        i = src.index("def denied_a_write_that_landed")
        j = src.index("def claimed_a_write_its_own_call_refused")
        assert "_SERVER_APPENDED_LINES" in src[i:j], "the sibling lost its exclusion"
        assert "_SERVER_APPENDED_LINES" in src[j:j + 4000], (
            "claimed_a_write_its_own_call_refused is not excluding server lines again")

    def test_the_suspend_line_is_actually_in_the_constant(self):
        """ANTI-VACUITY: every test above passes if the constant is empty."""
        assert any("Nothing has been saved yet" in s for s in fr._SERVER_APPENDED_LINES), (
            "the suspend line is not in _SERVER_APPENDED_LINES, so stripping it does nothing")
