"""27 V2-C5 — the ARTIFACT-I/O ADAPTERS: the seven passes' engines, behind one signature.

The engines already exist and are already tested. C5 is explicit that this layer adds **no engine
rewrites** — each adapter only:

  1. reads the pass's inputs out of the resolved artifact bodies (by POINTER — `plan_pass_service`
     hands us exactly the artifacts the fingerprint was computed over, never a latest-by-kind
     lookup, which is the PF-3 rot);
  2. calls the engine that already knows how to do the work;
  3. returns the artifact body to store under the pass's `output_kind`.

Three rules the adapters must not break:

**Degrade-safe, never fabricate.** Every engine here already returns `[]` on an LLM/parse failure.
An adapter passes that emptiness through *as emptiness* — it never substitutes a plausible default.
An empty `cast_plan` means "the cast pass produced nothing", and the human checkpoint is where that
gets noticed. A fabricated cast is a plan that silently isn't the author's.

**Absent ≠ zero.** Where we could not even LOOK (no motif retriever), the artifact says so with
`degraded: True` + a warning, rather than shipping a `[]` that reads as "this book has no motifs".

**A blocking pass emits its artifact and STOPS.** `cast` and `beats` complete with
`decision:"pending"`; `plan_pass_service.assert_runnable` refuses to start the next pass until a
human resolves them. The adapter's job ends at the artifact — it does not decide.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from app.clients.llm_client import LLMClient
from app.db.models import PlanPassId

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PassContext:
    """Everything an adapter may read. Assembled once by the worker op."""

    llm: LLMClient
    user_id: str
    book_id: UUID
    project_id: UUID
    model_source: str
    model_ref: str
    #: The run's `planning_package` body (the compile output) — present iff the pass `reads_package`.
    package: dict[str, Any] = field(default_factory=dict)
    #: Resolved upstream artifact bodies, keyed by the PASS that produced them (not by kind — pass 7
    #: re-emits `scene_plan`, so kind is not a unique key; that is PF-3's whole point).
    inputs: dict[str, Any] = field(default_factory=dict)
    genre_tags: list[str] = field(default_factory=list)
    source_language: str = "auto"
    #: Per-pass knobs (k_ceiling, thresholds…). Fingerprinted WITH the pass, so changing one stales
    #: exactly that pass and everything downstream of it.
    params: dict[str, Any] = field(default_factory=dict)
    retriever: Any = None
    trace_id: str | None = None
    cancel_check: Callable[[], Awaitable[bool]] | None = None

    # ── package readers ──────────────────────────────────────────────────────────────────────
    # The package is the compile output; these are the only fields the passes read from it. Keeping
    # them in one place means a package-shape change breaks HERE, loudly, and not in seven adapters.

    @property
    def premise(self) -> str:
        return str(self.package.get("premise") or "")

    @property
    def arc_title(self) -> str:
        return str(self.package.get("arc_title") or "")

    @property
    def beats(self) -> list[dict[str, Any]]:
        b = self.package.get("beats")
        return b if isinstance(b, list) else []

    @property
    def chapters(self) -> list[dict[str, Any]]:
        c = self.package.get("chapters")
        return c if isinstance(c, list) else []


def _chapter_plans(ctx: PassContext, beat_roles: dict[int, str | None] | None = None) -> list[Any]:
    """The package's chapters as the engines' `ChapterPlan`, optionally carrying pass-4's roles.

    `chapter_id` is the plan's EVENT id, not a manuscript chapter's uuid — at plan time the
    manuscript chapter may not exist yet (the linker writes `outline_node.chapter_id = NULL`,
    "planned, not yet written"). The engines only ever use it as an opaque key.
    """
    from app.engine.plan import ChapterPlan

    out: list[ChapterPlan] = []
    for i, ch in enumerate(ctx.chapters, start=1):
        ordinal = int(ch.get("ordinal") or i)
        out.append(ChapterPlan(
            chapter_id=str(ch.get("event_id") or ordinal),
            title=str(ch.get("title") or ""),
            sort_order=ordinal,
            beat_role=(beat_roles or {}).get(ordinal),
            intent=str(ch.get("synopsis") or ch.get("intent") or ""),
        ))
    return out


# ── pass 1 · motifs ──────────────────────────────────────────────────────────────────────────────
async def run_motifs(ctx: PassContext) -> dict[str, Any]:
    from app.engine.motif_plan import select_arc_motifs

    if ctx.retriever is None:
        # Absent ≠ zero. No retriever means we could not even LOOK for motifs — which is not the
        # same as "this book has none", and a bare `[]` here would render as the latter forever.
        logger.warning("motifs pass: no motif retriever available → degraded")
        return {"motifs": [], "degraded": True,
                "warning": "the motif library was unreachable; no motifs were considered"}
    selected = await select_arc_motifs(
        ctx.llm, ctx.retriever, user_id=ctx.user_id, book_id=ctx.book_id,
        project_id=ctx.project_id, premise=ctx.premise, genre_tags=ctx.genre_tags,
        source_language=ctx.source_language, model_source=ctx.model_source,
        model_ref=ctx.model_ref,
        max_select=int(ctx.params.get("max_select", 4)),
        candidate_limit=int(ctx.params.get("candidate_limit", 15)),
        trace_id=ctx.trace_id, cancel_check=ctx.cancel_check,
    )
    return {"motifs": [
        {"code": m.code, "name": m.name, "summary": m.summary,
         "why": m.why, "arc_role": m.arc_role}
        for m in selected
    ]}


# ── pass 2 · cast (BLOCKING) ─────────────────────────────────────────────────────────────────────
async def run_cast(ctx: PassContext) -> dict[str, Any]:
    from app.engine.cast_plan import cast_attributes, propose_cast

    proposed = await propose_cast(
        ctx.llm, user_id=ctx.user_id, model_source=ctx.model_source, model_ref=ctx.model_ref,
        premise=ctx.premise, source_language=ctx.source_language, genre_tags=ctx.genre_tags,
        trace_id=ctx.trace_id, cancel_check=ctx.cancel_check,
    )
    return {"cast": [
        {"name": c.name, "role": c.role, "archetype": c.archetype, "summary": c.summary,
         "is_new": c.is_new, "attributes": cast_attributes(c)}
        for c in proposed
    ]}


# ── pass 3 · world ───────────────────────────────────────────────────────────────────────────────
async def run_world(ctx: PassContext) -> dict[str, Any]:
    from app.engine.world_plan import propose_world, world_attributes

    cast = _cast_of(ctx)
    proposed = await propose_world(
        ctx.llm, user_id=ctx.user_id, model_source=ctx.model_source, model_ref=ctx.model_ref,
        premise=ctx.premise, source_language=ctx.source_language, genre_tags=ctx.genre_tags,
        cast_names=[c["name"] for c in cast if c.get("name")],
        trace_id=ctx.trace_id, cancel_check=ctx.cancel_check,
    )
    return {"entities": [
        {"name": e.name, "kind": e.kind, "summary": e.summary, "is_new": e.is_new,
         "attributes": world_attributes(e)}
        for e in proposed
    ]}


# ── pass 4 · beats (BLOCKING) ────────────────────────────────────────────────────────────────────
async def run_beats(ctx: PassContext) -> dict[str, Any]:
    """The C4 hoist. Emits the beat map AND the tension curve, so a human can block on the story's
    SHAPE before pass 6 spends a per-chapter L2 call against a shape they were going to reject.

    Pass 6 reads the curve back and HONOURS it (`grounded_decompose(tension_curve=…)`) — recomputing
    it there would silently discard whatever the human edited at this checkpoint."""
    from app.engine.grounded_plan import map_beats_and_shape

    mapped, unmapped_beats, curve = await map_beats_and_shape(
        ctx.llm, user_id=ctx.user_id, model_source=ctx.model_source, model_ref=ctx.model_ref,
        premise=ctx.premise, beats=ctx.beats, chapters=_chapter_plans(ctx),
        source_language=ctx.source_language,
        trace_id=ctx.trace_id, cancel_check=ctx.cancel_check,
    )
    return {
        "chapters": [
            {"ordinal": ch.sort_order, "event_id": ch.chapter_id, "title": ch.title,
             "beat_role": ch.beat_role, "intent": ch.intent}
            for ch in mapped
        ],
        "tension_curve": [
            {"chapter_index": c.chapter_index, "beat_role": c.beat_role,
             "tension_target": c.tension_target}
            for c in curve
        ],
        # Surfaced, not swallowed: a beat the model could not place anywhere is a beat the story
        # will never hit. The human sees it AT the blocking checkpoint, which is the whole point.
        "unmapped_beats": list(unmapped_beats),
    }


# ── pass 5 · character_arcs ──────────────────────────────────────────────────────────────────────
async def run_character_arcs(ctx: PassContext) -> dict[str, Any]:
    from app.engine.character_plan import plan_character_arcs

    beat_chapters = ctx.inputs.get("beats", {}).get("chapters", [])
    arcs = await plan_character_arcs(
        ctx.llm, user_id=ctx.user_id, model_source=ctx.model_source, model_ref=ctx.model_ref,
        premise=ctx.premise, cast=_cast_of(ctx),
        beat_roles=[c.get("beat_role") for c in beat_chapters],
        source_language=ctx.source_language,
        trace_id=ctx.trace_id, cancel_check=ctx.cancel_check,
    )
    return {"character_arcs": [
        {"name": a.name, "role": a.role, "arc": a.arc,
         "introduce_at_chapter": a.introduce_at_chapter}
        for a in arcs
    ]}


# ── pass 6 · scenes ──────────────────────────────────────────────────────────────────────────────
async def run_scenes(ctx: PassContext) -> dict[str, Any]:
    from app.engine.arc_plan import ChapterTension
    from app.engine.grounded_plan import grounded_decompose

    motifs = ctx.inputs.get("motifs", {}).get("motifs", []) or []
    beats_art = ctx.inputs.get("beats", {}) or {}
    char_arcs = ctx.inputs.get("character_arcs", {}).get("character_arcs", []) or []

    roles = {
        int(c["ordinal"]): c.get("beat_role")
        for c in beats_art.get("chapters", []) or []
        if c.get("ordinal") is not None
    }
    # Pass 4's curve, honoured verbatim (V2-C4) — including any edit the human made at the blocking
    # checkpoint. Recomputing it from the roles would throw that edit away.
    curve = [
        ChapterTension(
            chapter_index=int(c["chapter_index"]),
            beat_role=c.get("beat_role"),
            tension_target=int(c["tension_target"]),
        )
        for c in beats_art.get("tension_curve", []) or []
        if c.get("chapter_index") is not None and c.get("tension_target") is not None
    ]
    result = await grounded_decompose(
        ctx.llm, user_id=ctx.user_id, model_source=ctx.model_source, model_ref=ctx.model_ref,
        premise=ctx.premise, arc_title=ctx.arc_title, beats=ctx.beats,
        chapters=_chapter_plans(ctx, roles), cast=_cast_of(ctx),
        motifs=[{"name": m.get("name", ""), "arc_role": m.get("arc_role", "")} for m in motifs],
        char_arcs=char_arcs,
        k_ceiling=int(ctx.params.get("k_ceiling", 3)),
        high_threshold=int(ctx.params.get("high_threshold", 70)),
        min_scenes=int(ctx.params.get("min_scenes", 2)),
        max_scenes=int(ctx.params.get("max_scenes", 5)),
        source_language=ctx.source_language,
        # L1 already ran, in pass 4. Re-running it here would drift the beats out of sync with the
        # intro schedule pass 5 planned against — and would re-spend the tokens pass 4 spent.
        skip_l1=True,
        tension_curve=curve or None,
        trace_id=ctx.trace_id, cancel_check=ctx.cancel_check,
    )
    return _decompose_to_artifact(result)


# ── pass 7 · self_heal ───────────────────────────────────────────────────────────────────────────
async def run_self_heal(ctx: PassContext) -> dict[str, Any]:
    """Emits a NEW `scene_plan` — which is exactly why inputs resolve by POINTER. Under a
    latest-by-kind rule this pass would read its own output as its input and stale itself against
    itself, forever (PF-3)."""
    from app.engine.plan_heal import run_plan_self_heal

    scenes_art = ctx.inputs.get("scenes", {}) or {}
    result = _artifact_to_decompose(scenes_art)
    if not result.chapters:
        # Nothing to heal is not a failure — but it is also not a silent success. Say so.
        return {**scenes_art,
                "heal": {"findings": [], "edits_applied": 0, "note": "no scenes to heal"}}
    healed, report = await run_plan_self_heal(
        ctx.llm, result, user_id=ctx.user_id, model_source=ctx.model_source,
        model_ref=ctx.model_ref, source_language=ctx.source_language,
        trace_id=ctx.trace_id, cancel_check=ctx.cancel_check,
    )
    out = _decompose_to_artifact(healed)
    out["heal"] = {
        "findings": [
            {"chapter": f.chapter, "scene": f.scene, "type": f.type, "issue": f.issue,
             "fix": f.fix, "applied": f.applied, "skip_reason": f.skip_reason}
            for f in report.findings
        ],
        "edits_applied": report.edits_applied,
    }
    return out


# ── shared readers ───────────────────────────────────────────────────────────────────────────────
def _cast_of(ctx: PassContext) -> list[dict[str, Any]]:
    """The cast, from pass 2's artifact. Passes 3/5/6 all read it; one reader, one shape."""
    return ctx.inputs.get("cast", {}).get("cast", []) or []


# ── DecomposeResult ⇄ artifact ───────────────────────────────────────────────────────────────────
# Passes 6 and 7 both speak `scene_plan`, so the mapping lives in ONE place: pass 7 must be able to
# read back exactly what pass 6 wrote (it heals it IN PLACE), and a round-trip that loses a field
# would silently drop scenes between the two. `test_scene_plan_round_trips` pins it.

def _decompose_to_artifact(result: Any) -> dict[str, Any]:
    return {
        "arc_title": result.arc_title,
        "chapters": [
            {
                "chapter": {
                    "chapter_id": cs.chapter.chapter_id,
                    "title": cs.chapter.title,
                    "sort_order": cs.chapter.sort_order,
                    "beat_role": cs.chapter.beat_role,
                    "intent": cs.chapter.intent,
                },
                "scenes": [
                    {
                        "title": s.title,
                        "synopsis": s.synopsis,
                        "tension": s.tension,
                        "present_entity_ids": [str(e) for e in (s.present_entity_ids or [])],
                        "present_entity_names_unresolved": list(
                            s.present_entity_names_unresolved or [],
                        ),
                        "suggested_k": s.suggested_k,
                    }
                    for s in cs.scenes
                ],
                "warning": cs.warning,
                "exit_state": cs.exit_state.model_dump(mode="json") if cs.exit_state else None,
            }
            for cs in result.chapters
        ],
        "unmapped_beats": list(result.unmapped_beats or []),
        "motif_coverage": dict(result.motif_coverage or {}),
    }


def _artifact_to_decompose(art: dict[str, Any]) -> Any:
    from app.engine.plan import (
        ChapterExitState, ChapterPlan, ChapterScenes, DecomposeResult, ScenePlan,
    )

    chapters: list[ChapterScenes] = []
    for ch in art.get("chapters", []) or []:
        cp = ch.get("chapter") or {}
        exit_raw = ch.get("exit_state")
        chapters.append(ChapterScenes(
            chapter=ChapterPlan(
                chapter_id=str(cp.get("chapter_id") or ""),
                title=str(cp.get("title") or ""),
                sort_order=int(cp.get("sort_order") or 0),
                beat_role=cp.get("beat_role"),
                intent=str(cp.get("intent") or ""),
            ),
            scenes=[
                ScenePlan(
                    title=str(s.get("title") or ""),
                    synopsis=str(s.get("synopsis") or ""),
                    tension=s.get("tension"),
                    present_entity_ids=[UUID(e) for e in (s.get("present_entity_ids") or [])],
                    present_entity_names_unresolved=list(
                        s.get("present_entity_names_unresolved") or [],
                    ),
                    suggested_k=s.get("suggested_k"),
                )
                for s in (ch.get("scenes") or [])
            ],
            warning=ch.get("warning"),
            exit_state=ChapterExitState(**exit_raw) if exit_raw else None,
        ))
    return DecomposeResult(
        arc_title=str(art.get("arc_title") or ""),
        chapters=chapters,
        unmapped_beats=list(art.get("unmapped_beats") or []),
        motif_coverage=dict(art.get("motif_coverage") or {}),
    )


#: pass_id → adapter. `plan_pass_service.PASS_REGISTRY` is the contract; this is its implementation,
#: and the test that asserts the two key sets are EQUAL is what stops a pass from being declared and
#: never wired (a registry entry with no adapter is a pass that 500s the first time anyone runs it).
PASS_ADAPTERS: dict[PlanPassId, Callable[[PassContext], Awaitable[dict[str, Any]]]] = {
    "motifs": run_motifs,
    "cast": run_cast,
    "world": run_world,
    "beats": run_beats,
    "character_arcs": run_character_arcs,
    "scenes": run_scenes,
    "self_heal": run_self_heal,
}
