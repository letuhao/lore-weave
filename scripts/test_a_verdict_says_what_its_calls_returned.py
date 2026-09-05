"""`proven` means REACHABLE, and a verdict that does not say so is read as the stronger word.

DQ-T74, answered by the owner 2026-08-31: "STATE IT, DO NOT DEMOTE. A tool's verdict must say
what its calls actually returned -- 'proven (reachable; 0 of N calls returned ok)' -- so the
silent half is audible without re-opening part of the catalogue by side effect."

    THE INVARIANT. A verdict states which sense of the word it earned.

WHY THE WORD WAS AMBIGUOUS. The LIVE bar is `called >= 1` with zero errored RUNS, and a run
errors when the HARNESS fails, not when the tool returns an error. So a tool the model reaches
for and that refuses every single time passes it. Measured over the whole chat store: fourteen
`proven` tools had never once returned ok and never even reached a confirm card --
catalog_get_book at 0 of 79, composition_conformance_run at 0 of 37.

THE MIDDLE CASE IS WHY A NAIVE COUNT OVERSTATES BY 6x. A Tier-A write that stops at a confirm
card is `ok:false`, and the gate counts that as the tool WORKING -- "the tool ran and its gate
held". An earlier pass at this measurement tested only "never returned ok" and reported 68 tools;
57 were writes legitimately held at a card. So the annotation distinguishes the two, and this
file asserts that it does.
"""
from __future__ import annotations

import json
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "toolloop"))

LEDGER = ROOT / "contracts" / "tool-deep-dive-ledger.json"
CONTRACT = ROOT / "contracts" / "tool-call-outcomes.json"

try:
    import call_outcome
except Exception as e:  # pragma: no cover - the module is the subject
    pytest.skip(f"call_outcome not importable: {e}", allow_module_level=True)


@pytest.fixture(scope="module")
def ledger():
    return json.loads(LEDGER.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def outcomes():
    assert CONTRACT.exists(), (
        f"{CONTRACT} is missing. The annotation is DERIVED from it; without the contract every "
        "verdict silently loses its clause and the defect returns unannounced.")
    return json.loads(CONTRACT.read_text(encoding="utf-8"))["tools"]


class TestTheAnnotationSaysTheRightThing:
    def test_a_tool_that_never_succeeded_says_so(self):
        """The population the row was opened on. Uses the module's own formatter, so a change to
        the wording cannot pass this by accident."""
        note = call_outcome.annotate("catalog_get_book")
        assert "0 of" in note and "returned ok" in note, (
            f"catalog_get_book's annotation is {note!r} -- it has 0 successes across 79 recorded "
            "calls and its verdict must say so")
        assert "REACHABLE, not working" in note, (
            "the annotation reports a number but never says which sense of `proven` was earned, "
            "which is the whole point of the ruling")

    def test_a_HELD_CARD_is_not_reported_as_a_failure(self):
        """🔴 THE 6x OVERSTATEMENT THIS GUARDS. A Tier-A write held at a confirm card is
        `ok:false` and the gate counts it as the tool WORKING. Reporting it as a bare
        zero-success would be the same error that turned 11 tools into 68."""
        note = call_outcome.annotate("glossary_entity_restore")
        assert "confirm card" in note, (
            f"glossary_entity_restore's annotation is {note!r}. It has 5 calls held at a card, "
            "and an annotation that says only '0 returned ok' reads as a failure it is not")

    def test_a_tool_that_SUCCEEDS_is_left_alone(self):
        """An annotation on all 204 rows would be noise, and noise is how an annotation nobody
        reads gets there. Silence is the correct output for a working tool."""
        for name in ("book_read", "glossary_search", "composition_arc_get"):
            assert call_outcome.annotate(name) == "", (
                f"{name} succeeds and still gained a verdict clause")

    def test_an_unknown_tool_says_nothing(self):
        assert call_outcome.annotate("no_such_tool_anywhere") == ""


class TestEveryRowCarriesItsVerdict:
    def test_no_row_states_a_bare_verdict_it_has_not_earned(self, ledger, outcomes):
        """The ruling is about the rows that ALREADY exist, so it is asserted over all of them.

        This is the same check `gate.py audit` runs; having it here too means a hand-edited
        ledger fails the suite and not only the gate."""
        wrong = []
        for name, row in (ledger.get("tools") or {}).items():
            state = row.get("state")
            if not state:
                continue
            want = state + call_outcome.annotate(name)
            if row.get("verdict") != want:
                wrong.append((name, row.get("verdict"), want))
        assert not wrong, (
            f"{len(wrong)} row(s) carry a verdict that does not match what their calls returned, "
            f"first: {wrong[0]}. Re-run `python scripts/toolloop/call_outcome.py`.")

    def test_the_STATE_was_not_touched(self, ledger):
        """🔴 THE OTHER HALF OF THE RULING, AND THE EASIER ONE TO BREAK. "STATE IT, DO NOT
        DEMOTE" -- annotating must never reclassify a tool, because that would re-open part of
        the catalogue by side effect, which is exactly what the owner declined."""
        for name, row in (ledger.get("tools") or {}).items():
            verdict, state = row.get("verdict"), row.get("state")
            if not state or not verdict:
                continue
            assert verdict.split(" (")[0] == state, (
                f"{name}: verdict {verdict!r} disagrees with state {state!r} — the annotation "
                "has changed a classification, which the ruling forbids")

    def test_the_defects_population_still_exists_and_is_named(self, ledger, outcomes):
        """Non-vacuity. If the annotation ever silently applied to nothing, every test above
        would still pass while the ruling was unbuilt."""
        proven = {k for k, v in (ledger.get("tools") or {}).items() if v.get("state") == "proven"}
        never = [t for t in proven
                 if (o := outcomes.get(t)) and o["done"] == 0 and o["deferred"] == 0
                 and o["calls"] >= 1]
        assert never, (
            "no `proven` tool has zero successes any more. That would be good news, but this "
            "guard cannot tell it apart from a broken derivation — re-derive with "
            "call_outcome.py and confirm before deleting this assertion.")
        for t in never:
            assert "returned ok" in (ledger["tools"][t].get("verdict") or ""), (
                f"{t} has never returned ok and its verdict does not say so")


class TestEveryCallSiteComposesTheVerdict:
    """🔴 THE BACKFILL AND THE GATE ARE TWO DIFFERENT CALL SITES, and only one of them is
    exercised by re-running call_outcome.py. `stamp()` fixes the rows that exist; `_record()` is
    what writes a verdict the NEXT time a tool is concluded, and a fix that annotates only the
    past would go quietly stale from the first new conclusion onward.

    Asserted over the SOURCE rather than by concluding a tool, because concluding one writes a
    real ledger row and this must not need a state change to prove a formatting rule.
    """

    def _gate_src(self):
        return (ROOT / "scripts" / "toolloop" / "gate.py").read_text(encoding="utf-8")

    def test_the_gate_records_an_annotated_verdict(self):
        import ast

        src = self._gate_src()
        tree = ast.parse(src)
        fn = next((n for n in ast.walk(tree)
                   if isinstance(n, ast.FunctionDef) and n.name == "_record"), None)
        assert fn is not None, "_record has been renamed — this guard is now blind"
        body = ast.unparse(fn)
        assert "call_outcome.annotate" in body, (
            "gate.py's `_record` writes the verdict and does not annotate it. Every tool "
            "concluded from now on would carry a bare state, which is the exact defect DQ-T74 "
            "ruled on.")
        assert '"verdict"' in body or "'verdict'" in body, (
            "_record does not write a `verdict` field at all")

    def test_the_audit_keeps_it_true_afterwards(self):
        """A one-time stamp is a one-day fact: every batch adds calls. Without a standing check
        a row can say '0 of 79 returned ok' long after the tool started working, which is worse
        than silence because it is confidently wrong."""
        src = self._gate_src()
        assert "stale_verdicts" in src, (
            "gate.py audit has no check that a row's verdict still matches its calls")
        assert "fix-verdicts" in src, (
            "there is no repair path, so the only way to clear the check would be to edit rows "
            "by hand — which is how a derived number becomes a typed one")


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
