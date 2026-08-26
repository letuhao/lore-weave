"""D-THE-GBUILD-SCENARIO-CANNOT-TEST-ITS-OWN-FALSIFIER — the mechanical half.

    THE INVARIANT. "A falsifier EXISTS" and "the falsifier HELD" are different sentences, and a
    bar that prints the same `ok` for both is asserting the stronger one for free.

composition-glossary-build-with-an-ontology predicts POST-CALL behaviour: refuted if entities
are created with no confirm card, if the op is not `start` on a first request, or if the model
invents a run_id. Every one needs the tool to have RUN. Across 39 live runs it was never called
once — the gate blocks earlier, on `LIVE called >= 1` — so the prediction has never been
evaluated, and `[tool] DATA falsifier` still read `ok`.

MEASURED over every batch file on disk 2026-08-27: 241 of 671 tool entries (36%) carry a
falsifier on a batch where `called_count` is 0. Every one printed a bare `ok`.

🔴 IT STILL PASSES, AND THAT IS DELIBERATE. The bar asks whether a prediction was WRITTEN, and
it was. `LIVE called` already fails those batches. Making this bar fail too would red every
`blocked` conclusion that legitimately rests on a tool which could not be exercised — which is
re-freezing a baseline larger in order to look stricter, and the run forbids exactly that. What
changes is only that an UNEVALUATED prediction can no longer be read as a satisfied one.

THE OTHER HALF IS NOT MINE. Splitting the scenario into a naming arm and a selection arm is
either repairing something never well-formed or rewriting a bar so a blocked tool passes, and
the difference is intent. Raised as DQ-T50 with my recommendation, and the row is now linked by
`blocked_by_dq` — which it never was, so the generator had been offering it as actionable work.
"""
from __future__ import annotations

import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "toolloop"))

import gate as gt  # noqa: E402

EVID = ROOT / "docs" / "eval" / "toolloop" / "2026-08-14"
LEDGER = json.loads((ROOT / "contracts" / "tool-deep-dive-ledger.json").read_text(
    encoding="utf-8"))


def _bars(called: int, falsifier="if X then refuted"):
    batch = {"batch": "t", "tools": [{"tool": "zz", "falsifier": falsifier,
                                      "called_count": called, "runs": []}]}
    g = gt.Gate(batch, EVID / "b41-norail.json")
    g.run()
    return [ln for ln in list(g.ok) + list(g.fail) if "DATA falsifier" in ln]


def test_never_called_is_labelled_UNEVALUATED():
    line = next(ln for ln in _bars(0) if "not violated" not in ln and "back-dated" not in ln)
    assert "UNEVALUATED" in line
    assert "never called" in line


def test_called_at_least_once_is_NOT_labelled():
    line = next(ln for ln in _bars(3) if "not violated" not in ln and "back-dated" not in ln)
    assert "UNEVALUATED" not in line, line


def test_it_still_PASSES_so_no_blocked_conclusion_is_re_frozen():
    """🔴 THE POINT OF RESTRAINT. Failing here would red every `blocked` conclusion resting on a
    tool that could not be exercised — a baseline re-frozen larger to look stricter."""
    batch = {"batch": "t", "tools": [{"tool": "zz", "falsifier": "if X then refuted",
                                      "called_count": 0, "runs": []}]}
    g = gt.Gate(batch, EVID / "b41-norail.json")
    g.run()
    assert not any("DATA falsifier —" in ln for ln in g.fail), g.fail
    assert any("DATA falsifier (UNEVALUATED" in ln for ln in g.ok)


def test_a_MISSING_falsifier_still_fails_whatever_the_call_count():
    """PRECISION. The label is about evaluation; the bar is about existence, and it must keep
    failing when nothing was written at all."""
    for called in (0, 5):
        batch = {"batch": "t", "tools": [{"tool": "zz", "called_count": called, "runs": []}]}
        g = gt.Gate(batch, EVID / "b41-norail.json")
        g.run()
        assert any("DATA falsifier" in ln for ln in g.fail), called


def test_the_REAL_batch_the_row_names_shows_it():
    """ANTI-VACUITY against the corpus — a batch whose tool was never called."""
    p = EVID / "b41-norail.json"
    if not p.exists():
        import pytest
        pytest.skip("b41-norail is not on disk")
    batch = json.loads(p.read_text(encoding="utf-8"))
    assert any(int(t.get("called_count") or 0) == 0 for t in batch["tools"]), (
        "that batch's tool is now called — pick another instance and re-derive"
    )
    g = gt.Gate(batch, p)
    g.run()
    assert any("UNEVALUATED" in ln for ln in g.ok), g.ok


def test_the_population_is_worth_the_label():
    """ANTI-VACUITY on the size. If almost every batch called its tool, the label is decoration."""
    hit = tot = 0
    for f in sorted((ROOT / "docs" / "eval" / "toolloop").rglob("*.json")):
        if f.name.endswith("-raw.json"):
            continue
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(d, dict) or "tools" not in d:
            continue
        for t in d.get("tools") or []:
            if not isinstance(t, dict) or not t.get("falsifier"):
                continue
            tot += 1
            if int(t.get("called_count") or 0) == 0:
                hit += 1
    assert tot >= 300, tot
    assert hit >= 100, f"only {hit} of {tot} entries carry an unevaluated falsifier — re-derive"


def test_the_row_is_LINKED_to_its_deferred_question():
    """🔴 THE ROW SAID "the owner decides" IN ITS OWN WORDS AND CARRIED NO LINK, so the
    generator offered it as actionable work. `blocked_by_dq` is the only field it reads."""
    row = LEDGER["defects"]["D-THE-GBUILD-SCENARIO-CANNOT-TEST-ITS-OWN-FALSIFIER"]
    assert row.get("blocked_by_dq") == "DQ-T50"
    dq = LEDGER["deferred_questions"]["DQ-T50"]
    assert dq["state"] == "open"
    assert "my_recommendation" in dq, "a DQ without a recommendation is a question, not a hand-off"


def test_the_recommendation_does_not_decide_it():
    """SAFETY, verbatim: DQs get a RECOMMENDATION and are DECIDED BY THE OWNER. A recommendation
    that reads as a decision is a decision."""
    dq = LEDGER["deferred_questions"]["DQ-T50"]
    assert dq["state"] == "open"
    assert "I am not" in dq["my_recommendation"] or "owner" in dq["my_recommendation"].lower()
