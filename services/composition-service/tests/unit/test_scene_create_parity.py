"""D-SCENE-CREATE-PARITY — every scene column PlanForge writes must be reachable here.

There are two ways a scene node comes into being:

* **PlanForge** — `plan_link_service._UPSERT_SCENE`, when a compiled plan is linked;
* **an author or agent** — `composition_outline_node_create` / the unified
  `composition_outline_node_edit op="create"`.

They wrote different column sets, and the difference was invisible because every missing
field degrades QUIETLY rather than failing:

* `story_order` — the reading axis. NULL meant the cross-scene state-reinjection
  (`prior_scene_drafts`: `story_order < $3`) matched nothing, so every scene drafted blind
  and five scenes of Chương 1 closed on the SAME image.
* `present_entity_ids` — the scene's CAST, and what the packer loads character lore and
  voices from. Empty means a scene is drafted with no idea who is in it.
* `tension` — the beat's charge, read by the pacing lens and the arc-conformance judge.

Each was found by reading the two paths side by side. That does not scale, and it is not
something a reviewer should have to redo every time PlanForge gains a field — so this is a
gate, not a checklist. It parses the real `_UPSERT_SCENE` statement and fails when it names
a scene column the create path cannot reach.
"""
from __future__ import annotations

import re

from app.mcp.server import _NodeCreateArgs, _OutlineNodeEditArgs
from app.services.plan_link_service import _UPSERT_SCENE

#: Columns PlanForge writes that an author path deliberately does NOT expose, each with the
#: reason it is not a gap. Anything NOT listed here must be reachable — a new exemption has
#: to be argued for in this dict, which is the point.
_NOT_AN_AUTHOR_FIELD: dict[str, str] = {
    "created_by": "actor stamp, taken from the tool context — never a caller argument",
    "project_id": "the Work partition, resolved from the gate/ambient context",
    "book_id": "derived inside the INSERT from composition_work; can never be passed",
    "kind": "a required positional on the create tool, not an optional field",
    "rank": "the UI tree axis — auto-computed on append (`_next_rank`)",
    "parent_id": "a required positional on the create tool",
    "status": "a required field with a default on the create tool",
    "story_order": (
        "the reading axis — auto-derived via `_renumber_scene_story_order` so a writer "
        "never has to know the column exists (D-SCENE-STORY-ORDER-UNWIRED)"
    ),
    "source": "provenance ('planforge' vs the default) — set by the writer, not the caller",
    "plan_run_id": "plan-run provenance; meaningless outside a compile",
    "plan_event_id": "plan-run provenance; meaningless outside a compile",
}


def _upsert_scene_columns() -> list[str]:
    """The column list from the real INSERT — parsed, not transcribed, so this gate reads
    what actually ships rather than a copy that can drift from it."""
    m = re.search(r"INSERT INTO outline_node\s*\((.*?)\)\s*VALUES", _UPSERT_SCENE, re.S)
    assert m, "could not parse _UPSERT_SCENE's column list — has the statement changed shape?"
    return [c.strip() for c in m.group(1).split(",") if c.strip()]


def test_the_gate_can_see_planforges_columns():
    """A parser that silently returns nothing would make every assertion below vacuous."""
    cols = _upsert_scene_columns()
    assert len(cols) >= 12, cols
    for expected in ("title", "synopsis", "tension", "present_entity_ids", "story_order"):
        assert expected in cols, f"{expected} missing — the parse is wrong, not the code"


def test_every_planforge_scene_column_is_reachable_from_the_create_tool():
    unreachable = [
        c for c in _upsert_scene_columns()
        if c not in _NOT_AN_AUTHOR_FIELD and c not in _NodeCreateArgs.model_fields
    ]
    assert not unreachable, (
        "PlanForge writes these scene columns and the author/agent create path cannot:\n  "
        + "\n  ".join(unreachable)
        + "\n\nEvery field in this set degrades SILENTLY — a scene is still created, and "
        "some downstream lens just has less to work with. Either expose it on "
        "_NodeCreateArgs, or add it to _NOT_AN_AUTHOR_FIELD with the reason it is not a gap."
    )


def test_the_unified_edit_tool_forwards_them_too():
    """`composition_outline_node_edit` is what an agent actually calls (the `*_create`
    variants are `visibility='legacy'`). A field reachable only on the legacy tool is still
    unreachable in practice."""
    missing = [
        c for c in _upsert_scene_columns()
        if c not in _NOT_AN_AUTHOR_FIELD and c not in _OutlineNodeEditArgs.model_fields
    ]
    assert not missing, (
        "reachable on the legacy create tool but NOT on the unified edit tool an agent "
        f"actually calls: {missing}"
    )


def test_the_cast_and_charge_are_editable_after_creation():
    """The two fields found missing in the live review. A cast list is what an author most
    often gets wrong on the first pass — a character joins the scene late — so create-only
    would just be a slower version of the same dead end `chapter_id` was."""
    for field in ("tension", "present_entity_ids"):
        assert field in _OutlineNodeEditArgs.model_fields, field


def test_the_exemption_list_stays_honest():
    """An exemption for a column PlanForge no longer writes is dead weight that makes the
    gate look more considered than it is."""
    cols = set(_upsert_scene_columns())
    stale = [c for c in _NOT_AN_AUTHOR_FIELD if c not in cols]
    assert not stale, f"exempted but no longer written by PlanForge: {stale}"
