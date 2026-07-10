"""R-NODE-P1 (data plane) — the cross-workstream integration guard.

The ONE test that exercises all 7 Wave-1 workstreams' code together against a real
seeded DB through the actual repo/engine paths (no HTTP, no LLM, no provider-registry):

  W7 seeds (migrate delegation) -> W1 create a user motif -> W3 retrieve ranks a SEED
  motif (DEGRADE path: the platform embed model is unset, so retrieve falls back to
  genre+tension per R4) -> W2 write a motif_application with beat_key in annotations
  -> W5 trace reads it back -> W2 anti-repetition aggregate.

The full HTTP + LLM-decompose + semantic-embed R-NODE-P1 runs at the Wave-2 stack
stand-up (it needs composition-service rebuilt + a platform embed model). This guard
locks the data-plane contracts that the parallel build had to assume across WSs.
"""

from __future__ import annotations

import os
import uuid

import asyncpg
import pytest

from app.db.migrate import run_migrations
from app.db.models import MotifCreateArgs
from app.db.repositories.motif_application import MotifApplicationRepo
from app.db.repositories.motif_repo import MotifRepo
from app.db.repositories.motif_retrieve import MotifRetriever
from app.routers.conformance import ConformanceTraceReader

_DSN = os.environ.get("TEST_COMPOSITION_DB_URL")

pytestmark = [
    pytest.mark.skipif(
        not _DSN, reason="set TEST_COMPOSITION_DB_URL to a throwaway DB to run",
    ),
    # Shared-Postgres tests serialize onto one xdist worker (CLAUDE.md).
    pytest.mark.xdist_group("pg"),
]

_TABLES = [
    "consumed_tokens", "motif_application", "motif_link", "import_source",
    "arc_template", "motif", "outline_node",
]


@pytest.fixture
async def pool():
    p = await asyncpg.create_pool(_DSN, min_size=1, max_size=4)

    async def _drop():
        async with p.acquire() as c:
            for t in _TABLES:
                await c.execute(f"DROP TABLE IF EXISTS {t} CASCADE")

    try:
        await _drop()
        await run_migrations(p)          # W7 seeds load via the migrate delegation
        yield p
    finally:
        await _drop()
        await p.close()


async def test_rnode_p1_dataplane_all_workstreams_compose(pool):
    # ── W7: the seed pack loaded; pick a genre that actually has active seeds ──────
    async with pool.acquire() as c:
        nsys = await c.fetchval("SELECT count(*) FROM motif WHERE owner_user_id IS NULL")
        genre = await c.fetchval(
            "SELECT g FROM motif, unnest(genre_tags) g "
            "WHERE owner_user_id IS NULL AND status='active' "
            "GROUP BY g ORDER BY count(*) DESC LIMIT 1"
        )
    assert nsys >= 40, f"expected the W7 seed pack (>=40 system motifs), got {nsys}"
    assert genre, "seeds carry no genre tags"

    user, project, book = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()

    # ── W1: create a USER-tier motif (owner stamped server-side, embedding NULL) ───
    repo = MotifRepo(pool)
    um = await repo.create(user, MotifCreateArgs(
        code="my.custom_hook", name="My Hook", kind="hook",
        genre_tags=[genre], tension_target=4, summary="a custom cliffhanger",
    ))
    assert um.owner_user_id == user and um.visibility == "private"

    # a chapter node in the project (the bind target; H-5 scope guard validates it).
    # 25 M3: created_by = actor stamp, book_id NOT NULL is the tenancy scope key.
    async with pool.acquire() as c:
        node = await c.fetchval(
            "INSERT INTO outline_node (created_by, project_id, book_id, kind, rank, chapter_id, beat_role, tension) "
            "VALUES ($1,$2,$3,'chapter','a0',$4,'hook',80) RETURNING id",
            user, project, book, uuid.uuid4(),
        )

    # ── W3: retrieve candidates for a hook beat — DEGRADE path (no embed model) ────
    retr = MotifRetriever(pool)
    cands = await retr.retrieve(
        user, book_id=book, project_id=project, genre_tags=[genre],
        language="en", beat_role="hook", tension=4, limit=6,
    )
    assert cands, "W3 retrieve returned no candidates"
    # the unset platform model => R4 degrade (genre+tension), never a 500.
    assert cands[0].match_reason.get("degraded") is True
    assert cands[0].match_reason.get("cosine") == 0.0
    assert set(cands[0].match_reason) >= {"tension", "genre", "precond", "cosine"}
    seed_cand = next((c for c in cands if c.motif.owner_user_id is None), None)
    assert seed_cand is not None, "no SEED (system) motif among the candidates"
    chosen = seed_cand.motif

    # ── W2: write the binding ledger row (beat_key folded into annotations) ────────
    # 25 M3/DA-11: scope keys (project, book) are positional; created_by is the
    # keyword-only actor stamp (stored, never filtered on).
    apps = MotifApplicationRepo(pool)
    written = await apps.insert_many(project, book, rows=[{
        "motif_id": str(chosen.id), "motif_version": chosen.version,
        "outline_node_id": str(node), "role_bindings": {"hero": "ent-1"},
        "annotations": {"beat_key": "hook"},
    }], created_by=user)
    assert len(written) == 1 and written[0].motif_id == chosen.id

    # ── W5: the trace reads it back — the W2->W5 beat_key seam, verified live ──────
    reader = ConformanceTraceReader(pool)
    trace = await reader.apps_by_nodes(project, [node])
    app = trace.get(node)
    assert app is not None
    assert app.motif_id == chosen.id
    assert app.annotations.get("beat_key") == "hook"  # the seam the parallel build assumed

    # ── W2: anti-repetition aggregate counts the binding ──────────────────────────
    # 25 M3: the per-book aggregate is scoped by book_id alone (no per-user leg).
    counts = await apps.count_by_motif_for_book(book)
    assert counts.get(str(chosen.id)) == 1
