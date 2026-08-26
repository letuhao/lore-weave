"""D-ANSWER-GATE-CALIBRATED-ON-THE-BROKEN-POPULATION.

    THE INVARIANT. Assert the PROPOSITION, not a symptom of its absence — and a negative phrase
    gate must state, on the scenario, why that phrase is a false claim about THIS fixture.

`none_of:['currently offer']` discriminated 9 of 10 on the BROKEN population and then failed 4
of 5 CORRECT replies after the fix, because the corrected answer must NAME the thing it is not
in order to disclaim it. A gate that has only ever seen the broken population is untested in
the only direction that matters.

🔴 THE SWEEP THE ROW ASKED FOR WAS RUN, AND IT CAME BACK CLEAN — which is worth more than a
finding here, because it is the direction that could have refuted the whole approach.

    51  negative phrase gates across the corpus
    30  recorded answers from a batch that PROVED its tool (the "fixed population")
     0  confirmed mis-calibrations

The one apparent hit is kg-entity-edge-timeline's `"couldn't find"` firing on "i couldn't find
any information about Aldric Vane…". Its `why` says the node EXISTS and turn 1's graph read
shows it — so that answer is the failure the gate was written to catch, and the gate is
working. Read the other way it would have been a false positive; the `why` is what settles it,
which is the whole argument for requiring one.

🔴 AND A GATE I ALMOST SHIPPED WAS REFUTED BY READING ITS OWN OUTPUT. I first proposed requiring
each `why` to record a MEASUREMENT over both populations, and scored 13 of 51 compliant. Reading
the other 38 shows the test was wrong, not the scenarios: they justify from the FIXTURE — "Both
maps exist", "Ironhold is a seeded marker", "The book has two chapters", "zero translations" —
which is GROUND TRUTH and strictly stronger than a population measurement. Shipping that gate
would have flagged 38 correct justifications and been switched off within a day.

So what remains mechanical is narrow and honest: a negative phrase gate must carry a `why` AT
ALL. 47 of 51 already do. Whether a given `why` argues the proposition or merely a symptom is a
judgement no substring can make, and this file does not pretend otherwise.
"""
from __future__ import annotations

import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
BASELINE = ROOT / "contracts" / "negative-gate-without-a-reason-baseline.json"


def negative_gates():
    """(file, id, phrases, why) for every scenario carrying a none_of / must_not_contain."""
    for f in sorted((ROOT / "scripts" / "toolloop").glob("scenarios-*.json")):
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        for s in d.get("scenarios", []):
            ae = s.get("answer_expect")
            if not isinstance(ae, dict):
                continue
            negs = list(ae.get("none_of") or []) + list(ae.get("must_not_contain") or [])
            if negs:
                yield f.name, s.get("id"), negs, str(ae.get("why") or "").strip()


def offenders() -> set[str]:
    return {f"{fn}::{sid}" for fn, sid, _, why in negative_gates() if not why}


def _baseline() -> set[str]:
    if not BASELINE.exists():
        return set()
    return set(json.loads(BASELINE.read_text(encoding="utf-8"))["scenarios"])


def test_the_scan_sees_the_corpus():
    """ANTI-VACUITY. If the schema moves, everything below passes for free."""
    all_ = list(negative_gates())
    assert len(all_) >= 40, f"only {len(all_)} negative phrase gates found"
    assert sum(1 for *_, why in all_ if why) >= 40, "almost none carry a why — re-derive"


def test_no_NEW_negative_gate_without_a_reason():
    """THE GATE, shrink-only. A bar with no stated reason is a place to hide a mis-calibration,
    and this row is what that costs: a phrase that discriminated 9 of 10 and then failed 4 of 5
    correct replies."""
    new = sorted(offenders() - _baseline())
    assert not new, (
        "these scenarios forbid a phrase and do not say why it is a FALSE CLAIM about their own "
        "fixture:\n  " + "\n  ".join(new)
        + "\n\nWrite the proposition the phrase contradicts — 'both maps exist', 'the fixture has "
          "zero translations'. A phrase the broken answer merely happened to use is the shape "
          "that breaks the day the tool is fixed."
    )


def test_the_baseline_only_shrinks():
    stale = sorted(_baseline() - offenders())
    assert not stale, f"no longer offenders, remove from {BASELINE.name}: {stale}"


def test_the_baseline_is_small_and_named():
    """It is FOUR scenarios, in older duplicate files. Their reasons are not invented here: a
    justification written by someone who did not choose the phrase is not a justification."""
    b = json.loads(BASELINE.read_text(encoding="utf-8"))
    assert b["count"] == len(b["scenarios"])
    assert 0 < b["count"] <= 8, b["count"]


def test_the_measurement_gate_that_was_REFUTED_is_not_here():
    """🔴 A GUARD AGAINST MY OWN REJECTED DESIGN. Requiring each `why` to record a two-population
    MEASUREMENT scores 13 of 51 — and the other 38 justify from the FIXTURE, which is ground
    truth and stronger. If that rule ever reappears it will flag 38 correct justifications, so
    the count is pinned here as the reason it must not."""
    fixture_style = 0
    for *_, why in negative_gates():
        low = why.lower()
        if any(k in low for k in ("before", "after", "broken", "fixed", "recalibrat",
                                  "population", "discriminat", "measured")):
            continue
        if why:
            fixture_style += 1
    assert fixture_style >= 25, (
        f"only {fixture_style} whys argue from the fixture — re-derive whether a measurement "
        "rule would now be right"
    )
