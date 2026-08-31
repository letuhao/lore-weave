"""D-A-LOW-RATE-TOOL-CANNOT-BE-PROVEN-WITHOUT-SAMPLING-FOR-A-VERDICT — the measurable half.

    THE INVARIANT. A verdict must say at what RATE the tool was reachable, because "proven" over
    a 1-in-50 tool and "proven" over a 50-in-50 tool are not the same sentence.

The LIVE bar asks for K>=5 with at least one call. For a tool the model picks reliably that is a
fair test; for one it picks 15% of the time a fresh batch is close to a coin flip, and whichever
way it lands the batch is concludable in one direction and not the other. The loop cannot
resolve that by measuring more — re-running until a call appears is SAMPLING FOR A VERDICT, and
concluding `blocked` on a zero sample over-reads it. Both were done once and withdrawn.

MEASURED over every raw record on disk 2026-08-27: 65 tools with >= 5 non-errored runs, 19
below a 0.5 selection rate — and EVERY non-zero one of them is already `proven`.
translation_job_control is proven on 1 call in 50 runs.

🔴 THE BAR IS NOT CHANGED. What counts as reachable-at-a-rate is DQ-T51 and belongs to the
owner; changing it here would redefine `proven` for every stochastic tool in the denominator by
side effect, which IS the decision. What ships is the number, stated where the verdict is read.

It does NOT say those 19 conclusions are wrong. Each tool worked on the runs where it was
called. It says the word carries a different weight for them, and nothing recorded which.
"""
from __future__ import annotations

import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "toolloop"))

import gate as gt  # noqa: E402
import selection_rate as sr  # noqa: E402

LEDGER = json.loads((ROOT / "contracts" / "tool-deep-dive-ledger.json").read_text(
    encoding="utf-8"))
EVID = ROOT / "docs" / "eval" / "toolloop" / "2026-08-14"


def _live(tool: str, called: int = 2, runs: int = 5):
    """(the LIVE-called line, whether it PASSED). Both halves matter: an earlier version of this
    helper returned only the text, and searched `ok` and `fail` together — so the guard below
    that exists to pin the bar as PASSING was satisfied by a FAILING line saying the same words.
    Making a low rate fail the bar left every test green."""
    batch = {"batch": "t", "tools": [{"tool": tool, "called_count": called,
                                      "runs": [{"via": "fe_runner"} for _ in range(runs)]}]}
    g = gt.Gate(batch, EVID / "c-nowrite1.json")
    g.run()
    ok = next((ln for ln in g.ok if "LIVE called" in ln), None)
    bad = next((ln for ln in g.fail if "LIVE called" in ln), None)
    return (ok or bad), ok is not None


def _live_line(tool: str, called: int = 2, runs: int = 5):
    return _live(tool, called, runs)[0]


def test_a_LOW_rate_tool_carries_its_rate():
    """🔴 THE COUNTS WERE PINNED AS `1/50` AND WENT STALE THE MOMENT THE CORPUS GREW — 1/55 on
    2026-08-31, with the RATE unchanged at 0.02 and the verdict therefore identical. A guard that
    fails when more evidence arrives teaches the next reader to edit the number, which is how a
    real regression gets edited away too.

    Both halves are still asserted; the counts now come from the same contract the annotation is
    built from, so the guard checks that the line QUOTES ITS SOURCE rather than that the corpus
    has a particular size."""
    import json as _json
    rates = _json.loads(
        (ROOT / "contracts" / "tool-selection-rates.json").read_text("utf-8"))["rates"]
    r = rates["translation_job_control"]
    assert r["rate"] < 0.1, f"the fixture tool is no longer low-rate ({r}) — pick another"
    line = _live_line("translation_job_control")
    assert f"selection rate {r['rate']:.2f}" in line, line
    assert f"{r['calls']}/{r['runs']}" in line, line


def test_a_HIGH_rate_tool_does_not():
    """PRECISION. If every verdict carried the annotation it would be wallpaper."""
    assert "selection rate" not in _live_line("composition_arc_apply")


def test_a_tool_with_TOO_FEW_runs_is_not_labelled():
    """A rate over 3 runs is noise, and labelling it would invent a finding."""
    assert sr.rate_for("book_list") is None
    assert "selection rate" not in _live_line("book_list")


def _selection_line(tool: str, called: int = 0, runs: int = 5):
    """The SELECTION verdict line, if the gate raised one."""
    batch = {"batch": "t", "tools": [{"tool": tool, "called_count": called,
                                      "runs": [{"via": "fe_runner"} for _ in range(runs)]}]}
    g = gt.Gate(batch, EVID / "c-nowrite1.json")
    g.run()
    return next((ln for ln in g.fail if "SELECTION below the reachability bar" in ln), None)


def test_the_bar_itself_is_UNCHANGED():
    """🔴 THE RESTRAINT IS THE POINT. Making the bar fail on a low rate would redefine `proven`
    for 19 already-concluded tools by side effect — which is the owner's decision, not a
    consequence of stating a number.

    RE-ANCHORED 2026-08-30, and I nearly filed the change it caught as a regression of my own.
    The second half used to assert that a zero-call batch produces "never invoked" — true when
    written, and no longer true for a tool BELOW the reachability bar, because DQ-T51 was
    answered: "below that the row is a SELECTION defect, not an unproven tool." The gate now
    routes those zeros to a SELECTION verdict instead, which is the ruling working, not a defect.

    What the old assertion was really protecting is untouched and is still asserted: a zero-call
    batch MUST NOT PASS. So both sides of the ruling are pinned here rather than one —
    below the bar it fails as SELECTION, above it as "never invoked" — because a rule with only
    its convenient half guarded is how "below the bar" would quietly become "exempt"."""
    line, passed = _live("translation_job_control", called=1)
    assert "selection rate 0.02" in line, line
    assert passed, (
        "a low selection rate now FAILS the LIVE bar — that redefines `proven` for 19 "
        "already-concluded tools by side effect, which is DQ-T51's decision and not a "
        "consequence of stating a number"
    )

    # BELOW the bar: a zero is a lost draw, so it becomes a SELECTION defect — and still FAILS.
    line, passed = _live("translation_job_control", called=0)
    assert not passed, "a zero-call batch must still fail, rate or no rate"
    sel = _selection_line("translation_job_control")
    assert sel and "0.02" in sel, (
        "a below-bar zero no longer raises the SELECTION verdict DQ-T51 asked for — it has "
        f"either become a silent pass or reverted to a plain LIVE failure: {sel!r}")

    # ABOVE the bar: the zero IS evidence about the tool, and must still say so in those words.
    line, passed = _live("composition_arc_apply", called=0)
    assert not passed and "never invoked" in (line or ""), (
        "an ABOVE-bar zero-call batch no longer reports 'never invoked' — the DQ-T51 SELECTION "
        f"route has swallowed the case it was explicitly not meant to cover: {line!r}")
    assert _selection_line("composition_arc_apply") is None, (
        "a tool above the reachability bar is being excused as a SELECTION defect")


def test_the_census_is_derived_and_discriminates():
    d = sr.derive()
    assert d["measured"] >= 50, d["measured"]
    assert 5 <= d["lottery_count"] < d["measured"] // 2, (
        f"{d['lottery_count']} of {d['measured']} in the lottery band — not a discrimination"
    )
    stored = json.loads(sr.CONTRACT.read_text(encoding="utf-8"))
    assert stored["_derived_by"] == "python scripts/toolloop/selection_rate.py"
    assert set(stored["lottery"]) == set(d["lottery"]), (
        "contracts/tool-selection-rates.json is stale — re-run the deriver"
    )


def test_the_finding_that_makes_this_matter():
    """ANTI-VACUITY on the claim in the DQ: every non-zero lottery tool is already `proven`. If
    that stops being true the DQ's urgency changes and it must be re-derived, not assumed."""
    stored = json.loads(sr.CONTRACT.read_text(encoding="utf-8"))
    tools = LEDGER["tools"]
    proven = [t for t in stored["lottery"]
              if stored["rates"][t]["calls"] > 0 and (tools.get(t) or {}).get("state") == "proven"]
    nonzero = [t for t in stored["lottery"] if stored["rates"][t]["calls"] > 0]
    assert proven == nonzero, (
        f"{len(nonzero) - len(proven)} lottery tool(s) are no longer proven — re-derive DQ-T51"
    )
    assert "translation_job_control" in proven


def test_the_row_is_LINKED_and_the_recommendation_does_not_decide():
    """🔴 RE-ANCHORED 2026-08-28: DQ-T51 was answered and this row's block was correctly
    cleared, so pinning `state == "open"` punishes the decision landing rather than testing
    anything about the row. What must survive regardless is that the RECOMMENDATION, preserved
    verbatim on the DQ, never crossed into deciding it — and if the row still claims a block,
    that question must genuinely still be open."""
    row = LEDGER["defects"]["D-A-LOW-RATE-TOOL-CANNOT-BE-PROVEN-WITHOUT-SAMPLING-FOR-A-VERDICT"]
    named = row.get("blocked_by_dq")
    if named:
        assert LEDGER["deferred_questions"][named]["state"] == "open", (
            f"the row is blocked on {named}, which is no longer open")
    dq = LEDGER["deferred_questions"]["DQ-T51"]
    assert "I am not deciding it" in dq["my_recommendation"]
