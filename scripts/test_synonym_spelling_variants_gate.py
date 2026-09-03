"""A spelling variant is the same word. Declaring one and not the other hides the tool.

MEASURED 2026-08-22, cycle 1: `settings_model_set_favorite` surfaced 0/5. It declares `favorite`;
the author typed "Mark the first one as a **favourite**." The answerability matcher is exact on
word boundaries, so those are two different words and the tool was never on the wire.

BASELINE, NOT A HARD FAILURE. The five current gaps are real and worth fixing, but failing the
suite on them would block every unrelated change. This asserts the set does not GROW — the shape
`contracts/undeclared-required-args-baseline.json` already uses here.

WHAT THIS DOES NOT COVER, stated so its green is never read as "declarations are fine": it is one
narrow slice of mode 3 (the answerability misses where the declared word was never said, 12 of 27
tools in cycle 1). Three broader declaration lints were prototyped and REJECTED for noise — 49
flags/2 real, 178/9, 150/5 with cells like "book book" — because whether two nouns name the same
object is not derivable from the declarations. `scripts/lint_synonym_spelling_variants.py` carries
that reasoning. Mode 3 is closed by `scripts/toolloop/answerability_probe.py` against REAL measured
turns, not by a lint over declarations.
"""
from __future__ import annotations

import importlib.util
import json
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
BASELINE = ROOT / "contracts" / "synonym-spelling-variants-baseline.json"

_SPEC = importlib.util.spec_from_file_location(
    "lint_spelling", ROOT / "scripts" / "lint_synonym_spelling_variants.py")
lint = importlib.util.module_from_spec(_SPEC)
try:
    _SPEC.loader.exec_module(lint)
except Exception as e:  # chat-service not importable in this environment
    pytest.skip(f"lint not importable: {e}", allow_module_level=True)


def _baseline() -> dict:
    return json.loads(BASELINE.read_text(encoding="utf-8"))["gaps"]


def test_no_new_tool_declares_one_spelling_and_not_the_other():
    now = lint.find_gaps()
    new = {k: v for k, v in now.items() if k not in _baseline()}
    assert not new, (
        "new spelling-variant gap(s): "
        + "; ".join(f"{k}: {', '.join(v)}" for k, v in sorted(new.items()))
        + " — add the missing spelling to the tool's synonyms, or if the gap is intended run "
          "`python scripts/lint_synonym_spelling_variants.py --write` and say why in the commit"
    )


def test_a_fixed_gap_is_removed_from_the_baseline():
    """A baseline that only ever grows stops meaning anything. If a tool no longer has a gap it
    must leave the file, so the count is a real work-list rather than a monument."""
    now = lint.find_gaps()
    stale = [k for k in _baseline() if k not in now]
    assert not stale, (
        f"{stale} no longer have a spelling gap but are still in the baseline — run "
        "`python scripts/lint_synonym_spelling_variants.py --write`"
    )


def test_the_pair_list_stays_narrow():
    """🔴 THE FIRST VERSION OF THIS LINT REPRODUCED THE FAULT IT WAS WRITTEN TO AVOID.

    `("draft", "draught")` flagged EIGHT tools and every one was noise — a draught is a current of
    air, and the manuscript sense is "draft" in both dialects. 8 of 13 initial findings. A pair
    belongs in the list ONLY when the two spellings are the same word in the same sense.
    """
    pairs = {tuple(sorted(p)) for p in lint.PAIRS}
    for bad in [("draft", "draught"), ("dialog", "dialogue")]:
        assert tuple(sorted(bad)) not in pairs, (
            f"{bad} is not a spelling variant in this domain — it was removed after measuring "
            "that it produced only false positives"
        )


def test_the_detector_still_sees_the_gap_that_started_this():
    """🔴 REWRITTEN 2026-08-22, the same day, BECAUSE THE BUG WAS FIXED.

    The first version asserted `settings_model_set_favorite` is still in `find_gaps()`. Cycle 1
    then widened its declaration to include "favourite" — the correct outcome — and the test went
    RED for a fix. **A red-able assertion anchored on live data inverts the moment the defect is
    repaired**, which teaches the next person to keep the bug or delete the test.

    So the shape is the same and the input is SYNTHETIC: the detector is driven over a fabricated
    catalogue carrying the original declaration verbatim. It stays red-able forever and it cannot
    be satisfied by anything but a working detector.
    """
    original = {"a_tool": {"meta": {"synonyms": [
        "favorite", "mark model as favorite", "pin model", "unfavorite"]}}}
    gaps = lint.find_gaps(original)
    assert "a_tool" in gaps, "the detector no longer sees the declaration this lint was built for"
    assert any("favourite" in g for g in gaps["a_tool"])

    clean = {"a_tool": {"meta": {"synonyms": ["favorite", "favourite"]}}}
    assert not lint.find_gaps(clean), "a tool declaring BOTH spellings must not be flagged"
