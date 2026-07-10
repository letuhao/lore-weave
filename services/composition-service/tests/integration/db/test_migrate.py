"""M1 — schema migration integration test (real Postgres).

Gated on TEST_COMPOSITION_DB_URL (a THROWAWAY test DB — the fixture drops
every composition table on teardown). Verifies:
  - migrate runs TWICE clean (idempotent) and the 6 built-in templates seed
    exactly once;
  - one row inserts into every table (constraints + in-DB FKs hold).
"""

from __future__ import annotations

import os
import uuid

import asyncpg
import pytest

from app.db.migrate import BUILTIN_TEMPLATES, run_migrations

_DSN = os.environ.get("TEST_COMPOSITION_DB_URL")

pytestmark = [
    pytest.mark.skipif(
        not _DSN, reason="set TEST_COMPOSITION_DB_URL to a throwaway DB to run",
    ),
    # Shared-Postgres tests serialize onto one xdist worker (CLAUDE.md).
    pytest.mark.xdist_group("pg"),
]

_TABLES = [
    "outbox_events", "generation_job", "canon_rule", "scene_link",
    "outline_node", "structure_template", "composition_work",
]


@pytest.fixture
async def pool():
    p = await asyncpg.create_pool(_DSN, min_size=1, max_size=4)
    try:
        # Clean slate so a prior failed run doesn't poison this one.
        async with p.acquire() as c:
            for t in _TABLES:
                await c.execute(f"DROP TABLE IF EXISTS {t} CASCADE")
        yield p
    finally:
        async with p.acquire() as c:
            for t in _TABLES:
                await c.execute(f"DROP TABLE IF EXISTS {t} CASCADE")
        await p.close()


async def test_migrate_idempotent_and_seeds_once(pool):
    await run_migrations(pool)
    await run_migrations(pool)  # second run must not error or double-seed
    async with pool.acquire() as c:
        n = await c.fetchval(
            "SELECT count(*) FROM structure_template WHERE owner_user_id IS NULL"
        )
    assert n == len(BUILTIN_TEMPLATES) == 6


async def test_inserts_into_every_table(pool):
    await run_migrations(pool)
    user, project, book = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    chapter = uuid.uuid4()

    async with pool.acquire() as c:
        # composition_work (1:1 with the project). created_by = the 25 M3 actor
        # stamp (was user_id pre-re-key); book_id is the tenancy scope key.
        await c.execute(
            "INSERT INTO composition_work (project_id, created_by, book_id) VALUES ($1,$2,$3)",
            project, user, book,
        )
        # a user-custom template
        tmpl = await c.fetchval(
            "INSERT INTO structure_template (owner_user_id, name, kind) VALUES ($1,'Mine','generic') RETURNING id",
            user,
        )
        assert tmpl is not None
        # outline: a chapter node + a scene node (scene requires chapter_id). Every
        # re-keyed table now carries created_by (actor stamp) + book_id NOT NULL.
        chap_node = await c.fetchval(
            "INSERT INTO outline_node (created_by, project_id, book_id, kind, rank, chapter_id) "
            "VALUES ($1,$2,$3,'chapter','a0',$4) RETURNING id",
            user, project, book, chapter,
        )
        scene_node = await c.fetchval(
            "INSERT INTO outline_node (created_by, project_id, book_id, parent_id, kind, rank, chapter_id, beat_role, story_order) "
            "VALUES ($1,$2,$3,$4,'scene','a0',$5,'hook',1) RETURNING id",
            user, project, book, chap_node, chapter,
        )
        scene2 = await c.fetchval(
            "INSERT INTO outline_node (created_by, project_id, book_id, parent_id, kind, rank, chapter_id) "
            "VALUES ($1,$2,$3,$4,'scene','a1',$5) RETURNING id",
            user, project, book, chap_node, chapter,
        )
        # scene_link between the two scenes
        await c.execute(
            "INSERT INTO scene_link (created_by, project_id, book_id, from_node_id, to_node_id) VALUES ($1,$2,$3,$4,$5)",
            user, project, book, scene_node, scene2,
        )
        # canon_rule
        await c.execute(
            "INSERT INTO canon_rule (created_by, project_id, book_id, text, scope) VALUES ($1,$2,$3,'No one knows the king is dead','reveal_gate')",
            user, project, book,
        )
        # generation_job (base_revision_id is the OI-2 guard column)
        await c.execute(
            "INSERT INTO generation_job (created_by, project_id, book_id, outline_node_id, operation, base_revision_id) "
            "VALUES ($1,$2,$3,$4,'draft_scene',$5)",
            user, project, book, scene_node, uuid.uuid4(),
        )
        # outbox_events
        await c.execute(
            "INSERT INTO outbox_events (aggregate_id, event_type) VALUES ($1,'composition.scene_committed')",
            scene_node,
        )

        counts = {t: await c.fetchval(f"SELECT count(*) FROM {t}") for t in _TABLES}

    assert counts["composition_work"] == 1
    assert counts["outline_node"] == 3
    assert counts["scene_link"] == 1
    assert counts["canon_rule"] == 1
    assert counts["generation_job"] == 1
    assert counts["outbox_events"] == 1
    assert counts["structure_template"] == 6 + 1  # 6 built-ins + 1 custom


async def test_scene_requires_chapter_id(pool):
    """The outline_chapter_required CHECK rejects a scene with no chapter_id."""
    await run_migrations(pool)
    user, project, book = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    async with pool.acquire() as c:
        with pytest.raises(asyncpg.CheckViolationError):
            await c.execute(
                "INSERT INTO outline_node (created_by, project_id, book_id, kind, rank) VALUES ($1,$2,$3,'scene','a0')",
                user, project, book,
            )
