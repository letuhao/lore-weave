"""D-SCENE-INTENT-NEVER-SHOWN — the author fills twelve fields; the drafter saw four.

`gather_structural` built a five-key beat dict (beat_role, goal, pov, synopsis, title) and
its docstring said exactly that: it predates SC4, which added eight fields of authored
scene intent, and was never updated. `assemble.build_segments` then rendered four of them.

So `conflict`, `outcome`, `stakes`, `value_shift`, `tension`, `story_time`,
`location_entity_id` and `exit_state` were asked for on the create tool, validated at the
schema, written to the database — and never shown to the model.

Measured on the Mị Đế book: five scenes authored with `tension` 70/80/45/35/65 plus
conflict, outcome and stakes on every one. None of it reached the prompt. The prose came
back thin and drifting for the obvious reason: it was written from a goal and a summary,
with no idea what opposed the character, what was at risk, how the scene should resolve,
or what state it had to leave behind.

**A field an author fills that no consumer reads is not a feature — it is a lie about what
the tool does with their work.** These tests are a gate against a ninth field joining them:
they read the create tool's own schema and fail when an authored field cannot be traced all
the way to the rendered prompt.
"""
from __future__ import annotations

import pytest

from app.mcp.server import _NodeCreateArgs
from app.packer.assemble import build_segments
from app.packer.lenses import gather_structural

#: Fields on the create tool that are NOT scene intent, with the reason. Anything else must
#: reach the prompt — a new exemption has to be argued for here, which is the point.
_NOT_SCENE_INTENT: dict[str, str] = {
    "project_id": "the Work partition, not a story fact",
    "kind": "chapter|scene discriminator",
    "parent_id": "tree structure",
    "chapter_id": "manuscript binding",
    "title": "rendered separately (it names the scene, it is not a brief for it)",
    "status": "authoring workflow state, not story content",
    "target_words": "sizes the LENGTH directive + the output budget, not the beat block",
    "present_entity_ids": "rendered in <present> — the cast lens, not the beat line",
    # D-SCENE-BEATS. Same family as `target_words` directly above: it STRUCTURES the drafting
    # rather than being a story fact. `draft_beats` is how many calls the scene is written in
    # and what each covers, so the lens must NOT flatten it into the beat block — that would
    # hand the model every beat at once, which is precisely the whole-chapter-visible framing
    # that made the drafter annex its neighbours (SCENE-BOUNDARY, 2026-07-30).
    #
    # Each beat's CONTENT does reach a prompt in slice 2 — as the brief for its OWN call, one
    # at a time. This exemption covers the list, not the content.
    "draft_beats": "the drafting control structure (one call per beat), not a story fact; "
                   "each beat's content reaches its OWN call's prompt in slice 2",
}


def _beat_from(node: dict) -> dict:
    """The beat dict the lens builds — the first half of the path."""
    import asyncio
    import uuid
    from unittest.mock import AsyncMock

    scene_links = AsyncMock()
    scene_links.list_by_project = AsyncMock(return_value=[])
    outline = AsyncMock()
    outline.list_tree = AsyncMock(return_value=[])
    beat, _threads, _planned = asyncio.run(
        gather_structural(outline, scene_links, project_id=uuid.uuid4(), node=node)
    )
    return beat


@pytest.mark.parametrize("field", sorted(
    f for f in _NodeCreateArgs.model_fields if f not in _NOT_SCENE_INTENT
))
def test_every_authored_intent_field_is_carried_by_the_lens(field):
    """The lens is where the loss happened: it copied five keys out of a node that had
    thirteen, so the renderer downstream never had the chance."""
    node = {field: "x" if field not in ("value_shift", "tension") else 7}
    beat = _beat_from(node)
    assert field in beat, (
        f"`{field}` is an authored scene field the create tool accepts, and the beat lens "
        "drops it — so the author fills it and the drafter never sees it. Add it to the "
        "beat dict in `gather_structural`, or to _NOT_SCENE_INTENT with the reason it is "
        "not scene intent."
    )


def _rendered_beat(beat: dict, present: list[dict] | None = None) -> str:
    """Render through the REAL LensBundle. A hand-rolled stub would drift from the
    dataclass and start failing for its own reasons, which is not what this is testing."""
    from app.packer.lenses import LensBundle

    segs = build_segments(LensBundle(beat=beat, present=present or []))
    return " ".join(s.text for s in segs if s.block == "beat")


class TestTheBeatBlockRendersTheIntent:
    """The second half of the path: carried by the lens AND rendered into the prompt."""

    def test_the_dramatic_shape_is_rendered(self):
        """conflict/stakes/outcome are what make a scene a scene — a goal and a synopsis
        alone describe a summary, not a dramatic unit."""
        out = _rendered_beat({
            "goal": "G", "conflict": "kẻ thù còn thở", "stakes": "danh dự Lâm gia",
            "outcome": "chàng tha mạng",
        })
        assert "conflict=kẻ thù còn thở" in out
        assert "stakes=danh dự Lâm gia" in out
        assert "outcome=chàng tha mạng" in out

    def test_a_zero_tension_or_shift_is_still_rendered(self):
        """0 is MEANINGFUL — a deliberately flat beat, or no net emotional change. A
        falsiness test would drop exactly the value an author chose on purpose."""
        out = _rendered_beat({"tension": 0, "value_shift": 0})
        assert "tension=0/100" in out
        assert "value_shift=0" in out

    def test_an_unfilled_field_stays_quiet(self):
        """An outline in progress must not pad the prompt with empty labels."""
        out = _rendered_beat({"goal": "G"})
        assert "conflict=" not in out
        assert "stakes=" not in out
        assert "tension=" not in out

    def test_the_exit_state_envelope_renders_its_content_not_its_version(self):
        out = _rendered_beat({"exit_state": {"v": 1, "mood": "lạnh", "open": "ai đang đếm"}})
        assert "mood=lạnh" in out and "open=ai đang đếm" in out
        assert "v=1" not in out


def test_the_operation_instruction_tells_the_model_what_each_field_is_FOR():
    """Sending a field is half the job. A label with no job attached gets skimmed — the
    instruction used to name exactly the four fields that were then being sent, which was
    honest at the time and starves the model now that all of them arrive."""
    from app.engine.cowrite import _OPERATION_INSTRUCTIONS

    text = _OPERATION_INSTRUCTIONS["draft_scene"]
    for field in ("conflict", "stakes", "outcome", "tension", "value_shift", "leaves"):
        assert field in text, f"draft_scene never tells the model what `{field}` is for"
