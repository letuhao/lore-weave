"""D-SCENE-BEATS — the scene's draft units (slice 1: the field).

Why the field exists, measured rather than assumed
--------------------------------------------------
9 live runs on throwaway books, targets 200→1500:

    gemma-26b   565 · 673 · 497 · 625 · 559 · 519 · 509 · 528 · 698
    gpt-4o      461      ← for a 1500 target, FEWER than the local model

A frontier model with enormous output capacity produced the SHORTEST draft in the set, every
run ending `finish_reason="stop"`. So it is neither a model ceiling nor disobedience: one
beat's material genuinely runs out around 500 words, and both models do exactly what the
prompt says — *"stop when THIS scene's beat has played out"*.

Authors set `target_words` to 750–900 (the Mị Đế values), ~1.7× what one beat carries, so
every scene lands ~60% and the shortfall compounds across a chapter. A scene reaches its
target by having ENOUGH BEATS, not by asking one beat to stretch.

This slice adds the field only — nothing drafts per beat yet — so the invariant that matters
here is that an EMPTY `beats` behaves exactly as today, because that is every existing scene.
"""
from __future__ import annotations

from app.db.models import OutlineNode
from app.db.repositories.outline import _row_to_node
from app.engine.cowrite import DEFAULT_SCENE_TARGET_WORDS, MEASURED_BEAT_YIELD_WORDS
from app.routers.outline import NodeCreate, NodePatch


def _row(**over):
    base = dict(
        id="00000000-0000-0000-0000-000000000001",
        project_id="00000000-0000-0000-0000-000000000002",
        book_id="00000000-0000-0000-0000-000000000003",
        created_by="00000000-0000-0000-0000-000000000004",
        kind="scene", rank="a0", title="t", version=1, is_archived=False,
    )
    base.update(over)
    return base


# ── the legacy scene must be untouched ────────────────────────────────────────────────────

def test_a_row_written_before_the_column_existed_reads_as_an_empty_list():
    """A NULL must mean "legacy single-beat scene", never crash the whole node read — the
    same `or {}` reasoning `intent_slots` already documents."""
    assert _row_to_node(_row(draft_beats=None)).draft_beats == []


def test_a_jsonb_string_is_decoded_not_passed_through():
    """This pool sets no jsonb codec, so asyncpg hands back a STRING. Without the decode the
    model gets a str where a list is declared — the trap `exit_state` already carries."""
    node = _row_to_node(_row(draft_beats='[{"goal": "arrive"}]'))
    assert node.draft_beats == [{"goal": "arrive"}]


def test_an_already_decoded_list_passes_through():
    assert _row_to_node(_row(draft_beats=[{"goal": "x"}])).draft_beats == [{"goal": "x"}]


def test_the_model_defaults_to_empty_so_every_existing_scene_is_unchanged():
    n = OutlineNode(**_row())
    assert n.draft_beats == []


# ── the REST mirror must not silently drop it ─────────────────────────────────────────────

def test_the_create_body_declares_beats():
    """Pydantic's extra='ignore' drops an undeclared key, so the repo accepting the column is
    NOT enough — the write no-ops. This model's own comment records the same bug happening to
    the SC4 fields, and it happened again here: verified live, a PATCH carrying `beats`
    round-tripped as [] until the field was declared."""
    assert "draft_beats" in NodeCreate.model_fields
    body = NodeCreate(kind="scene", draft_beats=[{"goal": "arrive"}])
    assert body.model_dump(exclude_unset=True)["draft_beats"] == [{"goal": "arrive"}]


def test_the_patch_body_declares_beats_and_omits_it_when_unset():
    assert "draft_beats" in NodePatch.model_fields
    assert "draft_beats" not in NodePatch(title="x").model_dump(exclude_unset=True)
    assert NodePatch(draft_beats=[]).model_dump(exclude_unset=True)["draft_beats"] == []


def test_the_repo_accepts_beats_as_an_updatable_column():
    from app.db.repositories.outline import _UPDATABLE_COLUMNS
    assert "draft_beats" in _UPDATABLE_COLUMNS


# ── the measured constant ─────────────────────────────────────────────────────────────────

def test_the_beat_yield_is_below_the_scene_default_which_is_the_whole_finding():
    """If these were equal there would be no gap to explain. The scene default (and the
    750-900 authors set) is ~1.5-2x what one beat delivers."""
    assert MEASURED_BEAT_YIELD_WORDS < DEFAULT_SCENE_TARGET_WORDS
    assert 400 <= MEASURED_BEAT_YIELD_WORDS <= 700, "outside the measured 461-698 range"


def test_a_scene_target_implies_more_than_one_beat_at_the_measured_yield():
    """The arithmetic the next slice is built on: an 800-word scene needs 2 beats, not 1."""
    import math
    for target in (750, 800, 850, 900):
        assert math.ceil(target / MEASURED_BEAT_YIELD_WORDS) >= 2


# ── the name must not collide with the OTHER two meanings of "beat" ───────────────────────

def test_the_field_is_not_called_bare_beats():
    """`OutlineNode.beat_role` is which STRUCTURAL beat this node is (motif retrieval reads
    it), and `StructureTemplate.beats` is that same structural sense. A third meaning — the
    units a scene is DRAFTED in — sharing the bare word on the very model carrying `beat_role`
    is the one-name-one-concept violation the contract rules exist to prevent."""
    assert "draft_beats" in OutlineNode.model_fields
    assert "beats" not in OutlineNode.model_fields
    assert "beat_role" in OutlineNode.model_fields, "the colliding neighbour still exists"


# ── bounded, like every comparable list in this service ───────────────────────────────────

def test_the_list_is_capped():
    """It reaches a PROMPT. Every comparable list here is bounded (MaxPlanOps=50,
    maxDocExtractCandidates=200); an unbounded one is a bloat and prompt-blowup vector."""
    import pytest
    from app.db.models import MAX_DRAFT_BEATS

    ok = _row(draft_beats=[{"goal": f"b{i}"} for i in range(MAX_DRAFT_BEATS)])
    assert len(OutlineNode(**ok).draft_beats) == MAX_DRAFT_BEATS
    with pytest.raises(Exception):
        OutlineNode(**_row(draft_beats=[{"goal": f"b{i}"} for i in range(MAX_DRAFT_BEATS + 1)]))


def test_the_cap_is_generous_enough_for_any_real_scene():
    """At the measured ~500 words/beat the cap is a 12,000-word scene — past anything an
    author writes, so hitting it is a mistake or an attack, not a long scene."""
    from app.db.models import MAX_DRAFT_BEATS
    assert MAX_DRAFT_BEATS * MEASURED_BEAT_YIELD_WORDS >= 10_000


# ── both front doors, not just one ────────────────────────────────────────────────────────

def test_the_mcp_surface_can_write_it_too():
    """CF-9 — a field the repo accepts but one front door cannot send is the "one repo method,
    two front doors" divergence. REST lagged MCP for the SC4 fields; this is that gap
    mirrored, and the AGENT is the primary writer of a beat decomposition."""
    import inspect

    import app.mcp.server as srv

    src = inspect.getsource(srv)
    assert src.count("draft_beats: list[dict[str, Any]] | None") == 2, \
        "the MCP scene create AND edit arg models must both declare it"
    assert "draft_beats=args.draft_beats" in src, "create does not forward it"
    assert '"draft_beats": args.draft_beats' in src, "edit does not forward it"
