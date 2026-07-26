"""23 BA12 — the WIRED arc-injection proof (the gap the unit D2 test left open).

test_pack_arc.py proves the arc LENS works by injecting a FakeStructureRepo and hand-setting
`node['structure_node_id']`. But no production caller did either: the pack() call sites omitted
`structure_repo=`, and OutlineNode/OutlineRepo never carried structure_node_id — so in production
`arc_gated` always took the dormant branch and the arc never reached the prompt. The write-only-arc
bug the whole spec exists to kill was alive in prod, and D2 could not see it because it bypassed the
real chokepoint. (Found by /review-impl, 2026-07-11.)

This test closes that: it drives pack() with a REAL StructureRepo + REAL OutlineRepo against a real
DB, and a SCENE node that carries ONLY chapter_id (no structure_node_id — a scene may not carry one;
the outline_structure_kind CHECK forbids it). So it exercises the exact production path:
    scene node → chapter_id → OutlineRepo.chapter_structure_node_id → StructureRepo resolution → <arc>.
If a future edit drops `structure_repo=` at a call site, or removes the scene→chapter→arc resolution,
this reds. The external clients are stubbed (the arc lens is composition-local; grounding degrades).

Gated on TEST_COMPOSITION_DB_URL (throwaway DB — drops tables).
"""

from __future__ import annotations

import os
import uuid

import asyncpg
import pytest

from app.db.migrate import run_migrations
from app.db.repositories.outline import OutlineRepo
from app.db.repositories.structure import StructureRepo
from app.grant_client import GrantLevel
from app.packer.pack import PackRequest, pack

_DSN = os.environ.get("TEST_COMPOSITION_DB_URL")

pytestmark = [
    pytest.mark.skipif(not _DSN, reason="set TEST_COMPOSITION_DB_URL to a throwaway DB to run"),
    pytest.mark.xdist_group("pg"),
]


def _wc(text: str) -> int:
    return max(1, len(text.split()))


class _StubBook:
    async def get_draft(self, *a, **k):
        return {"text_content": ""}
    async def get_chapter_sort_orders(self, chapter_ids):
        return {}
    async def get_reader_language(self, *a, **k):
        return None


class _StubGrant:
    async def resolve_grant(self, *a, **k):
        return GrantLevel.OWNER
    async def resolve_access(self, *a, **k):
        return GrantLevel.OWNER, "active"


class _StubGlossary:
    async def select_for_context(self, *a, **k):
        return []


class _StubKnowledge:
    async def glossary_semantic(self, *a, **k):
        return []
    async def timeline(self, *a, **k):
        return []
    async def search_drawers(self, *a, **k):
        return []
    async def get_entity(self, *a, **k):
        return None


class _StubCanon:
    async def list_active(self, project_id):
        return []


class _StubSceneLinks:
    async def list_by_project(self, project_id):
        return []


@pytest.fixture
async def pool():
    p = await asyncpg.create_pool(_DSN, min_size=1, max_size=4)
    try:
        async with p.acquire() as c:
            for t in ("outline_node", "structure_node", "composition_work"):
                await c.execute(f"DROP TABLE IF EXISTS {t} CASCADE")
        await run_migrations(p)
        yield p
    finally:
        async with p.acquire() as c:
            for t in ("outline_node", "structure_node", "composition_work"):
                await c.execute(f"DROP TABLE IF EXISTS {t} CASCADE")
        await p.close()


async def _seed(pool, *, tracks: list[dict]) -> dict:
    """A book with one arc (carrying `tracks`), a chapter assigned to it, and a scene under
    the chapter. Returns the ids + the scene node dict pack() will draft."""
    actor, book, project, chapter = (uuid.uuid4() for _ in range(4))
    structures, outline = StructureRepo(pool), OutlineRepo(pool)
    async with pool.acquire() as c:
        await c.execute(
            "INSERT INTO composition_work (project_id, created_by, book_id) VALUES ($1,$2,$3)",
            project, actor, book,
        )
    arc = await structures.create_node(
        book, created_by=actor, kind="arc", title="Betrayal",
        goal="Kael turns on the crown", tracks=tracks,
    )
    # the CHAPTER node carries structure_node_id (a scene may not — the CHECK)
    chap = await outline.create_node(
        project, created_by=actor, kind="chapter", chapter_id=chapter, title="ch1",
    )
    assigned = await structures.assign_chapters(book, arc.id, [chap.id])
    assert assigned == 1
    scene = await outline.create_node(
        project, created_by=actor, kind="scene", parent_id=chap.id, chapter_id=chapter,
        title="s1", goal="the confrontation", story_order=5,
    )
    return {
        "actor": actor, "book": book, "project": project, "arc": arc,
        # the SCENE node dict — note: NO structure_node_id (a scene can't carry one)
        "scene_node": scene.model_dump(mode="python"),
    }


async def _pack_prompt(pool, seed) -> str:
    pc = await pack(
        PackRequest(user_id=seed["actor"], project_id=seed["project"], book_id=seed["book"],
                    node=seed["scene_node"], bearer="t", guide="", settings={}),
        book=_StubBook(), glossary=_StubGlossary(), knowledge=_StubKnowledge(),
        canon_repo=_StubCanon(), outline_repo=OutlineRepo(pool),
        scene_links_repo=_StubSceneLinks(),
        structure_repo=StructureRepo(pool),   # ← the wiring production must supply
        budget_tokens=10_000, counter=_wc, grant=_StubGrant(),
    )
    return pc.prompt


async def test_arc_reaches_the_prompt_through_the_real_scene_to_chapter_resolution(pool):
    """The scene carries no structure_node_id; the packer resolves it through the chapter and
    injects the arc. Proves BA12 on the REAL path, not a fake repo."""
    seed = await _seed(pool, tracks=[{"key": "loyalty", "label": "loyalty stays true"}])
    assert "structure_node_id" not in seed["scene_node"] or seed["scene_node"].get("structure_node_id") is None

    prompt = await _pack_prompt(pool, seed)
    assert "Betrayal" in prompt, "the resolved arc chain never reached the prompt (BA12 dormant)"
    assert "loyalty stays true" in prompt, "the arc's tracks never reached the prompt"


async def test_changing_tracks_changes_the_prompt_on_the_real_path(pool):
    """D2's effect, but through the production chokepoint: re-track the arc, re-pack the SAME
    scene, and the prompt must change."""
    seed_a = await _seed(pool, tracks=[{"key": "loyalty", "label": "loyalty stays true"}])
    before = await _pack_prompt(pool, seed_a)

    # re-track the same arc and re-pack the same scene
    await StructureRepo(pool).update(
        seed_a["arc"].id, {"tracks": [{"key": "loyalty", "label": "loyalty finally breaks"}]},
        expected_version=seed_a["arc"].version,
    )
    after = await _pack_prompt(pool, seed_a)

    assert before != after, "the packer did not react to a tracks change on the real path"
    assert "loyalty finally breaks" in after
    assert "loyalty stays true" not in after


async def test_arc_lens_dormant_for_an_unassigned_chapter(pool):
    """The gate: a scene whose chapter is NOT assigned to any arc injects no <arc> frame and
    does no arc work (the no-op path stays free)."""
    actor, book, project, chapter = (uuid.uuid4() for _ in range(4))
    outline = OutlineRepo(pool)
    async with pool.acquire() as c:
        await c.execute(
            "INSERT INTO composition_work (project_id, created_by, book_id) VALUES ($1,$2,$3)",
            project, actor, book,
        )
    await outline.create_node(project, created_by=actor, kind="chapter",
                              chapter_id=chapter, title="ch1")   # NOT assigned to an arc
    scene = await outline.create_node(project, created_by=actor, kind="scene",
                                      chapter_id=chapter, title="s1", story_order=5)
    prompt = await _pack_prompt(pool, {
        "actor": actor, "book": book, "project": project,
        "scene_node": scene.model_dump(mode="python"),
    })
    assert "<arc>" not in prompt, "an unassigned scene should inject no arc frame"
