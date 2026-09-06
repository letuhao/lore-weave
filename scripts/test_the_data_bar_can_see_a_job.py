"""D-STORE-SNAPSHOT-CANNOT-SEE-THE-JOB-PROJECTION.

`loreweave_jobs.job_projection` carries no book_id and no chapter_id, and `store_snapshot`
discovers its tables by scanning for a book_id column — so the projection could never be
included and no `jobs_*` tool's effect on it was visible to the DATA bar.

Measured: `jobs_pause` returned {'success': true, 'status': 'paused'} with an EMPTY diff, so the
idempotency probe reported "the first call changed nothing either" — while the SECOND call
refused with "action 'pause' not valid for status 'paused'", naming the new status. The proof
was in the refusal and not in the store.

🔴 SCOPED BY OWNER, WHICH THIS HARNESS ARGUES AGAINST EVERYWHERE ELSE. Checked before settling
for it rather than after: the table's columns are (service, job_id, owner_user_id, kind, status,
parent_job_id, detail_status, progress, title, error, job_created_at, job_updated_at,
projected_at, model, cost_usd, tokens_in, tokens_out, params), and `params` carries no book_id
or project_id in any of its 1,518 rows. There is nothing else to scope through — which is a
different situation from arc_template, where a per-run nonce existed and was used.

The cost is real and named on the row: under concurrency another repeat's job moves this count
too, so a diff here says A job changed during the window, not that THIS turn changed it.
"""
from __future__ import annotations

import pathlib
import subprocess
import sys

import pytest

import sys as _sys, pathlib as _pathlib
_sys.path.insert(0, str(_pathlib.Path(__file__).resolve().parent))
import live_stack  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "toolloop"))
sys.path.insert(0, str(ROOT / "scripts"))

import store_snapshot as ss  # noqa: E402

# 🔴 THE OLD GUARD COULD NOT SKIP IN CI. `(ROOT / "infra").exists()` is true in every
# checkout (the directory is committed) and `docker ps` succeeds on every GitHub runner, so
# both proxies were TRUE where there is no stack at all. 22 red-ability proofs ran on the
# runner and failed with `could not read NEO4J_PASSWORD`, `SnapshotUnavailable`,
# `httpx.ConnectError` and `psql failed` -- every one of them saying only "no stack here".
# `live_stack.up()` probes the thing itself, via the anchor gate-wiring-gate already uses.
pytestmark = pytest.mark.skipif(not live_stack.up(), reason=live_stack.REASON)


def _sql(db: str, q: str) -> str:
    return subprocess.run(
        ["docker", "exec", "-i", "infra-postgres-1", "psql", "-U", "loreweave", "-d", db, "-At", "-c", q],
        capture_output=True, text=True,
    ).stdout.strip()


def _owner() -> str:
    from eval.tool_liveness import config
    return config.USER_ID


def test_the_table_really_has_no_book_scoping():
    """ANTI-VACUITY, and the check that settled a RETRACTED claim the other way. The same
    assertion was once made for authoring_runs and plan_run and withdrawn, because both DO
    carry book_id. A blind spot is provable — one query against information_schema."""
    cols = _sql("loreweave_jobs",
                "SELECT string_agg(column_name, ',') FROM information_schema.columns "
                "WHERE table_name='job_projection';")
    assert "book_id" not in cols, f"job_projection now has a book scope: {cols}"
    assert "owner_user_id" in cols
    in_params = _sql("loreweave_jobs",
                     "SELECT count(*) FROM job_projection WHERE params ? 'book_id';")
    assert in_params == "0", (
        f"{in_params} rows carry book_id in params — scope through THAT instead of the owner"
    )


def test_the_counter_reads_the_owners_jobs():
    got = ss._job_counts(_owner())
    key = "loreweave_jobs.job_projection.owner"
    assert key in got, got
    total = int(_sql("loreweave_jobs",
                     f"SELECT count(*) FROM job_projection WHERE owner_user_id='{_owner()}';") or 0)
    assert got[key]["rows"] == total


def test_a_stranger_counts_nothing():
    """PRECISION. The scope is the owner, not the table."""
    assert ss._job_counts("00000000-0000-4000-8000-000000000000") == {}


def test_a_STATUS_change_is_visible_even_though_the_row_count_holds():
    """The measured case. `jobs_pause` moves status, not the row count — so `latest`
    (max job_updated_at) is what has to carry it, and the diff has to notice."""
    key = "loreweave_jobs.job_projection.owner"
    before = {key: {"rows": 1414, "latest": "2026-08-25 17:17:10+00"}}
    paused = {key: {"rows": 1414, "latest": "2026-08-27 09:00:00+00"}}
    assert ss.diff(before, paused), "a status change with a steady row count is still invisible"
    created = {key: {"rows": 1415, "latest": "2026-08-27 09:00:00+00"}}
    assert ss.diff(before, created)
    assert not ss.diff(before, before), "an unchanged store must stay silent"


def test_snapshot_ITSELF_carries_it():
    """Through the front door — a counter nothing calls is the same defect by another route,
    and a guard that only calls the helper cannot tell the difference."""
    book = _sql("loreweave_book", f"SELECT id FROM books WHERE owner_user_id='{_owner()}' LIMIT 1;")
    if not book:
        pytest.skip("the harness account owns no book")
    assert not any("job_projection" in k for k in ss.snapshot(book)), (
        "the book-scoped sweep already sees jobs — this test's premise is gone"
    )
    withowner = ss.snapshot(book, owner_user_id=_owner())
    assert any("job_projection" in k for k in withowner), withowner


def test_the_runner_passes_the_owner():
    src = (ROOT / "scripts" / "toolloop" / "fe_runner.py").read_text(encoding="utf-8")
    assert src.count("auth.user_id)") >= 2, (
        "fe_runner does not pass the owner to BOTH snapshots (before and after)"
    )
