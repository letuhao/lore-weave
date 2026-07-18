"""W7 — system-tier motif seed-pack integration tests (real Postgres).

Gated on TEST_COMPOSITION_DB_URL (a THROWAWAY DB — the fixture drops every motif
table on setup AND teardown, mirroring test_motif_migrate.py). These prove the seed
is IDEMPOTENT, SYSTEM-TIER, NULL-EMBEDDING (the W3 back-fill seam), and that the
seeded links respect the same-tier rule — on the REAL seed data through the REAL
run_migrations delegation.

Map to W7 §5: tests #12-#14 (+ the run_migrations delegation proof).
"""

from __future__ import annotations

import json
import os

import asyncpg
import pytest

from app.db.migrate import run_migrations
from app.db.seed_motifs import load_link_edges, load_motif_rows, seed_motif_packs

_DSN = os.environ.get("TEST_COMPOSITION_DB_URL")

pytestmark = [
    pytest.mark.skipif(
        not _DSN, reason="set TEST_COMPOSITION_DB_URL to a throwaway DB to run",
    ),
    # MANDATORY (CLAUDE.md test-parallelization): this file DROPs/re-migrates tables on the
    # shared dev PG. Without the group, xdist schedules it on a DIFFERENT worker than the
    # other real-DB files and they drop each other's tables mid-run — the counts then lie.
    pytest.mark.xdist_group("pg"),
]

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


def _expected_counts():
    rows = load_motif_rows()
    edges = load_link_edges(rows)
    return len(rows), len(edges)


# ── test #12 — idempotent double-seed + system-tier count, via run_migrations.
async def test_seed_idempotent_and_system_tier(pool):
    n_rows, n_edges = _expected_counts()
    # run_migrations fires the F0 delegation → seed_motif_packs (the chokepoint).
    await run_migrations(pool)
    async with pool.acquire() as c:
        sys_after_1 = await c.fetchval("SELECT count(*) FROM motif WHERE owner_user_id IS NULL")
        links_after_1 = await c.fetchval("SELECT count(*) FROM motif_link")
    assert sys_after_1 == n_rows, f"expected {n_rows} system motifs, got {sys_after_1}"
    assert links_after_1 == n_edges, f"expected {n_edges} link edges, got {links_after_1}"

    # second run must NOT double-insert (deterministic ids + ON CONFLICT DO NOTHING).
    await run_migrations(pool)
    async with pool.acquire() as c:
        sys_after_2 = await c.fetchval("SELECT count(*) FROM motif WHERE owner_user_id IS NULL")
        links_after_2 = await c.fetchval("SELECT count(*) FROM motif_link")
        # EVERY system motif row is non-private + authored (the tier + copyright invariants).
        bad_vis = await c.fetchval(
            "SELECT count(*) FROM motif WHERE owner_user_id IS NULL AND visibility = 'private'"
        )
        non_authored = await c.fetchval(
            "SELECT count(*) FROM motif WHERE owner_user_id IS NULL AND source <> 'authored'"
        )
    assert sys_after_2 == n_rows, "double-seed: system motif count grew on re-run"
    assert links_after_2 == n_edges, "double-seed: link count grew on re-run"
    assert bad_vis == 0, "a system seed row is 'private' (violates the both-NULL CHECK intent)"
    assert non_authored == 0, "a system seed row is not 'authored'"


# ── test #13 — seed rows ship NULL embedding (the W3 back-fill contract).
async def test_seed_rows_have_null_embedding(pool):
    await run_migrations(pool)
    async with pool.acquire() as c:
        embedded = await c.fetchval(
            "SELECT count(*) FROM motif WHERE owner_user_id IS NULL AND embedding IS NOT NULL"
        )
        non_empty_model = await c.fetchval(
            "SELECT count(*) FROM motif WHERE owner_user_id IS NULL AND embedding_model <> ''"
        )
    assert embedded == 0, "W7 must NOT embed at seed time (W3 back-fills)"
    assert non_empty_model == 0, "embedding_model must stay '' at seed (W3 sets it)"


# ── test #14 — every seeded link endpoint is a SYSTEM motif (same-tier, audit H-2).
async def test_seeded_links_respect_same_tier(pool):
    await run_migrations(pool)
    async with pool.acquire() as c:
        # any link whose from OR to is a user motif would be a cross-tier leak.
        cross = await c.fetchval(
            """
            SELECT count(*) FROM motif_link ml
            JOIN motif f ON f.id = ml.from_motif_id
            JOIN motif t ON t.id = ml.to_motif_id
            WHERE f.owner_user_id IS NOT NULL OR t.owner_user_id IS NOT NULL
            """
        )
    assert cross == 0, "a seeded link touches a non-system motif"


# ── bonus — the scheme info_asymmetry lands on the dedicated column AND annotations.
async def test_scheme_info_asymmetry_persisted(pool):
    await run_migrations(pool)
    async with pool.acquire() as c:
        row = await c.fetchrow(
            "SELECT info_asymmetry, annotations FROM motif "
            "WHERE owner_user_id IS NULL AND code = 'intrigue.planted_evidence_scheme'"
        )
    assert row is not None, "the planted-evidence scheme seed is missing"
    ia = row["info_asymmetry"]
    ia = json.loads(ia) if isinstance(ia, str) else ia
    assert ia and ia.get("knows") and ia.get("deceived") and ia.get("gap")
    ann = row["annotations"]
    ann = json.loads(ann) if isinstance(ann, str) else ann
    assert ann.get("info_asymmetry"), "annotations.info_asymmetry not persisted (D1)"


# ── bonus — the dev reseed=True path UPDATEs an existing system authored row in place.
async def test_reseed_updates_authored_system_row(pool):
    await run_migrations(pool)  # initial seed
    async with pool.acquire() as c:
        # mutate a system row's summary, then reseed → it must be restored to the pack.
        await c.execute(
            "UPDATE motif SET summary = 'TAMPERED' WHERE owner_user_id IS NULL "
            "AND code = 'cultivation.face_slap'"
        )
        await seed_motif_packs(c, reseed=True)
        restored = await c.fetchval(
            "SELECT summary FROM motif WHERE owner_user_id IS NULL AND code = 'cultivation.face_slap'"
        )
    assert restored != "TAMPERED", "reseed=True did not restore the pack summary"
    # default reseed=False is a no-op on an existing row (proven by test #12's stable count).
