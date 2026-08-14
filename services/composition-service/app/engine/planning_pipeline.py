"""Planning pipeline · Stage 6 — `run_planning_pipeline` (orchestration).

Chains the multi-step planner the one-shot decompose replaced (spec
`docs/specs/2026-06-30-planning-pipeline-architecture.md`):

  0. propose_cast → seed glossary → roster (entity-ids)   [cast]
  1. select_arc_motifs                                     [theme]
  L1. beat map (ONCE — its result feeds both 3 and 4)
  2. shape_tension_curve (inside grounded_decompose)       [pacing]
  3. plan_character_arcs (cast + beats)                    [arcs + intro schedule]
  4. grounded_decompose (cast + motifs + tension + intros) [grounded scenes]
  5. run_plan_self_heal (optional)                         [polish]

Each stage is independently degrade-safe (returns empty / unchanged on failure), so the
pipeline never hard-fails: a missing stage just thins the grounding. Human checkpoints
are the caller's concern — this returns the full intermediate result (cast / motifs /
arcs / heal report) so a UI can present + edit between stages; run it stage-by-stage for
a blocking checkpoint, or end-to-end (here) for the autonomous path.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from app.clients.llm_client import LLMClient
from app.engine.cast_plan import cast_attributes, propose_cast
from app.engine.character_plan import plan_character_arcs
from app.engine.grounded_plan import grounded_decompose
from app.engine.heal_canon import canon_from_proposed, convention_for
from app.engine.motif_plan import select_arc_motifs
from app.engine.plan import (
    ChapterPlan, DecomposeResult, _llm_json,
    build_chapter_map_messages, parse_chapter_map,
)
from app.engine.plan_heal import PlanHealReport, run_plan_self_heal
from app.llm_budget import max_tokens_for

logger = logging.getLogger(__name__)

#: The KG reading axis. **NOT** composition's own `STORY_ORDER_CHAPTER_STRIDE` (1 000), which
#: orders the outline. Same constant and same reason as `routers/canon.py`: a role written on
#: the wrong scale lands 1000x too early, every as-of read at the real position misses it, and
#: the canon check reports a character with no ties rather than a bad write.
KG_EVENT_ORDER_CHAPTER_STRIDE = 1_000_000


async def publish_planned_roles(
    kal, book_id, *, cast_objs, id_by_name: dict[str, str],
    introduce_at: dict[str, int | None], user_id,
) -> int:
    """T37 — write the roles the PLAN implies as `fact_kind='relation'` facts. Returns the
    count written.

    SPEC §4.2b gave roles two producers; this is the plan-time one. It runs AFTER Stage 3
    because of what Stage 3 knows: **a role cannot be in force before its holder appears on
    the page.** `introduce_at_chapter` is the character-arc stage's answer to exactly that,
    already clamped to `[1, n_chapters]`, so the role opens where the character does. An
    existing character has no introduction and opens at chapter 1.

    NEVER RAISES, and that is the opposite of `KalClient.append_role_fact`'s own convention —
    deliberately, because the callers differ. The studio endpoint raises so an author learns
    their declaration did not land. Here the caller is a planning pipeline whose every stage
    *"degrades independently"*: a KAL hiccup must not cost the user the plan they just waited
    for. A missing role is a thinner canon check; a lost plan is the run.

    Subjects are resolved through `id_by_name` — the roster read back AFTER seeding — so a
    role about a character the glossary did not accept is dropped rather than written against
    a guessed id. The OBJECT stays a NAME, matching `AppendFactRequest.value`: the KG's own
    relation facts are subject-id + predicate + string, and resolving the object here would
    invent an identity claim the plan did not make.
    """
    written = 0
    for c in cast_objs:
        subject_id = id_by_name.get(c.name)
        if not subject_id or not getattr(c, "roles", None):
            continue
        chapter = introduce_at.get(c.name) or 1
        ordinal = max(1, int(chapter)) * KG_EVENT_ORDER_CHAPTER_STRIDE
        for role in c.roles:
            try:
                await kal.append_role_fact(
                    book_id, subject_entity_id=subject_id,
                    predicate=role["predicate"], object_value=role["object"],
                    valid_from_ordinal=ordinal, user_id=user_id,
                    # T37c — marked as the PLAN's, so a later revision can close what it no
                    # longer implies without touching a role the author declared by hand.
                    origin="plan",
                )
                written += 1
            except Exception:  # noqa: BLE001 — see the docstring; the plan outranks the role
                logger.warning(
                    "T37: planned role not written subject=%s predicate=%s",
                    c.name, role.get("predicate"), exc_info=True,
                )
    if written:
        logger.info("T37: %d planned role(s) written as relation facts", written)
    return written


#: The producer mark this pipeline writes and — critically — the ONLY one it will close.
#: A constant rather than a literal at each site: a role written under one spelling and
#: searched for under another is un-retractable in a way nothing reports.
PLAN_FACT_ORIGIN = "plan"


async def close_stale_planned_roles(
    kal, book_id, *, cast_objs, id_by_name: dict[str, str],
    introduce_at: dict[str, int | None], user_id,
) -> int:
    """T37d — a plan REVISION closes the roles it no longer implies. Returns the count closed.

    §4.2b named this the plan-time producer's debt: a role appended when a plan was designed
    outlives the plan that justified it, and an as-of read would then hand the canon guard a
    tie the book abandoned — the same *stale but confidently served* failure T36 found in the
    175 already-closed `:RELATES_TO` edges.

    ⚠️ **IT CLOSES ONLY `origin='plan'`, AND THAT IS THE WHOLE SAFETY PROPERTY.** Roles have
    two producers (SPEC §4.2b). An author's hand-declared tie is not the plan's to remove, and
    before chain step 0066 nothing in `entity_facts` could tell them apart — both were
    `fact_kind='relation'` with a NULL episode. A close without that mark would have silently
    erased what a human deliberately said. **A stale role is wrong; an erased one is gone.**
    A fact with NO origin (anything older than 0066) is likewise never touched: unmarked means
    unclaimed, and this producer only retracts what it can prove it wrote.

    CLOSED, not deleted or invalidated. The fact stays true for the interval it covered, so a
    chapter drafted under the old plan still sees the role that was in force when it was
    written. Deleting would rewrite history; invalidating would say the claim was never
    believed. Neither is what a revision means.

    Never raises, for the same reason `publish_planned_roles` does not: this runs inside a
    pipeline whose every stage degrades independently. A close that cannot see the current
    state does NOTHING — `open_facts_for` returns `[]` on failure, so a read timeout retracts
    nothing rather than everything.
    """
    wanted: set[tuple[str, str, str]] = {
        (id_by_name[c.name], r["predicate"], r["object"])
        for c in cast_objs if c.name in id_by_name
        for r in (getattr(c, "roles", None) or [])
    }
    closed = 0
    for name, entity_id in id_by_name.items():
        for fact in await kal.open_facts_for(book_id, entity_id, user_id=user_id):
            if fact.get("fact_kind") != "relation":
                continue
            if fact.get("origin") != PLAN_FACT_ORIGIN:
                continue  # the author's, or unmarked — not this producer's to retract
            key = (entity_id, fact.get("attr_or_predicate") or "", fact.get("value") or "")
            if key in wanted:
                continue  # the revised plan still implies it
            # Closed AT the holder's current position: the role held up to here, and stops
            # being in force from the chapter this revision places them at.
            chapter = introduce_at.get(name) or 1
            ordinal = max(1, int(chapter)) * KG_EVENT_ORDER_CHAPTER_STRIDE
            try:
                await kal.close_fact(book_id, fact_id=fact["fact_id"],
                                     valid_to_ordinal=ordinal, user_id=user_id)
                closed += 1
            except Exception:  # noqa: BLE001 — the plan outranks the retraction
                logger.warning("T37d: stale planned role not closed fact=%s",
                               fact.get("fact_id"), exc_info=True)
    if closed:
        logger.info("T37d: %d planned role(s) closed by this revision", closed)
    return closed


@dataclass
class PipelineResult:
    decompose: DecomposeResult
    cast: list[dict[str, Any]] = field(default_factory=list)        # {name, role, is_new}
    motifs: list[dict[str, str]] = field(default_factory=list)      # {name, arc_role}
    char_arcs: list[dict[str, Any]] = field(default_factory=list)   # {name, introduce_at_chapter}
    heal_report: PlanHealReport | None = None
    canon: str = ""   # story bible (convention + per-character canon) for grounding self-heal


async def run_planning_pipeline(
    llm: LLMClient, retriever: Any, glossary: Any, kal: Any, *,
    user_id: str, book_id: UUID, project_id: UUID,
    premise: str, beats: list[dict[str, Any]], chapters: list[ChapterPlan],
    genre_tags: list[str], model_source: str, model_ref: str,
    k_ceiling: int, high_threshold: int, min_scenes: int, max_scenes: int,
    source_language: str = "auto", self_heal: bool = True,
    seed_cast: bool = True, trace_id: str | None = None,
    cancel_check: Callable[[], Awaitable[bool]] | None = None,
) -> PipelineResult:
    """Run the full multi-step planning pipeline end-to-end. Returns the healed plan +
    all intermediate artifacts. Each stage degrades independently."""
    mk = dict(user_id=user_id, model_source=model_source, model_ref=model_ref,
              trace_id=trace_id, cancel_check=cancel_check)

    # ── Stage 0 — cast: propose → seed → roster (entity-ids), joined by name.
    cast_objs = await propose_cast(llm, premise=premise, source_language=source_language,
                                   genre_tags=genre_tags, **mk)
    cast_chars = [{"name": c.name, "role": c.role, "is_new": c.is_new} for c in cast_objs]
    # Build the self-heal CANON from the SAME designed cast that drafting grounds on, so a
    # later heal needs no hand-written bible (convention is genre/language-selected).
    canon = canon_from_proposed(
        cast_objs, convention=convention_for(genre_tags, source_language))
    if seed_cast and cast_objs:
        # D-PLAN-CAST-ATTRS — persist DEPTH (role/personality/relationships/description),
        # not just the name, so drafting can ground on the designed cast.
        await glossary.seed_entities(
            book_id, source_language=source_language,
            entities=[{"kind_code": "character", "name": c.name, "attributes": cast_attributes(c)}
                      for c in cast_objs])
    roster = await kal.roster(book_id, user_id=UUID(str(user_id)))
    id_by_name = {e["name"]: e["entity_id"] for e in roster if e.get("name") and e.get("entity_id")}
    cast_decompose = [{"entity_id": id_by_name[c.name], "name": c.name}
                      for c in cast_objs if c.name in id_by_name]

    # ── Stage 1 — theme/motifs.
    motifs_sel = await select_arc_motifs(llm, retriever, book_id=book_id, project_id=project_id,
                                         premise=premise, genre_tags=genre_tags,
                                         source_language=source_language, **mk)
    motifs = [{"name": m.name, "arc_role": m.arc_role, "code": m.code} for m in motifs_sel]

    # ── L1 — beat map ONCE (feeds Stage 3 + Stage 4). Degrade → beat_role=None.
    mapped = chapters
    sys1, usr1 = build_chapter_map_messages(premise, beats, chapters, source_language)
    l1 = await _llm_json(llm, system=sys1, user=usr1,
                         max_tokens=max_tokens_for("chapter_beat_map", target=len(chapters)),
                         **mk)
    if l1 is not None:
        beat_keys = {b.get("key") for b in beats if isinstance(b.get("key"), str)}
        mapped, _ = parse_chapter_map(l1, chapters, beat_keys)
    beat_roles = [ch.beat_role for ch in mapped]

    # ── Stage 3 — character arcs + introduction schedule.
    arcs = await plan_character_arcs(llm, premise=premise, cast=cast_chars,
                                     beat_roles=beat_roles, source_language=source_language, **mk)
    arc_dicts = [{"name": a.name, "introduce_at_chapter": a.introduce_at_chapter} for a in arcs]

    # ── T37 — the plan-time role producer (SPEC §4.2b). HERE, not in Stage 0, because a role
    # cannot be in force before its holder appears and `introduce_at_chapter` is the answer
    # Stage 3 just computed. Degrades like every other stage: never raises.
    if seed_cast and cast_objs:
        _intro = {a.name: a.introduce_at_chapter for a in arcs}
        await publish_planned_roles(
            kal, book_id, cast_objs=cast_objs, id_by_name=id_by_name,
            introduce_at=_intro, user_id=UUID(str(user_id)),
        )
        # T37d — and CLOSE what this revision no longer implies. After the publish, not
        # before: the append is idempotent on its content key, so a role the new plan still
        # implies is already re-opened and will not be seen as stale. Closing first would
        # briefly leave a role the plan still wants marked as ended.
        await close_stale_planned_roles(
            kal, book_id, cast_objs=cast_objs, id_by_name=id_by_name,
            introduce_at=_intro, user_id=UUID(str(user_id)),
        )

    # ── Stage 4 — grounded decompose. skip_l1=True: L1 already ran ONCE above (its result
    # fed Stage 3's char arcs), so grounded reuses `mapped` as-is — even on an L1 degrade
    # (all-None) — instead of re-running and drifting the beats out of sync with the arcs.
    result = await grounded_decompose(
        llm, arc_title="Arc 1", premise=premise, beats=beats, chapters=mapped,
        cast=cast_decompose, motifs=motifs, char_arcs=arc_dicts, skip_l1=True,
        k_ceiling=k_ceiling, high_threshold=high_threshold,
        min_scenes=min_scenes, max_scenes=max_scenes, source_language=source_language, **mk)

    # ── Stage 5 — plan self-heal (optional).
    heal_report: PlanHealReport | None = None
    if self_heal:
        result, heal_report = await run_plan_self_heal(
            llm, result, source_language=source_language, **mk)

    return PipelineResult(decompose=result, cast=cast_chars, motifs=motifs,
                          char_arcs=arc_dicts, heal_report=heal_report, canon=canon)
