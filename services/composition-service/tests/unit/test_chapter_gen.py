"""B2 chapter_gen pure-helper tests — union cast, combined synopsis, pack node."""

from __future__ import annotations

import uuid

from app.db.models import OutlineNode
from app.engine.chapter_gen import (
    STORY_ORDER_CHAPTER_STRIDE,
    build_chapter_pack_node,
    build_combined_synopsis,
    union_cast,
)

U, P, CH = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
B = uuid.uuid4()
E1, E2, E3 = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()


def _scene(rank, *, title="", synopsis="", tension=None, present=None, pov=None, story_order=None):
    return OutlineNode(id=uuid.uuid4(), created_by=U, project_id=P, book_id=B, kind="scene",
                       rank=rank,
                       chapter_id=CH, title=title, synopsis=synopsis, tension=tension,
                       present_entity_ids=present or [], pov_entity_id=pov, story_order=story_order)


def test_union_cast_dedups_preserving_first_seen_order():
    scenes = [_scene("a0", present=[E1, E2], pov=E1),
              _scene("a1", present=[E2, E3])]
    assert union_cast(scenes) == [E1, E2, E3]


def test_union_cast_pov_included_before_present():
    # pov_entity_id is part of the cast, listed before that scene's present ids.
    scenes = [_scene("a0", pov=E3, present=[E1])]
    assert union_cast(scenes) == [E3, E1]


def test_union_cast_empty():
    assert union_cast([]) == []
    assert union_cast([_scene("a0")]) == []


def test_combined_synopsis_includes_intent_and_ordered_beats():
    scenes = [_scene("a0", title="Arrival", synopsis="they reach the gate", tension=30),
              _scene("a1", title="Duel", synopsis="swords cross", tension=85)]
    out = build_combined_synopsis("The company reaches the keep", scenes)
    assert out.startswith("The company reaches the keep")
    assert "Scenes in order:" in out
    assert "1. Arrival — they reach the gate (tension 30)" in out
    assert "2. Duel — swords cross (tension 85)" in out


def test_combined_synopsis_skips_empty_parts():
    # No intent, a scene with no synopsis / no tension → clean, no dangling sep.
    out = build_combined_synopsis("", [_scene("a0", title="Quiet")])
    assert out == "Scenes in order:\n1. Quiet"


def test_build_chapter_pack_node_shape():
    scenes = [_scene("a0", title="A", synopsis="x", tension=30, present=[E1], pov=E2)]
    node = build_chapter_pack_node(chapter_id=CH, chapter_sort=3,
                                   chapter_intent="intent", chapter_title="Ch1", scenes=scenes)
    assert node["id"] is None                      # synthetic — never persisted
    assert node["chapter_id"] == CH
    assert node["story_order"] == 3 * STORY_ORDER_CHAPTER_STRIDE  # chapter opening
    assert node["present_entity_ids"] == [E2, E1]  # union (pov first)
    assert node["pov_entity_id"] is None and node["beat_role"] is None
    assert node["goal"] == "intent" and node["title"] == "Ch1"
    assert "A — x (tension 30)" in node["synopsis"]


def test_build_chapter_pack_node_no_sort_leaves_story_order_none():
    node = build_chapter_pack_node(chapter_id=CH, chapter_sort=None,
                                   chapter_intent="", chapter_title="", scenes=[_scene("a0")])
    assert node["story_order"] is None


def test_build_messages_draft_chapter_instructs_whole_chapter():
    # /review-impl MED-1: 'draft_chapter' must register a chapter-level instruction,
    # NOT fall back to the per-scene "next passage of the scene" (which would
    # fragment the single-pass output). diverge() rebuilds these messages too.
    from app.engine.cowrite import build_messages
    from app.packer.profile import NEUTRAL

    user = build_messages("GROUNDING", NEUTRAL, "draft_chapter", "")[1]["content"]
    assert "ENTIRE chapter" in user
    assert "next passage of the scene" not in user
