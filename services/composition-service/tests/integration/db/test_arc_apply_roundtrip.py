"""23 A5 (BA3) — arc_apply / arc_extract_template round-trip against a real Postgres.

Proves the two explicit snapshot ops between an `arc_template` (library REGISTRY)
and a `structure_node` (per-book SPEC) are a real inverse pair:

  apply(template) → spec  : rescales chapter_span onto the arc's MEMBER chapters,
                            materializes scenes, writes a motif_application ledger,
                            writes the template's PACING curve INTO scene tension
                            (BA3 — pacing is derived-from-tension, not stored), and
                            stamps tracks/roster/roster_bindings + provenance.
  extract(spec) → template: reads it all back — scenes' tension → pacing, the ledger
                            → layout, resolved tracks → threads, roster → arc_roster.

The EFFECT gate (checklist-is-self-report-enforce-by-tests): the assertions are on
persisted rows (scene tension, ledger annotations, spec node columns) and on the
extracted template's fields matching the source — not on the functions' return alone.

Gated on TEST_COMPOSITION_DB_URL; drops + rebuilds the composition schema. Mirrors
test_structure_repo.py's fixture. xdist_group('pg') per the shared-DB rule.
"""

from __future__ import annotations

import os
import uuid

import asyncpg
import pytest

from app.db.migrate import run_migrations
from app.db.models import ArcTemplateCreateArgs, MotifCreateArgs
from app.db.repositories.arc_template_repo import ArcTemplateRepo
from app.db.repositories.motif_application import MotifApplicationRepo
from app.db.repositories.motif_repo import MotifRepo
from app.db.repositories.outline import OutlineRepo
from app.db.repositories.structure import StructureRepo
from app.db.repositories.works import WorksRepo
from app.engine.arc_apply import (
    ArcApplyConflict,
    ArcApplyError,
    arc_apply,
    arc_extract_template,
)
from app.routers.conformance import ConformanceTraceReader

_DSN = os.environ.get("TEST_COMPOSITION_DB_URL")

pytestmark = [
    pytest.mark.skipif(
        not _DSN, reason="set TEST_COMPOSITION_DB_URL to a throwaway DB to run",
    ),
    pytest.mark.xdist_group("pg"),
]

_TABLES = [
    "structure_node", "motif_application", "motif_link", "motif", "arc_template",
    "plan_bootstrap_proposal", "plan_artifact", "plan_run",
    "composition_daily_progress", "composition_progress_baseline",
    "style_profile", "voice_profile", "scene_grounding_pins", "reference_source",
    "decompose_commit", "outbox_events", "generation_correction", "generation_job",
    "narrative_thread", "canon_rule", "scene_link", "outline_node",
    "structure_template", "entity_override", "divergence_spec", "composition_work",
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


# ── seeding helpers ──────────────────────────────────────────────────────────────

async def _seed_motif(pool, actor, code, name):
    """A minimal 1-beat, 1-role motif so a placement materializes exactly one scene."""
    return await MotifRepo(pool).create(
        actor,
        MotifCreateArgs(
            code=code, name=name, kind="sequence",
            roles=[{"key": "protagonist", "actant": "subject", "label": "Hero"}],
            beats=[{"key": "b1", "label": f"{name} beat", "intent": "{protagonist} acts",
                    "order": 0, "tension_target": 3}],
        ),
    )


async def _make_arc_with_chapters(pool, actor, project, book, story_orders):
    """A spec arc + N member chapters (chapter outline nodes assigned to it)."""
    struct = StructureRepo(pool)
    outline = OutlineRepo(pool)
    arc = await struct.create_node(book, created_by=actor, kind="arc", title="Betrayal")
    chapter_ids = []
    for so in story_orders:
        ch = await outline.create_node(
            project, created_by=actor, kind="chapter", chapter_id=uuid.uuid4(),
            title=f"Ch{so}", story_order=so, status="outline",
        )
        chapter_ids.append(ch.id)
    await struct.assign_chapters(book, arc.id, chapter_ids)
    return arc, chapter_ids


def _resolver(motifs):
    by_id = {str(m.id): m for m in motifs}
    by_code = {m.code: m for m in motifs}

    async def resolve(placements):
        out = []
        for p in placements:
            if p.motif_id is not None:
                out.append(by_id.get(str(p.motif_id)))
            else:
                out.append(by_code.get(p.motif_code))
        return out

    return resolve


# ── the round-trip ───────────────────────────────────────────────────────────────

async def test_apply_then_extract_round_trips(pool):
    actor, project, book = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    await WorksRepo(pool).create(actor, project, book)
    arc, chapter_ids = await _make_arc_with_chapters(pool, actor, project, book, [0, 1, 2])

    m_hook = await _seed_motif(pool, actor, "m.hook", "Hook")
    m_mid = await _seed_motif(pool, actor, "m.mid", "Midpoint")
    m_climax = await _seed_motif(pool, actor, "m.climax", "Climax")

    template = await ArcTemplateRepo(pool).create(
        actor,
        ArcTemplateCreateArgs(
            code="arc.betrayal", name="Betrayal Arc", chapter_span=3,
            threads=[{"key": "combat", "label": "Combat"},
                     {"key": "cultivation", "label": "Cultivation"}],
            layout=[
                {"motif_code": "m.hook", "motif_id": m_hook.id, "thread": "combat",
                 "span_start": 1, "span_end": 1, "ord": 0},
                {"motif_code": "m.mid", "motif_id": m_mid.id, "thread": "combat",
                 "span_start": 2, "span_end": 2, "ord": 1},
                {"motif_code": "m.climax", "motif_id": m_climax.id, "thread": "cultivation",
                 "span_start": 3, "span_end": 3, "ord": 2},
            ],
            pacing=[{"tension": 40}, {"tension": 70}, {"tension": 100}],
            arc_roster=[{"key": "protagonist", "actant": "subject", "label": "Hero"}],
        ),
    )

    hero = uuid.uuid4()
    cast_index = {"hero": str(hero)}
    cast_names = {str(hero): "Hero"}

    struct = StructureRepo(pool)
    outline = OutlineRepo(pool)
    apps = MotifApplicationRepo(pool)

    result = await arc_apply(
        template, arc,
        created_by=actor,
        structure_repo=struct, outline_repo=outline, applications_repo=apps,
        resolve_motifs=_resolver([m_hook, m_mid, m_climax]),
        cast_index=cast_index, cast_names=cast_names,
        roster_bindings={"protagonist": "Hero"},
        k_ceiling=8, high_threshold=70, min_scenes=1, max_scenes=5,
    )

    # ── apply EFFECT: one scene per chapter, tension came FROM the pacing curve ──
    assert result.scenes_total == 3
    assert result.motif_applications == 3
    assert result.pacing_written == 3           # every scene got its chapter's pacing value

    tension_by_chapter = {}
    for j, cid in enumerate(chapter_ids):
        ch = await outline.get_node(cid)
        scenes = await outline.scenes_for_chapter(project, ch.chapter_id)
        assert len(scenes) == 1
        tension_by_chapter[j] = scenes[0].tension
    # BA3 crux: the template's pacing curve [40,70,100] landed in scene tension.
    assert [tension_by_chapter[0], tension_by_chapter[1], tension_by_chapter[2]] == [40, 70, 100]

    # spec node stamped: tracks ← threads, roster ← arc_roster, bindings resolved, provenance.
    reloaded = await struct.get(arc.id)
    assert {t["key"] for t in reloaded.tracks} == {"combat", "cultivation"}
    assert {r["key"] for r in reloaded.roster} == {"protagonist"}
    assert reloaded.roster_bindings == {"protagonist": str(hero)}
    assert reloaded.arc_template_id == template.id
    assert reloaded.template_version == template.version

    # the ledger pins the arc (annotations bridge) + the motif code for extract.
    scene_ids = [uuid.UUID(s) for s in result.scene_ids]
    ledger = await apps.by_nodes(project, scene_ids)
    assert len(ledger) == 3
    assert all(row.annotations.get("structure_node_id") == str(arc.id) for row in ledger)
    assert {row.annotations.get("motif_code") for row in ledger} == {"m.hook", "m.mid", "m.climax"}

    # ── A5→A4 seam BY EFFECT through arc_apply (not a hand-built row) ──────────────
    # (1) Every ledger row arc_apply wrote carries the arc on the FIRST-CLASS column,
    #     not merely in annotations — conformance reads the column (23-A4), so a row
    #     with the arc only in annotations would be INVISIBLE to the report it feeds.
    assert all(row.structure_node_id == arc.id for row in ledger), (
        "arc_apply did not set motif_application.structure_node_id first-class — "
        "the A5→A4 seam is broken (rows invisible to arc conformance)"
    )

    # (2) Read those exact rows back through the deep conformance job's own query and
    #     assert the SAME bindings surface: apply → column → conformance, end to end.
    reader = ConformanceTraceReader(pool)
    bindings = await reader.arc_bindings_by_structure(project, arc.id)
    assert len(bindings) == 3, (
        "arc_apply's bindings are invisible to arc_bindings_by_structure — the "
        "A5→A4 seam does not hold end to end through arc_apply"
    )
    # motif_code comes from the JOINed motif.code (the column path), and matches the
    # three motifs applied — proving the join lands on the real scenes, not annotations.
    assert {b["motif_code"] for b in bindings} == {"m.hook", "m.mid", "m.climax"}
    # the tension the pacing curve wrote rides back through the outline_node JOIN too.
    assert {b["tension"] for b in bindings} == {40, 70, 100}

    # (3) The column — not annotations — is the discriminator: a DIFFERENT arc id (even
    #     within the same project) captures none of these rows.
    assert await reader.arc_bindings_by_structure(project, uuid.uuid4()) == []

    # ── extract EFFECT: the exact inverse recovers the template's shape ──
    extract = await arc_extract_template(
        arc, code="arc.betrayal.saved", name="Betrayal (saved)",
        structure_repo=struct, outline_repo=outline, applications_repo=apps,
    )
    args = extract.args
    assert {t.key for t in args.threads} == {"combat", "cultivation"}
    assert args.chapter_span == 3
    assert {r.key for r in args.arc_roster} == {"protagonist"}
    # pacing curve read back out of scene tension → same values.
    assert [p["tension"] for p in args.pacing] == [40, 70, 100]
    # layout rebuilt from the ledger: same motifs, same threads, single-chapter spans.
    lay = {p.motif_code: p for p in args.layout}
    assert set(lay) == {"m.hook", "m.mid", "m.climax"}
    assert (lay["m.hook"].span_start, lay["m.hook"].span_end) == (1, 1)
    assert (lay["m.mid"].span_start, lay["m.mid"].span_end) == (2, 2)
    assert (lay["m.climax"].span_start, lay["m.climax"].span_end) == (3, 3)
    assert lay["m.hook"].thread == "combat" and lay["m.climax"].thread == "cultivation"


async def test_apply_no_member_chapters_is_clean_error(pool):
    actor, project, book = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    await WorksRepo(pool).create(actor, project, book)
    struct = StructureRepo(pool)
    arc = await struct.create_node(book, created_by=actor, kind="arc")
    template = await ArcTemplateRepo(pool).create(
        actor, ArcTemplateCreateArgs(code="arc.x", name="X", chapter_span=3))

    async def _resolve(_):
        return []

    with pytest.raises(ArcApplyError):
        await arc_apply(
            template, arc, created_by=actor,
            structure_repo=struct, outline_repo=OutlineRepo(pool),
            applications_repo=MotifApplicationRepo(pool),
            resolve_motifs=_resolve, cast_index={}, cast_names={},
            k_ceiling=8, high_threshold=70, min_scenes=1, max_scenes=5,
        )


async def test_apply_existing_scenes_conflict_then_replace(pool):
    actor, project, book = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    await WorksRepo(pool).create(actor, project, book)
    arc, _ = await _make_arc_with_chapters(pool, actor, project, book, [0])
    m = await _seed_motif(pool, actor, "m.only", "Only")
    template = await ArcTemplateRepo(pool).create(
        actor,
        ArcTemplateCreateArgs(
            code="arc.one", name="One", chapter_span=1,
            layout=[{"motif_code": "m.only", "motif_id": m.id, "thread": "main",
                     "span_start": 1, "span_end": 1, "ord": 0}],
            pacing=[{"tension": 55}],
        ),
    )
    struct, outline, apps = StructureRepo(pool), OutlineRepo(pool), MotifApplicationRepo(pool)
    common = dict(
        created_by=actor, structure_repo=struct, outline_repo=outline,
        applications_repo=apps, resolve_motifs=_resolver([m]),
        cast_index={}, cast_names={}, k_ceiling=8, high_threshold=70,
        min_scenes=1, max_scenes=5,
    )
    r1 = await arc_apply(template, arc, **common)
    assert r1.scenes_total == 1
    # second apply without replace → conflict (the chapter already has a scene)
    with pytest.raises(ArcApplyConflict):
        await arc_apply(template, arc, **common)
    # with replace → prior scene archived, re-materialized fresh
    r2 = await arc_apply(template, arc, replace=True, **common)
    assert r2.scenes_total == 1
    # exactly one ACTIVE scene remains (the prior one was archived, not duplicated)
    ch = await outline.get_node((await struct.member_chapter_ids(arc.id))[0])
    assert len(await outline.scenes_for_chapter(project, ch.chapter_id)) == 1
