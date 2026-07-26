"""Real-Postgres regression test for the publish-on-completion promotion guard.

Executes the EXACT statement the worker runs (`_PROMOTE_ACTIVE_SQL`, imported — not
a copy) against a live Postgres, covering all branches of the auto-promote logic:

  A. no active row yet            → INSERT promotes the clean version
  B. current active is an llm draft → DO UPDATE promotes the newer clean version
  C. current active is a human edit → guard SKIPS (the human's version stays active)
  D. new version is verifier-flagged (unresolved_high_count>0) → M5b gate SKIPS

Everything runs inside a transaction that is rolled back, so it never pollutes data.
Skips cleanly when no Postgres is reachable (CI without the stack) — point it at one
with TRANSLATION_TEST_PG_DSN. The mock-based test_chapter_worker.py asserts the SQL is
wired in; this proves the SQL actually behaves.
"""
import os
import uuid

import asyncpg
import pytest

from app.workers.chapter_worker import _PROMOTE_ACTIVE_SQL

_DSN = os.environ.get(
    "TRANSLATION_TEST_PG_DSN",
    "postgresql://loreweave:loreweave_dev@localhost:5555/loreweave_translation",
)

# Shared-dev-Postgres tests - serialize onto one xdist worker
# (`-n auto --dist loadgroup`) so concurrent workers cannot interleave.
pytestmark = pytest.mark.xdist_group("pg")


async def _mk_job(conn, book_id, uid):
    return await conn.fetchval(
        """INSERT INTO translation_jobs
             (book_id, owner_user_id, target_language, model_source, model_ref,
              system_prompt, user_prompt_tpl, chapter_ids)
           VALUES ($1,$2,'vi','user_model',$3,'sp','up',$4::uuid[])
           RETURNING job_id""",
        book_id, uid, uuid.uuid4(), [],
    )


async def _mk_version(conn, job_id, chapter_id, book_id, uid, *, version_num,
                      unresolved=0, authored_by="llm"):
    return await conn.fetchval(
        """INSERT INTO chapter_translations
             (job_id, chapter_id, book_id, owner_user_id, status, target_language,
              version_num, unresolved_high_count, authored_by)
           VALUES ($1,$2,$3,$4,'completed','vi',$5,$6,$7)
           RETURNING id""",
        job_id, chapter_id, book_id, uid, version_num, unresolved, authored_by,
    )


async def _active(conn, chapter_id):
    return await conn.fetchval(
        "SELECT chapter_translation_id FROM active_chapter_translation_versions "
        "WHERE chapter_id=$1 AND target_language='vi'",
        chapter_id,
    )


@pytest.mark.asyncio
async def test_promote_active_sql_all_branches_real_pg():
    try:
        conn = await asyncpg.connect(_DSN, timeout=3)
    except Exception:
        pytest.skip(f"no reachable Postgres at TRANSLATION_TEST_PG_DSN ({_DSN})")

    try:
        tx = conn.transaction()
        await tx.start()
        try:
            book_id, uid, chapter_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
            job = await _mk_job(conn, book_id, uid)

            # A: no active row → first clean version is promoted
            v1 = await _mk_version(conn, job, chapter_id, book_id, uid, version_num=1)
            await conn.execute(_PROMOTE_ACTIVE_SQL, chapter_id, v1)
            assert await _active(conn, chapter_id) == v1, "A: first clean version must publish"

            # B: current active is llm → a newer clean version promotes over it
            v2 = await _mk_version(conn, job, chapter_id, book_id, uid, version_num=2)
            await conn.execute(_PROMOTE_ACTIVE_SQL, chapter_id, v2)
            assert await _active(conn, chapter_id) == v2, "B: clean re-translation must promote over llm active"

            # C: current active is a human edit → promote is skipped
            await conn.execute("UPDATE chapter_translations SET authored_by='human' WHERE id=$1", v2)
            v3 = await _mk_version(conn, job, chapter_id, book_id, uid, version_num=3)
            await conn.execute(_PROMOTE_ACTIVE_SQL, chapter_id, v3)
            assert await _active(conn, chapter_id) == v2, "C: must not clobber a human-edited active version"

            # D: new version verifier-flagged (unresolved>0) → M5b gate skips it
            await conn.execute("UPDATE chapter_translations SET authored_by='llm' WHERE id=$1", v2)
            v4 = await _mk_version(conn, job, chapter_id, book_id, uid, version_num=4, unresolved=3)
            await conn.execute(_PROMOTE_ACTIVE_SQL, chapter_id, v4)
            assert await _active(conn, chapter_id) == v2, "D: a flagged version must not auto-publish"
        finally:
            await tx.rollback()
    finally:
        await conn.close()
