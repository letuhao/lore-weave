"""Real-Postgres coverage for the P4 job-level token-SUM + cost column.

D-JOBS-P4-TRANSL-TOKENS-PG: the finalize token-SUM was only FakeConn-tested (a mock
returns a canned row, never exercising COALESCE/SUM over real rows). This proves the exact
aggregate query sums across multiple chapter_translations rows and COALESCEs NULL tokens to
0. D-JOBS-P4-TRANSLATION-COST: also proves the additive translation_jobs.cost_usd column
exists and round-trips a NUMERIC. Runs inside a rolled-back transaction; skips when no
Postgres is reachable (point at one with TRANSLATION_TEST_PG_DSN)."""
import os
import uuid
from decimal import Decimal

import asyncpg
import pytest

_DSN = os.environ.get(
    "TRANSLATION_TEST_PG_DSN",
    "postgresql://loreweave:loreweave_dev@localhost:5555/loreweave_translation",
)

_SUM_SQL = (
    "SELECT COALESCE(SUM(input_tokens),0) AS ti, "
    "COALESCE(SUM(output_tokens),0) AS toks_out "
    "FROM chapter_translations WHERE job_id=$1"
)


async def _mk_job(conn) -> uuid.UUID:
    return await conn.fetchval(
        """INSERT INTO translation_jobs
             (book_id, owner_user_id, target_language, model_source, model_ref,
              system_prompt, user_prompt_tpl, chapter_ids, total_chapters, status)
           VALUES ($1,$2,'vi','user_model',$3,'sp','up',$4,3,'running')
           RETURNING job_id""",
        uuid.uuid4(), uuid.uuid4(), uuid.uuid4(), [uuid.uuid4()],
    )


async def _mk_ct(conn, job_id, *, in_tok, out_tok):
    await conn.execute(
        """INSERT INTO chapter_translations
             (job_id, chapter_id, book_id, owner_user_id, target_language,
              status, version_num, input_tokens, output_tokens)
           VALUES ($1,$2,$3,$4,'vi','completed',1,$5,$6)""",
        job_id, uuid.uuid4(), uuid.uuid4(), uuid.uuid4(), in_tok, out_tok,
    )


@pytest.mark.asyncio
async def test_token_sum_and_cost_column_real_pg():
    try:
        conn = await asyncpg.connect(_DSN, timeout=3)
    except Exception:
        pytest.skip(f"no reachable Postgres at TRANSLATION_TEST_PG_DSN ({_DSN})")
    try:
        tx = conn.transaction()
        await tx.start()
        try:
            job_id = await _mk_job(conn)
            # three chapters; the third has NULL tokens (a non-text / failed chapter) →
            # COALESCE must treat it as 0, not poison the SUM into NULL.
            await _mk_ct(conn, job_id, in_tok=1000, out_tok=800)
            await _mk_ct(conn, job_id, in_tok=500, out_tok=200)
            await _mk_ct(conn, job_id, in_tok=None, out_tok=None)

            row = await conn.fetchrow(_SUM_SQL, job_id)
            assert int(row["ti"]) == 1500
            assert int(row["toks_out"]) == 1000

            # The additive cost_usd column exists and round-trips a NUMERIC (the finalize
            # UPDATE persists the derived cost; the GUI reads it from the projection).
            await conn.execute(
                "UPDATE translation_jobs SET cost_usd = COALESCE($2, cost_usd) WHERE job_id=$1",
                job_id, Decimal("0.4242"),
            )
            got = await conn.fetchval("SELECT cost_usd FROM translation_jobs WHERE job_id=$1", job_id)
            assert got == Decimal("0.4242")
            # COALESCE keeps the prior value when a later resolve returns NULL (best-effort).
            await conn.execute(
                "UPDATE translation_jobs SET cost_usd = COALESCE($2, cost_usd) WHERE job_id=$1",
                job_id, None,
            )
            assert await conn.fetchval(
                "SELECT cost_usd FROM translation_jobs WHERE job_id=$1", job_id
            ) == Decimal("0.4242")
        finally:
            await tx.rollback()
    finally:
        await conn.close()
