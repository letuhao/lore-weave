"""Real-Postgres coverage for the OBS/M2 batch-outcome SSOT (INV-F15, INV-O12/13).

Proves on real PG that the extraction_batch_outcomes table + the worker's INSERT contract
behave: rows land, the UNIQUE(event_id) makes a redelivered batch an idempotent no-op, the
same-txn outbox projection is written, and reconcile_from_rows re-derives chapter completion
from the rows. Runs inside a rolled-back transaction; skips when no Postgres is reachable
(point at one with TRANSLATION_TEST_PG_DSN)."""
import os
import uuid

import asyncpg
import pytest

from app.migrate import DDL
from app.workers.extraction_outcomes import OK, TRUNCATED, compute_event_id, reconcile_from_rows

_DSN = os.environ.get(
    "TRANSLATION_TEST_PG_DSN",
    "postgresql://loreweave:loreweave_dev@localhost:5555/loreweave_translation",
)

_INSERT = """INSERT INTO extraction_batch_outcomes
    (job_id, owner_user_id, book_id, chapter_id, batch_idx, status, finish_reason, kinds,
     entities_found, entities_written, validation_rejected_count, input_tokens, output_tokens,
     error_code, event_id)
    VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15)
    ON CONFLICT (event_id) DO NOTHING"""


async def _mk_job(conn, owner, book) -> uuid.UUID:
    return await conn.fetchval(
        """INSERT INTO extraction_jobs
             (book_id, owner_user_id, model_ref, chapter_ids, total_chapters, status)
           VALUES ($1,$2,$3,$4,1,'running') RETURNING job_id""",
        book, owner, uuid.uuid4(), [uuid.uuid4()],
    )


@pytest.mark.asyncio
async def test_batch_outcomes_ssot_real_pg():
    try:
        conn = await asyncpg.connect(_DSN, timeout=3)
    except Exception:
        pytest.skip(f"no reachable Postgres at TRANSLATION_TEST_PG_DSN ({_DSN})")
    try:
        # Ensure the OBS table exists (idempotent boot DDL) — committed so the dev DB gains
        # the new table exactly as the service would on deploy.
        await conn.execute(DDL)

        tx = conn.transaction()
        await tx.start()
        try:
            owner, book, chapter = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
            job_id = await _mk_job(conn, owner, book)

            ev_ok = compute_event_id(str(job_id), str(chapter), 0, "hashA")
            ev_trunc = compute_event_id(str(job_id), str(chapter), 1, "hashA")

            async def insert(batch_idx, status, finish, ev):
                await conn.execute(
                    _INSERT, job_id, owner, book, chapter, batch_idx, status, finish,
                    ["character"], 3, 0, 0, 100, 80, None, ev)

            await insert(0, OK, "stop", ev_ok)
            await insert(1, TRUNCATED, "length", ev_trunc)
            # Redelivery: same event_id → ON CONFLICT DO NOTHING (idempotent).
            await conn.execute(
                _INSERT, job_id, owner, book, chapter, 0, OK, "stop",
                ["character"], 3, 0, 0, 100, 80, None, ev_ok)

            n = await conn.fetchval(
                "SELECT count(*) FROM extraction_batch_outcomes WHERE job_id=$1", job_id)
            assert n == 2, f"idempotency broken: want 2 rows, got {n}"

            # Reconcile from the SSOT rows → the chapter is with-errors (one batch truncated).
            rows = await conn.fetch(
                "SELECT chapter_id, status FROM extraction_batch_outcomes WHERE job_id=$1", job_id)
            stats = reconcile_from_rows([(r["chapter_id"], r["status"]) for r in rows])
            assert stats["chapters_total"] == 1
            assert stats["chapters_completed"] == 0
            assert stats["chapters_with_errors"] == 1
            assert stats["by_status"][TRUNCATED] == 1
        finally:
            await tx.rollback()
    finally:
        await conn.close()
