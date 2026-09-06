"""The loop's own STOP signal must be computed from the loop's own definition.

🔴 MEASURED 2026-08-25. `problem_remaining.py` printed a four-part CLEARED definition at the
bottom of every run, checked it in `_definition_complete`, correctly found that **13 of 16
problems failed it** — and then called them CLEARED anyway, because the verdict was the TOOL
COUNT. The summary line read `cleared=16 remaining=0`, and the script signed off with:

    No problem remains — every tool in the denominator reads `proven`.
    Stopping is legitimate.

with the twelve unmet problems printed above it as a warning nobody had to act on. One of them,
P7-FALSE-ABSENCE, had written the diagnosis into its own status field in capitals: "NOW READS
'CLEARED' BY TOOL COUNT AND ITS INVARIANT STILL FAILS".

A stop signal computed from a different rule than the definition will always stop early. Two
things are pinned here: the verdict follows the definition, and no further TOOL RUN can close a
problem whose invariant is unwritten — which is why `in_progress` and `tools_proven_invariant_open`
must stay distinguishable.

SECOND, AND THE SAME SHAPE: the DQ backlog this script printed before stopping was a HAND-TYPED
list in `contracts/tool-resolution-problems.json`, last edited 2026-08-22. It named 10 open
questions while 18 were open — DQ-T36..T43 were opened after it and none was added, and three of
those were filed in that same file under `unregistered` with ledger rows reading `open`. It is
now derived from the ledger, and the hand-typed list is marked superseded.
"""
from __future__ import annotations

import copy
import importlib.util
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
LEDGER = ROOT / "contracts" / "tool-deep-dive-ledger.json"
PROBLEMS = ROOT / "contracts" / "tool-resolution-problems.json"

_spec = importlib.util.spec_from_file_location(
    "problem_remaining", ROOT / "scripts" / "toolloop" / "problem_remaining.py")
pr = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pr)


def _ledger() -> dict:
    return json.loads(LEDGER.read_text(encoding="utf-8"))


class TestTheDqBacklogIsDerived:
    def test_every_unanswered_question_is_listed(self):
        """The set is the ledger's, not a list someone remembered to update."""
        led = _ledger()
        listed = {k for k, _ in pr.open_dqs(led)}
        expected = {
            k for k, v in led["deferred_questions"].items()
            if isinstance(v, dict)
            and not str(v.get("state") or v.get("status") or "").strip().upper().startswith(
                ("ANSWERED", "SHIPPED", "CLOSED", "WITHDRAWN"))
        }
        assert listed == expected

    def test_a_question_with_no_state_counts_as_OPEN(self):
        """The safe direction. Forgetting to state an answer must not retire the question."""
        led = copy.deepcopy(_ledger())
        led["deferred_questions"]["DQ-TEST"] = {"question": "?"}
        assert "DQ-TEST" in {k for k, _ in pr.open_dqs(led)}

    def test_it_is_bigger_than_the_hand_typed_list_it_replaced(self):
        """RED on the original defect: the frozen list is still in the file, and still short.

        Not a snapshot of 17 — that would rot the same way. The assertion is the RELATION: the
        derived set strictly contains the hand-typed one, so the stale list can never again be
        the thing that gets read.

        🔴 AND THE RELATION ROTTED ANYWAY, 2026-08-28. `hand < derived` assumed the backlog only
        ever GROWS. It does not: the owner answered DQ-T31 and DQ-T32, they left the derived open
        set, and a strict-subset check went red because questions got DECIDED. A guard that fails
        when the work succeeds is measuring the wrong thing.

        What the original defect was actually about is unchanged and is what is asserted now:
        nothing in the frozen list may be a question the LEDGER has never heard of. A hand-typed
        name that the ledger cannot account for is the stale-list failure; a hand-typed name the
        ledger has since ANSWERED is the list doing its job and then being overtaken.
        """
        led = _ledger()
        probs = json.loads(PROBLEMS.read_text(encoding="utf-8"))
        hand = set(probs["deferred_questions_backlog"]["registered_open"])
        derived = {k for k, _ in pr.open_dqs(led)}
        unknown = hand - derived - set(led["deferred_questions"])
        assert not unknown, (
            f"the frozen list names questions the ledger has never heard of: {sorted(unknown)}")
        # 🔴 THE SAME ROT, ONE ASSERTION FURTHER DOWN. The relation above was repaired
        # on 2026-08-28 when two questions were answered; this one assumed the derived set
        # would always have something LEFT to add, and the owner has now answered or
        # withdrawn all 68. An empty derived set is the queue finishing, not the generator
        # failing. Keep the anti-vacuity by CROSS-DERIVING it: if the generator reports
        # nothing open, the raw ledger must independently say the same.
        if derived:
            assert derived - hand, (
                "the derived set adds nothing over the hand-typed list, so the stale list is "
                "still as good as the generator — which was the original defect")
        else:
            qs = led["deferred_questions"]
            assert qs, "the ledger holds no questions at all — this read the wrong file"
            unfinished = sorted(q for q, v in qs.items()
                                if v.get("state") not in ("answered", "withdrawn"))
            assert not unfinished, (
                f"the generator derives NO open questions while {len(unfinished)} are "
                f"neither answered nor withdrawn: {unfinished[:5]} — the generator and the "
                "ledger disagree, which is the defect this gate exists to catch")
        assert probs["deferred_questions_backlog"].get("_SUPERSEDED_2026_08_25"), (
            "the hand-typed list must be marked superseded, or someone will edit it and "
            "believe it did something")


class TestAProblemIsClearedOnlyByItsDefinition:
    def _rows(self):
        probs = json.loads(PROBLEMS.read_text(encoding="utf-8"))
        return {p["id"]: p for p in probs["problems"]}

    def test_a_problem_whose_own_status_denies_it_is_not_cleared(self):
        """Read the problems' own words. Several say NOT CLEARED in capitals."""
        for pid, p in self._rows().items():
            own = (p.get("status") or "").strip().upper()
            if own.startswith(("CLEARED", "FIXED")) or not own:
                continue
            ok, why = pr._definition_complete(p)
            assert not ok, f"{pid} says {own[:40]!r} and the checker called it complete"
            assert why

    def test_a_problem_that_says_CANNOT_BE_CLEARED_anywhere_is_not_cleared(self):
        """P8 carries it in `blocked_on_dq_2026_08_23`, not in `status`. Scanning one field
        would miss the plainest possible statement that a problem is not cleared."""
        p = {"tools": ["x"], "status": "CLEARED", "cleared_note": "all four hold",
             "some_other_field": "🔴 P8 CANNOT BE CLEARED WITHOUT DQ-T32."}
        ok, why = pr._definition_complete(p)
        assert not ok and "CANNOT BE CLEARED" in why

    def test_an_emptied_problem_is_not_cleared(self):
        """0 of 0 satisfies done == n. Emptying a problem says where its TOOLS belong, not that
        its invariant holds."""
        ok, why = pr._definition_complete({"tools": [], "status": "CLEARED",
                                          "cleared_note": "x"})
        assert not ok and "EMPTY" in why

    def test_tools_all_proven_is_not_by_itself_cleared(self):
        """The defect, in one assertion: every condition but (4) satisfied."""
        ok, why = pr._definition_complete({"tools": ["a"], "status": "CLEARED"})
        assert not ok and "cleared_note" in why


class TestTheVerdictItself:
    """`verdict()` is the thing the headline prints. Pinned directly — no re-implementation and
    no parsing of printed output, both of which are extra things that can drift. The three rule
    helpers were closures inside main() until 2026-08-25; lifting them out is what made it
    possible to test the real ones."""

    def test_all_tools_proven_but_definition_unmet_is_its_OWN_verdict(self):
        p = {"tools": ["a"], "status": "DIAGNOSED — the fix is not written"}
        assert pr.verdict(p, 1, 1) == "tools_proven_invariant_open"

    def test_cleared_requires_the_definition(self):
        p = {"tools": ["a"], "status": "CLEARED", "cleared_note": "does not cover X"}
        assert pr.verdict(p, 1, 1) == "cleared"

    def test_empty_is_not_cleared(self):
        assert pr.verdict({"tools": []}, 0, 0) == "empty"

    def test_unfinished_is_in_progress(self):
        assert pr.verdict({"tools": ["a", "b"], "status": "CLEARED",
                           "cleared_note": "x"}, 1, 2) == "in_progress"

    def test_a_verdict_of_cleared_ALWAYS_tracks_the_definition(self):
        """THE STRICTER ASSERTION THE PREDECESSOR ASKED FOR, in its own words.

        This replaced `test_the_real_partition_has_more_unmet_than_cleared`, which asserted
        `len(unmet) > len(cleared)` against the shipped contract and said of itself: "if this ever
        flips, the loop is genuinely nearly done and this assertion should be replaced by a
        stricter one". It flipped on 2026-09-03 when the last of the twelve closed.

        🔴 THE OLD SHAPE WOULD HAVE GONE RED ON SUCCESS, which is the worst kind of guard: the
        only way to make it green again is to stop finishing the work. It was also a COUNT, and a
        count cannot say that the right problems are cleared -- only how many.

        This asserts the RELATION instead, which is what the original defect was about and cannot
        go stale: a problem reads `cleared` if and only if every one of its tools is proven AND
        `_definition_complete` holds. The headline said cleared=16 remaining=0 while thirteen
        problems failed the definition; that is exactly the disagreement this now forbids, in
        either direction.
        """
        probs = json.loads(PROBLEMS.read_text(encoding="utf-8"))
        led = _ledger()
        wrong = []
        for prob in probs["problems"]:
            done = sum(1 for t in prob["tools"] if pr.state_of(led, t) == "proven")
            v = pr.verdict(prob, done, len(prob["tools"]))
            defn_ok, _why = pr._definition_complete(prob)
            tools_ok = done == len(prob["tools"])
            if (v == "cleared") != (defn_ok and tools_ok):
                wrong.append(f"{prob['id']}: verdict={v} definition={defn_ok} tools={tools_ok}")
        assert not wrong, (
            "a verdict disagrees with the definition it is supposed to be derived from — the "
            "exact defect this file exists for, whichever way it points: " + "; ".join(wrong)
        )

    def test_the_definition_can_still_refuse(self):
        """The control. Without it the assertion above passes on a definition that never
        refuses anything -- which is how a derived verdict becomes a rubber stamp."""
        ok, why = pr._definition_complete({"tools": ["a"], "status": "DIAGNOSED, not written"})
        assert not ok and "its own status says" in why
