"""D-JOBS-LIST-ADVERTISES-CANCEL-ON-JOBS-THAT-CANNOT-BE-CANCELLED — the audit half.

    THE INVARIANT. A surface that advertises an affordance must be able to identify the
    resource the owning service will gate on — or say that it cannot.

The row asked for one thing it had not done: audit the OTHER services for the same shape.

CODE. Three services register a job-control tool and they do not gate the same way. Translation
checks `_require_edit(book_id)`; composition's `_require_own_run(book_id, run_id)` reconciles
the run against a book grant checked above it — so the SHAPE is not translation-specific.

🔴 AND THE LIVE QUESTION CANNOT BE ANSWERED GENERICALLY. Two of my attempts were wrong first:

  * applying ONE controllable-status list across four owning tables reported "1 orphaned +
    controllable". The vocabularies are DISJOINT — authoring_runs closed|draft|failed|gated|
    report_ready, generation_job cancelled|completed|failed, plan_run checkpoint|compiled|
    pending|proposed|validated, translation_jobs completed|failed. The one match was plan_run's
    `pending`, a plan awaiting something and not a job. One column name, four meanings — the
    same trap as the soft-archive predicate.
  * asking `job_projection`, the surface that actually advertises caps, reported 0 of 251
    controllable jobs referencing a dead book. THAT WAS VACUOUS: 0 of the 251 carry a `book_id`
    in `params` at all.

THE VACUOUS CHECK IS THE FINDING. `job_projection` carries no book_id — established from the
other side too (D-STORE-SNAPSHOT-CANNOT-SEE-THE-JOB-PROJECTION, none in `params` across 1,518
rows). The surface that advertises `control_caps` cannot identify the resource the owning
service gates on, so DQ-T46's option (a) VERIFY is necessarily "ask the owning service per
listed job". The cheap local variant a reader might imagine does not exist.

Nothing here answers DQ-T46. It removes one option from the menu by showing it was never on it.
"""
from __future__ import annotations

import json
import pathlib
import subprocess
import sys

import pytest

import sys as _sys, pathlib as _pathlib
_sys.path.insert(0, str(_pathlib.Path(__file__).resolve().parent))
import live_stack  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]
LEDGER = json.loads((ROOT / "contracts" / "tool-deep-dive-ledger.json").read_text(
    encoding="utf-8"))
# 🔴 WAS `docker ps`, WHICH SUCCEEDS ON EVERY GITHUB RUNNER. A guard whose proxy is
# true wherever there is no stack is not a guard: these tests ran in CI and failed with
# connection errors that read like defects. `live_stack.up()` probes the anchor
# gate-wiring-gate already uses, and fails CLOSED if the probe cannot be loaded.
_STACK = live_stack.up()


def _q(db, sql):
    return subprocess.run(
        ["docker", "exec", "-i", "infra-postgres-1", "psql", "-U", "loreweave", "-d", db,
         "-At", "-F", "|", "-c", sql], capture_output=True, text=True).stdout.strip()


def _caps():
    """🔴 LOADED BY PATH, NOT BY PACKAGE NAME. `from app.contract import …` passed in isolation
    and FAILED in the full suite: every service has an `app` package, so whichever one another
    test imported first wins the name. A test that is green alone and red beside its neighbours
    is worse than no test — it teaches the suite to be re-run until it agrees."""
    import importlib.util  # noqa: PLC0415
    path = ROOT / "services" / "jobs-service" / "app" / "contract.py"
    spec = importlib.util.spec_from_file_location("_jobs_contract", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.derive_control_caps


def test_control_caps_is_derived_from_status_and_kind_ALONE():
    """The row's claim, read from the code rather than inferred: no reachability input."""
    d = _caps()
    assert d("pending", "translation")
    assert not d("completed", "translation")
    src = (ROOT / "services" / "jobs-service" / "app" / "contract.py").read_text(encoding="utf-8")
    at = src.index("def derive_control_caps(")
    sig = src[at:src.index('"""', at)]
    assert "status" in sig and "kind" in sig
    assert "book" not in sig and "reachab" not in sig.lower()


@pytest.mark.skipif(not live_stack.up(), reason=live_stack.REASON)
def test_the_projection_cannot_identify_the_gated_resource():
    """🔴 THE FINDING, and the reason a local verification is impossible rather than merely
    expensive. If `params` ever starts carrying book_id this changes and DQ-T46 gets a cheaper
    option — so it must fail rather than quietly keep the old conclusion."""
    n = _q("loreweave_jobs", "SELECT count(*) FROM job_projection WHERE params ? 'book_id';")
    assert n == "0", f"{n} projected jobs now carry a book_id — re-derive DQ-T46's options"
    cols = _q("loreweave_jobs",
              "SELECT string_agg(column_name, ',' ORDER BY column_name) "
              "FROM information_schema.columns WHERE table_name='job_projection';")
    assert "book_id" not in cols, cols


@pytest.mark.skipif(not live_stack.up(), reason=live_stack.REASON)
def test_a_generic_status_list_is_NOT_comparable_across_owners():
    """🔴 THE MISTAKE THAT PRODUCED A FALSE '1 ORPHANED + CONTROLLABLE'. Four owning tables,
    four disjoint vocabularies. Pinned so nobody re-derives the row with a shared list."""
    vocab = {}
    for db, t in (("loreweave_composition", "authoring_runs"),
                  ("loreweave_composition", "generation_job"),
                  ("loreweave_composition", "plan_run"),
                  ("loreweave_translation", "translation_jobs")):
        got = _q(db, f"SELECT string_agg(DISTINCT status, ',' ORDER BY status) FROM {t};")
        vocab[t] = set((got or "").split(",")) - {""}
    assert all(vocab.values()), vocab
    shared = set.intersection(*vocab.values())
    assert not shared, f"the vocabularies now overlap ({shared}) — re-derive the audit"


@pytest.mark.skipif(not live_stack.up(), reason=live_stack.REASON)
def test_the_translation_population_that_motivated_the_row_is_CLEARED():
    """The per-batch sweep works: 60 orphaned jobs became 0."""
    books = set(_q("loreweave_book", "SELECT id::text FROM books;").splitlines())
    ids = [b for b in _q("loreweave_translation",
                         "SELECT DISTINCT book_id::text FROM translation_jobs "
                         "WHERE book_id IS NOT NULL;").splitlines() if b]
    orphaned = [b for b in ids if b not in books]
    assert not orphaned, f"{len(orphaned)} translation jobs are orphaned again"


def test_the_row_keeps_its_DQ_and_records_the_audit():
    """🔴 RE-ANCHORED 2026-08-28. DQ-T46 has since been answered TWICE — the owner's first
    answer named a mechanism jobs-service could not build, the question went back corrected,
    and the owner answered again ('ask the owning service'). The row's block was correctly
    cleared both times a real answer landed, so pinning `blocked_by_dq == "DQ-T46"` or
    `state == "open"` punishes exactly the progress this loop exists to make. What survives is
    the audit content, and — if the row still claims a block — that the named question is
    genuinely still open."""
    r = LEDGER["defects"]["D-JOBS-LIST-ADVERTISES-CANCEL-ON-JOBS-THAT-CANNOT-BE-CANCELLED"]
    assert "the_other_services_audit_2026_08_27" in r
    assert "and_the_vacuous_check_IS_the_finding" in r
    named = r.get("blocked_by_dq")
    if named:
        assert LEDGER["deferred_questions"][named]["state"] == "open", (
            f"the row is blocked on {named}, which is no longer open")
