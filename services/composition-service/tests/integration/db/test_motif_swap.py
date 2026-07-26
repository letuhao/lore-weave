"""W2 — motif swap/undo engine integration tests (real Postgres, throwaway DB).

Gated on TEST_COMPOSITION_DB_URL. These exercise the §7.4 swap guards that need the
real archive/restore + generation_job + narrative_thread + motif_application tables:

  - apply_motif_swap archives the chapter's SCENES while keeping the CHAPTER node,
    and does NOT delete the scenes' generation_job rows (prose preserved).
  - the new motif's scenes + motif_application rows are written.
  - undo_motif_swap is a lossless inverse (prior scenes + prose restored, new scenes
    archived).
  - IDOR: a chapter node from another project → MotifSwapError.
  - an open narrative_thread anchored at an archived scene is SURFACED, not closed.
  - count_by_motif_for_book aggregates the per-book anti-repetition count.
"""

from __future__ import annotations

import os
import uuid

import asyncpg
import pytest

from app.db.migrate import run_migrations
from app.db.models import Motif
from app.db.repositories.motif_application import MotifApplicationRepo
from app.db.repositories.outline import OutlineRepo
from app.engine.motif_select import (
    MotifBinding,
    MotifSwapError,
    SelectedMotif,
    apply_motif_swap,
    undo_motif_swap,
)

_DSN = os.environ.get("TEST_COMPOSITION_DB_URL")
pytestmark = [
    pytest.mark.skipif(
        not _DSN, reason="set TEST_COMPOSITION_DB_URL to a throwaway DB to run",
    ),
    # Shared-Postgres tests serialize onto one xdist worker (CLAUDE.md).
    pytest.mark.xdist_group("pg"),
]

_TABLES = [
    "motif_application", "motif_link", "import_source", "arc_template", "motif",
    "outbox_events", "generation_correction", "generation_job", "narrative_thread",
    "canon_rule", "scene_link", "outline_node", "structure_template",
    "entity_override", "divergence_spec", "composition_work", "consumed_tokens",
]


@pytest.fixture
async def pool():
    p = await asyncpg.create_pool(_DSN, min_size=1, max_size=4)
    try:
        async with p.acquire() as c:
            for t in _TABLES:
                await c.execute(f"DROP TABLE IF EXISTS {t} CASCADE")
        await run_migrations(p)
        yield p
    finally:
        async with p.acquire() as c:
            for t in _TABLES:
                await c.execute(f"DROP TABLE IF EXISTS {t} CASCADE")
        await p.close()


def _motif(*, code="m.swap", name="Swap", tension_target=4) -> Motif:
    return Motif.model_validate({
        "id": uuid.uuid4(), "owner_user_id": None, "code": code, "language": "en",
        "visibility": "unlisted", "kind": "scheme", "name": name,
        "summary": "s", "genre_tags": ["x"],
        "roles": [{"key": "hero", "actant": "subject", "label": "Lin", "constraints": []}],
        "beats": [
            {"key": "b1", "label": "Beat 1", "intent": "{hero} acts", "tension_target": 3, "order": 1},
            {"key": "b2", "label": "Beat 2", "intent": "{hero} wins", "tension_target": 5, "order": 2},
        ],
        "effects": [{"text": "e"}], "annotations": {},
        "tension_target": tension_target, "status": "active", "version": 2,
    })


async def _insert_motif(pool, m: Motif) -> None:
    """Insert the motif as a system row so motif_application's motif_id FK resolves."""
    async with pool.acquire() as c:
        await c.execute(
            "INSERT INTO motif (id, owner_user_id, code, language, visibility, kind, "
            "name, summary, status, version) "
            "VALUES ($1, NULL, $2, 'en', 'unlisted', 'scheme', $3, 's', 'active', $4)",
            m.id, m.code, m.name, m.version,
        )


def _sel(m: Motif) -> SelectedMotif:
    return SelectedMotif(motif=m, score=0.9, match_reason={})


def _binding() -> MotifBinding:
    return MotifBinding(role_bindings={"hero": str(uuid.uuid4())},
                        unresolved_roles=[], annotations={}, warning=None)


async def _seed_work(c, user, project, book) -> None:
    """Seed the project's composition_work row so create_node can derive book_id
    in-SQL (25 re-key: every outline_node INSERT does INSERT … SELECT w.book_id
    FROM composition_work WHERE project_id = $n). `created_by` is a plain actor
    stamp (never filtered)."""
    await c.execute(
        "INSERT INTO composition_work (created_by, project_id, book_id, status) "
        "VALUES ($1,$2,$3,'active')",
        user, project, book,
    )


async def _chapter_with_scenes(pool, user, project, book, chapter_id, *, n_scenes=2):
    """Create an arc→chapter→scenes tree; return (chapter_node, scene_nodes)."""
    outline = OutlineRepo(pool)
    async with pool.acquire() as c:
        await _seed_work(c, user, project, book)
        arc = await outline.create_node(project, created_by=user, kind="arc", title="Arc",
                                        status="outline", conn=c)
        ch = await outline.create_node(project, created_by=user, kind="chapter", parent_id=arc.id,
                                       chapter_id=chapter_id, title="Ch",
                                       beat_role="climax", status="outline", conn=c)
        scenes = []
        for i in range(n_scenes):
            sn = await outline.create_node(project, created_by=user, kind="scene", parent_id=ch.id,
                                           chapter_id=chapter_id, beat_role="climax",
                                           title=f"S{i}", tension=50, status="outline", conn=c)
            scenes.append(sn)
    return ch, scenes


async def _is_archived(pool, node_id) -> bool:
    async with pool.acquire() as c:
        return await c.fetchval("SELECT is_archived FROM outline_node WHERE id = $1", node_id)


async def test_apply_swap_archives_scenes_keeps_chapter_preserves_prose(pool):
    user, project, book = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    chapter_id = uuid.uuid4()
    ch, scenes = await _chapter_with_scenes(pool, user, project, book, chapter_id)
    # attach a generation_job (prose) to scene 0
    async with pool.acquire() as c:
        job_id = await c.fetchval(
            "INSERT INTO generation_job (created_by, project_id, book_id, outline_node_id, operation, "
            "status, result) VALUES ($1,$2,$3,$4,'generate','completed','{\"text\":\"prose\"}'::jsonb) "
            "RETURNING id",
            user, project, book, scenes[0].id,
        )

    outline = OutlineRepo(pool)
    apps = MotifApplicationRepo(pool)
    new_m = _motif(code="new")
    await _insert_motif(pool, new_m)
    async with pool.acquire() as c:
        async with c.transaction():
            res = await apply_motif_swap(
                outline, apps, project, book, ch.id, created_by=user,
                new_motif=_sel(new_m), binding=_binding(), cast_names={},
                k_ceiling=3, high_threshold=70, min_scenes=1, max_scenes=6, conn=c,
            )

    # prior scenes archived; chapter node NOT archived
    for s in scenes:
        assert await _is_archived(pool, s.id) is True
    assert await _is_archived(pool, ch.id) is False
    # the generation_job row survives + still references the (archived) scene
    async with pool.acquire() as c:
        node_ref = await c.fetchval("SELECT outline_node_id FROM generation_job WHERE id = $1", job_id)
    assert node_ref == scenes[0].id
    # new scenes + applications written
    assert len(res.new_scene_ids) == 2
    async with pool.acquire() as c:
        n_apps = await c.fetchval(
            "SELECT count(*) FROM motif_application WHERE outline_node_id = ANY($1::uuid[])",
            [uuid.UUID(s) for s in res.new_scene_ids],
        )
    assert n_apps == 2


async def test_undo_swap_is_lossless_inverse(pool):
    user, project, book = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    chapter_id = uuid.uuid4()
    ch, scenes = await _chapter_with_scenes(pool, user, project, book, chapter_id)
    outline, apps = OutlineRepo(pool), MotifApplicationRepo(pool)
    new_m = _motif(code="new")
    await _insert_motif(pool, new_m)
    async with pool.acquire() as c:
        async with c.transaction():
            res = await apply_motif_swap(
                outline, apps, project, book, ch.id, created_by=user,
                new_motif=_sel(new_m), binding=_binding(), cast_names={},
                k_ceiling=3, high_threshold=70, min_scenes=1, max_scenes=6, conn=c,
            )
        async with c.transaction():
            await undo_motif_swap(outline, apps, project, res.undo_token, conn=c)

    # prior scenes restored (active again); new scenes archived
    for s in scenes:
        assert await _is_archived(pool, s.id) is False
    for ns in res.new_scene_ids:
        assert await _is_archived(pool, uuid.UUID(ns)) is True


async def test_clear_motif_archives_scenes_no_new(pool):
    user, project, book = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    chapter_id = uuid.uuid4()
    ch, scenes = await _chapter_with_scenes(pool, user, project, book, chapter_id)
    outline, apps = OutlineRepo(pool), MotifApplicationRepo(pool)
    async with pool.acquire() as c:
        async with c.transaction():
            res = await apply_motif_swap(
                outline, apps, project, book, ch.id, created_by=user,
                new_motif=None, binding=None, cast_names={},
                k_ceiling=3, high_threshold=70, min_scenes=1, max_scenes=6, conn=c,
            )
    assert res.new_scene_ids == []
    assert res.new_motif_id is None
    for s in scenes:
        assert await _is_archived(pool, s.id) is True


async def test_swap_idor_other_project_rejected(pool):
    user, project, book = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    other_project = uuid.uuid4()
    chapter_id = uuid.uuid4()
    ch, _ = await _chapter_with_scenes(pool, user, project, book, chapter_id)
    outline, apps = OutlineRepo(pool), MotifApplicationRepo(pool)
    async with pool.acquire() as c:
        async with c.transaction():
            with pytest.raises(MotifSwapError):
                await apply_motif_swap(
                    outline, apps, other_project, book, ch.id, created_by=user,  # wrong project
                    new_motif=_sel(_motif()), binding=_binding(), cast_names={},
                    k_ceiling=3, high_threshold=70, min_scenes=1, max_scenes=6, conn=c,
                )


async def test_orphaned_thread_surfaced_not_closed(pool):
    user, project, book = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    chapter_id = uuid.uuid4()
    ch, scenes = await _chapter_with_scenes(pool, user, project, book, chapter_id)
    # open a promise anchored at scene 0
    async with pool.acquire() as c:
        thread_id = await c.fetchval(
            "INSERT INTO narrative_thread (created_by, project_id, book_id, kind, status, opened_at_node, summary) "
            "VALUES ($1,$2,$3,'promise','open',$4,'a promise') RETURNING id",
            user, project, book, scenes[0].id,
        )
    outline, apps = OutlineRepo(pool), MotifApplicationRepo(pool)
    m = _motif()
    await _insert_motif(pool, m)
    async with pool.acquire() as c:
        async with c.transaction():
            res = await apply_motif_swap(
                outline, apps, project, book, ch.id, created_by=user,
                new_motif=_sel(m), binding=_binding(), cast_names={},
                k_ceiling=3, high_threshold=70, min_scenes=1, max_scenes=6, conn=c,
            )
    assert str(thread_id) in res.orphaned_thread_ids
    # thread row UNTOUCHED (still open, not archived)
    async with pool.acquire() as c:
        row = await c.fetchrow("SELECT status, is_archived FROM narrative_thread WHERE id = $1", thread_id)
    assert row["status"] == "open"
    assert row["is_archived"] is False


async def test_count_by_motif_for_book_aggregates(pool):
    user, project, book = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    chapter_id = uuid.uuid4()
    ch, _ = await _chapter_with_scenes(pool, user, project, book, chapter_id)
    outline, apps = OutlineRepo(pool), MotifApplicationRepo(pool)
    m = _motif()
    await _insert_motif(pool, m)
    async with pool.acquire() as c:
        async with c.transaction():
            await apply_motif_swap(
                outline, apps, project, book, ch.id, created_by=user,
                new_motif=_sel(m), binding=_binding(), cast_names={},
                k_ceiling=3, high_threshold=70, min_scenes=1, max_scenes=6, conn=c,
            )
    counts = await apps.count_by_motif_for_book(book)
    assert counts.get(str(m.id)) == 2  # 2 beats → 2 application rows
