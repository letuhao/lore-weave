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


def _open_dq_names() -> set[str]:
    """The queue generator's OWN answer to "which questions are still open".

    Hard-coding a DQ name in a guard is what broke this file: the name was correct when written
    and became a stale assertion the moment the question was answered. Asking the generator keeps
    one home for the definition — the same one that decides whether a defect is actionable.
    """
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "goalgen", ROOT / "scripts" / "toolloop" / "goal_prompt_all_defects.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m._open_dq_names(LEDGER)
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


def test_the_ERROR_COUNT_holds_and_has_stopped_GROWING():
    """The row's ~49% is not what is wrong with it — but the RATE is the wrong quantity to pin.

    🔴 THIS BAR WAS A RATE BAND (0.35 < rate < 0.7) AND A CLEAN RUN BROKE IT, on 2026-08-30, for
    the second time in one day on this corpus. The numerator never moved: 58 errors when the row
    measured 105 runs, and 58 now at 170. The denominator grew by 65 clean runs — twenty of them
    a batch run deliberately that morning — and the rate fell to 0.341, under the floor.

    A FLOOR ON AN ERROR RATE IS BROKEN BY IMPROVEMENT, which makes it a bar that punishes good
    news and measures the population mix rather than the claim. The same repair was made hours
    earlier on D-THE-STALL-CONCENTRATES-ON-COMPOSITION-MOTIF-SEARCH's guard, for the identical
    reason, and it is recorded there as `the_concentration_bar_MOVED_THE_WRONG_WAY`.

    So the quantity is now the COUNT, which over a growing corpus can only rise. That is safe in
    the way a ceiling is not, and it is what the row is actually about: 58 real failures that
    thirteen hypotheses were tested against as if they were one thing.

    NOT A WEAKENED BAR: the old one could be broken by evidence SUPPORTING the row, and this one
    cannot. It goes red if the errors are ever re-classified away or the corpus loses them.
    """
    rs = runs()
    errs = sum(1 for r in rs if r.get("error"))
    assert errs >= 58, (
        f"{errs} errors — the population the row is about has SHRUNK below what was measured. "
        "A baseline may only grow here; losing errors means the corpus or the classifier moved.")
    assert len(rs) >= 105, f"{len(rs)} runs — fewer than the row measured"


def test_no_NEW_error_has_appeared_since_the_row_was_written():
    """🔴 THE FACT THE RATE BAND WAS HIDING, and it matters to the two questions that block this
    row. The error count is 58 at 105 runs and 58 at 170 — SIXTY-FIVE consecutive runs of this
    scenario with not one failure among them.

    That is not proof of a repair and must not be read as one: no fix was aimed at this scenario
    before those runs, and a row that stopped reproducing is not a row that was fixed. It is a
    measurement of where the population stands, and it belongs in front of whoever rules on
    DQ-T80 (how to split this row) and DQ-T81 (whether an unreproducible row may close).
    """
    rs = runs()
    errs = sum(1 for r in rs if r.get("error"))
    assert errs == 58, (
        f"the error count moved to {errs}. If it GREW the stall is back and both blocking "
        "questions should be re-read; if it SHRANK the classifier changed under us. Either way "
        "this is the assertion that should be re-derived first, not adjusted.")


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
    # 🔴 THE REFERENT MOVED, NOT THE INTENT. This read `== "DQ-T53"` until 2026-08-30, when
    # DQ-T53 was answered AND CARRIED OUT (the owner enabled the provider log; the re-runs were
    # executed). A row still pointing at finished work reads as blocked on something nobody
    # needs to do. What must stay true is that the row is blocked on a question that is genuinely
    # OPEN — asserted against the queue generator's own predicate rather than a hard-coded name,
    # so the next re-point does not silently unblock it either.
    blocker = r.get("blocked_by_dq")
    if blocker is None:
        # RULED AND RELEASED. The owner answered on 2026-08-31, the link moved to
        # `was_blocked_by_dq`, and the row is ready work — so "still blocked" is no longer the
        # thing to assert. What must stay true is that the release was REAL: a ruling exists and
        # the row records where it came from, rather than the link simply going missing.
        assert r.get("was_blocked_by_dq"), (
            "the row is unblocked and does not say what it was blocked on — a link that "
            "vanishes loses the decision that released it")
        prior = LEDGER["deferred_questions"].get(r["was_blocked_by_dq"], {})
        assert prior.get("state") == "answered", (
            f"{r['was_blocked_by_dq']} is not answered, yet the row stopped pointing at it")
    else:
        assert blocker in _open_dq_names(), (
            f"blocked_by_dq={blocker!r} is not an OPEN question — the row is in limbo, "
            "pointing at a decision that has already been made")


def test_the_row_says_WHAT_THE_DQ_DOES_NOT_COVER():
    """🔴 A BLOCK THAT OVER-CLAIMS IS WORSE THAN NO BLOCK. Half of this row is not waiting for a
    person, and a reader who sees only `blocked_by_dq` would stop looking at both halves."""
    r = LEDGER["defects"]["D-UPSTREAM-ERROR-WITH-NO-MESSAGE"]
    assert "what_the_DQ_link_does_and_does_NOT_cover" in r
    assert "IT DOES NOT COVER THE TIMEOUT HALF" in r["what_the_DQ_link_does_and_does_NOT_cover"]
