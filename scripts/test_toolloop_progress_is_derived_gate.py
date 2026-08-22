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
    114/198 where the shippable figure was 109/198."""
    led = copy.deepcopy(_ledger())
    derived = gate.recompute_progress(led)
    excluded = [k for k, v in led["tools"].items() if v.get("counts_toward_release") is False]
    assert excluded, "the fixture for this test is the five deprecated rows; none are present"
    assert (derived["tools_concluded_including_deprecated"]
            == derived["tools_concluded"] + len(excluded))


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
    """`defects_proven` + `defects_open` does not equal the total — three rows are shipped
    invariant fixes recorded with `commit`/`test` and no `state` at all. The remainder is STATED
    rather than lost, because a counter that quietly omits a shape is how 'closed' gets claimed."""
    d = gate.recompute_progress(_ledger())
    assert d["defects_total"] == len(_ledger()["defects"])
    assert d["defects_proven"] + d["defects_open"] + d["defects_other"] == d["defects_total"]
