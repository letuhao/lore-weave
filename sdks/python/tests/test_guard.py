"""loreweave_guard — S1. The tests are written around the measured false-greens, not around the
enum.

Two shapes this repo has actually shipped and paid for:

  · the canon guard returning ``status="skipped_no_cast"`` with ``resolved=True`` and
    ``violations=[]`` — three of four scenes in an 8,116-word chapter contained an invented
    character, and every field was individually honest;
  · a "no rules matched" amber that fires on every book in which nobody has died, which trains
    the author to ignore the banner and takes the real signal with it.
"""
from __future__ import annotations

import pytest

from loreweave_guard import CheckStatus, GuardReport, check_over, worst


# ── the verdict rule ──────────────────────────────────────────────────────────────────────

def test_a_verdict_from_a_guard_that_checked_NOTHING_is_None():
    """THE measured bug. `raw_verdict=True` + a check that never ran must not read as a pass."""
    r = GuardReport(checks={"canon_cast": CheckStatus.NO_SUBJECT}, raw_verdict=True)
    assert r.verdict is None
    assert r.status is CheckStatus.NO_SUBJECT
    assert r.covered == []


def test_CONTROL_a_verdict_from_a_guard_that_DID_check_survives():
    """Without this, "verdict is always None" would pass the test above and destroy the feature."""
    r = GuardReport(checks={"canon_cast": CheckStatus.CHECKED}, raw_verdict=True)
    assert r.verdict is True
    assert r.covered == ["canon_cast"]


def test_the_raw_verdict_is_still_readable_because_it_is_still_information():
    r = GuardReport(checks={"canon_cast": CheckStatus.DEGRADED}, raw_verdict=False)
    assert r.verdict is None and r.raw_verdict is False


def test_findings_are_NOT_suppressed_by_an_unverified_verdict():
    """'unverified ⇒ discard the evidence' breaks translation's corrector loop and two publish
    gates. A guard may legitimately have findings it could not fully verify, and the caller
    must still act on them."""
    r = GuardReport(checks={"rules": CheckStatus.DEGRADED},
                    findings=["a contradiction the symbolic tier found"], raw_verdict=None)
    assert r.verdict is None
    assert r.findings == ["a contradiction the symbolic tier found"]


# ── the derived headline ──────────────────────────────────────────────────────────────────

def test_one_degraded_check_among_passing_ones_does_not_read_as_checked():
    r = GuardReport(checks={"a": CheckStatus.CHECKED, "b": CheckStatus.CHECKED,
                            "c": CheckStatus.DEGRADED})
    assert r.status is CheckStatus.DEGRADED
    assert r.covered == ["a", "b"]
    assert r.gaps == {"c": CheckStatus.DEGRADED}


def test_a_check_that_was_never_in_scope_is_not_a_gap():
    """NOT_APPLICABLE must render as nothing. Counting a sampled-out check as a coverage hole
    is how a report goes permanently amber and stops being read."""
    r = GuardReport(checks={"a": CheckStatus.CHECKED, "sampled_out": CheckStatus.NOT_APPLICABLE})
    assert r.status is CheckStatus.CHECKED
    assert r.gaps == {}


def test_a_report_where_everything_was_out_of_scope_is_not_checked_and_not_amber():
    r = GuardReport(checks={"a": CheckStatus.NOT_APPLICABLE}, raw_verdict=True)
    assert r.status is CheckStatus.NOT_APPLICABLE
    assert r.verdict is None, "nothing ran, so nothing was proven"


def test_an_empty_report_is_not_a_pass():
    """A guard that declared no checks at all verified nothing. This is the shape a NEW code
    path takes before anyone wires its checks in — it must not default to green."""
    r = GuardReport(raw_verdict=True)
    assert r.status is CheckStatus.NOT_APPLICABLE and r.verdict is None


def test_failed_outranks_degraded_outranks_no_rules():
    assert worst([CheckStatus.NO_RULES, CheckStatus.DEGRADED, CheckStatus.FAILED]) is CheckStatus.FAILED
    assert worst([CheckStatus.NO_RULES, CheckStatus.DEGRADED]) is CheckStatus.DEGRADED
    assert worst([CheckStatus.NO_RULES, CheckStatus.CHECKED]) is CheckStatus.NO_RULES


def test_trusted_caller_is_worse_than_checked():
    """Self-reported is not verified. If it ranked as CHECKED, a guard could launder an
    upstream claim into a platform verdict."""
    assert worst([CheckStatus.TRUSTED_CALLER, CheckStatus.CHECKED]) is CheckStatus.TRUSTED_CALLER


def test_every_enum_member_is_rankable():
    """A member added to the enum but not to _RANK would fall through to CHECKED — a new
    failure mode silently ranking as a pass. This is the guard on the guard."""
    for member in CheckStatus:
        if member is CheckStatus.NOT_APPLICABLE:
            continue
        assert worst([member]) is member, f"{member} is not in _RANK"


# ── NO_RULES is about the CORPUS ──────────────────────────────────────────────────────────

def test_an_empty_corpus_is_NO_RULES_and_a_populated_one_is_CHECKED():
    assert check_over(0) is CheckStatus.NO_RULES
    assert check_over(12) is CheckStatus.CHECKED


def test_an_unreadable_corpus_is_DEGRADED_not_NO_RULES():
    """A corpus that could not be READ is not an empty corpus. Reporting NO_RULES for an outage
    is the "nothing found" / "nothing was checked" conflation one level down."""
    assert check_over(0, degraded=True) is CheckStatus.DEGRADED
    assert check_over(12, degraded=True) is CheckStatus.DEGRADED


# ── the boundary ──────────────────────────────────────────────────────────────────────────

def test_plain_strings_from_json_are_normalised_at_the_boundary():
    r = GuardReport(checks={"a": "checked", "b": "degraded"})
    assert r.checks["a"] is CheckStatus.CHECKED
    assert r.status is CheckStatus.DEGRADED


def test_an_unknown_status_raises_rather_than_ranking_as_a_pass():
    with pytest.raises(ValueError):
        GuardReport(checks={"a": "probably_fine"})


def test_the_wire_shape_carries_the_DERIVED_values():
    """A FE banner must not have to re-implement the honesty rules in TypeScript — that is a
    second place for them to drift."""
    d = GuardReport(checks={"a": CheckStatus.CHECKED, "b": CheckStatus.NO_JUDGE},
                    raw_verdict=True).to_dict()
    assert d["status"] == "no_judge"
    assert d["verdict"] is None and d["raw_verdict"] is True
    assert d["covered"] == ["a"] and d["gaps"] == {"b": "no_judge"}
