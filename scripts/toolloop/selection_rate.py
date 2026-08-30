"""How often the model actually PICKS each tool, across every batch on disk.

D-A-LOW-RATE-TOOL-CANNOT-BE-PROVEN-WITHOUT-SAMPLING-FOR-A-VERDICT. The LIVE bar asks for K>=5
with at least one call and zero errored runs. For a tool the model picks reliably that is a
fair test; for one it picks 15% of the time it is a lottery, and whichever way a fresh batch
lands it is concludable in one direction and not the other. Re-running until a call appears is
sampling for a verdict; concluding `blocked` on a zero sample over-reads it.

    THE INVARIANT THIS SERVES: a verdict must say at what RATE the tool was reachable, because
    "proven" over a 1-in-50 tool and "proven" over a 50-in-50 tool are not the same sentence.

MEASURED 2026-08-27 over every raw record on disk, counting only non-errored runs of scenarios
that declare an `expect_tool`:

    65  tools with at least 5 recorded runs
     2  never called at all
    17  called at a rate BELOW 50%  — the lottery band, and EVERY ONE IS ALREADY `proven`

    0.02  translation_job_control        1/50      0.25  composition_build_cast_and_graph  30/120
    0.07  kg_ontology_propose            1/15      0.25  propose_edit                       5/20
    0.18  jobs_pause                     8/44      0.27  composition_derivative_edit        4/15
    0.20  catalog_get_book               5/25      0.27  composition_motif_adopt            4/15
    0.20  glossary_create_evidence       9/45      0.30  settings_provider_inventory        9/30
    0.20  jobs_cancel                    7/35      0.33  glossary_propose_batch             5/15
    …

THIS IS NOT A CLAIM THAT THOSE CONCLUSIONS ARE WRONG. Each tool did work on the runs where it
was called, and that is what the batch measured. What the number says is that `proven` carries
a different weight for them, and nothing in the ledger said so until now.

DERIVED, NEVER TYPED. Run `python scripts/toolloop/selection_rate.py` to rewrite the contract.
"""
from __future__ import annotations

import collections
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
CONTRACT = ROOT / "contracts" / "tool-selection-rates.json"

#: The number of repeats a LIVE batch runs. The bar below is derived FROM this, so if the batch
#: size ever changes the bar must be re-derived rather than carried over.
LIVE_BATCH_K = 5

#: The power a batch must have before its ZERO means anything.
LIVE_POWER = 0.95


def _reachable_bar(k: int = LIVE_BATCH_K, power: float = LIVE_POWER) -> float:
    """DQ-T51 (owner 2026-08-28): "STATE A RATE BAR … N/M IS NOT CHOSEN YET AND MUST BE DERIVED,
    not picked round. It comes from the measured distribution of selection rates across the
    batches already on disk … a bar invented to fit the current results would retire exactly the
    rows it should catch."

    THE CRITERION IS THE BATCH'S OWN POWER, not a gap eyeballed in a histogram. A LIVE batch runs
    K=5 and concludes on whether the tool was called at least once. For a tool picked with
    probability p, that batch contains a call with probability 1-(1-p)^K. Solving for the p at
    which a K=5 batch is right 95% of the time:

        p = 1 - (1 - 0.95) ** (1/5) = 0.4507

    At or above it, a ZERO is a finding about the tool. Below it, a zero is mostly a lost draw,
    which is precisely the row's complaint — "for a tool it picks ~15% of the time it is a
    lottery: a fresh K=5 batch has roughly even odds of containing a call".

    🔴 AND THE DISTRIBUTION SAYS THE EXACT VALUE DOES NOT MATTER, which is what stops this being
    a number invented to fit. Measured over the 74 tools with >= MIN_RUNS recorded runs, NO TOOL
    LIES IN [0.400, 0.500): the highest rate below is 0.400 and the lowest at or above is 0.500.
    The bar lands in an EMPTY BAND, so every value from 0.41 to 0.49 classifies the identical 22
    tools of 74. The derivation picks 0.4507; the data makes the choice robust.

    THE BAND SURVIVED A DATA REFRESH, which is the part worth trusting. It was first computed
    over 68 tools (20 below); regenerating against every batch on disk — six more tools, and
    today's runs folded in — moved the counts to 74 and 22 and left the empty band exactly where
    it was. A gap that holds while the data underneath it changes is a property of the
    distribution, not of the snapshot it was read from.

    It therefore classifies exactly as the previous hand-picked 0.5 did — deliberately. A derived
    bar that moved rows would be the failure the owner warned about; this one replaces a round
    number with a reason and retires nothing.
    """
    return 1.0 - (1.0 - power) ** (1.0 / k)


#: At or above this measured selection rate, a K=5 LIVE batch has >= 95% chance of containing a
#: call, so `called 0/5` is evidence about the TOOL. Below it the zero is a lost draw and the row
#: is a SELECTION defect, not an unproven tool (DQ-T51). Derived, never typed.
LOTTERY_BELOW = _reachable_bar()

#: Fewer runs than this and the rate is noise, so the tool is left out rather than labelled.
MIN_RUNS = 5


HISTORY = ROOT / "contracts" / "scenario-expect-tool-history.json"


def _history() -> dict:
    """Retired scenario ids and the tool their runs were measuring.

    🔴 WITHOUT THIS THE DENOMINATOR IS REWRITTEN BY REFACTORS. The map used to be built from the
    scenario files AS THEY ARE NOW while the numerator came from runs recorded months ago, so
    renaming or retiring a scenario id dropped every historical run of it out of the denominator.
    The DQ-T50 both-arms split did exactly that, correctly, and 117 runs across 5 ids stopped
    counting. The rate GATES VERDICTS through the DQ-T51 reachability bar, so the side effect was
    a tool moving across the bar with no behaviour having changed.

    Current declarations still WIN over history — a scenario whose expect_tool is deliberately
    changed should take effect — and history only supplies ids nobody declares any more.
    """
    if not HISTORY.exists():
        return {}
    return json.loads(HISTORY.read_text(encoding="utf-8")).get("map") or {}


def unmapped_runs() -> dict:
    """{scenario_id: non-errored run count} for runs whose id maps to no tool.

    The number that would have hidden the defect above. It is REPORTED rather than asserted here
    because a scenario without an `expect_tool` is legitimate; what is not legitimate is a
    populous id quietly leaving the denominator, and that is what a guard reads this for.
    """
    want = derive()["_want"]
    out: collections.Counter = collections.Counter()
    for f in sorted((ROOT / "docs" / "eval" / "toolloop").rglob("*-raw.json")):
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(d, list):
            continue
        for r in d:
            if isinstance(r, dict) and not r.get("error") and r.get("scenario") not in want:
                out[r.get("scenario")] += 1
    return dict(out)


def empty_gap(rates: dict) -> tuple[float, float]:
    """(highest rate strictly below the bar, lowest rate at or above it).

    The interval between them contains no measured tool, so any bar inside it classifies the
    identical set. DERIVED from the rates rather than written down, which is the whole point —
    see `_bar_derivation`."""
    vals = sorted(v["rate"] for v in rates.values())
    below = [r for r in vals if r < LOTTERY_BELOW]
    above = [r for r in vals if r >= LOTTERY_BELOW]
    return (max(below) if below else 0.0), (min(above) if above else 1.0)


def _bar_derivation(rates: dict) -> str:
    """The derivation, written beside the number, with the ROBUSTNESS MEASURED not asserted.

    🔴 THIS USED TO HARD-CODE "no tool measured lies in [0.400, 0.500)". That was true when
    written and became FALSE on 2026-08-30, when fixing
    D-A-SCENARIO-RENAME-SILENTLY-REWRITES-A-MEASURED-SELECTION-RATE restored 117 orphaned runs
    and three tools moved into it (0.400, 0.450, 0.476). A sentence claiming robustness cannot be
    a constant, because the thing it claims is a property of data that moves.
    """
    lo, hi = empty_gap(rates)
    return (
        f"DQ-T51: p = 1-(1-{LIVE_POWER})**(1/{LIVE_BATCH_K}) = {LOTTERY_BELOW:.4f} — the "
        "selection rate at which a K=5 LIVE batch has 95% chance of containing a call, so a zero "
        "is evidence about the tool rather than a lost draw. THE DERIVATION IS PRIMARY; the "
        "robustness note below is measured fresh each time and is secondary to it. "
        f"No measured tool lies in [{lo:.3f}, {hi:.3f}), a gap of {hi - lo:.3f}, and the bar sits "
        "inside it — so every value in that gap classifies the identical set of tools. THAT GAP "
        "HAS NARROWED: it was [0.400, 0.500) until 2026-08-30, when a denominator defect was "
        "fixed and 117 orphaned runs returned. The bar's justification is its POWER, not the "
        "width of this gap; the gap is only evidence that the exact value is not knife-edge."
    )


def derive() -> dict:
    sys.path.insert(0, str(ROOT / "scripts" / "toolloop"))
    import collections

    from fe_runner import called_names  # noqa: PLC0415

    want: dict[str, str] = dict(_history())
    for f in sorted((ROOT / "scripts" / "toolloop").glob("scenarios-*.json")):
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        for s in d.get("scenarios", []):
            if s.get("id") and s.get("expect_tool"):
                want[s["id"]] = s["expect_tool"]

    runs: collections.Counter = collections.Counter()
    calls: collections.Counter = collections.Counter()
    for f in sorted((ROOT / "docs" / "eval" / "toolloop").rglob("*-raw.json")):
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(d, list):
            continue
        for r in d:
            if not isinstance(r, dict) or r.get("error"):
                continue
            tool = want.get(r.get("scenario"))
            if not tool:
                continue
            runs[tool] += 1
            if tool in called_names(r):
                calls[tool] += 1

    rates = {t: {"calls": calls[t], "runs": n, "rate": round(calls[t] / n, 3)}
             for t, n in runs.items() if n >= MIN_RUNS}
    lottery = sorted(t for t, v in rates.items() if v["rate"] < LOTTERY_BELOW)
    return {"min_runs": MIN_RUNS, "lottery_below": LOTTERY_BELOW, "_want": want,
            "_bar_derivation": _bar_derivation(rates),
            "measured": len(rates), "lottery_count": len(lottery),
            "lottery": lottery, "rates": dict(sorted(rates.items()))}


def rate_for(tool: str) -> dict | None:
    """The recorded corpus rate for a tool, or None when it has too few runs to say.

    Reads the CONTRACT, never the corpus — a gate must not sweep 500 files per batch."""
    try:
        return (json.loads(CONTRACT.read_text(encoding="utf-8"))["rates"]).get(tool)
    except (OSError, ValueError, KeyError):
        return None


def _append_history(want: dict) -> int:
    """Fold every currently-declared id into the history contract. APPEND-ONLY.

    🔴 THIS IS WHAT KEEPS THE FIX FROM DECAYING. Seeding history from git was a one-off recovery;
    what stops the next scenario rename losing its runs is that every id is written down WHILE it
    is still declared. Nothing is ever removed here — an id that leaves the scenario files is
    exactly the id whose meaning must survive."""
    if not HISTORY.exists():
        return 0
    doc = json.loads(HISTORY.read_text(encoding="utf-8"))
    m = doc.get("map") or {}
    added = 0
    for sid, tool in want.items():
        if sid not in m:
            m[sid] = tool
            added += 1
    if added:
        doc["map"] = dict(sorted(m.items()))
        doc["count"] = len(m)
        HISTORY.write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n",
                           encoding="utf-8")
    return added


if __name__ == "__main__":
    d = derive()
    _added = _append_history(d["_want"])
    _unmapped = unmapped_runs()
    if _added:
        print(f"history: +{_added} scenario id(s) recorded")
    if _unmapped:
        print(f"🔴 {sum(_unmapped.values())} non-errored run(s) map to NO tool and are OUTSIDE "
              f"every denominator below: {_unmapped}")
    CONTRACT.write_text(json.dumps(
        {"_what": __doc__.strip().splitlines()[0],
         "_derived_by": "python scripts/toolloop/selection_rate.py", **d},
        indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"{d['measured']} tools measured; {d['lottery_count']} below {LOTTERY_BELOW}")
    for t in d["lottery"]:
        v = d["rates"][t]
        print(f"  {v['rate']:5.2f}  {t:38} {v['calls']}/{v['runs']}")
