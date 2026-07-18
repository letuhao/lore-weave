"""F0 — narrative motif library schema migration integration test (real Postgres).

Gated on TEST_COMPOSITION_DB_URL (a THROWAWAY test DB — the fixture drops every
motif table on setup AND teardown). These are the audit risk-guards written
RED-first (F0 §4/§5): the DB IS the tenancy boundary, so each guard is a DB-level
assertion, not an app check.

Covered:
  - 4.1  migration runs TWICE clean (idempotent); the 5 motif tables + consumed_tokens
         exist after the second run.
  - 4.2  the 2 tenancy partials + the motif_user_owned CHECK (B-2: a both-NULL
         private orphan is rejected at the DB; an ownerless non-private row is OK).
  - 4.3  get_visible IDOR (system | public | owner returned; a foreign-private NOT).
  - 4.4  motif_link cycle + same-tier guard (H-2).
  - 4.5  motif_application book-scope + outline_node∈project guard (H-5).
  - 4.6  language is part of the dedup key (N-1: same code en+vi = 2 rows).
  - 4.7  one platform embedding model (single embedding_model column).
  - 4.8  B-3 publish-strip trigger (examples stripped + opaque lineage on publish).
"""

from __future__ import annotations

import os
import uuid

import asyncpg
import pytest

from app.db.migrate import run_migrations

_DSN = os.environ.get("TEST_COMPOSITION_DB_URL")

pytestmark = [
    pytest.mark.skipif(
        not _DSN, reason="set TEST_COMPOSITION_DB_URL to a throwaway DB to run",
    ),
    # Shared-Postgres tests serialize onto one xdist worker (CLAUDE.md).
    pytest.mark.xdist_group("pg"),
]

# Children first (FK + dependency order) so the drop is clean.
_MOTIF_TABLES = [
    "consumed_tokens", "motif_application", "motif_link",
    "import_source", "arc_template", "motif",
]


async def _drop_motif_tables(p: asyncpg.Pool) -> None:
    async with p.acquire() as c:
        for t in _MOTIF_TABLES:
            await c.execute(f"DROP TABLE IF EXISTS {t} CASCADE")


@pytest.fixture
async def pool():
    p = await asyncpg.create_pool(_DSN, min_size=1, max_size=4)
    try:
        await _drop_motif_tables(p)
        yield p
    finally:
        await _drop_motif_tables(p)
        await p.close()


async def _seed_motif(
    c: asyncpg.Connection,
    *,
    owner=None,
    code="m",
    language="en",
    visibility="private",
    source="authored",
    name="M",
    examples=None,
    source_ref=None,
):
    """Direct INSERT (the seed/migrate path — bypasses MotifRepo.create which stamps
    owner). Returns the new id."""
    import json

    return await c.fetchval(
        """
        INSERT INTO motif (owner_user_id, code, language, visibility, source, name,
                           examples, source_ref)
        VALUES ($1,$2,$3,$4,$5,$6,$7::jsonb,$8)
        RETURNING id
        """,
        owner, code, language, visibility, source, name,
        json.dumps(examples or []), source_ref,
    )


async def test_motif_migrate_idempotent(pool):
    """4.1 — run_migrations twice clean; the 5 motif tables + consumed_tokens exist."""
    await run_migrations(pool)
    await run_migrations(pool)  # second run must not error or double-create
    async with pool.acquire() as c:
        for t in _MOTIF_TABLES:
            exists = await c.fetchval("SELECT to_regclass($1)", t)
            assert exists is not None, f"table {t} missing after migrate"


async def test_motif_user_owned_check_and_partials(pool):
    """4.2 + 4.6 — the motif_user_owned CHECK (B-2) and the 2 tenancy partials (N-1)."""
    await run_migrations(pool)
    u1, u2 = uuid.uuid4(), uuid.uuid4()
    async with pool.acquire() as c:
        # B-2: a both-NULL private orphan is rejected at the DB.
        with pytest.raises(asyncpg.CheckViolationError):
            await _seed_motif(c, owner=None, visibility="private", code="sys_priv")
        # an ownerless NON-private (system/published) row IS allowed.
        await _seed_motif(c, owner=None, visibility="unlisted", code="sys_ok")

        # uq_motif_user: same (owner, code, language) twice → unique violation.
        await _seed_motif(c, owner=u1, code="dup", language="en")
        with pytest.raises(asyncpg.UniqueViolationError):
            await _seed_motif(c, owner=u1, code="dup", language="en")
        # N-1: same code, DIFFERENT language → both insert (language in the key).
        await _seed_motif(c, owner=u1, code="dup", language="vi")
        # same code, DIFFERENT owner → both insert (per-user tier).
        await _seed_motif(c, owner=u2, code="dup", language="en")

        # uq_motif_system: two system rows same (code, language) → unique violation.
        await _seed_motif(c, owner=None, code="syscode", visibility="public")
        with pytest.raises(asyncpg.UniqueViolationError):
            await _seed_motif(c, owner=None, code="syscode", visibility="public")

        n = await c.fetchval("SELECT count(*) FROM motif WHERE code = 'dup'")
        assert n == 3  # (u1,en) (u1,vi) (u2,en)


async def test_get_visible_idor_predicate(pool):
    """4.3 — the read predicate via the repo (system | public | owner; foreign-private
    is None). This is the master-plan F0 eval-gate."""
    from app.db.repositories.motif_repo import MotifRepo

    await run_migrations(pool)
    u1, u2 = uuid.uuid4(), uuid.uuid4()
    async with pool.acquire() as c:
        sys_id = await _seed_motif(c, owner=None, code="s", visibility="unlisted")
        pub_id = await _seed_motif(c, owner=u2, code="p", visibility="public")
        own_id = await _seed_motif(c, owner=u1, code="o", visibility="private")
        foreign_id = await _seed_motif(c, owner=u2, code="f", visibility="private")

    repo = MotifRepo(pool)
    assert (await repo.get_visible(u1, sys_id)) is not None
    assert (await repo.get_visible(u1, pub_id)) is not None
    assert (await repo.get_visible(u1, own_id)) is not None
    # the IDOR assertion: U2's private motif is invisible to U1.
    assert (await repo.get_visible(u1, foreign_id)) is None

    listed = {m.id for m in await repo.list_for_caller(u1)}
    assert sys_id in listed and pub_id in listed and own_id in listed
    assert foreign_id not in listed


async def test_motif_link_cycle_and_same_tier(pool):
    """4.4 — the cycle guard + same-tier guard (H-2)."""
    await run_migrations(pool)
    u1 = uuid.uuid4()
    async with pool.acquire() as c:
        a = await _seed_motif(c, owner=u1, code="a")
        b = await _seed_motif(c, owner=u1, code="b")
        cc = await _seed_motif(c, owner=u1, code="c")
        sys_m = await _seed_motif(c, owner=None, code="sys", visibility="unlisted")

        async def link(frm, to, kind="precedes"):
            await c.execute(
                "INSERT INTO motif_link (from_motif_id, to_motif_id, kind) VALUES ($1,$2,$3)",
                frm, to, kind,
            )

        await link(a, b)
        await link(b, cc)
        # closing the cycle C precedes A is rejected.
        with pytest.raises(asyncpg.CheckViolationError):
            await link(cc, a)
        # cross-tier: a user motif → system motif is rejected.
        with pytest.raises(asyncpg.CheckViolationError):
            await link(a, sys_m, kind="composed_of")


async def test_motif_application_scope_and_book_required(pool):
    """4.5 — the outline_node∈project guard (H-5) + book_id NOT NULL + SET NULL."""
    await run_migrations(pool)
    u1, p1, p2, book = uuid.uuid4(), uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    async with pool.acquire() as c:
        motif_id = await _seed_motif(c, owner=u1, code="ap")
        # a chapter node in project p1. outline_node is 25-re-keyed: user_id →
        # created_by (a plain actor stamp) and book_id is NOT NULL, so a direct
        # INSERT (bypassing the repo's INSERT … SELECT derive) must supply it.
        node = await c.fetchval(
            "INSERT INTO outline_node (created_by, project_id, book_id, kind, rank, chapter_id) "
            "VALUES ($1,$2,$3,'chapter','a0',$4) RETURNING id",
            u1, p1, book, uuid.uuid4(),
        )

        # cross-project: node∈p1 but application says project p2 → rejected (H-5).
        with pytest.raises(asyncpg.CheckViolationError):
            await c.execute(
                "INSERT INTO motif_application (created_by, project_id, book_id, motif_id, outline_node_id) "
                "VALUES ($1,$2,$3,$4,$5)",
                u1, p2, book, motif_id, node,
            )
        # matching project → OK.
        app_id = await c.fetchval(
            "INSERT INTO motif_application (created_by, project_id, book_id, motif_id, outline_node_id) "
            "VALUES ($1,$2,$3,$4,$5) RETURNING id",
            u1, p1, book, motif_id, node,
        )
        # book_id NOT NULL.
        with pytest.raises(asyncpg.NotNullViolationError):
            await c.execute(
                "INSERT INTO motif_application (created_by, project_id, book_id, motif_id) "
                "VALUES ($1,$2,NULL,$3)",
                u1, p1, motif_id,
            )
        # FK ON DELETE SET NULL: deleting the motif keeps the application row.
        await c.execute("DELETE FROM motif WHERE id = $1", motif_id)
        surviving = await c.fetchval(
            "SELECT motif_id FROM motif_application WHERE id = $1", app_id
        )
        assert surviving is None


async def _seed_arc(
    c: asyncpg.Connection, *, owner=None, code="a", language="en", visibility="private",
    source="authored", imported_derived=False, source_ref=None, name="A",
):
    return await c.fetchval(
        """
        INSERT INTO arc_template (owner_user_id, code, language, visibility, name,
                                  source, imported_derived, source_ref)
        VALUES ($1,$2,$3,$4,$5,$6,$7,$8) RETURNING id
        """,
        owner, code, language, visibility, name, source, imported_derived, source_ref,
    )


async def test_arc_publish_strip_trigger(pool):
    """D-W9-ARC-PUBLISH-STRIP — publishing an imported (or adopted-from-imported)
    arc_template opaque-izes a back-readable source_ref (the motif B-3 parity; arc has no
    examples column, its free-text is abstracted by the deconstruct scrub). An authored,
    non-derived arc keeps its source_ref."""
    await run_migrations(pool)
    u1 = uuid.uuid4()
    foreign = f"import:{uuid.uuid4()}"
    async with pool.acquire() as c:
        # imported arc → opaque-ized on publish.
        imp = await _seed_arc(c, owner=u1, code="aimp", source="imported",
                              visibility="private", source_ref=foreign)
        await c.execute("UPDATE arc_template SET visibility='public' WHERE id=$1", imp)
        ref = await c.fetchval("SELECT source_ref FROM arc_template WHERE id=$1", imp)
        assert ref.startswith("lineage:") and foreign not in ref

        # adopted-from-imported (source='authored' but imported_derived=True) ALSO strips.
        der = await _seed_arc(c, owner=u1, code="ader", source="authored",
                              imported_derived=True, visibility="private", source_ref=foreign)
        await c.execute("UPDATE arc_template SET visibility='public' WHERE id=$1", der)
        ref2 = await c.fetchval("SELECT source_ref FROM arc_template WHERE id=$1", der)
        assert ref2.startswith("lineage:") and foreign not in ref2

        # an authored, non-derived arc KEEPS its source_ref on publish (strip is import-only).
        auth = await _seed_arc(c, owner=u1, code="aauth", source="authored",
                               visibility="private", source_ref=foreign)
        await c.execute("UPDATE arc_template SET visibility='public' WHERE id=$1", auth)
        ref3 = await c.fetchval("SELECT source_ref FROM arc_template WHERE id=$1", auth)
        assert ref3 == foreign


async def test_publish_strip_trigger(pool):
    """4.8 — B-3: publishing an imported-derived motif strips examples + opaque-izes
    source_ref; an authored motif keeps its examples."""
    await run_migrations(pool)
    u1 = uuid.uuid4()
    foreign = f"import:{uuid.uuid4()}"
    async with pool.acquire() as c:
        imp = await _seed_motif(
            c, owner=u1, code="imp", source="imported", visibility="private",
            examples=[{"text": "a stolen passage"}], source_ref=foreign,
        )
        await c.execute("UPDATE motif SET visibility = 'public' WHERE id = $1", imp)
        row = await c.fetchrow(
            "SELECT examples, source_ref FROM motif WHERE id = $1", imp
        )
        import json

        ex = row["examples"]
        ex = json.loads(ex) if isinstance(ex, str) else ex
        assert ex == []  # source prose stripped
        assert row["source_ref"].startswith("lineage:")  # opaque (no back-readable id)
        assert foreign not in row["source_ref"]

        # an authored motif keeps its examples on publish (the strip is import-only).
        auth = await _seed_motif(
            c, owner=u1, code="auth", source="authored", visibility="private",
            examples=[{"text": "my own example"}],
        )
        await c.execute("UPDATE motif SET visibility = 'public' WHERE id = $1", auth)
        ex2 = await c.fetchval("SELECT examples FROM motif WHERE id = $1", auth)
        ex2 = json.loads(ex2) if isinstance(ex2, str) else ex2
        assert ex2 == [{"text": "my own example"}]
