"""25-T1 + 25-T2 — the book-package re-key migration, against a real legacy schema.

Spec: docs/specs/2026-07-01-writing-studio/25_package_migration_master.md (§Test strategy).

The legacy schema is not hand-written here: it is loaded from **git HEAD's `migrate.py`**
and applied verbatim. So this suite always migrates from whatever the previous schema
genuinely was, and cannot drift into testing a fiction of it.

  T1  a legacy DB seeded with per-user rows survives M0→M3: row counts unchanged,
      `created_by` == the old `user_id` bit-for-bit, zero NULL `book_id`, the partial
      uniques/PKs land, C23 derivatives survive, and a second run is a no-op.
      Plus the crash-before-stamp path converges instead of wedging (PM-13).
  T2  every M0 violation class REFUSES the migration, names the offending rows, and
      aborts BEFORE any DDL (PM-7). The failure path is load-bearing — test it, don't
      assume it (`checklist-is-self-report-enforce-by-tests`).

Gated on TEST_COMPOSITION_DB_URL, which MUST name a throwaway DB (the fixture drops every
table). A hard guard refuses any DSN whose database name lacks "test" — this suite would
otherwise destroy the shared dev DB (`kg-integration-tests-truncate-shared-dev-db`).
"""

from __future__ import annotations

import os
import uuid

import asyncpg
import pytest

from app.db.migrate import run_migrations
from app.db.package_rekey import _MARKER, revert_package_rekey

_DSN = os.environ.get("TEST_COMPOSITION_DB_URL")

pytestmark = [
    pytest.mark.skipif(
        not _DSN, reason="set TEST_COMPOSITION_DB_URL to a throwaway DB to run",
    ),
    # Shared-Postgres tests serialize onto one xdist worker (CLAUDE.md).
    pytest.mark.xdist_group("pg"),
]

# The 13 re-keyed package tables (12 BPS-1 + generation_correction).
_BOOK_ID_TABLES = (
    "outline_node", "scene_link", "narrative_thread", "canon_rule", "style_profile",
    "voice_profile", "scene_grounding_pins", "divergence_spec", "entity_override",
    "reference_source", "generation_job", "decompose_commit", "generation_correction",
)
# PM-16 / 00A §8 — outside the package or in the deps/ registry: tenancy UNTOUCHED.
_UNTOUCHED_OWNER_TABLES = ("structure_template", "import_source")

_DROP_ALL_TABLES = """
DO $$
DECLARE r record;
BEGIN
  FOR r IN SELECT tablename FROM pg_tables WHERE schemaname = 'public' LOOP
    EXECUTE 'DROP TABLE IF EXISTS public.' || quote_ident(r.tablename) || ' CASCADE';
  END LOOP;
END $$;
"""


def _guard_throwaway(dsn: str) -> None:
    db = dsn.rsplit("/", 1)[-1].split("?")[0]
    if "test" not in db.lower():
        raise RuntimeError(
            f"REFUSING to run: TEST_COMPOSITION_DB_URL points at {db!r}, which is not a "
            "throwaway DB. This suite drops every table."
        )


async def _build_legacy_schema(p: asyncpg.Pool) -> None:
    """Reshape a throwaway DB into the PRE-re-key (legacy, per-user) schema.

    The obvious trick — `git show HEAD:migrate.py` to load the old _SCHEMA_SQL — is
    FRAGILE: it inverts the moment the re-key commits. Once Deploy 1 is on HEAD, "HEAD's
    schema" IS the migrated schema, and seeding with `user_id` fails. (That is exactly
    how this suite silently broke after the Stage-1 commit.)

    Instead we build the legacy shape from the CURRENT migration and then REVERT it:
    `run_migrations` bootstraps a fresh DB straight into the final shape (marker stamped),
    and `revert_package_rekey` (the PM-13 down-SQL) renames created_by→user_id, drops
    book_id, restores the actor-leading PKs, and clears the marker. `test_t1_down_sql_
    round_trips` proves that down leaves a byte-identical legacy schema. This is
    self-maintaining — no git archaeology — and tracks the real schema as it evolves.
    """
    async with p.acquire() as c:
        await c.execute(_DROP_ALL_TABLES)
    await run_migrations(p)                      # fresh → final shape, marker stamped
    async with p.acquire() as c:
        await revert_package_rekey(c)            # final → legacy (per-user), marker cleared
        # sanity: the legacy shape is genuinely back (user_id present, book_id gone)
        assert await c.fetchval(
            "SELECT EXISTS (SELECT 1 FROM information_schema.columns "
            "WHERE table_name='composition_work' AND column_name='user_id')"
        ), "revert did not restore the legacy per-user schema"
        assert not await c.fetchval(
            "SELECT EXISTS (SELECT 1 FROM information_schema.columns "
            "WHERE table_name='outline_node' AND column_name='book_id')"
        ), "revert left book_id on outline_node — not a legacy schema"


@pytest.fixture
async def legacy_pool():
    """A throwaway DB carrying the PREVIOUS (pre-re-key) schema, wiped on entry and exit."""
    _guard_throwaway(_DSN)
    p = await asyncpg.create_pool(_DSN, min_size=1, max_size=4)
    try:
        await _build_legacy_schema(p)
        yield p
    finally:
        async with p.acquire() as c:
            await c.execute(_DROP_ALL_TABLES)
        await p.close()


async def _seed_legacy(c: asyncpg.Connection) -> dict:
    """One book, one canonical Work + one C23 derivative, and a row in every re-keyed
    table — all stamped with the legacy per-user `user_id`."""
    owner, grantee = uuid.uuid4(), uuid.uuid4()
    book, project, deriv_project = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    chapter = uuid.uuid4()

    work = await c.fetchval(
        "INSERT INTO composition_work (project_id, user_id, book_id) VALUES ($1,$2,$3) RETURNING id",
        project, owner, book,
    )
    # C23 derivative (dị bản): SAME book, its own project + its own partition.
    deriv = await c.fetchval(
        "INSERT INTO composition_work (project_id, user_id, book_id, source_work_id, branch_point) "
        "VALUES ($1,$2,$3,$4,3) RETURNING id",
        deriv_project, owner, book, work,
    )

    chap = await c.fetchval(
        "INSERT INTO outline_node (user_id, project_id, kind, rank, chapter_id) "
        "VALUES ($1,$2,'chapter','a0',$3) RETURNING id",
        owner, project, chapter,
    )
    scene = await c.fetchval(
        "INSERT INTO outline_node (user_id, project_id, parent_id, kind, rank, chapter_id, story_order) "
        "VALUES ($1,$2,$3,'scene','a0',$4,1) RETURNING id",
        owner, project, chap, chapter,
    )
    # A node on the DERIVATIVE's partition — must never merge into the source (PM-3).
    deriv_chap = await c.fetchval(
        "INSERT INTO outline_node (user_id, project_id, kind, rank, chapter_id) "
        "VALUES ($1,$2,'chapter','a0',$3) RETURNING id",
        owner, deriv_project, uuid.uuid4(),
    )
    await c.execute(
        "INSERT INTO scene_link (user_id, project_id, from_node_id, to_node_id) VALUES ($1,$2,$3,$4)",
        owner, project, scene, chap,
    )
    await c.execute(
        "INSERT INTO canon_rule (user_id, project_id, text, scope) VALUES ($1,$2,'The king is dead','reveal_gate')",
        owner, project,
    )
    await c.execute(
        "INSERT INTO narrative_thread (user_id, project_id, kind, summary) VALUES ($1,$2,'promise','a debt')",
        owner, project,
    )
    # A grantee-authored style row: distinct actor, distinct scope (M0.6 must stay clean).
    await c.execute(
        "INSERT INTO style_profile (user_id, project_id, scope_type, scope_id, density, pace) "
        "VALUES ($1,$2,'work',$3,50,50)",
        owner, project, work,
    )
    await c.execute(
        "INSERT INTO style_profile (user_id, project_id, scope_type, scope_id, density, pace) "
        "VALUES ($1,$2,'chapter',$3,60,40)",
        grantee, project, chapter,
    )
    await c.execute(
        "INSERT INTO voice_profile (user_id, project_id, entity_id, entity_name) VALUES ($1,$2,$3,'Mai')",
        owner, project, uuid.uuid4(),
    )
    await c.execute(
        "INSERT INTO scene_grounding_pins (user_id, project_id, outline_node_id, item_type, item_id, action) "
        "VALUES ($1,$2,$3,'canon',$4,'pin')",
        owner, project, scene, str(uuid.uuid4()),  # item_id is TEXT (a cross-DB id)
    )
    await c.execute(
        "INSERT INTO reference_source (user_id, project_id, content) VALUES ($1,$2,'a passage')",
        owner, project,
    )
    job = await c.fetchval(
        "INSERT INTO generation_job (user_id, project_id, outline_node_id, operation, status) "
        "VALUES ($1,$2,$3,'draft_scene','completed') RETURNING id",
        grantee, project, scene,  # grantee ran it → BYOK spend attribution must survive
    )
    await c.execute(
        "INSERT INTO generation_correction (user_id, project_id, job_id, kind) VALUES ($1,$2,$3,'edit')",
        grantee, project, job,
    )
    await c.execute(
        "INSERT INTO divergence_spec (user_id, project_id, work_id, taxonomy) VALUES ($1,$2,$3,'au')",
        owner, deriv_project, deriv,
    )
    await c.execute(
        "INSERT INTO entity_override (user_id, project_id, work_id, target_entity_id, overridden_fields) "
        "VALUES ($1,$2,$3,$4,'{}'::jsonb)",
        owner, deriv_project, deriv, uuid.uuid4(),
    )
    await c.execute(
        "INSERT INTO decompose_commit (user_id, project_id, structure_node_id, idempotency_key, result) "
        "VALUES ($1,$2,$3,'k1','{}'::jsonb)",
        owner, project, chap,
    )
    return {
        "owner": owner, "grantee": grantee, "book": book, "project": project,
        "deriv_project": deriv_project, "work": work, "deriv": deriv,
        "chap": chap, "scene": scene, "deriv_chap": deriv_chap, "job": job,
    }


async def _counts(c: asyncpg.Connection) -> dict[str, int]:
    return {t: await c.fetchval(f"SELECT count(*) FROM {t}") for t in _BOOK_ID_TABLES}


# style_profile / voice_profile are composite-PK tables with no surrogate `id`.
_ROW_KEY = {
    "style_profile": "project_id, scope_type, scope_id",
    "voice_profile": "project_id, entity_id",
}


async def _actor_map(c: asyncpg.Connection, actor_col: str) -> dict[str, dict]:
    """{table: {row-key: actor}} — so the rename can be checked bit-for-bit."""
    out: dict[str, dict] = {}
    for t in _BOOK_ID_TABLES:
        key = _ROW_KEY.get(t, "id")
        rows = await c.fetch(f"SELECT {key}, {actor_col} AS actor FROM {t}")
        cols = [k.strip() for k in key.split(",")]
        out[t] = {tuple(r[k] for k in cols): r["actor"] for r in rows}
    return out


async def _indexdef(c: asyncpg.Connection, name: str) -> str | None:
    return await c.fetchval(
        "SELECT pg_get_indexdef(i.oid) FROM pg_class i WHERE i.relname = $1", name
    )


# ─────────────────────────────────────────────────────────── T1 — the migration

async def test_t1_legacy_db_migrates_without_loss(legacy_pool):
    async with legacy_pool.acquire() as c:
        seed = await _seed_legacy(c)
        before = await _counts(c)
        actors = await _actor_map(c, "user_id")

    await run_migrations(legacy_pool)

    async with legacy_pool.acquire() as c:
        # (1) nothing was lost or duplicated
        assert await _counts(c) == before

        # (2) created_by == the old user_id, bit-for-bit, on every table
        after = await _actor_map(c, "created_by")
        for t, want in actors.items():
            assert after[t] == want, f"{t}: actor stamp drifted through the rename"

        # (3) book_id backfilled everywhere and correct. The M2 guarantee is "no migrated row
        #     loses its book home" — that still holds for EVERY table, and is the assertion
        #     that matters. How it is ENFORCED differs for one table:
        #
        #     BE-7c made `generation_job.book_id` NULLABLE on purpose. A corpus/book motif-mine
        #     and an arc-import are genuinely NOT Work-bound — there is no composition_work to
        #     derive a book from — and the old code papered over that with a synthetic uuid4()
        #     project_id, which the INSERT…SELECT could not resolve, so the PAID action 500'd
        #     after burning the confirm token. The honesty is now enforced by SHAPE rather than
        #     by NOT NULL: `generation_job_scope_shape` CHECKs both-or-neither, so a half-null
        #     (a book with no project, or vice versa) — the actual tenancy hole — is still
        #     unwritable, and the Work-less OPERATION allowlist lives in the writer.
        for t in _BOOK_ID_TABLES:
            assert await c.fetchval(f"SELECT count(*) FROM {t} WHERE book_id IS NULL") == 0, t
            nullable = await c.fetchval(
                "SELECT is_nullable FROM information_schema.columns "
                "WHERE table_name = $1 AND column_name = 'book_id'", t,
            )
            if t == "generation_job":
                assert nullable == "YES", "BE-7c: generation_job.book_id is scope-nullable"
                shape = await c.fetchval(
                    "SELECT count(*) FROM pg_constraint "
                    "WHERE conname = 'generation_job_scope_shape'")
                assert shape == 1, (
                    "generation_job.book_id is nullable but the both-or-neither CHECK is GONE — "
                    "that IS the tenancy hole (a book_id with no project). Restore it."
                )
            else:
                assert nullable == "NO", f"{t}.book_id must be NOT NULL after M2"
            assert await c.fetchval(f"SELECT count(*) FROM {t} WHERE book_id <> $1", seed["book"]) == 0, t

        # (4) PM-3: the derivative keeps its OWN partition — it did not merge into the source
        assert await c.fetchval(
            "SELECT project_id FROM outline_node WHERE id = $1", seed["deriv_chap"],
        ) == seed["deriv_project"]
        assert await c.fetchval(
            "SELECT count(*) FROM outline_node WHERE project_id = $1", seed["project"],
        ) == 2  # chap + scene — the derivative's node did NOT leak in

        # (5) PM-4: both Works survive on one book; the canonical unique is PARTIAL
        assert await c.fetchval("SELECT count(*) FROM composition_work WHERE book_id = $1", seed["book"]) == 2
        book_uq = await _indexdef(c, "uq_composition_work_book")
        assert book_uq and "source_work_id IS NULL" in book_uq and "book_id" in book_uq
        pending_uq = await _indexdef(c, "uq_composition_work_pending")
        assert pending_uq and "user_id" not in pending_uq and "pending_project_backfill" in pending_uq

        # a SECOND canonical Work on the same book must now be rejected by the DB
        with pytest.raises(asyncpg.UniqueViolationError):
            await c.execute(
                "INSERT INTO composition_work (project_id, created_by, book_id) VALUES ($1,$2,$3)",
                uuid.uuid4(), seed["owner"], seed["book"],
            )
        # ...but ANOTHER derivative on the same book is still legal (C23 preserved)
        await c.execute(
            "INSERT INTO composition_work (project_id, created_by, book_id, source_work_id, branch_point) "
            "VALUES ($1,$2,$3,$4,5)",
            uuid.uuid4(), seed["owner"], seed["book"], seed["work"],
        )

        # (6) PM-10: the exactly-once ledger is scoped (project_id, key) — NOT (book_id, key),
        # so the derivative may replay the same client key and get its OWN row.
        idem = await _indexdef(c, "idx_decompose_commit_idem")
        assert idem and "project_id" in idem and "idempotency_key" in idem and "user_id" not in idem
        await c.execute(
            "INSERT INTO decompose_commit (created_by, project_id, book_id, structure_node_id, idempotency_key, result) "
            "VALUES ($1,$2,$3,$4,'k1','{}'::jsonb)",
            seed["owner"], seed["deriv_project"], seed["book"], seed["deriv_chap"],
        )
        with pytest.raises(asyncpg.UniqueViolationError):
            await c.execute(
                "INSERT INTO decompose_commit (created_by, project_id, book_id, structure_node_id, idempotency_key, result) "
                "VALUES ($1,$2,$3,$4,'k1','{}'::jsonb)",
                seed["owner"], seed["project"], seed["book"], seed["chap"],
            )

        # (7) PM-5/M3.4: the actor is out of ROW IDENTITY on the composite-PK tables
        for table, want in (
            ("style_profile", {"project_id", "scope_type", "scope_id"}),
            ("voice_profile", {"project_id", "entity_id"}),
        ):
            cols = {
                r["attname"] for r in await c.fetch(
                    "SELECT a.attname FROM pg_constraint c "
                    "JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = ANY(c.conkey) "
                    "WHERE c.conname = $1", f"{table}_pkey",
                )
            }
            assert cols == want, f"{table} PK still embeds the actor: {cols}"

        # ...proven by EFFECT: a second actor writing the SAME scope UPDATES in place
        await c.execute(
            "INSERT INTO style_profile (created_by, project_id, book_id, scope_type, scope_id, density, pace) "
            "VALUES ($1,$2,$3,'work',$4,90,10) "
            "ON CONFLICT (project_id, scope_type, scope_id) "
            "DO UPDATE SET density = EXCLUDED.density, pace = EXCLUDED.pace, created_by = EXCLUDED.created_by",
            seed["grantee"], seed["project"], seed["book"], seed["work"],
        )
        rows = await c.fetch(
            "SELECT created_by, density FROM style_profile WHERE project_id = $1 AND scope_type = 'work'",
            seed["project"],
        )
        assert len(rows) == 1, "a grantee forked the shared style row instead of updating it (DA-11)"
        assert rows[0]["density"] == 90 and rows[0]["created_by"] == seed["grantee"]

        # (8) BYOK spend attribution survives: the job's actor is the grantee who ran it
        assert await c.fetchval(
            "SELECT created_by FROM generation_job WHERE id = $1", seed["job"],
        ) == seed["grantee"]

        # (9) PM-16 / deps registry: outside-the-package tenancy is UNTOUCHED
        for t in _UNTOUCHED_OWNER_TABLES:
            assert await c.fetchval(
                "SELECT EXISTS (SELECT 1 FROM information_schema.columns "
                "WHERE table_name = $1 AND column_name = 'owner_user_id')", t,
            ), f"{t}.owner_user_id must survive the re-key (PM-16)"

        # (10) the .runs/ tables renamed their actor too (PM-5)
        for t in ("plan_run", "plan_artifact", "authoring_runs", "plan_bootstrap_proposal"):
            assert await c.fetchval(
                "SELECT EXISTS (SELECT 1 FROM information_schema.columns "
                "WHERE table_name = $1 AND column_name = 'created_by')", t,
            ), f"{t} kept owner_user_id"

        # (11) no re-keyed table kept the old actor name (DA-10: one name per concept)
        for t in (*_BOOK_ID_TABLES, "composition_work", "motif_application"):
            assert not await c.fetchval(
                "SELECT EXISTS (SELECT 1 FROM information_schema.columns "
                "WHERE table_name = $1 AND column_name = 'user_id')", t,
            ), f"{t} still has user_id"


async def test_t1_second_run_is_a_noop(legacy_pool):
    async with legacy_pool.acquire() as c:
        await _seed_legacy(c)
    await run_migrations(legacy_pool)
    async with legacy_pool.acquire() as c:
        before = await _counts(c)
    await run_migrations(legacy_pool)  # must not error, re-backfill, or double-seed
    async with legacy_pool.acquire() as c:
        assert await _counts(c) == before
        assert await c.fetchval("SELECT count(*) FROM package_migration WHERE marker = $1", _MARKER) == 1


async def test_t1_crash_before_marker_stamp_converges(legacy_pool):
    """PM-13 rollback/idempotency: a crash after M3 but before the marker stamp must
    converge on the next boot, not wedge. Simulated by deleting the marker and re-running:
    every M0/M2/M3 step then re-executes against an ALREADY-migrated schema."""
    async with legacy_pool.acquire() as c:
        await _seed_legacy(c)
    await run_migrations(legacy_pool)
    async with legacy_pool.acquire() as c:
        before = await _counts(c)
        await c.execute("DELETE FROM package_migration WHERE marker = $1", _MARKER)

    await run_migrations(legacy_pool)  # the crash-resume path

    async with legacy_pool.acquire() as c:
        assert await _counts(c) == before
        assert await c.fetchval("SELECT count(*) FROM package_migration WHERE marker = $1", _MARKER) == 1
        for table, want in (
            ("style_profile", {"project_id", "scope_type", "scope_id"}),
            ("voice_profile", {"project_id", "entity_id"}),
        ):
            cols = {
                r["attname"] for r in await c.fetch(
                    "SELECT a.attname FROM pg_constraint c "
                    "JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = ANY(c.conkey) "
                    "WHERE c.conname = $1", f"{table}_pkey",
                )
            }
            assert cols == want, f"{table} PK diverged on the crash-resume path"


async def _schema_fingerprint(c: asyncpg.Connection) -> dict:
    """Columns (name/type/nullability), index definitions, and PK column sets for every
    re-keyed table — enough to prove two schemas are the same one."""
    tables = (*_BOOK_ID_TABLES, "composition_work", "motif_application",
              "plan_run", "plan_artifact", "authoring_runs", "plan_bootstrap_proposal")
    cols = await c.fetch(
        """SELECT table_name, column_name, data_type, is_nullable
           FROM information_schema.columns WHERE table_name = ANY($1::text[])
           ORDER BY table_name, column_name""", list(tables),
    )
    idx = await c.fetch(
        """SELECT tablename, indexname, indexdef FROM pg_indexes
           WHERE schemaname = 'public' AND tablename = ANY($1::text[])
           ORDER BY tablename, indexname""", list(tables),
    )
    pks = await c.fetch(
        """SELECT c.conrelid::regclass::text AS tbl, a.attname
           FROM pg_constraint c JOIN pg_attribute a
             ON a.attrelid = c.conrelid AND a.attnum = ANY(c.conkey)
           WHERE c.contype = 'p' AND c.conrelid::regclass::text = ANY($1::text[])
           ORDER BY tbl, a.attname""", list(tables),
    )
    return {
        "columns": [tuple(r) for r in cols],
        "indexes": [tuple(r) for r in idx],
        "pks": [tuple(r) for r in pks],
    }


async def test_t1_down_sql_round_trips(legacy_pool):
    """PM-13: 'M1-M2 are reversible by dropping the new columns/indexes; M3's renames
    reverse by renaming back.' That was a CLAIM. This is the effect: up → down → up must
    land on a byte-identical schema, and the down must genuinely restore the old shape."""
    async with legacy_pool.acquire() as c:
        seed = await _seed_legacy(c)
        legacy_counts = await _counts(c)

    await run_migrations(legacy_pool)
    async with legacy_pool.acquire() as c:
        up1 = await _schema_fingerprint(c)

    # ── down
    async with legacy_pool.acquire() as c:
        await revert_package_rekey(c)

        # the old shape is genuinely back
        for t in _BOOK_ID_TABLES:
            assert not await c.fetchval(
                "SELECT EXISTS (SELECT 1 FROM information_schema.columns "
                "WHERE table_name = $1 AND column_name = 'book_id')", t,
            ), f"{t}.book_id survived the revert"
        assert await c.fetchval(
            "SELECT EXISTS (SELECT 1 FROM information_schema.columns "
            "WHERE table_name = 'outline_node' AND column_name = 'user_id')"
        ), "outline_node.user_id was not restored"
        assert await c.fetchval(
            "SELECT EXISTS (SELECT 1 FROM information_schema.columns "
            "WHERE table_name = 'plan_run' AND column_name = 'owner_user_id')"
        ), "plan_run.owner_user_id was not restored"
        style_pk = {
            r["attname"] for r in await c.fetch(
                "SELECT a.attname FROM pg_constraint c JOIN pg_attribute a "
                "ON a.attrelid = c.conrelid AND a.attnum = ANY(c.conkey) "
                "WHERE c.conname = 'style_profile_pkey'"
            )
        }
        assert style_pk == {"user_id", "project_id", "scope_type", "scope_id"}
        assert await c.fetchval(
            "SELECT count(*) FROM package_migration WHERE marker = $1", _MARKER,
        ) == 0, "the marker must clear, or the next boot skips the re-key"
        # data survived the round trip down
        assert await _counts(c) == legacy_counts
        assert await c.fetchval(
            "SELECT user_id FROM generation_job WHERE id = $1", seed["job"],
        ) == seed["grantee"], "the actor value must survive rename → rename-back"

    # ── up again: must converge on the SAME schema, not merely 'a working one'
    await run_migrations(legacy_pool)
    async with legacy_pool.acquire() as c:
        up2 = await _schema_fingerprint(c)
        assert await _counts(c) == legacy_counts

    for key in ("columns", "indexes", "pks"):
        assert up2[key] == up1[key], f"{key} diverged across the down→up round trip"


# ─────────────────────────────────────────── T2 — M0 refuses, loudly, before any DDL

async def _assert_refused(pool, marker_text: str) -> None:
    with pytest.raises(RuntimeError, match=r"M0 pre-flight FAILED") as exc:
        await run_migrations(pool)
    assert marker_text in str(exc.value), f"the error must NAME the violation: {exc.value}"
    async with pool.acquire() as c:
        # PM-7: aborted BEFORE any DDL — the M1 column must not exist
        assert not await c.fetchval(
            "SELECT EXISTS (SELECT 1 FROM information_schema.columns "
            "WHERE table_name = 'outline_node' AND column_name = 'book_id')"
        ), "DDL ran despite a failed pre-flight"
        assert await c.fetchval("SELECT count(*) FROM package_migration WHERE marker = $1", _MARKER) == 0


async def test_t2_m0_1_refuses_two_canonical_works(legacy_pool):
    async with legacy_pool.acquire() as c:
        seed = await _seed_legacy(c)
        await c.execute(
            "INSERT INTO composition_work (project_id, user_id, book_id) VALUES ($1,$2,$3)",
            uuid.uuid4(), seed["owner"], seed["book"],  # a second CANONICAL Work — the F5 fork
        )
    await _assert_refused(legacy_pool, "M0.1")


async def test_t2_a_derivative_alone_does_not_trip_m0_1(legacy_pool):
    """The C23 exemption is the whole point of PM-4: _seed_legacy already creates a
    derivative sharing the book. If M0.1 fired on that, every dị bản book would be
    unmigratable — which is exactly the bug 23's P0.0 query had."""
    async with legacy_pool.acquire() as c:
        await _seed_legacy(c)
    await run_migrations(legacy_pool)  # must NOT raise
    async with legacy_pool.acquire() as c:
        assert await c.fetchval("SELECT count(*) FROM package_migration WHERE marker = $1", _MARKER) == 1


async def test_t2_m0_2_refuses_two_pending_works(legacy_pool):
    async with legacy_pool.acquire() as c:
        seed = await _seed_legacy(c)
        for _ in range(2):
            await c.execute(
                "INSERT INTO composition_work (project_id, user_id, book_id, pending_project_backfill) "
                "VALUES (NULL,$1,$2,true)",
                uuid.uuid4(), seed["book"],
            )
    # Two pending rows are ALSO two canonical rows, so M0.1 fires too — assert M0.2 is named.
    with pytest.raises(RuntimeError, match=r"M0 pre-flight FAILED") as exc:
        await run_migrations(legacy_pool)
    assert "M0.2" in str(exc.value)


async def test_t2_m0_3_refuses_beat_rows(legacy_pool):
    async with legacy_pool.acquire() as c:
        seed = await _seed_legacy(c)
        await c.execute(
            "INSERT INTO outline_node (user_id, project_id, kind, rank) VALUES ($1,$2,'beat','a0')",
            seed["owner"], seed["project"],
        )
    await _assert_refused(legacy_pool, "M0.3")


async def test_t2_m0_4_refuses_orphan_project_rows(legacy_pool):
    async with legacy_pool.acquire() as c:
        seed = await _seed_legacy(c)
        await c.execute(  # a canon_rule whose project has no composition_work row
            "INSERT INTO canon_rule (user_id, project_id, text, scope) VALUES ($1,$2,'orphan','reveal_gate')",
            seed["owner"], uuid.uuid4(),
        )
    await _assert_refused(legacy_pool, "M0.4")


async def test_m0_4_and_m2_agree_on_lazy_work_rows(legacy_pool):
    """A C16 lazy Work has `project_id NULL` and is addressed by its surrogate `id`, so its
    rows ARE recoverable — their book_id lives on the Work.

    TWO predicates must resolve the Work identically, and a mismatch is invisible until a
    real DB has a lazy Work (both bugs below were found by the live dev boot, 2026-07-10):
      · M0.4's anti-join sentinel must be `w.id`, not `w.project_id` — a MATCHED pending
        Work has project_id NULL by definition, so testing that column reports every one of
        its rows as an unrecoverable orphan and refuses the boot.
      · M2's backfill must carry the same disjunct — in BOTH the keyset-batched path
        (outline_node, generation_job) and the single-statement path. Patching only one
        leaves the other silently unable to fill book_id, and the boot dies at the
        zero-NULL assertion instead.

    So this seeds a lazy Work with rows in a BATCH table and a SMALL table.
    """
    async with legacy_pool.acquire() as c:
        seed = await _seed_legacy(c)
        lazy = await c.fetchval(
            "INSERT INTO composition_work (project_id, user_id, book_id, pending_project_backfill) "
            "VALUES (NULL,$1,$2,true) RETURNING id",
            seed["owner"], uuid.uuid4(),  # its own book — M0.1/M0.2 stay clean
        )
        chapter = uuid.uuid4()
        # batch-path tables (keyset backfill)
        node = await c.fetchval(
            "INSERT INTO outline_node (user_id, project_id, kind, rank, chapter_id) "
            "VALUES ($1,$2,'chapter','a0',$3) RETURNING id",
            seed["owner"], lazy, chapter,
        )
        await c.execute(
            "INSERT INTO generation_job (user_id, project_id, outline_node_id, operation, status) "
            "VALUES ($1,$2,$3,'draft_scene','completed')",
            seed["owner"], lazy, node,
        )
        # single-statement path
        await c.execute(
            "INSERT INTO canon_rule (user_id, project_id, text, scope) VALUES ($1,$2,'lazy','world')",
            seed["owner"], lazy,
        )

    await run_migrations(legacy_pool)  # must NOT raise — neither M0.4 nor M2's assertion

    async with legacy_pool.acquire() as c:
        assert await c.fetchval("SELECT count(*) FROM package_migration WHERE marker = $1", _MARKER) == 1
        for t in ("outline_node", "generation_job", "canon_rule"):
            assert await c.fetchval(f"SELECT count(*) FROM {t} WHERE book_id IS NULL") == 0, (
                f"M2 failed to derive book_id for a lazy Work's {t} rows"
            )
        # ...and derived the RIGHT book (the lazy Work's, not the canonical one's)
        lazy_book = await c.fetchval("SELECT book_id FROM composition_work WHERE id = $1", lazy)
        assert await c.fetchval(
            "SELECT book_id FROM outline_node WHERE project_id = $1", lazy,
        ) == lazy_book


async def test_t2_m0_7_refuses_cross_user_duplicate_decompose_keys(legacy_pool):
    """M3.2 NARROWS idx_decompose_commit_idem to (project_id, idempotency_key) (PM-10).
    Two actors who legally replayed the same client key on one project today would
    collide on the narrowed unique — without M0.7 that surfaces as a bare UniqueViolation
    mid-cutover (a crash-looping boot with no operator protocol), not a named refusal."""
    async with legacy_pool.acquire() as c:
        seed = await _seed_legacy(c)
        await c.execute(  # same (project, key) as the owner's row, different actor
            "INSERT INTO decompose_commit (user_id, project_id, structure_node_id, idempotency_key, result) "
            "VALUES ($1,$2,$3,'k1','{}'::jsonb)",
            seed["grantee"], seed["project"], seed["chap"],
        )
    await _assert_refused(legacy_pool, "M0.7")


async def test_t2_m0_6_refuses_cross_user_duplicate_style_rows(legacy_pool):
    """The M3.4 PK narrows to (project_id, scope_type, scope_id). Two actors holding the
    same scope today would collide on that PK — M0.6 must catch it BEFORE the swap."""
    async with legacy_pool.acquire() as c:
        seed = await _seed_legacy(c)
        await c.execute(  # same scope as the owner's 'work' row, different actor
            "INSERT INTO style_profile (user_id, project_id, scope_type, scope_id, density, pace) "
            "VALUES ($1,$2,'work',$3,70,30)",
            seed["grantee"], seed["project"], seed["work"],
        )
    await _assert_refused(legacy_pool, "M0.6")
