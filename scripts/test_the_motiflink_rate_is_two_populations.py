"""D-UPSTREAM-ERROR-WITH-NO-MESSAGE — the framing correction.

    THE INVARIANT. A rate is only a fact about one thing if it is one population. Thirteen
    hypotheses were refuted against this scenario's ~49%, and that number is two.

Re-derived 2026-08-27 over 105 runs of composition-motif-link-edit instead of 35 — 58 errored,
55%, so the RATE holds. What does not hold is that it is a single phenomenon:

    upstream_silent_after_call   24   provider failed without saying why, MID-turn
    no_output_timeout            23   ReadTimeout, ZERO tool calls
    upstream_silent_no_call       6
    other                         4
    timeout_after_call            1

Two populations of almost identical size. Turn length, schema payload, load, encoding, context
pressure, the supplier itself, pass count, turn count, service state — every one was tested
against their SUM. A cause that explains one half looks refuted by the other, which is exactly
what D-THE-TRANSPORT-STALL-IS-THREE-DIFFERENT-FAILURES said would happen.

WHAT IT MEANS FOR THE CONTROL THE ROW QUEUED. Rebuilding chat-service without the
missing-argument arming and comparing error rates must be read PER POPULATION: the arming can
plausibly bear on `upstream_silent_after_call` (the turn dies on the pass after the surface
widens) and cannot plausibly bear on `no_output_timeout` (nothing was ever called). Run against
the sum, a real effect on half the runs would dilute to noise and read as a refutation — the
fourteenth hypothesis tested against a mixture.

BLOCKED ON DQ-T53 FOR HALF OF IT. The `upstream_silent_*` 30 need the provider's own log, whose
newest file is dated 2026-08-04. The `no_output_timeout` 23 do NOT: since 2026-08-27 every such
run captures its own store signature and service log at the moment it fails. Waiting for the
next occurrence is a different state from waiting for a person.
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
SCENARIOS = {"composition-motif-link-edit", "composition-motif-link-edit-approved"}


def runs():
    out = []
    for f in sorted((ROOT / "docs" / "eval" / "toolloop").rglob("*-raw.json")):
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(d, list):
            continue
        out += [r for r in d if isinstance(r, dict) and r.get("scenario") in SCENARIOS]
    return out


def populations():
    return collections.Counter(
        fr.error_population(r.get("error"), len(fr.called_names(r)))
        for r in runs() if r.get("error"))


def test_the_sample_is_bigger_than_the_row_measured():
    rs = runs()
    assert len(rs) >= 90, f"{len(rs)} runs — the row measured 35"


def test_the_rate_itself_still_holds():
    """The row's ~49% is not what is wrong with it."""
    rs = runs()
    rate = sum(1 for r in rs if r.get("error")) / len(rs)
    assert 0.35 < rate < 0.7, rate


def test_it_is_TWO_populations_of_similar_size():
    """🔴 THE CORRECTION. If one bucket dominated, the thirteen refutations would have been
    tested against approximately one thing and the framing would stand."""
    p = populations()
    a, b = p["upstream_silent_after_call"], p["no_output_timeout"]
    assert a >= 10 and b >= 10, p
    assert 0.5 < a / b < 2.0, f"no longer two comparable populations: {dict(p)}"


def test_the_two_halves_are_DIFFERENT_shapes():
    """They are not the same failure wearing two error strings: one has tool calls and one has
    none, by construction. That is why a cause can explain one and not the other."""
    calls_after = [len(fr.called_names(r)) for r in runs()
                   if fr.error_population(r.get("error"), len(fr.called_names(r)))
                   == "upstream_silent_after_call"]
    calls_none = [len(fr.called_names(r)) for r in runs()
                  if fr.error_population(r.get("error"), len(fr.called_names(r)))
                  == "no_output_timeout"]
    assert calls_after and min(calls_after) >= 1
    assert calls_none and max(calls_none) == 0


def test_the_row_carries_the_correction_and_the_split_link():
    r = LEDGER["defects"]["D-UPSTREAM-ERROR-WITH-NO-MESSAGE"]
    blob = json.dumps(r)
    assert "RE_DERIVED_2026_08_27_and_the_rate_is_TWO_populations" in blob
    assert "D-THE-TRANSPORT-STALL-IS-THREE-DIFFERENT-FAILURES" in blob
    assert r.get("blocked_by_dq") == "DQ-T53"


def test_the_row_says_WHAT_THE_DQ_DOES_NOT_COVER():
    """🔴 A BLOCK THAT OVER-CLAIMS IS WORSE THAN NO BLOCK. Half of this row is not waiting for a
    person, and a reader who sees only `blocked_by_dq` would stop looking at both halves."""
    r = LEDGER["defects"]["D-UPSTREAM-ERROR-WITH-NO-MESSAGE"]
    assert "what_the_DQ_link_does_and_does_NOT_cover" in r
    assert "IT DOES NOT COVER THE TIMEOUT HALF" in r["what_the_DQ_link_does_and_does_NOT_cover"]
