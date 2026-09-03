"""A projection row whose owner no longer has the job must stop claiming it is running.

    THE INVARIANT. The backstop asks each owning service about the rows the projection still
    calls LIVE, and a row the owner does not return is marked terminal. A service that cannot
    answer leaves its rows UNVERIFIED — never silently "present".

OWNER RULING 2026-08-31 (DQ-T65): "a non-terminal row whose owner no longer has it is DEAD,
and is marked so" — and, separately: fix the architecture, not the MCP surface.

🔴 WHY A DELTA SWEEP CANNOT DO THIS. `ReconcileSweeper._sweep_source` reads
`GET /internal/{svc}/jobs?since=` and upserts what comes back. It is ADDITIVE and keyed on
CHANGE, so a row that stopped changing — or whose owning row was deleted — never appears in
another window. Measured 2026-08-31 against the live stores:

    28 rows at running/pending/paused, up to 74 days old, `cancel` advertised on every one
    22 of 22 composition rows had NO owning row at all
    446 of 910 composition projection rows have no owner (mostly this harness's own teardown)
    3 belong to real users — all knowledge/extraction, 9 to 11 weeks old

A safety net that reads only what the source still reports catches DRIFT and is blind to
ABSENCE. Those are different failures and only one of them had a backstop.
"""
from __future__ import annotations

import inspect

import pytest

from app import reconcile
from app.projection import store


class TestTheContractHasTwoModes:
    def test_the_fetch_sends_ids_instead_of_since(self):
        src = inspect.getsource(reconcile.ReconcileSweeper._fetch)
        assert '{"ids": ids}' in src
        assert '"since"' in src

    def test_exactly_one_mode_per_call(self):
        """"gone" and "not changed since" are different answers and must not share a
        response — an empty result has to mean exactly one thing."""
        src = inspect.getsource(reconcile.ReconcileSweeper._fetch)
        assert "ids is not None" in src


class TestAbsenceIsMeasuredNotAssumed:
    def test_a_source_that_cannot_answer_is_UNVERIFIED_not_clean(self):
        """🔴 THE FAILURE THIS GUARD EXISTS FOR. A source without the `?ids=` mode answers
        422/404. Reporting `gone: 0` there is indistinguishable from "every row is present",
        which is the degrade that turns a safety net into a decoration."""
        src = inspect.getsource(reconcile.ReconcileSweeper._verify_source)
        assert '"unverified": True' in src
        i, j = src.index("except Exception"), src.index("return {")
        assert "unverified" in src[i:], "the error path does not report unverified"

    def test_nothing_is_marked_when_the_owner_returns_the_row(self):
        src = inspect.getsource(reconcile.ReconcileSweeper._verify_source)
        assert "if i not in present" in src, "absence is not derived from the RESULT"

    def test_the_pass_runs_after_the_delta_sweep_never_before(self):
        """A row the sweep is about to heal must not be asked about and marked gone in the
        same tick."""
        src = inspect.getsource(reconcile.ReconcileSweeper.run)
        assert src.index("await self.sweep_once()") < src.index("verify_absent_once")

    def test_it_is_opt_in(self):
        """It is the only loop here that writes a terminal status no owning service emitted,
        so it is enabled deliberately rather than arriving with a deploy."""
        from app.config import settings
        assert settings.absence_check_enabled is False
        src = inspect.getsource(reconcile.ReconcileSweeper.run)
        assert "settings.absence_check_enabled" in src


class TestTheGraceIsRealAndFailsTowardDoingNothing:
    def test_only_rows_older_than_the_grace_are_asked_about(self):
        src = inspect.getsource(store.list_non_terminal_ids)
        assert "make_interval" in src and "older_than_s" in src

    def test_the_default_grace_is_not_seconds(self):
        """A job that started moments ago must never be asked about and marked gone because
        its own creation event is still in flight."""
        from app.config import settings
        assert settings.absence_check_min_age_s >= 3600

    def test_the_batch_is_capped(self):
        """The ids ride a query string; an unbounded list builds a URL no proxy will carry."""
        from app.config import settings
        assert 0 < settings.absence_check_batch <= 1000
        assert "absence_check_batch" in inspect.getsource(
            reconcile.ReconcileSweeper._verify_source)


class TestTheMarkDoesNotOVERSTATE:
    def test_it_says_the_outcome_is_not_recoverable(self):
        """`failed` asserts more than is known — the job may well have COMPLETED before its
        row was removed. The message must not pretend otherwise."""
        assert "not recoverable" in store.OWNER_LOST_ERROR["message"]
        assert store.OWNER_LOST_DETAIL == "owner_no_longer_has_row"

    def test_a_row_that_reached_a_real_terminal_state_is_not_overwritten(self):
        """The live stream can beat this pass. The UPDATE re-checks the status it replaces
        rather than trusting the read that selected the id."""
        src = inspect.getsource(store.mark_owner_lost)
        assert "status NOT IN" in src


class TestNothingIsOfferedOnALostRow:
    """🔴 REPLACING A SURFACE DOES NOT CARRY ITS GUARANTEES. Marking the rows `failed` removed
    the broken `cancel` this work is about — and handed SIX of the 28 a broken RETRY, because
    `extraction` and `enrichment_job` are in _RETRYABLE_KINDS and a retry would 404 against the
    service that no longer has the row. Caught by checking the caps live after the marking run,
    not by reading the diff."""

    def test_a_lost_row_offers_nothing(self):
        from app.contract import OWNER_LOST_DETAIL, derive_control_caps
        for kind in ("extraction", "enrichment_job", "plan_forge_propose", "translation"):
            assert derive_control_caps("failed", kind,
                                       detail_status=OWNER_LOST_DETAIL) == []

    def test_an_ordinary_failure_still_offers_retry(self):
        """The guard must not swallow the real thing it sits next to.

        MERGE 2026-09-03 — the expected list grew by RESUME, and the equality is KEPT rather
        than softened to `RETRY in caps`. A failed extraction can now resume from its last
        checkpoint, so RESUME belongs here; loosening the assertion to membership would stop
        this noticing if the owner-lost guard ever started eating one cap and not the other,
        which is the whole thing it sits next to."""
        from app.contract import ControlCap, derive_control_caps
        assert derive_control_caps("failed", "extraction") == [
            ControlCap.RESUME, ControlCap.RETRY]

    def test_every_call_site_passes_the_detail(self):
        """AUDIT ALL CALL SITES. Five call the function; the fifth — the one that GATES the
        action rather than displaying it — was missed on the first pass because its
        indentation differed from the other four."""
        import ast
        import pathlib as _p
        root = _p.Path(__file__).resolve().parents[1] / "app"
        seen = 0
        for f in root.rglob("*.py"):
            tree = ast.parse(f.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if (isinstance(node, ast.Call) and getattr(node.func, "id", "")
                        == "derive_control_caps"):
                    seen += 1
                    kws = {k.arg for k in node.keywords}
                    assert "detail_status" in kws, f"{f.name}:{node.lineno} does not pass it"
        assert seen >= 5, f"only {seen} call sites found — did they move?"


class TestTheTerminalSetHasONEHome:
    def test_the_projection_derives_it_from_the_contract(self):
        """🔴 FOUND WHILE SIZING A NEW STATUS. This file carried its own
        `("completed", "failed", "cancelled")` — a second copy of a set the SDK annotates as
        "The single source of truth (no parallel set to drift)". Adding one member to
        JobStatus would have left this tuple believing the old vocabulary."""
        from loreweave_jobs import TERMINAL
        assert store._TERMINAL_STATUSES == tuple(sorted(s.value for s in TERMINAL))
        src = inspect.getsource(store)
        assert '_TERMINAL_STATUSES = ("completed"' not in src


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
