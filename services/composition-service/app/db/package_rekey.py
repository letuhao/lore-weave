"""Book-package re-key M0-M3 (spec 25) — pre-flight → backfill → cutover, marker-gated.

The BPS-1/2 re-key (docs/specs/2026-07-01-writing-studio/25_package_migration_master.md):
`book_id` becomes the TENANCY scope key on the 13 package tables while `project_id`
survives as the Work PARTITION key (PM-3), and the actor column demotes to a plain
stamp — `user_id`/`owner_user_id` → `created_by`, STORED, never filtered on (PM-5).
Access is decided BEFORE the repo, at the E0 book gate (PM-8).

Execution shape — ONE marker-gated unit (`pkg_rekey_v1` in `package_migration`),
wired by `migrate.run_migrations` so the two halves run at the right points:

  M0 pre-flight   runs BEFORE any DDL (PM-7). Any hit → the offending rows are
                  logged (ids, counts, per-check label) and the boot FAILS LOUDLY.
                  Nothing is ever silently merged, deleted, or guessed.
  _SCHEMA_SQL     migrate.py's idempotent DDL (the M1 additive book_id columns +
                  indexes + the 23/22 structure/scene DDL ride inline in it) —
                  injected here via `apply_schema` so the unit stays one function.
  M2 backfill     book_id copied from composition_work: keyset 500/batch over the
                  UUIDv7 id for the two big tables (PM-6/F8), single-statement for
                  the small ones, FK-derived for divergence_spec/entity_override
                  (via work_id) and generation_correction (via job_id). Then a
                  zero-NULL assertion per table → NOT NULL flips.
  M3 cutover      manifest uniques (PM-4), decompose_commit ledger re-scope
                  (PM-10), the actor RENAMEs (PM-5), style/voice PK swaps (M3.4).

Every step is guarded/idempotent, so a crash mid-run re-runs safely on the next
boot; the marker stamps only after M3 completes. A fresh DB (no composition_work
table) skips pre-flight + backfill entirely and bootstraps straight into the
final post-M3 shape via _SCHEMA_SQL (whose CREATE TABLE texts already carry
`created_by` + NOT NULL `book_id`).

MANUAL QUARANTINE PROTOCOL (25 §M0 resolution — operator-only, NEVER automated):
when a pre-flight fires, an OPERATOR resolves it by hand, against the snapshot
first — M0.1/M0.2: pick the survivor Work and re-point the loser's children
(`UPDATE … SET project_id = <survivor>` per table) or archive the loser; M0.3:
inspect and hand-delete or re-kind the `kind='beat'` rows; M0.4: archive the
orphans into a `_pkg_rekey_quarantine` side table created BY HAND (this module
never creates or writes it); M0.6: merge duplicate style/voice rows per scope
(pick the survivor — normally the book owner's row — delete the rest); M0.7:
merge duplicate decompose_commit (project, idempotency_key) pairs (keep the
earliest committed result — replay must be idempotent, so the survivor is the
one whose `result` the client already saw). Then re-boot; M0 re-runs. The
2026-07-10 dev-DB preview pre-decided the two known hits (archive the empty
F5-fork Work; archive the four "Beat" rows) and measured M0.7 = 0.
"""

import logging
from collections.abc import Awaitable, Callable

import asyncpg

logger = logging.getLogger(__name__)

_MARKER = "pkg_rekey_v1"

_MARKER_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS package_migration (
  marker     TEXT PRIMARY KEY,
  applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
"""

# The 13 re-keyed package tables (12 BPS-1 + generation_correction) — every one
# gains book_id in M1 and flips it NOT NULL after the M2 backfill. composition_work
# itself already carries book_id NOT NULL.
_BOOK_ID_TABLES = (
    "outline_node",
    "scene_link",
    "narrative_thread",
    "canon_rule",
    "style_profile",
    "voice_profile",
    "scene_grounding_pins",
    "divergence_spec",
    "entity_override",
    "reference_source",
    "generation_job",
    "decompose_commit",
    "generation_correction",
)

# M2 shapes (PM-6): the two tables that track book scale (~4200 chapters) backfill
# in keyset batches; the small project-keyed tables in one statement each; the
# FK-derived trio via their parent row (belt: work_id / job_id, not project_id).
_BATCH_TABLES = ("outline_node", "generation_job")
_SMALL_PROJECT_TABLES = (
    "scene_link",
    "narrative_thread",
    "canon_rule",
    "style_profile",
    "voice_profile",
    "scene_grounding_pins",
    "reference_source",
    "decompose_commit",
)
_BATCH_SIZE = 500

# M0.4 orphan-sweep targets (project-keyed). divergence_spec/entity_override are
# FK'd to composition_work.id — no orphan possible (25 M0.4 note).
_ORPHAN_TABLES = (
    "outline_node",
    "generation_job",
    "scene_link",
    "narrative_thread",
    "canon_rule",
    "style_profile",
    "voice_profile",
    "scene_grounding_pins",
    "reference_source",
    "decompose_commit",
    "generation_correction",
)

# M3.3 actor renames (PM-5): user_id → created_by on the 12 BPS-1 tables +
# composition_work + generation_correction + motif_application; owner_user_id →
# created_by on the four .runs/ tables. Guarded per table, so a table that does
# not exist yet (created fresh by later DDL, already in the final shape) or was
# already renamed (crash re-run) is a no-op.
_USER_ID_RENAMES = (
    "composition_work",
    "outline_node",
    "scene_link",
    "narrative_thread",
    "canon_rule",
    "style_profile",
    "voice_profile",
    "scene_grounding_pins",
    "divergence_spec",
    "entity_override",
    "reference_source",
    "generation_job",
    "decompose_commit",
    "generation_correction",
    "motif_application",
)
_OWNER_USER_ID_RENAMES = (
    "plan_run",
    "plan_artifact",
    "authoring_runs",
    "plan_bootstrap_proposal",
)

# M3.1 + M3.2 (25 verbatim). uq_composition_work_book = ONE CANONICAL manifest per
# book (derivatives and archived Works exempt BY DESIGN — F6/PM-4); the pending
# partial re-keys (user_id, book_id) → (book_id) and stays as the narrow race
# guard the C16 comments reason about. idx_decompose_commit_idem re-scopes to
# (project_id, idempotency_key) — NOT (book_id, …): a derivative replaying a
# client key must not be handed the SOURCE Work's stored result (PM-10).
_M3_INDEX_SQL = """
-- M3.1 · the manifest uniques (PM-4)
CREATE UNIQUE INDEX IF NOT EXISTS uq_composition_work_book
  ON composition_work(book_id) WHERE source_work_id IS NULL AND status = 'active';
DROP INDEX IF EXISTS uq_composition_work_pending;
CREATE UNIQUE INDEX IF NOT EXISTS uq_composition_work_pending
  ON composition_work(book_id) WHERE pending_project_backfill;

-- M3.2 · the exactly-once ledger re-scope (PM-10; the arc_id → structure_node_id
-- column re-point happens in M5, not here)
DROP INDEX IF EXISTS idx_decompose_commit_idem;
CREATE UNIQUE INDEX IF NOT EXISTS idx_decompose_commit_idem
  ON decompose_commit(project_id, idempotency_key);
"""

# M3.3 tail + M3.4 (25 verbatim). The RENAME cascades the old actor indexes'
# definitions to created_by but keeps their names — only the composition_work one
# moves to its final name (spec-mandated). The PK swaps demote created_by to a
# plain actor column: after a bare rename the actor stays part of ROW IDENTITY,
# so a grantee editing a shared profile would INSERT a second row per scope
# instead of updating (DA-11 violated by the PK itself). Safe: M0.6 proved no
# cross-user duplicates. The style_voice.py upserts' ON CONFLICT targets change
# to these PKs in the SAME commit (a conflict target must name a live unique
# constraint — postgres-partial-index-on-conflict-predicate-must-match).
_M3_CUTOVER_TAIL_SQL = """
-- M3.3 tail · the composition_work actor index under its final name
DROP INDEX IF EXISTS idx_composition_work_user;
CREATE INDEX IF NOT EXISTS idx_composition_work_created_by ON composition_work(created_by);

-- M3.4 · composite-PK actor demotion (PM-5)
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM information_schema.constraint_column_usage
             WHERE table_name = 'style_profile' AND constraint_name = 'style_profile_pkey'
               AND table_schema = current_schema()
               AND column_name IN ('user_id', 'created_by')) THEN
    ALTER TABLE style_profile DROP CONSTRAINT style_profile_pkey;
    ALTER TABLE style_profile ADD PRIMARY KEY (project_id, scope_type, scope_id);
  END IF;
END $$;
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM information_schema.constraint_column_usage
             WHERE table_name = 'voice_profile' AND constraint_name = 'voice_profile_pkey'
               AND table_schema = current_schema()
               AND column_name IN ('user_id', 'created_by')) THEN
    ALTER TABLE voice_profile DROP CONSTRAINT voice_profile_pkey;
    ALTER TABLE voice_profile ADD PRIMARY KEY (project_id, entity_id);
  END IF;
END $$;
"""


# ── PM-13 · the reversal (Deploy 1 only; M4/M5 are the point of no return) ───
#
# 25 PM-13 states M1/M2 are "reversible by dropping the new columns/indexes" and
# M3 "reverses by renaming back". That was a CLAIM with no artifact and no test —
# a self-report, not an effect (`checklist-is-self-report-enforce-by-tests`). This
# is the artifact; `test_t1_down_sql_round_trips` is the effect.
#
# Order is the exact inverse of M3 → M2 → M1:
#   1. drop the indexes/uniques that NAME created_by or are new (M3.1/M3.2/M3.3-tail)
#   2. rename created_by back (M3.3)                → user_id / owner_user_id
#   3. restore the actor-leading composite PKs (M3.4)
#   4. recreate the legacy actor-scoped indexes on the restored column names
#   5. drop book_id from the 13 tables (M1.1) — CASCADE takes their M1.2 indexes
#   6. clear the marker so the next boot re-runs M0-M3 from the top
#
# NOT reversed (additive, owned by other specs, harmless on a downed DB):
# `structure_node` + its trigger, `outline_node.structure_node_id` and the 22 SC4
# columns, `motif_application.structure_node_id`. `composition_work.book_id` and
# `motif_application.book_id` predate the re-key and are never dropped.
_DOWN_SQL_TEMPLATE = """
-- 1 · indexes that name created_by, and the re-key's new uniques
DROP INDEX IF EXISTS uq_composition_work_book;
DROP INDEX IF EXISTS idx_composition_work_created_by;
DROP INDEX IF EXISTS uq_composition_work_pending;
DROP INDEX IF EXISTS idx_decompose_commit_idem;

-- 2 · actor renames, back (guarded: no-op if a table is missing / already down)
{renames}

-- 3 · restore the actor-leading composite PKs (M3.4 inverse)
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM information_schema.constraint_column_usage
                 WHERE table_name = 'style_profile' AND constraint_name = 'style_profile_pkey'
                   AND table_schema = current_schema()
                   AND column_name = 'user_id') THEN
    ALTER TABLE style_profile DROP CONSTRAINT IF EXISTS style_profile_pkey;
    ALTER TABLE style_profile ADD PRIMARY KEY (user_id, project_id, scope_type, scope_id);
  END IF;
END $$;
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM information_schema.constraint_column_usage
                 WHERE table_name = 'voice_profile' AND constraint_name = 'voice_profile_pkey'
                   AND table_schema = current_schema()
                   AND column_name = 'user_id') THEN
    ALTER TABLE voice_profile DROP CONSTRAINT IF EXISTS voice_profile_pkey;
    ALTER TABLE voice_profile ADD PRIMARY KEY (user_id, project_id, entity_id);
  END IF;
END $$;

-- 4 · the legacy actor-scoped indexes, on the restored column names
CREATE INDEX IF NOT EXISTS idx_composition_work_user ON composition_work(user_id);
CREATE UNIQUE INDEX IF NOT EXISTS uq_composition_work_pending
  ON composition_work(user_id, book_id) WHERE pending_project_backfill;
CREATE UNIQUE INDEX IF NOT EXISTS idx_decompose_commit_idem
  ON decompose_commit(user_id, project_id, idempotency_key);

-- 5 · drop the tenancy key (CASCADE removes the M1.2 book indexes with it)
{drop_book_id}

-- 6 · clear the marker: the next boot re-runs M0 → M3 from the top
DELETE FROM package_migration WHERE marker = '{marker}';
"""


def _rename_sql_back(table: str, new: str) -> str:
    """Inverse of `_rename_sql`: created_by → the table's original actor name."""
    return f"""
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM information_schema.columns
             WHERE table_name = '{table}' AND column_name = 'created_by'
               AND table_schema = current_schema()) THEN
    ALTER TABLE {table} RENAME COLUMN created_by TO {new};
  END IF;
END $$;"""


def _down_sql() -> str:
    renames = "\n".join(
        _rename_sql_back(t, "user_id") for t in _USER_ID_RENAMES
    ) + "\n" + "\n".join(
        _rename_sql_back(t, "owner_user_id") for t in _OWNER_USER_ID_RENAMES
    )
    drops = "\n".join(
        f"ALTER TABLE {t} DROP COLUMN IF EXISTS book_id CASCADE;" for t in _BOOK_ID_TABLES
    )
    return _DOWN_SQL_TEMPLATE.format(renames=renames, drop_book_id=drops, marker=_MARKER)


async def revert_package_rekey(conn: asyncpg.Connection) -> None:
    """Reverse Deploy 1 (M1-M3) — PM-13's rollback, as an executable artifact.

    Test/operator use only; never called at boot. Safe on an already-reverted DB
    (every step is guarded). After this, a re-boot re-applies M0-M3 and lands on the
    identical schema — asserted by `test_t1_down_sql_round_trips`.
    """
    await conn.execute(_down_sql())
    logger.warning("package re-key REVERTED (PM-13): book_id dropped, actor renamed back")


async def run_package_rekey(
    conn: asyncpg.Connection,
    apply_schema: Callable[[asyncpg.Connection], Awaitable[None]],
) -> bool:
    """Run the marker-gated M0-M3 re-key around `apply_schema` (= _SCHEMA_SQL).

    Returns True when the re-key was applied (or freshly stamped) this boot,
    False when the marker already existed (only the idempotent schema ran).
    PM-7: an M0 violation raises BEFORE apply_schema executes any DDL.
    """
    await conn.execute(_MARKER_TABLE_SQL)
    already = await conn.fetchval(
        "SELECT 1 FROM package_migration WHERE marker = $1", _MARKER
    )
    if already:
        await apply_schema(conn)
        return False

    if not await _table_exists(conn, "composition_work"):
        # Fresh DB: _SCHEMA_SQL bootstraps directly into the final post-M3 shape
        # (created_by columns, NOT NULL book_id, final indexes/PKs) — there is
        # nothing to pre-flight or backfill. Stamp so M0/M2/M3 never run later.
        await apply_schema(conn)
        await _stamp(conn)
        logger.info(
            "package re-key: fresh DB bootstrapped into final shape; marker %s stamped",
            _MARKER,
        )
        return True

    await _preflight_m0(conn)  # PM-7: raises before any DDL on a violation
    await apply_schema(conn)  # M1 additive DDL rides inline in _SCHEMA_SQL
    await _backfill_m2(conn)
    await _cutover_m3(conn)
    await _stamp(conn)
    logger.info("package re-key: M0-M3 applied; marker %s stamped", _MARKER)
    return True


# ── helpers ──────────────────────────────────────────────────────────────────

async def _table_exists(conn: asyncpg.Connection, table: str) -> bool:
    return bool(await conn.fetchval("SELECT to_regclass($1) IS NOT NULL", table))


async def _column_exists(conn: asyncpg.Connection, table: str, column: str) -> bool:
    return bool(
        await conn.fetchval(
            """SELECT EXISTS (SELECT 1 FROM information_schema.columns
                              WHERE table_name = $1 AND column_name = $2
                                AND table_schema = current_schema())""",
            table,
            column,
        )
    )


async def _stamp(conn: asyncpg.Connection) -> None:
    await conn.execute(
        "INSERT INTO package_migration (marker) VALUES ($1) ON CONFLICT (marker) DO NOTHING",
        _MARKER,
    )


# ── M0 — pre-flight assertions (25 lines 131-171, verbatim queries) ──────────

async def _preflight_m0(conn: asyncpg.Connection) -> None:
    """Run M0.1-M0.6 against the pre-DDL schema. Any hit → log offending rows +
    RAISE (PM-7). Checks whose table/old-column is already gone (a pre-feature DB,
    or a crash re-run after M3.3 renamed the actor column) skip — the guarded
    M2/M3 steps make the re-run converge."""
    violations: list[str] = []

    # M0.1 · one CANONICAL Work per book (derivatives exempt BY DESIGN — F6/PM-4).
    rows = await conn.fetch(
        """SELECT book_id, count(*) AS n, array_agg(id) AS ids FROM composition_work
           WHERE source_work_id IS NULL AND status = 'active'
           GROUP BY book_id HAVING count(*) > 1"""
    )
    for r in rows:
        logger.error(
            "M0.1 multi-canonical Work: book_id=%s count=%s work_ids=%s",
            r["book_id"], r["n"], r["ids"],
        )
    if rows:
        violations.append(f"M0.1: {len(rows)} book(s) with >1 canonical Work")

    # M0.2 · at most one PENDING (lazy) Work per book — two users' outage-forks
    # collide with the re-keyed uq_composition_work_pending(book_id).
    rows = await conn.fetch(
        """SELECT book_id, count(*) AS n, array_agg(id) AS ids FROM composition_work
           WHERE pending_project_backfill GROUP BY book_id HAVING count(*) > 1"""
    )
    for r in rows:
        logger.error(
            "M0.2 pending-Work fork: book_id=%s count=%s work_ids=%s",
            r["book_id"], r["n"], r["ids"],
        )
    if rows:
        violations.append(f"M0.2: {len(rows)} book(s) with >1 pending Work")

    # M0.3 · zero kind='beat' rows (BPS-4: verified dead, but `kind` was a free
    # string — F6 of 23).
    if await _table_exists(conn, "outline_node"):
        n_beat = await conn.fetchval("SELECT count(*) FROM outline_node WHERE kind = 'beat'")
        if n_beat:
            for r in await conn.fetch(
                "SELECT id, project_id, title FROM outline_node WHERE kind = 'beat' LIMIT 20"
            ):
                logger.error(
                    "M0.3 kind='beat' row: id=%s project_id=%s title=%r",
                    r["id"], r["project_id"], r["title"],
                )
            violations.append(f"M0.3: {n_beat} outline_node kind='beat' row(s)")

    # M0.4 · zero ORPHAN project rows — a project_id with no composition_work row
    # has an unrecoverable book_id (cross-DB; no join to knowledge at migration time).
    #
    # The Work is resolved by the C16 identity (project_id, or the surrogate `id` while
    # project_id is still NULL — a lazy Work created during a knowledge-service outage).
    # The anti-join sentinel MUST be `w.id`, never `w.project_id`: a successfully matched
    # PENDING Work has project_id NULL by definition, so testing that column would report
    # every row of every lazy Work as an unrecoverable orphan and refuse the boot.
    for t in _ORPHAN_TABLES:
        if not await _table_exists(conn, t):
            continue
        n = await conn.fetchval(
            f"""SELECT count(*) FROM {t} t
                LEFT JOIN composition_work w
                  ON (w.project_id = t.project_id
                      OR (w.project_id IS NULL AND w.id = t.project_id))
                WHERE w.id IS NULL"""
        )
        if n:
            sample = await conn.fetch(
                f"""SELECT DISTINCT t.project_id FROM {t} t
                    LEFT JOIN composition_work w
                  ON (w.project_id = t.project_id
                      OR (w.project_id IS NULL AND w.id = t.project_id))
                    WHERE w.id IS NULL LIMIT 20"""
            )
            logger.error(
                "M0.4 orphan rows in %s: count=%s sample project_ids=%s",
                t, n, [r["project_id"] for r in sample],
            )
            violations.append(f"M0.4: {t} has {n} orphan row(s)")

    # M0.5 · PM-15 settings inventory — INFORMATIONAL at runtime (the registry
    # cross-check lives in tests; source_language (OQ-7) and
    # reference_embed_model_ref/_source (OQ-9) are pre-decided keys, so the
    # inventory can never stall the migration).
    keys = await conn.fetch(
        "SELECT DISTINCT jsonb_object_keys(settings) AS key FROM composition_work ORDER BY key"
    )
    logger.info(
        "M0.5 (PM-15 inventory, informational): composition_work.settings keys = %s",
        [r["key"] for r in keys],
    )

    # M0.6 · zero cross-user duplicate style/voice rows per package scope — the
    # old PKs include user_id, so EDIT-grantees can already have written
    # caller-keyed rows that collide with M3.4's narrowed PKs (PM-5). Skipped
    # when user_id is already renamed (crash re-run: the check passed before).
    for table, scope_cols in (
        ("style_profile", "scope_type, scope_id"),
        ("voice_profile", "entity_id"),
    ):
        if not await _table_exists(conn, table) or not await _column_exists(conn, table, "user_id"):
            continue
        rows = await conn.fetch(
            f"""SELECT project_id, {scope_cols}, count(*) AS n, array_agg(user_id) AS users
                FROM {table} GROUP BY project_id, {scope_cols} HAVING count(*) > 1"""
        )
        for r in rows:
            logger.error("M0.6 cross-user duplicate in %s: %s", table, dict(r))
        if rows:
            violations.append(f"M0.6: {table} has {len(rows)} duplicated scope(s)")

    # M0.7 · zero cross-user duplicate (project_id, idempotency_key) pairs — M3.2
    # NARROWS idx_decompose_commit_idem from (user_id, project_id, key) to
    # (project_id, key) (PM-10). Two actors that replayed the same client key on one
    # project coexist legally TODAY and would collide on the narrowed unique. Without
    # this check the CREATE UNIQUE INDEX raises a bare UniqueViolation mid-cutover:
    # a crash-looping boot with no operator protocol. Symmetric to M0.6, which guards
    # the identical exposure on the style/voice PK narrowing. (Not in 25's enumerated
    # M0.1-M0.6 — the spec listed the style/voice narrowing but missed this one.)
    if await _table_exists(conn, "decompose_commit") and await _column_exists(
        conn, "decompose_commit", "user_id"
    ):
        rows = await conn.fetch(
            """SELECT project_id, idempotency_key, count(*) AS n, array_agg(user_id) AS users
               FROM decompose_commit GROUP BY project_id, idempotency_key HAVING count(*) > 1"""
        )
        for r in rows:
            logger.error(
                "M0.7 cross-user duplicate decompose_commit key: project_id=%s key=%r users=%s",
                r["project_id"], r["idempotency_key"], r["users"],
            )
        if rows:
            violations.append(f"M0.7: decompose_commit has {len(rows)} duplicated (project, key) pair(s)")

    if violations:
        raise RuntimeError(
            "package re-key (pkg_rekey_v1) M0 pre-flight FAILED — boot aborted before "
            "any DDL (PM-7; offending rows logged above). Resolve BY HAND per the "
            "operator protocol in docs/specs/2026-07-01-writing-studio/"
            "25_package_migration_master.md §M0, then re-boot. Violations: "
            + "; ".join(violations)
        )


# ── M2 — backfill (25 lines 226-243) + assertions + NOT NULL flips ───────────

async def _backfill_m2(conn: asyncpg.Connection) -> None:
    # Large tables: keyset batches of 500 over the UUIDv7 id (F8 pattern). The
    # cursor advances over the SELECTed ids regardless of update hits, so a row
    # that cannot resolve a Work (impossible past M0.4) can never loop forever —
    # the post-backfill assertion catches it instead.
    for t in _BATCH_TABLES:
        visited = 0
        last_id = None
        while True:
            if last_id is None:
                batch = await conn.fetch(
                    f"SELECT id FROM {t} WHERE book_id IS NULL ORDER BY id LIMIT $1",
                    _BATCH_SIZE,
                )
            else:
                batch = await conn.fetch(
                    f"""SELECT id FROM {t} WHERE book_id IS NULL AND id > $1
                        ORDER BY id LIMIT $2""",
                    last_id,
                    _BATCH_SIZE,
                )
            if not batch:
                break
            ids = [r["id"] for r in batch]
            await conn.execute(
                f"""UPDATE {t} t SET book_id = w.book_id
                    FROM composition_work w
                    WHERE (w.project_id = t.project_id
                           OR (w.project_id IS NULL AND w.id = t.project_id))
                      AND t.id = ANY($1::uuid[]) AND t.book_id IS NULL""",
                ids,
            )
            visited += len(ids)
            last_id = ids[-1]
        logger.info("M2 backfill %s: %d row(s) visited (keyset %d/batch)", t, visited, _BATCH_SIZE)

    # Small tables: one statement each (dozens-to-low-thousands of rows — PM-6).
    for t in _SMALL_PROJECT_TABLES:
        tag = await conn.execute(
            f"""UPDATE {t} t SET book_id = w.book_id FROM composition_work w
                WHERE (w.project_id = t.project_id OR (w.project_id IS NULL AND w.id = t.project_id))
                  AND t.book_id IS NULL"""
        )
        logger.info("M2 backfill %s: %s", t, tag)

    # FK-derived pair (belt: via work_id, not project_id):
    await conn.execute(
        """UPDATE divergence_spec t SET book_id = w.book_id FROM composition_work w
           WHERE w.id = t.work_id AND t.book_id IS NULL"""
    )
    await conn.execute(
        """UPDATE entity_override t SET book_id = w.book_id FROM composition_work w
           WHERE w.id = t.work_id AND t.book_id IS NULL"""
    )
    # generation_correction: via its job (the actor stamp stays the corrector's).
    # Runs AFTER generation_job's own backfill above.
    await conn.execute(
        """UPDATE generation_correction t SET book_id = j.book_id FROM generation_job j
           WHERE j.id = t.job_id AND t.book_id IS NULL"""
    )

    # Post-backfill assertions (same run, before M3): zero NULL book_id per table.
    failures: list[str] = []
    for t in _BOOK_ID_TABLES:
        n = await conn.fetchval(f"SELECT count(*) FROM {t} WHERE book_id IS NULL")
        if n:
            logger.error("M2 assertion FAILED: %s has %d NULL book_id row(s)", t, n)
            failures.append(f"{t}={n}")
    if failures:
        raise RuntimeError(
            "package re-key M2 left NULL book_id rows. Either an M0.4 orphan escaped "
            "(impossible unless M0 was bypassed), or a backfill predicate disagrees with "
            "M0.4's Work-resolution (both must resolve the Work by project_id OR, for a "
            "C16 lazy Work, the surrogate id). Rows: " + ", ".join(failures)
        )

    # NOT NULL flips (guarded DO-blocks — a fresh-created table is already NOT NULL).
    for t in _BOOK_ID_TABLES:
        await conn.execute(
            f"""
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM information_schema.columns
             WHERE table_name = '{t}' AND column_name = 'book_id'
               AND table_schema = current_schema()
               AND is_nullable = 'YES') THEN
    ALTER TABLE {t} ALTER COLUMN book_id SET NOT NULL;
  END IF;
END $$;"""
        )


# ── M3 — cutover DDL (25 lines 249-293) ──────────────────────────────────────

def _rename_sql(table: str, old: str) -> str:
    """One guarded DO-block per table (25 M3.3 verbatim shape). No-op when the
    table does not exist yet or the column is already renamed."""
    return f"""
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM information_schema.columns
             WHERE table_name = '{table}' AND column_name = '{old}'
               AND table_schema = current_schema()) THEN
    ALTER TABLE {table} RENAME COLUMN {old} TO created_by;
  END IF;
END $$;"""


async def _cutover_m3(conn: asyncpg.Connection) -> None:
    await conn.execute(_M3_INDEX_SQL)  # M3.1 + M3.2
    # M3.3 · actor renames (PM-5)
    for t in _USER_ID_RENAMES:
        await conn.execute(_rename_sql(t, "user_id"))
    for t in _OWNER_USER_ID_RENAMES:
        await conn.execute(_rename_sql(t, "owner_user_id"))
    await conn.execute(_M3_CUTOVER_TAIL_SQL)  # index final name + M3.4 PK swaps
    logger.info("M3 cutover applied (uniques, ledger re-scope, actor renames, PK swaps)")
