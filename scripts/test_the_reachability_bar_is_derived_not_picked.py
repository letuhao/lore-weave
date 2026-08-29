"""DQ-T51, answered by the owner 2026-08-28.

    "STATE A RATE BAR. A tool chosen in >= N of M runs counts as reachable; below that the row is
     a SELECTION defect, not an unproven tool. The owner declined letting a direct probe satisfy
     LIVE — the real chat path stays the bar.

     N/M IS NOT CHOSEN YET AND MUST BE DERIVED, not picked round. It comes from the measured
     distribution of selection rates across the batches already on disk, and the derivation is
     written down beside it — a bar invented to fit the current results would retire exactly the
     rows it should catch."

THE DERIVATION is the batch's own POWER, not a gap eyeballed in a histogram. A LIVE batch runs
K=5 and concludes on whether the tool was called at least once; for a tool picked with
probability p that batch contains a call with probability 1-(1-p)^K. Solving for 95%:

    p = 1 - (1 - 0.95) ** (1/5) = 0.4507

🔴 AND THE DATA MAKES THE EXACT VALUE IRRELEVANT, which is what stops it being a number invented
to fit: no measured tool lies in [0.400, 0.500), so every bar from 0.41 to 0.49 classifies the
identical set. That band held across a data refresh (68 tools/20 below -> 74/22) — a gap that
survives the data changing underneath it is a property of the distribution, not of a snapshot.
"""
from __future__ import annotations

import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "toolloop"))

import selection_rate  # noqa: E402

CONTRACT = json.loads(
    (ROOT / "contracts" / "tool-selection-rates.json").read_text(encoding="utf-8"))
RATES = sorted((v["rate"] if isinstance(v, dict) else v) for v in CONTRACT["rates"].values())


class TestTheBarIsDerivedFromTheBatchesOwnPower:
    def test_it_is_the_95_percent_power_point_for_K5(self):
        assert selection_rate.LIVE_BATCH_K == 5
        assert selection_rate.LIVE_POWER == 0.95
        assert abs(selection_rate.LOTTERY_BELOW - (1 - 0.05 ** (1 / 5))) < 1e-12

    def test_a_tool_AT_the_bar_gives_a_K5_batch_95_percent_power(self):
        p = selection_rate.LOTTERY_BELOW
        assert abs((1 - (1 - p) ** 5) - 0.95) < 1e-9

    def test_it_is_COMPUTED_not_typed(self):
        """🔴 THE OWNER'S ACTUAL CONSTRAINT. A literal would be a picked number wearing a
        derivation's docstring; the value has to fall out of the function."""
        src = (ROOT / "scripts" / "toolloop" / "selection_rate.py").read_text(encoding="utf-8")
        assert "LOTTERY_BELOW = _reachable_bar()" in src, (
            "the bar is assigned a literal again — it must be derived at import"
        )

    def test_changing_the_batch_size_moves_the_bar(self):
        """If K ever changes, the bar must follow. A bar that survives a change in the thing it
        was derived FROM has stopped being derived."""
        assert selection_rate._reachable_bar(k=10) < selection_rate.LOTTERY_BELOW
        assert selection_rate._reachable_bar(k=3) > selection_rate.LOTTERY_BELOW


class TestTheChoiceIsRobustToWhereInTheGapItSits:
    def test_no_measured_tool_lies_in_the_band(self):
        below = [r for r in RATES if r < 0.5]
        above = [r for r in RATES if r >= 0.5]
        assert below and above, "the distribution has collapsed to one side; re-derive the bar"
        assert max(below) <= 0.400 + 1e-9
        assert min(above) >= 0.500 - 1e-9

    def test_every_bar_across_the_band_classifies_identically(self):
        counts = {b: sum(1 for r in RATES if r < b)
                  for b in (0.41, 0.43, 0.45, 0.47, 0.49)}
        assert len(set(counts.values())) == 1, (
            f"the empty band has closed — the bar's exact value now changes the verdict: {counts}. "
            "Re-derive it and re-state the derivation rather than keeping this number."
        )

    def test_the_derived_bar_sits_inside_that_band(self):
        below = [r for r in RATES if r < 0.5]
        above = [r for r in RATES if r >= 0.5]
        assert max(below) <= selection_rate.LOTTERY_BELOW < min(above)

    def test_the_derivation_travels_WITH_the_contract(self):
        """The owner asked for the derivation to be written down beside the bar. A number in a
        JSON file with the reasoning only in a Python docstring is half of that."""
        assert "_bar_derivation" in CONTRACT
        text = CONTRACT["_bar_derivation"]
        assert "0.4507" in text and "95%" in text and "[0.400, 0.500)" in text


class TestTheGateActuallyAppliesIt:
    SRC = (ROOT / "scripts" / "toolloop" / "gate.py").read_text(encoding="utf-8")

    def test_below_the_bar_is_a_SELECTION_verdict_not_a_live_failure(self):
        assert "SELECTION below the reachability bar" in self.SRC

    def test_it_still_refuses_to_call_the_tool_proven(self):
        """🔴 THE LINE THIS MUST NOT CROSS. The owner reclassified the verdict; they did not
        excuse it. A below-bar tool is not proven — it is a selection defect — so the check must
        still be FALSE, or the bar becomes a way to pass a tool nobody could get called."""
        i = self.SRC.index("SELECTION below the reachability bar")
        window = self.SRC[i - 400:i]
        assert "self._check(\n                False," in window, (
            "the SELECTION branch no longer fails the bar — a below-bar tool could now conclude "
            "as proven, which is the opposite of the ruling"
        )

    def test_the_gate_reads_the_derived_constant_and_not_a_copy(self):
        """🔴 CHECKED AGAINST THE CODE, NOT THE TEXT. The first version of this test searched the
        raw source for "0.45" and failed on the explanatory COMMENT that quotes the derivation
        (0.4507) — the instrument reporting on itself. It now parses the file and looks only at
        numeric LITERALS in real expressions, which is the thing that would actually be a
        drifting copy."""
        import ast

        assert "selection_rate.LOTTERY_BELOW" in self.SRC
        tree = ast.parse(self.SRC)
        suspicious = [
            n.value for n in ast.walk(tree)
            if isinstance(n, ast.Constant) and isinstance(n.value, float)
            and 0.30 <= n.value <= 0.60
        ]
        assert not suspicious, (
            f"a hard-coded copy of the reachability bar appeared in gate.py's CODE: {suspicious}. "
            "It must read selection_rate.LOTTERY_BELOW so the two cannot drift."
        )
