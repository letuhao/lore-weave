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
from app.engine.cast_plan import propose_cast
from app.engine.character_plan import plan_character_arcs
from app.engine.grounded_plan import grounded_decompose
from app.engine.motif_plan import select_arc_motifs
from app.engine.plan import (
    ChapterPlan, DecomposeResult, _llm_json,
    build_chapter_map_messages, parse_chapter_map,
)
from app.engine.plan_heal import PlanHealReport, run_plan_self_heal

logger = logging.getLogger(__name__)


@dataclass
class PipelineResult:
    decompose: DecomposeResult
    cast: list[dict[str, Any]] = field(default_factory=list)        # {name, role, is_new}
    motifs: list[dict[str, str]] = field(default_factory=list)      # {name, arc_role}
    char_arcs: list[dict[str, Any]] = field(default_factory=list)   # {name, introduce_at_chapter}
    heal_report: PlanHealReport | None = None


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
    if seed_cast and cast_objs:
        await glossary.seed_entities(
            book_id, source_language=source_language,
            entities=[{"kind_code": "character", "name": c.name} for c in cast_objs])
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
    l1 = await _llm_json(llm, system=sys1, user=usr1, max_tokens=2048, **mk)
    if l1 is not None:
        beat_keys = {b.get("key") for b in beats if isinstance(b.get("key"), str)}
        mapped, _ = parse_chapter_map(l1, chapters, beat_keys)
    beat_roles = [ch.beat_role for ch in mapped]

    # ── Stage 3 — character arcs + introduction schedule.
    arcs = await plan_character_arcs(llm, premise=premise, cast=cast_chars,
                                     beat_roles=beat_roles, source_language=source_language, **mk)
    arc_dicts = [{"name": a.name, "introduce_at_chapter": a.introduce_at_chapter} for a in arcs]

    # ── Stage 4 — grounded decompose (pre-mapped chapters ⇒ skips its own L1).
    result = await grounded_decompose(
        llm, arc_title="Arc 1", premise=premise, beats=beats, chapters=mapped,
        cast=cast_decompose, motifs=motifs, char_arcs=arc_dicts,
        k_ceiling=k_ceiling, high_threshold=high_threshold,
        min_scenes=min_scenes, max_scenes=max_scenes, source_language=source_language, **mk)

    # ── Stage 5 — plan self-heal (optional).
    heal_report: PlanHealReport | None = None
    if self_heal:
        result, heal_report = await run_plan_self_heal(
            llm, result, source_language=source_language, **mk)

    return PipelineResult(decompose=result, cast=cast_chars, motifs=motifs,
                          char_arcs=arc_dicts, heal_report=heal_report)
