"""27 V2-C5 — the artifact-I/O adapters.

These tests exist because the adapter layer is a JOIN between two things that are each individually
green: the pass registry (a contracts table) and seven engines (each with its own suite). Nothing
tested the join. The failure mode is silent and total — a pass declared but not wired 500s the first
time a user runs it, and a lossy artifact round-trip drops scenes between pass 6 and pass 7 while
every engine test stays green.
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from app.engine.plan import ChapterPlan, ChapterScenes, DecomposeResult, ScenePlan
from app.services.plan_pass_adapters import (
    PASS_ADAPTERS, PassContext, _artifact_to_decompose, _decompose_to_artifact,
)
from app.services.plan_pass_service import PASS_REGISTRY


def test_every_registered_pass_has_an_adapter_and_vice_versa():
    """A registry entry with no adapter is a pass that 500s the first time anyone runs it; an
    adapter with no registry entry is dead code that no fingerprint covers. The two key sets are one
    contract, so they are asserted EQUAL — not "adapters ⊆ registry"."""
    assert set(PASS_ADAPTERS) == set(PASS_REGISTRY)


def test_the_adapter_map_is_ordered_like_the_registry():
    """`pass_cursor` walks the registry in dependency order. If the adapter map drifted out of that
    order a reader would silently trust the wrong sequence."""
    assert list(PASS_ADAPTERS) == list(PASS_REGISTRY)


# ── the scene_plan round-trip (passes 6 ⇄ 7) ─────────────────────────────────────────────────────

def _result() -> DecomposeResult:
    return DecomposeResult(
        arc_title="Arc 1",
        chapters=[
            ChapterScenes(
                chapter=ChapterPlan(
                    chapter_id="arc_1_event_1", title="The Summons",
                    sort_order=1, beat_role="setup", intent="call to action",
                ),
                scenes=[
                    ScenePlan(
                        title="At the gate", synopsis="Ha waits.", tension=42,
                        present_entity_ids=[uuid4()],
                        present_entity_names_unresolved=["the Gatekeeper"],
                        suggested_k=3,
                    ),
                ],
                warning=None,
            ),
            ChapterScenes(
                chapter=ChapterPlan(
                    chapter_id="arc_1_event_2", title="Through", sort_order=2,
                    beat_role=None, intent="",
                ),
                scenes=[],
                warning="no_scenes_parsed",
            ),
        ],
        unmapped_beats=["climax"],
        motif_coverage={"bound": 1, "of": 2},
    )


def test_the_scene_plan_round_trip_is_LOSSLESS():
    """Pass 7 heals pass 6's plan IN PLACE, so it must read back exactly what pass 6 wrote. A field
    dropped here vanishes from the healed plan while every engine test stays green — the plan simply
    comes back with fewer scenes than it went in with, and nothing says so."""
    art = _decompose_to_artifact(_result())
    back = _artifact_to_decompose(art)
    assert _decompose_to_artifact(back) == art  # fixed point ⇒ nothing was lost

    orig = _result()
    assert back.arc_title == orig.arc_title
    assert back.unmapped_beats == orig.unmapped_beats
    assert back.motif_coverage == orig.motif_coverage
    assert len(back.chapters) == 2

    s = back.chapters[0].scenes[0]
    o = orig.chapters[0].scenes[0]
    assert s.title == o.title and s.synopsis == o.synopsis and s.tension == o.tension
    assert s.suggested_k == o.suggested_k
    assert s.present_entity_names_unresolved == o.present_entity_names_unresolved
    assert len(s.present_entity_ids) == 1  # the UUID survived as a UUID, not a str

    # the degraded chapter keeps its warning — "0 scenes" and "0 scenes AND we know why" are not
    # the same artifact, and the second is the one a human can act on
    assert back.chapters[1].scenes == []
    assert back.chapters[1].warning == "no_scenes_parsed"
    assert back.chapters[0].chapter.beat_role == "setup"


def test_an_empty_artifact_round_trips_to_an_empty_result_not_a_crash():
    r = _artifact_to_decompose({})
    assert r.chapters == [] and r.arc_title == ""


# ── absent ≠ zero ────────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_the_motifs_pass_with_NO_RETRIEVER_is_DEGRADED_not_empty():
    """The bug class this repo keeps shipping: a green-looking zero over an unknown. With no motif
    retriever we could not even LOOK — which is not the same as "this book has no motifs". A bare
    `[]` renders as the latter, forever, and nobody ever finds out."""
    from app.services.plan_pass_adapters import run_motifs

    art = await run_motifs(PassContext(
        llm=None, user_id=str(uuid4()), book_id=uuid4(), project_id=uuid4(),
        model_source="user_model", model_ref="m", retriever=None,
    ))
    assert art["motifs"] == []
    assert art["degraded"] is True
    assert art["warning"]


@pytest.mark.asyncio
async def test_self_heal_with_no_scenes_says_so_rather_than_reporting_a_silent_success():
    """A success status with no work done is a bug, not a no-op (`silent-success-is-a-bug`)."""
    from app.services.plan_pass_adapters import run_self_heal

    art = await run_self_heal(PassContext(
        llm=None, user_id=str(uuid4()), book_id=uuid4(), project_id=uuid4(),
        model_source="user_model", model_ref="m",
        inputs={"scenes": {"chapters": []}},
    ))
    assert art["heal"]["note"] == "no scenes to heal"
    assert art["heal"]["edits_applied"] == 0


# ── the package readers ──────────────────────────────────────────────────────────────────────────

def test_the_package_readers_tolerate_a_malformed_package():
    """The package is produced by `compile()`, which is itself fed by a tolerant parser. A missing
    or wrong-typed key must degrade to empty, not raise inside a worker where the traceback is the
    only thing the user ever sees."""
    ctx = PassContext(
        llm=None, user_id=str(uuid4()), book_id=uuid4(), project_id=uuid4(),
        model_source="s", model_ref="m",
        package={"premise": None, "beats": "not a list", "chapters": None},
    )
    assert ctx.premise == "" and ctx.beats == [] and ctx.chapters == [] and ctx.arc_title == ""


def test_chapter_plans_carry_pass4s_beat_roles_onto_the_engines_shape():
    """Pass 6 hands pass 4's roles back to the engine on `ChapterPlan.beat_role` — that is what makes
    `grounded_decompose` skip L1 rather than re-run (and re-bill) it."""
    from app.services.plan_pass_adapters import _chapter_plans

    ctx = PassContext(
        llm=None, user_id=str(uuid4()), book_id=uuid4(), project_id=uuid4(),
        model_source="s", model_ref="m",
        package={"chapters": [
            {"ordinal": 1, "event_id": "arc_1_event_1", "title": "A", "synopsis": "sa"},
            {"ordinal": 2, "event_id": "arc_1_event_2", "title": "B", "synopsis": "sb"},
        ]},
    )
    plans = _chapter_plans(ctx, {1: "setup", 2: "climax"})
    assert [p.beat_role for p in plans] == ["setup", "climax"]
    assert [p.sort_order for p in plans] == [1, 2]
    # `chapter_id` is the PLAN's event id — at plan time the manuscript chapter may not exist yet
    assert [p.chapter_id for p in plans] == ["arc_1_event_1", "arc_1_event_2"]
