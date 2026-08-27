"""D-THE-STALL-CONCENTRATES-ON-COMPOSITION-MOTIF-SEARCH.

    THE INVARIANT. Assert the DISCRIMINATION, not the rate. A percentage measured on 41 runs is
    a lead; what a guard can hold is that the buckets still separate.

The row reported the stall concentrating on turns that call composition_motif_search: 73%
errored over 41 runs, against 6% baseline, with a 0%-error control of 16 motif-family runs that
never call the search.

🔴 RE-DERIVED 2026-08-27 OVER 1,491 RUNS INSTEAD OF 875, AND THE HEADLINE DID NOT SURVIVE:

                                     runs   errored    rate      (the row said)
    calls composition_motif_search      89       36    40.4%      73% over 41
    motif family, NO search             18        0     0.0%       0% over 16
    no motif tool at all             1,384       85     6.1%       6% over 818

The rate HALVED as n doubled. What survives is the separation — still 6.6x baseline, with the
zero-error control now at 18 runs — and it has not gone away: over runs recorded 2026-08-26 or
later, 3 of 8 search-calling runs errored (37.5%) against 4.6% over 131.

So this file asserts the SHAPE and refuses to assert the number. A guard pinned to 73% would
have gone red for the right reason and been "fixed" by editing the constant, which is how a
measurement becomes a monument.

WHAT IS ALSO KNOWN, and is why the row is blocked rather than open: the search alone does NOT
stall (batch20-motif-search-clean, K=5, 0 errored, the search as the ANSWER), and a controlled
A/B inside one batch showed the failing request IS built and IS sent — identical 14,556-token
preflight and byte-identical 532-byte tool result in all five runs, 3 dying and 2 not. The
failure is in GENERATION on the pass that must emit the next tool call, and the only record of
why is LM Studio's server log, whose newest file is dated 2026-08-04. That is DQ-T53.
"""
from __future__ import annotations

import collections
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "toolloop"))

import fe_runner as fr  # noqa: E402

LEDGER = json.loads((ROOT / "contracts" / "tool-deep-dive-ledger.json").read_text(
    encoding="utf-8"))


def buckets():
    runs: collections.Counter = collections.Counter()
    errs: collections.Counter = collections.Counter()
    for f in sorted((ROOT / "docs" / "eval" / "toolloop").rglob("*-raw.json")):
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(d, list):
            continue
        for r in d:
            if not isinstance(r, dict):
                continue
            called = fr.called_names(r)
            if "composition_motif_search" in called:
                b = "search"
            elif any(c.startswith("composition_motif") for c in called):
                b = "motif_no_search"
            else:
                b = "none"
            runs[b] += 1
            errs[b] += bool(r.get("error"))
    return runs, errs


def test_the_corpus_is_big_enough_to_say_anything():
    runs, _ = buckets()
    assert sum(runs.values()) >= 1000, sum(runs.values())
    assert runs["search"] >= 40, runs["search"]
    assert runs["motif_no_search"] >= 10, runs["motif_no_search"]


def test_the_buckets_still_SEPARATE():
    """The claim that survives. Not a rate — a ratio against the baseline."""
    runs, errs = buckets()
    search = errs["search"] / runs["search"]
    base = errs["none"] / runs["none"]
    assert search > 3 * base, f"search {search:.3f} vs baseline {base:.3f} — the separation is gone"


def test_the_ZERO_ERROR_control_still_holds():
    """🔴 THE CONTROL IS WHAT MAKES IT THE SEARCH AND NOT THE FAMILY, THE FIXTURE OR THE DOMAIN.
    If motif-family runs that never call the search start erroring, the whole reading changes."""
    runs, errs = buckets()
    assert errs["motif_no_search"] == 0, (
        f"{errs['motif_no_search']} of {runs['motif_no_search']} motif-family runs without the "
        "search now error — re-derive the row, the effect is no longer specific to the search"
    )


def test_the_ROW_no_longer_asserts_the_stale_rate():
    """🔴 A LEDGER CLAIM IS A LEAD, NOT A FACT. The 73% was measured on 41 runs and halved at 89.
    The row must carry the correction, or the next reader inherits the over-estimate."""
    r = LEDGER["defects"]["D-THE-STALL-CONCENTRATES-ON-COMPOSITION-MOTIF-SEARCH"]
    blob = json.dumps(r)
    assert "RE_DERIVED_2026_08_27_and_the_headline_was_an_over_estimate" in blob
    assert "40.4%" in blob and "1,491" in blob


def test_the_row_is_BLOCKED_on_the_owner_action_it_named():
    r = LEDGER["defects"]["D-THE-STALL-CONCENTRATES-ON-COMPOSITION-MOTIF-SEARCH"]
    assert r.get("blocked_by_dq") == "DQ-T53"
    dq = LEDGER["deferred_questions"]["DQ-T53"]
    assert dq["state"] == "open"
    assert "I am not able to do it" in dq["my_recommendation"]


def test_the_tautology_the_row_warned_about_is_not_repeated():
    """The row flagged a split it almost reported: 'search was the LAST call' errors 81% because
    when the turn dies after the search, the search IS the last call by consequence. Nothing
    here may reintroduce it."""
    src = pathlib.Path(__file__).read_text(encoding="utf-8")
    assert "last call" not in src.lower() or "tautolog" in src.lower()
