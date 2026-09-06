"""D-THE-BEFORE-SNAPSHOT-IS-NOT-THE-STATE-THE-TURN-STARTS-FROM.

    THE INVARIANT. `store_diff` is read as "what this TURN changed". A change whose timestamp
    PREDATES the turn is not that, and must not be attributed to it.

MEASURED 2026-08-30, session 01a04fe3-bd8e-7d21-81f2-4555c920a8c7 (c-silenttrigger2,
composition-arc-get-v2 rep 4). The DATA bar flagged a READ-intent scenario as a lifecycle write:

    before  loreweave_composition.composition_work  rows=1  latest=23:38:22.478817
    after                                           rows=1  latest=23:38:37.437706

The store's own timestamps refute it. The book's only composition_work row has
`created_at == updated_at == 23:38:37.437706`, and the turn's FIRST chat message is
23:38:40.448765 — the row was created three seconds BEFORE the turn began, and a row whose
updated_at equals its created_at was never updated. Nothing wrote inside the measured window.

🔴 AND REFUTING THAT ONE FLAG NEEDED A LIVE DB QUERY, because `started_at` is None on every run
record on disk. A week later the session would have been unrecoverable and the flag would have
stood. The fix is to write the fact down: `turn_started_at` is recorded immediately before the
first turn is sent, and this predicate uses it.

WHAT IS NOT FIXED HERE, and the row says so: the race itself. Something replaces that row between
the `before` snapshot and the turn, and taking the snapshot later is the row's open
recommendation, not this change.
"""
from __future__ import annotations

import importlib.util
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "toolloop"))


def _fe():
    spec = importlib.util.spec_from_file_location(
        "fe_runner_probe", ROOT / "scripts" / "toolloop" / "fe_runner.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


FE = _fe()

START = "2026-08-29T23:38:40.448765+00:00"


def _run(latest, started=START, table="loreweave_composition.composition_work"):
    return {"turn_started_at": started,
            "store_diff": {table: {"before": {"rows": 1, "latest": "2026-08-29 23:38:22.478817+00"},
                                   "after": {"rows": 1, "latest": latest}}}}


class TestAPreTurnChangeIsNotTheTurnsWrite:
    def test_the_founding_flag_is_no_longer_raised(self):
        """The exact timestamps from the session above."""
        r = _run("2026-08-29 23:38:37.437706+00")
        assert FE.read_intent_violations([r]) == []

    def test_a_change_DURING_the_turn_is_still_flagged(self):
        """🔴 THE HALF THAT MATTERS MORE. If this stopped firing, a read-intent scenario could
        write freely and the DATA bar would say nothing."""
        r = _run("2026-08-29 23:38:45.000000+00")
        assert len(FE.read_intent_violations([r])) == 1

    def test_a_change_exactly_AT_the_turn_start_is_flagged(self):
        """The boundary belongs to the turn. A write in the same microsecond as the first
        message is not evidence of innocence."""
        r = _run("2026-08-29 23:38:40.448765+00")
        assert len(FE.read_intent_violations([r])) == 1


class TestItFailsOPENWhenItCannotDateTheChange:
    """🔴 A GUARD THAT DROPPED WHAT IT COULD NOT DATE WOULD BE THE WORSE BUG. Every run recorded
    before 2026-08-30 carries no `turn_started_at`, and the whole corpus would go quiet."""

    def test_a_run_without_the_timestamp_is_unchanged(self):
        r = _run("2026-08-29 23:38:37.437706+00", started=None)
        del r["turn_started_at"]
        assert len(FE.read_intent_violations([r])) == 1

    def test_a_missing_after_snapshot_is_unchanged(self):
        r = {"turn_started_at": START,
             "store_diff": {"loreweave_book.chapters": {"before": {"rows": 1}, "after": None}}}
        assert len(FE.read_intent_violations([r])) == 1

    def test_an_unparseable_latest_is_unchanged(self):
        for bad in ("-", "", "not a date"):
            assert len(FE.read_intent_violations([_run(bad)])) == 1, bad


class TestTheIgnoreListStillApplies:
    def test_a_bookkeeping_table_is_still_ignored_whatever_its_timestamp(self):
        """The pre-existing rule is untouched: this predicate narrows which CHANGES count, never
        which TABLES do."""
        t = next(iter(FE.TURN_BOOKKEEPING_TABLES))
        r = _run("2026-08-29 23:38:45.000000+00", table=t)
        assert FE.read_intent_violations([r]) == []


class TestTheRunnerRecordsTheField:
    def test_run_scenario_stamps_turn_started_at(self):
        """ASSERT THE CALL SITE, not just the helper. A predicate reading a field nothing writes
        is a mechanism that cannot fire — this loop has shipped one of those before."""
        src = (ROOT / "scripts" / "toolloop" / "fe_runner.py").read_text(encoding="utf-8")
        assert 'r["turn_started_at"] = _turn_started_at' in src, (
            "run_scenario no longer stamps turn_started_at — the predicate above still reads it "
            "and would silently fail open on every run")
