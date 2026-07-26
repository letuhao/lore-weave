"""Unit tests for the C25 packer override-merge (dị bản two-project assemble).

The packer, for a DERIVATIVE Work, must:
  • read BASE grounding from the SOURCE project_id, filtered `≤ branch_point`
    (the existing before_order / reading-order branch-filter), then
  • merge DELTA grounding from the DERIVATIVE's own project_id (full),
  • apply `entity_override[]` to the inherited base entities BEFORE the prompt
    window (re-read + re-applied every pack — NO stale cache, self-syncing),
  • delta entities/relations take PRECEDENCE on collision,
  • GUARD: a derivative pack asserts project-scoping (refuses a null/missing
    base or delta project_id — the cross-project leak C23's guard prevents),
  • base/delta entity IDENTITY is reconciled after normalizing the two
    partitions' name/anchor (the recurring cross-service normalization seam).

These tests use a PROJECT-AWARE knowledge stub so base and delta return
distinct data and the branch cutoff is observable per project.
"""

from __future__ import annotations

import uuid

import pytest

from app.db.models import EntityOverride
from app.engine.canon_check import EVENT_ORDER_CHAPTER_STRIDE
from app.packer.pack import PackRequest, pack
from app.grant_client import GrantLevel

from tests.unit.test_pack import (
    BOOK, CHAPTER, NODE, USER, StubBook, StubCanon, StubGlossary, StubGrant,
    StubOutline, StubSceneLinks, _wc,
)

SOURCE_PROJECT = uuid.uuid4()   # base partition (the source Work's project)
DELTA_PROJECT = uuid.uuid4()    # the derivative's own partition (delta)


class ProjectAwareKnowledge:
    """Returns DISTINCT timeline/lore/entity data per project_id, and records the
    `before_order` cutoff each project was queried with — so a test can assert the
    base was branch-capped while the delta read full. `present`/`semantic` is keyed
    by project too (base bios vs delta bios)."""

    def __init__(self, *, base_events=None, delta_events=None,
                 base_hits=None, delta_hits=None,
                 base_bios=None, delta_bios=None, entities=None):
        self.base_events = base_events or []
        self.delta_events = delta_events or []
        self.base_hits = base_hits or []
        self.delta_hits = delta_hits or []
        self.base_bios = base_bios or []
        self.delta_bios = delta_bios or []
        self._entities = entities or {}
        self.seen_before_order: dict[str, int | None] = {}

    def _is_base(self, project_id) -> bool:
        return str(project_id) == str(SOURCE_PROJECT)

    async def glossary_semantic(self, user_id, *, project_id, query, **kw):
        return self.base_bios if self._is_base(project_id) else self.delta_bios

    async def timeline(self, bearer, *, project_id, before_order=None, after_order=None, **kw):
        self.seen_before_order[str(project_id)] = before_order
        return self.base_events if self._is_base(project_id) else self.delta_events

    async def search_drawers(self, bearer, *, project_id, query, **kw):
        return self.base_hits if self._is_base(project_id) else self.delta_hits

    async def get_entity(self, bearer, entity_id):
        return self._entities.get(str(entity_id))


def _derivative_req(*, branch_point=3, story_order=5, overrides=None, settings=None,
                    source_project_id=SOURCE_PROJECT, project_id=DELTA_PROJECT,
                    pov_anchor=None, pov_entity_id=None):
    return PackRequest(
        user_id=USER, project_id=project_id, book_id=BOOK,
        node={"id": str(NODE), "chapter_id": str(CHAPTER), "story_order": story_order,
              "present_entity_ids": [], "pov_entity_id": pov_entity_id, "beat_role": "hook",
              "goal": "rescue", "synopsis": "the escape", "title": "Ch5"},
        bearer="jwt", guide="", settings=settings or {},
        source_project_id=source_project_id, branch_point=branch_point,
        overrides=overrides, pov_anchor=pov_anchor,
    )


async def _pack_deriv(req, *, knowledge, book=None, glossary=None):
    bk = book or StubBook(sort_map={str(CHAPTER): 5})
    return await pack(
        req, book=bk, glossary=glossary or StubGlossary(bios=[]),
        knowledge=knowledge, canon_repo=StubCanon(),
        outline_repo=StubOutline(), scene_links_repo=StubSceneLinks(),
        budget_tokens=10_000, counter=_wc,
        grant=StubGrant(GrantLevel.OWNER),
    )


def _event(title, order):
    return {"title": title, "summary": f"{title} happened", "event_order": order}


def _bio(entity_id, name, desc):
    return {"entity_id": entity_id, "cached_name": name, "short_description": desc}


# ── DPS1: two-project base+delta merge + branch-filter + GUARD ──


async def test_base_read_capped_at_branch_point():
    # branch_point=3 < scene chapter sort=5 → the BASE (source project) timeline is
    # queried with before_order = 3×stride (the branch cutoff), NOT 5×stride.
    kn = ProjectAwareKnowledge(base_events=[_event("base ev", 1 * EVENT_ORDER_CHAPTER_STRIDE)])
    await _pack_deriv(_derivative_req(branch_point=3, story_order=5), knowledge=kn)
    assert kn.seen_before_order[str(SOURCE_PROJECT)] == 3 * EVENT_ORDER_CHAPTER_STRIDE
    # The DELTA (derivative project) reads at the full scene cutoff (5×stride).
    assert kn.seen_before_order[str(DELTA_PROJECT)] == 5 * EVENT_ORDER_CHAPTER_STRIDE


async def test_base_does_not_leak_content_after_branch_point():
    # A base event at order 4×stride is AFTER branch_point=3 → must be excluded from
    # the base contribution (the source query is capped at the branch cutoff, and the
    # spoiler re-filter drops anything ≥ cutoff). An event ≤ branch survives.
    kn = ProjectAwareKnowledge(
        base_events=[
            _event("pre-branch", 2 * EVENT_ORDER_CHAPTER_STRIDE),
            _event("post-branch", 4 * EVENT_ORDER_CHAPTER_STRIDE),
        ],
    )
    pc = await _pack_deriv(_derivative_req(branch_point=3, story_order=5), knowledge=kn)
    assert "pre-branch" in pc.prompt
    assert "post-branch" not in pc.prompt


async def test_base_and_delta_both_merged():
    # Non-colliding base + delta entities BOTH appear (the two-project merge unions).
    kn = ProjectAwareKnowledge(
        base_bios=[_bio("g-base", "Kael", "a knight of the source canon")],
        delta_bios=[_bio("g-delta", "Mira", "a delta-only character")],
    )
    pc = await _pack_deriv(_derivative_req(), knowledge=kn)
    assert "Kael" in pc.prompt        # inherited base entity
    assert "Mira" in pc.prompt        # delta-only entity


async def test_delta_precedence_on_entity_collision():
    # NOTE: this stub returns PROJECT-DISTINCT bios; the REAL glossary `present` lens
    # is BOOK-scoped, so base and delta return the SAME bio for a shared entity and
    # this precedence is a no-op for bios in production — the entity's genuine
    # divergence flows through the OVERRIDE layer (applied after the merge), not the
    # base/delta bio merge. The merge precedence still matters for project-scoped
    # lenses (timeline/lore) and for a future project-scoped present source.
    # Same anchor id in both partitions → DELTA wins (the derivative's version of
    # the entity overrides the inherited base one).
    kn = ProjectAwareKnowledge(
        base_bios=[_bio("g-1", "Zhang", "the original male protagonist")],
        delta_bios=[_bio("g-1", "Zhang", "now reimagined in the delta")],
    )
    pc = await _pack_deriv(_derivative_req(), knowledge=kn)
    assert "now reimagined in the delta" in pc.prompt
    assert "the original male protagonist" not in pc.prompt


async def test_delta_timeline_precedence_on_collision():
    # A delta event with the same title at the same order shadows the base event.
    kn = ProjectAwareKnowledge(
        base_events=[{"title": "Duel", "summary": "base duel", "event_order": 1 * EVENT_ORDER_CHAPTER_STRIDE}],
        delta_events=[{"title": "Duel", "summary": "delta duel", "event_order": 1 * EVENT_ORDER_CHAPTER_STRIDE}],
    )
    pc = await _pack_deriv(_derivative_req(), knowledge=kn)
    assert "delta duel" in pc.prompt
    assert "base duel" not in pc.prompt


async def test_guard_refuses_derivative_with_null_source_project():
    # GUARD: a derivative pack (branch_point set) with a null SOURCE project_id is
    # refused — the cross-project leak C23's NOT-NULL guard exists for.
    kn = ProjectAwareKnowledge()
    with pytest.raises(ValueError, match="derivative"):
        await _pack_deriv(
            _derivative_req(source_project_id=None, branch_point=3), knowledge=kn)


async def test_guard_refuses_derivative_with_null_delta_project():
    # A derivative whose OWN (delta) project_id is null must also be refused — it
    # would widen the delta read cross-project. (project_id=None routes to the C16
    # null path; the derivative branch must guard BEFORE that degrades grounding.)
    kn = ProjectAwareKnowledge()
    with pytest.raises(ValueError, match="derivative"):
        await _pack_deriv(
            _derivative_req(project_id=None, source_project_id=SOURCE_PROJECT, branch_point=3),
            knowledge=kn)


async def test_base_delta_entity_identity_reconciled_by_anchor():
    # base + delta both carry the SAME glossary anchor id → reconcile to ONE entity
    # (delta precedence), NOT a duplicate. This is the present-entity identity axis:
    # both partitions anchor to the same glossary, so the stable anchor id is the
    # reconciliation key (gather_present drops anchorless items upstream).
    kn = ProjectAwareKnowledge(
        base_bios=[_bio("g-shared", "Kael", "base description")],
        delta_bios=[_bio("g-shared", "Kael", "delta description")],
    )
    pc = await _pack_deriv(_derivative_req(), knowledge=kn)
    assert "delta description" in pc.prompt
    assert "base description" not in pc.prompt
    # exactly one Kael present line (no duplicate from the un-reconciled base).
    assert pc.prompt.count("Kael") == 1


async def test_base_delta_timeline_identity_reconciled_by_normalized_title():
    # The timeline merge reconciles events by (title, event_order) AFTER normalizing
    # the title's case/whitespace — a base "The Duel " vs a delta "the duel" at the
    # same order must fold to ONE (delta wins), not duplicate. This is the recurring
    # cross-service normalization seam on the event axis.
    kn = ProjectAwareKnowledge(
        base_events=[{"title": "The Duel ", "summary": "base duel", "event_order": 1 * EVENT_ORDER_CHAPTER_STRIDE}],
        delta_events=[{"title": "the duel", "summary": "delta duel", "event_order": 1 * EVENT_ORDER_CHAPTER_STRIDE}],
    )
    pc = await _pack_deriv(_derivative_req(), knowledge=kn)
    assert "delta duel" in pc.prompt
    assert "base duel" not in pc.prompt


# ── C27 (dị bản M4): the delta flywheel CLOSES — the next pack reads a fact the
#     flywheel wrote into the derivative's delta partition (reconcile-by-truth:
#     assert via the packer's OWN delta-read path, not a parallel query) ──


async def test_flywheel_new_delta_fact_surfaces_in_next_scene_grounding():
    # SCENARIO: a derivative chapter was approved → the flywheel extracted a NEW fact
    # into the derivative's OWN delta partition. Modeled here as a fresh delta
    # timeline event present ONLY in the delta project (not the base). The NEXT
    # scene's pack must surface that delta fact in grounding — proving the flywheel
    # closes. Reconcile-by-truth: we read it through the SAME packer delta path C25
    # uses (the delta project's timeline lens), not an independent query.
    new_delta_fact = {
        "title": "张若尘 declares herself empress",
        "summary": "a delta-only event the dị bản established",
        "event_order": 4 * EVENT_ORDER_CHAPTER_STRIDE,  # forward of branch 3, ≤ scene 5
    }
    kn = ProjectAwareKnowledge(
        base_events=[_event("base-only event", 1 * EVENT_ORDER_CHAPTER_STRIDE)],
        delta_events=[new_delta_fact],
    )
    pc = await _pack_deriv(_derivative_req(branch_point=3, story_order=5), knowledge=kn)
    # The flywheel-written delta fact is now in the next scene's grounding.
    assert "declares herself empress" in pc.prompt
    # And it came from the DELTA partition's read (the derivative's own project) —
    # the packer queried the delta project at the full scene cutoff.
    assert kn.seen_before_order[str(DELTA_PROJECT)] == 5 * EVENT_ORDER_CHAPTER_STRIDE


async def test_flywheel_delta_fact_after_scene_position_is_spoiler_filtered():
    # A delta fact written FORWARD of the current scene (a later derivative chapter)
    # must NOT leak into an earlier scene's grounding — the in-world spoiler filter
    # still applies on the delta read, so the flywheel can't time-travel facts back.
    kn = ProjectAwareKnowledge(
        delta_events=[
            {"title": "near delta fact", "summary": "at scene", "event_order": 4 * EVENT_ORDER_CHAPTER_STRIDE},
            {"title": "future delta fact", "summary": "later chapter", "event_order": 9 * EVENT_ORDER_CHAPTER_STRIDE},
        ],
    )
    pc = await _pack_deriv(_derivative_req(branch_point=3, story_order=5), knowledge=kn)
    assert "near delta fact" in pc.prompt
    assert "future delta fact" not in pc.prompt


# ── DPS2: override mutation seam (self-syncing, re-applied every pack) ──


def _override(target_entity_id, fields):
    return EntityOverride(
        created_by=USER, project_id=DELTA_PROJECT, work_id=DELTA_PROJECT,
        target_entity_id=target_entity_id, overridden_fields=fields,
    )


async def test_override_mutates_inherited_entity_field_before_prompt():
    # An entity-field override on an INHERITED base entity mutates its summary
    # BEFORE it reaches the prompt window.
    ent_id = uuid.uuid4()
    kn = ProjectAwareKnowledge(
        base_bios=[_bio(str(ent_id), "Zhang", "a young man")],
    )
    ov = [_override(ent_id, {"summary": "now a woman (genderbend)"})]
    pc = await _pack_deriv(_derivative_req(overrides=ov), knowledge=kn)
    assert "now a woman (genderbend)" in pc.prompt
    assert "a young man" not in pc.prompt


async def test_override_description_alias_maps_to_summary():
    # Field-name normalization seam: the C24 wizard authors the override as
    # `description`, but the present-item bio field is `summary` (← glossary
    # short_description). The override must still apply (no silent field-name drop).
    ent_id = uuid.uuid4()
    kn = ProjectAwareKnowledge(base_bios=[_bio(str(ent_id), "Zhang", "a young man")])
    ov = [_override(ent_id, {"description": "now a woman (genderbend)"})]
    pc = await _pack_deriv(_derivative_req(overrides=ov), knowledge=kn)
    assert "now a woman (genderbend)" in pc.prompt
    assert "a young man" not in pc.prompt


async def test_override_name_field_applied():
    ent_id = uuid.uuid4()
    kn = ProjectAwareKnowledge(base_bios=[_bio(str(ent_id), "Zhang", "the hero")])
    ov = [_override(ent_id, {"name": "Zhang (she)"})]
    pc = await _pack_deriv(_derivative_req(overrides=ov), knowledge=kn)
    assert "Zhang (she)" in pc.prompt


async def test_override_canon_rule_scope_appended_to_canon_block():
    # The M0 override scope includes ADDED canon-rule text — it must reach the
    # <canon> block of the prompt.
    ent_id = uuid.uuid4()
    kn = ProjectAwareKnowledge(base_bios=[_bio(str(ent_id), "Zhang", "the hero")])
    ov = [_override(ent_id, {"canon_rule": "Zhang is addressed as 'she' throughout"})]
    pc = await _pack_deriv(_derivative_req(overrides=ov), knowledge=kn)
    assert "Zhang is addressed as 'she' throughout" in pc.prompt
    assert "<canon>" in pc.prompt


async def test_override_reapplied_every_pack_no_stale_cache():
    # Self-syncing: an EDITED override set takes effect on the NEXT pack (no cache).
    ent_id = uuid.uuid4()
    kn = ProjectAwareKnowledge(base_bios=[_bio(str(ent_id), "Zhang", "a young man")])
    pc1 = await _pack_deriv(
        _derivative_req(overrides=[_override(ent_id, {"summary": "v1 override"})]),
        knowledge=kn)
    assert "v1 override" in pc1.prompt
    # The author edits the override → next pack reflects the new value, not v1.
    pc2 = await _pack_deriv(
        _derivative_req(overrides=[_override(ent_id, {"summary": "v2 edited"})]),
        knowledge=kn)
    assert "v2 edited" in pc2.prompt
    assert "v1 override" not in pc2.prompt


async def test_override_targets_only_matching_entity():
    # An override whose target doesn't match any inherited entity leaves the others
    # untouched (no accidental mutation).
    ent_a, ent_b = uuid.uuid4(), uuid.uuid4()
    kn = ProjectAwareKnowledge(
        base_bios=[_bio(str(ent_a), "Kael", "untouched knight")],
    )
    ov = [_override(ent_b, {"summary": "should not apply"})]
    pc = await _pack_deriv(_derivative_req(overrides=ov), knowledge=kn)
    assert "untouched knight" in pc.prompt
    assert "should not apply" not in pc.prompt


async def test_build_derivative_context_resolves_base_via_source_id_not_project():
    # REGRESSION (live-smoke caught): a source Work's surrogate `id` is NOT
    # necessarily its project_id — build_derivative_context MUST look the source up
    # by id and use the source's project_id as the base, not reuse source_work_id
    # as a project_id directly (which would point the base read at the wrong / a
    # non-existent partition).
    from types import SimpleNamespace
    from app.packer.pack import build_derivative_context

    source_id = uuid.uuid4()
    source_project = uuid.uuid4()   # DISTINCT from the source's id
    work = SimpleNamespace(
        id=DELTA_PROJECT, source_work_id=source_id, branch_point=3,
    )

    class WR:
        async def get_by_id(self, work_id):
            assert str(work_id) == str(source_id)  # looked up by id, not project
            return SimpleNamespace(project_id=source_project)

    class DR:
        async def list_overrides_for_work(self, work_id):
            return []

    ctx = await build_derivative_context(
        work, works_repo=WR(), derivatives_repo=DR())
    assert ctx.source_project_id == source_project  # the source's PROJECT, not its id
    assert ctx.branch_point == 3


async def test_build_derivative_context_empty_for_non_derivative():
    from types import SimpleNamespace
    from app.packer.pack import build_derivative_context
    work = SimpleNamespace(id=DELTA_PROJECT, source_work_id=None, branch_point=None)
    ctx = await build_derivative_context(
        work, works_repo=object(), derivatives_repo=object())
    assert ctx.source_project_id is None
    assert ctx.overrides == []
    assert ctx.pov_anchor is None


# ── Part A (2026-07-18 spec) — POV-shift derivative: pov_anchor default-fill + render ──


async def test_build_derivative_context_reads_pov_anchor_from_spec():
    """Part A — build_derivative_context surfaces the divergence spec's pov_anchor
    (read fresh, self-syncing) so the pack path can default-fill the POV."""
    from types import SimpleNamespace
    from app.packer.pack import build_derivative_context
    source_id, source_project, anchor = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    work = SimpleNamespace(id=DELTA_PROJECT, source_work_id=source_id, branch_point=3)

    class WR:
        async def get_by_id(self, work_id):
            return SimpleNamespace(project_id=source_project)

    class DR:
        async def list_overrides_for_work(self, work_id):
            return []
        async def get_spec_for_work(self, work_id):
            return SimpleNamespace(pov_anchor=anchor)

    ctx = await build_derivative_context(work, works_repo=WR(), derivatives_repo=DR())
    assert ctx.pov_anchor == anchor


async def test_pov_anchor_default_fills_and_renders_explicit_pov():
    """Part A (PO-1 default-fill + PO-2 explicit render + PO-3 apply-when-set) — a
    derivative with pov_anchor=Kai and a scene that sets NO pov_entity_id → the beat
    renders `pov=Kai` (name resolved from the present set) and Kai's bio grounds."""
    kai = uuid.uuid4()
    kn = ProjectAwareKnowledge(base_bios=[_bio(str(kai), "Kai", "the rescued prisoner")])
    pc = await _pack_deriv(_derivative_req(pov_anchor=kai), knowledge=kn)
    assert "pov=Kai" in pc.prompt          # explicit POV steer (proves default-fill + render)
    assert "the rescued prisoner" in pc.prompt  # the POV character's bio grounds


async def test_scene_pov_wins_over_anchor():
    """PO-1 default-fill: a scene that sets its OWN pov_entity_id keeps it; the anchor
    only fills where the scene set none."""
    kai, lena = uuid.uuid4(), uuid.uuid4()
    kn = ProjectAwareKnowledge(base_bios=[
        _bio(str(lena), "Lena", "the guard"), _bio(str(kai), "Kai", "prisoner")])
    pc = await _pack_deriv(
        _derivative_req(pov_anchor=kai, pov_entity_id=str(lena)), knowledge=kn)
    assert "pov=Lena" in pc.prompt   # scene POV wins
    assert "pov=Kai" not in pc.prompt


async def test_no_pov_line_when_anchor_unset_regression():
    """A derivative with NO pov_anchor (and a scene with no POV) renders NO pov line —
    the pack is unchanged from pre-Part-A behaviour."""
    kn = ProjectAwareKnowledge(base_bios=[_bio(str(uuid.uuid4()), "Someone", "a bystander")])
    pc = await _pack_deriv(_derivative_req(pov_anchor=None), knowledge=kn)
    assert "pov=" not in pc.prompt


async def test_foreign_anchor_not_in_present_renders_no_pov_line():
    """Book-scope safety (spec B.2): a pov_anchor that resolves to NO present item
    (a foreign / book-scope-missed anchor) renders no pov line — no leak, no crash."""
    stranger = uuid.uuid4()  # not in any bio → never surfaces in present
    kn = ProjectAwareKnowledge(base_bios=[_bio(str(uuid.uuid4()), "Local", "in-book")])
    pc = await _pack_deriv(_derivative_req(pov_anchor=stranger), knowledge=kn)
    assert "pov=" not in pc.prompt


async def test_non_derivative_pack_unchanged_no_base_merge():
    # A NON-derivative Work (source_project_id=None) takes the normal single-project
    # path — knowledge is queried once at the delta project, no base merge, no guard.
    kn = ProjectAwareKnowledge(delta_bios=[_bio("g-d", "Solo", "single-project entity")])
    req = _derivative_req(source_project_id=None, branch_point=None)
    pc = await _pack_deriv(req, knowledge=kn)
    assert "Solo" in pc.prompt
    # base partition never queried.
    assert str(SOURCE_PROJECT) not in kn.seen_before_order
