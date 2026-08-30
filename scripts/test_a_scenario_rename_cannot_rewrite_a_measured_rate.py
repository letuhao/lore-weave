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
        """The fix RESTORES a population, so it changes rates. What must NOT change is which side
        of the verdict bar a tool lands on — that is what the rename defect did.

        🔴 RE-AIMED 2026-08-30 AT THE PROPERTY THE NAME CLAIMS. This asserted that ONE tool,
        composition_build_cast_and_graph, sits BELOW the bar. That was a snapshot of a day when
        both sides of the comparison happened to be below it, not a statement about the history —
        and it went red when the tool crossed on new data: two fresh batches called it 5/5 each,
        moving it 70/165 = 0.424 to 80/175 = 0.457 against a bar of 0.4507. The denominator grew
        by exactly the ten runs the numerator did, so nothing was re-composed; the tool simply got
        picked more.

        The assertion now compares the two derivations directly — WITH the history map and with it
        emptied — and requires that they classify identically. Measured 2026-08-30 over the 80
        tools present in both: ZERO depend on the history for their side of the bar, including the
        one this defect was found on (0.457 with, 0.588 without — both above). That is strictly
        stronger than the pinned value, and it cannot rot when a new batch lands.
        """
        d = sr.derive()
        r = d["rates"]["composition_build_cast_and_graph"]
        assert r["runs"] >= 150, (
            f"the restored denominator is {r['runs']}, not the ~155 the history recovers — the "
            "orphaned runs have fallen out again")

        real = sr._history
        sr._history = lambda: {}
        try:
            without = sr.derive()["rates"]
        finally:
            sr._history = real

        bar = sr.LOTTERY_BELOW
        both = [t for t in d["rates"] if t in without]
        assert len(both) >= 50, f"only {len(both)} tools in both derivations — nothing was compared"
        moved = {t: (d["rates"][t]["rate"], without[t]["rate"])
                 for t in both
                 if (d["rates"][t]["rate"] < bar) != (without[t]["rate"] < bar)}
        assert not moved, (
            "the history map decides which side of the verdict bar these tools land on, so a "
            f"scenario rename can still rewrite what `proven` means for them: {moved}")

class TestADeclarationCannotSILENTLYOVERRULETheHistory:
    """🔴 THE DOOR THE 2026-08-30 INSTANCE CAME THROUGH, NAMED. `derive()` lets a CURRENT
    declaration beat the history map — deliberately, so that deliberately changing a scenario's
    `expect_tool` takes effect. The cost is that re-declaring a RECORDED id with a different tool
    silently reattributes every historical run of it, and nothing said so.

    Restoring `scenarios-c-gbuild-restored.json` did exactly that: it reused the recorded id
    `composition-glossary-build-with-an-ontology` — already claimed by the DQ-T50 split, which
    maps it to composition_build_cast_and_graph — and declared glossary_propose_entities instead.
    85 runs changed owner and the pipeline tool's denominator fell 165 -> 85.

    The existing guard above caught it only because it happened to pin that one tool's value. This
    names the conflict itself, and fails with the id rather than with a number.
    """

    def test_no_id_is_declared_with_two_different_tools(self):
        seen: dict[str, set[str]] = {}
        where: dict[str, set[str]] = {}
        for f in sorted((ROOT / "scripts" / "toolloop").glob("scenarios-*.json")):
            try:
                d = json.loads(f.read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001
                continue
            for sc in d.get("scenarios", []):
                if sc.get("id") and sc.get("expect_tool"):
                    seen.setdefault(sc["id"], set()).add(sc["expect_tool"])
                    where.setdefault(sc["id"], set()).add(f.name)
        assert len(seen) >= 100, f"only {len(seen)} ids scanned — the sweep read nothing"
        clash = {k: (sorted(v), sorted(where[k])) for k, v in seen.items() if len(v) > 1}
        assert not clash, (
            "one scenario id declares two different tools, so whichever file is read last decides "
            f"which tool every recorded run of it measured: {clash}")

    def test_no_declaration_contradicts_the_recorded_history(self):
        hist = sr._history()
        assert len(hist) >= 200, f"history has {len(hist)} entries — it was not read"
        bad = {}
        for f in sorted((ROOT / "scripts" / "toolloop").glob("scenarios-*.json")):
            try:
                d = json.loads(f.read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001
                continue
            for sc in d.get("scenarios", []):
                sid, tool = sc.get("id"), sc.get("expect_tool")
                if sid and tool and sid in hist and hist[sid] != tool:
                    bad[sid] = {"declared": tool, "history": hist[sid], "file": f.name}
        assert not bad, (
            "a scenario re-declares a RECORDED id with a different tool, so every historical run "
            "of that id has silently changed owner. Give the new arm its own id — the runs already "
            f"on disk measured the tool the history names: {bad}")
