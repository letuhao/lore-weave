"""D-A-TURN-THAT-EXHAUSTS-ITS-PASSES-WRITES-AND-SAYS-NOTHING — the framing correction.

    THE INVARIANT. "Told the author nothing" and "showed the author a card that does not
    mention the write" are different defects with different remedies. A count that merges them
    points the fix at the wrong surface.

The row was filed on c-gbuild3: 2 of 5 runs wrote to the store — glossary_entities +2,
kg_add_nodes reporting nodes_created 2 — with an empty reply.

🔴 BOTH OF THOSE RUNS ARE `left_suspended: true`. Split by whether a card was pending, over
1,370 clean run records:

    259  empty reply · card pending · no write
    150  empty reply · card pending · WROTE        <- the row's real population
      9  empty reply · NO card     · no write      <- D-SILENT-TURN-NO-CARD-NO-PROSE
      0  empty reply · NO card     · WROTE         <- the row's claim, as written

Every one of the 150 has a card. So the author is not told nothing: they are asked about step
two with no account of step one. The gbuild scenario is 47 of the 150, so the instance stands
and the framing moves.

WHY IT MATTERS FOR THE REMEDY. DQ-T33 asks what to show when a turn ends with no visible text.
For the 9 genuinely silent runs that is the whole question. For these 150 there IS a surface
already, and the cheapest honest fix may be to name the completed writes ON the card rather than
invent prose for an empty reply — a narrower product decision than the row posed, and still the
owner's.

A first sweep of mine found ZERO of everything, because it excluded suspended runs as "not
silence". That exclusion was the whole population.
"""
from __future__ import annotations

import collections
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
LEDGER = json.loads((ROOT / "contracts" / "tool-deep-dive-ledger.json").read_text(
    encoding="utf-8"))
#: Written for EVERY turn by chat.turn_completed, whatever tool ran — not evidence of a write.
BOOKKEEPING = frozenset({"loreweave_knowledge.extraction_pending"})


def cells():
    out: collections.Counter = collections.Counter()
    total = 0
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
            total += 1
            if (r.get("text") or "").strip():
                continue
            wrote = bool({k for k in (r.get("store_diff") or {}) if k not in BOOKKEEPING})
            out[(bool(r.get("pending_approval")), wrote)] += 1
    return out, total


def test_the_corpus_is_big_enough():
    _, total = cells()
    assert total >= 1000, total


def test_the_claim_AS_WRITTEN_has_zero_instances():
    """🔴 THE CORRECTION. Not one run wrote to the store, said nothing, and had no card."""
    c, _ = cells()
    assert c[(False, True)] == 0, (
        f"{c[(False, True)]} run(s) now write silently with no card — the row's original "
        "framing has become true and must be re-derived rather than kept corrected"
    )


def test_the_REAL_population_is_large_and_always_carded():
    c, _ = cells()
    assert c[(True, True)] >= 50, dict(c)


def test_the_GENUINELY_silent_turn_is_a_different_and_smaller_cell():
    """It is D-SILENT-TURN-NO-CARD-NO-PROSE, and keeping the two apart is the point."""
    c, _ = cells()
    assert 0 < c[(False, False)] < c[(True, True)], dict(c)


def test_bookkeeping_alone_does_not_count_as_a_write():
    """`extraction_pending` is queued for every turn by chat.turn_completed whatever tool ran.
    Counting it would make almost every empty reply look like a silent write."""
    assert "loreweave_knowledge.extraction_pending" in BOOKKEEPING
    c, _ = cells()
    assert c[(True, True)] < c[(True, False)] + c[(True, True)], dict(c)


def test_the_row_carries_the_correction_and_is_LINKED():
    """🔴 RE-ANCHORED 2026-08-28. This pinned `blocked_by_dq == "DQ-T33"` and the DQ's `state ==
    "open"`. DQ-T33 was answered the same day and the row's block was correctly cleared — a
    resume pointer must never aim at a settled question — so pinning either value punishes the
    decision landing. What survives is the substance: the correction stays on the row whatever
    its current block state, and IF the row still claims a block, that question must genuinely
    still be open."""
    r = LEDGER["defects"]["D-A-TURN-THAT-EXHAUSTS-ITS-PASSES-WRITES-AND-SAYS-NOTHING"]
    assert "RE_DERIVED_2026_08_27_the_claim_as_stated_has_ZERO_instances" in r
    assert "the_defect_restated" in r
    named = r.get("blocked_by_dq")
    if named:
        assert LEDGER["deferred_questions"][named]["state"] == "open", (
            f"the row is blocked on {named}, which is no longer open")
