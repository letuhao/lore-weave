"""Re-plan MERGES author-settled intent instead of replacing it (spec 2026-07-28).

WHY THIS EXISTS. `outline_node` is the SSOT for settled intent — but that choice does not survive
its own code path without this behaviour: a re-plan `is_archived`s the chapter/scene nodes and
inserts a FRESH tree built purely from the plan output, carrying nothing forward. So the first time
an author re-planned, every slot they had settled would be silently deleted and replaced by the
planner's values (which, measured 2026-07-28, are empty: 0 of 95 chapter nodes carried any intent
slot, and 0 of 30 plan chapter entries carried a non-empty `intent`).

An intent-collection FSM whose output the next re-plan deletes is worse than none, because by then
the author is relying on it. Hence: merge, with the higher-tier-wins cascade this repo already
mandates for settings — author-settled shadows planner-proposed.

The EFFECT gate: every assertion reads PERSISTED rows after a real re-plan, not a return value.

Gated on TEST_COMPOSITION_DB_URL; drops + rebuilds the schema. xdist_group('pg') per the shared-DB
rule.
"""

from __future__ import annotations

import json
import os
import uuid

import asyncpg
import pytest

from app.db.migrate import run_migrations
from app.db.repositories.outline import OutlineRepo
from app.db.repositories.works import WorksRepo

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


def _plan(chapter_id: str, *, intent: str, beat_role: str) -> list[dict]:
    """One chapter the planner proposes, in the shape the materializer consumes."""
    return [{
        "chapter_id": chapter_id,
        "title": "The Wet Ink",
        "intent": intent,
        "beat_role": beat_role,
        "story_order": 1000,
        "scenes": [{"title": "s1", "synopsis": "…", "tension": 3, "story_order": 1000}],
    }]


async def _chapter_row(pool, project_id, chapter_id):
    async with pool.acquire() as c:
        return await c.fetchrow(
            "SELECT goal, beat_role, intent_slots FROM outline_node "
            "WHERE project_id=$1 AND kind='chapter' AND chapter_id=$2 AND NOT is_archived",
            project_id, chapter_id,
        )


async def _seed_work(pool):
    actor, book_id = uuid.uuid4(), uuid.uuid4()
    work = await WorksRepo(pool).create_pending(actor, book_id)
    return actor, book_id, work.id


@pytest.mark.asyncio
async def test_the_chapter_node_gets_its_OWN_beat_role(pool):
    """It did not, and was justified by a docstring claiming a DB CHECK forbade it. The check says
    the opposite (kind IN ('scene','chapter')), so the plan's curve lived only in plan_artifact
    while outline_node.beat_role was 0 of 95."""
    actor, book_id, project_id = await _seed_work(pool)
    ch = str(uuid.uuid4())
    repo = OutlineRepo(pool)
    await repo.commit_decomposed_tree(
        project_id, created_by=actor, book_id=book_id, arc_title="Arc I",
        chapters=_plan(ch, intent="he refuses the summons", beat_role="hook"),
    )
    row = await _chapter_row(pool, project_id, ch)
    assert row["beat_role"] == "hook"


@pytest.mark.asyncio
async def test_a_re_plan_KEEPS_the_slot_the_author_settled(pool):
    """The load-bearing case. The author settles `goal`; the planner then proposes a different one
    on a re-plan. Author-settled shadows planner-proposed."""
    actor, book_id, project_id = await _seed_work(pool)
    ch = str(uuid.uuid4())
    repo = OutlineRepo(pool)
    await repo.commit_decomposed_tree(
        project_id, created_by=actor, book_id=book_id, arc_title="Arc I",
        chapters=_plan(ch, intent="planner's first idea", beat_role="hook"),
    )
    # The author settles the goal — what the FSM's apply step will do.
    async with pool.acquire() as c:
        await c.execute(
            "UPDATE outline_node SET goal=$3, intent_slots=$4::jsonb "
            "WHERE project_id=$1 AND kind='chapter' AND chapter_id=$2 AND NOT is_archived",
            project_id, ch, "Lâm Uyên refuses the summons", json.dumps({"goal": "settled"}),
        )

    await repo.commit_decomposed_tree(
        project_id, created_by=actor, book_id=book_id, arc_title="Arc I",
        chapters=_plan(ch, intent="planner's SECOND idea", beat_role="setback"),
        replace=True,
    )

    row = await _chapter_row(pool, project_id, ch)
    assert row["goal"] == "Lâm Uyên refuses the summons", "the author's settled goal was destroyed"
    # A slot the author never touched DOES take the planner's fresh value — the merge must not
    # freeze the whole node, which is why node-level `source` was too coarse for this.
    assert row["beat_role"] == "setback"


@pytest.mark.asyncio
async def test_the_merge_survives_a_SECOND_re_plan(pool):
    """`intent_slots` is re-stamped on the fresh node. Dropping it would make the merge work
    exactly once — the kind of bug that looks fixed in a demo and loses work in week two."""
    actor, book_id, project_id = await _seed_work(pool)
    ch = str(uuid.uuid4())
    repo = OutlineRepo(pool)
    await repo.commit_decomposed_tree(
        project_id, created_by=actor, book_id=book_id, arc_title="Arc I",
        chapters=_plan(ch, intent="v1", beat_role="hook"),
    )
    async with pool.acquire() as c:
        await c.execute(
            "UPDATE outline_node SET goal=$3, intent_slots=$4::jsonb "
            "WHERE project_id=$1 AND kind='chapter' AND chapter_id=$2 AND NOT is_archived",
            project_id, ch, "authored", json.dumps({"goal": "settled"}),
        )
    for v in ("v2", "v3"):
        await repo.commit_decomposed_tree(
            project_id, created_by=actor, book_id=book_id, arc_title="Arc I",
            chapters=_plan(ch, intent=v, beat_role="hook"), replace=True,
        )
    row = await _chapter_row(pool, project_id, ch)
    assert row["goal"] == "authored"
    assert row["intent_slots"] in ('{"goal": "settled"}', {"goal": "settled"})


@pytest.mark.asyncio
async def test_an_ABSENT_slot_is_not_quietly_refilled(pool):
    """`absent` is an AUTHORED STATEMENT — "the story has not decided this" — not a gap. A re-plan
    that refills it would re-introduce exactly what the three-state model exists to prevent: the
    machine answering a question the author declined."""
    actor, book_id, project_id = await _seed_work(pool)
    ch = str(uuid.uuid4())
    repo = OutlineRepo(pool)
    await repo.commit_decomposed_tree(
        project_id, created_by=actor, book_id=book_id, arc_title="Arc I",
        chapters=_plan(ch, intent="", beat_role="hook"),
    )
    async with pool.acquire() as c:
        await c.execute(
            "UPDATE outline_node SET goal='', intent_slots=$3::jsonb "
            "WHERE project_id=$1 AND kind='chapter' AND chapter_id=$2 AND NOT is_archived",
            project_id, ch, json.dumps({"goal": "absent"}),
        )

    await repo.commit_decomposed_tree(
        project_id, created_by=actor, book_id=book_id, arc_title="Arc I",
        chapters=_plan(ch, intent="the planner's confident guess", beat_role="hook"),
        replace=True,
    )

    row = await _chapter_row(pool, project_id, ch)
    assert row["goal"] == "", "an absent slot was refilled by the planner"
    state = row["intent_slots"]
    if isinstance(state, str):
        state = json.loads(state)
    assert state == {"goal": "absent"}, "the absent marker must survive, or it is re-asked forever"


@pytest.mark.asyncio
async def test_a_FIRST_plan_takes_the_planner_values_untouched(pool):
    """No carry-forward on a first plan — there is nothing settled yet, and a merge that leaked
    into the greenfield path would make the planner's output unreachable."""
    actor, book_id, project_id = await _seed_work(pool)
    ch = str(uuid.uuid4())
    await OutlineRepo(pool).commit_decomposed_tree(
        project_id, created_by=actor, book_id=book_id, arc_title="Arc I",
        chapters=_plan(ch, intent="planner goal", beat_role="climax"),
    )
    row = await _chapter_row(pool, project_id, ch)
    assert row["goal"] == "planner goal"
    assert row["beat_role"] == "climax"
