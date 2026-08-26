"""A one-time cleanup for a per-run leak is not a fix.

Every translation scenario seeds a pending job on its throwaway book; teardown removes the book
and the JOB survives, because it lives in another database with no FK to it. `jobs_list` then
advertises control_caps ["cancel"] for each orphan and every cancel refuses — correctly, since
translation_job_control gates on the book's EDIT grant and the book is gone.

🔴 THE SWEEP EXISTED AND NOTHING CALLED IT. `sweep_orphan_translation_jobs` was run once by hand
on 2026-08-24 (310 rows -> 6). Re-measured 2026-08-26: 14 controllable translation jobs
referencing 14 distinct books, ZERO of which still existed. The debris came straight back,
because the leak is per-run and the cleanup was not.

The consequence is not litter. The next batch reads its predecessor's orphans as product state —
this row cost a probe before anyone understood the ids were fine and the books were not.
"""
from __future__ import annotations

import ast
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
RUNNER = (ROOT / "scripts" / "toolloop" / "fe_runner.py").read_text(encoding="utf-8")
PROVISION = (ROOT / "scripts" / "toolloop" / "provision.py").read_text(encoding="utf-8")


def test_the_runner_actually_calls_the_job_sweep():
    """The whole defect was a helper nobody invoked."""
    assert "sweep_orphan_translation_jobs" in RUNNER, (
        "the job sweep is still something a human has to remember to run")
    assert "await asyncio.to_thread(sweep_orphan_translation_jobs)" in RUNNER


def test_it_sweeps_BEFORE_the_batch_not_after():
    """Same reasoning the book sweep already documents: a crashed run leaves debris, and the
    NEXT batch must not measure it. An after-only sweep is skipped by the crash that caused it."""
    i = RUNNER.index("await asyncio.to_thread(sweep_orphan_translation_jobs)")
    j = RUNNER.index("async with httpx.AsyncClient(timeout=TURN_TIMEOUT) as client:")
    assert i < j, "the job sweep runs after the batch, so a crash leaves the debris in place"


def test_the_sweep_is_BOOK_SCOPED_and_cannot_touch_a_live_book_s_jobs():
    """The conservative half. A sweep keyed on anything but 'the book is gone' could delete a
    real user's running job — far worse than the debris it removes."""
    src = PROVISION[PROVISION.index("def sweep_orphan_translation_jobs"):][:2200]
    assert "books" in src and "book_id" in src, "the sweep is not keyed on the book's existence"
    tree = ast.parse(PROVISION)
    fn = next(n for n in ast.walk(tree)
              if isinstance(n, ast.FunctionDef) and n.name == "sweep_orphan_translation_jobs")
    body = ast.get_source_segment(PROVISION, fn) or ""
    assert "DELETE" in body.upper(), "the sweep does not delete anything"
    assert "SELECT" in body.upper(), "the sweep deletes without reading first"
    assert body.upper().index("SELECT") < body.upper().index("DELETE"), (
        "SELECT before DML — the standing rule, and the only thing standing between this sweep "
        "and a live job")
