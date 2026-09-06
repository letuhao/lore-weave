"""The ledger's headline must be arithmetic over its own rows, not a number someone remembered.

FOUND 2026-08-22, with the deep-dive closed at 198/198 and `gate.py audit` reporting CLEAN: the
`progress` block still read `concluded_in_release_surface: 40` and `remaining_in_release_surface:
158`. Ten fields disagreed with the rows sitting in the same file. Anyone opening the ledger — the
document whose entire job is to say how far the work got — was told **40 of 198**.

What makes it worth a chokepoint rather than a correction is the SHAPE. A previous fix had already
added a recompute, and the block carries its own warning about this exact class:

    "_stale_block_note": "This block read tools_concluded=35 while its own rows held 92, for
     batches 2-14. It is now RECOMPUTED from the rows on every update; a hand-typed progress
     number always drifts toward what was true when someone last remembered to edit it."

That claim was TRUE of the five counters the recompute happened to list and FALSE of the other
ten, because the recompute was an inline `pr.update({...})` literal inside `_record`. **A partial
recompute that advertises itself as total is worse than none**: the stale half is now stamped as
derived, and the note tells the next reader to trust it.

Same family as the two instruments this loop has already had to repair — a check that reports
success without touching the thing it claims to verify, and a coverage score whose denominator
came from what was built rather than from the SSOT.

THE INVARIANT: every counter in `progress` is derived by `gate.recompute_progress()` from the
rows, and `gate.py audit` REFUSES when the stored block disagrees. A field that cannot be derived
from the rows must not be a counter there at all.

WHAT THIS DOES NOT CHECK: whether a row's `state` is true about its tool. This guards the
arithmetic between the rows and the headline — not the honesty of a row. Nothing here would catch
a tool marked `proven` that is broken.
"""
from __future__ import annotations

import copy
import json
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "toolloop"))

LEDGER = ROOT / "contracts" / "tool-deep-dive-ledger.json"

gate = pytest.importorskip("gate", reason="scripts/toolloop/gate.py must be importable")


def _ledger() -> dict:
    return json.loads(LEDGER.read_text(encoding="utf-8"))


def test_the_shipped_ledger_agrees_with_its_own_rows():
    """The standing green. This is the assertion that was RED on the original defect."""
    drift = gate.progress_drift(_ledger())
    assert not drift, (
        "`progress` disagrees with the rows in "
        + ", ".join(f"{k} (stored {s!r}, rows say {w!r})" for k, (s, w) in sorted(drift.items()))
        + " — run `python scripts/toolloop/gate.py audit --fix-progress`"
    )


@pytest.mark.parametrize(
    "field, bad",
    [
        ("concluded_in_release_surface", 40),   # the original, verbatim
        ("remaining_in_release_surface", 158),  # the original, verbatim
        ("tools_proven", 1),
        ("tools_blocked", 999),
        ("deferred_questions", 7),
        ("last_batch", "batch-17 (2026-08-14)"),
    ],
)
def test_a_hand_typed_number_is_caught(field, bad):
    """Prove the guard is RED-able, on a COPY.

    Deliberately not by editing the file and restoring it: a `git checkout` to undo an injected
    drift discards every real edit in that file made in the same session, which is a lesson this
    repo has already paid for. `progress_drift` is a pure function of the dict, so the injection
    lives entirely in memory.
    """
    led = copy.deepcopy(_ledger())
    assert led["progress"][field] != bad, f"pick a value {field} does not already hold"
    led["progress"][field] = bad
    drift = gate.progress_drift(led)
    assert field in drift, f"{field} was set to {bad!r} and the drift check did not notice"


def test_the_split_inside_evidence_split_is_checked_too():
    """A nested counter is exactly where a drift check stops looking. It did not, and must not."""
    led = copy.deepcopy(_ledger())
    led["progress"]["evidence_split"]["gate_backed"] = 62  # the original, verbatim
    assert "evidence_split.gate_backed" in gate.progress_drift(led)


def test_the_counters_track_the_rows_and_not_a_constant():
    """Green because the numbers match is not the same as green because they are DERIVED.

    Flip one row from `proven` to `blocked` and both counters must move. A recompute that returned
    frozen values would pass every test above and fail this one.
    """
    led = copy.deepcopy(_ledger())
    before = gate.recompute_progress(led)
    victim = next(k for k, v in led["tools"].items()
                  if v.get("state") == "proven" and v.get("counts_toward_release") is not False)
    led["tools"][victim]["state"] = "blocked"
    after = gate.recompute_progress(led)
    assert after["tools_proven"] == before["tools_proven"] - 1
    assert after["tools_blocked"] == before["tools_blocked"] + 1
    assert after["tools_concluded"] == before["tools_concluded"], "both states are terminal"


def test_a_deprecated_row_stays_out_of_the_numerator():
    """The predecessor's own correction, kept red-able: counting the five deprecated rows read
    114/198 where the shippable figure was 109/198.

    🔴 THIS TEST WENT RED AT HEAD AND NOBODY SAW IT, because the commit that broke it ran only
    the composition-service suite. `composition_glossary_build` was added as a RENAME REDIRECT
    with `state: deprecated`, so the excluded set grew from five rows to six — and the sixth is
    not a concluded tool at all, it is a pointer. `len(excluded)` had quietly come to mean two
    different things: "deprecated but CONCLUDED" (which belongs in the wider count) and "not a
    tool" (which belongs in neither). Both halves are now asserted separately, so a third shape
    cannot merge into either.
    """
    led = copy.deepcopy(_ledger())
    derived = gate.recompute_progress(led)
    excluded = {k: v for k, v in led["tools"].items()
                if v.get("counts_toward_release") is False}
    concluded_but_deprecated = [k for k, v in excluded.items() if v.get("state") in gate.TERMINAL]
    not_a_tool = [k for k, v in excluded.items() if v.get("state") not in gate.TERMINAL]

    assert concluded_but_deprecated, "the fixture for this test is the deprecated PROVEN rows"
    assert (derived["tools_concluded_including_deprecated"]
            == derived["tools_concluded"] + len(concluded_but_deprecated))

    # A redirect row is in the ledger so an old NAME resolves, not because a tool was concluded,
    # and it must stay out of BOTH counters. The one way it could leak back in is by being given
    # a terminal state, so the shape is pinned rather than the count.
    for k in not_a_tool:
        assert led["tools"][k].get("state") == "deprecated", (
            f"{k} counts toward no release and is not concluded, so it should carry the redirect "
            f"shape `deprecated`; it carries {led['tools'][k].get('state')!r}. A new shape here "
            f"will start inflating tools_concluded_including_deprecated silently.")


def test_the_last_batch_regex_sees_both_naming_conventions():
    """`batch40.json` and `b41-norail.json` are both evidence. An anchored `batch(\\d+)` stops at
    40 while four batch-41 files sit beside it — the same under-counting shape as an anchored LIKE
    that found 2 rows where a wrapped one found 91."""
    led = copy.deepcopy(_ledger())
    led["tools"] = {
        "a": {"state": "proven", "evidence_file": "docs/eval/toolloop/2026-08-14/batch40.json"},
        "b": {"state": "proven", "evidence_file": "docs/eval/toolloop/2026-08-14/b41-norail.json"},
    }
    assert gate.recompute_progress(led)["last_batch"] == "batch-41 (2026-08-14)"


def test_nothing_is_silently_dropped_from_the_defect_counters():
    """🔴 THE ASSERTION THIS REPLACES COULD NOT FAIL.

    It read `defects_proven + defects_open + defects_other == defects_total`, and `defects_other`
    was DEFINED as `total - proven - open`. The identity holds for every possible partition,
    including the one that was actually shipped: 14 open, 117 "other", against 71 genuinely open
    defects. A remainder bucket makes any classifier look complete, and an assertion over a
    remainder bucket makes any classifier look tested.

    The counter now reads a CLOSED `state` and raises on anything else, so the real assertions
    are: every state is in the closed set, the named buckets sum to the total with no remainder,
    and — the one with teeth — an unclassifiable row STOPS the count instead of joining it.
    """
    led = _ledger()
    d = gate.recompute_progress(led)

    assert d["defects_total"] == len(led["defects"])
    named = {f"defects_{s}" for s in gate.DEFECT_STATES}
    assert named <= set(d), f"missing a bucket: {named - set(d)}"
    assert "defects_other" not in d, "the remainder bucket is back; it is what hid 57 open rows"
    assert sum(d[k] for k in named) == d["defects_total"], (
        "the named buckets do not account for every row, and there is nowhere else for one to be")


@pytest.mark.parametrize("bad", [None, "OPEN — measured 2026-08-23", "opened", "Open"])
def test_a_state_the_counter_cannot_classify_stops_the_count(bad):
    """Prove it RED on the ORIGINAL defect, in memory.

    `"OPEN — measured 2026-08-23"` is not a hypothetical — it is the verbatim shape of 57 shipped
    rows, and the old `startswith("open")` scored every one of them as not-open. Each value here
    must now raise rather than be counted, because the failure mode being guarded is not a wrong
    bucket, it is a row that quietly belongs to none.
    """
    led = copy.deepcopy(_ledger())
    victim = next(iter(led["defects"]))
    if bad is None:
        led["defects"][victim].pop("state", None)
    else:
        led["defects"][victim]["state"] = bad

    with pytest.raises(ValueError, match="not one of"):
        gate.recompute_progress(led)


class TestTheEvidenceLabelMeansWhatTheLedgerSaysItMeans:
    """🔴 A LABEL THAT NOTHING CHECKS AGAINST ITS OWN DEFINITION.

    The ledger states the rule in its own progress block: a conclusion is `gate-backed` when it
    **cites an evidence file that exists and that gate.py can re-check**. Nothing enforced it.
    Measured 2026-08-25: **43 of the 173 rows carrying the label cited no file at all**, so the
    headline "173 of 198 gate-backed" was overstated by 42 and the re-checkable figure is 131.

    The tempting repair is worse than the defect. Every one of those 43 tools DOES have an entry
    in some evidence file — two to five files each — so a sweep could have "recovered" a citation
    for all of them. That would have invented exactly what the label is supposed to guarantee: a
    specific, named measurement that can be re-run. Only one row named its own file in prose
    ("PROVEN, gate-passed 2026-08-14 (batch4-rest)") and only that one was backfilled.
    """

    def test_every_row_label_matches_the_derived_truth(self):
        led = _ledger()
        wrong = {
            t: (r.get("evidence_class"), gate.GATE_BACKED if gate.is_gate_backed(t, r)
                else gate.PROSE_NOTE)
            for t, r in led["tools"].items()
            if r.get("counts_toward_release") is not False
            and r.get("evidence_class") != "renamed"
            and r.get("evidence_class") != (gate.GATE_BACKED if gate.is_gate_backed(t, r)
                                            else gate.PROSE_NOTE)
        }
        assert not wrong, (
            "these rows label themselves something the evidence does not support "
            f"{{tool: (stored, derived)}}: {wrong}")

    def test_a_row_that_cites_nothing_is_not_gate_backed(self):
        """The exact shape of the 43. A detailed note is not a citation."""
        assert not gate.is_gate_backed("anything", {
            "state": "proven", "evidence_class": "gate-backed",
            "note": "Called 3/3, read-clean 3/3, absent case truthful — pages of real prose."})

    def test_a_row_that_cites_a_file_NOT_carrying_its_entry_is_not_gate_backed(self):
        """Citing a real file is not enough — it has to be a file about THIS tool. This is the
        error I made by hand while investigating: reading composition_authoring_run_manage's
        ship_audit out of rebaseline.json, which is not the file its row cites."""
        real = "docs/eval/toolloop/2026-08-14/rebaseline.json"
        assert (ROOT / real).exists(), "fixture file went missing"
        # The contrast is the assertion: SAME file, one tool it carries and one it does not.
        assert gate.is_gate_backed("jobs_pause", {"evidence_file": real}), (
            "jobs_pause has an entry in that batch, so citing it IS a citation")
        assert not gate.is_gate_backed("a_tool_that_is_not_in_that_batch",
                                       {"evidence_file": real})

    def test_the_split_counts_the_derived_truth_not_the_label(self):
        """Flip a label and the counter must NOT move — it reads the evidence, not the word."""
        led = copy.deepcopy(_ledger())
        victim = next(t for t, r in led["tools"].items()
                      if gate.is_gate_backed(t, r) and r.get("counts_toward_release") is not False)
        before = gate.recompute_progress(led)["evidence_split"]["gate_backed"]
        led["tools"][victim]["evidence_class"] = "prose-note (pre-gate)"
        after = gate.recompute_progress(led)["evidence_split"]["gate_backed"]
        assert after == before, (
            "the counter followed the LABEL. It must follow whether the row cites a re-checkable "
            "file, which is what the ledger's own definition says.")
