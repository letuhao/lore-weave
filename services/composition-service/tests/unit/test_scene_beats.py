"""D-SCENE-BEATS — the scene's draft units (slice 1: the field).

Why the field exists — and the correction to why it was FIRST said to exist
---------------------------------------------------------------------------
It was introduced on this reading of 10 live runs (targets 200→1500):

    gemma-26b   565 · 673 · 497 · 625 · 559 · 519 · 509 · 528 · 698
    gpt-4o      461      ← for a 1500 target, FEWER than the local model

    "…neither a model ceiling nor disobedience: one beat's material genuinely runs out
    around 500 words, and both models do exactly what the prompt says."

**The runs were real; the reading was wrong.** Every one went through `select_draft`, which
had no `target_words` parameter, so the LENGTH directive never entered the prompt
(D-LENGTH-DIRECTIVE-NEVER-SENT — see `test_scene_beats_drafting.py`). Output uncorrelated
with an ask that was never sent says nothing about what a beat's material can carry. The
"~500 words per beat" ceiling, and the arithmetic that a 900-word scene therefore needs two
beats, were conclusions drawn from a broken measurement.

What survives is the CAPABILITY, on its own merits: an author who wants a scene written as
three consecutive passages, each with its own brief, can say so — and slice 2 drafts it that
way. Whether it is also the answer to short scenes is now an open question with the
confounder removed, not a settled one.

This slice adds the field only. The invariant that matters here is that an EMPTY list behaves
exactly as today, because that is every existing scene.
"""
from __future__ import annotations

from app.db.models import OutlineNode
from app.db.repositories.outline import _row_to_node
from app.engine.cowrite import DEFAULT_SCENE_TARGET_WORDS, MEASURED_UNDIRECTED_YIELD_WORDS
from app.routers.outline import NodeCreate, NodePatch


def _repo_root() -> str:
    import pathlib
    return str(pathlib.Path(__file__).resolve().parents[4])


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

def test_the_undirected_yield_is_recorded_as_what_it_actually_measured():
    """It stays in the range the 10 runs produced, and it stays BELOW the scene default —
    that gap is the size of the bug those runs were really showing.

    What this deliberately no longer asserts: that a scene therefore needs ≥2 beats. That
    arithmetic (`ceil(target / 500) >= 2`) was a real test here one commit ago, and it encoded
    a conclusion drawn from prompts that carried no length instruction."""
    assert MEASURED_UNDIRECTED_YIELD_WORDS < DEFAULT_SCENE_TARGET_WORDS
    assert 400 <= MEASURED_UNDIRECTED_YIELD_WORDS <= 700, "outside the measured 461-698 range"


def test_nothing_in_the_engine_computes_from_the_undirected_yield():
    """It is a historical datum, not a design input. `beat_targets` divides the SCENE's
    target; if this number ever starts governing behaviour, a stale measurement is steering
    the engine again."""
    import subprocess
    hits = subprocess.run(
        ["git", "grep", "-l", "MEASURED_UNDIRECTED_YIELD_WORDS", "--", "services/"],
        capture_output=True, text=True, cwd=_repo_root()).stdout.split()
    assert sorted(hits) == sorted([
        "services/composition-service/app/engine/cowrite.py",
        "services/composition-service/tests/unit/test_scene_beats.py",
        "services/composition-service/tests/unit/test_scene_beats_drafting.py",
    ]), f"a new consumer appeared: {hits}"


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
    """Even at a conservative few-hundred words per passage the cap is a five-figure scene —
    past anything an author writes, so hitting it is a mistake or an attack, not a long
    scene."""
    from app.db.models import MAX_DRAFT_BEATS
    assert MAX_DRAFT_BEATS * MEASURED_UNDIRECTED_YIELD_WORDS >= 10_000


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
