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


# ── the sweep's OWN debris, found 2026-08-28 ───────────────────────────────────────────────

def test_the_sweep_reconciles_the_PROJECTION_it_orphans():
    """🔴 THE FIX ABOVE WAS MANUFACTURING FRESH INSTANCES OF THE DEFECT IT SERVED.

    `sweep_orphan_translation_jobs` deletes from `loreweave_translation.translation_jobs` and
    left `loreweave_jobs.job_projection` untouched — a different database, no FK. Every run
    therefore turned an orphaned-BOOK job into a PHANTOM: a projection row for a job that exists
    nowhere at all. Measured 2026-08-28, before this guard:

        translation_jobs                                     6 rows, 0 controllable
        job_projection, service=translation, controllable   92 rows
        ...of those 92, job_id still in translation_jobs     0

    That is strictly worse than the debris it replaced, because `job_projection` is the table
    `jobs_list` READS. All 92 were advertised with control_caps ["cancel"] against a job row that
    cannot be found — which is D-JOBS-LIST-ADVERTISES-CANCEL-ON-JOBS-THAT-CANNOT-BE-CANCELLED,
    the very row this sweep was written to stop polluting.
    """
    assert "sweep_phantom_job_projections" in PROVISION, (
        "deleting a job row still leaves its projection behind")
    tree = ast.parse(PROVISION)
    fn = next(n for n in ast.walk(tree)
              if isinstance(n, ast.FunctionDef) and n.name == "sweep_phantom_job_projections")
    body = ast.get_source_segment(PROVISION, fn) or ""
    assert "job_projection" in body, "the sweep does not touch the projection table"
    # 🔴 STRIP THE DOCSTRING FIRST. The prose above the code says "deletes from …", and an
    # index() over the whole function found that word before the first SELECT and went red on a
    # sweep that is correctly ordered. A falsifier that anchors on literal text must be pointed
    # at the CODE, or it reports on how the function is described rather than what it does.
    stmts = fn.body[1:] if ast.get_docstring(fn) else fn.body
    code = "\n".join(ast.get_source_segment(PROVISION, st) or "" for st in stmts)
    assert code.upper().index("SELECT") < code.upper().index("DELETE"), (
        "SELECT before DML")


def test_the_phantom_sweep_is_scoped_to_the_HARNESS_ACCOUNT():
    """The conservative half, and it is narrower than the leak it repairs on purpose.

    A projection row is the unified read model: deleting one for a real user destroys history
    that nothing else holds. The harness is the only actor here that deletes job rows out from
    under it, so the harness account is the only place a missing job row is unambiguously this
    sweep's own debris. Verified 2026-08-28: 407 rows removed, all on the harness account, and
    the 55 translation rows belonging to other users were untouched."""
    tree = ast.parse(PROVISION)
    fn = next(n for n in ast.walk(tree)
              if isinstance(n, ast.FunctionDef) and n.name == "sweep_phantom_job_projections")
    body = ast.get_source_segment(PROVISION, fn) or ""
    assert body.count("OWNER_ID") >= 2, (
        "the phantom sweep is not scoped to the harness account on BOTH the read and the delete")
    assert "service='translation'" in body, (
        "the sweep is not scoped to the one producer this harness seeds and deletes")


def test_the_runner_calls_the_phantom_sweep_UNCONDITIONALLY():
    """🔴 IT CANNOT LIVE ONLY INSIDE THE BOOK SWEEP, and this is not hypothetical — it is
    today's state. `sweep_orphan_translation_jobs` returns EARLY when no orphaned books remain,
    which is exactly the situation the per-batch book sweep produces. The 92 phantoms it had
    already created were therefore unreachable by their own cleanup: the function that would
    have removed them returns before it gets there."""
    assert "await asyncio.to_thread(sweep_phantom_job_projections)" in RUNNER, (
        "the phantom sweep only runs when the book sweep finds work, so a clean book sweep "
        "leaves every phantom in place")
    i = RUNNER.index("await asyncio.to_thread(sweep_phantom_job_projections)")
    j = RUNNER.index("async with httpx.AsyncClient(timeout=TURN_TIMEOUT) as client:")
    assert i < j, "the phantom sweep runs after the batch, so a crash leaves the debris in place"
