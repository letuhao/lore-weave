"""C2 — migration up/down idempotency against a REAL Postgres.

Asserts the acceptance gate:
  1. upgrade() creates all 5 tables + the H0 trigger.
  2. downgrade() reverses to empty with no orphaned objects (table /
     trigger / function all gone).
  3. up→down→up is idempotent (re-apply collides on nothing).

Skips when no real DB is reachable (see conftest._dsn); verify-cycle-2.sh
supplies the compose Postgres so this runs for real in the CI gate.
"""

from __future__ import annotations

import uuid

import pytest

from app.db.migrate import run_down_migrations, run_migrations

pytestmark = pytest.mark.asyncio

_PROJECT = uuid.uuid4()
_USER = uuid.uuid4()

TABLES = [
    "source_corpus",
    "source_corpus_chunk",
    "cultural_grounding_ref",
    "enrichment_template",
    "enrichment_job",
    "enrichment_proposal",
    "enrichment_eval_runs",  # C15 additive eval table
]


async def _table_exists(conn, name: str) -> bool:
    return await conn.fetchval("SELECT to_regclass($1) IS NOT NULL", name)


async def _trigger_exists(conn) -> bool:
    return await conn.fetchval(
        "SELECT EXISTS (SELECT 1 FROM pg_trigger "
        "WHERE tgname = 'trg_enrichment_proposal_h0' AND NOT tgisinternal)"
    )


async def _function_exists(conn) -> bool:
    return await conn.fetchval(
        "SELECT EXISTS (SELECT 1 FROM pg_proc "
        "WHERE proname = 'enrichment_proposal_h0_guard')"
    )


async def test_upgrade_creates_all_objects(pool):
    # The fixture already ran down→up; assert the full object set is present.
    async with pool.acquire() as conn:
        for t in TABLES:
            assert await _table_exists(conn, t), f"missing table {t}"
        assert await _trigger_exists(conn), "missing H0 trigger"
        assert await _function_exists(conn), "missing H0 guard function"


async def test_downgrade_reverses_to_empty(pool):
    await run_down_migrations(pool)
    async with pool.acquire() as conn:
        for t in TABLES:
            assert not await _table_exists(conn, t), f"orphaned table {t}"
        assert not await _trigger_exists(conn), "orphaned trigger after down"
        assert not await _function_exists(conn), "orphaned function after down"
    # Restore so the fixture's teardown + later tests see a consistent state.
    await run_migrations(pool)


async def test_up_down_up_idempotent(pool):
    # A second up on an already-migrated DB must not collide.
    await run_migrations(pool)
    await run_down_migrations(pool)
    # Down on an already-down DB must not error (IF EXISTS everywhere).
    await run_down_migrations(pool)
    await run_migrations(pool)
    await run_migrations(pool)
    async with pool.acquire() as conn:
        for t in TABLES:
            assert await _table_exists(conn, t), f"missing {t} after round-trip"
        assert await _trigger_exists(conn)


async def test_confidence_check_rejects_canon(pool):
    """H0 at INSERT time: a proposal can never be born with confidence >= 1.0."""
    job_id = await _seed_job(pool)
    async with pool.acquire() as conn:
        with pytest.raises(Exception):  # asyncpg.CheckViolationError
            await conn.execute(
                """
                INSERT INTO enrichment_proposal
                  (job_id, project_id, user_id, entity_kind, content,
                   technique, confidence)
                VALUES ($1,$2,$3,'location','x','template', 1.0)
                """,
                job_id,
                _PROJECT,
                _USER,
            )


async def test_source_corpus_license_check_constraint(pool):
    """C17: the additive license CHECK pins source_corpus.license to the
    recognised vocabulary — the C2 default 'public-domain' is admitted; a garbage
    free-text license is REJECTED at the schema level (so a corpus can never carry
    a license the default-deny normaliser would silently treat as UNKNOWN)."""
    async with pool.acquire() as conn:
        # admissible / honest statuses persist (the DB records the truth)
        for lic in ("public-domain", "public_domain", "licensed",
                    "unlicensed", "copyrighted", "restricted", "unknown"):
            cid = await conn.fetchval(
                """INSERT INTO source_corpus (project_id, user_id, name, kind, license)
                   VALUES ($1,$2,$3,'history',$4) RETURNING corpus_id""",
                _PROJECT, _USER, f"corpus-{lic}", lic,
            )
            assert cid is not None
        # garbage free-text license → CHECK violation
        with pytest.raises(Exception):  # asyncpg.CheckViolationError
            await conn.execute(
                """INSERT INTO source_corpus (project_id, user_id, name, kind, license)
                   VALUES ($1,$2,'corpus-bad','history','cc-by-nc-totally-made-up')""",
                _PROJECT, _USER,
            )


async def _seed_job(pool) -> uuid.UUID:
    async with pool.acquire() as conn:
        return await conn.fetchval(
            """
            INSERT INTO enrichment_job (project_id, user_id, technique, entity_kind)
            VALUES ($1, $2, 'template', 'location')
            RETURNING job_id
            """,
            _PROJECT,
            _USER,
        )
