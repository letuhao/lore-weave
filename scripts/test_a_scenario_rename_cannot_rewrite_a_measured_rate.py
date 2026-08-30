"""A selection rate's DENOMINATOR must not be editable by renaming a scenario.

🔴 THE DEFECT THIS PINS, found 2026-08-30 by chasing an anomaly rather than accepting it.

`selection_rate.derive()` built its `scenario id -> expect_tool` map from the scenario files AS
THEY ARE NOW, and counted runs recorded weeks earlier. So retiring or renaming a scenario id
silently removed every historical run of it from the denominator. The DQ-T50 both-arms split did
exactly that — correctly, it replaced one scenario with two better ones — and the side effect was:

    composition_build_cast_and_graph    30/125 = 0.24   before
                                        35/70  = 0.50   after the rename
                                        60/155 = 0.387  with history restored

The denominator SHRANK from 125 to 70 while the corpus only grew, and the rate nearly doubled
with no behaviour having changed at all. 117 non-errored runs across 5 ids were orphaned.

IT IS NOT COSMETIC. That rate GATES VERDICTS: DQ-T51's reachability bar (0.4507) decides whether
`called 0/5` is read as evidence about a tool or as a lost draw, and 0.24 -> 0.50 moved this tool
ACROSS it. A scenario rename could therefore change how a zero-call batch is judged. It also
briefly looked like corroboration of a real finding — the challenger's measured inversion on
D-A-HOT-SET-INCUMBENT-WITH-A-RECIPE-BEATS-AN-R1-FORCED-CHALLENGER — which is the worst kind of
artefact, one that agrees with what you already believe.

THE FIX is contracts/scenario-expect-tool-history.json: append-only, seeded by reading every
version of every scenarios-*.json across 324 commits, so a retired id keeps its meaning. Current
declarations still win; history only supplies ids nobody declares any more.

This file guards the two ways that fix can rot: the history shrinking, and runs quietly falling
outside every denominator again.
"""
from __future__ import annotations

import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "toolloop"))

import selection_rate as sr  # noqa: E402

HISTORY = json.loads((ROOT / "contracts" / "scenario-expect-tool-history.json").read_text(
    encoding="utf-8"))

#: The orphan population at the moment the defect was found and fixed. The one survivor is
#: `glossary-build-is-it-in-the-catalogue` (5 runs), whose declaration carries no `expect_tool` in
#: any commit — it is below MIN_RUNS and cannot move a rate, and it is named rather than rounded
#: away so that a LATER orphan is visible as an increase rather than lost in a tolerance.
ORPHANS_AT_THE_FIX = 5


class TestTheHistoryOnlyGrows:
    def test_it_is_not_empty_so_the_guard_is_not_vacuous(self):
        """This loop has shipped a guard over an empty set before."""
        assert HISTORY["count"] >= 300, HISTORY["count"]
        assert len(HISTORY["map"]) == HISTORY["count"]

    def test_every_CURRENTLY_declared_id_is_recorded(self):
        """The append step runs with the deriver. If a declared id is missing from history, the
        next rename of it loses its runs — which is the whole defect, back again."""
        missing = sorted(set(sr.derive()["_want"]) - set(HISTORY["map"]))
        assert not missing, (
            f"{len(missing)} scenario id(s) are in use but absent from the history contract, so "
            f"retiring them would orphan their runs — run the deriver: {missing[:10]}")

    def test_the_deprecated_tool_name_is_never_the_answer(self):
        """Two ids ever declared two tools, both from the composition_glossary_build ->
        composition_build_cast_and_graph rename. Resolving toward the dead name would attribute
        live runs to a deprecated tool and quietly empty the successor's denominator."""
        assert "composition_glossary_build" not in set(HISTORY["map"].values())


class TestRunsDoNotFallOutOfEVERYDenominator:
    def test_orphaned_runs_have_not_grown(self):
        """🔴 THE ONE THAT WOULD HAVE CAUGHT THE ORIGINAL. 117 runs sat outside every denominator
        and nothing said so; the rate simply moved. Orphans are not forbidden — a scenario with no
        `expect_tool` is legitimate — but a GROWING orphan population means ids are being retired
        without their meaning being kept."""
        orphans = sr.unmapped_runs()
        total = sum(orphans.values())
        assert total <= ORPHANS_AT_THE_FIX, (
            f"{total} non-errored runs now map to no tool, up from {ORPHANS_AT_THE_FIX} when this "
            f"was fixed. A scenario id has been retired without its history being kept, and every "
            f"rate it fed is now measuring a different population: {orphans}")

    def test_the_orphan_report_actually_looks_at_the_corpus(self):
        """ANTI-VACUITY. `unmapped_runs` returning {} because it read nothing would pass the guard
        above forever, and this loop has drawn a conclusion from a silently-empty capture before."""
        want = sr.derive()["_want"]
        assert len(want) >= 300, len(want)
        assert sr.derive()["measured"] >= 50


class TestTheBarStillClassifiesTheSameTools:
    def test_restoring_the_history_did_not_move_a_tool_across_the_bar(self):
        """The fix RESTORES a population, so it changes rates — and the one it changed most,
        composition_build_cast_and_graph, lands back where it was before the rename rather than
        somewhere new. A fix that reshuffled the band would need its own justification."""
        d = sr.derive()
        r = d["rates"]["composition_build_cast_and_graph"]
        assert r["runs"] >= 150, (
            f"the restored denominator is {r['runs']}, not the ~155 the history recovers — the "
            "orphaned runs have fallen out again")
        assert r["rate"] < sr.LOTTERY_BELOW, (
            f"composition_build_cast_and_graph is at {r['rate']} and no longer in the lottery "
            "band. If that is a real behaviour change it is a finding; if it is a denominator "
            "changing composition again, it is this defect returning")
