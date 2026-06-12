"""Non-destructive live proof of the compose_draft technique migration (slice 1 T1).

Runs the real migration DDL against the LIVE loreweave_lore_enrichment Postgres
(which already has the enrichment tables with the OLD 4-value technique CHECK from
the running service's startup — the exact "already-deployed" scenario the DO-block
migration must widen), then inserts a compose_draft job + proposal and a bogus
technique, asserting the first succeeds and the second is rejected.

EVERYTHING runs inside a transaction that is ROLLED BACK — Postgres DDL is
transactional, so the shared DB is left byte-identical (no schema change persists).
This proves the migration SQL is valid + the widened CHECK admits compose_draft
WITHOUT mutating the stack the other worktree is using.

Run:  python scripts/smoke_compose_draft_migration.py
"""

from __future__ import annotations

import asyncio
import os

import asyncpg

from app.db.migrate import DDL  # imports asyncpg only — no app.config / env needed

DSN = os.environ.get(
    "LORE_ENRICHMENT_DB_URL",
    "postgresql://loreweave:loreweave_dev@localhost:5555/loreweave_lore_enrichment",
)
_PROJECT = "33333333-3333-3333-3333-333333333333"
_USER = "44444444-4444-4444-4444-444444444444"


async def main() -> int:
    conn = await asyncpg.connect(DSN)
    try:
        # Confirm we are hitting the already-deployed table with the OLD constraint.
        old = await conn.fetchval(
            "SELECT pg_get_constraintdef(oid) FROM pg_constraint "
            "WHERE conname = 'enrichment_job_technique_check'"
        )
        print(f"pre-migration enrichment_job CHECK: {old}")

        tr = conn.transaction()
        await tr.start()
        try:
            # Apply the real migration DDL (idempotent; widens the technique CHECK).
            await conn.execute(DDL)
            vocab = await conn.fetchval(
                "SELECT pg_get_constraintdef(oid) FROM pg_constraint "
                "WHERE conname = 'enrichment_job_technique_vocab'"
            )
            print(f"post-migration enrichment_job CHECK: {vocab}")
            assert vocab and "compose_draft" in vocab, "vocab constraint missing compose_draft"

            # A compose_draft job + proposal must INSERT (the widened CHECK admits it).
            job_id = await conn.fetchval(
                """INSERT INTO enrichment_job (project_id, user_id, technique, entity_kind)
                   VALUES ($1,$2,'compose_draft','generic') RETURNING job_id""",
                _PROJECT, _USER,
            )
            pid = await conn.fetchval(
                """INSERT INTO enrichment_proposal
                     (job_id, project_id, user_id, entity_kind, canonical_name, content,
                      technique, confidence, provenance_json)
                   VALUES ($1,$2,$3,'generic','新天地','概述：作者草稿扩写……',
                           'compose_draft', 0.30, '{"seed":"author_draft"}'::jsonb)
                   RETURNING proposal_id""",
                job_id, _PROJECT, _USER,
            )
            print(f"inserted compose_draft job={job_id} proposal={pid} ✓")

            # A genuinely-unknown technique must STILL be rejected (CHECK widened, not dropped).
            sp = conn.transaction()
            await sp.start()
            rejected = False
            try:
                await conn.execute(
                    """INSERT INTO enrichment_job (project_id, user_id, technique, entity_kind)
                       VALUES ($1,$2,'totally_made_up','generic')""",
                    _PROJECT, _USER,
                )
            except asyncpg.PostgresError as exc:
                rejected = True
                print(f"bogus technique rejected ✓ ({type(exc).__name__})")
            finally:
                await sp.rollback()
            assert rejected, "bogus technique was NOT rejected — CHECK is too loose"
        finally:
            await tr.rollback()  # leave the shared DB byte-identical

        # Prove the rollback restored the prior state (no vocab constraint persisted).
        still = await conn.fetchval(
            "SELECT pg_get_constraintdef(oid) FROM pg_constraint "
            "WHERE conname = 'enrichment_job_technique_vocab'"
        )
        assert still is None, "ROLLBACK failed — vocab constraint leaked into shared DB!"
        print("rolled back — shared DB untouched ✓")
        print("\nLIVE-SMOKE T1 PASS: compose_draft migration valid on the deployed DB.")
        return 0
    finally:
        await conn.close()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
